#!/usr/bin/env python3
"""Fetch popular movie data from TMDB and save it as CSV."""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


BASE_URL = "https://api.themoviedb.org/3"
KOBIS_BASE_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest"
DEFAULT_TOKEN_FILE = Path("config/tmdb_token.txt")
DEFAULT_KOBIS_KEY_FILE = Path("config/kobis_key.txt")
DEFAULT_OUTPUT_FILE = Path("data/popular_movies.csv")
NULL_VALUE = "null"

CSV_FIELDS = [
    "rank",
    "tmdb_id",
    "title",
    "original_title",
    "original_language",
    "release_date",
    "release_year",
    "popularity",
    "vote_average",
    "vote_count",
    "adult",
    "video",
    "genre_ids",
    "genres",
    "runtime",
    "status",
    "tagline",
    "budget",
    "revenue",
    "homepage",
    "imdb_id",
    "production_companies",
    "production_countries",
    "spoken_languages",
    "cast",
    "directors",
    "keywords",
    "overview",
    "poster_url",
    "backdrop_url",
    "kobis_movie_cd",
    "kobis_movie_nm",
    "kobis_open_dt",
    "kobis_match_status",
    "kobis_boxoffice_date",
    "kobis_rank",
    "kobis_audi_acc",
    "kobis_sales_acc",
    "kobis_daily_audi_cnt",
    "kobis_daily_sales_amt",
    "kobis_scrn_cnt",
    "kobis_show_cnt",
    "page",
    "fetched_at",
]

ADULT_LIKE_KEYWORDS = {
    "adult",
    "erotic",
    "erotica",
    "porn",
    "pornography",
    "sexploitation",
    "softcore",
}

ADULT_LIKE_TITLE_TERMS = (
    "19금",
    "av",
    "가슴 큰",
    "동창회의 목적",
    "룸싸롱",
    "마사지",
    "무삭제",
    "불륜",
    "사촌여동생",
    "색녀",
    "섹스",
    "스와핑",
    "아내의 언니",
    "아이돌 섹스",
    "어린 엄마",
    "어린 형수",
    "엄마친구",
    "여대생",
    "여직원들",
    "여친 언니",
    "여자 하숙집",
    "유부녀",
    "정사",
    "젊은 엄마",
    "처제",
    "출장마사지",
    "친구엄마",
    "큰 울 엄마",
    "하숙집",
    "형수",
)

ADULT_LIKE_ALLOWLIST_TMDB_IDS = {
    670,  # 올드보이
    17903,  # 쌍화점
    290098,  # 아가씨
    269955,  # 인간중독
    287649,  # 마담 뺑덕
    50727,  # 방자전
    49797,  # 악마를 보았다
    705996,  # 헤어질 결심
    491584,  # 버닝
    45202,  # 하녀
    50476,  # 스캔들: 조선남녀상열지사
}


