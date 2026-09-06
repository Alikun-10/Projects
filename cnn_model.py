from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageFile

from .calibration import calibrate_threshold, evaluate_scores
from .data import iter_labeled_rows, parquet_files, read_split
from .utils import Timer, binary_labels, ensure_dir

ImageFile.LOAD_TRUNCATED_IMAGES = True


def _torch():
    """Import torch lazily so non-CNN paths stay lightweight."""
    import torch
    return torch


def _nn():
    """Import torch.nn lazily for CNN definitions."""
    import torch.nn as nn
    return nn


class SmallCNN(_nn().Module):
    """Compact CNN trained from scratch for Task 2."""
    def __init__(self, width: int = 24, dropout: float = 0.25) -> None:
        """Initialize the object."""
        super().__init__()
        nn = _nn()
        self.features = nn.Sequential(
            nn.Conv2d(3, width, kernel_size=3, padding=1),
            nn.BatchNorm2d(width),
            nn.ReLU(inplace=True),
            nn.Conv2d(width, width, kernel_size=3, padding=1),
            nn.BatchNorm2d(width),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(width, width * 2, kernel_size=3, padding=1),
            nn.BatchNorm2d(width * 2),
            nn.ReLU(inplace=True),
            nn.Conv2d(width * 2, width * 2, kernel_size=3, padding=1),
            nn.BatchNorm2d(width * 2),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(width * 2, width * 4, kernel_size=3, padding=1),
            nn.BatchNorm2d(width * 4),
            nn.ReLU(inplace=True),
            nn.Conv2d(width * 4, width * 4, kernel_size=3, padding=1),
            nn.BatchNorm2d(width * 4),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(width * 4, 2),
        )

    def forward(self, x):
        """Run the forward pass."""
        return self.classifier(self.features(x))


def _pil_to_tensor(image_bytes: bytes, image_size: int = 128):
    """Decode image bytes into a normalized tensor."""
    torch = _torch()
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB").resize((image_size, image_size), Image.Resampling.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = np.transpose(arr, (2, 0, 1)).copy()
    return torch.from_numpy(arr)


class ImageBytesDataset(_torch().utils.data.Dataset):
    """Dataset wrapper for image bytes and optional labels."""
    def __init__(self, images: Sequence[bytes], labels: Optional[Sequence[int]] = None, image_size: int = 128) -> None:
        """Initialize the object."""
        self.images = list(images)
        self.labels = None if labels is None else np.asarray(labels, dtype=np.int64)
        self.image_size = int(image_size)

    def __len__(self) -> int:
        """Return the number of images."""
        return len(self.images)

    def __getitem__(self, idx: int):
        """Return one tensor sample and optional label."""
        x = _pil_to_tensor(bytes(self.images[idx]), self.image_size)
        if self.labels is None:
            return x
        return x, int(self.labels[idx])


def load_labeled_image_bytes(root: Path, split: str) -> Tuple[List[bytes], np.ndarray]:
    """Load image bytes and binary labels from a labeled split."""
    images: List[bytes] = []
    labels: List[int] = []
    for _, image_bytes, source_class in iter_labeled_rows(root, split):
        images.append(bytes(image_bytes))
        labels.append(int(source_class > 0))
    return images, np.asarray(labels, dtype=np.int64)


def load_cleaned_train(clean_dir: Path) -> Optional[Tuple[List[bytes], np.ndarray]]:
    """Load cleaned training shards when they are available."""
    files = sorted(clean_dir.glob("*.parquet"))
    if not files:
        return None
    frames = [pd.read_parquet(p, columns=["image", "label"]) for p in files]
    df = pd.concat(frames, ignore_index=True)
    return [bytes(x) for x in df["image"].values], df["label"].astype(np.int64).to_numpy()


def score_images(model, images: Sequence[bytes], batch_size: int = 128, image_size: int = 128) -> np.ndarray:
    """Return AI probabilities for a sequence of images."""
    torch = _torch()
    device = torch.device("cpu")
    model.to(device)
    model.eval()
    loader = torch.utils.data.DataLoader(ImageBytesDataset(images, image_size=image_size), batch_size=batch_size, shuffle=False, num_workers=0)
    scores: List[np.ndarray] = []
    with torch.no_grad():
        for x in loader:
            logits = model(x.to(device))
            probs = torch.softmax(logits, dim=1)[:, 1]
            scores.append(probs.cpu().numpy())
    return np.concatenate(scores).astype(np.float64) if scores else np.empty(0, dtype=np.float64)


@dataclass
class CNNResult:
    """Training result bundle for the CNN candidate."""
    model_path: Path
    threshold: float
    metrics_calibration: Dict[str, object]
    metrics_validation: Optional[Dict[str, object]]
    metrics_validation_augmented: Optional[Dict[str, object]]
    cal_scores: np.ndarray = None
    val_scores: Optional[np.ndarray] = None
    vaug_scores: Optional[np.ndarray] = None


