import glob
import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from core.dataset import TARGET_COLUMNS, prepare_train_xy


def _load_result_csvs(data_dir):
    pattern = os.path.join(data_dir, "result_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        raise FileNotFoundError(f"result_*.csv が見つかりません: {data_dir}")

    frames = [pd.read_csv(path) for path in files]
    df = pd.concat(frames, ignore_index=True)

    if df.empty:
        raise ValueError("学習用データが空です")

    return df


def _build_model():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(
            n_estimators=400,
            max_depth=12,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )),
    ])


def train_one_target(df, target_col, model_dir="models"):
    X, y = prepare_train_xy(df, target_col)

    if len(X) < 50:
        raise ValueError(f"{target_col}: 学習件数が少なすぎます")

    if y.nunique() < 2:
        raise ValueError(f"{target_col}: 目的変数が1種類しかありません")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.25,
        random_state=42,
        stratify=y
    )

    model = _build_model()
    model.fit(X_train, y_train)

    pred = model.predict(X_test)
    acc = float(accuracy_score(y_test, pred))
    f1 = float(f1_score(y_test, pred, zero_division=0))

    auc = None
    if hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba(X_test)[:, 1]
            auc = float(roc_auc_score(y_test, proba))
        except Exception:
            auc = None

    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, f"{target_col}.joblib")

    joblib.dump({
        "target_col": target_col,
        "feature_columns": list(X.columns),
        "model": model,
    }, model_path)

    return {
        "target_col": target_col,
        "model_path": model_path,
        "rows": int(len(X)),
        "positive_rate": float(y.mean()),
        "accuracy": acc,
        "f1": f1,
        "auc": auc,
    }


def train_all_models(data_dir="data", model_dir="models"):
    df = _load_result_csvs(data_dir)
    summaries = []

    for target_col in TARGET_COLUMNS:
        try:
            summaries.append(train_one_target(df, target_col=target_col, model_dir=model_dir))
        except Exception as e:
            summaries.append({
                "target_col": target_col,
                "error": str(e),
            })

    return summaries
