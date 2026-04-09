import os
from typing import Iterable

def ensure_dirs(paths: Iterable[str]) -> None:
    for path in paths:
        os.makedirs(path, exist_ok=True)
