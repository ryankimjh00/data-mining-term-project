#!/usr/bin/env python3
"""Build model-ready movie success features from KOBIS/TMDB matched data."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

try:
    from feature_title import create_title_feature_frame
except ImportError:  # pragma: no cover - supports package-style imports
    from .feature_title import create_title_feature_frame


DEFAULT_INPUT_FILE = Path("data/kobis_tmdb_title_matches.csv")
DEFAULT_OUTPUT_FILE = Path("data/processed/movie_features.csv")
DEFAULT_POSTER_FEATURE_FILE = Path("data/processed/poster_features.csv")
DEFAULT_TITLE_FIELD = "match_title"
SUCCESS_THRESHOLDS = (1_000_000, 3_000_000, 5_000_000, 10_000_000)
SUCCESS_RANK_THRESHOLDS = (
    ("S", 10_000_000),
    ("A", 5_000_000),
    ("B", 3_000_000),
    ("C", 1_000_000),
    ("D", 0),
)
SUCCESS_RANK_CODES = {
    "D": 0,
    "C": 1,
    "B": 2,
    "A": 3,
    "S": 4,
}

NUMERIC_SOURCE_FIELDS = {
    "meta_tmdb_release_year": "tmdb_release_year",
    "meta_tmdb_runtime": "tmdb_runtime",
    "meta_tmdb_budget": "tmdb_budget",
}

LOG_FEATURES = {
    "meta_log_tmdb_budget": "meta_tmdb_budget",
}
TOP_DIRECTOR_FEATURE_LIMIT = 30
TOP_CAST_FEATURE_LIMIT = 50


def parse_thresholds(value: str) -> List[int]:
    thresholds: List[int] = []
    for part in value.split(","):
        text = part.strip().replace("_", "")
        if not text:
            continue
        thresholds.append(int(text))
    if not thresholds:
        raise ValueError("흥행 기준값을 하나 이상 입력해야 합니다.")
    return thresholds


def split_values(value: object) -> List[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null"}:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def clean_cast_name(value: str) -> str:
    return re.sub(r"\([^)]*\)$", "", value).strip()


def safe_feature_name(value: str) -> str:
    normalized = re.sub(r"\s+", "_", value.strip())
    normalized = re.sub(r"[^\w가-힣]+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized or "unknown"


def to_number_series(series):
    import pandas as pd

    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .replace({"": None, "null": None, "nan": None, "None": None}),
        errors="coerce",
    )


def source_series(frame, field: str):
    import pandas as pd

    if field in frame.columns:
        return frame[field]
    return pd.Series([None] * len(frame), index=frame.index)


def add_target_columns(result, raw_frame, thresholds: Sequence[int]):
    import numpy as np

    audience_count = to_number_series(source_series(raw_frame, "audience_count"))
    result["audience_count"] = audience_count
    result["target_log_audience"] = np.log1p(audience_count.clip(lower=0))
    result["success_rank"] = audience_count.map(success_rank)
    result["success_rank_code"] = result["success_rank"].map(SUCCESS_RANK_CODES)
    for threshold in thresholds:
        column = f"is_success_{threshold}"
        result[column] = (audience_count >= threshold).where(audience_count.notna())
    return result


def success_rank(audience_count: float) -> str | None:
    import pandas as pd

    if pd.isna(audience_count):
        return None
    for rank, threshold in SUCCESS_RANK_THRESHOLDS:
        if audience_count >= threshold:
            return rank
    return None


def add_numeric_features(result, raw_frame):
    import numpy as np

    for output_field, source_field in NUMERIC_SOURCE_FIELDS.items():
        result[output_field] = to_number_series(source_series(raw_frame, source_field))

    for output_field, source_field in LOG_FEATURES.items():
        result[output_field] = np.log1p(result[source_field].clip(lower=0))
    return result


def season_from_month(month: float) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "fall"
    if month in (12, 1, 2):
        return "winter"
    return "unknown"


def add_date_features(result, raw_frame):
    import pandas as pd

    open_dates = pd.to_datetime(source_series(raw_frame, "open_date"), errors="coerce")
    open_month = open_dates.dt.month
    result["meta_open_year"] = open_dates.dt.year
    result["meta_open_month"] = open_month
    result["meta_open_quarter"] = open_dates.dt.quarter
    result["meta_is_summer_peak"] = open_month.isin([7, 8]).astype(int)
    result["meta_is_winter_peak"] = open_month.isin([12, 1]).astype(int)
    result["meta_is_year_end"] = (open_month == 12).astype(int)

    seasons = open_month.map(season_from_month)
    result["open_season"] = seasons
    for season in ("spring", "summer", "fall", "winter"):
        result[f"meta_season_{season}"] = (seasons == season).astype(int)
    return result


def add_genre_features(result, raw_frame):
    genre_lists = source_series(raw_frame, "tmdb_genres").map(split_values)
    genres = sorted({genre for values in genre_lists for genre in values})
    for genre in genres:
        column = f"genre_{safe_feature_name(genre)}"
        result[column] = genre_lists.map(lambda values, item=genre: int(item in values))
    result["meta_genre_count"] = genre_lists.map(len)
    return result


def frequency_summary_features(
    result,
    raw_frame,
    source_field: str,
    prefix: str,
    cleaner=None,
):
    value_lists = source_series(raw_frame, source_field).map(split_values)
    if cleaner is not None:
        value_lists = value_lists.map(lambda values: [cleaner(value) for value in values])
    value_lists = value_lists.map(lambda values: [value for value in values if value])

    counts = Counter(value for values in value_lists for value in values)
    result[f"{prefix}_count"] = value_lists.map(len)
    result[f"{prefix}_max_frequency"] = value_lists.map(
        lambda values: max((counts[value] for value in values), default=0)
    )
    result[f"{prefix}_mean_frequency"] = value_lists.map(
        lambda values: (
            sum(counts[value] for value in values) / len(values) if values else 0
        )
    )
    return result


def top_value_indicator_features(
    result,
    raw_frame,
    source_field: str,
    prefix: str,
    limit: int,
    cleaner=None,
):
    value_lists = source_series(raw_frame, source_field).map(split_values)
    if cleaner is not None:
        value_lists = value_lists.map(lambda values: [cleaner(value) for value in values])
    value_lists = value_lists.map(lambda values: [value for value in values if value])

    counts = Counter(value for values in value_lists for value in values)
    top_values = [
        value
        for value, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]

    feature_data = {}
    used_columns: set[str] = set()
    for value in top_values:
        base_column = f"{prefix}_{safe_feature_name(value)}"
        column = base_column
        suffix = 2
        while column in used_columns or column in result.columns:
            column = f"{base_column}_{suffix}"
            suffix += 1
        used_columns.add(column)
        feature_data[column] = value_lists.map(lambda values, item=value: int(item in values))

    if not feature_data:
        return result

    import pandas as pd

    return pd.concat([result, pd.DataFrame(feature_data, index=result.index)], axis=1)


def add_frequency_features(result, raw_frame):
    frequency_summary_features(
        result,
        raw_frame,
        "tmdb_directors",
        "meta_director",
    )
    frequency_summary_features(
        result,
        raw_frame,
        "tmdb_cast",
        "meta_cast",
        cleaner=clean_cast_name,
    )
    frequency_summary_features(
        result,
        raw_frame,
        "tmdb_production_companies",
        "meta_production_company",
    )
    result = top_value_indicator_features(
        result,
        raw_frame,
        "tmdb_directors",
        "meta_top_director",
        TOP_DIRECTOR_FEATURE_LIMIT,
    )
    result = top_value_indicator_features(
        result,
        raw_frame,
        "tmdb_cast",
        "meta_top_cast",
        TOP_CAST_FEATURE_LIMIT,
        cleaner=clean_cast_name,
    )
    return result


def merge_title_features(result, raw_frame, title_field: str):
    title_features = create_title_feature_frame(raw_frame, title_field)
    feature_columns = [column for column in title_features.columns if column.startswith("title_")]
    return result.join(title_features[feature_columns])


def merge_poster_features(result, poster_features_path: Path, title_field: str):
    import pandas as pd

    if not poster_features_path.exists():
        return result

    poster_features = pd.read_csv(poster_features_path, encoding="utf-8-sig")
    if title_field not in poster_features.columns:
        raise ValueError(f"포스터 특성 파일에 제목 컬럼이 없습니다: {title_field}")

    numeric_columns = [
        column
        for column in poster_features.columns
        if column.startswith("poster_") and column != "poster_feature_status"
    ]
    poster_features = poster_features[[title_field] + numeric_columns].drop_duplicates(
        subset=[title_field],
        keep="first",
    )
    return result.merge(poster_features, on=title_field, how="left")


def build_feature_frame(
    raw_frame,
    title_field: str = DEFAULT_TITLE_FIELD,
    thresholds: Sequence[int] = SUCCESS_THRESHOLDS,
    poster_features_path: Path | None = DEFAULT_POSTER_FEATURE_FILE,
):
    import pandas as pd

    if title_field not in raw_frame.columns:
        raise ValueError(f"제목 컬럼이 없습니다: {title_field}")

    keep_columns = [
        column
        for column in [
            title_field,
            "open_date",
            "tmdb_release_date",
            "tmdb_genres",
            "tmdb_poster_url",
        ]
        if column in raw_frame.columns
    ]
    result = raw_frame[keep_columns].copy()
    add_target_columns(result, raw_frame, thresholds)
    add_numeric_features(result, raw_frame)
    add_date_features(result, raw_frame)
    add_genre_features(result, raw_frame)
    result = add_frequency_features(result, raw_frame)
    result = merge_title_features(result, raw_frame, title_field)
    if poster_features_path is not None:
        result = merge_poster_features(result, poster_features_path, title_field)

    feature_columns = get_feature_columns(
        result,
        include_title=True,
        include_poster=True,
    )
    for column in feature_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def get_feature_columns(
    frame,
    include_title: bool = True,
    include_poster: bool = True,
) -> List[str]:
    prefixes = ["meta_", "genre_"]
    if include_title:
        prefixes.append("title_")
    if include_poster:
        prefixes.append("poster_")

    columns = [
        column
        for column in frame.columns
        if any(column.startswith(prefix) for prefix in prefixes)
        and column != "poster_feature_status"
    ]
    return columns


def experiment_feature_columns(frame, experiment: str) -> List[str]:
    experiment_map: Dict[str, Dict[str, bool]] = {
        "metadata": {"include_title": False, "include_poster": False},
        "metadata_title": {"include_title": True, "include_poster": False},
        "metadata_poster": {"include_title": False, "include_poster": True},
        "all": {"include_title": True, "include_poster": True},
    }
    if experiment not in experiment_map:
        raise ValueError(f"알 수 없는 실험 이름입니다: {experiment}")
    return get_feature_columns(
        frame,
        **experiment_map[experiment],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KOBIS/TMDB 매칭 CSV를 모델 학습용 특성 CSV로 변환합니다."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_FILE,
        help=f"입력 CSV 경로입니다. 기본값: {DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"특성 CSV 저장 경로입니다. 기본값: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--title-field",
        default=DEFAULT_TITLE_FIELD,
        help=f"제목 컬럼명입니다. 기본값: {DEFAULT_TITLE_FIELD}",
    )
    parser.add_argument(
        "--poster-features",
        type=Path,
        default=DEFAULT_POSTER_FEATURE_FILE,
        help=f"포스터 특성 CSV 경로입니다. 없으면 병합하지 않습니다. 기본값: {DEFAULT_POSTER_FEATURE_FILE}",
    )
    parser.add_argument(
        "--no-poster-features",
        action="store_true",
        help="포스터 특성 CSV가 있어도 병합하지 않습니다.",
    )
    parser.add_argument(
        "--success-thresholds",
        default="1000000,3000000,5000000,10000000",
        help="쉼표로 구분한 흥행 기준 관객 수입니다. 기본값: 1000000,3000000,5000000,10000000",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import pandas as pd

    thresholds = parse_thresholds(args.success_thresholds)
    raw_frame = pd.read_csv(args.input, encoding="utf-8-sig")
    poster_features_path = None if args.no_poster_features else args.poster_features
    feature_frame = build_feature_frame(
        raw_frame,
        title_field=args.title_field,
        thresholds=thresholds,
        poster_features_path=poster_features_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    feature_frame.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"rows: {len(feature_frame)}")
    print(f"features: {len(get_feature_columns(feature_frame))}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
