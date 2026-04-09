import os
import re
import time
from typing import List, Tuple

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    CACHE_DIR,
    ENABLE_HTML_CACHE,
    HEADLESS,
    REQUEST_RETRY,
    REQUEST_TIMEOUT,
    SLEEP_BETWEEN_RETRY,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

_HTML_CACHE_ENABLED = bool(ENABLE_HTML_CACHE)

KAISAI_PLACE_CODES = [
    "01","02","03","04","05","06","07","08","09","10",
]

def _normalize_date(date: str) -> str:
    if date is None:
        raise ValueError("日付が未入力です")

    value = str(date).strip()
    if not value:
        raise ValueError("日付が未入力です")

    normalized = value.replace("-", "").replace("/", "").strip()

    if not re.fullmatch(r"\d{8}", normalized):
        raise ValueError(
            "日付形式が不正です。YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD のいずれかで入力してください"
        )

    return normalized


def _build_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _extract_race_ids(html: str) -> List[str]:
    return sorted(set(re.findall(r"race_id=(\d{12})", html)))


def get_race_ids(date: str) -> List[str]:
    date = _normalize_date(date)
    driver = _build_driver()

    try:
        all_ids = set()

        url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date}"
        driver.get(url)

        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            pass

        time.sleep(2)

        html = driver.page_source
        all_ids.update(_extract_race_ids(html))

        if not all_ids:
            for code in KAISAI_PLACE_CODES:
                sub_url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={date}&kaisai_place={code}"
                driver.get(sub_url)
                time.sleep(1.5)
                html = driver.page_source
                all_ids.update(_extract_race_ids(html))

        if not all_ids:
            raise RuntimeError(
                "レースIDを取得できませんでした。"
                "JRA非開催日の可能性があります（基本は土日）。"
            )

        return sorted(all_ids)

    finally:
        driver.quit()


def fetch_race_page(race_id: str, mode: str = "entry", use_cache: bool = True) -> str:
    if mode == "entry":
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    else:
        url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"

    res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    res.raise_for_status()
    res.encoding = res.apparent_encoding or "utf-8"
    return res.text
