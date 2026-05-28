#!/usr/bin/env python3
"""Extract simple Korean movie title features."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_INPUT_FILE = Path("data/kobis_tmdb_title_matches.csv")
DEFAULT_OUTPUT_FILE = Path("data/processed/title_features.csv")
DEFAULT_TITLE_FIELD = "match_title"

DIGIT_PATTERN = re.compile(r"\d")
ENGLISH_PATTERN = re.compile(r"[A-Za-z]")
SPECIAL_CHAR_PATTERN = re.compile(r"[:;!?.,~·…'\"()\[\]{}<>+\-_/]")
SPACE_PATTERN = re.compile(r"\s+")

SERIES_KEYWORDS = (
    "2",
    "3",
    "4",
    "ii",
    "iii",
    "part",
    "season",
    "리턴즈",
    "비긴즈",
    "어게인",
    "파트",
    "시즌",
    "더 무비",
    "속편",
)

KEYWORD_GROUPS = {
    "love": ("사랑", "연애", "로맨스", "결혼", "첫사랑"),
    "war": ("전쟁", "군", "작전", "전투", "첩보"),
    "crime": ("범죄", "살인", "도둑", "형사", "경찰", "검사", "범인"),
    "horror": ("귀신", "괴담", "공포", "저주", "악마", "죽음"),
    "family": ("가족", "엄마", "아빠", "아버지", "어머니", "형", "동생"),
    "comedy": ("웃음", "코미디", "웃긴", "바보", "황당"),
    "action": ("액션", "추격", "킬러", "복수", "전설", "영웅"),
    "fantasy": ("신", "마법", "괴물", "외계", "초능력", "미래"),
    "youth": ("청춘", "학교", "소녀", "소년", "친구", "꿈"),
}


def normalize_title(value: object) -> str:
    return SPACE_PATTERN.sub(" ", str(value or "")).strip()


def contains_keyword(text: str, keywords: Iterable[str]) -> int:
    lowered = text.casefold()
    return int(any(keyword.casefold() in lowered for keyword in keywords))


def extract_title_feature_row(title: object) -> Dict[str, int]:
    normalized_title = normalize_title(title)
    title_without_space = SPACE_PATTERN.sub("", normalized_title)
    word_count = len(normalized_title.split()) if normalized_title else 0

    features: Dict[str, int] = {
        "title_length": len(normalized_title),
        "title_length_no_space": len(title_without_space),
        "title_word_count": word_count,
        "title_has_digit": int(bool(DIGIT_PATTERN.search(normalized_title))),
        "title_has_english": int(bool(ENGLISH_PATTERN.search(normalized_title))),
        "title_has_special_char": int(bool(SPECIAL_CHAR_PATTERN.search(normalized_title))),
        "title_has_series_keyword": contains_keyword(normalized_title, SERIES_KEYWORDS),
    }

    has_any_keyword = 0
    for group_name, keywords in KEYWORD_GROUPS.items():
        value = contains_keyword(normalized_title, keywords)
        features[f"title_keyword_{group_name}"] = value
        has_any_keyword = max(has_any_keyword, value)

    features["title_has_emotion_genre_keyword"] = has_any_keyword
    return features


def create_title_feature_frame(frame, title_field: str = DEFAULT_TITLE_FIELD):
    import pandas as pd

    if title_field not in frame.columns:
        raise ValueError(f"제목 컬럼이 없습니다: {title_field}")

    features: List[Dict[str, int]] = [
        extract_title_feature_row(title) for title in frame[title_field].fillna("")
    ]
    feature_frame = pd.DataFrame(features, index=frame.index)
    return pd.concat([frame[[title_field]].copy(), feature_frame], axis=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="영화 제목에서 길이, 문자 유형, 키워드 기반 특성을 추출합니다."
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import pandas as pd

    frame = pd.read_csv(args.input, encoding="utf-8-sig")
    feature_frame = create_title_feature_frame(frame, args.title_field)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    feature_frame.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"rows: {len(feature_frame)}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
