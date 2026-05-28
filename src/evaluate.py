#!/usr/bin/env python3
"""Shared evaluation helpers for movie success models."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


def classification_metrics(y_true, y_pred, y_score=None) -> Dict[str, float | int | None]:
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    metrics: Dict[str, float | int | None] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": None,
    }

    if y_score is not None and len(set(y_true)) == 2:
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_score))
        except ValueError:
            metrics["roc_auc"] = None

    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    metrics.update(
        {
            "true_negative": int(matrix[0, 0]),
            "false_positive": int(matrix[0, 1]),
            "false_negative": int(matrix[1, 0]),
            "true_positive": int(matrix[1, 1]),
        }
    )
    return metrics


def regression_metrics(y_true, y_pred) -> Dict[str, float]:
    import numpy as np
    from sklearn.metrics import (
        mean_absolute_error,
        mean_squared_error,
        mean_squared_log_error,
        r2_score,
    )

    y_pred_clipped = np.clip(y_pred, 0, None)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred_clipped)),
        "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred_clipped))),
        "r2": float(r2_score(y_true, y_pred_clipped)),
        "rmsle": float(mean_squared_log_error(y_true, y_pred_clipped) ** 0.5),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_rows(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_confusion_matrix(path: Path, y_true, y_pred, title: str) -> None:
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

    path.parent.mkdir(parents=True, exist_ok=True)
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    display = ConfusionMatrixDisplay(
        confusion_matrix=matrix,
        display_labels=["non-success", "success"],
    )
    display.plot(cmap="Blues", values_format="d")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def write_feature_importance(
    path: Path,
    feature_names: Iterable[str],
    importance_values: Iterable[float],
    signed_values: Iterable[float] | None = None,
) -> None:
    rows: List[Dict[str, object]] = []
    signed_list = list(signed_values) if signed_values is not None else None
    for index, (feature, importance) in enumerate(zip(feature_names, importance_values)):
        row: Dict[str, object] = {
            "feature": feature,
            "importance": float(importance),
        }
        if signed_list is not None:
            row["signed_value"] = float(signed_list[index])
        rows.append(row)

    rows.sort(key=lambda row: abs(float(row["importance"])), reverse=True)
    write_rows(path, rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="모델 학습 스크립트에서 사용하는 평가 함수 모듈입니다."
    )
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("evaluate.py provides helper functions for training scripts.")


if __name__ == "__main__":
    main()
