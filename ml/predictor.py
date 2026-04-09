import glob
import json
import os
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

from core.dataset import FEATURE_COLUMNS, enrich_dataframe


DEFAULT_WEIGHT_MAP = {
    "target_win": 3.0,
    "target_top2": 2.0,
    "target_top3": 2.2,
    "target_top5": 1.4,
    "target_favorite_win": 0.8,
    "target_longshot_top3": 2.3,
}


def _load_model_files(model_dir: str) -> List[str]:
    files = sorted(glob.glob(os.path.join(model_dir, "*.joblib")))
    if not files:
        raise FileNotFoundError(f"モデルファイルがありません: {model_dir}")
    return files


def _merge_history_features(df: pd.DataFrame, history_map: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()

    horse = history_map.get("horse")
    jockey = history_map.get("jockey")
    track = history_map.get("track")
    distance = history_map.get("distance")
    surface = history_map.get("surface")
    pair = history_map.get("pair")

    if horse is not None:
        out = out.merge(horse, on="horse_name", how="left")
    if jockey is not None:
        out = out.merge(jockey, on="jockey", how="left")
    if track is not None:
        out = out.merge(track, on="track", how="left")
    if distance is not None:
        out = out.merge(distance, on="distance", how="left")
    if surface is not None:
        out = out.merge(surface, on="surface_code", how="left")
    if pair is not None:
        out = out.merge(pair, on=["horse_name", "jockey"], how="left")

    fill_defaults = {
        "hist_horse_win_rate": 0.0,
        "hist_horse_top3_rate": 0.0,
        "hist_horse_avg_rank": 99.0,
        "hist_horse_race_count": 0.0,
        "hist_jockey_win_rate": 0.0,
        "hist_jockey_top3_rate": 0.0,
        "hist_jockey_avg_rank": 99.0,
        "hist_jockey_race_count": 0.0,
        "hist_track_win_rate": 0.0,
        "hist_distance_top3_rate": 0.0,
        "hist_surface_top3_rate": 0.0,
        "hist_pair_top3_rate": 0.0,
    }
    for col, default in fill_defaults.items():
        if col not in out.columns:
            out[col] = default
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(default)

    return out


def _normalize_by_race(series: pd.Series, race_ids: pd.Series) -> pd.Series:
    work = pd.DataFrame({"race_id": race_ids.astype(str), "value": pd.to_numeric(series, errors="coerce").fillna(0.0)})

    def _norm(group: pd.Series) -> pd.Series:
        min_v = float(group.min())
        max_v = float(group.max())
        if abs(max_v - min_v) < 1e-9:
            return pd.Series(np.full(len(group), 0.5), index=group.index)
        return (group - min_v) / (max_v - min_v)

    return work.groupby("race_id")["value"].transform(_norm)


def _score_quality(metrics: Dict) -> float:
    if not isinstance(metrics, dict):
        return 1.0
    f1 = float(metrics.get("f1", 0.0) or 0.0)
    auc = float(metrics.get("auc", 0.0) or 0.0)
    recall = float(metrics.get("recall", 0.0) or 0.0)
    return max(0.1, f1 * 0.60 + auc * 0.25 + recall * 0.15)


def predict_from_entry(entry_csv_path: str, model_dir: str = "models", output_path=None, strategy: str = "balanced", **kwargs):
    if not os.path.exists(entry_csv_path):
        raise FileNotFoundError(f"出走表CSVが見つかりません: {entry_csv_path}")

    df = pd.read_csv(entry_csv_path)
    if df.empty:
        raise ValueError("出走表CSVが空です")

    df = enrich_dataframe(df, is_result=False)
    result_df = df.copy()

    model_paths = _load_model_files(model_dir)
    all_score_cols: List[str] = []
    weighted_score = np.zeros(len(result_df), dtype=float)
    quality_weight_sum = np.zeros(len(result_df), dtype=float)

    for model_path in model_paths:
        saved = joblib.load(model_path)
        target_col = saved["target_col"]
        feature_columns = list(saved.get("feature_columns", FEATURE_COLUMNS))
        aux_feature_columns = list(saved.get("aux_feature_columns", []))
        model = saved["model"]
        history_map = saved.get("history_map", {})
        threshold = float(saved.get("threshold", 0.5))
        metrics = saved.get("metrics", {})

        merged = _merge_history_features(result_df.copy(), history_map)
        for col in feature_columns:
            if col not in merged.columns:
                merged[col] = 0.0
        X_model = merged[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)

        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X_model)[:, 1]
        else:
            proba = model.predict(X_model)

        proba_col = f"proba_{target_col}"
        pred_col = f"pred_{target_col}"
        result_df[proba_col] = proba

        decision_threshold = threshold
        if target_col == "target_longshot_top3":
            decision_threshold = max(0.10, threshold * 0.85)

        result_df[pred_col] = (proba >= decision_threshold).astype(int)
        all_score_cols.append(proba_col)

        normalized = _normalize_by_race(result_df[proba_col], result_df["race_id"])
        quality_weight = _score_quality(metrics) * DEFAULT_WEIGHT_MAP.get(target_col, 1.0)
        weighted_score += normalized.to_numpy() * quality_weight
        quality_weight_sum += quality_weight

    if not all_score_cols:
        raise ValueError("予測スコア列が作成されませんでした")

    quality_weight_sum = np.where(quality_weight_sum == 0, 1.0, quality_weight_sum)
    result_df["score_mean"] = result_df[all_score_cols].mean(axis=1)
    result_df["score_composite"] = weighted_score / quality_weight_sum
    result_df["score"] = result_df["score_composite"]

    if "proba_target_longshot_top3" in result_df.columns and "popularity" in result_df.columns:
        longshot_boost = np.where(result_df["popularity"] >= 8, result_df["proba_target_longshot_top3"] * 0.12, 0.0)
        result_df["score_composite"] = result_df["score_composite"] + longshot_boost
        result_df["score"] = result_df["score_composite"]

    result_df["pred_rank"] = (
        result_df.groupby("race_id")["score_composite"].rank(ascending=False, method="first").astype(int)
    )
    result_df["pred_rank_in_race"] = result_df["pred_rank"]

    if "popularity" in result_df.columns:
        result_df["popularity_diff"] = pd.to_numeric(result_df["popularity"], errors="coerce") - pd.to_numeric(result_df["pred_rank"], errors="coerce")
    else:
        result_df["popularity_diff"] = 0

    result_df = result_df.sort_values(by=["race_id", "pred_rank", "horse_no"], ascending=[True, True, True]).reset_index(drop=True)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        result_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return result_df

