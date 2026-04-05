import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup


def _safe_text(cells, idx: int) -> str:
    return cells[idx].get_text(" ", strip=True) if idx < len(cells) else ""


def _to_int(value: str) -> Optional[int]:
    value = value.strip()
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    return None


def _to_float(value: str) -> Optional[float]:
    value = value.strip().replace(",", "")
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", value):
        return float(value)
    return None


def _split_sex_age(value: str) -> tuple[Optional[str], Optional[int]]:
    m = re.match(r"([牡牝セ騙])\s*(\d+)", value)
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def _parse_body_weight(value: str) -> tuple[Optional[int], Optional[int]]:
    m = re.match(r"(\d+)\(([-+]?\d+)\)", value.replace(" ", ""))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def parse_race_meta(html: str) -> Dict[str, Optional[str]]:
    soup = BeautifulSoup(html, "lxml")
    race_name = None
    race_class = None
    course_info = None
    weather = None
    ground = None

    title_el = soup.select_one(".RaceName") or soup.select_one(".RaceList_Name")
    if title_el:
        race_name = title_el.get_text(" ", strip=True)

    data01 = soup.select_one(".RaceData01")
    if data01:
        text = data01.get_text(" ", strip=True)
        course_info = text
        weather_m = re.search(r"天候\s*:\s*([^\s/]+)", text)
        ground_m = re.search(r"馬場\s*:\s*([^\s/]+)", text)
        if weather_m:
            weather = weather_m.group(1)
        if ground_m:
            ground = ground_m.group(1)

    data02 = soup.select_one(".RaceData02")
    if data02:
        race_class = data02.get_text(" ", strip=True)

    return {
        "race_name": race_name,
        "race_class": race_class,
        "course_info": course_info,
        "weather": weather,
        "ground": ground,
    }


def parse_entry_table(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for cls in ["RaceTable01", "race_table_01", "race_table"]:
        table = soup.find("table", class_=cls)
        if table:
            break

    if not table:
        raise ValueError("出走表テーブルが見つかりません")

    horses: List[Dict] = []
    for row in table.select("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        frame = _to_int(_safe_text(cells, 0))
        number = _to_int(_safe_text(cells, 1))
        horse_name = _safe_text(cells, 3)
        sex_age_raw = _safe_text(cells, 4)
        sex, age = _split_sex_age(sex_age_raw)
        carried_weight = _to_float(_safe_text(cells, 5))
        jockey = _safe_text(cells, 6)
        body_weight, body_weight_diff = _parse_body_weight(_safe_text(cells, 7))
        odds = _to_float(_safe_text(cells, 9))
        popularity = _to_int(_safe_text(cells, 10))

        if not horse_name:
            continue

        horses.append(
            {
                "frame": frame,
                "number": number,
                "horse_name": horse_name,
                "sex": sex,
                "age": age,
                "sex_age": sex_age_raw,
                "carried_weight": carried_weight,
                "jockey": jockey,
                "body_weight": body_weight,
                "body_weight_diff": body_weight_diff,
                "odds": odds,
                "popularity": popularity,
            }
        )
    return horses


def parse_result_table(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for cls in ["RaceTable01", "race_table_01", "race_table"]:
        table = soup.find("table", class_=cls)
        if table:
            break

    if not table:
        raise ValueError("結果テーブルが見つかりません")

    results: List[Dict] = []
    for row in table.select("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 12:
            continue

        rank = _to_int(_safe_text(cells, 0))
        frame = _to_int(_safe_text(cells, 1))
        number = _to_int(_safe_text(cells, 2))
        horse_name = _safe_text(cells, 3)
        sex_age_raw = _safe_text(cells, 4)
        sex, age = _split_sex_age(sex_age_raw)
        carried_weight = _to_float(_safe_text(cells, 5))
        jockey = _safe_text(cells, 6)
        finish_time = _safe_text(cells, 7)
        odds = _to_float(_safe_text(cells, 9))
        popularity = _to_int(_safe_text(cells, 10))
        body_weight, body_weight_diff = _parse_body_weight(_safe_text(cells, 11))

        if not horse_name:
            continue

        results.append(
            {
                "rank": rank,
                "frame": frame,
                "number": number,
                "horse_name": horse_name,
                "sex": sex,
                "age": age,
                "sex_age": sex_age_raw,
                "carried_weight": carried_weight,
                "jockey": jockey,
                "finish_time": finish_time,
                "odds": odds,
                "popularity": popularity,
                "body_weight": body_weight,
                "body_weight_diff": body_weight_diff,
            }
        )
    return results
