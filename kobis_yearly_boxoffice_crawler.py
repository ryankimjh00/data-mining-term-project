#!/usr/bin/env python3
"""Crawl KOBIS official yearly box office data and save it as CSV."""

from __future__ import annotations

import argparse
import csv
import html
import http.cookiejar
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_URL = "https://www.kobis.or.kr"
YEARLY_BOXOFFICE_PATH = "/kobis/business/stat/offc/findYearlyBoxOfficeList.do"
DEFAULT_OUTPUT_FILE = Path("data/kobis_yearly_boxoffice_korean.csv")
NATION_LABELS = {
    "": "전체",
    "K": "한국",
    "F": "외국",
}
MOVIE_TYPE_LABELS = {
    "": "전체",
    "Y": "독립·예술영화",
    "N": "일반영화",
}
CSV_FIELDS = [
    "search_year",
    "rank",
    "movie_code",
    "movie_name",
    "open_date",
    "sales_amount",
    "sales_share",
    "audience_count",
    "screen_count",
    "nation",
    "movie_type",
    "final_base_year_month",
    "crawled_at",
]


class KobisCrawlerError(RuntimeError):
    pass


class YearOptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_year_select = False
        self.options: List[Tuple[int, bool]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        if tag == "select" and attr_map.get("id") == "sSearchYearFrom":
            self.in_year_select = True
            return

        if self.in_year_select and tag == "option":
            value = attr_map.get("value", "")
            if value and value.isdigit():
                self.options.append((int(value), "selected" in attr_map))

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self.in_year_select:
            self.in_year_select = False


class ResultTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: List[Dict[str, str]] = []
        self.current_row: Optional[Dict[str, str]] = None
        self.current_cell_id = ""
        self.current_cell_text: List[str] = []
        self.movie_title = ""
        self.movie_code = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        if tag == "tr" and str(attr_map.get("id", "")).startswith("tr_tot"):
            self.current_row = {}
            return

        if self.current_row is None:
            return

        if tag == "td":
            self.current_cell_id = str(attr_map.get("id", ""))
            self.current_cell_text = []
            return

        if tag == "a" and self.current_cell_id == "td_movie":
            self.movie_title = str(attr_map.get("title") or "")
            onclick = str(attr_map.get("onclick") or "")
            match = re.search(r"mstView\('movie','([^']+)'\)", onclick)
            if match:
                self.movie_code = match.group(1)

    def handle_data(self, data: str) -> None:
        if self.current_row is not None and self.current_cell_id:
            self.current_cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.current_row is not None and self.current_cell_id:
            text = normalize_space("".join(self.current_cell_text))
            if self.current_cell_id == "td_movie" and self.movie_title:
                text = self.movie_title
            self.current_row[self.current_cell_id] = text
            self.current_cell_id = ""
            self.current_cell_text = []
            return

        if tag == "tr" and self.current_row is not None:
            if "td_rank" in self.current_row:
                self.current_row["movie_code"] = self.movie_code
                self.rows.append(self.current_row)
            self.current_row = None
            self.current_cell_id = ""
            self.current_cell_text = []
            self.movie_title = ""
            self.movie_code = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KOBIS 공식통계 연도별 박스오피스 화면을 조회해 CSV로 저장합니다."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="조회할 연도입니다. 생략하면 사이트 기본 선택 연도를 사용합니다.",
    )
    parser.add_argument(
        "--all-years",
        action="store_true",
        help="사이트 조회기간 드롭다운의 모든 연도를 수집합니다.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="여러 연도 수집 시 시작 연도입니다.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="여러 연도 수집 시 종료 연도입니다.",
    )
    parser.add_argument(
        "--nation",
        choices=sorted(NATION_LABELS.keys()),
        default="K",
        help="국적 필터입니다. K=한국, F=외국, 빈 값=전체. 기본값: K",
    )
    parser.add_argument(
        "--movie-type",
        choices=sorted(MOVIE_TYPE_LABELS.keys()),
        default="",
        help="영화구분 필터입니다. Y=독립·예술영화, N=일반영화, 빈 값=전체.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"CSV 저장 경로입니다. 기본값: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="연도별 요청 사이 대기 시간(초)입니다.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="진행 로그를 출력하지 않습니다.",
    )
    return parser.parse_args()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize_number(value: str) -> str:
    return normalize_space(value).replace(",", "")


def normalize_percent(value: str) -> str:
    return normalize_space(value).replace("%", "")


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message, flush=True)


