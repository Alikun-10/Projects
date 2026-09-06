from __future__ import annotations

import io
import multiprocessing as mp
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from tqdm import tqdm

from .data import load_image

try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover for older Pillow
    RESAMPLE_BILINEAR = Image.BILINEAR
    RESAMPLE_LANCZOS = Image.LANCZOS


def _safe_float(x: float) -> float:
    """Return a finite float value."""
    if np.isfinite(x):
        return float(x)
    return 0.0


def _entropy_from_hist(hist: np.ndarray) -> float:
    """Compute entropy from histogram counts."""
    p = hist.astype(np.float64)
    s = p.sum()
    if s <= 0:
        return 0.0
    p = p / s
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def _gradient_features(gray: np.ndarray) -> List[float]:
    """Compute gradient and Laplacian texture features."""
    gray = gray.astype(np.float32)
    gx = np.diff(gray, axis=1, append=gray[:, -1:])
    gy = np.diff(gray, axis=0, append=gray[-1:, :])
    mag = np.sqrt(gx * gx + gy * gy)
    lap = np.zeros_like(gray, dtype=np.float32)
    lap[1:-1, 1:-1] = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return [
        _safe_float(mag.mean()),
        _safe_float(mag.std()),
        _safe_float(np.quantile(mag, 0.90)),
        _safe_float(np.quantile(mag, 0.99)),
        _safe_float((mag > 15).mean()),
        _safe_float((mag > 30).mean()),
        _safe_float(lap.var()),
        _safe_float(np.mean(np.abs(lap))),
    ]


def _multiscale_gradient_features(gray64: np.ndarray) -> List[float]:
    """Gradient magnitude mean/std/p90 at 32×32 scale (3 features).

    Natural images are self-similar across scales; AI images break this.
    Coarser scale is robust to blur/JPEG because low-frequency structure persists.
    """
    # Downsample 64×64 gray to 32×32 via 2×2 block averaging
    g32 = gray64.reshape(32, 2, 32, 2).mean(axis=(1, 3)).astype(np.float32)
    gx = np.diff(g32, axis=1, append=g32[:, -1:])
    gy = np.diff(g32, axis=0, append=g32[-1:, :])
    mag32 = np.sqrt(gx * gx + gy * gy)
    return [
        _safe_float(mag32.mean()),
        _safe_float(mag32.std()),
        _safe_float(np.quantile(mag32, 0.90)),
    ]


def _hsv_features(arr: np.ndarray) -> List[float]:
    """HSV H and S channel statistics (10 features).

    AI images from diffusion/GAN models cluster in HSV space: oversaturated,
    biased hue distributions. This signal survives JPEG, blur, and downscaling.
    Returns H(mean,std,p10,p50,p90) + S(mean,std,p10,p50,p90).
    """
    rgb = arr / 255.0
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    s = np.where(cmax > 1e-6, delta / (cmax + 1e-8), 0.0)

    h = np.zeros_like(delta, dtype=np.float32)
    m_r = (cmax == r) & (delta > 1e-6)
    m_g = (cmax == g) & (delta > 1e-6)
    m_b = (cmax == b) & (delta > 1e-6)
    h[m_r] = ((g[m_r] - b[m_r]) / (delta[m_r] + 1e-8)) % 6.0
    h[m_g] = ((b[m_g] - r[m_g]) / (delta[m_g] + 1e-8)) + 2.0
    h[m_b] = ((r[m_b] - g[m_b]) / (delta[m_b] + 1e-8)) + 4.0
    h = h / 6.0  # [0, 1]

    feats: List[float] = []
    for ch in (h, s):
        x = ch.flatten().astype(np.float64)
        feats += [
            _safe_float(x.mean()),
            _safe_float(x.std()),
            _safe_float(np.quantile(x, 0.10)),
            _safe_float(np.quantile(x, 0.50)),
            _safe_float(np.quantile(x, 0.90)),
        ]
    return feats  # 10 features


