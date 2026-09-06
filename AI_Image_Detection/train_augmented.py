from __future__ import annotations

import os
from pathlib import Path

import joblib
import numpy as np

try:
    from lightgbm import LGBMClassifier
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from src.data import parquet_files, read_split
from src.features import extract_feature_matrix_from_bytes, feature_names
from src.calibration import calibrate_threshold, evaluate_scores
from src.models import ai_scores
from src.utils import (
    artifacts_dir,
    binary_labels,
    common_arg_parser,
    data_dir,
    ensure_dir,
    load_json,
    print_header,
    save_json,
    set_reproducible,
)


def load_npz(prepared_dir: Path, split: str):
    """Load cached prepared features for one split."""
    path = prepared_dir / f"{split}_features.npz"
    if not path.exists():
        return None, None
    z = np.load(path)
    return z["X"], z["y"]


def cache_matches(meta_path: Path, variants: list[str], expected_feature_dim: int) -> bool:
    """Check whether an existing augmented-feature cache matches requested variants and feature dim."""
    if not meta_path.exists():
        return False
    try:
        meta = load_json(meta_path)
        return (
            list(meta.get("variants", [])) == list(variants)
            and meta.get("feature_dim") == expected_feature_dim
        )
    except Exception:
        return False


def build_or_load_augmented_train(
    root: Path,
    out_dir: Path,
    variants: list[str],
    workers: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Build or load deterministic augmented training features."""
    cache = out_dir / "train_augmented_features.npz"
    meta_path = out_dir / "train_augmented_meta.json"

    expected_dim = len(feature_names())
    if cache.exists() and cache_matches(meta_path, variants, expected_dim):
        print(f"loading cached augmented features from {cache}")
        z = np.load(cache)
        return z["X"], z["y"]

    if cache.exists():
        print("existing augmented cache uses different variants or feature dim; rebuilding")
        cache.unlink()
    if meta_path.exists():
        meta_path.unlink()

    if not parquet_files(root, "train"):
        fallback = "validation" if parquet_files(root, "validation") else None
        if fallback is None:
            raise FileNotFoundError("No train split available for augmented training.")
        print(f"warning: using {fallback} as fallback because train split is missing")
        split = fallback
    else:
        split = "train"

    print_header(f"Extracting augmented training features from {split}")
    df = read_split(root, split)
    if not {"image", "source_class"}.issubset(df.columns):
        raise ValueError(f"split {split} must contain image and source_class columns")

    y = binary_labels(df["source_class"].values)
    X_aug, y_aug = extract_feature_matrix_from_bytes(
        df["image"].values,
        labels=y,
        desc="augmented train features",
        variants=variants,
        workers=workers,
    )

    np.savez_compressed(cache, X=X_aug, y=y_aug)
    save_json(
        {
            "split_used": split,
            "variants": list(variants),
            "workers": int(workers),
            "n_raw_images": int(len(df)),
            "n_feature_rows": int(len(y_aug)),
            "feature_dim": int(X_aug.shape[1]),
            "feature_names": feature_names(),
        },
        meta_path,
    )
    return X_aug, y_aug


def build_model(seed: int, fast: bool) -> Pipeline:
    """Build a single LightGBM pipeline (HGB fallback if LightGBM unavailable)."""
    if _HAS_LGB and not fast:
        clf = LGBMClassifier(
            n_estimators=1200,
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
        )
        model_name = "lightgbm_augmented"
    else:
        clf = HistGradientBoostingClassifier(
            max_iter=150 if fast else 400,
            learning_rate=0.05,
            l2_regularization=0.03,
            min_samples_leaf=20,
            early_stopping=True,
            random_state=seed,
        )
        model_name = "hgb_augmented"
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("clf", clf)]), model_name


def main() -> None:
    parser = common_arg_parser("Train Task 3 robust classifier")
    parser.add_argument("--target_fpr", type=float, default=0.20)
    parser.add_argument(
        "--cal_mode",
        type=str,
        default="augmented",
        choices=["combined", "augmented", "clean"],
        help="Calibration set: 'augmented'=cal_aug only (default), 'combined'=clean+aug, 'clean'=clean only",
    )
    parser.add_argument("--fast", action="store_true", help="Smaller model for quick tests")
    parser.add_argument(
        "--variants",
        type=str,
        default="original,jpeg70,jpeg45,blur,downup,contrast,graymix",
        help="Comma-separated augmentation variants; 'random' samples a continuous distribution per image",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 1),
        help="Feature extraction workers",
    )
    args = parser.parse_args()
    set_reproducible(args.seed)

    root = data_dir()
    prepared_dir = artifacts_dir() / "prepared"
    out_dir = ensure_dir(artifacts_dir() / "task03")

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    workers = max(1, int(args.workers))
    cal_mode = args.cal_mode

    print_header("Task 3 augmented training")
    print(f"augmentation variants: {variants}")
    print(f"feature workers: {workers}")
    print(f"calibration mode: {cal_mode}")

    X_train, y_train = build_or_load_augmented_train(root, out_dir, variants, workers)

    X_cal_clean, y_cal_clean = load_npz(prepared_dir, "calibration")
    X_cal_aug, y_cal_aug = load_npz(prepared_dir, "calibration_augmented")

    if cal_mode == "augmented":
        X_cal, y_cal = X_cal_aug, y_cal_aug
        calibration_split = "calibration_augmented"
    elif cal_mode == "clean":
        X_cal, y_cal = X_cal_clean, y_cal_clean
        calibration_split = "calibration"
    else:  # combined
        if X_cal_clean is not None and X_cal_aug is not None:
            X_cal = np.vstack([X_cal_clean, X_cal_aug])
            y_cal = np.concatenate([y_cal_clean, y_cal_aug])
            calibration_split = "calibration+calibration_augmented"
        elif X_cal_clean is not None:
            X_cal, y_cal = X_cal_clean, y_cal_clean
            calibration_split = "calibration"
        elif X_cal_aug is not None:
            X_cal, y_cal = X_cal_aug, y_cal_aug
            calibration_split = "calibration_augmented"
        else:
            X_cal, y_cal = None, None

    if X_cal is None:
        X_cal, y_cal = load_npz(prepared_dir, "validation")
        calibration_split = "validation"
        print("warning: no calibration split found; using validation as fallback")
    if X_cal is None:
        X_cal, y_cal = X_train, y_train
        calibration_split = "augmented_train_fallback"

    X_val, y_val = load_npz(prepared_dir, "validation")
    X_val_aug, y_val_aug = load_npz(prepared_dir, "validation_augmented")

    print_header("Training on augmented data")
    model, model_name = build_model(seed=args.seed, fast=args.fast)
    print(f"model: {model_name}", flush=True)

    # With variants=["original","random"], rows interleave: orig, rand, orig, rand, ...
    # Augmented AI samples get a higher weight to push harder on the hard cases.
    sample_weight = np.where(y_train == 1, 1.3, 1.0)
    if len(variants) == 2 and "random" in variants:
        aug_ai = np.zeros(len(y_train), dtype=bool)
        aug_ai[1::2] = y_train[1::2] == 1
        sample_weight[aug_ai] = 1.5
    try:
        model.fit(X_train, y_train, clf__sample_weight=sample_weight)
    except TypeError:
        model.fit(X_train, y_train)

    cal_scores = ai_scores(model, X_cal)
    threshold = calibrate_threshold(cal_scores, y_cal, target_fpr=args.target_fpr)
    metrics_cal = evaluate_scores(cal_scores, y_cal, threshold)
    print(f"calibration ({calibration_split}): recall_ai={metrics_cal['recall_ai']:.4f}  fpr_real={metrics_cal['fpr_real']:.4f}")

    metrics_val, metrics_val_aug = None, None

    if X_val is not None and y_val is not None:
        metrics_val = evaluate_scores(ai_scores(model, X_val), y_val, threshold)
        print(f"validation:            recall_ai={metrics_val['recall_ai']:.4f}  fpr_real={metrics_val['fpr_real']:.4f}")

    if X_val_aug is not None and y_val_aug is not None:
        metrics_val_aug = evaluate_scores(ai_scores(model, X_val_aug), y_val_aug, threshold)
        print(f"validation_augmented:  recall_ai={metrics_val_aug['recall_ai']:.4f}  fpr_real={metrics_val_aug['fpr_real']:.4f}")

    bundle = {
        "task": "task03",
        "model_name": model_name,
        "model": model,
        "threshold": float(threshold),
        "target_fpr": float(args.target_fpr),
        "augmentation_variants": variants,
        "calibration_split": calibration_split,
    }
    joblib.dump(bundle, out_dir / "model.joblib")

    save_json(
        {
            "model_name": model_name,
            "target_fpr": float(args.target_fpr),
            "augmentation_variants": variants,
            "calibration_split": calibration_split,
            "calibration": metrics_cal,
            "validation": metrics_val,
            "validation_augmented": metrics_val_aug,
        },
        out_dir / "metrics.json",
    )

    print(f"\nsaved model  → {out_dir / 'model.joblib'}")
    print(f"saved metrics → {out_dir / 'metrics.json'}")


if __name__ == "__main__":
    main()