def build_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def request_html(
    opener: urllib.request.OpenerDirector,
    data: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> str:
    url = f"{BASE_URL}{YEARLY_BOXOFFICE_PATH}"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": "kobis-yearly-boxoffice-csv/1.0",
    }
    encoded_data = None
    if data is not None:
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Origin"] = BASE_URL
        headers["Referer"] = url

    request = urllib.request.Request(
        url,
        data=encoded_data,
        headers=headers,
        method="POST" if data is not None else "GET",
    )

    try:
        with opener.open(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise KobisCrawlerError(f"KOBIS 조회 실패 ({exc.code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise KobisCrawlerError(f"KOBIS 연결 실패: {exc.reason}") from exc


def parse_csrf_token(page_html: str) -> str:
    matches = re.findall(r'name="CSRFToken"\s+value="([^"]+)"', page_html)
    if not matches:
        raise KobisCrawlerError("CSRFToken을 찾지 못했습니다.")
    return html.unescape(matches[-1])


def parse_year_options(page_html: str) -> Tuple[List[int], int]:
    parser = YearOptionParser()
    parser.feed(page_html)
    years = [year for year, _ in parser.options]
    selected_years = [year for year, selected in parser.options if selected]
    if not years:
        raise KobisCrawlerError("조회기간 연도 목록을 찾지 못했습니다.")
    return years, selected_years[-1] if selected_years else years[-1]


def parse_final_base_year_month(page_html: str) -> str:
    match = re.search(r"최종\s*기준년월\s*:\s*([0-9]{4}/[0-9]{2})", page_html)
    return match.group(1) if match else ""


def parse_result_rows(page_html: str, year: int, args: argparse.Namespace) -> List[Dict[str, str]]:
    parser = ResultTableParser()
    parser.feed(page_html)
    final_base_year_month = parse_final_base_year_month(page_html)
    crawled_at = datetime.now(timezone.utc).isoformat()
    rows = []

    for item in parser.rows:
        rows.append(
            {
                "search_year": str(year),
                "rank": normalize_number(item.get("td_rank", "")),
                "movie_code": item.get("movie_code", ""),
                "movie_name": item.get("td_movie", ""),
                "open_date": item.get("td_openDt", ""),
                "sales_amount": normalize_number(item.get("td_totSalesAcc", "")),
                "sales_share": normalize_percent(item.get("td_totSalesShare", "")),
                "audience_count": normalize_number(item.get("td_totAudiAcc", "")),
                "screen_count": normalize_number(item.get("td_totScrnCnt", "")),
                "nation": NATION_LABELS[args.nation],
                "movie_type": MOVIE_TYPE_LABELS[args.movie_type],
                "final_base_year_month": final_base_year_month,
                "crawled_at": crawled_at,
            }
        )

    return rows


def choose_years(available_years: Iterable[int], default_year: int, args: argparse.Namespace) -> List[int]:
    years = sorted(set(available_years))
    if args.all_years:
        selected = years
    elif args.start_year is not None or args.end_year is not None:
        start_year = args.start_year if args.start_year is not None else min(years)
        end_year = args.end_year if args.end_year is not None else max(years)
        selected = [year for year in years if start_year <= year <= end_year]
    else:
        selected = [args.year or default_year]

    unknown_years = [year for year in selected if year not in years]
    if unknown_years:
        available = f"{min(years)}-{max(years)}"
        raise KobisCrawlerError(f"지원하지 않는 조회 연도입니다: {unknown_years} (가능 범위: {available})")

    return selected


def fetch_year(
    opener: urllib.request.OpenerDirector,
    csrf_token: str,
    year: int,
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, str]], str]:
    payload = {
        "CSRFToken": csrf_token,
        "loadEnd": "0",
        "searchType": "search",
        "sSearchYearFrom": str(year),
        "sMultiMovieYn": args.movie_type,
        "sRepNationCd": args.nation,
    }
    page_html = request_html(opener, payload)
    rows = parse_result_rows(page_html, year, args)
    return rows, parse_csrf_token(page_html)


def write_csv(rows: List[Dict[str, str]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    opener = build_opener()

    log("KOBIS 연도별 박스오피스 페이지를 불러오는 중입니다.", args.quiet)
    initial_html = request_html(opener)
    csrf_token = parse_csrf_token(initial_html)
    available_years, default_year = parse_year_options(initial_html)
    years = choose_years(available_years, default_year, args)

    all_rows: List[Dict[str, str]] = []
    for index, year in enumerate(years, start=1):
        log(f"[{index}/{len(years)}] {year}년 국적={NATION_LABELS[args.nation]} 조회 중", args.quiet)
        rows, csrf_token = fetch_year(opener, csrf_token, year, args)
        log(f"  - {len(rows)}건 수집", args.quiet)
        all_rows.extend(rows)
        if index < len(years) and args.delay > 0:
            time.sleep(args.delay)

    write_csv(all_rows, args.output)
    log(f"CSV 저장 완료: {args.output} ({len(all_rows)}건)", args.quiet)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KobisCrawlerError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
