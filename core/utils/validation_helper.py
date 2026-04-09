import re

def normalize_date(date_value: str) -> str:
    value = str(date_value or "").strip().replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError("日付形式が不正です。YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD のいずれかで入力してください")
    return value
