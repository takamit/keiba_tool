from __future__ import annotations

from typing import Dict, List

import pandas as pd


SEX_MAP = {"牡": 0, "牝": 1, "セ": 2, "騙": 2}


def _flatten_races(payload: Dict, is_result: bool) -> pd.DataFrame:
    rows: List[Dict] = []
    for track in payload.get("tracks", []):
        for race in track.get("races", []):
            for horse in race.get("horses", []):
                row = {
                    "date": payload.get("date"),
                    "track": track.get("name"),
                    "race_id": race.get("race_id"),
                    "race_name": race.get("race_name"),
                    "race_class": race.get("race_class"),
                    "course_info": race.get("course_info"),
                    "weather": race.get("weather"),
                    "ground": race.get("ground"),
                    **horse,
                }
                if is_result:
                    rank = horse.get("rank")
                    row["target_top3"] = 1 if isinstance(rank, int) and rank <= 3 else 0
                    row["target_win"] = 1 if rank == 1 else 0
                rows.append(row)
    return pd.DataFrame(rows)


def build_entry_dataframe(payload: Dict) -> pd.DataFrame:
    return _flatten_races(payload, is_result=False)


def build_result_dataframe(payload: Dict) -> pd.DataFrame:
    return _flatten_races(payload, is_result=True)


def prepare_learning_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "sex" in out.columns:
        out["sex_code"] = out["sex"].map(SEX_MAP).fillna(-1)

    cat_columns = ["track", "weather", "ground", "jockey", "race_class"]
    for col in cat_columns:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("未設定")

    numeric_cols = [
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
    for col in numeric_cols:
        if col not in out.columns:
            out[col] = None

    return out
