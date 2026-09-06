# AMLS SoSe 2026 - AI Image Detection

**Team members:** Hana Halitim, Ali Yassine
**Submission date:** July 2026

## 1. Dataset Exploration and Cleaning (Task 1.1)

The training split has 29,688 images with a 1:5 class imbalance — 4,948 real images (MS COCO) and 24,740 AI-generated across five generators. The first thing we noticed when looking at the metadata is that image dimensions alone almost perfectly separate the classes:

| Feature | Sym. AUC | Real mean | AI mean | Note |
|---|---|---|---|---|
| `width` | 0.997 | 579.5 px | 310.1 px | AI images capped at ~320 px |
| `height` | 0.985 | 483.3 px | 310.1 px | Same pattern |
| `byte_len` | 0.839 | 51,023 B | 26,687 B | Real files roughly twice as large |
| `aspect` | 0.750 | 1.26 | 1.00 | All AI images are square |

Width alone gives a symmetric AUC of 0.997 — basically a solved problem if you are allowed to use it. We are not: this shortcut is specific to the dataset construction and would break immediately on any resized holdout. We therefore resize all images to 128×128 px (bilinear) as the first substantive step, which removes both the size and aspect-ratio signal entirely.

The rest of the cleaning pipeline is straightforward: images are decoded with Pillow and confirmed to be RGB JPEG (no format conversion needed). SHA-256 deduplication removed 312 same-label duplicates, leaving 29,376 clean images. We chose 128×128 as the target resolution after some experimentation — 64×64 visibly degraded the noise-residual features we were planning to extract, while 256×256 pushed the feature extraction time beyond the CPU budget. Cleaned images are written to `artifacts/` because the data directory is treated as read-only.

**Figure 1** — Image-size distribution before and after cleaning (`image_sizes_train.png`)

## 2. Modeling and Tuning (Task 1.2)

### 2.1 Feature engineering

Rather than feeding raw pixels to a shallow classifier, we built a 101-dimensional hand-crafted feature vector. The motivation was twofold: training is fast enough to iterate on CPU, and interpretable features make the explainability analysis in Section 4 meaningful.

| Group | # | Features |
|---|---|---|
| Color statistics | 24 | Mean, std, min, max, p10, p50, p90, entropy per R/G/B channel |
| Grayscale statistics | 5 | Mean, std, p10, p50, p90 of luminance |
| HSV statistics | 10 | Mean, std, p10, p50, p90 of H and S channels |
| Gradient / edge | 8 | Sobel magnitude (mean, std, p90, p99, edge fraction ×2), Laplacian variance and mean-abs |
| Multi-scale gradient | 3 | Sobel mean, std, p90 at 32×32 scale |
| FFT frequency | 3 | Power fraction in low / mid / high radial bands |
| Noise residual | 11 | Box-blur residual statistics + cross-channel correlations (RG, GB, RB) |
| Radial spectrum | 3 | Log-log fit of azimuthally averaged FFT: slope, intercept, MSE |
| GLCM texture | 8 | Contrast, homogeneity, energy, correlation — mean + std |
| LBP histogram | 10 | Uniform LBP (P=8, R=1) |
| Tiny 4×4 grayscale | 16 | Spatially downsampled luminance |

The noise residual group deserves a note. The idea is that real photographs carry sensor-noise patterns from camera demosaicing, while AI-generated images are typically denoised by their synthesis pipeline. We include the cross-channel residual correlations (RG, GB, RB) to try to capture this. As Section 4 shows, these turn out to be the most informative features by gain, though the direction the model learned is empirical and does not straightforwardly confirm the demosaicing hypothesis.

We also evaluated 48 tiny RGB pixels at 4×4 resolution per channel but dropped them: they encode scene content (sky, grass, faces) rather than generation artifacts, making them a dataset-specific shortcut analogous to the image-size issue. The 16 grayscale tiny pixels we kept are far less scene-specific.

HSV statistics (10 dims) were added for Task 3. Hue and saturation distributions are more stable under JPEG compression and blurring than raw RGB, so they help the model generalise to the degraded `validation_augmented` split.

### 2.2 Model selection

The pipeline is `SimpleImputer(median)` → `RobustScaler` → classifier. We trained five classical candidates with a sample weight of 1.3 on AI images to compensate for the class imbalance: Logistic Regression, Extra Trees (500 estimators), HistGradientBoosting (400 iterations), LightGBM (1,500 estimators, 63 leaves, lr = 0.03), and a ClassicalEnsemble that averages their scores equally.

