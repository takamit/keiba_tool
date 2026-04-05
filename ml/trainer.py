from __future__ import annotations

import os
from typing import Dict

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from config.settings import MODEL_DIR
from core.dataset import prepare_learning_dataframe


FEATURE_COLUMNS = [
    "track",
    "weather",
    "ground",
    "jockey",
    "race_class",
    "frame",
    "number",
    "age",
    "carried_weight",
    "body_weight",
    "body_weight_diff",
    "odds",
    "popularity",
    "sex_code",
]


class KeibaModelTrainer:
    def train(self, df: pd.DataFrame, target_col: str = "target_top3") -> Dict:
        if target_col not in df.columns:
            raise ValueError(f"学習用ターゲット列がありません: {target_col}")

        work = prepare_learning_dataframe(df)
        work = work.dropna(subset=[target_col]).copy()
        if len(work) < 30:
            raise ValueError("学習データが少なすぎます。最低でも30頭分以上の結果データを集めてください。")

        X = work[FEATURE_COLUMNS]
        y = work[target_col]

        numeric_cols = [c for c in FEATURE_COLUMNS if c not in ["track", "weather", "ground", "jockey", "race_class"]]
        categorical_cols = ["track", "weather", "ground", "jockey", "race_class"]

        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "num",
                    Pipeline([
                        ("imputer", SimpleImputer(strategy="median")),
                    ]),
                    numeric_cols,
                ),
                (
                    "cat",
                    Pipeline([
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]),
                    categorical_cols,
                ),
            ]
        )

        model = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=300,
                        max_depth=10,
                        min_samples_leaf=2,
                        random_state=42,
                        class_weight="balanced",
                    ),
                ),
            ]
        )

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y
        )
        model.fit(X_train, y_train)
        pred = model.predict(X_test)

        accuracy = float(accuracy_score(y_test, pred))
        report = classification_report(y_test, pred, zero_division=0)

        model_path = os.path.join(MODEL_DIR, f"keiba_model_{target_col}.joblib")
        joblib.dump(model, model_path)

        return {
            "model_path": model_path,
            "target": target_col,
            "train_rows": len(X_train),
            "test_rows": len(X_test),
            "accuracy": accuracy,
            "report": report,
        }