def _frequency_features(gray_small: np.ndarray) -> List[float]:
    """Compute simple FFT energy features."""
    arr = gray_small.astype(np.float32)
    arr = arr - arr.mean()
    fft = np.fft.fftshift(np.fft.fft2(arr))
    power = np.abs(fft) ** 2
    h, w = power.shape
    yy, xx = np.ogrid[:h, :w]
    cy, cx = h // 2, w // 2
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    total = power.sum() + 1e-8
    low = power[r <= min(h, w) * 0.10].sum() / total
    mid = power[(r > min(h, w) * 0.10) & (r <= min(h, w) * 0.28)].sum() / total
    high = power[r > min(h, w) * 0.28].sum() / total
    return [_safe_float(low), _safe_float(mid), _safe_float(high)]


def _box_blur(arr: np.ndarray) -> np.ndarray:
    """Fast 3×3 box blur via reflect padding."""
    padded = np.pad(arr.astype(np.float32), 1, mode="reflect")
    return (
        padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:]
        + padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:]
        + padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
    ) / 9.0


def _noise_features(gray: np.ndarray, rgb_arr: np.ndarray) -> List[float]:
    """Noise residual stats and cross-channel correlations.

    Real camera images carry sensor/demosaicing noise; AI images are denoised by
    construction and have fundamentally different residual distributions.
    Returns 11 features.
    """
    gray_resid = gray.astype(np.float32) - _box_blur(gray)
    abs_r = np.abs(gray_resid)
    r_flat = gray_resid.flatten()
    r_std = float(r_flat.std()) + 1e-8
    kurt = float(np.mean(((r_flat - r_flat.mean()) / r_std) ** 4)) - 3.0

    feats: List[float] = [
        _safe_float(float(gray_resid.std())),
        _safe_float(float(np.percentile(abs_r, 90))),
        _safe_float(float(np.percentile(abs_r, 99))),
        _safe_float(float((abs_r > 5.0).mean())),
        _safe_float(kurt),
    ]

    ch_residuals: List[np.ndarray] = []
    for c in range(3):
        resid_c = rgb_arr[:, :, c].astype(np.float32) - _box_blur(rgb_arr[:, :, c])
        ch_residuals.append(resid_c.flatten())
        feats.append(_safe_float(float(resid_c.std())))

    # Cross-channel residual correlations (Bayer demosaicing signature in real photos)
    for i, j in ((0, 1), (1, 2), (0, 2)):
        try:
            corr = float(np.corrcoef(ch_residuals[i], ch_residuals[j])[0, 1])
        except Exception:
            corr = 0.0
        feats.append(_safe_float(corr))

    return feats  # 5 + 3 + 3 = 11


def _radial_spectrum_features(gray_resid: np.ndarray) -> List[float]:
    """Fit log(power) vs log(freq) on the azimuthal residual spectrum.

    Real images follow ~1/f^α; diffusion/GAN outputs deviate measurably.
    Returns 3 features: slope, intercept, fit-MSE.
    """
    fft = np.fft.fftshift(np.fft.fft2(gray_resid.astype(np.float32)))
    power = np.abs(fft) ** 2
    h, w = power.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).flatten()
    p = power.flatten()
    r_max = min(h, w) / 2.0
    n_bins = 16
    bin_centers, bin_powers = [], []
    for i in range(1, n_bins + 1):
        lo = r_max * (i - 1) / n_bins
        hi = r_max * i / n_bins
        mask = (r >= lo) & (r < hi)
        if mask.sum() > 0:
            bin_centers.append((lo + hi) / 2.0)
            bin_powers.append(float(p[mask].mean()))
    if len(bin_centers) < 3:
        return [0.0, 0.0, 0.0]
    bc = np.array(bin_centers, dtype=np.float32)
    bp = np.array(bin_powers, dtype=np.float32)
    valid = bp > 0
    if valid.sum() < 3:
        return [0.0, 0.0, 0.0]
    lf = np.log(bc[valid] + 1e-8)
    lp = np.log(bp[valid] + 1e-8)
    coeffs = np.polyfit(lf, lp, 1)
    fitted = np.polyval(coeffs, lf)
    mse = float(np.mean((lp - fitted) ** 2))
    return [_safe_float(float(coeffs[0])), _safe_float(float(coeffs[1])), _safe_float(mse)]


