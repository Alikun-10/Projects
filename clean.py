from __future__ import annotations

"""Task 1.1: dataset exploration and deterministic cleaning.

This script is intentionally self-contained and CPU-friendly. It reads the labeled
training split, records exploratory statistics/figures, detects corrupt images,
and can write a deterministic cleaned image dataset under solution/artifacts/clean/.

The grader mounts solution/data/ as read-only, so all outputs go to artifacts/.
"""

import argparse
import hashlib
import io
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image, ImageFile
from tqdm import tqdm

from src.data import LABELED_SPLITS, parquet_files
from src.utils import artifacts_dir, common_arg_parser, data_dir, ensure_dir, print_header, save_json, set_reproducible

ImageFile.LOAD_TRUNCATED_IMAGES = True

NUMERIC_SHORTCUT_FEATURES = [
    "width", "height", "aspect", "byte_len",
    "gray_mean", "gray_std", "edge_mean", "dark_frac", "bright_frac",
    "mean_r", "mean_g", "mean_b", "std_r", "std_g", "std_b",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line options for this script."""
    parser = common_arg_parser("Task 1.1 dataset exploration and deterministic cleaning")
    parser.add_argument(
        "--split",
        default="auto",
        help="Labeled split to explore/clean. Default: train if present, otherwise first available labeled split for local samples.",
    )
    parser.add_argument("--image_size", type=int, default=128, help="Fixed cleaned image side length in pixels.")
    parser.add_argument("--jpeg_quality", type=int, default=95, help="JPEG quality for cleaned RGB images.")
    parser.add_argument("--batch_size", type=int, default=512, help="Rows per cleaned parquet shard.")
    parser.add_argument(
        "--write_cleaned_dataset",
        action="store_true",
        help="Also write resized cleaned image parquet shards. The timed default writes diagnostics only.",
    )
    parser.add_argument(
        "--stats_sample_rows",
        type=int,
        default=0,
        help="Number of rows to decode for pixel-level Task 1 diagnostics. Use 0 to decode every row.",
    )
    parser.add_argument(
        "--max_rows",
        type=int,
        default=None,
        help="Optional local-debug limit. Do not use for final submission.",
    )
    return parser.parse_args()


def pick_split(root: Path, requested: str) -> str:
    """Choose the labeled split to process."""
    if requested != "auto":
        if not parquet_files(root, requested):
            raise FileNotFoundError(f"No parquet files found for split {requested!r} under {root}")
        return requested
    if parquet_files(root, "train"):
        return "train"
    for split in LABELED_SPLITS:
        if parquet_files(root, split):
            print(f"warning: data/train not found; using {split!r} for local sample exploration only")
            return split
    raise FileNotFoundError(f"No labeled parquet files found under {root}")


def load_rgb(image_bytes: bytes) -> Image.Image:
    """Decode image bytes as an RGB Pillow image."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.convert("RGB")


def image_stats(image_bytes: bytes) -> Dict[str, Any]:
    """Decode an image and return metadata plus cheap descriptive statistics."""
    with Image.open(io.BytesIO(image_bytes)) as opened:
        orig_format = str(opened.format)
        orig_mode = str(opened.mode)
        width, height = int(opened.width), int(opened.height)
        rgb = opened.convert("RGB")

    arr = np.asarray(rgb, dtype=np.float32)
    gray = arr.mean(axis=2)
    # Cheap edge/texture proxy. Large values usually indicate sharper or more textured images.
    dx = np.abs(np.diff(gray, axis=1)).mean() if gray.shape[1] > 1 else 0.0
    dy = np.abs(np.diff(gray, axis=0)).mean() if gray.shape[0] > 1 else 0.0
    edge_mean = float((dx + dy) / 2.0)

    return {
        "width": width,
        "height": height,
        "aspect": float(width / max(height, 1)),
        "mode": orig_mode,
        "format": orig_format,
        "byte_len": int(len(image_bytes)),
        "gray_mean": float(gray.mean()),
        "gray_std": float(gray.std()),
        "edge_mean": edge_mean,
        "dark_frac": float((gray < 25).mean()),
        "bright_frac": float((gray > 230).mean()),
        "mean_r": float(arr[:, :, 0].mean()),
        "mean_g": float(arr[:, :, 1].mean()),
        "mean_b": float(arr[:, :, 2].mean()),
        "std_r": float(arr[:, :, 0].std()),
        "std_g": float(arr[:, :, 1].std()),
        "std_b": float(arr[:, :, 2].std()),
    }


def clean_image_bytes(image_bytes: bytes, image_size: int, jpeg_quality: int) -> bytes:
    """Deterministic cleaning: decode, RGB-convert, resize, re-encode."""
    img = load_rgb(image_bytes)
    try:
        resample = Image.Resampling.BILINEAR
    except AttributeError:  # Pillow < 9 fallback
        resample = Image.BILINEAR
    img = img.resize((image_size, image_size), resample=resample)
    buf = io.BytesIO()
    # optimize=False keeps output deterministic across runs and avoids extra CPU work.
    img.save(buf, format="JPEG", quality=int(jpeg_quality), optimize=False)
    return buf.getvalue()


def auc_rank_score(x: np.ndarray, y: np.ndarray) -> float:
    """Return AUC for using x alone to rank AI-generated images above real images.

    Values near 0.5 mean no obvious one-dimensional shortcut. Values near 0 or 1
    mean the feature strongly separates the two labels; we report max(AUC, 1-AUC)
    in the diagnostics because either direction can be suspicious.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.int8)
    mask = np.isfinite(x)
    x, y = x[mask], y[mask]
    n0 = int((y == 0).sum())
    n1 = int((y == 1).sum())
    if n0 == 0 or n1 == 0 or len(np.unique(x)) <= 1:
        return float("nan")

    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.arange(1, len(x) + 1, dtype=np.float64)

    # Average ranks for ties.
    sorted_x = x[order]
    start = 0
    while start < len(x):
        end = start + 1
        while end < len(x) and sorted_x[end] == sorted_x[start]:
            end += 1
        if end - start > 1:
            avg = (start + 1 + end) / 2.0
            ranks[order[start:end]] = avg
        start = end

    rank_sum_pos = ranks[y == 1].sum()
    auc = (rank_sum_pos - n1 * (n1 + 1) / 2.0) / (n0 * n1)
    return float(auc)


def shortcut_diagnostics(valid: pd.DataFrame) -> pd.DataFrame:
    """Measure simple feature shortcuts between real and AI labels."""
    rows: List[Dict[str, Any]] = []
    if valid.empty or valid["label"].nunique() < 2:
        return pd.DataFrame()
    for feat in NUMERIC_SHORTCUT_FEATURES:
        if feat not in valid.columns:
            continue
        real = pd.to_numeric(valid.loc[valid["label"] == 0, feat], errors="coerce").dropna().to_numpy()
        ai = pd.to_numeric(valid.loc[valid["label"] == 1, feat], errors="coerce").dropna().to_numpy()
        if len(real) == 0 or len(ai) == 0:
            continue
        pooled = np.concatenate([real, ai])
        pooled_std = float(np.std(pooled))
        diff = float(np.mean(ai) - np.mean(real))
        standardized_diff = float(diff / pooled_std) if pooled_std > 1e-12 else 0.0
        pair = valid[[feat, "label"]].copy()
        pair[feat] = pd.to_numeric(pair[feat], errors="coerce")
        pair = pair.dropna(subset=[feat, "label"])
        auc = auc_rank_score(pair[feat].to_numpy(), pair["label"].to_numpy())
        rows.append({
            "feature": feat,
            "real_mean": float(np.mean(real)),
            "ai_mean": float(np.mean(ai)),
            "difference_ai_minus_real": diff,
            "standardized_difference": standardized_diff,
            "auc_ai_higher": auc,
            "shortcut_strength_auc_symmetric": float(max(auc, 1.0 - auc)) if math.isfinite(auc) else float("nan"),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("shortcut_strength_auc_symmetric", ascending=False)
    return out


def plot_outputs(valid: pd.DataFrame, out_dir: Path, split: str) -> None:
    """Write basic dataset exploration plots."""
    if valid.empty:
        return

    # Source-class distribution. Labels 1..5 are AI generator subtypes.
    plt.figure(figsize=(6, 4))
    valid["source_class"].value_counts().sort_index().plot(kind="bar")
    plt.xlabel("source_class (0=real, 1..5=AI sources)")
    plt.ylabel("count")
    plt.title(f"Class distribution ({split})")
    plt.tight_layout()
    plt.savefig(out_dir / f"class_distribution_{split}.png", dpi=160)
    plt.close()

    plt.figure(figsize=(5, 4))
    valid["label"].value_counts().sort_index().rename(index={0: "real", 1: "AI"}).plot(kind="bar")
    plt.xlabel("binary label")
    plt.ylabel("count")
    plt.title(f"Binary class distribution ({split})")
    plt.tight_layout()
    plt.savefig(out_dir / f"binary_distribution_{split}.png", dpi=160)
    plt.close()

    size_valid = valid.dropna(subset=["width", "height"]) if {"width", "height"}.issubset(valid.columns) else pd.DataFrame()
    if not size_valid.empty:
        plt.figure(figsize=(6, 4))
        plt.scatter(size_valid["width"], size_valid["height"], s=12, alpha=0.55)
        plt.xlabel("width")
        plt.ylabel("height")
        plt.title(f"Image size distribution ({split})")
        plt.tight_layout()
        plt.savefig(out_dir / f"image_sizes_{split}.png", dpi=160)
        plt.close()

    for col, xlabel, title in [
        ("byte_len", "encoded image byte length", "Byte length by binary label"),
        ("gray_mean", "mean grayscale intensity", "Brightness by binary label"),
        ("edge_mean", "mean adjacent-pixel difference", "Texture/edge proxy by binary label"),
    ]:
        if col not in valid.columns:
            continue
        plt.figure(figsize=(6, 4))
        for label, group in valid.groupby("label"):
            values = pd.to_numeric(group[col], errors="coerce").dropna()
            if values.empty:
                continue
            plt.hist(values, bins=40, alpha=0.55, label="real" if label == 0 else "AI")
        plt.xlabel(xlabel)
        plt.ylabel("count")
        plt.title(f"{title} ({split})")
        plt.legend()
        plt.tight_layout()
        plt.savefig(out_dir / f"{col}_by_label_{split}.png", dpi=160)
        plt.close()


def write_markdown_notes(summary: Dict[str, Any], diagnostics: pd.DataFrame, out_path: Path) -> None:
    """Write concise Task 1 notes for the report."""
    split = summary["split"]
    binary = summary.get("binary_label_counts", {})
    source = summary.get("source_class_counts", {})
    size = summary.get("image_size_summary", {})
    potential = summary.get("potential_shortcut_features", [])

    lines = [
        f"# Task 1.1 notes for `{split}`",
        "",
        "## Dataset exploration",
        f"- Valid images: {summary.get('n_valid', 0)} / {summary.get('n_rows', 0)}.",
        f"- Corrupt/unreadable images removed: {summary.get('n_corrupt', 0)}.",
        f"- Duplicate hash groups: {summary.get('duplicates', {}).get('duplicate_hash_groups', 0)}; conflicting-label duplicate groups: {summary.get('duplicates', {}).get('conflicting_label_duplicate_groups', 0)}.",
        f"- Binary labels: {binary} where `0=real` and `1=AI-generated`.",
        f"- Original source-class counts: {source}.",
        f"- Image sizes: width {size.get('width_min')}..{size.get('width_max')}, height {size.get('height_min')}..{size.get('height_max')}.",
        f"- Formats: {summary.get('formats', {})}; modes: {summary.get('modes', {})}.",
        "",
        "## Possible shortcut characteristics",
    ]
    if potential:
        lines.append("The strongest one-dimensional differences were:")
        for item in potential[:5]:
            lines.append(
                f"- `{item['feature']}`: symmetric AUC={item['shortcut_strength_auc_symmetric']:.3f}, "
                f"real mean={item['real_mean']:.3f}, AI mean={item['ai_mean']:.3f}."
            )
        lines.append("These features should be discussed as possible shortcuts rather than automatically trusted semantic evidence.")
    else:
        lines.append("No strong single-feature shortcut was detected with the simple diagnostics used here.")

    lines += [
        "",
        "## Deterministic cleaning pipeline",
        "1. Scan every row for source class, binary label, byte length, SHA-256 hash, and duplicates.",
        f"2. Decode {summary.get('n_pixel_checked', 0)} rows for image dimensions and pixel-level shortcut diagnostics.",
        "3. Store Task 1 metadata and figures only under `solution/artifacts/clean/`, never under the read-only `solution/data/` directory.",
        f"4. Optional cleaned image shards can be regenerated with `--write_cleaned_dataset`; that path decodes, RGB-converts, resizes to `{summary.get('cleaned_image_size')}x{summary.get('cleaned_image_size')}`, and re-encodes JPEGs with fixed quality `{summary.get('jpeg_quality')}`.",
        "",
        "## Figures produced by `clean.py`",
        f"- `class_distribution_{split}.png`",
        f"- `binary_distribution_{split}.png`",
        f"- `image_sizes_{split}.png`",
        f"- `byte_len_by_label_{split}.png`",
        f"- `gray_mean_by_label_{split}.png`",
        f"- `edge_mean_by_label_{split}.png`",
        "",
        "Use these notes as a starting point for the final report and cite the artifacts generated from the full `train/` split.",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def flush_clean_batch(rows: List[Dict[str, Any]], cleaned_dir: Path, shard_idx: int) -> int:
    """Write one cleaned-image parquet shard."""
    if not rows:
        return shard_idx
    df = pd.DataFrame(rows)
    df.to_parquet(cleaned_dir / f"part-{shard_idx:05d}.parquet", index=False)
    rows.clear()
    return shard_idx + 1


def main() -> None:
    """Run the script entry point."""
    args = parse_args()
    set_reproducible(args.seed)

    root = data_dir()
    out_dir = ensure_dir(artifacts_dir() / "clean")
    split = pick_split(root, args.split)
    files = parquet_files(root, split)
    cleaned_dir = out_dir / f"cleaned_{split}_{args.image_size}px"
    if args.write_cleaned_dataset:
        ensure_dir(cleaned_dir)
        for old in cleaned_dir.glob("*.parquet"):
            old.unlink()

    print_header(f"Task 1.1: exploring and cleaning split {split!r}")
    print(f"input files: {[str(p) for p in files]}")
    print(f"outputs: {out_dir}")

    start = time.perf_counter()
    reserve_seconds = 10

    metadata_rows: List[Dict[str, Any]] = []
    corrupt_rows: List[Dict[str, Any]] = []
    clean_batch: List[Dict[str, Any]] = []
    seen_clean_hash_labels: set[tuple[str, int]] = set()
    n_cleaned_rows = 0
    n_skipped_same_label_duplicates = 0
    shard_idx = 0
    sample_id = 0
    stopped_early = False

    pbar_total: Optional[int] = None
    try:
        pbar_total = sum(len(pd.read_parquet(p, columns=["source_class"])) for p in files)
    except Exception:
        pbar_total = None
    stats_sample_rows = int(args.stats_sample_rows)
    decode_all_stats = stats_sample_rows <= 0 or (pbar_total is not None and stats_sample_rows >= pbar_total)
    stats_stride = 1
    if not decode_all_stats and pbar_total is not None:
        stats_stride = max(1, pbar_total // max(stats_sample_rows, 1))

    with tqdm(total=pbar_total, desc=f"clean {split}") as pbar:
        for file_idx, parquet_path in enumerate(files):
            df = pd.read_parquet(parquet_path, columns=["image", "source_class"])
            if not {"image", "source_class"}.issubset(df.columns):
                raise ValueError(f"{parquet_path} must contain columns image and source_class")
            for row_idx, (image_value, source_value) in enumerate(zip(df["image"].values, df["source_class"].values)):
                if args.max_rows is not None and sample_id >= args.max_rows:
                    stopped_early = True
                    break
                if time.perf_counter() - start > max(1, args.timeout_seconds - reserve_seconds):
                    print("warning: stopping early to avoid timeout")
                    stopped_early = True
                    break

                source_class = int(source_value)
                label = int(source_class > 0)
                raw_bytes = bytes(image_value)
                raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
                base = {
                    "sample_id": sample_id,
                    "source_file": parquet_path.name,
                    "source_row": int(row_idx),
                    "source_class": source_class,
                    "label": label,
                    "sha256": raw_sha256,
                    "byte_len": int(len(raw_bytes)),
                }
                should_decode = bool(args.write_cleaned_dataset or decode_all_stats)
                if not should_decode:
                    if pbar_total is None:
                        should_decode = sample_id < stats_sample_rows
                    else:
                        should_decode = sample_id % stats_stride == 0
                try:
                    if should_decode:
                        stats = image_stats(raw_bytes)
                        meta_row = {**base, **stats, "pixel_checked": 1, "is_valid": 1, "error": ""}
                    else:
                        stats = {}
                        meta_row = {**base, "pixel_checked": 0, "is_valid": 1, "error": ""}
                    metadata_rows.append(meta_row)

                    if args.write_cleaned_dataset:
                        clean_key = (raw_sha256, label)
                        if clean_key in seen_clean_hash_labels:
                            n_skipped_same_label_duplicates += 1
                        else:
                            seen_clean_hash_labels.add(clean_key)
                            cleaned_bytes = clean_image_bytes(raw_bytes, args.image_size, args.jpeg_quality)
                            clean_batch.append({
                                **base,
                                "image": cleaned_bytes,
                                "orig_width": stats["width"],
                                "orig_height": stats["height"],
                                "orig_format": stats["format"],
                                "orig_mode": stats["mode"],
                                "orig_byte_len": stats["byte_len"],
                                "clean_width": int(args.image_size),
                                "clean_height": int(args.image_size),
                            })
                            n_cleaned_rows += 1
                            if len(clean_batch) >= args.batch_size:
                                shard_idx = flush_clean_batch(clean_batch, cleaned_dir, shard_idx)
                except Exception as exc:
                    bad = {**base, "is_valid": 0, "error": repr(exc)}
                    metadata_rows.append(bad)
                    corrupt_rows.append(bad)

                sample_id += 1
                pbar.update(1)
            if stopped_early:
                break

    if args.write_cleaned_dataset:
        shard_idx = flush_clean_batch(clean_batch, cleaned_dir, shard_idx)

    metadata = pd.DataFrame(metadata_rows)
    metadata_path = out_dir / f"metadata_{split}.csv"
    metadata.to_csv(metadata_path, index=False)
    if corrupt_rows:
        pd.DataFrame(corrupt_rows).to_csv(out_dir / f"corrupt_{split}.csv", index=False)

    valid = metadata[metadata["is_valid"] == 1].copy() if not metadata.empty else pd.DataFrame()
    duplicate_summary: Dict[str, Any] = {
        "duplicate_hash_groups": 0,
        "duplicate_rows_total": 0,
        "same_label_duplicate_groups": 0,
        "conflicting_label_duplicate_groups": 0,
        "same_label_duplicate_rows_skipped_from_cleaned_dataset": int(n_skipped_same_label_duplicates),
    }
    if not valid.empty and "sha256" in valid.columns:
        duplicate_records: List[Dict[str, Any]] = []
        for sha256, group in valid.groupby("sha256"):
            if len(group) <= 1:
                continue
            labels = sorted(int(x) for x in group["label"].unique())
            duplicate_records.append({
                "sha256": sha256,
                "count": int(len(group)),
                "labels": ";".join(str(x) for x in labels),
                "source_classes": ";".join(str(int(x)) for x in sorted(group["source_class"].unique())),
                "sample_ids": ";".join(str(int(x)) for x in group["sample_id"].head(20)),
                "conflicting_labels": int(len(labels) > 1),
            })
        if duplicate_records:
            duplicate_df = pd.DataFrame(duplicate_records).sort_values(["conflicting_labels", "count"], ascending=False)
            duplicate_df.to_csv(out_dir / f"duplicates_{split}.csv", index=False)
            duplicate_summary = {
                "duplicate_hash_groups": int(len(duplicate_df)),
                "duplicate_rows_total": int(duplicate_df["count"].sum()),
                "same_label_duplicate_groups": int((duplicate_df["conflicting_labels"] == 0).sum()),
                "conflicting_label_duplicate_groups": int((duplicate_df["conflicting_labels"] == 1).sum()),
                "same_label_duplicate_rows_skipped_from_cleaned_dataset": int(n_skipped_same_label_duplicates),
                "duplicates_csv": str((out_dir / f"duplicates_{split}.csv").relative_to(root.parent)),
            }
    diagnostics = shortcut_diagnostics(valid)
    diagnostics_path = out_dir / f"shortcut_diagnostics_{split}.csv"
    diagnostics.to_csv(diagnostics_path, index=False)

    if not valid.empty:
        plot_outputs(valid, out_dir, split)

    source_counts = Counter(valid["source_class"].astype(int).tolist()) if not valid.empty else Counter()
    binary_counts = Counter(valid["label"].astype(int).tolist()) if not valid.empty else Counter()
    pixel_valid = valid[valid.get("pixel_checked", 0) == 1].copy() if not valid.empty else pd.DataFrame()
    formats = Counter(pixel_valid["format"].astype(str).tolist()) if "format" in pixel_valid else Counter()
    modes = Counter(pixel_valid["mode"].astype(str).tolist()) if "mode" in pixel_valid else Counter()

    potential_shortcuts: List[Dict[str, Any]] = []
    if not diagnostics.empty:
        suspicious = diagnostics[diagnostics["shortcut_strength_auc_symmetric"] >= 0.70]
        potential_shortcuts = suspicious.head(10).to_dict(orient="records")

    summary: Dict[str, Any] = {
        "split": split,
        "n_rows": int(len(metadata_rows)),
        "n_valid": int(len(valid)),
        "n_pixel_checked": int(len(pixel_valid)),
        "n_corrupt": int(len(corrupt_rows)),
        "stopped_early": bool(stopped_early),
        "source_class_counts": {str(k): int(v) for k, v in sorted(source_counts.items())},
        "binary_label_counts": {str(k): int(v) for k, v in sorted(binary_counts.items())},
        "formats": dict(formats),
        "modes": dict(modes),
        "cleaned_dataset_written": bool(args.write_cleaned_dataset),
        "cleaned_dataset_dir": str(cleaned_dir.relative_to(root.parent)) if args.write_cleaned_dataset else None,
        "cleaned_parquet_shards": int(shard_idx),
        "cleaned_rows_written": int(n_cleaned_rows),
        "duplicates": duplicate_summary,
        "cleaned_image_size": int(args.image_size),
        "jpeg_quality": int(args.jpeg_quality),
        "metadata_csv": str(metadata_path.relative_to(root.parent)),
        "shortcut_diagnostics_csv": str(diagnostics_path.relative_to(root.parent)),
        "potential_shortcut_features": potential_shortcuts,
        "deterministic_cleaning_pipeline": (
            [
                "decode image bytes with Pillow",
                "remove corrupt or unreadable images",
                "convert every valid image to RGB",
                f"resize every valid image to {args.image_size}x{args.image_size} with bilinear interpolation",
                f"re-encode cleaned images as JPEG with fixed quality {args.jpeg_quality}",
                "skip exact duplicate images with the same binary label in cleaned training shards",
                "write derived data only below solution/artifacts",
            ]
            if args.write_cleaned_dataset
            else [
                "scan every row for source class, binary label, byte length, SHA-256, and duplicates",
                "decode rows for image dimensions and pixel-level shortcut diagnostics",
                "write derived data only below solution/artifacts",
                "cleaned image shards can be regenerated with --write_cleaned_dataset",
            ]
        ),
    }
    if not pixel_valid.empty:
        summary["image_size_summary"] = {
            "width_min": int(pixel_valid["width"].min()),
            "width_median": float(pixel_valid["width"].median()),
            "width_max": int(pixel_valid["width"].max()),
            "height_min": int(pixel_valid["height"].min()),
            "height_median": float(pixel_valid["height"].median()),
            "height_max": int(pixel_valid["height"].max()),
            "aspect_min": float(pixel_valid["aspect"].min()),
            "aspect_median": float(pixel_valid["aspect"].median()),
            "aspect_max": float(pixel_valid["aspect"].max()),
        }
        by_label: Dict[str, Dict[str, Dict[str, float]]] = {}
        feature_cols = [c for c in NUMERIC_SHORTCUT_FEATURES if c in valid.columns]
        grouped = valid.groupby("label")[feature_cols].agg(["mean", "std", "min", "median", "max"]).round(6)
        for label_value, row in grouped.iterrows():
            label_key = str(int(label_value))
            by_label[label_key] = {}
            for feature in feature_cols:
                by_label[label_key][feature] = {}
                for stat_name in ["mean", "std", "min", "median", "max"]:
                    value = row[(feature, stat_name)]
                    by_label[label_key][feature][stat_name] = None if pd.isna(value) else float(value)
        summary["numeric_feature_summary_by_label"] = by_label

    save_json(summary, out_dir / f"summary_{split}.json")
    write_markdown_notes(summary, diagnostics, out_dir / f"task1_report_notes_{split}.md")

    print(f"wrote metadata: {metadata_path}")
    print(f"wrote summary: {out_dir / f'summary_{split}.json'}")
    if args.write_cleaned_dataset:
        print(f"wrote cleaned parquet shards: {cleaned_dir} ({shard_idx} files)")
    print(f"wrote report notes: {out_dir / f'task1_report_notes_{split}.md'}")


if __name__ == "__main__":
    main()
