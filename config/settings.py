import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
MODEL_DIR = os.path.join(BASE_DIR, "models")

REQUEST_TIMEOUT = 15
REQUEST_RETRY = 3
SLEEP_BETWEEN_RETRY = 1
MAX_WORKERS = 6

TRACK_CANDIDATES = ["東京", "中山", "阪神", "京都", "中京", "札幌", "函館", "福島", "新潟", "小倉"]

for path in [DATA_DIR, LOG_DIR, CACHE_DIR, MODEL_DIR]:
    os.makedirs(path, exist_ok=True)