def _glcm_features(gray: np.ndarray) -> List[float]:
    """GLCM texture: contrast, homogeneity, energy, correlation (mean+std each = 8 features)."""
    try:
        from skimage.feature import graycomatrix, graycoprops
        gray8 = np.clip(gray.astype(np.uint8) // 32, 0, 7)
        glcm = graycomatrix(gray8, distances=[1, 2], angles=[0, np.pi / 2],
                            levels=8, symmetric=True, normed=True)
        feats: List[float] = []
        for prop in ("contrast", "homogeneity", "energy", "correlation"):
            vals = graycoprops(glcm, prop)
            feats.append(_safe_float(float(vals.mean())))
            feats.append(_safe_float(float(vals.std())))
        return feats
    except Exception:
        return [0.0] * 8


def _lbp_features(gray: np.ndarray) -> List[float]:
    """Local Binary Pattern histogram (10 uniform bins = 10 features)."""
    try:
        from skimage.feature import local_binary_pattern
        lbp = local_binary_pattern(gray.astype(np.uint8), P=8, R=1, method="uniform")
        hist, _ = np.histogram(lbp, bins=10, range=(0.0, 10.0), density=True)
        return [_safe_float(float(v)) for v in hist]
    except Exception:
        return [0.0] * 10


def feature_names(grid_size: int = 8) -> List[str]:
    """Return engineered feature names in extraction order."""
    names: List[str] = []
    for channel in ("r", "g", "b"):
        names += [
            f"{channel}_mean",
            f"{channel}_std",
            f"{channel}_min",
            f"{channel}_max",
            f"{channel}_p10",
            f"{channel}_p50",
            f"{channel}_p90",
            f"{channel}_entropy",
        ]
    names += ["gray_mean", "gray_std", "gray_p10", "gray_p50", "gray_p90"]
    names += [
        "hsv_h_mean", "hsv_h_std", "hsv_h_p10", "hsv_h_p50", "hsv_h_p90",
        "hsv_s_mean", "hsv_s_std", "hsv_s_p10", "hsv_s_p50", "hsv_s_p90",
    ]
    names += [
        "grad_mean",
        "grad_std",
        "grad_p90",
        "grad_p99",
        "edge_frac_15",
        "edge_frac_30",
        "lap_var",
        "lap_abs_mean",
    ]
    names += ["grad32_mean", "grad32_std", "grad32_p90"]
    names += ["fft_low", "fft_mid", "fft_high"]
    # Noise residual features (sensor/demosaicing noise vs AI denoising)
    names += [
        "nr_gray_std", "nr_gray_p90", "nr_gray_p99", "nr_gray_frac5", "nr_gray_kurt",
        "nr_r_std", "nr_g_std", "nr_b_std",
        "nr_corr_rg", "nr_corr_gb", "nr_corr_rb",
    ]
    # Radial spectrum slope on noise residual (1/f^alpha deviation)
    names += ["rspec_slope", "rspec_intercept", "rspec_mse"]
    # GLCM texture (mean+std for contrast, homogeneity, energy, correlation)
    names += [
        "glcm_contrast_m", "glcm_contrast_s",
        "glcm_homo_m", "glcm_homo_s",
        "glcm_energy_m", "glcm_energy_s",
        "glcm_corr_m", "glcm_corr_s",
    ]
    # LBP histogram (10 uniform bins)
    names += [f"lbp_{i}" for i in range(10)]
    # Tiny 4×4 grayscale patch (spatial structure, reduced from 8×8)
    names += [f"tiny_gray_{i}" for i in range(4 * 4)]
    # tiny RGB pixels removed — they encode scene content, not generation artifacts
    return names


def extract_features_from_image(img: Image.Image, byte_len: Optional[int] = None, grid_size: int = 8) -> np.ndarray:
    """Extract deterministic engineered features from an image."""
    img = img.convert("RGB")
    width, height = img.size
    small_rgb_img = img.resize((64, 64), RESAMPLE_BILINEAR)
    arr = np.asarray(small_rgb_img, dtype=np.float32)
    gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])

    feats: List[float] = []

    for c in range(3):
        x = arr[:, :, c].reshape(-1)
        hist, _ = np.histogram(x, bins=16, range=(0, 255))
        feats += [
            _safe_float(x.mean()),
            _safe_float(x.std()),
            _safe_float(x.min()),
            _safe_float(x.max()),
            _safe_float(np.quantile(x, 0.10)),
            _safe_float(np.quantile(x, 0.50)),
            _safe_float(np.quantile(x, 0.90)),
            _entropy_from_hist(hist),
        ]

    g = gray.reshape(-1)
    feats += [
        _safe_float(g.mean()),
        _safe_float(g.std()),
        _safe_float(np.quantile(g, 0.10)),
        _safe_float(np.quantile(g, 0.50)),
        _safe_float(np.quantile(g, 0.90)),
    ]
    feats += _hsv_features(arr)  # 10 features: H and S channel stats
    grad_feats = _gradient_features(gray)
    feats += grad_feats
    feats += _multiscale_gradient_features(gray)  # 3 features at 32×32 scale
    feats += _frequency_features(np.asarray(img.convert("L").resize((32, 32), RESAMPLE_BILINEAR), dtype=np.float32))

    # Noise residual + cross-channel correlations (11 features)
    gray_resid = gray.astype(np.float32) - _box_blur(gray)
    feats += _noise_features(gray, arr)

    # Radial spectrum slope on noise residual (3 features)
    feats += _radial_spectrum_features(gray_resid)

    # GLCM texture features (8 features)
    feats += _glcm_features(gray)

    # LBP histogram (10 features)
    feats += _lbp_features(gray)

    # Tiny 4×4 grayscale (16 features — reduced from 8×8=64; tiny RGB dropped entirely)
    tiny_gray = img.convert("L").resize((4, 4), RESAMPLE_BILINEAR)
    feats += (np.asarray(tiny_gray, dtype=np.float32).reshape(-1) / 255.0).tolist()

    return np.asarray(feats, dtype=np.float32)


