from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import LABELED_SPLITS, parquet_files, read_split
from src.features import extract_feature_matrix_from_bytes, feature_names
from src.utils import artifacts_dir, binary_labels, common_arg_parser, data_dir, ensure_dir, print_header, save_json, set_reproducible


def prepare_labeled_split(root: Path, out_dir: Path, split: str, workers: int) -> None:
    """Extract and cache deterministic features for one labeled split."""
    files = parquet_files(root, split)
    if not files:
        print(f"skip missing split: {split}")
        return
    target = out_dir / f"{split}_features.npz"
    meta_target = out_dir / f"{split}_meta.json"
    if target.exists() and meta_target.exists():
        print(f"skip already prepared split: {split}")
        return
    print_header(f"Preparing {split}")
    df = read_split(root, split)
    if not {"image", "source_class"}.issubset(df.columns):
        raise ValueError(f"split {split} must have image and source_class columns")
    y = binary_labels(df["source_class"].values)
    X, y_clean = extract_feature_matrix_from_bytes(df["image"].values, labels=y, desc=f"{split} features", workers=workers)
    np.savez_compressed(out_dir / f"{split}_features.npz", X=X, y=y_clean)
    meta = {
        "split": split,
        "n_raw": int(len(df)),
        "n_prepared": int(len(y_clean)),
        "source_class_counts": {str(k): int(v) for k, v in df["source_class"].value_counts().sort_index().items()},
        "binary_counts": {str(k): int(v) for k, v in pd.Series(y_clean).value_counts().sort_index().items()},
    }
    save_json(meta, out_dir / f"{split}_meta.json")


def main() -> None:
    """Run the script entry point."""
    parser = common_arg_parser("Prepare deterministic feature matrices")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()
    set_reproducible(args.seed)

    root = data_dir()
    out_dir = ensure_dir(artifacts_dir() / "prepared")
    save_json({"feature_names": feature_names()}, out_dir / "feature_names.json")

    # Important: do not read solution/data/predict here.
    for split in LABELED_SPLITS:
        prepare_labeled_split(root, out_dir, split, workers=max(1, int(args.workers)))

    print(f"wrote prepared features to {out_dir}")


if __name__ == "__main__":
    main()
