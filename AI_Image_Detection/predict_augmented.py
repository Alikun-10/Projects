from __future__ import annotations

import joblib
import pandas as pd

from src.data import iter_predict_rows
from src.features import extract_feature_matrix_from_bytes
from src.models import ai_scores
from src.calibration import scores_to_labels
from src.utils import artifacts_dir, common_arg_parser, data_dir, ensure_dir, print_header, set_reproducible


def main() -> None:
    parser = common_arg_parser("Task 3 inference")
    args = parser.parse_args()
    set_reproducible(args.seed)

    print_header("Task 3 prediction")
    root = data_dir()
    out_dir = ensure_dir(artifacts_dir() / "task03")
    model_path = out_dir / "model.joblib"
    if not model_path.exists():
        raise FileNotFoundError("Task 3 model not found. Run train_augmented.py before predict_augmented.py.")
    bundle = joblib.load(model_path)

    row_ids = []
    image_bytes = []
    for row_id, b in iter_predict_rows(root):
        row_ids.append(row_id)
        image_bytes.append(b)
    if not row_ids:
        raise FileNotFoundError("No predict parquet files found under solution/data/predict/")

    X, _ = extract_feature_matrix_from_bytes(image_bytes, labels=None, desc="predict augmented features")
    scores = ai_scores(bundle["model"], X)
    pred = scores_to_labels(scores, bundle["threshold"])
    df = pd.DataFrame({"row_id": row_ids, "predicted_label": pred.astype(int)}).sort_values("row_id")
    df.to_csv(out_dir / "predictions.csv", index=False)
    print(f"wrote {len(df)} predictions to {out_dir / 'predictions.csv'}")


if __name__ == "__main__":
    main()
