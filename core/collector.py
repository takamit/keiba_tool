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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
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
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

_HTML_CACHE_ENABLED = bool(ENABLE_HTML_CACHE)
_SESSION: requests.Session | None = None


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


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _SESSION = session
    return _SESSION


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
    options.add_argument("--disable-extensions")
    options.add_argument("--start-maximized")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)

    try:
        driver.set_page_load_timeout(max(REQUEST_TIMEOUT, 30))
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


def _extract_race_ids(html: str) -> List[str]:
    ids = sorted(set(re.findall(r"race_id=(\d{12})", html)))
    return ids


def _looks_blocked_or_invalid(html: str, mode: str) -> bool:
    if not html or len(html.strip()) < 200:
        return True

    blocked_markers = [
        "アクセスが集中",
        "しばらく時間をおいて",
        "forbidden",
        "access denied",
        "too many requests",
        "error 403",
        "error 429",
    ]
    lower_html = html.lower()
    if any(marker in html for marker in blocked_markers[:2]):
        return True
    if any(marker in lower_html for marker in blocked_markers[2:]):
        return True

    if mode == "entry":
        valid_markers = [
            "RaceTable01",
            "race_table_01",
            "Shutuba_Table",
            "出馬表",
            "出走表",
            "馬名",
        ]
    else:
        valid_markers = [
            "RaceTable01",
            "race_table_01",
            "着順",
            "払戻",
            "結果",
            "タイム",
        ]

    return not any(marker in html for marker in valid_markers)


def _request_html(url: str, referer: str | None = None) -> str:
    session = _get_session()
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer

    response = session.get(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def _fetch_with_requests(url: str, mode: str) -> str:
    last_error: Exception | None = None

    for attempt in range(REQUEST_RETRY):
        try:
            html = _request_html(
                url=url,
                referer="https://race.netkeiba.com/",
            )
            if _looks_blocked_or_invalid(html, mode):
                raise RuntimeError("requests取得結果がブロックまたは不完全HTMLでした")
            return html
        except Exception as exc:
            last_error = exc
            sleep_sec = SLEEP_BETWEEN_RETRY * (attempt + 1)
            time.sleep(sleep_sec)

    raise RuntimeError(f"requests取得失敗: {last_error}")


def _wait_for_race_list(driver, timeout: int = 15) -> str:
    end_time = time.time() + timeout
    last_html = ""

    while time.time() < end_time:
        html = driver.page_source or ""
        last_html = html
        if _extract_race_ids(html):
            return html
        time.sleep(0.5)

    return last_html


def _fetch_with_selenium(url: str, mode: str, wait_sec: int = 20) -> str:
    driver = _build_driver()
    try:
        driver.get(url)

        if "race_list.html" in url:
            html = _wait_for_race_list(driver, timeout=wait_sec)
            if _extract_race_ids(html):
                return html
            raise RuntimeError("Seleniumでrace_idを取得できませんでした")

        try:
            WebDriverWait(driver, wait_sec).until(
                lambda d: not _looks_blocked_or_invalid(d.page_source or "", mode)
            )
        except TimeoutException:
            pass

        html = driver.page_source or ""
        if _looks_blocked_or_invalid(html, mode):
            raise RuntimeError("Selenium取得結果がブロックまたは不完全HTMLでした")
        return html
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def get_race_ids(date: str) -> List[str]:
    if not re.fullmatch(r"\d{8}", date):
        raise ValueError("日付は YYYYMMDD 8桁で入力してください")

    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date}"
    cache_name = f"race_list_{date}"
    cache_path = _cache_path(cache_name)

    if _HTML_CACHE_ENABLED and os.path.exists(cache_path):
        html = _read_cache(cache_name)
        race_ids = _extract_race_ids(html)
        if race_ids:
            return race_ids

    last_error: Exception | None = None

    for attempt in range(REQUEST_RETRY):
        try:
            html = _fetch_with_selenium(url, mode="entry", wait_sec=15 + attempt * 5)
            race_ids = _extract_race_ids(html)
            if not race_ids:
                raise RuntimeError("開催ページからrace_idを抽出できませんでした")
            _write_cache(cache_name, html)
            return race_ids
        except Exception as exc:
            last_error = exc
            time.sleep(SLEEP_BETWEEN_RETRY * (attempt + 1))

    raise RuntimeError(f"race_id取得失敗: date={date}, error={last_error}")


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
        html = _read_cache(cache_name)
        if not _looks_blocked_or_invalid(html, mode):
            return html

    request_error: Exception | None = None
    try:
        html = _fetch_with_requests(url, mode)
        _write_cache(cache_name, html)
        return html
    except Exception as exc:
        request_error = exc

    selenium_error: Exception | None = None
    try:
        html = _fetch_with_selenium(url, mode=mode, wait_sec=20)
        _write_cache(cache_name, html)
        return html
    except Exception as exc:
        selenium_error = exc

    raise RuntimeError(
        "レースページ取得失敗: "
        f"race_id={race_id}, mode={mode}, "
        f"requests_error={request_error}, selenium_error={selenium_error}"
    )