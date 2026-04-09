import glob
import json
import os
from typing import Any, Dict, List

import joblib

def load_model(path: str) -> Any:
    return joblib.load(path)

def save_model(model: Any, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    joblib.dump(model, path)
    return path

def list_model_files(model_dir: str) -> List[str]:
    return sorted(glob.glob(os.path.join(model_dir, "*.joblib")))

def save_summary(summary: Dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return path