For the required neural comparison, we implemented a SmallCNN trained from scratch (3 conv blocks, AdaptiveAvgPool, 2 FC layers). On CPU the 1800 s time budget only allows one full epoch, which gives recall ≈ 0.52 and FPR ≈ 0.24. This is expected — a convolutional network needs many epochs to converge, and the CPU constraint makes it unviable. It is not part of the final pipeline.

Threshold calibration finds the lowest threshold at which FPR ≤ 0.18 on the calibration split, leaving a 0.02 buffer below the hard 0.20 constraint to absorb the distribution shift between calibration and validation.

### 2.3 Results

| Model | Val recall_ai | Val FPR_real | Val acc. | FPR ≤ 0.20 |
|---|---|---|---|---|
| Logistic Regression | 0.651 | 0.186 | 0.678 | ✔ |
| Extra Trees | 0.810 | 0.218 | 0.805 | ✘ |
| HistGradientBoosting | 0.825 | 0.213 | 0.819 | ✘ |
| **LightGBM (selected)** | **0.857** | **0.197** | **0.848** | **✔** |
| ClassicalEnsemble | 0.806 | 0.181 | 0.808 | ✔ |

LightGBM is the clear winner: highest recall at 0.857 while staying within the FPR constraint. Extra Trees and HistGradientBoosting both score lower recall (0.810 and 0.825) and also violate FPR ≤ 0.20, so they are worse on both metrics simultaneously. The ClassicalEnsemble satisfies the constraint but gives up 5 points of recall compared to LightGBM. The selected threshold is 0.935.

One concern after selection: the Task 2 model scores recall = 0.571 and FPR = 0.209 on `validation_augmented` using the same threshold. The FPR constraint is marginally violated and recall drops by nearly 29 percentage points. This gap between the clean and degraded splits is what Task 3 is designed to close.

## 3. Data Augmentation and Feature Engineering (Task 1.3)

### 3.1 Approach

The core problem in Task 2 is that the model was trained and calibrated on clean images, and it does not generalise well to blurred, compressed, or downscaled inputs. The fix is to augment the training data so the model sees degraded versions during training, and to recalibrate the threshold on augmented data as well.

Each training image produces several deterministic feature rows: the original image and six degraded variants. The final augmentation set is `original`, `jpeg70`, `jpeg45`, `blur`, `downup`, `contrast`, and `graymix`. These variants simulate common real-world transformations: moderate JPEG compression, stronger JPEG compression, blur, downscaling followed by upscaling, contrast changes, and partial grayscale conversion. This increases the training set size and makes the model less dependent on fragile clean-image patterns.

The Task 3 model is trained as a separate robustness model, but it uses the same engineered-feature pipeline as Task 2. Instead of training only on clean feature rows, it trains on augmented feature rows. For threshold calibration we use `calibration_augmented` only. We keep the official false-positive constraint with a target FPR of 0.20. Calibrating directly on the degraded distribution helps control the false-positive rate on `validation_augmented`.

### 3.2 Results

| Split | Task 2 (no aug.) | Task 3 (+ aug.) |
|---|---|---|
| validation recall_ai | 0.857 | 0.759 |
| validation FPR_real | 0.197 ✔ | 0.112 ✔ |
| validation_augmented recall_ai | 0.571 | **0.601** ✔ |
| validation_augmented FPR_real | 0.209 ✘ | **0.193** ✔ |

The trade-off is clear: recall on clean images falls from 0.857 to 0.759, but robustness on the degraded split improves. On `validation_augmented`, Task 2 reaches only 0.571 recall and also violates the 20% false-positive constraint with FPR = 0.209. The Task 3 model improves augmented recall to 0.601 and reduces the false-positive rate to 0.193, satisfying the required operating point. The FPR on clean validation also improves substantially from 0.197 to 0.112, suggesting the model became more conservative once it was exposed to harder examples during training.

## 4. Explainability (Task 1.4)

### 4.1 Method

All analysis uses the Task 3 LightGBM model on `validation_augmented`. We applied three complementary methods.

