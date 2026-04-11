from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence, Tuple, TypeVar

from core.collector import fetch_race_page, get_race_ids_by_date
from core.parser import parse_entry, parse_result

T = TypeVar("T")

ProgressCallback = Callable[[float, float, str], None]
LogCallback = Callable[[str], None]
WaitCallback = Callable[[], None]
CancelCallback = Callable[[], None]


@dataclass(frozen=True)
class HoldingDateBatch:
    date_obj: object
    date_str: str
    race_ids: List[str]


def resolve_holding_dates(
    date_list: Sequence[T],
    *,
    date_to_str: Callable[[T], str],
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
    wait_if_paused: WaitCallback | None = None,
    check_cancel: CancelCallback | None = None,
) -> Tuple[List[HoldingDateBatch], List[str]]:
    if not date_list:
        return [], []

    normalized_dates = [date_to_str(date_obj) for date_obj in date_list]
    total = max(len(date_list), 1)
    status_state = {"current_index": 0}

    def status_callback(message: str) -> None:
        if progress_callback:
            current = min(status_state["current_index"] + 0.5, float(total))
            progress_callback(current, float(total), message)

    resolved_pairs, skipped_dates = get_race_ids_by_date(
        normalized_dates,
        status_callback=status_callback,
        wait_if_paused=wait_if_paused,
        check_cancel=check_cancel,
    )
    race_id_map = {date_str: race_ids for date_str, race_ids in resolved_pairs}

    valid_batches: List[HoldingDateBatch] = []
    for index, date_obj in enumerate(date_list, start=1):
        status_state["current_index"] = index
        date_str = date_to_str(date_obj)
        race_ids = race_id_map.get(date_str, [])

        if progress_callback:
            progress_callback(float(index), float(total), f"開催日判定完了 {date_str}")

        if race_ids:
            valid_batches.append(
                HoldingDateBatch(
                    date_obj=date_obj,
                    date_str=date_str,
                    race_ids=race_ids,
                )
            )
            if log_callback:
                log_callback(f"[開催判定] {date_str}: 開催あり / race_id数={len(race_ids)}")
        else:
            if log_callback:
                log_callback(f"[開催判定] {date_str}: 非開催")

    return valid_batches, skipped_dates


def collect_rows_for_race_ids(
    race_ids: Iterable[str],
    *,
    mode: str,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    wait_if_paused: WaitCallback | None = None,
    check_cancel: CancelCallback | None = None,
) -> List[dict]:
    rows: List[dict] = []
    parser_func = parse_entry if mode == "entry" else parse_result
    race_ids = list(race_ids)
    total = max(len(race_ids), 1)

    for index, race_id in enumerate(race_ids, start=1):
        if log_callback:
            log_callback(f"[INFO] {mode}取得中: race_id={race_id}")
        if progress_callback:
            progress_callback(float(index - 1), float(total), f"{mode}取得中 {race_id}")

        html = fetch_race_page(
            race_id,
            mode=mode,
            use_cache=True,
            status_callback=lambda message, idx=index, total_count=total: (
                progress_callback(min(float(idx - 1) + 0.5, float(total_count)), float(total_count), message)
                if progress_callback
                else None
            ),
            wait_if_paused=wait_if_paused,
            check_cancel=check_cancel,
        )
        rows.extend(parser_func(html, race_id))

        if progress_callback:
            progress_callback(float(index), float(total), f"{mode}取得完了 {race_id}")

    return rows
