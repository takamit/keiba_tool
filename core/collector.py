import os
import re
import time
from typing import Callable, Iterable, List, Optional, Tuple

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
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

_HTML_CACHE_ENABLED = bool(ENABLE_HTML_CACHE)

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

NO_RACE_KEYWORDS = [
    "開催はありません",
    "対象のレースはありません",
    "レースはありません",
    "該当するレースはありません",
    "該当する開催はありません",
]

StatusCallback = Optional[Callable[[str], None]]
WaitCallback = Optional[Callable[[], None]]
CancelCallback = Optional[Callable[[], None]]


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
    with open(_cache_path(name), "w", encoding="utf-8") as file:
        file.write(html)


def _read_cache(name: str) -> str:
    with open(_cache_path(name), "r", encoding="utf-8") as file:
        return file.read()


def get_html_cache_summary() -> Tuple[int, int]:
    _ensure_dir(CACHE_DIR)
    count = 0
    total_size = 0
    for name in os.listdir(CACHE_DIR):
        if not name.lower().endswith(".html"):
            continue
        path = os.path.join(CACHE_DIR, name)
        if os.path.isfile(path):
            count += 1
            total_size += os.path.getsize(path)
    return count, total_size


def clear_html_cache() -> int:
    _ensure_dir(CACHE_DIR)
    removed = 0
    for name in os.listdir(CACHE_DIR):
        if not name.lower().endswith(".html"):
            continue
        path = os.path.join(CACHE_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


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


def _cooperate(wait_if_paused: WaitCallback = None, check_cancel: CancelCallback = None) -> None:
    if check_cancel:
        check_cancel()
    if wait_if_paused:
        wait_if_paused()
    if check_cancel:
        check_cancel()


def _cooperative_sleep(
    seconds: float,
    *,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
    interval: float = 0.2,
) -> None:
    end_at = time.time() + max(seconds, 0.0)
    while True:
        _cooperate(wait_if_paused=wait_if_paused, check_cancel=check_cancel)
        remaining = end_at - time.time()
        if remaining <= 0:
            return
        time.sleep(min(interval, remaining))


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
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='race_id=']")
        for link in links:
            href = link.get_attribute("href") or ""
            found.update(re.findall(r"race_id=(\d{12})", href))
    except Exception:
        pass
    return sorted(found)


def _wait_for_page(
    driver,
    *,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
) -> None:
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except TimeoutException:
        pass

    _cooperative_sleep(2.0, wait_if_paused=wait_if_paused, check_cancel=check_cancel)

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.35);")
        _cooperative_sleep(0.7, wait_if_paused=wait_if_paused, check_cancel=check_cancel)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.7);")
        _cooperative_sleep(0.7, wait_if_paused=wait_if_paused, check_cancel=check_cancel)
        driver.execute_script("window.scrollTo(0, 0);")
        _cooperative_sleep(0.5, wait_if_paused=wait_if_paused, check_cancel=check_cancel)
    except Exception:
        pass


def _load_page_and_collect_ids(
    driver,
    url: str,
    cache_name: str,
    *,
    status_callback: StatusCallback = None,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
) -> Tuple[List[str], str]:
    _cooperate(wait_if_paused=wait_if_paused, check_cancel=check_cancel)
    if status_callback:
        status_callback(f"ページ取得中: {cache_name}")
    driver.get(url)
    _wait_for_page(driver, wait_if_paused=wait_if_paused, check_cancel=check_cancel)

    html = driver.page_source or ""
    _write_cache(cache_name, html)

    race_ids = set(_extract_race_ids_from_html(html))
    if not race_ids:
        race_ids.update(_extract_race_ids_from_dom(driver))

    return sorted(race_ids), html


def _classify_failure_html(html: str) -> Tuple[str, str]:
    if not html:
        return "empty", "HTML未取得"

    lowered = html.lower()

    if "アクセスが集中" in html:
        return "blocked", "アクセス集中"

    if "メンテナンス" in html:
        return "maintenance", "メンテナンス表示"

    if any(keyword in html for keyword in NO_RACE_KEYWORDS):
        return "no_race", "開催なし"

    if "お探しのページは見つかりません" in html or "404" in lowered:
        return "not_found", "404相当"

    if "netkeiba" not in lowered:
        return "unexpected", "想定外HTML"

    return "no_race_id", "race_id未検出"


def _should_treat_as_no_race_day(primary_code: str, sub_codes: List[str]) -> bool:
    if primary_code == "no_race":
        return True

    if primary_code == "not_found" and sub_codes:
        allowed = {"not_found", "no_race", "unexpected", "empty"}
        return all(code in allowed for code in sub_codes)

    return False