def build_bet_recommendations(result_df: pd.DataFrame, bet_types=None) -> List[Dict]:
    bet_types = bet_types or ["単勝"]
    if result_df is None or result_df.empty:
        return []
    recommendations: List[Dict] = []
    for race_id, race_df in result_df.groupby("race_id"):
        sorted_df = race_df.sort_values(by=["pred_rank", "horse_no"], ascending=[True, True]).reset_index(drop=True)
        top = sorted_df.head(3)
        if top.empty:
            continue
        race_no = ""
        track = ""
        if "race_id" in top.columns:
            race_no = str(race_id)[-2:]
        if "track" in top.columns:
            track = str(top.iloc[0].get("track", ""))
        for bet_type in bet_types:
            if bet_type == "単勝":
                row = top.iloc[0]
                recommendations.append({
                    "race_id": race_id,
                    "track": track,
                    "race_no": race_no,
                    "bet_type": bet_type,
                    "bet_text": f"{int(row.get('horse_no', 0)) if pd.notna(row.get('horse_no', 0)) else row.get('horse_name', '')}",
                    "confidence": float(row.get("score", 0.0)),
                })
            elif bet_type == "複勝":
                row = top.iloc[0]
                recommendations.append({
                    "race_id": race_id,
                    "track": track,
                    "race_no": race_no,
                    "bet_type": bet_type,
                    "bet_text": f"{int(row.get('horse_no', 0)) if pd.notna(row.get('horse_no', 0)) else row.get('horse_name', '')}",
                    "confidence": float(row.get("score", 0.0)),
                })
            elif bet_type in {"ワイド", "馬連"} and len(top) >= 2:
                a = top.iloc[0]
                b = top.iloc[1]
                recommendations.append({
                    "race_id": race_id,
                    "track": track,
                    "race_no": race_no,
                    "bet_type": bet_type,
                    "bet_text": f"{int(a.get('horse_no', 0)) if pd.notna(a.get('horse_no', 0)) else a.get('horse_name', '')}-{int(b.get('horse_no', 0)) if pd.notna(b.get('horse_no', 0)) else b.get('horse_name', '')}",
                    "confidence": float((a.get("score", 0.0) + b.get("score", 0.0)) / 2.0),
                })
            elif bet_type in {"3連複", "三連複"} and len(top) >= 3:
                nums = []
                conf = 0.0
                for _, row in top.head(3).iterrows():
                    nums.append(str(int(row.get("horse_no", 0))) if pd.notna(row.get("horse_no", 0)) else str(row.get("horse_name", "")))
                    conf += float(row.get("score", 0.0))
                recommendations.append({
                    "race_id": race_id,
                    "track": track,
                    "race_no": race_no,
                    "bet_type": bet_type,
                    "bet_text": "-".join(nums),
                    "confidence": conf / 3.0,
                })
    return recommendations
