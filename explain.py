from __future__ import annotations

from pathlib import Path
from typing import List

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from src.data import load_image, parquet_files, read_split
from src.features import extract_features_from_image, feature_names
from src.models import ai_scores
from src.calibration import scores_to_labels
from src.utils import artifacts_dir, binary_labels, common_arg_parser, data_dir, ensure_dir, print_header, save_json, set_reproducible


def occlusion_map(model, image_bytes: bytes, grid: int = 8, patch_value: int = 128) -> tuple[np.ndarray, float]:
    img = load_image(image_bytes)
    base = extract_features_from_image(img, byte_len=len(image_bytes))[None, :]
    base_score = float(ai_scores(model, base)[0])
    w, h = img.size
    heat = np.zeros((grid, grid), dtype=np.float32)
    for gy in range(grid):
        for gx in range(grid):
            patched = img.copy()
            x0 = int(gx * w / grid)
            x1 = int((gx + 1) * w / grid)
            y0 = int(gy * h / grid)
            y1 = int((gy + 1) * h / grid)
            patch = Image.new("RGB", (x1 - x0, y1 - y0), color=(patch_value, patch_value, patch_value))
            patched.paste(patch, (x0, y0))
            x = extract_features_from_image(patched, byte_len=len(image_bytes))[None, :]
            patched_score = float(ai_scores(model, x)[0])
            heat[gy, gx] = base_score - patched_score
    return heat, base_score


