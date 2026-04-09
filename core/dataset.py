import math
from typing import Dict, Iterable, List, Tuple

import pandas as pd


SEX_MAP = {"牡": 0, "牝": 1, "セ": 2, "騙": 2}

TRACK_MAP = {
    "札幌": 1,
    "函館": 2,
    "福島": 3,
    "新潟": 4,
    "東京": 5,
    "中山": 6,
    "中京": 7,
    "京都": 8,
    "阪神": 9,
    "小倉": 10,
}

WEATHER_MAP = {"晴": 1, "曇": 2, "雨": 3, "小雨": 4, "雪": 5}
GROUND_MAP = {"良": 1, "稍重": 2, "重": 3, "不良": 4}
SURFACE_MAP = {"芝": 0, "ダ": 1, "障": 2}
DIRECTION_MAP = {"右": 0, "左": 1, "直線": 2}

FEATURE_COLUMNS = [
    "track_code",
    "weather_code",
    "ground_code",
    "surface_code",
    "direction_code",
    "race_no",
    "month",
    "day",
    "weekday",
    "distance",
    "frame_no",
    "horse_no",
    "age",
    "carried_weight",
    "body_weight",
    "body_weight_diff",
    "odds",
    "odds_log",
    "popularity",
    "popularity_rev",
    "sex_code",
    "field_size",
    "frame_ratio",
    "horse_no_ratio",
    "is_favorite",
    "is_outer_half",
    "is_grade",
    "is_newcomer",
    "is_maiden",
]

TARGET_COLUMNS = [
    "target_win",
    "target_top2",
    "target_top3",
    "target_top5",
    "target_favorite_win",
    "target_longshot_top3",
]

AUX_FEATURE_GROUPS = {
    "horse_jockey_specialized": [
        "horse_win_rate",
        "horse_top3_rate",
        "horse_avg_rank",
        "horse_start_count",
        "jockey_win_rate",
        "jockey_top3_rate",
        "jockey_avg_rank",
        "jockey_start_count",
        "horse_jockey_top3_rate",
        "horse_jockey_start_count",
    ],
    "trainer_specialized": [
        "trainer_win_rate",
        "trainer_top3_rate",
        "trainer_avg_rank",
        "trainer_start_count",
    ],
    "track_specialized": [
        "track_win_rate",
        "track_top3_rate",
        "track_avg_rank",
        "track_field_avg",
        "track_distance_top3_rate",
    ],
    "weather_specialized": [
        "weather_top3_rate",
        "ground_top3_rate",
        "track_weather_top3_rate",
    ],
    "distance_specialized": [
        "distance_bucket_top3_rate",
        "distance_bucket_win_rate",
        "surface_distance_top3_rate",
        "track_distance_top3_rate",
    ],
}
AUX_FEATURE_GROUPS["all_rounder"] = sorted({c for v in AUX_FEATURE_GROUPS.values() for c in v})
AUX_FEATURE_GROUPS["general"] = []


