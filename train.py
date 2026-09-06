from __future__ import annotations

import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.calibration import calibrate_threshold, evaluate_scores
from src.features import feature_names
from src.models import ai_scores, train_and_select
from src.utils import artifacts_dir, common_arg_parser, data_dir, ensure_dir, print_header, save_json, set_reproducible


GEOMETRY_FEATURES = {"byte_len", "width", "height", "aspect", "area"}
ENSEMBLE_WEIGHTS = {"rf_content": 0.60, "mlp_content": 0.16, "cnn": 0.24}


def load_npz(prepared_dir: Path, split: str):
    """Load cached features for one split."""
    path = prepared_dir / f"{split}_features.npz"
    if not path.exists():
        return None, None
    z = np.load(path)
    return z["X"], z["y"]


def require_training_splits(prepared_dir: Path):
    """Load required Task 2 feature splits."""
    X_train, y_train = load_npz(prepared_dir, "train")
    if X_train is None:
        X_train, y_train = load_npz(prepared_dir, "validation")
        if X_train is None:
            raise FileNotFoundError("No prepared train split found. Run prepare.py after placing data/train under solution/data/.")
        print("warning: using validation as training fallback because train split is missing")

    X_cal, y_cal = load_npz(prepared_dir, "calibration")
    if X_cal is None:
        X_cal, y_cal = load_npz(prepared_dir, "validation")
        if X_cal is None:
            X_cal, y_cal = X_train, y_train
        print("warning: calibration split missing; using fallback split for threshold calibration")

    X_val, y_val = load_npz(prepared_dir, "validation")
    X_vaug, y_vaug = load_npz(prepared_dir, "validation_augmented")
    return X_train, y_train, X_cal, y_cal, X_val, y_val, X_vaug, y_vaug


def rank_metrics(metrics: dict | None, target_fpr: float) -> tuple[int, float, float, float]:
    """Rank metrics by feasibility and recall."""
    if not metrics:
        return (0, -1.0, -1.0, 0.0)
    feasible = 1 if float(metrics["fpr_real"]) <= target_fpr + 1e-12 else 0
    return (feasible, float(metrics["recall_ai"]), -float(metrics["fpr_real"]), float(metrics["accuracy"]))


def content_feature_indices() -> np.ndarray:
    """Return feature indices that exclude geometry shortcuts."""
    names = feature_names()
    return np.asarray([i for i, name in enumerate(names) if name not in GEOMETRY_FEATURES], dtype=np.int64)


