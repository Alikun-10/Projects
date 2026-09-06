from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageFile
from tqdm import tqdm

from .utils import binary_labels

ImageFile.LOAD_TRUNCATED_IMAGES = True

LABELED_SPLITS = [
    "train",
    "calibration",
    "calibration_augmented",
    "validation",
    "validation_augmented",
]
PREDICT_SPLIT = "predict"


def split_dir(root: Path, split: str) -> Path:
    """Return the directory for a data split."""
    return root / split


def parquet_files(root: Path, split: str) -> List[Path]:
    """List parquet files for a split."""
    d = split_dir(root, split)
    if not d.exists():
        return []
    return sorted(d.glob("*.parquet"))


def read_parquet_files(files: Sequence[Path], columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Read and concatenate parquet files."""
    frames = []
    for p in files:
        frames.append(pd.read_parquet(p, columns=columns))
    if not frames:
        return pd.DataFrame(columns=columns or [])
    return pd.concat(frames, ignore_index=True)


def read_split(root: Path, split: str, columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Read all parquet files for one split."""
    return read_parquet_files(parquet_files(root, split), columns=columns)


def load_image(image_bytes: bytes) -> Image.Image:
    """Decode image bytes as RGB."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.convert("RGB")


def image_metadata(image_bytes: bytes) -> Dict[str, object]:
    """Return basic metadata for image bytes."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        return {
            "width": int(img.width),
            "height": int(img.height),
            "mode": str(img.mode),
            "format": str(img.format),
            "byte_len": int(len(image_bytes)),
        }


def iter_labeled_rows(root: Path, split: str) -> Iterator[Tuple[int, bytes, int]]:
    """Yield indexed image bytes and source labels."""
    files = parquet_files(root, split)
    global_idx = 0
    for p in files:
        df = pd.read_parquet(p)
        if not {"image", "source_class"}.issubset(df.columns):
            raise ValueError(f"{p} must contain image and source_class columns")
        for image_bytes, source_class in zip(df["image"].values, df["source_class"].values):
            yield global_idx, image_bytes, int(source_class)
            global_idx += 1


def iter_predict_rows(root: Path, split: str = PREDICT_SPLIT) -> Iterator[Tuple[int, bytes]]:
    """Yield row IDs and image bytes for prediction."""
    files = parquet_files(root, split)
    for p in files:
        df = pd.read_parquet(p)
        if not {"row_id", "image"}.issubset(df.columns):
            raise ValueError(f"{p} must contain row_id and image columns")
        for row_id, image_bytes in zip(df["row_id"].values, df["image"].values):
            yield int(row_id), image_bytes


def has_split(root: Path, split: str) -> bool:
    """Check whether a split exists."""
    return len(parquet_files(root, split)) > 0


def split_summary(root: Path) -> Dict[str, object]:
    """Summarize available data splits."""
    out: Dict[str, object] = {}
    for split in LABELED_SPLITS + [PREDICT_SPLIT]:
        files = parquet_files(root, split)
        out[split] = {"exists": bool(files), "files": [str(p) for p in files]}
    return out
