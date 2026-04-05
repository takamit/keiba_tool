from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from core.controller import Controller


class AppGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("競馬予想ツール")
        self.root.geometry("900x650")

        self.controller = Controller()

        self.fetch_date_var = tk.StringVar()
        self.result_dates_var = tk.StringVar()
        self.predict_date_var = tk.StringVar()
        self.model_path_var = tk.StringVar()
        self.target_var = tk.StringVar(value="target_top3")

        self._build_layout()

    def _build_layout(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        fetch_tab = ttk.Frame(notebook)
        train_tab = ttk.Frame(notebook)
        predict_tab = ttk.Frame(notebook)

        notebook.add(fetch_tab, text="1. データ取得")
        notebook.add(train_tab, text="2. 学習")
        notebook.add(predict_tab, text="3. 予測")

        self._build_fetch_tab(fetch_tab)
        self._build_train_tab(train_tab)
        self._build_predict_tab(predict_tab)

        log_frame = ttk.LabelFrame(self.root, text="実行ログ")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, wrap="word", height=14)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_fetch_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="単日取得日付 (YYYYMMDD)").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.fetch_date_var, width=20).grid(row=0, column=1, sticky="w")

        ttk.Button(frame, text="出走表を取得", command=self.fetch_entry).grid(row=1, column=0, pady=8, sticky="w")
        ttk.Button(frame, text="結果を取得", command=self.fetch_result).grid(row=1, column=1, pady=8, sticky="w")

        ttk.Separator(frame).grid(row=2, column=0, columnspan=3, sticky="ew", pady=15)

        ttk.Label(frame, text="学習用の過去日付一覧（カンマ区切り）").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.result_dates_var, width=60).grid(row=3, column=1, columnspan=2, sticky="ew")
        ttk.Button(frame, text="複数日の結果をまとめて取得", command=self.fetch_multi_results).grid(row=4, column=0, columnspan=2, sticky="w", pady=8)

        frame.columnconfigure(2, weight=1)

    def _build_train_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="学習ターゲット").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(
            frame,
            textvariable=self.target_var,
            values=["target_top3", "target_win"],
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(frame, text="data/result_*.csv を自動で連結して学習します").grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(frame, text="学習開始", command=self.train_model).grid(row=2, column=0, sticky="w", pady=8)

    def _build_predict_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="予測日付 (YYYYMMDD)").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.predict_date_var, width=20).grid(row=0, column=1, sticky="w")

        ttk.Label(frame, text="学習済みモデルのパス").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.model_path_var, width=70).grid(row=1, column=1, sticky="ew")

        ttk.Button(frame, text="予測CSVを出力", command=self.predict).grid(row=2, column=0, sticky="w", pady=8)
        ttk.Label(frame, text="空なら models/keiba_model_target_top3.joblib を使います").grid(row=2, column=1, sticky="w")

        frame.columnconfigure(1, weight=1)

    def _validate_date(self, value: str) -> str:
        value = value.strip()
        if len(value) != 8 or not value.isdigit():
            raise ValueError("日付は YYYYMMDD の8桁で入力してください")
        return value

    def _append_log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def fetch_entry(self):
        date = self._validate_date(self.fetch_date_var.get())
        result = self.controller.collect_entry_by_date(date)
        self._append_log(f"出走表取得完了: {date} -> {result['csv']}")
        messagebox.showinfo("完了", f"出走表を保存しました\n{result['csv']}")

    def fetch_result(self):
        date = self._validate_date(self.fetch_date_var.get())
        result = self.controller.collect_result_by_date(date)
        self._append_log(f"結果取得完了: {date} -> {result['csv']}")
        messagebox.showinfo("完了", f"結果を保存しました\n{result['csv']}")

    def fetch_multi_results(self):
        raw = self.result_dates_var.get().strip()
        dates = [self._validate_date(x) for x in raw.split(",") if x.strip()]
        if not dates:
            raise ValueError("日付を1件以上入力してください")
        outputs = self.controller.collect_results_by_dates(dates)
        self._append_log(f"複数日結果取得完了: {len(outputs)}日")
        messagebox.showinfo("完了", f"{len(outputs)}日分の結果CSVを保存しました")

    def train_model(self):
        result = self.controller.train_from_saved_results(target_col=self.target_var.get())
        self.model_path_var.set(result["model_path"])
        self._append_log(f"学習完了: accuracy={result['accuracy']:.4f}")
        self._append_log(result["report"])
        messagebox.showinfo("学習完了", f"モデル保存先\n{result['model_path']}")

    def predict(self):
        date = self._validate_date(self.predict_date_var.get())
        model_path = self.model_path_var.get().strip() or os.path.join("models", "keiba_model_target_top3.joblib")
        result = self.controller.predict_from_saved_entry(date, model_path)
        self._append_log(f"予測完了: {date} -> {result['csv']}")
        messagebox.showinfo("予測完了", f"予測CSVを保存しました\n{result['csv']}")

    def run(self):
        try:
            self.root.mainloop()
        except Exception as exc:
            messagebox.showerror("エラー", str(exc))
            raise
