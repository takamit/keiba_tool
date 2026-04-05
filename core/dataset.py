import math
import pandas as pd


SEX_MAP = {"牡": 0, "牝": 1, "セ": 2, "騙": 2}

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


def enrich_dataframe(df, is_result=False):
    out = df.copy()

    required_cols = [
        "race_id", "track", "race_name", "race_class", "course_info", "weather", "ground",
        "frame_no", "horse_no", "horse_name", "sex", "age", "carried_weight",
        "jockey", "body_weight", "body_weight_diff", "odds", "popularity", "rank"
    ]
    for col in required_cols:
        if col not in out.columns:
            out[col] = None

    out["race_id"] = out["race_id"].astype(str)
    out["date"] = out["race_id"].str[:8]
    out["race_no"] = pd.to_numeric(out["race_id"].str[-2:], errors="coerce")
    out["month"] = pd.to_numeric(out["date"].str[4:6], errors="coerce")
    out["day"] = pd.to_numeric(out["date"].str[6:8], errors="coerce")
    out["weekday"] = pd.to_datetime(out["date"], format="%Y%m%d", errors="coerce").dt.weekday

    out["sex_code"] = out["sex"].map(SEX_MAP).fillna(-1)

    course = out["course_info"].fillna("").astype(str)
    out["surface"] = course.str.extract(r"([芝ダ障])", expand=False).fillna("")
    out["surface_code"] = out["surface"].map({"芝": 0, "ダ": 1, "障": 2}).fillna(-1)

    out["distance"] = pd.to_numeric(
        course.str.extract(r"(\d{3,4})m", expand=False),
        errors="coerce"
    )

    out["direction"] = course.str.extract(r"(右|左|直線)", expand=False).fillna("")
    out["direction_code"] = out["direction"].map({"右": 0, "左": 1, "直線": 2}).fillna(-1)

    out["track_code"] = out["track"].map({
        "札幌": 1, "函館": 2, "福島": 3, "新潟": 4, "東京": 5,
        "中山": 6, "中京": 7, "京都": 8, "阪神": 9, "小倉": 10
    }).fillna(0)

    out["weather_code"] = out["weather"].map({
        "晴": 1, "曇": 2, "雨": 3, "小雨": 4, "雪": 5
    }).fillna(0)

    out["ground_code"] = out["ground"].map({
        "良": 1, "稍重": 2, "重": 3, "不良": 4
    }).fillna(0)

    numeric_cols = [
        "frame_no", "horse_no", "age", "carried_weight",
        "body_weight", "body_weight_diff", "odds", "popularity", "rank"
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["field_size"] = out.groupby("race_id")["horse_name"].transform("count")
    out["frame_ratio"] = out["frame_no"] / out["field_size"].replace(0, pd.NA)
    out["horse_no_ratio"] = out["horse_no"] / out["field_size"].replace(0, pd.NA)

    out["is_favorite"] = (out["popularity"] == 1).astype(int)
    out["is_outer_half"] = (
        out["horse_no"] > (out["field_size"] / 2)
    ).fillna(False).astype(int)

    out["odds_log"] = out["odds"].apply(
        lambda x: math.log1p(x) if pd.notna(x) and x >= 0 else None
    )
    out["popularity_rev"] = out["field_size"] - out["popularity"] + 1

    class_label = out["race_class"].fillna("").astype(str)
    out["is_grade"] = class_label.str.contains(r"G1|G2|G3", regex=True).astype(int)
    out["is_newcomer"] = class_label.str.contains(r"新馬", regex=True).astype(int)
    out["is_maiden"] = class_label.str.contains(r"未勝利", regex=True).astype(int)

    if is_result:
        out["target_win"] = (out["rank"] == 1).astype(int)
        out["target_top2"] = (out["rank"] <= 2).astype(int)
        out["target_top3"] = (out["rank"] <= 3).astype(int)
        out["target_top5"] = (out["rank"] <= 5).astype(int)
        out["target_favorite_win"] = ((out["rank"] == 1) & (out["popularity"] == 1)).astype(int)
        out["target_longshot_top3"] = ((out["rank"] <= 3) & (out["popularity"] >= 8)).astype(int)

    return out


def prepare_train_xy(df, target_col):
    if target_col not in df.columns:
        raise ValueError(f"ターゲット列がありません: {target_col}")

    work = df.copy()

    for col in FEATURE_COLUMNS:
        if col not in work.columns:
            work[col] = None

    X = work[FEATURE_COLUMNS].copy()
    y = pd.to_numeric(work[target_col], errors="coerce")

    valid_mask = y.notna()
    X = X.loc[valid_mask].copy()
    y = y.loc[valid_mask].astype(int).copy()

    return X, y
