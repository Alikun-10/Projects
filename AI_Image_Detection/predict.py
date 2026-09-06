from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.data import iter_predict_rows
from src.features import extract_feature_matrix_from_bytes
from src.models import ai_scores
from src.calibration import scores_to_labels
from src.utils import artifacts_dir, common_arg_parser, data_dir, ensure_dir, print_header, set_reproducible


def main() -> None:
    """Run the script entry point."""
    parser = common_arg_parser("Task 2 inference")
    args = parser.parse_args()
    set_reproducible(args.seed)

    print_header("Task 2 prediction")
    root = data_dir()
    out_dir = ensure_dir(artifacts_dir() / "task02")
    model_path = out_dir / "model.joblib"
    if not model_path.exists():
        raise FileNotFoundError("Task 2 model not found. Run train.py before predict.py.")
    bundle = joblib.load(model_path)

    row_ids = []
    image_bytes = []
    for row_id, b in iter_predict_rows(root):
        row_ids.append(row_id)
        image_bytes.append(bytes(b))
    if not row_ids:
        raise FileNotFoundError("No predict parquet files found under solution/data/predict/")

    kind = bundle.get("model_kind")
    if kind == "weighted_ensemble":
        from src.cnn_model import load_cnn_model, score_images

        X, _ = extract_feature_matrix_from_bytes(image_bytes, labels=None, desc="predict features")
        idx = np.asarray(bundle["content_feature_indices"], dtype=np.int64)
        cnn_path = Path(bundle["cnn_model_path"])
        if not cnn_path.is_absolute():
            cnn_path = out_dir / cnn_path
        cnn_model, image_size = load_cnn_model(cnn_path)
        weights = bundle["weights"]
        scores = (
            float(weights["rf_content"]) * ai_scores(bundle["rf_content"], X[:, idx])
            + float(weights["mlp_content"]) * ai_scores(bundle["mlp_content"], X[:, idx])
            + float(weights["cnn"]) * score_images(cnn_model, image_bytes, batch_size=128, image_size=image_size)
        )
    elif kind == "cnn":
        from src.cnn_model import load_cnn_model, score_images

        cnn_path = Path(bundle["model_path"])
        if not cnn_path.is_absolute():
            cnn_path = out_dir / cnn_path
        model, image_size = load_cnn_model(cnn_path)
        scores = score_images(model, image_bytes, batch_size=128, image_size=image_size)
    elif kind == "soft_ensemble":
        from src.cnn_model import load_cnn_model, score_images

        cnn_path = Path(bundle["cnn_model_path"])
        if not cnn_path.is_absolute():
            cnn_path = out_dir / cnn_path
        cnn_model, image_size = load_cnn_model(cnn_path)
        batch_size = int(bundle.get("cnn_batch_size", 128))
        cnn_scores = score_images(cnn_model, image_bytes, batch_size=batch_size, image_size=image_size)
        X, _ = extract_feature_matrix_from_bytes(image_bytes, labels=None, desc="predict features")
        classical_scores = ai_scores(bundle["classical_model"], X)
        weights = bundle.get("weights", {"cnn": 0.5, "classical": 0.5})
        scores = float(weights["cnn"]) * cnn_scores + float(weights["classical"]) * classical_scores
    else:
        X, _ = extract_feature_matrix_from_bytes(image_bytes, labels=None, desc="predict features")
        scores = ai_scores(bundle["model"], X)

    pred = scores_to_labels(scores, bundle["threshold"])
    df = pd.DataFrame({"row_id": row_ids, "predicted_label": pred.astype(int)})
    df = df.sort_values("row_id")
    df.to_csv(out_dir / "predictions.csv", index=False)
    print(f"wrote {len(df)} predictions to {out_dir / 'predictions.csv'}")


if __name__ == "__main__":
    main()
