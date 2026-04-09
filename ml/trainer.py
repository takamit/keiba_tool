import glob
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, VotingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline

from core.dataset import FEATURE_COLUMNS, TARGET_COLUMNS, enrich_dataframe


AUX_FEATURE_COLUMNS = [
    "hist_horse_win_rate",
    "hist_horse_top3_rate",
    "hist_horse_avg_rank",
    "hist_horse_race_count",
    "hist_jockey_win_rate",
    "hist_jockey_top3_rate",
    "hist_jockey_avg_rank",
    "hist_jockey_race_count",
    "hist_track_win_rate",
    "hist_distance_top3_rate",
    "hist_surface_top3_rate",
    "hist_pair_top3_rate",
]


LONGSHOT_TARGET = "target_longshot_top3"


def _load_result_csvs(data_dir: str) -> pd.DataFrame:
    pattern = os.path.join(data_dir, "result_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"result_*.csv が見つかりません: {data_dir}")

    frames: List[pd.DataFrame] = []
    for path in files:
        try:
            frames.append(pd.read_csv(path))
        except Exception:
            continue

    if not frames:
        raise ValueError("学習用CSVの読み込みに失敗しました")

    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        raise ValueError("学習用データが空です")

    return enrich_dataframe(df, is_result=True)


def _build_history_feature_map(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    work = df.copy()
    work["rank"] = pd.to_numeric(work["rank"], errors="coerce")
    work["is_win"] = (work["rank"] == 1).astype(int)
    work["is_top3"] = (work["rank"] <= 3).astype(int)

    horse_stats = (
        work.groupby("horse_name", dropna=False)
        .agg(
            hist_horse_win_rate=("is_win", "mean"),
            hist_horse_top3_rate=("is_top3", "mean"),
            hist_horse_avg_rank=("rank", "mean"),
            hist_horse_race_count=("horse_name", "size"),
        )
        .reset_index()
    )

    jockey_stats = (
        work.groupby("jockey", dropna=False)
        .agg(
            hist_jockey_win_rate=("is_win", "mean"),
            hist_jockey_top3_rate=("is_top3", "mean"),
            hist_jockey_avg_rank=("rank", "mean"),
            hist_jockey_race_count=("jockey", "size"),
        )
        .reset_index()
    )

    track_stats = (
        work.groupby("track", dropna=False)
        .agg(hist_track_win_rate=("is_win", "mean"))
        .reset_index()
    )

    distance_stats = (
        work.groupby("distance", dropna=False)
        .agg(hist_distance_top3_rate=("is_top3", "mean"))
        .reset_index()
    )

    surface_stats = (
        work.groupby("surface_code", dropna=False)
        .agg(hist_surface_top3_rate=("is_top3", "mean"))
        .reset_index()
    )

    pair_stats = (
        work.groupby(["horse_name", "jockey"], dropna=False)
        .agg(hist_pair_top3_rate=("is_top3", "mean"))
        .reset_index()
    )

    return {
        "horse": horse_stats,
        "jockey": jockey_stats,
        "track": track_stats,
        "distance": distance_stats,
        "surface": surface_stats,
        "pair": pair_stats,
    }


def _merge_history_features(df: pd.DataFrame, history_map: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()

    if "horse" in history_map:
        out = out.merge(history_map["horse"], on="horse_name", how="left")
    if "jockey" in history_map:
        out = out.merge(history_map["jockey"], on="jockey", how="left")
    if "track" in history_map:
        out = out.merge(history_map["track"], on="track", how="left")
    if "distance" in history_map:
        out = out.merge(history_map["distance"], on="distance", how="left")
    if "surface" in history_map:
        out = out.merge(history_map["surface"], on="surface_code", how="left")
    if "pair" in history_map:
        out = out.merge(history_map["pair"], on=["horse_name", "jockey"], how="left")

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


def _build_feature_frame(df: pd.DataFrame, history_map: Dict[str, pd.DataFrame], include_aux: bool = True) -> pd.DataFrame:
    work = enrich_dataframe(df.copy(), is_result=True)
    work = _merge_history_features(work, history_map)

    feature_columns = FEATURE_COLUMNS + AUX_FEATURE_COLUMNS if include_aux else FEATURE_COLUMNS
    for col in feature_columns:
        if col not in work.columns:
            work[col] = 0.0

    feature_df = work[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0)
    return feature_df


def _time_split(df: pd.DataFrame, test_ratio: float = 0.25) -> Tuple[pd.DataFrame, pd.DataFrame]:
    work = df.copy()
    work["date_sort"] = pd.to_datetime(work.get("date"), format="%Y%m%d", errors="coerce")
    work = work.sort_values(["date_sort", "race_id", "horse_no"], ascending=[True, True, True]).reset_index(drop=True)

    if len(work) < 20:
        split_idx = max(1, int(len(work) * (1 - test_ratio)))
        return work.iloc[:split_idx].copy(), work.iloc[split_idx:].copy()

    unique_dates = work["date_sort"].dropna().drop_duplicates().sort_values().tolist()
    if len(unique_dates) >= 4:
        split_pos = max(1, int(len(unique_dates) * (1 - test_ratio)))
        split_date = unique_dates[split_pos - 1]
        train_df = work[work["date_sort"] <= split_date].copy()
        test_df = work[work["date_sort"] > split_date].copy()
        if not train_df.empty and not test_df.empty:
            return train_df, test_df

    split_idx = max(1, int(len(work) * (1 - test_ratio)))
    return work.iloc[:split_idx].copy(), work.iloc[split_idx:].copy()


def _oversample_binary(X: pd.DataFrame, y: pd.Series, random_state: int = 42) -> Tuple[pd.DataFrame, pd.Series]:
    y = pd.Series(y).astype(int)
    class_counts = y.value_counts()
    if len(class_counts) < 2:
        return X, y

    major_class = int(class_counts.idxmax())
    minor_class = int(class_counts.idxmin())
    major_count = int(class_counts.max())
    minor_count = int(class_counts.min())

    if minor_count == 0 or minor_count >= major_count:
        return X, y

    rng = np.random.default_rng(random_state)
    minor_idx = y[y == minor_class].index.to_numpy()
    add_count = major_count - minor_count
    sampled_idx = rng.choice(minor_idx, size=add_count, replace=True)

    X_balanced = pd.concat([X, X.loc[sampled_idx]], axis=0).reset_index(drop=True)
    y_balanced = pd.concat([y, y.loc[sampled_idx]], axis=0).reset_index(drop=True)
    return X_balanced, y_balanced


def _build_model_for_target(target_col: str) -> Pipeline:
    rf = RandomForestClassifier(
        n_estimators=500 if target_col != LONGSHOT_TARGET else 650,
        max_depth=14 if target_col != LONGSHOT_TARGET else 16,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    et = ExtraTreesClassifier(
        n_estimators=400 if target_col != LONGSHOT_TARGET else 550,
        max_depth=None if target_col == LONGSHOT_TARGET else 18,
        min_samples_leaf=1,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    clf = VotingClassifier(
        estimators=[("rf", rf), ("et", et)],
        voting="soft",
        flatten_transform=True,
    )
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", clf),
    ])


def _calculate_auc(y_true: pd.Series, proba: np.ndarray) -> float:
    try:
        if pd.Series(y_true).nunique() >= 2:
            return float(roc_auc_score(y_true, proba))
    except Exception:
        pass
    return 0.0


def _metrics_from_threshold(y_true: pd.Series, proba: np.ndarray, threshold: float) -> Dict[str, float]:
    pred = (proba >= threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "auc": _calculate_auc(y_true, proba),
    }


def _evaluate_thresholds(y_true: pd.Series, proba: np.ndarray, target_col: str) -> Tuple[float, Dict[str, float]]:
    best_threshold = 0.50
    best_score = -1.0
    best_metrics: Dict[str, float] = {
        "accuracy": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "auc": 0.0,
    }

    auc = _calculate_auc(y_true, proba)

    for threshold in np.linspace(0.10, 0.90, 33):
        pred = (proba >= threshold).astype(int)
        metrics = {
            "accuracy": float(accuracy_score(y_true, pred)),
            "precision": float(precision_score(y_true, pred, zero_division=0)),
            "recall": float(recall_score(y_true, pred, zero_division=0)),
            "f1": float(f1_score(y_true, pred, zero_division=0)),
            "auc": auc,
        }

        score = metrics["f1"]
        if target_col == LONGSHOT_TARGET:
            score = metrics["f1"] * 0.70 + metrics["recall"] * 0.30

        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
            best_metrics = metrics

    return best_threshold, best_metrics


def _extract_feature_importances(model: Pipeline, feature_columns: List[str]) -> Dict[str, float]:
    importances = np.zeros(len(feature_columns), dtype=float)

    try:
        clf = model.named_steps.get("clf")
    except Exception:
        clf = None

    estimators = []
    if clf is not None and hasattr(clf, "estimators_"):
        estimators = list(clf.estimators_)
    elif clf is not None and hasattr(clf, "estimators"):
        estimators = [est for _, est in clf.estimators]

    valid_count = 0
    for est in estimators:
        if hasattr(est, "feature_importances_"):
            arr = np.asarray(est.feature_importances_, dtype=float)
            if len(arr) == len(feature_columns):
                importances += arr
                valid_count += 1

    if valid_count > 0:
        importances = importances / valid_count

    total = float(importances.sum())
    if total > 0:
        importances = importances / total

    return {col: float(val) for col, val in zip(feature_columns, importances)}


def _feature_impact_summary(feature_importance_map: Dict[str, float]) -> Dict[str, object]:
    base_total = float(sum(feature_importance_map.get(col, 0.0) for col in FEATURE_COLUMNS))
    aux_total = float(sum(feature_importance_map.get(col, 0.0) for col in AUX_FEATURE_COLUMNS))

    aux_sorted = sorted(
        ((col, float(feature_importance_map.get(col, 0.0))) for col in AUX_FEATURE_COLUMNS),
        key=lambda x: x[1],
        reverse=True,
    )
    base_sorted = sorted(
        ((col, float(feature_importance_map.get(col, 0.0))) for col in FEATURE_COLUMNS),
        key=lambda x: x[1],
        reverse=True,
    )

    return {
        "base_feature_total_importance": base_total,
        "aux_feature_total_importance": aux_total,
        "aux_feature_ratio": float(aux_total / (base_total + aux_total)) if (base_total + aux_total) > 0 else 0.0,
        "top_aux_features": [
            {"feature": col, "importance": imp}
            for col, imp in aux_sorted[:5]
        ],
        "top_base_features": [
            {"feature": col, "importance": imp}
            for col, imp in base_sorted[:5]
        ],
    }


def _estimate_aux_feature_effect(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_col: str,
    history_map: Dict[str, pd.DataFrame],
    full_metrics: Dict[str, float],
) -> Dict[str, object]:
    X_train_base = _build_feature_frame(train_df, history_map, include_aux=False)
    X_test_base = _build_feature_frame(test_df, history_map, include_aux=False)
    y_train = train_df[target_col].reset_index(drop=True)
    y_test = test_df[target_col].reset_index(drop=True)

    X_train_base_balanced, y_train_balanced = _oversample_binary(X_train_base, y_train)

    base_model = _build_model_for_target(target_col)
    base_model.fit(X_train_base_balanced, y_train_balanced)
    base_proba = base_model.predict_proba(X_test_base)[:, 1]
    base_threshold, base_metrics = _evaluate_thresholds(y_test, base_proba, target_col)

    deltas = {
        key: float(full_metrics.get(key, 0.0) - base_metrics.get(key, 0.0))
        for key in ["accuracy", "precision", "recall", "f1", "auc"]
    }

    return {
        "base_only_metrics": base_metrics,
        "base_only_threshold": float(base_threshold),
        "full_minus_base": deltas,
        "is_aux_helpful_f1": bool(deltas.get("f1", 0.0) > 0),
        "is_aux_helpful_auc": bool(deltas.get("auc", 0.0) > 0),
    }


def train_one_target(df: pd.DataFrame, target_col: str, model_dir: str = "models") -> Dict:
    if target_col not in TARGET_COLUMNS:
        raise ValueError(f"未知のターゲットです: {target_col}")

    work = enrich_dataframe(df.copy(), is_result=True)
    if target_col not in work.columns:
        raise ValueError(f"ターゲット列がありません: {target_col}")

    work = work.dropna(subset=[target_col]).copy()
    work[target_col] = pd.to_numeric(work[target_col], errors="coerce")
    work = work[work[target_col].notna()].copy()
    work[target_col] = work[target_col].astype(int)

    if len(work) < 50:
        raise ValueError(f"{target_col}: 学習件数が少なすぎます")
    if work[target_col].nunique() < 2:
        raise ValueError(f"{target_col}: 目的変数が1種類しかありません")

    train_df, test_df = _time_split(work)
    if train_df.empty or test_df.empty:
        raise ValueError(f"{target_col}: 学習/検証データの分割に失敗しました")

    history_map = _build_history_feature_map(train_df)
    X_train = _build_feature_frame(train_df, history_map, include_aux=True)
    y_train = train_df[target_col].reset_index(drop=True)
    X_test = _build_feature_frame(test_df, history_map, include_aux=True)
    y_test = test_df[target_col].reset_index(drop=True)

    X_train_balanced, y_train_balanced = _oversample_binary(X_train, y_train)

    model = _build_model_for_target(target_col)
    model.fit(X_train_balanced, y_train_balanced)

    proba = model.predict_proba(X_test)[:, 1]
    threshold, metrics = _evaluate_thresholds(y_test, proba, target_col)
    pred = (proba >= threshold).astype(int)

    feature_columns = list(FEATURE_COLUMNS + AUX_FEATURE_COLUMNS)
    feature_importance_map = _extract_feature_importances(model, feature_columns)
    feature_impact = _feature_impact_summary(feature_importance_map)
    aux_effect = _estimate_aux_feature_effect(train_df, test_df, target_col, history_map, metrics)

    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, f"{target_col}.joblib")

    payload = {
        "target_col": target_col,
        "feature_columns": feature_columns,
        "base_feature_columns": list(FEATURE_COLUMNS),
        "aux_feature_columns": list(AUX_FEATURE_COLUMNS),
        "threshold": float(threshold),
        "metrics": metrics,
        "feature_importance_map": feature_importance_map,
        "feature_impact": feature_impact,
        "aux_effect": aux_effect,
        "history_map": history_map,
        "model": model,
    }
    joblib.dump(payload, model_path)

    return {
        "target_col": target_col,
        "model_path": model_path,
        "rows": int(len(work)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "positive_count": int(work[target_col].sum()),
        "negative_count": int((1 - work[target_col]).sum()),
        "positive_rate": float(work[target_col].mean()),
        "accuracy": float(metrics["accuracy"]),
        "precision": float(metrics["precision"]),
        "recall": float(metrics["recall"]),
        "f1": float(metrics["f1"]),
        "auc": float(metrics["auc"]),
        "threshold": float(threshold),
        "predicted_positive_count": int(pred.sum()),
        "feature_count": int(len(feature_columns)),
        "feature_impact": feature_impact,
        "aux_effect": aux_effect,
        "error": None,
    }


def train_all_models(data_dir: str = "data", model_dir: str = "models") -> Dict:
    df = _load_result_csvs(data_dir)

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model_dir": os.path.abspath(model_dir),
        "data_dir": os.path.abspath(data_dir),
        "target_count": len(TARGET_COLUMNS),
        "success_count": 0,
        "error_count": 0,
        "summaries": [],
    }

    for target_col in TARGET_COLUMNS:
        try:
            result = train_one_target(df, target_col=target_col, model_dir=model_dir)
            summary["summaries"].append(result)
            summary["success_count"] += 1
        except Exception as exc:
            summary["summaries"].append({
                "target_col": target_col,
                "error": str(exc),
            })
            summary["error_count"] += 1

    os.makedirs(model_dir, exist_ok=True)
    summary_path = os.path.join(model_dir, "training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary
