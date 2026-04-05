import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from config import (
    APP_TITLE,
    DATA_DIR,
    MODEL_DIR,
    CACHE_DIR,
    LOG_DIR,
    ENTRY_FILE_PATTERN,
    RESULT_FILE_PATTERN,
    PREDICT_FILE_PATTERN,
)
from core import collector, dataset, parser
from ml import predictor, trainer


class AppGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x760")

        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(MODEL_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.collect_tab = ttk.Frame(notebook)
        self.train_tab = ttk.Frame(notebook)
        self.predict_tab = ttk.Frame(notebook)

        notebook.add(self.collect_tab, text="データ取得")
        notebook.add(self.train_tab, text="AI学習")
        notebook.add(self.predict_tab, text="予測")

        self._build_collect_tab()
        self._build_train_tab()
        self._build_predict_tab()

    def _build_collect_tab(self):
        frame = ttk.Frame(self.collect_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="日付（YYYYMMDD またはカンマ区切り）").pack(anchor=tk.W)
        self.collect_date_entry = ttk.Entry(frame)
        self.collect_date_entry.pack(fill=tk.X, pady=5)

        ttk.Button(
            frame,
            text="出走＋結果取得",
            command=lambda: self._run_in_thread(self.run_collect)
        ).pack(pady=10)

        self.collect_log = tk.Text(frame, height=30)
        self.collect_log.pack(fill=tk.BOTH, expand=True)

    def _build_train_tab(self):
        frame = ttk.Frame(self.train_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="学習元フォルダ（result_*.csv）").pack(anchor=tk.W)
        self.train_data_dir_entry = ttk.Entry(frame)
        self.train_data_dir_entry.insert(0, DATA_DIR)
        self.train_data_dir_entry.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text="モデル保存先フォルダ").pack(anchor=tk.W)
        self.model_dir_entry = ttk.Entry(frame)
        self.model_dir_entry.insert(0, MODEL_DIR)
        self.model_dir_entry.pack(fill=tk.X, pady=5)

        ttk.Button(
            frame,
            text="AI学習開始（複数モデル）",
            command=lambda: self._run_in_thread(self.run_train)
        ).pack(pady=10)

        self.train_log = tk.Text(frame, height=28)
        self.train_log.pack(fill=tk.BOTH, expand=True)

    def _build_predict_tab(self):
        frame = ttk.Frame(self.predict_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="予測対象日（YYYYMMDD）").pack(anchor=tk.W)
        self.predict_date_entry = ttk.Entry(frame)
        self.predict_date_entry.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text="使用するモデルフォルダ").pack(anchor=tk.W)
        self.predict_model_dir_entry = ttk.Entry(frame)
        self.predict_model_dir_entry.insert(0, MODEL_DIR)
        self.predict_model_dir_entry.pack(fill=tk.X, pady=5)

        ttk.Button(
            frame,
            text="予測実行",
            command=lambda: self._run_in_thread(self.run_predict)
        ).pack(pady=10)

        self.predict_log = tk.Text(frame, height=28)
        self.predict_log.pack(fill=tk.BOTH, expand=True)

    def _run_in_thread(self, func):
        threading.Thread(target=func, daemon=True).start()

    def _log(self, widget, msg: str):
        widget.insert(tk.END, msg + "\n")
        widget.see(tk.END)
        self.update_idletasks()

    def run_collect(self):
        raw = self.collect_date_entry.get().strip()
        if not raw:
            messagebox.showerror("エラー", "日付を入力してください")
            return

        dates = [x.strip() for x in raw.split(",") if x.strip()]
        if not dates:
            messagebox.showerror("エラー", "日付を正しく入力してください")
            return

        try:
            for date in dates:
                self._log(self.collect_log, f"=== {date} 開始 ===")
                race_ids = collector.get_race_ids(date)
                self._log(self.collect_log, f"race_id数: {len(race_ids)}")

                entry_rows = []
                result_rows = []

                for race_id in race_ids:
                    entry_html = collector.fetch_race_page(race_id, mode="entry", use_cache=False)
                    entry_rows.extend(parser.parse_entry(entry_html, race_id))

                    try:
                        result_html = collector.fetch_race_page(race_id, mode="result", use_cache=False)
                        result_rows.extend(parser.parse_result(result_html, race_id))
                    except Exception:
                        pass

                if entry_rows:
                    entry_df = dataset.build_entry_df(entry_rows)
                    entry_path = os.path.join(DATA_DIR, ENTRY_FILE_PATTERN.format(date=date))
                    entry_df.to_csv(entry_path, index=False, encoding="utf-8-sig")
                    self._log(self.collect_log, f"出走表保存: {entry_path} / {len(entry_df)}件")
                else:
                    self._log(self.collect_log, "出走表データなし")

                if result_rows:
                    result_df = dataset.build_result_df(result_rows)
                    result_path = os.path.join(DATA_DIR, RESULT_FILE_PATTERN.format(date=date))
                    result_df.to_csv(result_path, index=False, encoding="utf-8-sig")
                    self._log(self.collect_log, f"結果保存: {result_path} / {len(result_df)}件")
                else:
                    self._log(self.collect_log, "結果データなし（未来日または未確定の可能性あり）")

                self._log(self.collect_log, f"=== {date} 完了 ===\n")

            messagebox.showinfo("完了", "データ取得が完了しました")
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def run_train(self):
        data_dir = self.train_data_dir_entry.get().strip() or DATA_DIR
        model_dir = self.model_dir_entry.get().strip() or MODEL_DIR

        try:
            self._log(self.train_log, "学習開始...")
            summaries = trainer.train_all_models(data_dir=data_dir, model_dir=model_dir)

            self._log(self.train_log, "=== 学習結果 ===")
            for s in summaries:
                if "error" in s:
                    self._log(self.train_log, f"[NG] {s['target_col']} : {s['error']}")
                else:
                    auc_text = "None" if s["auc"] is None else f"{s['auc']:.4f}"
                    self._log(
                        self.train_log,
                        f"[OK] {s['target_col']} | rows={s['rows']} | "
                        f"positive_rate={s['positive_rate']:.4f} | "
                        f"acc={s['accuracy']:.4f} | f1={s['f1']:.4f} | auc={auc_text}"
                    )
                    self._log(self.train_log, f"保存: {s['model_path']}")

            messagebox.showinfo("完了", "AI学習が完了しました")
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def run_predict(self):
        date = self.predict_date_entry.get().strip()
        model_dir = self.predict_model_dir_entry.get().strip() or MODEL_DIR

        if not date:
            messagebox.showerror("エラー", "予測対象日を入力してください")
            return

        try:
            self._log(self.predict_log, f"{date} の出走表取得中...")
            race_ids = collector.get_race_ids(date)
            self._log(self.predict_log, f"race_id数: {len(race_ids)}")

            entry_rows = []
            for race_id in race_ids:
                html = collector.fetch_race_page(race_id, mode="entry", use_cache=False)
                entry_rows.extend(parser.parse_entry(html, race_id))

            if not entry_rows:
                raise ValueError("出走表データを取得できませんでした")

            entry_df = dataset.build_entry_df(entry_rows)
            entry_path = os.path.join(DATA_DIR, ENTRY_FILE_PATTERN.format(date=date))
            entry_df.to_csv(entry_path, index=False, encoding="utf-8-sig")
            self._log(self.predict_log, f"出走表保存: {entry_path}")

            output_path = os.path.join(DATA_DIR, PREDICT_FILE_PATTERN.format(date=date))
            result_df = predictor.predict_from_entry(
                entry_csv_path=entry_path,
                model_dir=model_dir,
                output_path=output_path
            )

            self._log(self.predict_log, f"予測保存: {output_path}")
            self._log(self.predict_log, f"予測件数: {len(result_df)}")
            self._log(self.predict_log, "score_composite と pred_rank_in_race を確認してください")

            messagebox.showinfo("完了", "予測が完了しました")
        except Exception as e:
            messagebox.showerror("エラー", str(e))
