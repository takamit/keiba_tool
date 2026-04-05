from __future__ import annotations

import joblib
import pandas as pd

from core.dataset import prepare_learning_dataframe
from ml.trainer import FEATURE_COLUMNS


class KeibaPredictor:
    def predict(self, model_path: str, entry_df: pd.DataFrame) -> pd.DataFrame:
        if entry_df.empty:
            raise ValueError("予測対象データが空です")

        model = joblib.load(model_path)
        work = prepare_learning_dataframe(entry_df)
        features = work[FEATURE_COLUMNS]

        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(features)
            positive_scores = probs[:, 1]
        else:
            positive_scores = model.predict(features)

        result = entry_df.copy()
        result["pred_score"] = positive_scores
        result["pred_rank_in_race"] = result.groupby("race_id")["pred_score"].rank(ascending=False, method="min")
        return result.sort_values(["race_id", "pred_rank_in_race", "number"])
