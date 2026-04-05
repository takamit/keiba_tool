import glob
import os

import joblib
import pandas as pd

from core.dataset import FEATURE_COLUMNS


def _load_model_files(model_dir):
    files = sorted(glob.glob(os.path.join(model_dir, "*.joblib")))
    if not files:
        raise FileNotFoundError(f"モデルファイルがありません: {model_dir}")
    return files


def predict_from_entry(entry_csv_path, model_dir="models", output_path=None):
    if not os.path.exists(entry_csv_path):
        raise FileNotFoundError(f"出走表CSVが見つかりません: {entry_csv_path}")

    df = pd.read_csv(entry_csv_path)
    if df.empty:
        raise ValueError("出走表CSVが空です")

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None

    X = df[FEATURE_COLUMNS].copy()
    result_df = df.copy()

    score_cols = []

    for model_path in _load_model_files(model_dir):
        saved = joblib.load(model_path)
        target_col = saved["target_col"]
        feature_columns = saved["feature_columns"]
        model = saved["model"]

        X_model = X.copy()
        for col in feature_columns:
            if col not in X_model.columns:
                X_model[col] = None
        X_model = X_model[feature_columns]

        if hasattr(model, "predict_proba"):
            score = model.predict_proba(X_model)[:, 1]
        else:
            score = model.predict(X_model)

        score_name = f"score_{target_col}"
        result_df[score_name] = score
        score_cols.append(score_name)

    if not score_cols:
        raise ValueError("予測スコア列が作成されませんでした")

    result_df["score_mean"] = result_df[score_cols].mean(axis=1)

    weight_map = {
        "score_target_win": 0.30,
        "score_target_top2": 0.20,
        "score_target_top3": 0.20,
        "score_target_top5": 0.10,
        "score_target_favorite_win": 0.10,
        "score_target_longshot_top3": 0.10,
    }

    result_df["score_composite"] = 0.0
    for col in score_cols:
        result_df["score_composite"] += result_df[col] * weight_map.get(col, 0.0)

    result_df["pred_rank_in_race"] = (
        result_df.groupby("race_id")["score_composite"]
        .rank(ascending=False, method="min")
    )

    result_df = result_df.sort_values(
        by=["race_id", "pred_rank_in_race", "horse_no"],
        ascending=[True, True, True]
    ).reset_index(drop=True)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        result_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return result_df