class TmdbError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TMDB popular movies API를 호출해 영화 정보를 CSV로 저장합니다."
    )
    parser.add_argument(
        "--init-key",
        action="store_true",
        help="API Key 또는 Read Access Token을 입력받아 파일에 저장합니다.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help=f"키를 읽거나 저장할 파일 경로입니다. 기본값: {DEFAULT_TOKEN_FILE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"CSV 저장 경로입니다. 기본값: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="기존 TMDB CSV를 읽어 KOBIS 조인만 수행할 때 사용할 입력 파일입니다.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="가져올 페이지 수입니다. TMDB popular API는 페이지당 20개를 반환합니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="필터링 후 저장할 최대 영화 수입니다.",
    )
    parser.add_argument(
        "--language",
        default="ko-KR",
        help="응답 언어입니다. 예: ko-KR, en-US",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="선택 지역 코드입니다. 예: KR, US",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="API 호출 사이 대기 시간(초)입니다.",
    )
    parser.add_argument(
        "--cast-limit",
        type=int,
        default=10,
        help="CSV에 저장할 주요 출연진 수입니다.",
    )
    parser.add_argument(
        "--basic-only",
        action="store_true",
        help="상세 정보 API를 호출하지 않고 인기 목록 기본 정보만 저장합니다.",
    )
    parser.add_argument(
        "--korean-only",
        action="store_true",
        help="TMDB에서 한국어 원어 영화만 인기도순으로 가져옵니다.",
    )
    parser.add_argument(
        "--exclude-adult-like",
        action="store_true",
        help="성인 비디오성 영화로 보이는 항목을 제목과 TMDB 키워드 기준으로 제외합니다.",
    )
    parser.add_argument(
        "--join-kobis",
        action="store_true",
        help="KOBIS 영화코드와 박스오피스 관객수 데이터를 조인합니다.",
    )
    parser.add_argument(
        "--kobis-key-file",
        type=Path,
        default=DEFAULT_KOBIS_KEY_FILE,
        help=f"KOBIS 키 파일 경로입니다. 기본값: {DEFAULT_KOBIS_KEY_FILE}",
    )
    parser.add_argument(
        "--kobis-scan-days",
        type=int,
        default=60,
        help="KOBIS 누적 관객수 탐색을 위해 개봉일부터 스캔할 일수입니다.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="진행 로그를 출력하지 않습니다.",
    )
    return parser.parse_args()


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message, flush=True)


def save_token(token_file: Path) -> None:
    token = getpass.getpass("TMDB API Key 또는 Read Access Token 입력: ").strip()
    if not token:
        raise TmdbError("입력된 키가 없습니다.")

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"키를 저장했습니다: {token_file}")


def load_token(token_file: Path) -> str:
    env_token = os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_API_KEY")
    if env_token:
        return env_token.strip()

    if not token_file.exists():
        raise TmdbError(
            f"키 파일이 없습니다: {token_file}\n"
            f"먼저 `python3 fetch_popular_movies.py --init-key`를 실행하세요."
        )

    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise TmdbError(f"키 파일이 비어 있습니다: {token_file}")
    return token


def load_kobis_key(kobis_key_file: Path) -> str:
    env_key = os.getenv("KOBIS_API_KEY")
    if env_key:
        return env_key.strip()

    if not kobis_key_file.exists():
        raise TmdbError(f"KOBIS 키 파일이 없습니다: {kobis_key_file}")

    key = kobis_key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise TmdbError(f"KOBIS 키 파일이 비어 있습니다: {kobis_key_file}")
    return key


def is_read_access_token(token: str) -> bool:
    normalized = token.removeprefix("Bearer ").strip()
    return "." in normalized or normalized.startswith("eyJ")


def build_request(url: str, token: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/json",
        "User-Agent": "tmdb-popular-movies-csv/1.0",
    }
    if is_read_access_token(token):
        headers["Authorization"] = f"Bearer {token.removeprefix('Bearer ').strip()}"
    return urllib.request.Request(url, headers=headers, method="GET")


