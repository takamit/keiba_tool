import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def _safe_text(cells, idx: int) -> str:
    return cells[idx].get_text(" ", strip=True) if idx < len(cells) else ""


def _to_int(value: str) -> Optional[int]:
    value = value.strip().replace(",", "")
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    return None


def _to_float(value: str) -> Optional[float]:
    value = value.strip().replace(",", "")
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", value):
        return float(value)
    return None


def _split_sex_age(value: str) -> Tuple[Optional[str], Optional[int]]:
    m = re.match(r"([牡牝セ騙])\s*(\d+)", value.strip())
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def _parse_body_weight(value: str) -> Tuple[Optional[int], Optional[int]]:
    value = value.replace(" ", "")
    m = re.match(r"(\d+)\(([-+]?\d+)\)", value)
    if not m:
        if re.fullmatch(r"\d+", value):
            return int(value), None
        return None, None
    return int(m.group(1)), int(m.group(2))


def _find_main_table(soup: BeautifulSoup):
    for cls in ["RaceTable01", "race_table_01", "race_table"]:
        table = soup.find("table", class_=cls)
        if table:
            return table
    return None


def parse_race_meta(html: str, race_id: str) -> Dict:
    soup = BeautifulSoup(html, "lxml")

    race_name = ""
    race_class = ""
    course_info = ""
    weather = ""
    ground = ""
    track = ""

    race_name_el = soup.select_one(".RaceName") or soup.select_one(".RaceList_Name")
    if race_name_el:
        race_name = race_name_el.get_text(" ", strip=True)

    data01 = soup.select_one(".RaceData01")
    if data01:
        course_info = data01.get_text(" ", strip=True)

        m = re.search(r"天候\s*:\s*([^\s/]+)", course_info)
        if m:
            weather = m.group(1)

        m = re.search(r"馬場\s*:\s*([^\s/]+)", course_info)
        if m:
            ground = m.group(1)

    data02 = soup.select_one(".RaceData02")
    if data02:
        race_class = data02.get_text(" ", strip=True)

    for t in ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]:
        if t in html:
            track = t
            break

    return {
        "race_id": race_id,
        "track": track,
        "race_name": race_name,
        "race_class": race_class,
        "course_info": course_info,
        "weather": weather,
        "ground": ground,
    }


def parse_entry(html: str, race_id: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    meta = parse_race_meta(html, race_id)
    table = _find_main_table(soup)

    if not table:
        raise ValueError(f"出走表テーブルが見つかりません: {race_id}")

    rows: List[Dict] = []

    for tr in table.select("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 10:
            continue

        frame_no = _to_int(_safe_text(cells, 0))
        horse_no = _to_int(_safe_text(cells, 1))
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

        rows.append({
            **meta,
            "rank": None,
            "frame_no": frame_no,
            "horse_no": horse_no,
            "horse_name": horse_name,
            "sex": sex,
            "age": age,
            "carried_weight": carried_weight,
            "jockey": jockey,
            "body_weight": body_weight,
            "body_weight_diff": body_weight_diff,
            "odds": odds,
            "popularity": popularity,
            "finish_time": None,
        })

    return rows


def parse_result(html: str, race_id: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    meta = parse_race_meta(html, race_id)
    table = _find_main_table(soup)

    if not table:
        raise ValueError(f"結果テーブルが見つかりません: {race_id}")

    rows: List[Dict] = []

    for tr in table.select("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 12:
            continue

        rank = _to_int(_safe_text(cells, 0))
        frame_no = _to_int(_safe_text(cells, 1))
        horse_no = _to_int(_safe_text(cells, 2))
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

        rows.append({
            **meta,
            "rank": rank,
            "frame_no": frame_no,
            "horse_no": horse_no,
            "horse_name": horse_name,
            "sex": sex,
            "age": age,
            "carried_weight": carried_weight,
            "jockey": jockey,
            "body_weight": body_weight,
            "body_weight_diff": body_weight_diff,
            "odds": odds,
            "popularity": popularity,
            "finish_time": finish_time,
        })

    return rows