def get_race_ids(
    date: str,
    *,
    driver=None,
    allow_empty: bool = True,
    status_callback: StatusCallback = None,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
) -> List[str]:
    normalized_date = _normalize_date(date)

    own_driver = driver is None
    if own_driver:
        driver = _build_driver()

    try:
        _cooperate(wait_if_paused=wait_if_paused, check_cancel=check_cancel)
        all_race_ids = set()
        failure_notes: List[str] = []
        primary_code = "empty"
        sub_codes: List[str] = []

        primary_url = (
            f"https://race.netkeiba.com/top/race_list.html?kaisai_date={normalized_date}"
        )

        try:
            ids, primary_html = _load_page_and_collect_ids(
                driver,
                primary_url,
                f"race_list_{normalized_date}",
                status_callback=status_callback,
                wait_if_paused=wait_if_paused,
                check_cancel=check_cancel,
            )
            all_race_ids.update(ids)

            if not ids:
                primary_code, primary_label = _classify_failure_html(primary_html)
                failure_notes.append(f"race_list={primary_label}")
            else:
                primary_code = "ok"

        except WebDriverException as exc:
            primary_code = "webdriver_error"
            failure_notes.append(
                f"race_list=webdriver_error:{exc.__class__.__name__}"
            )

        if not all_race_ids:
            for place_code in KAISAI_PLACE_CODES:
                _cooperate(wait_if_paused=wait_if_paused, check_cancel=check_cancel)
                sub_url = (
                    "https://race.netkeiba.com/top/race_list_sub.html"
                    f"?kaisai_date={normalized_date}&kaisai_place={place_code}"
                )

                try:
                    ids, sub_html = _load_page_and_collect_ids(
                        driver,
                        sub_url,
                        f"race_list_{normalized_date}_{place_code}",
                        status_callback=status_callback,
                        wait_if_paused=wait_if_paused,
                        check_cancel=check_cancel,
                    )
                    all_race_ids.update(ids)

                    if ids:
                        sub_codes.append("ok")
                        continue

                    sub_code, sub_label = _classify_failure_html(sub_html)
                    sub_codes.append(sub_code)
                    failure_notes.append(f"sub_{place_code}={sub_label}")

                except WebDriverException as exc:
                    sub_codes.append("webdriver_error")
                    failure_notes.append(
                        f"sub_{place_code}=webdriver_error:{exc.__class__.__name__}"
                    )

                _cooperative_sleep(
                    0.8,
                    wait_if_paused=wait_if_paused,
                    check_cancel=check_cancel,
                )

        race_ids = sorted(all_race_ids)
        if race_ids:
            return race_ids

        if allow_empty and _should_treat_as_no_race_day(primary_code, sub_codes):
            return []

        detail = " / ".join(failure_notes[:6]) if failure_notes else "詳細不明"
        raise RuntimeError(
            "レースIDを取得できませんでした。"
            f"日付={normalized_date}、診断={detail}。"
            "開催が存在しない日付、netkeiba側の表示変更、"
            "またはアクセス制限の可能性があります。"
        )

    finally:
        if own_driver and driver is not None:
            driver.quit()


def get_race_ids_by_date(
    dates: Iterable[str],
    *,
    status_callback: StatusCallback = None,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    driver = _build_driver()
    try:
        normalized_dates = [_normalize_date(str(raw_date)) for raw_date in dates]
        resolved: List[Tuple[str, List[str]]] = []
        skipped_dates: List[str] = []
        total = max(len(normalized_dates), 1)

        for index, normalized_date in enumerate(normalized_dates, start=1):
            _cooperate(wait_if_paused=wait_if_paused, check_cancel=check_cancel)
            if status_callback:
                status_callback(f"開催日判定中 ({index}/{total}): {normalized_date}")

            race_ids = get_race_ids(
                normalized_date,
                driver=driver,
                allow_empty=True,
                status_callback=status_callback,
                wait_if_paused=wait_if_paused,
                check_cancel=check_cancel,
            )
            if race_ids:
                resolved.append((normalized_date, race_ids))
            else:
                skipped_dates.append(normalized_date)

            _cooperative_sleep(
                1.2,
                wait_if_paused=wait_if_paused,
                check_cancel=check_cancel,
            )

        return resolved, skipped_dates
    finally:
        driver.quit()


def get_race_ids_for_dates(
    dates: Iterable[str],
    *,
    status_callback: StatusCallback = None,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
) -> Tuple[List[str], List[str]]:
    resolved, skipped_dates = get_race_ids_by_date(
        dates,
        status_callback=status_callback,
        wait_if_paused=wait_if_paused,
        check_cancel=check_cancel,
    )
    merged = sorted({race_id for _, race_ids in resolved for race_id in race_ids})
    return merged, skipped_dates


def fetch_race_page(
    race_id: str,
    mode: str = "entry",
    use_cache: bool = True,
    *,
    status_callback: StatusCallback = None,
    wait_if_paused: WaitCallback = None,
    check_cancel: CancelCallback = None,
) -> str:
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

    last_error: Optional[Exception] = None
    for attempt in range(1, REQUEST_RETRY + 1):
        _cooperate(wait_if_paused=wait_if_paused, check_cancel=check_cancel)
        if status_callback:
            status_callback(f"{mode}ページ取得中: {race_id} ({attempt}/{REQUEST_RETRY})")
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            html = response.text
            _write_cache(cache_name, html)
            return html
        except Exception as exc:
            last_error = exc
            _cooperative_sleep(
                SLEEP_BETWEEN_RETRY,
                wait_if_paused=wait_if_paused,
                check_cancel=check_cancel,
            )

    raise RuntimeError(
        f"レースページ取得失敗: race_id={race_id}, mode={mode}, error={last_error}"
    )
