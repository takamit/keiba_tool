import re

def compact_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
