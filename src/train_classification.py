#!/usr/bin/env python3
"""Train classification models for movie success prediction."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from evaluate import (
        classification_metrics,
        save_confusion_matrix,
        write_feature_importance,
        write_rows,
    )
    from preprocessing import DEFAULT_OUTPUT_FILE, experiment_feature_columns
except ImportError:  # pragma: no cover - supports package-style imports
    from .evaluate import (
        classification_metrics,
        save_confusion_matrix,
        write_feature_importance,
        write_rows,
    )
    from .preprocessing import DEFAULT_OUTPUT_FILE, experiment_feature_columns


DEFAULT_METRICS_FILE = Path("outputs/metrics/classification_metrics.csv")
DEFAULT_PREDICTIONS_FILE = Path("outputs/metrics/classification_predictions.csv")
DEFAULT_FIGURES_DIR = Path("outputs/figures")
DEFAULT_PREDICTION_FIGURES_DIR = Path("outputs/figures/classification_predictions")
DEFAULT_IMPORTANCE_DIR = Path("outputs/metrics/feature_importance")
DEFAULT_TARGET = "is_success_3000000"
EXPERIMENTS = ("metadata", "metadata_title", "metadata_poster", "all")
PREDICTION_CONTEXT_COLUMNS = (
    "match_title",
    "open_date",
    "audience_count",
    "tmdb_genres",
)


def parse_experiments(value: str) -> List[str]:
    experiments = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(experiments) - set(EXPERIMENTS))
    if unknown:
        raise ValueError(f"알 수 없는 실험 이름입니다: {', '.join(unknown)}")
    return experiments


def build_models(random_state: int) -> Dict[str, object]:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.tree import DecisionTreeClassifier

    return {
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                random_state=random_state,
            ),
        ),
        "decision_tree": make_pipeline(
            SimpleImputer(strategy="median"),
            DecisionTreeClassifier(
                max_depth=5,
                min_samples_leaf=5,
                class_weight="balanced",
                random_state=random_state,
            ),
        ),
        "random_forest": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=300,
                min_samples_leaf=3,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            ),
        ),
        "dnn_mlp": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation="relu",
                alpha=0.001,
                early_stopping=True,
                max_iter=1000,
                random_state=random_state,
            ),
        ),
    }


def prediction_scores(model, features):
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(features)
        if probabilities.shape[1] > 1:
            return probabilities[:, 1]
    if hasattr(model, "decision_function"):
        return model.decision_function(features)
    return None


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
        coefficients = estimator.coef_[0]
        write_feature_importance(
            output_path,
            feature_names,
            abs(coefficients),
            signed_values=coefficients,
        )


def classification_result(actual: int, predicted: int) -> str:
    if actual == 1 and predicted == 1:
        return "true_positive"
    if actual == 0 and predicted == 0:
        return "true_negative"
    if actual == 0 and predicted == 1:
        return "false_positive"
    return "false_negative"


def prediction_rows(
    frame,
    test_indices,
    experiment: str,
    model_name: str,
    target: str,
    y_true,
    y_pred,
    scores,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for position, index in enumerate(test_indices):
        source_row = frame.loc[index]
        actual = int(y_true.iloc[position])
        predicted = int(y_pred[position])
        output_row: Dict[str, object] = {
            "experiment": experiment,
            "model": model_name,
            "target": target,
            "row_index": int(index) if isinstance(index, int) else index,
            "actual_label": actual,
            "predicted_label": predicted,
            "predicted_score": None if scores is None else float(scores[position]),
            "classification_result": classification_result(actual, predicted),
        }
        for column in PREDICTION_CONTEXT_COLUMNS:
            if column in frame.columns:
                output_row[column] = source_row.get(column, "")
        rows.append(output_row)
    return rows


def target_threshold(target: str) -> int | None:
    prefix = "is_success_"
    if not target.startswith(prefix):
        return None
    try:
        return int(target.removeprefix(prefix))
    except ValueError:
        return None


def save_prediction_scatter(
    output_path: Path,
    rows: List[Dict[str, object]],
    title: str,
    target: str,
) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    if not rows:
        return

    frame = pd.DataFrame(rows)
    if "audience_count" not in frame.columns:
        return

    frame["audience_count"] = pd.to_numeric(frame["audience_count"], errors="coerce")
    frame["predicted_score"] = pd.to_numeric(frame["predicted_score"], errors="coerce")
    frame = frame.dropna(subset=["audience_count", "predicted_score"])
    frame = frame[frame["audience_count"] > 0]
    if frame.empty:
        return

    colors = {
        "true_positive": "#2ca02c",
        "true_negative": "#1f77b4",
        "false_positive": "#ff7f0e",
        "false_negative": "#d62728",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(10, 6))
    for result_name, group in frame.groupby("classification_result"):
        axis.scatter(
            group["audience_count"],
            group["predicted_score"],
            label=f"{result_name} ({len(group)})",
            color=colors.get(result_name, "#7f7f7f"),
            alpha=0.8,
            s=42,
            edgecolors="white",
            linewidths=0.5,
        )

    threshold = target_threshold(target)
    if threshold is not None:
        axis.axvline(
            threshold,
            color="#444444",
            linestyle="--",
            linewidth=1,
            label=f"success threshold ({threshold:,})",
        )
    axis.axhline(0.5, color="#999999", linestyle=":", linewidth=1)
    axis.set_xscale("log")
    axis.set_xlabel("Actual audience count")
    axis.set_ylabel("Predicted success score")
    axis.set_title(title)
    axis.set_ylim(-0.05, 1.05)
    axis.grid(True, which="both", axis="x", alpha=0.2)
    axis.grid(True, axis="y", alpha=0.2)
    axis.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def train_single_experiment(
    frame,
    experiment: str,
    target: str,
    test_size: float,
    random_state: int,
    figures_dir: Path,
    prediction_figures_dir: Path,
    importance_dir: Path,
) -> tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    import pandas as pd
    from sklearn.model_selection import train_test_split

    feature_columns = experiment_feature_columns(frame, experiment)
    if not feature_columns:
        return (
            [
                {
                    "experiment": experiment,
                    "model": "skipped",
                    "target": target,
                    "reason": "no_features",
                }
            ],
            [],
        )

    data = frame[feature_columns + [target]].copy()
    data[target] = pd.to_numeric(data[target], errors="coerce")
    data = data.dropna(subset=[target])
    data[target] = data[target].astype(int)
    if data[target].nunique() < 2:
        return (
            [
                {
                    "experiment": experiment,
                    "model": "skipped",
                    "target": target,
                    "reason": "single_class_target",
                }
            ],
            [],
        )

    features = data[feature_columns].apply(pd.to_numeric, errors="coerce")
    target_values = data[target]
    class_counts = target_values.value_counts()
    stratify = target_values if class_counts.min() >= 2 else None
    x_train, x_test, y_train, y_test, _, test_indices = train_test_split(
        features,
        target_values,
        data.index,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify,
    )

    rows: List[Dict[str, object]] = []
    prediction_output_rows: List[Dict[str, object]] = []
    for model_name, model in build_models(random_state).items():
        model.fit(x_train, y_train)
        predictions = model.predict(x_test)
        scores = prediction_scores(model, x_test)
        metric_row: Dict[str, object] = {
            "experiment": experiment,
            "model": model_name,
            "target": target,
            "n_rows": len(data),
            "n_train": len(x_train),
            "n_test": len(x_test),
            "n_features": len(feature_columns),
        }
        metric_row.update(classification_metrics(y_test, predictions, scores))
        rows.append(metric_row)
        model_prediction_rows = prediction_rows(
            frame=frame,
            test_indices=test_indices,
            experiment=experiment,
            model_name=model_name,
            target=target,
            y_true=y_test,
            y_pred=predictions,
            scores=scores,
        )
        prediction_output_rows.extend(model_prediction_rows)

        safe_name = f"{experiment}_{model_name}_{target}"
        save_confusion_matrix(
            figures_dir / f"confusion_matrix_{safe_name}.png",
            y_test,
            predictions,
            f"{experiment} / {model_name}",
        )
        save_model_importance(
            model,
            feature_columns,
            importance_dir / f"classification_{safe_name}.csv",
        )
        save_prediction_scatter(
            prediction_figures_dir / f"classification_predictions_{safe_name}.png",
            model_prediction_rows,
            f"{experiment} / {model_name}",
            target,
        )

    return rows, prediction_output_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="흥행 여부 분류 모델과 ablation study를 실행합니다."
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
        help=f"분류 타깃 컬럼입니다. 기본값: {DEFAULT_TARGET}",
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
        "--predictions-output",
        type=Path,
        default=DEFAULT_PREDICTIONS_FILE,
        help=f"테스트셋 예측 결과 CSV 저장 경로입니다. 기본값: {DEFAULT_PREDICTIONS_FILE}",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES_DIR,
        help=f"Confusion Matrix 이미지 저장 디렉터리입니다. 기본값: {DEFAULT_FIGURES_DIR}",
    )
    parser.add_argument(
        "--prediction-figures-dir",
        type=Path,
        default=DEFAULT_PREDICTION_FIGURES_DIR,
        help=f"분류 결과 산점도 이미지 저장 디렉터리입니다. 기본값: {DEFAULT_PREDICTION_FIGURES_DIR}",
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
    prediction_output_rows: List[Dict[str, object]] = []
    for experiment in parse_experiments(args.experiments):
        experiment_metrics, experiment_predictions = train_single_experiment(
            frame,
            experiment=experiment,
            target=args.target,
            test_size=args.test_size,
            random_state=args.random_state,
            figures_dir=args.figures_dir,
            prediction_figures_dir=args.prediction_figures_dir,
            importance_dir=args.importance_dir,
        )
        metric_rows.extend(experiment_metrics)
        prediction_output_rows.extend(experiment_predictions)

    write_rows(args.output, metric_rows)
    write_rows(args.predictions_output, prediction_output_rows)
    print(f"metrics: {args.output}")
    print(f"predictions: {args.predictions_output}")
    print(f"rows: {len(metric_rows)}")


if __name__ == "__main__":
    main()
