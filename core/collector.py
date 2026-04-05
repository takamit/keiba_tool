import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests

from bs4 import BeautifulSoup

from config.settings import CACHE_DIR, MAX_WORKERS, REQUEST_RETRY, REQUEST_TIMEOUT, SLEEP_BETWEEN_RETRY, TRACK_CANDIDATES
from core.parser import parse_entry_table, parse_race_meta, parse_result_table
from utils.logger import get_logger

logger = get_logger()


class RaceDataCollector:
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _cache_path(self, race_id: str, mode: str) -> str:
        return os.path.join(CACHE_DIR, f"{mode}_{race_id}.html")

    def _fetch_html(self, url: str, cache_path: str) -> Optional[str]:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        for retry in range(1, REQUEST_RETRY + 1):
            try:
                res = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                res.raise_for_status()
                res.encoding = res.apparent_encoding
                html = res.text
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(html)
                return html
            except Exception as exc:
                logger.warning("HTML取得失敗 %s retry=%s/%s", url, retry, REQUEST_RETRY)
                logger.warning("detail: %s", exc)
                time.sleep(SLEEP_BETWEEN_RETRY)
        return None

    def _extract_track(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        for name in TRACK_CANDIDATES:
            if name in text:
                return name
        return "不明"

    def fetch_entry(self, race_id: str) -> Optional[Dict]:
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
        html = self._fetch_html(url, self._cache_path(race_id, "entry"))
        if not html:
            return None

        meta = parse_race_meta(html)
        horses = parse_entry_table(html)
        return {
            "race_id": race_id,
            "track": self._extract_track(html),
            **meta,
            "horses": horses,
        }

    def fetch_result(self, race_id: str) -> Optional[Dict]:
        url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
        html = self._fetch_html(url, self._cache_path(race_id, "result"))
        if not html:
            return None

        meta = parse_race_meta(html)
        horses = parse_result_table(html)
        return {
            "race_id": race_id,
            "track": self._extract_track(html),
            **meta,
            "horses": horses,
        }

    def collect_entries(self, date: str, race_ids: List[str]) -> Dict:
        return self._collect(date, race_ids, self.fetch_entry)

    def collect_results(self, date: str, race_ids: List[str]) -> Dict:
        return self._collect(date, race_ids, self.fetch_result)

    def _collect(self, date: str, race_ids: List[str], fetch_func) -> Dict:
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_func, race_id) for race_id in race_ids]
            for future in as_completed(futures):
                data = future.result()
                if data:
                    results.append(data)

        results.sort(key=lambda x: x["race_id"])
        if not results:
            raise ValueError("レースデータを1件も取得できませんでした")

        grouped: Dict[str, List[Dict]] = {}
        for race in results:
            grouped.setdefault(race["track"], []).append(race)

        return {
            "date": date,
            "tracks": [{"name": k, "races": v} for k, v in grouped.items()],
        }
