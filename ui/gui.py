import datetime as dt
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tkcalendar import DateEntry

from config import (
    APP_TITLE,
    CACHE_DIR,
    DATA_DIR,
    ENTRY_FILE_PATTERN,
    LOG_DIR,
    MODEL_DIR,
    PREDICT_FILE_PATTERN,
    RESULT_FILE_PATTERN,
)
from core import collector, dataset, parser
from ml import predictor, trainer


class AppGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(1080, 760)

        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(MODEL_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

        self._create_context_menu()

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

    # =========================
    # 共通UI
    # =========================
    def _create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="切り取り", command=lambda: self._event_generate_for_focus("<<Cut>>"))
        self.context_menu.add_command(label="コピー", command=lambda: self._event_generate_for_focus("<<Copy>>"))
        self.context_menu.add_command(label="貼り付け", command=lambda: self._event_generate_for_focus("<<Paste>>"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="すべて選択", command=self._select_all_for_focus)

        self.bind_all("<Control-a>", self._on_ctrl_a)
        self.bind_all("<Control-A>", self._on_ctrl_a)
        self.bind_all("<Button-3>", self._show_context_menu)

    def _event_generate_for_focus(self, sequence: str):
        widget = self.focus_get()
        if widget is not None:
            try:
                widget.event_generate(sequence)
            except Exception:
                pass

    def _select_all_for_focus(self):
        widget = self.focus_get()
        if widget is None:
            return

        try:
            if isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.selection_range(0, tk.END)
                widget.icursor(tk.END)
            elif isinstance(widget, tk.Text):
                widget.tag_add(tk.SEL, "1.0", tk.END)
                widget.mark_set(tk.INSERT, "1.0")
                widget.see(tk.INSERT)
        except Exception:
            pass

    def _on_ctrl_a(self, event):
        widget = event.widget
        try:
            if isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.selection_range(0, tk.END)
                widget.icursor(tk.END)
                return "break"
            if isinstance(widget, tk.Text):
                widget.tag_add(tk.SEL, "1.0", tk.END)
                widget.mark_set(tk.INSERT, "1.0")
                widget.see(tk.INSERT)
                return "break"
        except Exception:
            pass
        return None

    def _show_context_menu(self, event):
        widget = event.widget
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            try:
                widget.focus_set()
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()

    def _run_in_thread(self, func):
        threading.Thread(target=func, daemon=True).start()

    def _log(self, widget, msg: str):
        widget.insert(tk.END, msg + "\n")
        widget.see(tk.END)
        self.update_idletasks()

    def _browse_directory_to_entry(self, entry_widget):
        selected = filedialog.askdirectory()
        if selected:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, selected)

    def _parse_ymd(self, value: str) -> dt.date:
        return dt.datetime.strptime(value, "%Y%m%d").date()

    def _date_to_str(self, value: dt.date) -> str:
        return value.strftime("%Y%m%d")

    def _daterange(self, start_date: dt.date, end_date: dt.date):
        current = start_date
        while current <= end_date:
            yield current
            current += dt.timedelta(days=1)

    def _resolve_single_or_range_dates(self, mode: str, single_widget, start_widget, end_widget):
        if mode == "single":
            value = single_widget.get_date()
            return [self._date_to_str(value)]

        start_date = start_widget.get_date()
        end_date = end_widget.get_date()

        if start_date > end_date:
            raise ValueError("開始日は終了日以前にしてください")

        return [self._date_to_str(d) for d in self._daterange(start_date, end_date)]

    def _filter_dates_with_races(self, date_list, log_widget, log_prefix: str):
        valid_dates = []
        for date in date_list:
            try:
                race_ids = collector.get_race_ids(date)
                if race_ids:
                    valid_dates.append((date, race_ids))
                    self._log(log_widget, f"{log_prefix} {date}: 開催あり / race_id数={len(race_ids)}")
            except Exception:
                self._log(log_widget, f"{log_prefix} {date}: 開催なしのためスキップ")
        return valid_dates

    def _set_collect_mode(self):
        mode = self.collect_mode_var.get()
        if mode == "single":
            self.collect_single_frame.pack(fill=tk.X, pady=(0, 8))
            self.collect_range_frame.pack_forget()
        else:
            self.collect_single_frame.pack_forget()
            self.collect_range_frame.pack(fill=tk.X, pady=(0, 8))

    def _set_predict_mode(self):
        mode = self.predict_mode_var.get()
        if mode == "single":
            self.predict_single_frame.pack(fill=tk.X, pady=(0, 8))
            self.predict_range_frame.pack_forget()
        else:
            self.predict_single_frame.pack_forget()
            self.predict_range_frame.pack(fill=tk.X, pady=(0, 8))

    # =========================
    # データ取得タブ
    # =========================
    def _build_collect_tab(self):
        frame = ttk.Frame(self.collect_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        mode_frame = ttk.LabelFrame(frame, text="取得日指定", padding=10)
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        self.collect_mode_var = tk.StringVar(value="single")

        mode_select_frame = ttk.Frame(mode_frame)
        mode_select_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Radiobutton(
            mode_select_frame,
            text="単日指定",
            variable=self.collect_mode_var,
            value="single",
            command=self._set_collect_mode,
        ).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Radiobutton(
            mode_select_frame,
            text="期間指定",
            variable=self.collect_mode_var,
            value="range",
            command=self._set_collect_mode,
        ).pack(side=tk.LEFT)

        today = dt.date.today()

        self.collect_single_frame = ttk.Frame(mode_frame)
        ttk.Label(self.collect_single_frame, text="開催日").pack(anchor=tk.W)
        self.collect_date_picker = DateEntry(
            self.collect_single_frame,
            date_pattern="yyyy-mm-dd",
            locale="ja_JP",
            width=18,
        )
        self.collect_date_picker.set_date(today)
        self.collect_date_picker.pack(anchor=tk.W, pady=(4, 0))

        self.collect_range_frame = ttk.Frame(mode_frame)
        range_row = ttk.Frame(self.collect_range_frame)
        range_row.pack(fill=tk.X)

        left = ttk.Frame(range_row)
        left.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(left, text="開始日").pack(anchor=tk.W)
        self.collect_start_picker = DateEntry(
            left,
            date_pattern="yyyy-mm-dd",
            locale="ja_JP",
            width=18,
        )
        self.collect_start_picker.set_date(today)
        self.collect_start_picker.pack(anchor=tk.W, pady=(4, 0))

        right = ttk.Frame(range_row)
        right.pack(side=tk.LEFT)
        ttk.Label(right, text="終了日").pack(anchor=tk.W)
        self.collect_end_picker = DateEntry(
            right,
            date_pattern="yyyy-mm-dd",
            locale="ja_JP",
            width=18,
        )
        self.collect_end_picker.set_date(today)
        self.collect_end_picker.pack(anchor=tk.W, pady=(4, 0))

        self._set_collect_mode()

        ttk.Button(
            frame,
            text="出走＋結果取得",
            command=lambda: self._run_in_thread(self.run_collect),
        ).pack(pady=(0, 10))

        self.collect_log = tk.Text(frame, height=30, wrap="word", undo=True)
        self.collect_log.pack(fill=tk.BOTH, expand=True)

    # =========================
    # AI学習タブ
    # =========================
    def _build_train_tab(self):
        frame = ttk.Frame(self.train_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        data_dir_frame = ttk.Frame(frame)
        data_dir_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(data_dir_frame, text="学習元フォルダ（result_*.csv）").pack(anchor=tk.W)
        data_dir_row = ttk.Frame(data_dir_frame)
        data_dir_row.pack(fill=tk.X, pady=(4, 0))

        self.train_data_dir_entry = ttk.Entry(data_dir_row)
        self.train_data_dir_entry.insert(0, DATA_DIR)
        self.train_data_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(
            data_dir_row,
            text="参照",
            command=lambda: self._browse_directory_to_entry(self.train_data_dir_entry),
            width=10,
        ).pack(side=tk.LEFT, padx=(8, 0))

        model_dir_frame = ttk.Frame(frame)
        model_dir_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(model_dir_frame, text="モデル保存先フォルダ").pack(anchor=tk.W)
        model_dir_row = ttk.Frame(model_dir_frame)
        model_dir_row.pack(fill=tk.X, pady=(4, 0))

        self.model_dir_entry = ttk.Entry(model_dir_row)
        self.model_dir_entry.insert(0, MODEL_DIR)
        self.model_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(
            model_dir_row,
            text="参照",
            command=lambda: self._browse_directory_to_entry(self.model_dir_entry),
            width=10,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            frame,
            text="AI学習開始（複数モデル）",
            command=lambda: self._run_in_thread(self.run_train),
        ).pack(pady=10)

        self.train_log = tk.Text(frame, height=28, wrap="word", undo=True)
        self.train_log.pack(fill=tk.BOTH, expand=True)

    # =========================
    # 予測タブ
    # =========================
    def _build_predict_tab(self):
        frame = ttk.Frame(self.predict_tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        mode_frame = ttk.LabelFrame(frame, text="予測対象日指定", padding=10)
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        self.predict_mode_var = tk.StringVar(value="single")

        mode_select_frame = ttk.Frame(mode_frame)
        mode_select_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Radiobutton(
            mode_select_frame,
            text="単日指定",
            variable=self.predict_mode_var,
            value="single",
            command=self._set_predict_mode,
        ).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Radiobutton(
            mode_select_frame,
            text="期間指定",
            variable=self.predict_mode_var,
            value="range",
            command=self._set_predict_mode,
        ).pack(side=tk.LEFT)

        today = dt.date.today()

        self.predict_single_frame = ttk.Frame(mode_frame)
        ttk.Label(self.predict_single_frame, text="開催予定日").pack(anchor=tk.W)
        self.predict_date_picker = DateEntry(
            self.predict_single_frame,
            date_pattern="yyyy-mm-dd",
            locale="ja_JP",
            width=18,
        )
        self.predict_date_picker.set_date(today)
        self.predict_date_picker.pack(anchor=tk.W, pady=(4, 0))

        self.predict_range_frame = ttk.Frame(mode_frame)
        range_row = ttk.Frame(self.predict_range_frame)
        range_row.pack(fill=tk.X)

        left = ttk.Frame(range_row)
        left.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(left, text="開始日").pack(anchor=tk.W)
        self.predict_start_picker = DateEntry(
            left,
            date_pattern="yyyy-mm-dd",
            locale="ja_JP",
            width=18,
        )
        self.predict_start_picker.set_date(today)
        self.predict_start_picker.pack(anchor=tk.W, pady=(4, 0))

        right = ttk.Frame(range_row)
        right.pack(side=tk.LEFT)
        ttk.Label(right, text="終了日").pack(anchor=tk.W)
        self.predict_end_picker = DateEntry(
            right,
            date_pattern="yyyy-mm-dd",
            locale="ja_JP",
            width=18,
        )
        self.predict_end_picker.set_date(today)
        self.predict_end_picker.pack(anchor=tk.W, pady=(4, 0))

        self._set_predict_mode()

        model_dir_frame = ttk.Frame(frame)
        model_dir_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(model_dir_frame, text="使用するモデルフォルダ").pack(anchor=tk.W)
        model_dir_row = ttk.Frame(model_dir_frame)
        model_dir_row.pack(fill=tk.X, pady=(4, 0))

        self.predict_model_dir_entry = ttk.Entry(model_dir_row)
        self.predict_model_dir_entry.insert(0, MODEL_DIR)
        self.predict_model_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(
            model_dir_row,
            text="参照",
            command=lambda: self._browse_directory_to_entry(self.predict_model_dir_entry),
            width=10,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            frame,
            text="予測実行",
            command=lambda: self._run_in_thread(self.run_predict),
        ).pack(pady=10)

        self.predict_log = tk.Text(frame, height=28, wrap="word", undo=True)
        self.predict_log.pack(fill=tk.BOTH, expand=True)

    # =========================
    # 実処理
    # =========================
    def run_collect(self):
        try:
            self._log(self.collect_log, "開催日判定中...")
            requested_dates = self._resolve_single_or_range_dates(
                mode=self.collect_mode_var.get(),
                single_widget=self.collect_date_picker,
                start_widget=self.collect_start_picker,
                end_widget=self.collect_end_picker,
            )

            valid_dates = self._filter_dates_with_races(
                requested_dates,
                log_widget=self.collect_log,
                log_prefix="[開催判定]",
            )

            if not valid_dates:
                raise ValueError("指定範囲に開催日がありませんでした")

            for date, race_ids in valid_dates:
                self._log(self.collect_log, f"=== {date} 開始 ===")
                self._log(self.collect_log, f"race_id数: {len(race_ids)}")

                entry_rows = []
                result_rows = []

                for race_id in race_ids:
                    entry_html = collector.fetch_race_page(race_id, mode="entry", use_cache=False)
                    entry_rows.extend(parser.parse_entry(entry_html, race_id))

                    try:
                        result_html = collector.fetch_race_page(race_id, mode="result", use_cache=False)
                        result_rows.extend(parser.parse_result(result_html, race_id))
                    except Exception as ex:
                        self._log(self.collect_log, f"[INFO] result未取得: race_id={race_id} / {ex}")

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
        model_dir = self.predict_model_dir_entry.get().strip() or MODEL_DIR

        try:
            self._log(self.predict_log, "開催日判定中...")
            requested_dates = self._resolve_single_or_range_dates(
                mode=self.predict_mode_var.get(),
                single_widget=self.predict_date_picker,
                start_widget=self.predict_start_picker,
                end_widget=self.predict_end_picker,
            )

            valid_dates = self._filter_dates_with_races(
                requested_dates,
                log_widget=self.predict_log,
                log_prefix="[開催判定]",
            )

            if not valid_dates:
                raise ValueError("指定範囲に開催予定日がありませんでした")

            for date, race_ids in valid_dates:
                self._log(self.predict_log, f"=== {date} 予測開始 ===")
                self._log(self.predict_log, f"race_id数: {len(race_ids)}")

                entry_rows = []
                for race_id in race_ids:
                    html = collector.fetch_race_page(race_id, mode="entry", use_cache=False)
                    entry_rows.extend(parser.parse_entry(html, race_id))

                if not entry_rows:
                    self._log(self.predict_log, f"{date}: 出走表データを取得できませんでした")
                    continue

                entry_df = dataset.build_entry_df(entry_rows)
                entry_path = os.path.join(DATA_DIR, ENTRY_FILE_PATTERN.format(date=date))
                entry_df.to_csv(entry_path, index=False, encoding="utf-8-sig")
                self._log(self.predict_log, f"出走表保存: {entry_path}")

                output_path = os.path.join(DATA_DIR, PREDICT_FILE_PATTERN.format(date=date))
                result_df = predictor.predict_from_entry(
                    entry_csv_path=entry_path,
                    model_dir=model_dir,
                    output_path=output_path,
                )

                self._log(self.predict_log, f"予測保存: {output_path}")
                self._log(self.predict_log, f"予測件数: {len(result_df)}")
                self._log(self.predict_log, "score_composite と pred_rank_in_race を確認してください")
                self._log(self.predict_log, f"=== {date} 予測完了 ===\n")

            messagebox.showinfo("完了", "予測が完了しました")
        except Exception as e:
            messagebox.showerror("エラー", str(e))