def call_tmdb(
    path: str,
    token: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    query = dict(params or {})
    if not is_read_access_token(token):
        query["api_key"] = token

    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(query)}"
    request = build_request(url, token)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise TmdbError(f"TMDB API 오류 ({exc.code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise TmdbError(f"TMDB API 연결 실패: {exc.reason}") from exc

    return json.loads(body)


def call_kobis(
    path: str,
    key: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    query = dict(params or {})
    query["key"] = key
    url = f"{KOBIS_BASE_URL}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "tmdb-popular-movies-csv/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise TmdbError(f"KOBIS API 오류 ({exc.code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise TmdbError(f"KOBIS API 연결 실패: {exc.reason}") from exc

    payload = json.loads(body)
    if "faultInfo" in payload:
        message = payload["faultInfo"].get("message", payload["faultInfo"])
        raise TmdbError(f"KOBIS API 오류: {message}")
    return payload


def image_url(path: Optional[str]) -> str:
    if not path:
        return ""
    return f"https://image.tmdb.org/t/p/original{path}"


def join_names(items: Iterable[Dict[str, Any]], key: str = "name") -> str:
    return "|".join(str(item.get(key, "")).strip() for item in items if item.get(key))


def cast_summary(cast: Iterable[Dict[str, Any]], limit: int) -> str:
    people = []
    for person in list(cast)[:limit]:
        name = str(person.get("name", "")).strip()
        character = str(person.get("character", "")).strip()
        if not name:
            continue
        people.append(f"{name}({character})" if character else name)
    return "|".join(people)


def directors_summary(crew: Iterable[Dict[str, Any]]) -> str:
    directors = [
        person
        for person in crew
        if person.get("job") == "Director" and person.get("name")
    ]
    return join_names(directors)


def normalize_text(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def release_year(value: Any) -> str:
    release_dt = parse_date(value)
    return str(release_dt.year) if release_dt else ""


def adult_like_reason(
    movie: Dict[str, Any],
    detail: Optional[Dict[str, Any]] = None,
) -> str:
    if movie.get("id") in ADULT_LIKE_ALLOWLIST_TMDB_IDS:
        return ""

    if is_true(movie.get("adult")):
        return "adult flag"

    title_text = " ".join(
        str(movie.get(key, "")).lower()
        for key in ("title", "original_title")
    )
    for term in ADULT_LIKE_TITLE_TERMS:
        if term.lower() in title_text:
            return f"title term: {term}"

    if not detail:
        return ""

    keywords = detail.get("keywords") if isinstance(detail.get("keywords"), dict) else {}
    keyword_items = keywords.get("keywords", []) if isinstance(keywords, dict) else []
    for item in keyword_items:
        keyword = str(item.get("name", "")).strip().lower()
        if keyword in ADULT_LIKE_KEYWORDS:
            return f"keyword: {keyword}"

    return ""


def fetch_movie_detail(
    movie_id: Any,
    token: str,
    language: str,
) -> Dict[str, Any]:
    return call_tmdb(
        f"/movie/{movie_id}",
        token,
        {
            "append_to_response": "credits,keywords",
            "language": language,
        },
    )


def movie_to_row(
    movie: Dict[str, Any],
    rank: int,
    page: int,
    fetched_at: str,
    detail: Optional[Dict[str, Any]],
    cast_limit: int,
) -> Dict[str, Any]:
    detail = detail or {}
    credits = detail.get("credits") if isinstance(detail.get("credits"), dict) else {}
    keywords = detail.get("keywords") if isinstance(detail.get("keywords"), dict) else {}
    keyword_items = keywords.get("keywords", []) if isinstance(keywords, dict) else []
    genres = detail.get("genres", []) or []
    release_date = movie.get("release_date", "")

    return {
        "rank": rank,
        "tmdb_id": movie.get("id", ""),
        "title": movie.get("title", ""),
        "original_title": movie.get("original_title", ""),
        "original_language": movie.get("original_language", ""),
        "release_date": release_date,
        "release_year": release_year(release_date),
        "popularity": movie.get("popularity", ""),
        "vote_average": movie.get("vote_average", ""),
        "vote_count": movie.get("vote_count", ""),
        "adult": movie.get("adult", ""),
        "video": movie.get("video", ""),
        "genre_ids": "|".join(str(genre_id) for genre_id in movie.get("genre_ids", [])),
        "genres": join_names(genres),
        "runtime": detail.get("runtime", ""),
        "status": detail.get("status", ""),
        "tagline": detail.get("tagline", ""),
        "budget": detail.get("budget", ""),
        "revenue": detail.get("revenue", ""),
        "homepage": detail.get("homepage", ""),
        "imdb_id": detail.get("imdb_id", ""),
        "production_companies": join_names(detail.get("production_companies", []) or []),
        "production_countries": join_names(
            detail.get("production_countries", []) or [], key="iso_3166_1"
        ),
        "spoken_languages": join_names(
            detail.get("spoken_languages", []) or [], key="english_name"
        ),
        "cast": cast_summary(credits.get("cast", []) if credits else [], cast_limit),
        "directors": directors_summary(credits.get("crew", []) if credits else []),
        "keywords": join_names(keyword_items),
        "overview": movie.get("overview", ""),
        "poster_url": image_url(movie.get("poster_path")),
        "backdrop_url": image_url(movie.get("backdrop_path")),
        "kobis_movie_cd": "",
        "kobis_movie_nm": "",
        "kobis_open_dt": "",
        "kobis_match_status": "pending",
        "kobis_boxoffice_date": "",
        "kobis_rank": "",
        "kobis_audi_acc": "",
        "kobis_sales_acc": "",
        "kobis_daily_audi_cnt": "",
        "kobis_daily_sales_amt": "",
        "kobis_scrn_cnt": "",
        "kobis_show_cnt": "",
        "page": page,
        "fetched_at": fetched_at,
    }


def fetch_popular_movies(
    token: str,
    pages: int,
    limit: Optional[int],
    language: str,
    region: Optional[str],
    delay: float,
    include_details: bool,
    cast_limit: int,
    korean_only: bool,
    exclude_adult_like: bool,
    quiet: bool,
) -> List[Dict[str, Any]]:
    if pages < 1:
        raise TmdbError("--pages 값은 1 이상이어야 합니다.")
    if limit is not None and limit < 1:
        raise TmdbError("--limit 값은 1 이상이어야 합니다.")

    rows: List[Dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    log(
        f"수집 시작: pages={pages}, language={language}, "
        f"limit={limit or 'none'}, "
        f"details={'on' if include_details else 'off'}, "
        f"korean_only={'on' if korean_only else 'off'}, "
        f"exclude_adult_like={'on' if exclude_adult_like else 'off'}",
        quiet,
    )

    for page in range(1, pages + 1):
        log(f"[목록] {page}/{pages} 페이지 요청 중", quiet)
        params: Dict[str, Any] = {
            "language": language,
            "page": page,
        }
        if region:
            params["region"] = region

        path = "/movie/popular"
        if korean_only:
            path = "/discover/movie"
            params.update(
                {
                    "sort_by": "popularity.desc",
                    "with_original_language": "ko",
                    "include_adult": "false",
                }
            )

        payload = call_tmdb(path, token, params)
        movies = payload.get("results", [])
        if not isinstance(movies, list):
            raise TmdbError("TMDB 응답 형식이 예상과 다릅니다.")

        log(f"[목록] {page} 페이지에서 {len(movies)}개 영화 확인", quiet)
        for movie in movies:
            detail = None
            title = movie.get("title") or movie.get("original_title") or movie.get("id")
            if exclude_adult_like:
                reason = adult_like_reason(movie)
                if reason:
                    log(f"[제외] {title}: {reason}", quiet)
                    continue

            if include_details:
                log(f"[상세] {len(rows) + 1}번째 영화 조회 중: {title}", quiet)
                detail = fetch_movie_detail(movie.get("id"), token, language)
                if delay > 0:
                    time.sleep(delay)
                if exclude_adult_like:
                    reason = adult_like_reason(movie, detail)
                    if reason:
                        log(f"[제외] {title}: {reason}", quiet)
                        continue

            rank = len(rows) + 1
            rows.append(
                movie_to_row(
                    movie=movie,
                    rank=rank,
                    page=page,
                    fetched_at=fetched_at,
                    detail=detail,
                    cast_limit=cast_limit,
                )
            )
            log(f"[완료] {rank}번째 영화 저장 준비 완료: {title}", quiet)
            if limit and len(rows) >= limit:
                log(f"저장 목표 수에 도달했습니다: limit={limit}", quiet)
                return rows

        total_pages = int(payload.get("total_pages") or page)
        if page >= total_pages:
            log(f"TMDB 전체 페이지 끝에 도달했습니다: total_pages={total_pages}", quiet)
            break
        if delay > 0 and page < pages:
            time.sleep(delay)

    log(f"수집 완료: {len(rows)}개 영화", quiet)
    return rows


def search_kobis_movie(
    key: str,
    row: Dict[str, Any],
    delay: float,
) -> Optional[Dict[str, Any]]:
    release_dt = parse_date(row.get("release_date"))
    release_year = release_dt.year if release_dt else None
    titles = []
    for title_key in ("title", "original_title"):
        title = str(row.get(title_key, "")).strip()
        if title and title not in titles:
            titles.append(title)

    best_movie = None
    best_score = -1
    for title in titles:
        payload = call_kobis(
            "/movie/searchMovieList.json",
            key,
            {
                "movieNm": title,
                "itemPerPage": 10,
            },
        )
        movies = (
            payload.get("movieListResult", {}).get("movieList", [])
            if isinstance(payload.get("movieListResult"), dict)
            else []
        )
        normalized_title = normalize_text(title)
        for movie in movies:
            movie_names = [
                normalize_text(movie.get("movieNm")),
                normalize_text(movie.get("movieNmEn")),
            ]
            score = 0
            if normalized_title in movie_names:
                score += 100
            elif any(normalized_title and normalized_title in name for name in movie_names):
                score += 70

            kobis_open_dt = parse_date(movie.get("openDt"))
            if release_dt and kobis_open_dt == release_dt:
                score += 50
            elif release_year and str(release_year) == str(movie.get("prdtYear", "")):
                score += 20

            if "한국" in str(movie.get("repNationNm", "")):
                score += 10

            if score > best_score:
                best_movie = movie
                best_score = score

        if best_movie:
            break
        if delay > 0:
            time.sleep(delay)

    if best_score < 70:
        return None
    return best_movie


def fetch_daily_boxoffice(
    key: str,
    target_dt: date,
    cache: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    target_text = target_dt.strftime("%Y%m%d")
    if target_text in cache:
        return cache[target_text]

    payload = call_kobis(
        "/boxoffice/searchDailyBoxOfficeList.json",
        key,
        {
            "targetDt": target_text,
            "itemPerPage": 10,
            "repNationCd": "K",
        },
    )
    boxoffice = payload.get("boxOfficeResult", {})
    movies = boxoffice.get("dailyBoxOfficeList", []) if isinstance(boxoffice, dict) else []
    cache[target_text] = movies
    return movies


def find_kobis_boxoffice(
    key: str,
    movie_cd: str,
    open_dt: Optional[date],
    scan_days: int,
    delay: float,
    cache: Dict[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    if not movie_cd or not open_dt or scan_days < 1:
        return None

    today = datetime.now().date()
    best_match = None
    best_audi_acc = -1
    for offset in range(scan_days):
        target_dt = open_dt + timedelta(days=offset)
        if target_dt >= today:
            break

        movies = fetch_daily_boxoffice(key, target_dt, cache)
        for movie in movies:
            if str(movie.get("movieCd", "")) != str(movie_cd):
                continue
            audi_acc = int(str(movie.get("audiAcc") or "0").replace(",", ""))
            if audi_acc >= best_audi_acc:
                best_match = dict(movie)
                best_match["boxofficeDate"] = target_dt.strftime("%Y-%m-%d")
                best_audi_acc = audi_acc

        if delay > 0:
            time.sleep(delay)

    return best_match


def clear_kobis_values(row: Dict[str, Any]) -> None:
    for field in (
        "kobis_movie_cd",
        "kobis_movie_nm",
        "kobis_open_dt",
        "kobis_boxoffice_date",
        "kobis_rank",
        "kobis_audi_acc",
        "kobis_sales_acc",
        "kobis_daily_audi_cnt",
        "kobis_daily_sales_amt",
        "kobis_scrn_cnt",
        "kobis_show_cnt",
    ):
        row[field] = NULL_VALUE


def fill_kobis_boxoffice(row: Dict[str, Any], boxoffice: Dict[str, Any]) -> None:
    row["kobis_match_status"] = "matched_boxoffice"
    row["kobis_boxoffice_date"] = boxoffice.get("boxofficeDate", "") or NULL_VALUE
    row["kobis_rank"] = boxoffice.get("rank", "") or NULL_VALUE
    row["kobis_audi_acc"] = boxoffice.get("audiAcc", "") or NULL_VALUE
    row["kobis_sales_acc"] = boxoffice.get("salesAcc", "") or NULL_VALUE
    row["kobis_daily_audi_cnt"] = boxoffice.get("audiCnt", "") or NULL_VALUE
    row["kobis_daily_sales_amt"] = boxoffice.get("salesAmt", "") or NULL_VALUE
    row["kobis_scrn_cnt"] = boxoffice.get("scrnCnt", "") or NULL_VALUE
    row["kobis_show_cnt"] = boxoffice.get("showCnt", "") or NULL_VALUE


def enrich_row_with_kobis(
    row: Dict[str, Any],
    kobis_key: str,
    scan_days: int,
    delay: float,
    boxoffice_cache: Dict[str, List[Dict[str, Any]]],
) -> None:
    movie = search_kobis_movie(kobis_key, row, delay)
    if not movie:
        clear_kobis_values(row)
        row["kobis_match_status"] = "not_found"
        return

    row["kobis_movie_cd"] = movie.get("movieCd", "") or NULL_VALUE
    row["kobis_movie_nm"] = movie.get("movieNm", "") or NULL_VALUE
    row["kobis_open_dt"] = movie.get("openDt", "") or NULL_VALUE

    open_dt = parse_date(movie.get("openDt")) or parse_date(row.get("release_date"))
    boxoffice = find_kobis_boxoffice(
        kobis_key,
        str(movie.get("movieCd", "")),
        open_dt,
        scan_days,
        delay,
        boxoffice_cache,
    )
    if not boxoffice:
        row["kobis_match_status"] = "matched_no_boxoffice"
        for field in (
            "kobis_boxoffice_date",
            "kobis_rank",
            "kobis_audi_acc",
            "kobis_sales_acc",
            "kobis_daily_audi_cnt",
            "kobis_daily_sales_amt",
            "kobis_scrn_cnt",
            "kobis_show_cnt",
        ):
            row[field] = NULL_VALUE
        return

    fill_kobis_boxoffice(row, boxoffice)


def enrich_rows_with_kobis(
    rows: List[Dict[str, Any]],
    kobis_key: str,
    scan_days: int,
    delay: float,
    quiet: bool,
) -> None:
    boxoffice_cache: Dict[str, List[Dict[str, Any]]] = {}
    total = len(rows)
    log(f"KOBIS 조인 시작: {total}개 영화, scan_days={scan_days}", quiet)

    for index, row in enumerate(rows, start=1):
        title = row.get("title") or row.get("original_title") or row.get("tmdb_id")
        log(f"[KOBIS] {index}/{total} 영화 매칭 중: {title}", quiet)
        movie = search_kobis_movie(kobis_key, row, delay)
        if not movie:
            clear_kobis_values(row)
            row["kobis_match_status"] = "not_found"
            log(f"[KOBIS] 매칭 실패: {title}", quiet)
            continue

        row["kobis_movie_cd"] = movie.get("movieCd", "") or NULL_VALUE
        row["kobis_movie_nm"] = movie.get("movieNm", "") or NULL_VALUE
        row["kobis_open_dt"] = movie.get("openDt", "") or NULL_VALUE
        row["kobis_match_status"] = "matched"

        open_dt = parse_date(movie.get("openDt")) or parse_date(row.get("release_date"))
        boxoffice = find_kobis_boxoffice(
            kobis_key,
            str(movie.get("movieCd", "")),
            open_dt,
            scan_days,
            delay,
            boxoffice_cache,
        )
        if not boxoffice:
            row["kobis_match_status"] = "matched_no_boxoffice"
            log(f"[KOBIS] 박스오피스 관객수 없음: {title}", quiet)
            continue

        fill_kobis_boxoffice(row, boxoffice)
        log(
            f"[KOBIS] 관객수 조인 완료: {title} "
            f"audiAcc={row['kobis_audi_acc']} date={row['kobis_boxoffice_date']}",
            quiet,
        )


def write_csv(rows: Iterable[Dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_suffix(output.suffix + ".tmp")
    with temp_output.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    temp_output.replace(output)


def read_csv(input_file: Path) -> List[Dict[str, Any]]:
    if not input_file.exists():
        raise TmdbError(f"입력 CSV가 없습니다: {input_file}")

    with input_file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = [{field: row.get(field, "") for field in CSV_FIELDS} for row in reader]

    if not rows:
        raise TmdbError(f"입력 CSV에 데이터가 없습니다: {input_file}")
    return rows


def load_kobis_resume_rows(input_file: Path, output: Path) -> List[Dict[str, Any]]:
    if input_file.resolve() == output.resolve():
        raise TmdbError("KOBIS 결과 CSV는 원본 입력 CSV와 다른 경로로 지정해야 합니다.")

    if output.exists():
        return read_csv(output)

    rows = read_csv(input_file)
    write_csv(rows, output)
    return rows


def enrich_csv_with_kobis_incrementally(
    input_file: Path,
    output: Path,
    kobis_key: str,
    scan_days: int,
    delay: float,
    quiet: bool,
) -> List[Dict[str, Any]]:
    rows = load_kobis_resume_rows(input_file, output)
    boxoffice_cache: Dict[str, List[Dict[str, Any]]] = {}
    pending_statuses = {"", "pending"}
    total = len(rows)
    processed = 0

    log(
        f"KOBIS CSV 조인 시작: input={input_file}, output={output}, "
        f"rows={total}, scan_days={scan_days}",
        quiet,
    )

    for index, row in enumerate(rows, start=1):
        status = str(row.get("kobis_match_status", "")).strip()
        if status not in pending_statuses:
            continue

        title = row.get("title") or row.get("original_title") or row.get("tmdb_id")
        log(f"[KOBIS] {index}/{total} 처리 중: {title}", quiet)
        try:
            enrich_row_with_kobis(
                row,
                kobis_key=kobis_key,
                scan_days=scan_days,
                delay=delay,
                boxoffice_cache=boxoffice_cache,
            )
        except TmdbError:
            write_csv(rows, output)
            raise

        processed += 1
        write_csv(rows, output)
        log(
            f"[KOBIS] {index}/{total} 저장 완료: "
            f"status={row.get('kobis_match_status')} "
            f"audiAcc={row.get('kobis_audi_acc')}",
            quiet,
        )

    log(f"KOBIS CSV 조인 완료: 이번 실행 처리={processed}개", quiet)
    return rows


def main() -> int:
    args = parse_args()

    try:
        if args.init_key:
            save_token(args.token_file)
            return 0

        if args.input:
            if not args.join_kobis:
                raise TmdbError("--input 사용 시 --join-kobis를 함께 지정해야 합니다.")
            kobis_key = load_kobis_key(args.kobis_key_file)
            rows = enrich_csv_with_kobis_incrementally(
                input_file=args.input,
                output=args.output,
                kobis_key=kobis_key,
                scan_days=args.kobis_scan_days,
                delay=args.delay,
                quiet=args.quiet,
            )
        else:
            token = load_token(args.token_file)
            rows = fetch_popular_movies(
                token=token,
                pages=args.pages,
                limit=args.limit,
                language=args.language,
                region=args.region,
                delay=args.delay,
                include_details=not args.basic_only,
                cast_limit=args.cast_limit,
                korean_only=args.korean_only,
                exclude_adult_like=args.exclude_adult_like,
                quiet=args.quiet,
            )
            if args.join_kobis:
                kobis_key = load_kobis_key(args.kobis_key_file)
                enrich_rows_with_kobis(
                    rows,
                    kobis_key=kobis_key,
                    scan_days=args.kobis_scan_days,
                    delay=args.delay,
                    quiet=args.quiet,
                )
            log(f"CSV 저장 중: {args.output}", args.quiet)
            write_csv(rows, args.output)
    except TmdbError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{len(rows)}개 영화 정보를 저장했습니다: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