def train_cnn(
    root: Path,
    artifacts_root: Path,
    target_fpr: float = 0.20,
    seed: int = 2026,
    timeout_seconds: int = 1800,
    image_size: int = 128,
    batch_size: int = 64,
    max_epochs: int = 10,
    patience: int = 3,
    width: int = 24,
) -> CNNResult:
    """Train and calibrate the compact CNN candidate."""
    torch = _torch()
    nn = _nn()
    torch.manual_seed(seed)
    torch.set_num_threads(min(8, torch.get_num_threads()))
    torch.set_num_interop_threads(1)

    out_dir = ensure_dir(artifacts_root / "task02")
    model_path = out_dir / "cnn_model.pt"
    clean_train_dir = artifacts_root / "clean" / f"cleaned_train_{image_size}px"
    cleaned = load_cleaned_train(clean_train_dir)
    if cleaned is None:
        train_images, y_train = load_labeled_image_bytes(root, "train")
    else:
        train_images, y_train = cleaned
    cal_images, y_cal = load_labeled_image_bytes(root, "calibration")
    val_images, y_val = load_labeled_image_bytes(root, "validation") if parquet_files(root, "validation") else ([], np.empty(0, dtype=np.int64))
    vaug_images, y_vaug = load_labeled_image_bytes(root, "validation_augmented") if parquet_files(root, "validation_augmented") else ([], np.empty(0, dtype=np.int64))

    device = torch.device("cpu")
    model = SmallCNN(width=width, dropout=0.25).to(device)
    counts = np.bincount(y_train, minlength=2).astype(np.float32)
    weights = counts.sum() / np.maximum(counts, 1.0)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    gen = torch.Generator().manual_seed(seed)
    loader = torch.utils.data.DataLoader(
        ImageBytesDataset(train_images, y_train, image_size=image_size),
        batch_size=batch_size,
        shuffle=True,
        generator=gen,
        num_workers=0,
    )
    timer = Timer(timeout_seconds=timeout_seconds, reserve_seconds=120)
    best_key = (-1.0, 0.0)
    best_state = None
    best_threshold = 0.5
    best_cal = None
    best_val = None
    best_cal_scores: Optional[np.ndarray] = None
    best_val_scores: Optional[np.ndarray] = None
    stale = 0

    for epoch in range(max_epochs):
        model.train()
        losses: List[float] = []
        for x, y in loader:
            if timer.should_stop():
                break
            optimizer.zero_grad(set_to_none=True)
            logits = model(x.to(device))
            loss = criterion(logits, y.to(device))
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        cal_scores = score_images(model, cal_images, batch_size=batch_size, image_size=image_size)
        threshold = calibrate_threshold(cal_scores, y_cal, target_fpr=target_fpr)
        cal_metrics = evaluate_scores(cal_scores, y_cal, threshold)
        val_scores_epoch: Optional[np.ndarray] = None
        val_metrics = None
        if len(val_images):
            val_scores_epoch = score_images(model, val_images, batch_size=batch_size, image_size=image_size)
            val_metrics = evaluate_scores(val_scores_epoch, y_val, threshold)
        metric_for_stop = val_metrics or cal_metrics
        feasible = float(metric_for_stop["fpr_real"]) <= target_fpr + 1e-12
        key = (float(metric_for_stop["recall_ai"]), -float(metric_for_stop["fpr_real"])) if feasible else (-1.0, -float(metric_for_stop["fpr_real"]))
        print(f"cnn epoch {epoch+1}/{max_epochs} loss={np.mean(losses) if losses else float('nan'):.4f} cal={cal_metrics} val={val_metrics}", flush=True)
        if key > best_key:
            best_key = key
            best_state = {k: v.cpu() for k, v in model.state_dict().items()}
            best_threshold = float(threshold)
            best_cal = cal_metrics
            best_val = val_metrics
            best_cal_scores = cal_scores.copy()
            best_val_scores = val_scores_epoch.copy() if val_scores_epoch is not None else None
            torch.save({"state_dict": best_state, "image_size": image_size, "width": width, "threshold": best_threshold}, model_path)
            stale = 0
        else:
            stale += 1
        if stale >= patience or timer.should_stop():
            break

    if best_state is None:
        best_state = {k: v.cpu() for k, v in model.state_dict().items()}
        torch.save({"state_dict": best_state, "image_size": image_size, "width": width, "threshold": best_threshold}, model_path)
        best_cal_scores = score_images(model, cal_images, batch_size=batch_size, image_size=image_size)
        best_cal = evaluate_scores(best_cal_scores, y_cal, best_threshold)
    model.load_state_dict(best_state)
    vaug_scores: Optional[np.ndarray] = None
    vaug_metrics = None
    if len(vaug_images):
        vaug_scores = score_images(model, vaug_images, batch_size=batch_size, image_size=image_size)
        vaug_metrics = evaluate_scores(vaug_scores, y_vaug, best_threshold)
    return CNNResult(
        model_path=model_path,
        threshold=float(best_threshold),
        metrics_calibration=best_cal or {},
        metrics_validation=best_val,
        metrics_validation_augmented=vaug_metrics,
        cal_scores=best_cal_scores if best_cal_scores is not None else np.empty(0, dtype=np.float64),
        val_scores=best_val_scores,
        vaug_scores=vaug_scores,
    )


def load_cnn_model(model_path: Path):
    """Load a saved CNN checkpoint for inference."""
    torch = _torch()
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model = SmallCNN(width=int(checkpoint.get("width", 24)))
    model.load_state_dict(checkpoint["state_dict"])
    return model, int(checkpoint.get("image_size", 128))