Global feature importance is taken directly from LightGBM's gain-based ranking — how much total reduction in loss each feature contributes across all trees. SHAP values (via `shap.TreeExplainer`) give exact per-sample attribution: how much each feature pushed the model's output up or down relative to its base rate for each individual image. Occlusion sensitivity works differently — a grey patch (value 128) replaces each cell of an 8×8 spatial grid in turn, and we measure the change in the model's score (Δ = score_base − score_patched). A positive delta means that region was supporting the prediction; negative means it was acting against it. Because our model scores a feature vector rather than raw pixels, occlusion affects texture-sensitive features (noise residual, GLCM, LBP) indirectly — it is not the same as pixel-level saliency.

### 4.2 Figures

**Figure 2** — Feature importance (LightGBM gain, top 30) (`feature_importance.png`)

**Figure 3** — SHAP beeswarm plot (top 20 features, validation_augmented) (`shap_beeswarm.png`)

**Figure 4** — SHAP waterfall for the most confidently misclassified False Positive (real image scored 0.999) (`shap_waterfall_fp.png`)

**Figure 5** — SHAP waterfall for the most confidently misclassified False Negative (AI image scored 0.006) (`shap_waterfall_fn.png`)

### 4.3 Discussion

The feature importance chart (Figure 2) puts `nr_corr_gb`, the green-blue noise residual correlation, clearly at the top with roughly 22% more gain than the second-ranked `g_max`. The SHAP beeswarm (Figure 3) shows that high values of `nr_corr_gb` push the model toward AI. This is the opposite of the naive camera-noise story — one might expect real images to have higher cross-channel correlations from sensor demosaicing. Whether the feature has been learned in a physically meaningful direction or is picking up on something about the MS COCO image population is genuinely unclear, and we would want to investigate this further before making any claims about it.

The other striking pattern in Figure 2 is the concentration of HSV features in the top 15: `hsv_h_p50`, `hsv_s_p10`, `hsv_h_mean`, `hsv_h_p90`, `hsv_s_std`, and `hsv_s_mean` all appear. These features added for Task 3 are contributing, not just stabilising the threshold.

The waterfall plots reveal two distinct failure modes. The False Negative (Figure 5) is an AI image the model scores at 0.006 — nearly certain it is real. The dominant SHAP contribution is `hsv_h_mean = 0` at −1.93, which essentially overrides everything else including `nr_corr_gb` pushing in the right direction at +1.06. The issue is that hue is undefined in dark or low-saturation pixels, so `hsv_h_mean` collapsing to zero means the image is dark or desaturated, not that it is real. The model has learned a shortcut: zero hue → real image. For this particular AI image, that shortcut fires incorrectly.

The False Positive (Figure 4) is a real image scored at 0.999. Here the dominant contributions come from `rspec_mse = 0.911` (+0.78 SHAP) — a poor fit of the radial spectrum log-log curve, which the model associates with AI — and slightly elevated channel minima (`b_min = 40`, `g_min = 44`, SHAP +0.65 and +0.56). This real image apparently has an unusual spectral profile that resembles the generator signatures the model learned.

Occlusion results are harder to use. For high-confidence true positives the mean delta is around 1×10⁻⁶ — the model is so saturated that no individual 16×16 pixel patch moves it measurably. The False Negative is more informative: every single spatial region produces a negative delta (max delta = −8.6×10⁻⁴), meaning no part of the image is providing evidence for the AI prediction. This is consistent with the SHAP finding — the model's score is being pulled down by a global image statistic (HSV) rather than any localised feature.

More broadly, the model is clearly relying on low-level statistical properties rather than anything semantic. This is somewhat expected given the feature design, but it also means the model is vulnerable to distribution shifts in image content. The MS COCO training set has particular brightness and saturation characteristics, and it is not obvious how well the model would transfer to a different real-image source. The `nr_corr_gb` direction inconsistency, the HSV hue shortcut, and the spectral mismatch failures all point to the same underlying issue: the model has found decision boundaries that work well within this dataset but may not reflect fundamental differences between real and AI-generated images.

## 5. Summary

| Task | Result |
|---|---|
| 1.1 Cleaning | 29,376 images after deduplication; size/aspect shortcut removed by 128×128 resize |
| 1.2 Modeling | LightGBM on 101 hand-crafted features; recall_ai = 0.857, FPR = 0.197 on validation |
| 1.3 Augmentation | Deterministic compression, blur, resize, contrast, and grayscale-mix augmentations; recall_ai = 0.601, FPR = 0.193 on validation_augmented |
| 1.4 Explainability | `nr_corr_gb` dominant but direction unclear; FN failure from HSV hue shortcut; FP failure from atypical radial spectrum profile |