def build_entry_df(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return enrich_dataframe(df, is_result=False)


def build_result_df(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return enrich_dataframe(df, is_result=True)


def _ensure_columns(df, columns: Iterable[str], default=None):
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = default
    return out


def _to_numeric_columns(df, columns: Iterable[str]):
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _fill_group_numeric(series: pd.Series, fallback=0.0, use_median=True) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().any():
        base = s.median() if use_median else s.max()
        if pd.isna(base):
            base = fallback
    else:
        base = fallback
    return s.fillna(base)


def _distance_bucket(distance: float) -> int:
    if pd.isna(distance):
        return 0
    if distance < 1400:
        return 1
    if distance < 1800:
        return 2
    if distance < 2200:
        return 3
    return 4


def enrich_dataframe(df, is_result=False):
    out = df.copy()
    required_cols = [
        "race_id", "track", "race_name", "race_class", "course_info", "weather", "ground", "rank",
        "frame_no", "horse_no", "horse_name", "sex", "age", "carried_weight", "jockey", "trainer",
        "body_weight", "body_weight_diff", "odds", "popularity", "finish_time",
    ]
    out = _ensure_columns(out, required_cols, default=None)

    out["race_id"] = out["race_id"].astype(str)
    out["date"] = out["race_id"].str[:8]
    out["race_no"] = pd.to_numeric(out["race_id"].str[-2:], errors="coerce")
    out["month"] = pd.to_numeric(out["date"].str[4:6], errors="coerce")
    out["day"] = pd.to_numeric(out["date"].str[6:8], errors="coerce")
    out["weekday"] = pd.to_datetime(out["date"], format="%Y%m%d", errors="coerce").dt.weekday

    out = _to_numeric_columns(
        out,
        [
            "frame_no", "horse_no", "age", "carried_weight", "body_weight", "body_weight_diff",
            "odds", "popularity", "rank", "race_no", "month", "day", "weekday",
        ],
    )

    out["sex_code"] = out["sex"].map(SEX_MAP).fillna(-1)
    course = out["course_info"].fillna("").astype(str)
    out["surface"] = course.str.extract(r"([芝ダ障])", expand=False).fillna("")
    out["surface_code"] = out["surface"].map(SURFACE_MAP).fillna(-1)
    out["distance"] = pd.to_numeric(course.str.extract(r"(\d{3,4})m", expand=False), errors="coerce")
    out["direction"] = course.str.extract(r"(右|左|直線)", expand=False).fillna("")
    out["direction_code"] = out["direction"].map(DIRECTION_MAP).fillna(-1)

    out["track_code"] = out["track"].map(TRACK_MAP).fillna(0)
    out["weather_code"] = out["weather"].map(WEATHER_MAP).fillna(0)
    out["ground_code"] = out["ground"].map(GROUND_MAP).fillna(0)

    out["field_size"] = out.groupby("race_id")["horse_name"].transform("count")
    out["field_size"] = pd.to_numeric(out["field_size"], errors="coerce").fillna(0)

    for col, fallback, use_median in [
        ("body_weight", 0.0, True),
        ("body_weight_diff", 0.0, True),
        ("odds", 0.0, True),
        ("popularity", None, False),
        ("carried_weight", 55.0, True),
        ("age", 3.0, True),
        ("distance", 0.0, True),
    ]:
        if col == "popularity":
            out[col] = out.groupby("race_id")[col].transform(lambda s: _fill_group_numeric(s, fallback=len(s), use_median=False))
        else:
            out[col] = out.groupby("race_id")[col].transform(lambda s, fb=fallback, um=use_median: _fill_group_numeric(s, fallback=fb, use_median=um))

    out["odds"] = out["odds"].clip(lower=0)
    out["odds_log"] = out["odds"].apply(lambda x: math.log1p(x) if pd.notna(x) and x >= 0 else 0.0)
    out["popularity_rev"] = out["field_size"] - out["popularity"] + 1

    field_size_safe = out["field_size"].replace(0, pd.NA)
    out["frame_ratio"] = (out["frame_no"] / field_size_safe).fillna(0)
    out["horse_no_ratio"] = (out["horse_no"] / field_size_safe).fillna(0)
    out["is_favorite"] = (out["popularity"] == 1).astype(int)
    out["is_outer_half"] = (out["horse_no"] > (out["field_size"] / 2)).fillna(False).astype(int)

    class_label = out["race_class"].fillna("").astype(str)
    out["is_grade"] = class_label.str.contains(r"G1|G2|G3", regex=True).astype(int)
    out["is_newcomer"] = class_label.str.contains(r"新馬", regex=True).astype(int)
    out["is_maiden"] = class_label.str.contains(r"未勝利", regex=True).astype(int)
    out["distance_bucket"] = out["distance"].apply(_distance_bucket).astype(int)

    if is_result:
        out["target_win"] = (out["rank"] == 1).astype(int)
        out["target_top2"] = (out["rank"] <= 2).astype(int)
        out["target_top3"] = (out["rank"] <= 3).astype(int)
        out["target_top5"] = (out["rank"] <= 5).astype(int)
        out["target_favorite_win"] = ((out["rank"] == 1) & (out["popularity"] == 1)).astype(int)
        out["target_longshot_top3"] = ((out["rank"] <= 3) & (out["popularity"] >= 8)).astype(int)

    numeric_cols = FEATURE_COLUMNS + TARGET_COLUMNS + ["distance_bucket"]
    out = _to_numeric_columns(out, numeric_cols)
    out = out.replace([math.inf, -math.inf], pd.NA)
    out[FEATURE_COLUMNS] = out[FEATURE_COLUMNS].fillna(0)

    return out


def prepare_train_xy(df, target_col):
    if target_col not in df.columns:
        raise ValueError(f"ターゲット列がありません: {target_col}")

    work = enrich_dataframe(df.copy(), is_result=(target_col in df.columns))
    for col in FEATURE_COLUMNS:
        if col not in work.columns:
            work[col] = 0

    X = work[FEATURE_COLUMNS].copy()
    y = pd.to_numeric(work[target_col], errors="coerce")
    valid_mask = y.notna()
    X = X.loc[valid_mask].copy().fillna(0)
    y = y.loc[valid_mask].astype(int).copy()
    return X, y


def compute_history_stats(result_df: pd.DataFrame) -> Dict[str, Dict]:
    df = enrich_dataframe(result_df.copy(), is_result=True)
    if df.empty:
        return {}

    df["is_win"] = (df["rank"] == 1).astype(float)
    df["is_top3"] = (df["rank"] <= 3).astype(float)
    df["rank_num"] = pd.to_numeric(df["rank"], errors="coerce")
    df["distance_bucket"] = df["distance_bucket"].astype(int)

    def _agg(group_cols: List[str], prefix: str) -> Dict:
        g = df.groupby(group_cols, dropna=False).agg(
            start_count=("horse_name", "count"),
            win_rate=("is_win", "mean"),
            top3_rate=("is_top3", "mean"),
            avg_rank=("rank_num", "mean"),
        ).reset_index()
        mapping = {}
        for _, row in g.iterrows():
            key = tuple(row[c] for c in group_cols) if len(group_cols) > 1 else row[group_cols[0]]
            mapping[key] = {
                f"{prefix}_start_count": float(row["start_count"]),
                f"{prefix}_win_rate": float(row["win_rate"]),
                f"{prefix}_top3_rate": float(row["top3_rate"]),
                f"{prefix}_avg_rank": float(row["avg_rank"]) if pd.notna(row["avg_rank"]) else 9.0,
            }
        return mapping

    stats = {
        "horse": _agg(["horse_name"], "horse"),
        "jockey": _agg(["jockey"], "jockey"),
        "trainer": _agg(["trainer"], "trainer"),
        "horse_jockey": _agg(["horse_name", "jockey"], "horse_jockey"),
        "track": _agg(["track_code"], "track"),
        "weather": _agg(["weather_code"], "weather"),
        "ground": _agg(["ground_code"], "ground"),
        "distance_bucket": _agg(["distance_bucket"], "distance_bucket"),
        "track_weather": _agg(["track_code", "weather_code"], "track_weather"),
        "track_distance": _agg(["track_code", "distance_bucket"], "track_distance"),
        "surface_distance": _agg(["surface_code", "distance_bucket"], "surface_distance"),
        "defaults": {},
    }

    stats["defaults"] = {
        "horse_start_count": 0.0,
        "horse_win_rate": float(df["is_win"].mean()),
        "horse_top3_rate": float(df["is_top3"].mean()),
        "horse_avg_rank": float(df["rank_num"].mean()),
        "jockey_start_count": 0.0,
        "jockey_win_rate": float(df["is_win"].mean()),
        "jockey_top3_rate": float(df["is_top3"].mean()),
        "jockey_avg_rank": float(df["rank_num"].mean()),
        "trainer_start_count": 0.0,
        "trainer_win_rate": float(df["is_win"].mean()),
        "trainer_top3_rate": float(df["is_top3"].mean()),
        "trainer_avg_rank": float(df["rank_num"].mean()),
        "horse_jockey_start_count": 0.0,
        "horse_jockey_top3_rate": float(df["is_top3"].mean()),
        "track_start_count": float(df["field_size"].mean()) if "field_size" in df.columns else 0.0,
        "track_win_rate": float(df["is_win"].mean()),
        "track_top3_rate": float(df["is_top3"].mean()),
        "track_avg_rank": float(df["rank_num"].mean()),
        "track_field_avg": float(df["field_size"].mean()) if "field_size" in df.columns else 0.0,
        "weather_top3_rate": float(df["is_top3"].mean()),
        "ground_top3_rate": float(df["is_top3"].mean()),
        "track_weather_top3_rate": float(df["is_top3"].mean()),
        "distance_bucket_start_count": 0.0,
        "distance_bucket_win_rate": float(df["is_win"].mean()),
        "distance_bucket_top3_rate": float(df["is_top3"].mean()),
        "distance_bucket_avg_rank": float(df["rank_num"].mean()),
        "track_distance_top3_rate": float(df["is_top3"].mean()),
        "surface_distance_top3_rate": float(df["is_top3"].mean()),
    }
    return stats


def apply_history_stats(df: pd.DataFrame, stats: Dict[str, Dict], family: str) -> pd.DataFrame:
    out = enrich_dataframe(df.copy(), is_result=("rank" in df.columns and pd.to_numeric(df["rank"], errors="coerce").notna().any()))
    defaults = stats.get("defaults", {})

    def _map_single(source_col: str, mapping_name: str, feature_names: List[str]):
        mapping = stats.get(mapping_name, {})
        for feat in feature_names:
            out[feat] = out[source_col].map(lambda key, m=mapping, f=feat: m.get(key, {}).get(f, defaults.get(f, 0.0)))

    def _map_pair(col_a: str, col_b: str, mapping_name: str, feature_names: List[str]):
        mapping = stats.get(mapping_name, {})
        keys = list(zip(out[col_a], out[col_b]))
        for feat in feature_names:
            out[feat] = [mapping.get(key, {}).get(feat, defaults.get(feat, 0.0)) for key in keys]

    _map_single("horse_name", "horse", ["horse_start_count", "horse_win_rate", "horse_top3_rate", "horse_avg_rank"])
    _map_single("jockey", "jockey", ["jockey_start_count", "jockey_win_rate", "jockey_top3_rate", "jockey_avg_rank"])
    _map_single("trainer", "trainer", ["trainer_start_count", "trainer_win_rate", "trainer_top3_rate", "trainer_avg_rank"])
    _map_pair("horse_name", "jockey", "horse_jockey", ["horse_jockey_start_count", "horse_jockey_top3_rate"])
    _map_single("track_code", "track", ["track_start_count", "track_win_rate", "track_top3_rate", "track_avg_rank"])
    _map_single("weather_code", "weather", ["weather_start_count", "weather_win_rate", "weather_top3_rate", "weather_avg_rank"])
    _map_single("ground_code", "ground", ["ground_start_count", "ground_win_rate", "ground_top3_rate", "ground_avg_rank"])
    _map_single("distance_bucket", "distance_bucket", ["distance_bucket_start_count", "distance_bucket_win_rate", "distance_bucket_top3_rate", "distance_bucket_avg_rank"])
    _map_pair("track_code", "weather_code", "track_weather", ["track_weather_start_count", "track_weather_win_rate", "track_weather_top3_rate", "track_weather_avg_rank"])
    _map_pair("track_code", "distance_bucket", "track_distance", ["track_distance_start_count", "track_distance_win_rate", "track_distance_top3_rate", "track_distance_avg_rank"])
    _map_pair("surface_code", "distance_bucket", "surface_distance", ["surface_distance_start_count", "surface_distance_win_rate", "surface_distance_top3_rate", "surface_distance_avg_rank"])

    out["track_field_avg"] = out["track_start_count"].fillna(defaults.get("track_field_avg", 0.0))
    keep_aux = AUX_FEATURE_GROUPS.get(family, [])
    for col in AUX_FEATURE_GROUPS["all_rounder"]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(defaults.get(col, 0.0))
        if family != "all_rounder" and col not in keep_aux:
            out.drop(columns=[col], inplace=True, errors="ignore")

    return out.replace([math.inf, -math.inf], 0).fillna(0)


def get_feature_columns_for_family(family: str) -> List[str]:
    return FEATURE_COLUMNS + AUX_FEATURE_GROUPS.get(family, [])
