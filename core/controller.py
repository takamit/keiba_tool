from __future__ import annotations

import glob
import os
from typing import Dict, List

import pandas as pd

from config.settings import DATA_DIR
from core.collector import RaceDataCollector
from core.dataset import build_entry_dataframe, build_result_dataframe
from core.race_scraper import RaceListScraper
from ml.predictor import KeibaPredictor
from ml.trainer import KeibaModelTrainer
from utils.file_utils import save_json
from utils.logger import get_logger

logger = get_logger()


class Controller:
    def __init__(self):
        self.list_scraper = RaceListScraper()
        self.collector = RaceDataCollector()
        self.trainer = KeibaModelTrainer()
        self.predictor = KeibaPredictor()

    def collect_entry_by_date(self, date: str) -> Dict:
        race_ids = self.list_scraper.get_race_ids(date)
        if not race_ids:
            raise ValueError("対象日のrace_idを取得できませんでした")
        payload = self.collector.collect_entries(date, race_ids)
        json_path = os.path.join(DATA_DIR, f"entry_{date}.json")
        csv_path = os.path.join(DATA_DIR, f"entry_{date}.csv")
        save_json(json_path, payload)
        build_entry_dataframe(payload).to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info("出走表保存: %s / %s", json_path, csv_path)
        return {"json": json_path, "csv": csv_path, "count": len(race_ids)}

    def collect_result_by_date(self, date: str) -> Dict:
        race_ids = self.list_scraper.get_race_ids(date)
        if not race_ids:
            raise ValueError("対象日のrace_idを取得できませんでした")
        payload = self.collector.collect_results(date, race_ids)
        json_path = os.path.join(DATA_DIR, f"result_{date}.json")
        csv_path = os.path.join(DATA_DIR, f"result_{date}.csv")
        save_json(json_path, payload)
        build_result_dataframe(payload).to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info("結果保存: %s / %s", json_path, csv_path)
        return {"json": json_path, "csv": csv_path, "count": len(race_ids)}

    def collect_results_by_dates(self, dates: List[str]) -> List[Dict]:
        outputs = []
        for date in dates:
            outputs.append(self.collect_result_by_date(date))
        return outputs

    def train_from_saved_results(self, target_col: str = "target_top3") -> Dict:
        csv_files = sorted(glob.glob(os.path.join(DATA_DIR, "result_*.csv")))
        if not csv_files:
            raise ValueError("学習対象の result_*.csv が data フォルダにありません")
        df = pd.concat([pd.read_csv(path) for path in csv_files], ignore_index=True)
        logger.info("学習データ読込件数: %s", len(df))
        return self.trainer.train(df, target_col=target_col)

    def predict_from_saved_entry(self, date: str, model_path: str) -> Dict:
        entry_path = os.path.join(DATA_DIR, f"entry_{date}.csv")
        if not os.path.exists(entry_path):
            self.collect_entry_by_date(date)
        df = pd.read_csv(entry_path)
        pred_df = self.predictor.predict(model_path, df)
        output_path = os.path.join(DATA_DIR, f"predict_{date}.csv")
        pred_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info("予測保存: %s", output_path)
        return {"csv": output_path, "rows": len(pred_df)}
