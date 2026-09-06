from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

try:
    from lightgbm import LGBMClassifier
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from .calibration import calibrate_threshold, evaluate_scores


@dataclass
class CandidateResult:
    """Result record for a trained candidate model."""
    name: str
    model: object
    threshold: float
    metrics_calibration: Dict[str, object]
    metrics_validation: Optional[Dict[str, object]]


class ClassicalEnsemble:
    """Averages AI-class probabilities from multiple fitted sklearn pipelines."""

    def __init__(self, models: List[object]) -> None:
        self.models = models

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        scores = np.mean(np.stack([ai_scores(m, X) for m in self.models], axis=1), axis=1)
        return np.column_stack([1.0 - scores, scores])


def build_candidates(seed: int = 2026, fast: bool = False) -> Dict[str, object]:
    """Create classical model candidates."""
    n_estimators = 120 if fast else 500
    max_iter = 80 if fast else 400
    candidates = {
        "logreg_robust": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", RobustScaler(with_centering=True, with_scaling=True)),
            ("clf", LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                solver="lbfgs",
                C=1.0,
                random_state=seed,
            )),
        ]),
        "extra_trees": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("clf", ExtraTreesClassifier(
                n_estimators=n_estimators,
                max_depth=None,
                min_samples_leaf=2,
                class_weight="balanced",
                n_jobs=-1,
                random_state=seed,
            )),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("clf", HistGradientBoostingClassifier(
                max_iter=max_iter,
                learning_rate=0.05,
                l2_regularization=0.03,
                min_samples_leaf=20,
                early_stopping=True,
                random_state=seed,
            )),
        ]),
    }
    if _HAS_LGB and not fast:
        candidates["lightgbm"] = Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("clf", LGBMClassifier(
                n_estimators=1500,
                learning_rate=0.03,
                num_leaves=63,
                min_child_samples=20,
                reg_alpha=0.1,
                reg_lambda=0.1,
                feature_fraction=0.85,
                bagging_fraction=0.85,
                bagging_freq=5,
                n_jobs=-1,
                random_state=seed,
                verbose=-1,
            )),
        ])
    return candidates


def ai_scores(model: object, X: np.ndarray) -> np.ndarray:
    """Return AI-class scores from a fitted model."""
    X = np.asarray(X, dtype=np.float32)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        if hasattr(model, "predict_proba"):
            return model.predict_proba(X)[:, 1]
        if hasattr(model, "decision_function"):
            z = model.decision_function(X)
            return 1.0 / (1.0 + np.exp(-z))
        pred = model.predict(X)
    return np.asarray(pred, dtype=np.float64)


def train_and_select(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    X_val: Optional[np.ndarray] = None,
    y_val: Optional[np.ndarray] = None,
    target_fpr: float = 0.20,
    seed: int = 2026,
    fast: bool = False,
) -> CandidateResult:
    """Train classical candidates and select the best feasible model."""
    candidates = build_candidates(seed=seed, fast=fast)
    results: List[CandidateResult] = []
    # Upweight AI class slightly to bias toward confident AI predictions;
    # threshold calibration handles FPR, so this helps recall without blowing the budget.
    sample_weight = np.where(y_train == 1, 1.3, 1.0)

    for name, model in candidates.items():
        print(f"training candidate: {name}", flush=True)
        try:
            model.fit(X_train, y_train, clf__sample_weight=sample_weight)
        except TypeError:
            model.fit(X_train, y_train)
        cal_scores = ai_scores(model, X_cal)
        threshold = calibrate_threshold(cal_scores, y_cal, target_fpr=target_fpr)
        metrics_cal = evaluate_scores(cal_scores, y_cal, threshold)
        metrics_val = None
        if X_val is not None and y_val is not None and len(y_val):
            val_scores = ai_scores(model, X_val)
            metrics_val = evaluate_scores(val_scores, y_val, threshold)
        print(f"candidate {name} cal={metrics_cal} val={metrics_val}", flush=True)
        results.append(CandidateResult(name, model, threshold, metrics_cal, metrics_val))

    # Add ensemble of all trained models as an additional candidate
    if len(results) >= 2:
        ens_model = ClassicalEnsemble([r.model for r in results])
        ens_cal_scores = ai_scores(ens_model, X_cal)
        ens_thr = calibrate_threshold(ens_cal_scores, y_cal, target_fpr=target_fpr)
        ens_cal_m = evaluate_scores(ens_cal_scores, y_cal, ens_thr)
        ens_val_m = None
        if X_val is not None and y_val is not None and len(y_val):
            ens_val_scores = ai_scores(ens_model, X_val)
            ens_val_m = evaluate_scores(ens_val_scores, y_val, ens_thr)
        print(f"candidate classical_ensemble cal={ens_cal_m} val={ens_val_m}", flush=True)
        results.append(CandidateResult("classical_ensemble", ens_model, ens_thr, ens_cal_m, ens_val_m))

    def rank_key(r: CandidateResult) -> Tuple[int, float, float, float]:
        """Rank a candidate by feasibility and validation quality."""
        m = r.metrics_validation or r.metrics_calibration
        feasible = 1 if float(m["fpr_real"]) <= target_fpr + 1e-12 else 0
        return (
            feasible,
            float(m["recall_ai"]),
            -float(m["fpr_real"]),
            float(m["accuracy"]),
        )

    best = sorted(results, key=rank_key, reverse=True)[0]
    print(f"selected model: {best.name}", flush=True)
    return best