def extract_features(image_bytes: bytes, grid_size: int = 8) -> np.ndarray:
    """Extract deterministic content features from encoded image bytes."""
    return extract_features_from_image(load_image(image_bytes), byte_len=len(image_bytes), grid_size=grid_size)


def augment_image(img: Image.Image, variant: str) -> Image.Image:
    """Apply one deterministic augmentation variant."""
    img = img.convert("RGB")
    if variant == "original":
        return img
    if variant == "jpeg70":
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    if variant == "jpeg45":
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=45)
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    if variant == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=1.1))
    if variant == "downup":
        w, h = img.size
        small = img.resize((max(16, w // 2), max(16, h // 2)), RESAMPLE_BILINEAR)
        return small.resize((w, h), RESAMPLE_BILINEAR)
    if variant == "contrast":
        return ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(1.08)).enhance(1.18)
    if variant == "graymix":
        gray = img.convert("L").convert("RGB")
        return Image.blend(img, gray, alpha=0.25)
    if variant == "center_crop_resize":
        w, h = img.size
        m = int(min(w, h) * 0.88)
        left = (w - m) // 2
        top = (h - m) // 2
        return img.crop((left, top, left + m, top + m)).resize((w, h), RESAMPLE_BILINEAR)
    if variant == "noise":
        arr = np.asarray(img, dtype=np.int16)
        rng = np.random.default_rng(2026)
        arr = np.clip(arr + rng.normal(0, 3.0, arr.shape), 0, 255).astype(np.uint8)
        return Image.fromarray(arr, mode="RGB")
    raise ValueError(f"Unknown augmentation variant: {variant}")


def _random_augment_from_seed(img: Image.Image, seed: int) -> Image.Image:
    """Sample one augmentation from a continuous distribution, reproducibly per image."""
    rng = np.random.default_rng(seed)
    p = float(rng.random())
    if p < 0.40:
        quality = int(rng.integers(35, 91))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    elif p < 0.65:
        radius = float(rng.uniform(0.4, 1.6))
        return img.filter(ImageFilter.GaussianBlur(radius=radius))
    elif p < 0.85:
        w, h = img.size
        scale = float(rng.uniform(0.5, 0.85))
        small = img.resize((max(16, int(w * scale)), max(16, int(h * scale))), RESAMPLE_BILINEAR)
        return small.resize((w, h), RESAMPLE_BILINEAR)
    else:
        brightness = float(rng.uniform(0.9, 1.15))
        contrast = float(rng.uniform(0.9, 1.25))
        return ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(brightness)).enhance(contrast)


DEFAULT_AUGMENTATION_VARIANTS = ["original", "jpeg70", "blur", "downup", "contrast", "graymix"]


def _apply_variant(img: Image.Image, variant: str, idx: int) -> Image.Image:
    """Apply a named or random augmentation variant."""
    if variant == "random":
        return _random_augment_from_seed(img, seed=2026 + idx)
    return augment_image(img, variant)


def _extract_feature_job(args: Tuple[int, bytes, Sequence[str], Optional[int]]) -> Tuple[int, List[np.ndarray], List[int]]:
    """Extract one image's feature rows for multiprocessing."""
    idx, b, variants, label = args
    img = load_image(b)
    rows = [extract_features_from_image(_apply_variant(img, v, idx), byte_len=len(b)) for v in variants]
    labels = [int(label)] * len(rows) if label is not None else []
    return idx, rows, labels


def extract_feature_matrix_from_bytes(
    image_bytes_list: Sequence[bytes],
    desc: str = "features",
    variants: Optional[Sequence[str]] = None,
    labels: Optional[Sequence[int]] = None,
    workers: int = 1,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Build a feature matrix from image bytes."""
    variants = list(variants or ["original"])
    xs: List[np.ndarray] = []
    ys: List[int] = []

    jobs = [(idx, b, variants, None if labels is None else int(labels[idx])) for idx, b in enumerate(image_bytes_list)]
    if workers and workers > 1:
        with mp.get_context("spawn").Pool(processes=workers) as pool:
            iterator = pool.imap(_extract_feature_job, jobs, chunksize=32)
            for idx, rows, row_labels in tqdm(iterator, total=len(jobs), desc=desc):
                xs.extend(rows)
                ys.extend(row_labels)
        X = np.vstack(xs).astype(np.float32) if xs else np.empty((0, len(feature_names())), dtype=np.float32)
        y = np.asarray(ys, dtype=np.int8) if labels is not None else None
        return X, y

    for idx, b in enumerate(tqdm(image_bytes_list, desc=desc)):
        try:
            img = load_image(b)
            for variant in variants:
                aug = _apply_variant(img, variant, idx)
                xs.append(extract_features_from_image(aug, byte_len=len(b)))
                if labels is not None:
                    ys.append(int(labels[idx]))
        except Exception as e:
            # Corrupt images are skipped. clean.py records these for the train split.
            print(f"warning: skipped corrupt image at index {idx}: {e}")
            continue
    X = np.vstack(xs).astype(np.float32) if xs else np.empty((0, len(feature_names())), dtype=np.float32)
    y = np.asarray(ys, dtype=np.int8) if labels is not None else None
    return X, y
