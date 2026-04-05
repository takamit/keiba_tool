import math
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

WEATHER_MAP = {
    "晴": 1,
    "曇": 2,
    "雨": 3,
    "小雨": 4,
    "雪": 5,
}

GROUND_MAP = {
    "良": 1,
    "稍重": 2,
    "重": 3,
    "不良": 4,
}

SURFACE_MAP = {
    "芝": 0,
    "ダ": 1,
    "障": 2,
}

DIRECTION_MAP = {
    "右": 0,
    "左": 1,
    "直線": 2,
}


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
    "popularity_rate",
    "odds_rank_norm",
]

TARGET_COLUMNS = [
    "target_win",
    "target_top2",
    "target_top3",
    "target_top5",
    "target_favorite_win",
    "target_longshot_top3",
]


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


def _ensure_columns(df, columns, default=None):
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = default
    return out


def _to_numeric_columns(df, columns):
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _fill_popularity(group: pd.Series) -> pd.Series:
    g = pd.to_numeric(group, errors="coerce")
    if g.notna().any():
        fallback = g.max()
    else:
        fallback = len(g)
    return g.fillna(fallback)


def _fill_odds(group: pd.Series) -> pd.Series:
    g = pd.to_numeric(group, errors="coerce")
    if g.notna().any():
        fallback = g.median()
    else:
        fallback = 0.0
    return g.fillna(fallback)


def enrich_dataframe(df, is_result=False):
    out = df.copy()

    required_cols = [
        "race_id",
        "track",
        "race_name",
        "race_class",
        "course_info",
        "weather",
        "ground",
        "rank",
        "frame_no",
        "horse_no",
        "horse_name",
        "sex",
        "age",
        "carried_weight",
        "jockey",
        "body_weight",
        "body_weight_diff",
        "odds",
        "popularity",
        "finish_time",
    ]
    out = _ensure_columns(out, required_cols, default=None)

    out["race_id"] = out["race_id"].astype(str)

    out["date"] = out["race_id"].str[:8]
    out["race_no"] = pd.to_numeric(out["race_id"].str[-2:], errors="coerce")
    out["month"] = pd.to_numeric(out["date"].str[4:6], errors="coerce")
    out["day"] = pd.to_numeric(out["date"].str[6:8], errors="coerce")
    out["weekday"] = pd.to_datetime(
        out["date"], format="%Y%m%d", errors="coerce"
    ).dt.weekday

    out = _to_numeric_columns(
        out,
        [
            "frame_no",
            "horse_no",
            "age",
            "carried_weight",
            "body_weight",
            "body_weight_diff",
            "odds",
            "popularity",
            "rank",
            "race_no",
            "month",
            "day",
            "weekday",
        ],
    )

    out["sex_code"] = out["sex"].map(SEX_MAP).fillna(-1)

    course = out["course_info"].fillna("").astype(str)

    out["surface"] = course.str.extract(r"([芝ダ障])", expand=False).fillna("")
    out["surface_code"] = out["surface"].map(SURFACE_MAP).fillna(-1)

    out["distance"] = pd.to_numeric(
        course.str.extract(r"(\d{3,4})m", expand=False),
        errors="coerce",
    )

    out["direction"] = course.str.extract(r"(右|左|直線)", expand=False).fillna("")
    out["direction_code"] = out["direction"].map(DIRECTION_MAP).fillna(-1)

    out["track_code"] = out["track"].map(TRACK_MAP).fillna(0)
    out["weather_code"] = out["weather"].map(WEATHER_MAP).fillna(0)
    out["ground_code"] = out["ground"].map(GROUND_MAP).fillna(0)

    out["field_size"] = out.groupby("race_id")["horse_name"].transform("count")
    out["field_size"] = pd.to_numeric(out["field_size"], errors="coerce").fillna(0)

    out["popularity"] = out.groupby("race_id")["popularity"].transform(_fill_popularity)
    out["odds"] = out.groupby("race_id")["odds"].transform(_fill_odds)

    out["odds_log"] = out["odds"].apply(
        lambda x: math.log1p(x) if pd.notna(x) and x >= 0 else 0.0
    )

    out["popularity_rev"] = out["field_size"] - out["popularity"] + 1

    field_size_safe = out["field_size"].replace(0, pd.NA)

    out["frame_ratio"] = out["frame_no"] / field_size_safe
    out["horse_no_ratio"] = out["horse_no"] / field_size_safe

    out["is_favorite"] = (out["popularity"] == 1).astype(int)
    out["is_outer_half"] = (
        out["horse_no"] > (out["field_size"] / 2)
    ).fillna(False).astype(int)

    class_label = out["race_class"].fillna("").astype(str)
    out["is_grade"] = class_label.str.contains(r"G1|G2|G3", regex=True).astype(int)
    out["is_newcomer"] = class_label.str.contains(r"新馬", regex=True).astype(int)
    out["is_maiden"] = class_label.str.contains(r"未勝利", regex=True).astype(int)

    out["popularity_rate"] = out["popularity"] / field_size_safe

    odds_rank = out.groupby("race_id")["odds"].rank(method="average", ascending=True)
    out["odds_rank_norm"] = odds_rank / field_size_safe

    if is_result:
        out["target_win"] = (out["rank"] == 1).astype(int)
        out["target_top2"] = (out["rank"] <= 2).astype(int)
        out["target_top3"] = (out["rank"] <= 3).astype(int)
        out["target_top5"] = (out["rank"] <= 5).astype(int)
        out["target_favorite_win"] = (
            (out["rank"] == 1) & (out["popularity"] == 1)
        ).astype(int)
        out["target_longshot_top3"] = (
            (out["rank"] <= 3) & (out["popularity"] >= 8)
        ).astype(int)

    numeric_feature_like_cols = FEATURE_COLUMNS + TARGET_COLUMNS + ["distance"]
    for col in numeric_feature_like_cols:
        if col not in out.columns:
            out[col] = None

    out = _to_numeric_columns(out, numeric_feature_like_cols)
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
    X = X.loc[valid_mask].copy()
    y = y.loc[valid_mask].astype(int).copy()

    return X, y