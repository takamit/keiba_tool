from typing import Iterable, List

from core.collector import fetch_race_page, get_race_ids, get_race_ids_for_dates
from core.parser import parse_entry, parse_result


def collect_entry_rows(date: str) -> List[dict]:
    rows: List[dict] = []
    for race_id in get_race_ids(date):
        html = fetch_race_page(race_id, mode="entry", use_cache=True)
        rows.extend(parse_entry(html, race_id))
    return rows


def collect_result_rows(date: str) -> List[dict]:
    rows: List[dict] = []
    for race_id in get_race_ids(date):
        html = fetch_race_page(race_id, mode="result", use_cache=True)
        rows.extend(parse_result(html, race_id))
    return rows


def collect_entry_rows_for_dates(dates: Iterable[str]) -> List[dict]:
    rows: List[dict] = []
    race_ids, _ = get_race_ids_for_dates(dates)
    for race_id in race_ids:
        html = fetch_race_page(race_id, mode="entry", use_cache=True)
        rows.extend(parse_entry(html, race_id))
    return rows


def collect_result_rows_for_dates(dates: Iterable[str]) -> List[dict]:
    rows: List[dict] = []
    race_ids, _ = get_race_ids_for_dates(dates)
    for race_id in race_ids:
        html = fetch_race_page(race_id, mode="result", use_cache=True)
        rows.extend(parse_result(html, race_id))
    return rows
