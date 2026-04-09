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

# JRA主な開催場コード
KAISAI_PLACE_CODES = [
    "01",  # 札幌
    "02",  # 函館
    "03",  # 福島
    "04",  # 新潟
    "05",  # 東京
    "06",  # 中山
    "07",  # 中京
    "08",  # 京都
    "09",  # 阪神
    "10",  # 小倉
]


def set_html_cache_enabled(enabled: bool) -> None:
    global _HTML_CACHE_ENABLED
    _HTML_CACHE_ENABLED = bool(enabled)


def is_html_cache_enabled() -> bool:
    return _HTML_CACHE_ENABLED


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _cache_path(name: str) -> str:
    _ensure_dir(CACHE_DIR)
    safe = re.sub(r"[^0-9A-Za-z_\-]", "_", name)
    return os.path.join(CACHE_DIR, f"{safe}.html")


def _write_cache(name: str, html: str) -> None:
    if not _HTML_CACHE_ENABLED:
        return
    cache_path = _cache_path(name)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(html)


def _read_cache(name: str) -> str:
    cache_path = _cache_path(name)
    with open(cache_path, "r", encoding="utf-8") as f:
        return f.read()


def _normalize_date(date: str) -> str:
    """
    許可形式:
      - YYYYMMDD
      - YYYY-MM-DD
      - YYYY/MM/DD
    戻り値は YYYYMMDD
    """
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

    yyyy = int(normalized[0:4])
    mm = int(normalized[4:6])
    dd = int(normalized[6:8])

    if yyyy < 1900 or yyyy > 2100:
        raise ValueError("年の値が不正です")
    if mm < 1 or mm > 12:
        raise ValueError("月の値が不正です")
    if dd < 1 or dd > 31:
        raise ValueError("日の値が不正です")

    return normalized


def _build_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--lang=ja-JP")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent="
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            },
        )
    except Exception:
        pass

    return driver


def get_html_cache_summary() -> Tuple[int, int]:
    _ensure_dir(CACHE_DIR)
    total_size = 0
    files = []
    for name in os.listdir(CACHE_DIR):
        if not name.lower().endswith(".html"):
            continue
        path = os.path.join(CACHE_DIR, name)
        if os.path.isfile(path):
            files.append(path)
            total_size += os.path.getsize(path)
    return len(files), total_size


def clear_html_cache() -> int:
    _ensure_dir(CACHE_DIR)
    removed = 0
    for name in os.listdir(CACHE_DIR):
        if not name.lower().endswith(".html"):
            continue
        path = os.path.join(CACHE_DIR, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def _extract_race_ids_from_html(html: str) -> List[str]:
    patterns = [
        r"race_id=(\d{12})",
        r"/race/shutuba\.html\?race_id=(\d{12})",
        r"/race/result\.html\?race_id=(\d{12})",
        r'"race_id":"(\d{12})"',
        r"'race_id':'(\d{12})'",
    ]

    found = set()
    for pattern in patterns:
        found.update(re.findall(pattern, html))

    return sorted(found)


def _extract_race_ids_from_dom(driver) -> List[str]:
    found = set()

    try:
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='race_id=']")
        for elem in elements:
            href = elem.get_attribute("href") or ""
            found.update(re.findall(r"race_id=(\d{12})", href))
    except Exception:
        pass

    return sorted(found)


def _load_page_and_collect_ids(driver, url: str, cache_name: str) -> Tuple[List[str], str]:
    driver.get(url)

    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except TimeoutException:
        pass

    time.sleep(2.0)

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(0.7)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(0.7)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
    except Exception:
        pass

    html = driver.page_source or ""
    _write_cache(cache_name, html)

    race_ids = set(_extract_race_ids_from_html(html))
    if not race_ids:
        race_ids.update(_extract_race_ids_from_dom(driver))

    return sorted(race_ids), html


def get_race_ids(date: str) -> List[str]:
    normalized_date = _normalize_date(date)
    driver = _build_driver()

    try:
        all_race_ids = set()
        primary_html = ""

        primary_url = (
            f"https://race.netkeiba.com/top/race_list.html?kaisai_date={normalized_date}"
        )
        try:
            ids, primary_html = _load_page_and_collect_ids(
                driver,
                primary_url,
                f"race_list_{normalized_date}",
            )
            all_race_ids.update(ids)
        except WebDriverException:
            pass

        if not all_race_ids:
            for place_code in KAISAI_PLACE_CODES:
                sub_url = (
                    "https://race.netkeiba.com/top/race_list_sub.html"
                    f"?kaisai_date={normalized_date}&kaisai_place={place_code}"
                )
                try:
                    ids, _ = _load_page_and_collect_ids(
                        driver,
                        sub_url,
                        f"race_list_{normalized_date}_{place_code}",
                    )
                    all_race_ids.update(ids)
                except WebDriverException:
                    continue

        race_ids = sorted(all_race_ids)

        if not race_ids:
            if primary_html:
                lower_html = primary_html.lower()
                if "地方" in primary_html or "nar" in lower_html:
                    raise RuntimeError(
                        "指定日は地方競馬開催日の可能性があります。"
                        "現在のレースID取得はJRA開催前提です。"
                        "JRA開催日（土日中心）を指定してください。"
                    )

            raise RuntimeError(
                "レースIDを取得できませんでした。"
                "JRA非開催日の可能性があります。"
                "まずは土日の開催日を指定してください。"
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

    if _HTML_CACHE_ENABLED and use_cache and os.path.exists(cache_path):
        return _read_cache(cache_name)

    last_error = None
    for _ in range(REQUEST_RETRY):
        try:
            res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            res.raise_for_status()
            res.encoding = res.apparent_encoding or "utf-8"
            html = res.text
            _write_cache(cache_name, html)
            return html
        except Exception as e:
            last_error = e
            time.sleep(SLEEP_BETWEEN_RETRY)

    raise RuntimeError(
        f"レースページ取得失敗: race_id={race_id}, mode={mode}, error={last_error}"
    )
