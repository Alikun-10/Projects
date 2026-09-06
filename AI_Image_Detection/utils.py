from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np


RANDOM_SEED = 2026


def set_reproducible(seed: int = RANDOM_SEED) -> None:
    """Seed Python and NumPy randomness."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))


def solution_dir() -> Path:
    """Return the solution directory path."""
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """Return the read-only data directory path."""
    return solution_dir() / "data"


def artifacts_dir() -> Path:
    """Return the writable artifacts directory path."""
    p = solution_dir() / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dir(path: Path) -> Path:
    """Create a directory if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(obj: Dict[str, Any], path: Path) -> None:
    """Write a JSON file with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def load_json(path: Path) -> Dict[str, Any]:
    """Read a JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def common_arg_parser(description: str) -> argparse.ArgumentParser:
    """Create the shared command-line parser."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--timeout_seconds", type=int, default=10**9, help="Soft time budget provided by grader")
    p.add_argument("--seed", type=int, default=RANDOM_SEED)
    return p


class Timer:
    """Soft timeout helper for grader-provided budgets."""
    def __init__(self, timeout_seconds: int, reserve_seconds: int = 30):
        """Initialize the object."""
        self.start = time.perf_counter()
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.reserve_seconds = max(0, int(reserve_seconds))

    @property
    def elapsed(self) -> float:
        """Return elapsed seconds."""
        return time.perf_counter() - self.start

    @property
    def remaining(self) -> float:
        """Return remaining seconds."""
        return self.timeout_seconds - self.elapsed

    def should_stop(self) -> bool:
        """Check whether work should stop soon."""
        return self.remaining <= self.reserve_seconds


def binary_labels(source_class: np.ndarray) -> np.ndarray:
    """Merge source classes 1..5 into the single AI-generated class 1."""
    return (np.asarray(source_class) > 0).astype(np.int8)


def print_header(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80, flush=True)
