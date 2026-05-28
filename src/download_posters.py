#!/usr/bin/env python3
"""Download movie poster images from a CSV file."""

from __future__ import annotations

import argparse
import csv
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_INPUT_FILE = Path("data/kobis_tmdb_title_matches.csv")
DEFAULT_OUTPUT_DIR = Path("data/posters")
DEFAULT_TITLE_FIELDS = ("match_title", "title", "tmdb_title")
DEFAULT_POSTER_FIELDS = ("tmdb_poster_url", "poster_url")
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CSV의 포스터 URL을 내려받아 한국어 영화 제목.jpg 형식으로 저장합니다."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_FILE,
        help=f"입력 CSV 경로입니다. 기본값: {DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"포스터 저장 디렉터리입니다. 기본값: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--title-field",
        default=None,
        help="영화 제목 컬럼명입니다. 생략하면 match_title, title, tmdb_title 순서로 찾습니다.",
    )
    parser.add_argument(
        "--poster-field",
        default=None,
        help="포스터 URL 컬럼명입니다. 생략하면 tmdb_poster_url, poster_url 순서로 찾습니다.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="이미 같은 이름의 파일이 있으면 덮어씁니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="다운로드할 최대 포스터 수입니다.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="다운로드 요청 사이 대기 시간(초)입니다. 기본값: 0.1",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="요청 타임아웃(초)입니다. 기본값: 20",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 다운로드 없이 저장될 파일명만 확인합니다.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError(f"CSV 헤더를 찾을 수 없습니다: {path}")
        return reader.fieldnames, list(reader)


def select_field(
    fieldnames: Iterable[str], requested_field: str | None, candidates: Iterable[str]
) -> str:
    fields = set(fieldnames)
    if requested_field:
        if requested_field not in fields:
            raise ValueError(f"CSV에 컬럼이 없습니다: {requested_field}")
        return requested_field

    for field in candidates:
        if field in fields:
            return field

    raise ValueError(f"사용 가능한 컬럼을 찾지 못했습니다: {', '.join(candidates)}")


def sanitize_filename(value: str) -> str:
    filename = INVALID_FILENAME_CHARS.sub("_", value.strip())
    filename = re.sub(r"\s+", " ", filename)
    filename = filename.strip(". ")
    if not filename:
        raise ValueError("파일명으로 사용할 수 없는 빈 제목입니다.")
    return filename


def poster_path(output_dir: Path, title: str) -> Path:
    return output_dir / f"{sanitize_filename(title)}.jpg"


def download_file(url: str, output_path: Path, timeout: float) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        output_path.write_bytes(response.read())


def main() -> None:
    args = parse_args()
    fieldnames, rows = read_csv(args.input)
    title_field = select_field(fieldnames, args.title_field, DEFAULT_TITLE_FIELDS)
    poster_field = select_field(fieldnames, args.poster_field, DEFAULT_POSTER_FIELDS)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    skip_count = 0
    fail_count = 0

    for row in rows:
        if args.limit is not None and success_count >= args.limit:
            break

        title = row.get(title_field, "").strip()
        poster_url = row.get(poster_field, "").strip()
        if not title or not poster_url:
            skip_count += 1
            continue

        output_path = poster_path(args.output_dir, title)
        if output_path.exists() and not args.overwrite:
            print(f"skip exists: {output_path}")
            skip_count += 1
            continue

        if args.dry_run:
            print(f"dry-run: {title} -> {output_path}")
            success_count += 1
            continue

        try:
            download_file(poster_url, output_path, args.timeout)
            print(f"downloaded: {title} -> {output_path}")
            success_count += 1
            if args.delay > 0:
                time.sleep(args.delay)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as error:
            print(f"failed: {title} ({error})")
            fail_count += 1

    print(f"success: {success_count}")
    print(f"skipped: {skip_count}")
    print(f"failed: {fail_count}")
    print(f"output_dir: {args.output_dir}")


if __name__ == "__main__":
    main()
