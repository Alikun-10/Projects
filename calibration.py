from __future__ import annotations

from typing import Dict, Tuple

import numpy as np


def calibrate_threshold(scores: np.ndarray, y_true: np.ndarray, target_fpr: float = 0.20) -> float:
    """Choose the lowest threshold whose FPR on real images is <= target_fpr.

    Predictions use: predicted_label = int(score >= threshold).
    The threshold is calibrated only on real calibration images, because the
    constraint is about false accusations of real images.
    """
    scores = np.asarray(scores, dtype=np.float64)
    y_true = np.asarray(y_true, dtype=np.int8)
    real_scores = scores[y_true == 0]
    if len(real_scores) == 0:
        # No real calibration examples: fall back to a conservative threshold.
        return float(np.quantile(scores, 0.80)) if len(scores) else 0.5

    candidates = np.unique(real_scores)
    # Also allow thresholds above the maximum score if needed.
    candidates = np.concatenate([candidates, [np.nextafter(real_scores.max(), np.inf)]])
    candidates.sort()
    chosen = float(candidates[-1])
    for t in candidates:
        fpr = float((real_scores >= t).mean())
        if fpr <= target_fpr + 1e-12:
            chosen = float(t)
            break
    return chosen


def scores_to_labels(scores: np.ndarray, threshold: float) -> np.ndarray:
    """Convert AI scores to binary labels using a threshold."""
    return (np.asarray(scores) >= float(threshold)).astype(np.int8)


def evaluate_scores(scores: np.ndarray, y_true: np.ndarray, threshold: float) -> Dict[str, float | int | list]:
    """Compute binary classification metrics at a fixed threshold."""
    y_true = np.asarray(y_true).astype(np.int8)
    scores = np.asarray(scores, dtype=np.float64)
    pred = scores_to_labels(scores, threshold)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    n_real = int((y_true == 0).sum())
    n_ai = int((y_true == 1).sum())
    precision = tp / max(tp + fp, 1)
    recall_ai = tp / max(n_ai, 1)
    fpr_real = fp / max(n_real, 1)
    accuracy = (tp + tn) / max(len(y_true), 1)
    return {
        "n": int(len(y_true)),
        "n_real": n_real,
        "n_ai": n_ai,
        "threshold": float(threshold),
        "accuracy": float(accuracy),
        "precision_ai": float(precision),
        "recall_ai": float(recall_ai),
        "fpr_real": float(fpr_real),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "confusion_matrix_rows_true_0_1_cols_pred_0_1": [[tn, fp], [fn, tp]],
    }
