#!/usr/bin/env python3
"""Train regression models for audience count prediction."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from evaluate import regression_metrics, write_feature_importance, write_rows
    from preprocessing import DEFAULT_OUTPUT_FILE, experiment_feature_columns
except ImportError:  # pragma: no cover - supports package-style imports
    from .evaluate import regression_metrics, write_feature_importance, write_rows
    from .preprocessing import DEFAULT_OUTPUT_FILE, experiment_feature_columns


DEFAULT_METRICS_FILE = Path("outputs/metrics/regression_metrics.csv")
DEFAULT_IMPORTANCE_DIR = Path("outputs/metrics/feature_importance")
DEFAULT_TARGET = "target_log_audience"
EXPERIMENTS = ("metadata", "metadata_title", "metadata_poster", "all")


def parse_experiments(value: str) -> List[str]:
    experiments = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(experiments) - set(EXPERIMENTS))
    if unknown:
        raise ValueError(f"알 수 없는 실험 이름입니다: {', '.join(unknown)}")
    return experiments


def build_models(random_state: int) -> Dict[str, object]:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Lasso, LinearRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "linear_regression": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LinearRegression(),
        ),
        "ridge": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=1.0, random_state=random_state),
        ),
        "lasso": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Lasso(alpha=0.001, max_iter=5000, random_state=random_state),
        ),
        "random_forest_regressor": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestRegressor(
                n_estimators=300,
                min_samples_leaf=3,
                random_state=random_state,
                n_jobs=-1,
            ),
        ),
    }


def estimator_from_pipeline(model):
    if hasattr(model, "steps"):
        return model.steps[-1][1]
    return model


def save_model_importance(
    model,
    feature_names: Iterable[str],
    output_path: Path,
) -> None:
    estimator = estimator_from_pipeline(model)
    if hasattr(estimator, "feature_importances_"):
        write_feature_importance(
            output_path,
            feature_names,
            estimator.feature_importances_,
        )
        return

    if hasattr(estimator, "coef_"):
        coefficients = estimator.coef_
        write_feature_importance(
            output_path,
            feature_names,
            abs(coefficients),
            signed_values=coefficients,
        )


def train_single_experiment(
    frame,
    experiment: str,
    target: str,
    test_size: float,
    random_state: int,
    importance_dir: Path,
) -> List[Dict[str, object]]:
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split

    feature_columns = experiment_feature_columns(frame, experiment)
    if not feature_columns:
        return [
            {
                "experiment": experiment,
                "model": "skipped",
                "target": target,
                "reason": "no_features",
            }
        ]

    required_columns = feature_columns + [target, "audience_count"]
    data = frame[required_columns].copy()
    data[target] = pd.to_numeric(data[target], errors="coerce")
    data["audience_count"] = pd.to_numeric(data["audience_count"], errors="coerce")
    data = data.dropna(subset=[target, "audience_count"])
    if len(data) < 5:
        return [
            {
                "experiment": experiment,
                "model": "skipped",
                "target": target,
                "reason": "not_enough_rows",
            }
        ]

    features = data[feature_columns].apply(pd.to_numeric, errors="coerce")
    target_values = data[target]
    audience_count = data["audience_count"]
    x_train, x_test, y_train, y_test, _, audience_test = train_test_split(
        features,
        target_values,
        audience_count,
        test_size=test_size,
        random_state=random_state,
    )

    rows: List[Dict[str, object]] = []
    for model_name, model in build_models(random_state).items():
        model.fit(x_train, y_train)
        log_predictions = model.predict(x_test)
        predictions = np.expm1(log_predictions)
        metric_row: Dict[str, object] = {
            "experiment": experiment,
            "model": model_name,
            "target": target,
            "n_rows": len(data),
            "n_train": len(x_train),
            "n_test": len(x_test),
            "n_features": len(feature_columns),
        }
        metric_row.update(regression_metrics(audience_test, predictions))
        rows.append(metric_row)

        safe_name = f"{experiment}_{model_name}_{target}"
        save_model_importance(
            model,
            feature_columns,
            importance_dir / f"regression_{safe_name}.csv",
        )

    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="누적 관객 수 로그 회귀 모델과 ablation study를 실행합니다."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"전처리된 특성 CSV 경로입니다. 기본값: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"회귀 타깃 컬럼입니다. 기본값: {DEFAULT_TARGET}",
    )
    parser.add_argument(
        "--experiments",
        default=",".join(EXPERIMENTS),
        help=f"실행할 실험 목록입니다. 사용 가능: {', '.join(EXPERIMENTS)}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_METRICS_FILE,
        help=f"성능 지표 CSV 저장 경로입니다. 기본값: {DEFAULT_METRICS_FILE}",
    )
    parser.add_argument(
        "--importance-dir",
        type=Path,
        default=DEFAULT_IMPORTANCE_DIR,
        help=f"변수 중요도 CSV 저장 디렉터리입니다. 기본값: {DEFAULT_IMPORTANCE_DIR}",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="테스트 데이터 비율입니다. 기본값: 0.2",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="재현성을 위한 난수 시드입니다. 기본값: 42",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import pandas as pd

    frame = pd.read_csv(args.input, encoding="utf-8-sig")
    if args.target not in frame.columns:
        raise ValueError(f"타깃 컬럼이 없습니다: {args.target}")

    metric_rows: List[Dict[str, object]] = []
    for experiment in parse_experiments(args.experiments):
        metric_rows.extend(
            train_single_experiment(
                frame,
                experiment=experiment,
                target=args.target,
                test_size=args.test_size,
                random_state=args.random_state,
                importance_dir=args.importance_dir,
            )
        )

    write_rows(args.output, metric_rows)
    print(f"metrics: {args.output}")
    print(f"rows: {len(metric_rows)}")


if __name__ == "__main__":
    main()
