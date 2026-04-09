from typing import List
from core.collector import fetch_race_page, get_race_ids
from core.parser import parse_entry, parse_result

def collect_entry_rows(date: str) -> List[dict]:
    rows = []
    for race_id in get_race_ids(date):
        html = fetch_race_page(race_id, mode="entry", use_cache=True)
        rows.extend(parse_entry(html, race_id))
    return rows

def collect_result_rows(date: str) -> List[dict]:
    rows = []
    for race_id in get_race_ids(date):
        html = fetch_race_page(race_id, mode="result", use_cache=True)
        rows.extend(parse_result(html, race_id))
    return rows
