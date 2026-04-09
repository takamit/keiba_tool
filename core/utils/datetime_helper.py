from datetime import datetime

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