def choose_examples(df: pd.DataFrame, scores: np.ndarray, threshold: float, max_examples: int) -> List[int]:
    y = binary_labels(df["source_class"].values)
    pred = scores_to_labels(scores, threshold)
    categories = [
        np.where((y == 1) & (pred == 1))[0],  # true positive
        np.where((y == 0) & (pred == 1))[0],  # false positive
        np.where((y == 1) & (pred == 0))[0],  # false negative
        np.where((y == 0) & (pred == 0))[0],  # true negative
    ]
    chosen: List[int] = []
    for inds in categories:
        if len(inds):
            order = inds[np.argsort(np.abs(scores[inds] - threshold))[::-1]]
            chosen.extend(order[: max(1, max_examples // 4)].tolist())
    if len(chosen) < max_examples:
        remaining = [i for i in np.argsort(np.abs(scores - threshold))[::-1].tolist() if i not in chosen]
        chosen.extend(remaining[: max_examples - len(chosen)])
    return chosen[:max_examples]


def save_shap_analysis(
    model, X: np.ndarray, scores: np.ndarray, y: np.ndarray,
    threshold: float, out_dir: Path
) -> None:
    """SHAP TreeExplainer: beeswarm (global) + waterfall plots for key FP and FN cases."""
    try:
        import shap
        clf = model.named_steps["clf"]
        imp = model.named_steps["impute"]
        X_imp = imp.transform(X).astype(np.float32)
        names = feature_names()
        if len(names) != X_imp.shape[1]:
            names = [f"f{i}" for i in range(X_imp.shape[1])]

        explainer = shap.TreeExplainer(clf)
        shap_values = explainer.shap_values(X_imp)
        # LightGBM binary: shap_values may be list [class0, class1] or single array
        if isinstance(shap_values, list):
            sv = shap_values[1]
        else:
            sv = shap_values

        # --- Global beeswarm ---
        fig, ax = plt.subplots(figsize=(9, 8))
        shap.summary_plot(sv, X_imp, feature_names=names, show=False, max_display=20, plot_size=None)
        plt.title("SHAP summary (beeswarm) — top 20 features", fontsize=11)
        plt.tight_layout()
        plt.savefig(out_dir / "shap_beeswarm.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"saved SHAP beeswarm → {out_dir / 'shap_beeswarm.png'}")

        # --- Waterfall plots for most confident FP and FN ---
        pred = (scores >= threshold).astype(int)
        fp_idx = np.where((y == 0) & (pred == 1))[0]
        fn_idx = np.where((y == 1) & (pred == 0))[0]

        base_value = explainer.expected_value
        if isinstance(base_value, (list, np.ndarray)):
            base_value = float(base_value[1])

        for label, idxs in [("FP", fp_idx), ("FN", fn_idx)]:
            if len(idxs) == 0:
                continue
            # pick highest-confidence wrong prediction
            i = idxs[np.argmax(np.abs(scores[idxs] - threshold))]
            expl = shap.Explanation(
                values=sv[i],
                base_values=base_value,
                data=X_imp[i],
                feature_names=names,
            )
            plt.figure(figsize=(9, 6))
            shap.waterfall_plot(expl, max_display=15, show=False)
            plt.title(f"SHAP waterfall — {label} example (score={scores[i]:.3f})", fontsize=10)
            plt.tight_layout()
            out_path = out_dir / f"shap_waterfall_{label.lower()}.png"
            plt.savefig(out_path, dpi=150, bbox_inches="tight")
            plt.close()
            print(f"saved SHAP waterfall {label} → {out_path.name}")

    except Exception as e:
        print(f"warning: SHAP analysis failed: {e}")


def save_feature_importance(model, out_dir: Path) -> None:
    """Save LightGBM feature importance bar chart (top 30 features by gain)."""
    try:
        clf = model.named_steps["clf"]
        importances = clf.booster_.feature_importance(importance_type="gain")
        names = feature_names()
        if len(names) != len(importances):
            names = [f"f{i}" for i in range(len(importances))]

        idx = np.argsort(importances)[::-1][:30]
        top_names = [names[i] for i in idx]
        top_vals = importances[idx]
        top_vals = top_vals / (top_vals.sum() + 1e-8)

        fig, ax = plt.subplots(figsize=(8, 7))
        ax.barh(range(len(top_names)), top_vals[::-1], color="#3a7ebf")
        ax.set_yticks(range(len(top_names)))
        ax.set_yticklabels(top_names[::-1], fontsize=8)
        ax.set_xlabel("Relative importance (gain, normalised)")
        ax.set_title("Top-30 feature importances (LightGBM gain)")
        plt.tight_layout()
        plt.savefig(out_dir / "feature_importance.png", dpi=160)
        plt.close()

        pd.DataFrame({"feature": names, "importance_gain": importances}).sort_values(
            "importance_gain", ascending=False
        ).to_csv(out_dir / "feature_importance.csv", index=False)
        print(f"saved feature importance → {out_dir / 'feature_importance.png'}")
    except Exception as e:
        print(f"warning: could not extract feature importance: {e}")


def save_category_feature_profiles(
    X: np.ndarray, scores: np.ndarray, y: np.ndarray, threshold: float, out_dir: Path
) -> None:
    """Mean feature value per prediction category for the top-10 most important features."""
    try:
        pred = (scores >= threshold).astype(int)
        names = feature_names()
        if len(names) != X.shape[1]:
            names = [f"f{i}" for i in range(X.shape[1])]

        masks = {
            "TP (AI, correct)": (y == 1) & (pred == 1),
            "FP (real, wrong)": (y == 0) & (pred == 1),
            "FN (AI, wrong)": (y == 1) & (pred == 0),
            "TN (real, correct)": (y == 0) & (pred == 0),
        }

        # Use variance across category means to pick discriminative features
        means = {k: X[m].mean(axis=0) for k, m in masks.items() if m.sum() > 0}
        if len(means) < 2:
            return
        mean_matrix = np.vstack(list(means.values()))
        var_across = mean_matrix.var(axis=0)
        top_idx = np.argsort(var_across)[::-1][:12]
        top_names = [names[i] for i in top_idx]

        fig, axes = plt.subplots(3, 4, figsize=(14, 9))
        axes = axes.flatten()
        colors = {"TP (AI, correct)": "#2196F3", "FP (real, wrong)": "#F44336",
                  "FN (AI, wrong)": "#FF9800", "TN (real, correct)": "#4CAF50"}
        for ax, feat_idx, feat_name in zip(axes, top_idx, top_names):
            for label, mask in masks.items():
                if mask.sum() > 0:
                    vals = X[mask, feat_idx]
                    ax.hist(vals, bins=20, alpha=0.5, label=label, color=colors[label], density=True)
            ax.set_title(feat_name, fontsize=7)
            ax.set_xlabel("")
            ax.tick_params(labelsize=6)
        handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.5) for c in colors.values()]
        fig.legend(handles, list(colors.keys()), loc="lower center", ncol=4, fontsize=8)
        fig.suptitle("Feature distributions per prediction category (top-12 discriminative features)", fontsize=10)
        plt.tight_layout(rect=[0, 0.06, 1, 1])
        plt.savefig(out_dir / "feature_profiles_by_category.png", dpi=140)
        plt.close()
        print(f"saved category profiles → {out_dir / 'feature_profiles_by_category.png'}")
    except Exception as e:
        print(f"warning: could not save category feature profiles: {e}")


def main() -> None:
    parser = common_arg_parser("Occlusion sensitivity + feature importance explainability")
    parser.add_argument("--model_task", choices=["task02", "task03"], default="task03")
    parser.add_argument("--split", default="validation_augmented")
    parser.add_argument("--max_examples", type=int, default=8)
    parser.add_argument("--grid", type=int, default=8)
    args = parser.parse_args()
    set_reproducible(args.seed)

    root = data_dir()
    if not parquet_files(root, args.split):
        print(f"warning: split {args.split} missing; using validation")
        args.split = "validation"
    if not parquet_files(root, args.split):
        raise FileNotFoundError("No validation split found for explainability.")

    model_path = artifacts_dir() / args.model_task / "model.joblib"
    if not model_path.exists() and args.model_task == "task03":
        model_path = artifacts_dir() / "task02" / "model.joblib"
    if not model_path.exists():
        raise FileNotFoundError("No trained model found. Run train.py or train_augmented.py first.")
    bundle = joblib.load(model_path)

    out_dir = ensure_dir(artifacts_dir() / "explain")
    print_header(f"Explainability on {args.split} using {model_path}")
    df = read_split(root, args.split)

    X_list = []
    valid_rows = []
    for i, b in enumerate(df["image"].values):
        try:
            X_list.append(extract_features_from_image(load_image(b), byte_len=len(b)))
            valid_rows.append(i)
        except Exception:
            continue
    X_arr = np.vstack(X_list)
    scores = ai_scores(bundle["model"], X_arr)
    threshold = float(bundle["threshold"])
    y_arr = binary_labels(df.iloc[valid_rows]["source_class"].values)

    # --- Global: SHAP values (TreeExplainer, exact for LightGBM) ---
    print_header("SHAP analysis")
    save_shap_analysis(bundle["model"], X_arr, scores, y_arr, threshold, out_dir)

    # --- Global: feature importance ---
    print_header("Feature importance")
    save_feature_importance(bundle["model"], out_dir)

    # --- Global: per-category feature distributions ---
    print_header("Feature profiles by prediction category")
    save_category_feature_profiles(X_arr, scores, y_arr, threshold, out_dir)

    # --- Local: occlusion heatmaps ---
    print_header("Occlusion heatmaps")
    chosen_local = choose_examples(
        df.iloc[valid_rows].reset_index(drop=True), scores, threshold, args.max_examples
    )

    rows = []
    for rank, local_idx in enumerate(chosen_local):
        original_idx = valid_rows[local_idx]
        image_bytes = df.iloc[original_idx]["image"]
        source_class = int(df.iloc[original_idx]["source_class"])
        label = int(source_class > 0)
        score = float(scores[local_idx])
        pred = int(score >= threshold)
        heat, base_score = occlusion_map(bundle["model"], image_bytes, grid=args.grid)

        img = load_image(image_bytes)
        plt.figure(figsize=(5.5, 5))
        plt.imshow(img)
        plt.imshow(heat, cmap="coolwarm", alpha=0.45, extent=(0, img.width, img.height, 0))
        plt.axis("off")
        category = {(1, 1): "TP", (0, 1): "FP", (1, 0): "FN", (0, 0): "TN"}[(label, pred)]
        plt.title(f"{category} | y={label}, pred={pred}, score={score:.3f}")
        out_path = out_dir / f"occlusion_{rank:02d}_{category}_idx{original_idx}.png"
        plt.tight_layout()
        plt.savefig(out_path, dpi=160)
        plt.close()
        print(f"  {category} idx={original_idx} score={score:.3f} → {out_path.name}")

        rows.append({
            "rank": rank,
            "category": category,
            "split": args.split,
            "idx": int(original_idx),
            "source_class": source_class,
            "label": label,
            "predicted_label": pred,
            "score": score,
            "threshold": threshold,
            "heatmap_path": str(out_path),
            "mean_occlusion_delta": float(heat.mean()),
            "max_occlusion_delta": float(heat.max()),
            "min_occlusion_delta": float(heat.min()),
        })

    pd.DataFrame(rows).to_csv(out_dir / "occlusion_summary.csv", index=False)
    save_json({
        "method": "occlusion sensitivity + LightGBM feature importance",
        "interpretation": "occlusion: positive=patch reduces AI score (region supports AI decision); negative=patch raises AI score. feature_importance: gain-based, normalised.",
        "model_task": bundle.get("task", args.model_task),
        "split": args.split,
        "n_examples": len(rows),
    }, out_dir / "explainability_notes.json")
    print(f"\nwrote all explainability outputs to {out_dir}")


if __name__ == "__main__":
    main()