def build_heavy_ensemble_candidate(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    X_val: np.ndarray | None,
    y_val: np.ndarray | None,
    X_vaug: np.ndarray | None,
    y_vaug: np.ndarray | None,
    target_fpr: float,
    seed: int,
    timeout_seconds: int,
    cnn_epochs: int,
    cnn_batch_size: int,
    cnn_image_size: int,
    cnn_width: int,
) -> dict:
    """Train and evaluate the weighted RF/MLP/CNN ensemble (kept for --with_ensemble)."""
    idx = content_feature_indices()
    print_header("Heavy ensemble training (RF + MLP + CNN)")
    rf = RandomForestClassifier(
        n_estimators=800,
        min_samples_leaf=1,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=seed,
        max_features="sqrt",
    )
    mlp = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", MLPClassifier(
            hidden_layer_sizes=(128, 64),
            activation="relu",
            alpha=1e-4,
            batch_size=256,
            learning_rate_init=1e-3,
            max_iter=80,
            early_stopping=True,
            n_iter_no_change=8,
            random_state=seed,
        )),
    ])
    print("training ensemble member: rf_content", flush=True)
    rf.fit(X_train[:, idx], y_train)
    print("training ensemble member: mlp_content", flush=True)
    mlp.fit(X_train[:, idx], y_train)

    from src.cnn_model import load_cnn_model, load_labeled_image_bytes, score_images, train_cnn

    cnn = train_cnn(
        root=data_dir(),
        artifacts_root=artifacts_dir(),
        target_fpr=target_fpr,
        seed=seed,
        timeout_seconds=timeout_seconds,
        image_size=cnn_image_size,
        batch_size=cnn_batch_size,
        max_epochs=cnn_epochs,
        patience=2,
        width=cnn_width,
    )
    cnn_model, image_size = load_cnn_model(cnn.model_path)
    cal_images, _ = load_labeled_image_bytes(data_dir(), "calibration")
    val_images, _ = load_labeled_image_bytes(data_dir(), "validation") if X_val is not None and y_val is not None else ([], None)
    vaug_images, _ = load_labeled_image_bytes(data_dir(), "validation_augmented") if X_vaug is not None and y_vaug is not None else ([], None)

    def combined_scores(X: np.ndarray, images: list[bytes]) -> np.ndarray:
        """Combine ensemble member scores."""
        return (
            ENSEMBLE_WEIGHTS["rf_content"] * ai_scores(rf, X[:, idx])
            + ENSEMBLE_WEIGHTS["mlp_content"] * ai_scores(mlp, X[:, idx])
            + ENSEMBLE_WEIGHTS["cnn"] * score_images(cnn_model, images, batch_size=cnn_batch_size, image_size=image_size)
        )

    cal_scores = combined_scores(X_cal, cal_images)
    threshold = calibrate_threshold(cal_scores, y_cal, target_fpr=target_fpr)
    metrics_cal = evaluate_scores(cal_scores, y_cal, threshold)
    metrics_val = None
    if X_val is not None and y_val is not None and len(y_val):
        metrics_val = evaluate_scores(combined_scores(X_val, val_images), y_val, threshold)
    metrics_vaug = None
    if X_vaug is not None and y_vaug is not None and len(y_vaug):
        metrics_vaug = evaluate_scores(combined_scores(X_vaug, vaug_images), y_vaug, threshold)

    return {
        "family": "heavy_ensemble",
        "model_name": "rf_mlp_cnn_content_ensemble",
        "threshold": float(threshold),
        "metrics_calibration": metrics_cal,
        "metrics_validation": metrics_val,
        "metrics_validation_augmented": metrics_vaug,
        "bundle": {
            "task": "task02",
            "model_kind": "weighted_ensemble",
            "model_name": "rf_mlp_cnn_content_ensemble",
            "rf_content": rf,
            "mlp_content": mlp,
            "content_feature_indices": idx.tolist(),
            "cnn_model_path": str(cnn.model_path),
            "cnn_image_size": int(image_size),
            "weights": {k: float(v) for k, v in ENSEMBLE_WEIGHTS.items()},
            "threshold": float(threshold),
            "target_fpr": float(target_fpr),
        },
    }


