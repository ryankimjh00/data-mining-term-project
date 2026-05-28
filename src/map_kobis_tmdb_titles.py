#!/usr/bin/env python3
"""Map KOBIS and TMDB CSV rows by matching Korean movie titles."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_KOBIS_FILE = Path("data/kobis_yearly_boxoffice_korean_all_years.csv")
DEFAULT_TMDB_FILE = Path("data/tmdb_korean_movies.csv")
DEFAULT_OUTPUT_FILE = Path("data/kobis_tmdb_title_matches.csv")
KOBIS_TITLE_FIELD = "movie_name"
TMDB_TITLE_FIELD = "title"
PRIMARY_KOBIS_FIELDS = [
    "open_date",
    "sales_amount",
    "sales_share",
    "audience_count",
    "screen_count",
]
EXCLUDED_KOBIS_FIELDS = {
    "movie_name",
    "nation",
    "final_base_year_month",
    "crawled_at",
}
EXCLUDED_TMDB_FIELDS = {
    "overview",
    "imdb_id",
    "spoken_languages",
    "production_countries",
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
    "title",
    "original_language",
    "adult",
    "video",
    "status",
    "homepage",
    "tmdb_id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KOBIS/TMDB CSV에서 영화 제목이 일치하는 행을 병합해 저장합니다."
    )
    parser.add_argument(
        "--kobis",
        type=Path,
        default=DEFAULT_KOBIS_FILE,
        help=f"KOBIS CSV 경로입니다. 기본값: {DEFAULT_KOBIS_FILE}",
    )
    parser.add_argument(
        "--tmdb",
        type=Path,
        default=DEFAULT_TMDB_FILE,
        help=f"TMDB CSV 경로입니다. 기본값: {DEFAULT_TMDB_FILE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"저장할 CSV 경로입니다. 기본값: {DEFAULT_OUTPUT_FILE}",
    )
    return parser.parse_args()


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_csv(path: Path) -> tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError(f"CSV 헤더를 찾을 수 없습니다: {path}")
        return reader.fieldnames, list(reader)


def require_field(fieldnames: Iterable[str], field: str, path: Path) -> None:
    if field not in fieldnames:
        raise ValueError(f"필수 컬럼이 없습니다: {path} ({field})")


def prefixed_fields(prefix: str, fields: Iterable[str]) -> List[str]:
    return [f"{prefix}{field}" for field in fields]


def main() -> None:
    args = parse_args()
    kobis_fields, kobis_rows = read_csv(args.kobis)
    tmdb_fields, tmdb_rows = read_csv(args.tmdb)

    require_field(kobis_fields, KOBIS_TITLE_FIELD, args.kobis)
    require_field(tmdb_fields, TMDB_TITLE_FIELD, args.tmdb)
    for field in PRIMARY_KOBIS_FIELDS:
        require_field(kobis_fields, field, args.kobis)

    tmdb_output_fields = [
        field for field in tmdb_fields if field not in EXCLUDED_TMDB_FIELDS
    ]
    kobis_prefixed_fields = [
        field
        for field in kobis_fields
        if field not in PRIMARY_KOBIS_FIELDS and field not in EXCLUDED_KOBIS_FIELDS
    ]
    tmdb_by_title: dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in tmdb_rows:
        title = normalize_title(row.get(TMDB_TITLE_FIELD, ""))
        if title:
            tmdb_by_title[title].append(row)

    output_fields = (
        ["match_title"]
        + PRIMARY_KOBIS_FIELDS
        + prefixed_fields("kobis_", kobis_prefixed_fields)
        + prefixed_fields("tmdb_", tmdb_output_fields)
    )

    matched_rows: List[Dict[str, str]] = []
    matched_titles: set[str] = set()
    for kobis_row in kobis_rows:
        title = normalize_title(kobis_row.get(KOBIS_TITLE_FIELD, ""))
        if not title or title not in tmdb_by_title:
            continue

        matched_titles.add(title)
        for tmdb_row in tmdb_by_title[title]:
            output_row = {"match_title": title}
            output_row.update(
                {field: kobis_row.get(field, "") for field in PRIMARY_KOBIS_FIELDS}
            )
            output_row.update(
                {
                    f"kobis_{field}": kobis_row.get(field, "")
                    for field in kobis_prefixed_fields
                }
            )
            output_row.update(
                {
                    f"tmdb_{field}": tmdb_row.get(field, "")
                    for field in tmdb_output_fields
                }
            )
            matched_rows.append(output_row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(matched_rows)

    print(f"KOBIS rows: {len(kobis_rows)}")
    print(f"TMDB rows: {len(tmdb_rows)}")
    print(f"Matched unique titles: {len(matched_titles)}")
    print(f"Matched output rows: {len(matched_rows)}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
