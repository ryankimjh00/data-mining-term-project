#!/usr/bin/env python3
"""Extract color and structure features from downloaded poster images."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

try:
    from download_posters import poster_path
except ImportError:  # pragma: no cover - supports package-style imports
    from .download_posters import poster_path


DEFAULT_INPUT_FILE = Path("data/kobis_tmdb_title_matches.csv")
DEFAULT_POSTER_DIR = Path("data/posters")
DEFAULT_OUTPUT_FILE = Path("data/processed/poster_features.csv")
DEFAULT_TITLE_FIELD = "match_title"


def empty_poster_features(status: str) -> Dict[str, object]:
    return {
        "poster_available": 0,
        "poster_feature_status": status,
        "poster_width": None,
        "poster_height": None,
        "poster_aspect_ratio": None,
        "poster_brightness_mean": None,
        "poster_saturation_mean": None,
        "poster_red_mean": None,
        "poster_green_mean": None,
        "poster_blue_mean": None,
        "poster_contrast": None,
        "poster_edge_density": None,
    }


def extract_image_features(path: Path) -> Dict[str, object]:
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        rgb = np.asarray(rgb_image, dtype=np.float32) / 255.0
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]
        brightness = 0.299 * red + 0.587 * green + 0.114 * blue

        hsv = np.asarray(rgb_image.convert("HSV"), dtype=np.float32) / 255.0
        saturation = hsv[:, :, 1]

        vertical_diff = np.abs(np.diff(brightness, axis=0))
        horizontal_diff = np.abs(np.diff(brightness, axis=1))
        edge_pixels = 0
        if vertical_diff.size:
            edge_pixels += int((vertical_diff > 0.12).sum())
        if horizontal_diff.size:
            edge_pixels += int((horizontal_diff > 0.12).sum())
        edge_denominator = max(
            int(vertical_diff.size + horizontal_diff.size),
            1,
        )

    return {
        "poster_available": 1,
        "poster_feature_status": "ok",
        "poster_width": width,
        "poster_height": height,
        "poster_aspect_ratio": width / height if height else None,
        "poster_brightness_mean": float(brightness.mean()),
        "poster_saturation_mean": float(saturation.mean()),
        "poster_red_mean": float(red.mean()),
        "poster_green_mean": float(green.mean()),
        "poster_blue_mean": float(blue.mean()),
        "poster_contrast": float(brightness.std()),
        "poster_edge_density": edge_pixels / edge_denominator,
    }


def create_poster_feature_frame(
    frame,
    poster_dir: Path = DEFAULT_POSTER_DIR,
    title_field: str = DEFAULT_TITLE_FIELD,
):
    import pandas as pd

    if title_field not in frame.columns:
        raise ValueError(f"제목 컬럼이 없습니다: {title_field}")

    rows = []
    for title in frame[title_field].fillna(""):
        output_row = {title_field: title}
        path = poster_path(poster_dir, str(title))
        if not path.exists():
            output_row.update(empty_poster_features("missing"))
            rows.append(output_row)
            continue

        try:
            output_row.update(extract_image_features(path))
        except Exception as error:  # noqa: BLE001 - image decoding failures vary by backend
            output_row.update(empty_poster_features(f"error:{error.__class__.__name__}"))
        rows.append(output_row)

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="다운로드된 영화 포스터 이미지에서 색상과 복잡도 특성을 추출합니다."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_FILE,
        help=f"입력 CSV 경로입니다. 기본값: {DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--poster-dir",
        type=Path,
        default=DEFAULT_POSTER_DIR,
        help=f"포스터 이미지 디렉터리입니다. 기본값: {DEFAULT_POSTER_DIR}",
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
    feature_frame = create_poster_feature_frame(frame, args.poster_dir, args.title_field)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    feature_frame.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"rows: {len(feature_frame)}")
    print(f"available: {int(feature_frame['poster_available'].sum())}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