def main() -> None:
    """Run the script entry point."""
    parser = common_arg_parser("Train Task 2 classifier and calibrate threshold")
    parser.add_argument("--target_fpr", type=float, default=0.18)
    parser.add_argument("--fast", action="store_true", help="Use smaller candidate models for quick local tests")
    parser.add_argument("--with_cnn", action="store_true", help="Also train CNN candidate (slow on CPU, rarely wins)")
    parser.add_argument("--no_cnn", action="store_true", help="[deprecated] no-op, CNN is off by default")
    parser.add_argument("--with_ensemble", action="store_true", help="Also train the heavy RF/MLP/CNN ensemble")
    parser.add_argument("--skip_ensemble", action="store_true", help="[deprecated] no-op")
    parser.add_argument("--cnn_epochs", type=int, default=8)
    parser.add_argument("--cnn_batch_size", type=int, default=128)
    parser.add_argument("--cnn_image_size", type=int, default=64)
    parser.add_argument("--cnn_width", type=int, default=24)
    args = parser.parse_args()
    set_reproducible(args.seed)

    t_start = time.monotonic()
    prepared_dir = artifacts_dir() / "prepared"
    out_dir = ensure_dir(artifacts_dir() / "task02")
    print_header("Task 2 training")

    X_train, y_train, X_cal, y_cal, X_val, y_val, X_vaug, y_vaug = require_training_splits(prepared_dir)

    # --- Step 1: classical engineered-feature models ---
    classical = train_and_select(
        X_train=X_train,
        y_train=y_train,
        X_cal=X_cal,
        y_cal=y_cal,
        X_val=X_val,
        y_val=y_val,
        target_fpr=args.target_fpr,
        seed=args.seed,
        fast=args.fast,
    )
    classical_vaug_metrics = None
    if X_vaug is not None and y_vaug is not None and len(y_vaug):
        vaug_scores = ai_scores(classical.model, X_vaug)
        classical_vaug_metrics = evaluate_scores(vaug_scores, y_vaug, classical.threshold)
        print(f"Task2 val_aug metrics: {classical_vaug_metrics}", flush=True)

    candidates = [
        {
            "family": "engineered_features",
            "model_name": classical.name,
            "threshold": float(classical.threshold),
            "metrics_calibration": classical.metrics_calibration,
            "metrics_validation": classical.metrics_validation,
            "metrics_validation_augmented": classical_vaug_metrics,
            "bundle": {
                "task": "task02",
                "model_kind": "sklearn_features",
                "model_name": classical.name,
                "model": classical.model,
                "threshold": float(classical.threshold),
                "target_fpr": float(args.target_fpr),
                "feature_names_path": str(prepared_dir / "feature_names.json"),
            },
        }
    ]

    skip_cnn = not args.with_cnn
    if not skip_cnn:
        # --- Step 2: CNN trained from scratch ---
        elapsed = time.monotonic() - t_start
        # Reserve 60s for post-CNN bookkeeping (classical scoring on arrays, joblib.dump).
        # Ensemble scoring reuses scores already computed inside train_cnn, so no image I/O here.
        cnn_budget = int(max(300, args.timeout_seconds - elapsed - 60))
        print(f"classical finished in {elapsed:.0f}s; CNN budget = {cnn_budget}s", flush=True)

        from src.cnn_model import train_cnn

        try:
            cnn_result = train_cnn(
                root=data_dir(),
                artifacts_root=artifacts_dir(),
                target_fpr=args.target_fpr,
                seed=args.seed,
                timeout_seconds=cnn_budget,
                image_size=args.cnn_image_size,
                batch_size=args.cnn_batch_size,
                max_epochs=args.cnn_epochs,
                patience=3,
                width=args.cnn_width,
            )
            candidates.append({
                "family": "cnn",
                "model_name": "small_cnn",
                "threshold": float(cnn_result.threshold),
                "metrics_calibration": cnn_result.metrics_calibration,
                "metrics_validation": cnn_result.metrics_validation,
                "bundle": {
                    "task": "task02",
                    "model_kind": "cnn",
                    "model_name": "small_cnn",
                    "model_path": "cnn_model.pt",
                    "threshold": float(cnn_result.threshold),
                    "target_fpr": float(args.target_fpr),
                },
            })
        except Exception as exc:
            print(f"warning: CNN training failed: {exc}", flush=True)
            cnn_result = None

        # --- Step 3: soft ensemble (CNN 50% + classical 50%) ---
        if cnn_result is not None:
            try:
                # Reuse scores already computed inside train_cnn — no image reloading needed.
                cnn_cal = cnn_result.cal_scores
                cls_cal = ai_scores(classical.model, X_cal)
                ens_cal = 0.5 * cnn_cal + 0.5 * cls_cal
                ens_thr = calibrate_threshold(ens_cal, y_cal, target_fpr=args.target_fpr)
                ens_metrics_cal = evaluate_scores(ens_cal, y_cal, ens_thr)

                ens_metrics_val = None
                if X_val is not None and y_val is not None and len(y_val) and cnn_result.val_scores is not None:
                    cls_val = ai_scores(classical.model, X_val)
                    ens_val = 0.5 * cnn_result.val_scores + 0.5 * cls_val
                    ens_metrics_val = evaluate_scores(ens_val, y_val, ens_thr)

                ens_metrics_vaug = None
                if X_vaug is not None and y_vaug is not None and len(y_vaug) and cnn_result.vaug_scores is not None:
                    cls_vaug = ai_scores(classical.model, X_vaug)
                    ens_vaug = 0.5 * cnn_result.vaug_scores + 0.5 * cls_vaug
                    ens_metrics_vaug = evaluate_scores(ens_vaug, y_vaug, ens_thr)

                candidates.append({
                    "family": "soft_ensemble",
                    "model_name": "cnn_classical_avg",
                    "threshold": float(ens_thr),
                    "metrics_calibration": ens_metrics_cal,
                    "metrics_validation": ens_metrics_val,
                    "metrics_validation_augmented": ens_metrics_vaug,
                    "bundle": {
                        "task": "task02",
                        "model_kind": "soft_ensemble",
                        "model_name": "cnn_classical_avg",
                        "classical_model": classical.model,
                        "cnn_model_path": "cnn_model.pt",
                        "cnn_image_size": int(args.cnn_image_size),
                        "cnn_batch_size": int(args.cnn_batch_size),
                        "weights": {"cnn": 0.5, "classical": 0.5},
                        "threshold": float(ens_thr),
                        "target_fpr": float(args.target_fpr),
                    },
                })
            except Exception as exc:
                print(f"warning: soft ensemble failed: {exc}", flush=True)

    # --- Optional heavy RF/MLP/CNN ensemble ---
    if args.with_ensemble and not args.no_cnn and not args.skip_ensemble:
        try:
            elapsed = time.monotonic() - t_start
            heavy_budget = int(max(300, args.timeout_seconds - elapsed - 60))
            candidates.append(build_heavy_ensemble_candidate(
                X_train=X_train,
                y_train=y_train,
                X_cal=X_cal,
                y_cal=y_cal,
                X_val=X_val,
                y_val=y_val,
                X_vaug=X_vaug,
                y_vaug=y_vaug,
                target_fpr=args.target_fpr,
                seed=args.seed,
                timeout_seconds=heavy_budget,
                cnn_epochs=args.cnn_epochs if not args.fast else min(args.cnn_epochs, 1),
                cnn_batch_size=args.cnn_batch_size,
                cnn_image_size=args.cnn_image_size,
                cnn_width=args.cnn_width,
            ))
        except Exception as exc:
            print(f"warning: heavy ensemble training failed: {exc}", flush=True)

    # --- Select best candidate ---
    selected = sorted(
        candidates,
        key=lambda c: rank_metrics(c.get("metrics_validation") or c.get("metrics_calibration"), args.target_fpr),
        reverse=True,
    )[0]
    joblib.dump(selected["bundle"], out_dir / "model.joblib")

    metrics = {
        "selected_family": selected["family"],
        "selected_model": selected["model_name"],
        "target_fpr": float(args.target_fpr),
        "candidates": [
            {k: v for k, v in c.items() if k != "bundle"}
            for c in candidates
        ],
        "calibration": selected["metrics_calibration"],
        "validation": selected["metrics_validation"],
        "validation_augmented": selected.get("metrics_validation_augmented"),
    }
    save_json(metrics, out_dir / "metrics.json")
    print(f"selected family/model: {selected['family']} / {selected['model_name']}")
    print(f"saved model to {out_dir / 'model.joblib'}")
    print(f"saved metrics to {out_dir / 'metrics.json'}")
    print(f"total train.py elapsed: {time.monotonic() - t_start:.0f}s")


if __name__ == "__main__":
    main()
