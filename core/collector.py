import os
import re
import time
from typing import List

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import CACHE_DIR, HEADLESS, REQUEST_RETRY, REQUEST_TIMEOUT, SLEEP_BETWEEN_RETRY


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _cache_path(name: str) -> str:
    _ensure_dir(CACHE_DIR)
    safe = re.sub(r"[^0-9A-Za-z_\-]", "_", name)
    return os.path.join(CACHE_DIR, f"{safe}.html")


def _build_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--lang=ja-JP")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def get_race_ids(date: str) -> List[str]:
    if not re.fullmatch(r"\d{8}", date):
        raise ValueError("日付は YYYYMMDD 8桁で入力してください")

    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date}"
    driver = _build_driver()

    try:
        driver.get(url)
        time.sleep(3)

        html = driver.page_source

        cache_path = _cache_path(f"race_list_{date}")
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(html)

        race_ids = sorted(set(re.findall(r"race_id=(\d{12})", html)))

        if not race_ids:
            raise ValueError(
                f"race_idを取得できませんでした: {date}\n"
                f"確認ファイル: {cache_path}"
            )

        return race_ids
    finally:
        driver.quit()


def fetch_race_page(race_id: str, mode: str = "entry", use_cache: bool = True) -> str:
    if not re.fullmatch(r"\d{12}", race_id):
        raise ValueError(f"race_id形式が不正です: {race_id}")

    if mode == "entry":
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    elif mode == "result":
        url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    else:
        raise ValueError(f"不正なmodeです: {mode}")

    cache_name = f"{mode}_{race_id}"
    cache_path = _cache_path(cache_name)

    if use_cache and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()

    last_error = None

    for _ in range(REQUEST_RETRY):
        try:
            res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            res.raise_for_status()
            res.encoding = res.apparent_encoding or "utf-8"
            html = res.text

            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(html)

            return html
        except Exception as e:
            last_error = e
            time.sleep(SLEEP_BETWEEN_RETRY)

    raise RuntimeError(f"レースページ取得失敗: race_id={race_id}, mode={mode}, error={last_error}")
