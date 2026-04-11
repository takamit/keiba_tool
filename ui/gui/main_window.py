
import calendar
import datetime as dt
import glob
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import pandas as pd

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
from core.services.batch_collect_service import resolve_holding_dates
from ml import predictor, trainer


class OperationCancelled(Exception):
    pass




def create_text_checkbox(parent, text, variable, bg="#ffffff", fg="#0f172a", font=("Yu Gothic UI", 10), command=None):
    frame = tk.Frame(parent, bg=bg, highlightthickness=0, bd=0)
    label = tk.Label(
        frame,
        text="",
        bg=bg,
        fg=fg,
        font=font,
        cursor="hand2",
        anchor="w",
        justify="left",
        padx=2,
        pady=2,
    )
    label.pack(fill=tk.X, expand=True)

    def update(*_args):
        label.config(text=("☑ " if bool(variable.get()) else "☐ ") + text)

    def toggle(event=None):
        variable.set(not bool(variable.get()))
        update()
        if command:
            command()

    label.bind("<Button-1>", toggle)
    frame.bind("<Button-1>", toggle)
    variable.trace_add("write", update)
    update()
    return frame


class CalendarPopup(tk.Toplevel):
    def __init__(self, master, anchor_widget, initial_date, on_select):
        super().__init__(master)
        self.anchor_widget = anchor_widget
        self.on_select = on_select
        self.current_year = initial_date.year
        self.current_month = initial_date.month
        self.selected_date = initial_date
        self.today = dt.date.today()

        self.withdraw()
        self.transient(master)
        self.resizable(False, False)
        self.title("日付選択")
        self.configure(bg="#dbe7f7")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda e: self.destroy())

        self._build_ui()
        self._render_calendar()
        self._place_near_anchor()

        self.deiconify()
        self.grab_set()
        self.focus_force()

    def _build_ui(self):
        shell = tk.Frame(self, bg="#dbe7f7", padx=1, pady=1)
        shell.pack(fill=tk.BOTH, expand=True)

        outer = ttk.Frame(shell, padding=14, style="CalendarCard.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer, style="CalendarCard.TFrame")
        header.pack(fill=tk.X, pady=(0, 10))

        nav = ttk.Frame(header, style="CalendarCard.TFrame")
        nav.pack(fill=tk.X)

        left_nav = ttk.Frame(nav, style="CalendarCard.TFrame")
        left_nav.pack(side=tk.LEFT)
        ttk.Button(left_nav, text="−年", width=5, style="CalendarNav.TButton", command=self._prev_year).pack(side=tk.LEFT)
        ttk.Button(left_nav, text="−月", width=5, style="CalendarNav.TButton", command=self._prev_month).pack(side=tk.LEFT, padx=(6, 0))

        center = ttk.Frame(nav, style="CalendarCard.TFrame")
        center.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)
        self.month_label = ttk.Label(center, text="", anchor="center", style="CalendarTitle.TLabel")
        self.month_label.pack(fill=tk.X)
        self.sub_label = ttk.Label(center, text="", anchor="center", style="CalendarMeta.TLabel")
        self.sub_label.pack(fill=tk.X, pady=(2, 0))

        right_nav = ttk.Frame(nav, style="CalendarCard.TFrame")
        right_nav.pack(side=tk.RIGHT)
        ttk.Button(right_nav, text="＋月", width=5, style="CalendarNav.TButton", command=self._next_month).pack(side=tk.LEFT)
        ttk.Button(right_nav, text="＋年", width=5, style="CalendarNav.TButton", command=self._next_year).pack(side=tk.LEFT, padx=(6, 0))

        info_row = ttk.Frame(outer, style="CalendarInfo.TFrame")
        info_row.pack(fill=tk.X, pady=(0, 10))
        self.selected_chip = ttk.Label(info_row, text="", style="CalendarChip.TLabel")
        self.selected_chip.pack(side=tk.LEFT)
        ttk.Label(info_row, text="土日は色分け、今日と選択日は強調表示", style="CalendarMeta.TLabel").pack(side=tk.RIGHT)

        weekday_bar = ttk.Frame(outer, style="CalendarCard.TFrame")
        weekday_bar.pack(fill=tk.X, pady=(0, 6))
        headers = ["月", "火", "水", "木", "金", "土", "日"]
        styles = [
            "CalendarWeekday.TLabel",
            "CalendarWeekday.TLabel",
            "CalendarWeekday.TLabel",
            "CalendarWeekday.TLabel",
            "CalendarWeekday.TLabel",
            "CalendarSaturday.TLabel",
            "CalendarSunday.TLabel",
        ]
        for col, (text, style_name) in enumerate(zip(headers, styles)):
            lbl = ttk.Label(weekday_bar, text=text, anchor="center", style=style_name)
            lbl.grid(row=0, column=col, padx=2, pady=0, sticky="nsew")
            weekday_bar.grid_columnconfigure(col, weight=1, uniform="calendar_weekday")

        self.grid_frame = ttk.Frame(outer, style="CalendarCard.TFrame")
        self.grid_frame.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(outer, style="CalendarCard.TFrame")
        footer.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(footer, text="今日を選択", style="Secondary.TButton", command=self._pick_today).pack(side=tk.LEFT)
        ttk.Button(footer, text="選択日に戻す", style="Secondary.TButton", command=self._pick_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text="閉じる", style="CalendarGhost.TButton", command=self.destroy).pack(side=tk.RIGHT)

    def _place_near_anchor(self):
        self.update_idletasks()
        anchor_x = self.anchor_widget.winfo_rootx()
        anchor_y = self.anchor_widget.winfo_rooty()
        anchor_h = self.anchor_widget.winfo_height()

        req_w = self.winfo_reqwidth()
        req_h = self.winfo_reqheight()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        x = anchor_x
        y = anchor_y + anchor_h + 8

        if x + req_w > screen_w - 12:
            x = max(12, screen_w - req_w - 12)
        if y + req_h > screen_h - 56:
            y = max(12, anchor_y - req_h - 8)

        self.geometry(f"+{x}+{y}")

    def _render_calendar(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()

        self.month_label.configure(text=f"{self.current_year:04d}年 {self.current_month:02d}月")
        self.sub_label.configure(text=f"選択中: {self.selected_date.strftime('%Y-%m-%d')}")
        self.selected_chip.configure(text=f"{self.selected_date.strftime('%m/%d')} を選択")

        month_matrix = calendar.Calendar(firstweekday=0).monthdayscalendar(self.current_year, self.current_month)

        for row_index, week in enumerate(month_matrix):
            week_frame = ttk.Frame(self.grid_frame, style="CalendarCard.TFrame")
            week_frame.grid(row=row_index, column=0, sticky="ew", pady=2)
            self.grid_frame.grid_columnconfigure(0, weight=1)
            for col_index, day in enumerate(week):
                week_frame.grid_columnconfigure(col_index, weight=1, uniform="calendar_day")
                if day == 0:
                    spacer = ttk.Label(week_frame, text="", style="CalendarBlank.TLabel")
                    spacer.grid(row=0, column=col_index, padx=2, sticky="nsew")
                    continue

                day_date = dt.date(self.current_year, self.current_month, day)
                is_today = day_date == self.today
                is_selected = day_date == self.selected_date
                is_saturday = col_index == 5
                is_sunday = col_index == 6

                day_style = "CalendarDay.TButton"
                if is_saturday:
                    day_style = "CalendarSaturday.TButton"
                if is_sunday:
                    day_style = "CalendarSunday.TButton"
                if is_today:
                    day_style = "CalendarToday.TButton"
                if is_selected:
                    day_style = "CalendarSelected.TButton"

                button = ttk.Button(
                    week_frame,
                    text=str(day),
                    style=day_style,
                    command=lambda d=day: self._select_day(d),
                )
                button.grid(row=0, column=col_index, padx=2, sticky="nsew", ipady=6)

        for row in range(len(month_matrix)):
            self.grid_frame.grid_rowconfigure(row, weight=1)

    def _select_day(self, day):
        selected = dt.date(self.current_year, self.current_month, day)
        self.selected_date = selected
        self.on_select(selected)
        self.destroy()

    def _pick_today(self):
        self.selected_date = dt.date.today()
        self.on_select(self.selected_date)
        self.destroy()

    def _pick_selected(self):
        self.on_select(self.selected_date)
        self.destroy()

    def _prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._render_calendar()

    def _next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._render_calendar()

    def _prev_year(self):
        self.current_year -= 1
        self._render_calendar()

    def _next_year(self):
        self.current_year += 1
        self._render_calendar()


class PropertiesDialog(tk.Toplevel):
    def __init__(self, master, on_save):
        super().__init__(master)
        self._on_save = on_save
        self.title("プロパティ")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.configure(bg="#f3f6fb")

        self.cache_enabled_var = tk.BooleanVar(value=collector.is_html_cache_enabled())

        count, total_bytes = collector.get_html_cache_summary()
        size_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0

        outer = ttk.Frame(self, padding=14, style="Card.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="HTMLキャッシュ設定", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="取得時に保存するHTMLキャッシュの利用有無を切り替えます。保存設定は config.py に反映されます。",
            style="Muted.TLabel",
            wraplength=420,
        ).pack(anchor=tk.W, pady=(4, 10))

        create_text_checkbox(
            outer,
            "HTMLキャッシュを有効にする",
            self.cache_enabled_var,
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor=tk.W)

        info = ttk.Frame(outer, style="Card.TFrame")
        info.pack(fill=tk.X, pady=(12, 10))
        ttk.Label(info, text=f"現在のHTMLファイル数: {count}", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Label(info, text=f"現在の合計サイズ: {size_mb:.2f} MB", style="Muted.TLabel").pack(anchor=tk.W, pady=(4, 0))

        btns = ttk.Frame(outer, style="Card.TFrame")
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns, text="保存", style="Primary.TButton", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="閉じる", style="Secondary.TButton", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _save(self):
        self._on_save(self.cache_enabled_var.get())
        self.destroy()


class AppGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1240x860")
        self.minsize(1120, 760)
        self.configure(bg="#eef2f8")

        self.data_dir_abs = os.path.abspath(DATA_DIR)
        self.model_dir_abs = os.path.abspath(MODEL_DIR)
        self.cache_dir_abs = os.path.abspath(CACHE_DIR)
        self.log_dir_abs = os.path.abspath(LOG_DIR)

        for path in [self.data_dir_abs, self.model_dir_abs, self.cache_dir_abs, self.log_dir_abs]:
            os.makedirs(path, exist_ok=True)

        self.ui_queue = queue.Queue()
        self.current_operation = None
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.operation_widgets = {}
        self.operation_logs = {}
        self.colors = {
            "bg": "#eef2f8",
            "card": "#ffffff",
            "primary": "#2563eb",
            "primary_active": "#1d4ed8",
            "accent": "#0f172a",
            "muted": "#64748b",
            "soft": "#f8fafc",
        }

        self._apply_styles()
        self._create_context_menu()
        self._create_menu_bar()
        self._build_layout()

        self.after_idle(self.focus_set)
        self.after(100, self._process_ui_queue)
        self.after(1200, self._maybe_start_self_learning)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- style / menu ----------
    def _apply_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = "#eef2f8"
        card = "#ffffff"
        primary = "#2563eb"
        primary_active = "#1d4ed8"
        accent = "#0f172a"
        muted = "#64748b"
        soft = "#f8fafc"

        style.configure("App.TFrame", background=bg)
        style.configure("Card.TFrame", background=card)
        style.configure("Header.TFrame", background=card)
        style.configure("HeroTitle.TLabel", background=card, foreground=accent, font=("Yu Gothic UI", 18, "bold"))
        style.configure("HeroSub.TLabel", background=card, foreground=muted, font=("Yu Gothic UI", 10))
        style.configure("Section.TLabelframe", background=card, borderwidth=1, relief="solid")
        style.configure("Section.TLabelframe.Label", background=card, foreground=accent, font=("Yu Gothic UI", 11, "bold"))
        style.configure("SectionTitle.TLabel", background=card, foreground=accent, font=("Yu Gothic UI", 10, "bold"))
        style.configure("CalendarCard.TFrame", background="#f8fbff")
        style.configure("CalendarInfo.TFrame", background="#eef5ff")
        style.configure("CalendarTitle.TLabel", background="#f8fbff", foreground=accent, font=("Yu Gothic UI", 13, "bold"))
        style.configure("CalendarMeta.TLabel", background="#f8fbff", foreground=muted, font=("Yu Gothic UI", 8))
        style.configure("CalendarChip.TLabel", background="#dbeafe", foreground="#1d4ed8", font=("Yu Gothic UI", 8, "bold"), padding=(10, 4))
        style.configure("Muted.TLabel", background=card, foreground=muted, font=("Yu Gothic UI", 9))
        style.configure("LogToolbar.TFrame", background=card)
        style.configure("LogHint.TLabel", background=card, foreground=muted, font=("Yu Gothic UI", 8))
        style.configure("LogAction.TButton", background="#edf2f7", foreground=accent, padding=(8, 5), font=("Yu Gothic UI", 8, "bold"))
        style.map("LogAction.TButton", background=[("active", "#dbe4f0")])
        style.configure("FieldHelp.TLabel", background=card, foreground=muted, font=("Yu Gothic UI", 8))
        style.configure("Value.TLabel", background=card, foreground=accent, font=("Consolas", 10))
        style.configure("TLabel", background=card, foreground=accent)
        style.configure("TRadiobutton", background=card, foreground=accent)
        style.configure("TCheckbutton", background=card, foreground=accent, indicatorcolor=primary, indicatormargin=2, padding=4)
        style.configure("TEntry", fieldbackground=soft, padding=7)
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Yu Gothic UI", 10, "bold"))
        style.configure("Primary.TButton", background=primary, foreground="#ffffff", padding=(14, 8))
        style.map("Primary.TButton", background=[("active", primary_active), ("disabled", "#93c5fd")])
        style.configure("Secondary.TButton", background="#e2e8f0", foreground=accent, padding=(12, 8))
        style.map("Secondary.TButton", background=[("active", "#cbd5e1")])
        style.configure("Nav.TButton", background="#e2e8f0", foreground=accent, padding=(10, 7), font=("Yu Gothic UI", 9, "bold"))
        style.map("Nav.TButton", background=[("active", "#cbd5e1")])
        style.configure("CalendarNav.TButton", background="#eff6ff", foreground="#1d4ed8", padding=(10, 7), font=("Yu Gothic UI", 9, "bold"), borderwidth=0)
        style.map("CalendarNav.TButton", background=[("active", "#dbeafe")], foreground=[("active", "#1d4ed8")])
        style.configure("CalendarGhost.TButton", background="#f8fafc", foreground=accent, padding=(12, 8), borderwidth=0)
        style.map("CalendarGhost.TButton", background=[("active", "#e2e8f0")])
        style.configure("Quick.TButton", background="#f1f5f9", foreground=accent, padding=(10, 6))
        style.map("Quick.TButton", background=[("active", "#e2e8f0")])
        style.configure("Danger.TButton", background="#ef4444", foreground="#ffffff", padding=(12, 8))
        style.map("Danger.TButton", background=[("active", "#dc2626"), ("disabled", "#fca5a5")])
        style.configure("CalendarBlank.TLabel", background="#f8fbff")
        style.configure("CalendarWeekday.TLabel", background="#f8fbff", foreground=muted, font=("Yu Gothic UI", 9, "bold"), padding=(0, 2))
        style.configure("CalendarSaturday.TLabel", background="#f8fbff", foreground="#2563eb", font=("Yu Gothic UI", 9, "bold"), padding=(0, 2))
        style.configure("CalendarSunday.TLabel", background="#f8fbff", foreground="#e11d48", font=("Yu Gothic UI", 9, "bold"), padding=(0, 2))
        style.configure("CalendarDay.TButton", background="#ffffff", foreground=accent, padding=(8, 7), font=("Yu Gothic UI", 9), borderwidth=0)
        style.map("CalendarDay.TButton", background=[("active", "#eff6ff")], foreground=[("active", accent)])
        style.configure("CalendarSaturday.TButton", background="#f8fbff", foreground="#2563eb", padding=(8, 7), font=("Yu Gothic UI", 9), borderwidth=0)
        style.map("CalendarSaturday.TButton", background=[("active", "#dbeafe")], foreground=[("active", "#1d4ed8")])
        style.configure("CalendarSunday.TButton", background="#fff1f2", foreground="#e11d48", padding=(8, 7), font=("Yu Gothic UI", 9), borderwidth=0)
        style.map("CalendarSunday.TButton", background=[("active", "#ffe4e6")], foreground=[("active", "#be123c")])
        style.configure("CalendarToday.TButton", background="#dbeafe", foreground="#1d4ed8", padding=(8, 7), font=("Yu Gothic UI", 9, "bold"), borderwidth=0)
        style.map("CalendarToday.TButton", background=[("active", "#bfdbfe")])
        style.configure("CalendarSelected.TButton", background=primary, foreground="#ffffff", padding=(8, 7), font=("Yu Gothic UI", 9, "bold"), borderwidth=0)
        style.map("CalendarSelected.TButton", background=[("active", primary_active)])
        style.configure("Treeview", rowheight=24, fieldbackground="#ffffff", background="#ffffff", foreground=accent)
        style.configure("Treeview.Heading", font=("Yu Gothic UI", 9, "bold"))
        style.configure(
            "TProgressbar",
            thickness=16,
            background=primary,
            troughcolor="#dbe4f0",
            bordercolor="#dbe4f0",
            lightcolor=primary,
            darkcolor=primary,
        )



    def _create_menu_bar(self):
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="データフォルダを開く", command=lambda: self._open_path(self.data_dir_abs))
        file_menu.add_command(label="モデルフォルダを開く", command=lambda: self._open_path(self.model_dir_abs))
        file_menu.add_command(label="キャッシュフォルダを開く", command=lambda: self._open_path(self.cache_dir_abs))
        file_menu.add_command(label="ログフォルダを開く", command=lambda: self._open_path(self.log_dir_abs))
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self._on_close)
        menu_bar.add_cascade(label="ファイル", menu=file_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=0)
        edit_menu.add_command(label="コピー", command=self._copy_focus_selection)
        edit_menu.add_command(label="すべて選択", command=self._select_all_for_focus)
        edit_menu.add_separator()
        edit_menu.add_command(label="現在タブのログを消去", command=self._clear_current_log)
        menu_bar.add_cascade(label="編集", menu=edit_menu)

        run_menu = tk.Menu(menu_bar, tearoff=0)
        run_menu.add_command(label="データ取得を実行", command=self._start_collect)
        run_menu.add_command(label="AI学習を実行", command=self._start_train)
        run_menu.add_command(label="予測を実行", command=self._start_predict)
        run_menu.add_separator()
        run_menu.add_command(label="一時停止 / 再開", command=self._toggle_pause_current)
        run_menu.add_command(label="停止", command=self._stop_current_operation)
        menu_bar.add_cascade(label="実行", menu=run_menu)

        tools_menu = tk.Menu(menu_bar, tearoff=0)
        tools_menu.add_command(label="プロパティ", command=self._open_properties_dialog)
        tools_menu.add_command(label="HTMLキャッシュを削除", command=self._clear_html_cache_from_menu)
        tools_menu.add_separator()
        tools_menu.add_command(label="データ取得タブへ移動", command=lambda: self.notebook.select(self.collect_tab))
        tools_menu.add_command(label="AI学習タブへ移動", command=lambda: self.notebook.select(self.train_tab))
        tools_menu.add_command(label="予測タブへ移動", command=lambda: self.notebook.select(self.predict_tab))
        menu_bar.add_cascade(label="ツール", menu=tools_menu)

        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="使い方", command=self._show_help)
        help_menu.add_command(label="このツールについて", command=self._show_about)
        menu_bar.add_cascade(label="ヘルプ", menu=help_menu)

        self.config(menu=menu_bar)

    def _show_help(self):
        messagebox.showinfo(
            "使い方",
            "データ取得: 単日または期間を選ぶと、その範囲の開催日だけを取得します。\n"
            "AI学習: result_*.csv を含むフォルダを指定して複数モデルを学習します。\n"
            "予測: 未来日のみを対象に、開催予定日の予測を行います。\n"
            "プロパティからHTMLキャッシュの保存有無を切り替えられます。"
        )

    def _show_about(self):
        enabled = "ON" if collector.is_html_cache_enabled() else "OFF"
        messagebox.showinfo("このツールについて", f"{APP_TITLE}\nHTMLキャッシュ: {enabled}")

    # ---------- layout ----------
    def _build_layout(self):
        root = ttk.Frame(self, padding=14, style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root, padding=16, style="Header.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text=APP_TITLE, style="HeroTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="モダンUI版 / 進捗表示・一時停止・停止・プロパティに対応",
            style="HeroSub.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        note = ttk.Label(
            header,
            text="HTMLキャッシュ: " + ("ON" if collector.is_html_cache_enabled() else "OFF"),
            style="Muted.TLabel",
        )
        note.pack(anchor=tk.W, pady=(6, 0))
        self.cache_status_note = note

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.collect_tab = ttk.Frame(self.notebook, padding=10, style="App.TFrame")
        self.train_tab = ttk.Frame(self.notebook, padding=0, style="App.TFrame")
        self.predict_tab = ttk.Frame(self.notebook, padding=0, style="App.TFrame")

        self.notebook.add(self.collect_tab, text="データ取得")
        self.notebook.add(self.train_tab, text="AI学習")
        self.notebook.add(self.predict_tab, text="予測")

        self.train_tab_body = self._create_scrollable_tab_body(self.train_tab)
        self.predict_tab_body = self._create_scrollable_tab_body(self.predict_tab)

        self._build_collect_tab()
        self._build_train_tab()
        self._build_predict_tab()


    def _create_scrollable_tab_body(self, tab_parent):
        outer = ttk.Frame(tab_parent, padding=10, style="App.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        hint = ttk.Label(
            outer,
            text="このタブ全体は縦スクロールできます。ログ欄の上ではログ自体、その他の場所ではタブ全体が動きます。",
            style="Muted.TLabel",
        )
        hint.pack(fill=tk.X, pady=(0, 6))

        canvas_wrap = ttk.Frame(outer, style="App.TFrame")
        canvas_wrap.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(
            canvas_wrap,
            bg=self.colors["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(canvas_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas, padding=(0, 0, 8, 8), style="App.TFrame")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scrollregion(_event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        def _fit_inner_width(event):
            try:
                canvas.itemconfigure(window_id, width=event.width)
            except Exception:
                pass

        inner.bind("<Configure>", _sync_scrollregion, add="+")
        canvas.bind("<Configure>", _fit_inner_width, add="+")

        def _bind_children_mousewheel(widget):
            try:
                widget.bind("<MouseWheel>", lambda e, c=canvas: self._on_tab_canvas_mousewheel(e, c), add="+")
                widget.bind("<Button-4>", lambda e, c=canvas: self._on_tab_canvas_mousewheel_linux(e, c, -1), add="+")
                widget.bind("<Button-5>", lambda e, c=canvas: self._on_tab_canvas_mousewheel_linux(e, c, 1), add="+")
            except Exception:
                pass
            for child in widget.winfo_children():
                _bind_children_mousewheel(child)

        def _refresh_bindings():
            _bind_children_mousewheel(inner)
            self.after(250, _refresh_bindings)

        self.after(250, _refresh_bindings)
        _sync_scrollregion()

        canvas._scrollbar = scrollbar
        inner._scroll_canvas = canvas
        return inner

    def _on_tab_canvas_mousewheel(self, event, canvas):
        widget = event.widget
        if isinstance(widget, (tk.Text, ttk.Treeview)):
            return None
        delta = 0
        if getattr(event, "delta", 0):
            delta = int(-event.delta / 120)
        if delta:
            try:
                canvas.yview_scroll(delta, "units")
            except Exception:
                pass
            return "break"
        return None

    def _on_tab_canvas_mousewheel_linux(self, event, canvas, direction):
        widget = event.widget
        if isinstance(widget, (tk.Text, ttk.Treeview)):
            return None
        try:
            canvas.yview_scroll(direction, "units")
        except Exception:
            pass
        return "break"


    def _set_collect_mode(self):
        mode = self.collect_mode_var.get()
        if mode == "single":
            self.collect_single_frame.pack(fill=tk.X)
            self.collect_range_frame.pack_forget()
        else:
            self.collect_single_frame.pack_forget()
            self.collect_range_frame.pack(fill=tk.X)

    def _set_predict_mode(self):
        mode = self.predict_mode_var.get()
        if mode == "single":
            self.predict_single_frame.pack(fill=tk.X)
            self.predict_range_frame.pack_forget()
        else:
            self.predict_single_frame.pack_forget()
            self.predict_range_frame.pack(fill=tk.X)

    def _build_collect_tab(self):
        settings = ttk.LabelFrame(
            self.collect_tab,
            text="取得条件",
            padding=14,
            style="Section.TLabelframe",
        )
        settings.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(
            settings,
            text="単日または期間を選択すると、その範囲内で実際に開催されている日だけを自動取得します。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        mode_row = ttk.Frame(settings, style="Card.TFrame")
        mode_row.pack(fill=tk.X, pady=(0, 8))

        self.collect_mode_var = tk.StringVar(value="single")
        ttk.Radiobutton(mode_row, text="単日指定", variable=self.collect_mode_var, value="single", command=self._set_collect_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="期間指定", variable=self.collect_mode_var, value="range", command=self._set_collect_mode).pack(side=tk.LEFT, padx=(12, 0))

        self.collect_single_frame = ttk.Frame(settings, style="Card.TFrame")
        self.collect_single_frame.pack(fill=tk.X)
        self._create_date_field(self.collect_single_frame, "開催日（YYYY-MM-DD）", "collect_single_entry")

        self.collect_range_frame = ttk.Frame(settings, style="Card.TFrame")
        self.collect_range_inner = ttk.Frame(self.collect_range_frame, style="Card.TFrame")
        self.collect_range_inner.pack(fill=tk.X)

        left = ttk.Frame(self.collect_range_inner, style="Card.TFrame")
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._create_date_field(left, "開始日（YYYY-MM-DD）", "collect_start_entry")

        right = ttk.Frame(self.collect_range_inner, style="Card.TFrame")
        right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._create_date_field(right, "終了日（YYYY-MM-DD）", "collect_end_entry")

        self._set_collect_mode()

        ops = ttk.LabelFrame(self.collect_tab, text="実行", padding=14, style="Section.TLabelframe")
        ops.pack(fill=tk.X, pady=(0, 12))
        self.operation_widgets["collect"] = self._create_operation_widgets(ops, "出走＋結果取得", self._start_collect)

        logs = ttk.LabelFrame(self.collect_tab, text="ログ", padding=14, style="Section.TLabelframe")
        logs.pack(fill=tk.BOTH, expand=True)
        self.collect_log = self._create_log_area(logs)
        self.operation_logs["collect"] = self.collect_log

    def _build_train_tab(self):
        parent = getattr(self, "train_tab_body", self.train_tab)

        settings = ttk.LabelFrame(
            parent,
            text="学習設定",
            padding=14,
            style="Section.TLabelframe",
        )
        settings.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(
            settings,
            text="result_*.csv を含むフォルダから学習し、汎用 / 特化 / 総合モデルをまとめて生成します。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        self.train_data_dir_entry = self._create_path_field(
            settings,
            "学習元フォルダ（result_*.csv を含むフォルダ）",
            self.data_dir_abs,
        )
        self.model_dir_entry = self._create_path_field(
            settings,
            "モデル保存先フォルダ（*.joblib を保存するフォルダ）",
            self.model_dir_abs,
        )

        family_frame = ttk.Frame(settings, style="Card.TFrame")
        family_frame.pack(fill=tk.X, pady=(8, 6))
        ttk.Label(family_frame, text="生成する学習モデル", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            family_frame,
            text="一般 / 競馬場 / 天候 / 距離 / 馬・騎手 / 調教師 / 全取り込み を個別に選択できます。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 6))

        self.train_family_vars = {}
        family_specs = [
            ("general", "汎用モデル"),
            ("track_specialized", "競馬場特化"),
            ("weather_specialized", "天候特化"),
            ("distance_specialized", "距離特化"),
            ("horse_jockey_specialized", "馬・騎手特化"),
            ("trainer_specialized", "調教師特化"),
            ("all_rounder", "全取り込み総合モデル"),
        ]
        grid = ttk.Frame(family_frame, style="Card.TFrame")
        grid.pack(fill=tk.X)
        for idx, (key, label) in enumerate(family_specs):
            var = tk.BooleanVar(value=True)
            self.train_family_vars[key] = var
            create_text_checkbox(
                grid,
                label,
                var,
                bg="#ffffff",
                fg="#0f172a",
            ).grid(row=idx // 3, column=idx % 3, sticky="w", padx=(0, 16), pady=(0, 4))

        self.self_learning_var = tk.BooleanVar(value=self._read_self_learning_flag(self.model_dir_abs))
        create_text_checkbox(
            settings,
            "起動時に新しい result_*.csv があれば自己学習（自動再学習）する",
            self.self_learning_var,
            bg="#ffffff",
            fg="#0f172a",
        ).pack(anchor=tk.W, pady=(8, 2))
        ttk.Label(
            settings,
            text="常時勝手に裏で増殖するような仕組みにはしていないわ。起動時の安全な自動再学習だけに留める。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W)

        ops = ttk.LabelFrame(parent, text="実行", padding=14, style="Section.TLabelframe")
        ops.pack(fill=tk.X, pady=(0, 12))
        self.operation_widgets["train"] = self._create_operation_widgets(ops, "AI学習開始（複数モデル）", self._start_train)

        logs = ttk.LabelFrame(parent, text="ログ", padding=14, style="Section.TLabelframe")
        logs.pack(fill=tk.BOTH, expand=True)
        self.train_log = self._create_log_area(logs)
        self.operation_logs["train"] = self.train_log

    def _build_predict_tab(self):
        parent = getattr(self, "predict_tab_body", self.predict_tab)

        settings = ttk.LabelFrame(
            parent,
            text="予測条件",
            padding=14,
            style="Section.TLabelframe",
        )
        settings.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(
            settings,
            text=(
                "予測は未来日のみ実行できます。単日または期間を指定すると、開催予定日だけを対象にします。\n"
                "日付欄は手入力でもカレンダーでも指定可能です。出力CSVには score / pred_rank / popularity_diff などを含めます。"
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        mode_row = ttk.Frame(settings, style="Card.TFrame")
        mode_row.pack(fill=tk.X, pady=(0, 8))

        self.predict_mode_var = tk.StringVar(value="single")
        ttk.Radiobutton(mode_row, text="単日指定", variable=self.predict_mode_var, value="single", command=self._set_predict_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="期間指定", variable=self.predict_mode_var, value="range", command=self._set_predict_mode).pack(side=tk.LEFT, padx=(12, 0))

        self.predict_single_frame = ttk.Frame(settings, style="Card.TFrame")
        self.predict_single_frame.pack(fill=tk.X)
        self._create_date_field(self.predict_single_frame, "開催予定日（YYYY-MM-DD / 手入力可）", "predict_single_entry")

        self.predict_range_frame = ttk.Frame(settings, style="Card.TFrame")
        self.predict_range_inner = ttk.Frame(self.predict_range_frame, style="Card.TFrame")
        self.predict_range_inner.pack(fill=tk.X)

        left = ttk.Frame(self.predict_range_inner, style="Card.TFrame")
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._create_date_field(left, "開始日（YYYY-MM-DD / 手入力可）", "predict_start_entry")

        right = ttk.Frame(self.predict_range_inner, style="Card.TFrame")
        right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._create_date_field(right, "終了日（YYYY-MM-DD / 手入力可）", "predict_end_entry")

        self._set_predict_mode()

        self.predict_model_dir_entry = self._create_path_field(
            settings,
            "使用するモデルフォルダ（*.joblib を含むフォルダ）",
            self.model_dir_abs,
        )

        option_frame = ttk.LabelFrame(settings, text="絞り込みとモデル選択", padding=12, style="Section.TLabelframe")
        option_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(option_frame, text="予測モデル", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.predict_model_strategy_var = tk.StringVar(value="auto_best")
        self.predict_model_strategy_combo = ttk.Combobox(
            option_frame,
            state="readonly",
            values=[
                "auto_best",
                "all_rounder",
                "general",
                "track_specialized",
                "weather_specialized",
                "distance_specialized",
                "horse_jockey_specialized",
                "trainer_specialized",
            ],
            textvariable=self.predict_model_strategy_var,
            width=28,
        )
        self.predict_model_strategy_combo.grid(row=0, column=1, sticky="w", padx=(8, 24))

        ttk.Label(option_frame, text="競馬場指定", style="SectionTitle.TLabel").grid(row=0, column=2, sticky="w")
        self.predict_track_var = tk.StringVar(value="すべて")
        self.predict_track_combo = ttk.Combobox(
            option_frame,
            state="readonly",
            values=["すべて", "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"],
            textvariable=self.predict_track_var,
            width=12,
        )
        self.predict_track_combo.grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Label(option_frame, text="R指定", style="SectionTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        race_wrap = ttk.Frame(option_frame, style="Card.TFrame")
        race_wrap.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.predict_race_from_entry = ttk.Entry(race_wrap, width=6)
        self.predict_race_from_entry.pack(side=tk.LEFT)
        self.predict_race_from_entry.insert(0, "")
        ttk.Label(race_wrap, text="〜", style="Muted.TLabel").pack(side=tk.LEFT, padx=4)
        self.predict_race_to_entry = ttk.Entry(race_wrap, width=6)
        self.predict_race_to_entry.pack(side=tk.LEFT)
        self.predict_race_to_entry.insert(0, "")
        ttk.Label(option_frame, text="空欄なら全R", style="Muted.TLabel").grid(row=1, column=2, sticky="w", pady=(10, 0), padx=(0, 0))
        ttk.Label(option_frame, text="auto_best を既定にしておけば、条件に応じて最も無難なモデルを優先します。", style="FieldHelp.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        option_frame.grid_columnconfigure(1, weight=1)
        option_frame.grid_columnconfigure(3, weight=1)

        bet_frame = ttk.LabelFrame(settings, text="買い目出力", padding=12, style="Section.TLabelframe")
        bet_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(bet_frame, text="出力する買い目形式", style="SectionTitle.TLabel").pack(anchor=tk.W)
        self.bet_type_vars = {}
        bet_specs = ["単勝", "複勝", "馬連ボックス", "ワイドボックス", "三連複ボックス", "三連単フォーメーション"]
        bet_grid = ttk.Frame(bet_frame, style="Card.TFrame")
        bet_grid.pack(fill=tk.X, pady=(4, 0))
        for idx, name in enumerate(bet_specs):
            var = tk.BooleanVar(value=True)
            self.bet_type_vars[name] = var
            create_text_checkbox(
                bet_grid,
                name,
                var,
                bg="#ffffff",
                fg="#0f172a",
            ).grid(row=idx // 3, column=idx % 3, sticky="w", padx=(0, 18), pady=(0, 4))

        ops = ttk.LabelFrame(parent, text="実行", padding=14, style="Section.TLabelframe")
        ops.pack(fill=tk.X, pady=(0, 12))
        self.operation_widgets["predict"] = self._create_operation_widgets(ops, "予測実行", self._start_predict)

        view = ttk.Panedwindow(parent, orient=tk.VERTICAL)
        view.pack(fill=tk.BOTH, expand=True)

        logs = ttk.LabelFrame(view, text="ログ", padding=14, style="Section.TLabelframe")
        self.predict_log = self._create_log_area(logs)
        self.operation_logs["predict"] = self.predict_log
        view.add(logs, weight=2)

        rec = ttk.LabelFrame(view, text="買い目サマリー", padding=10, style="Section.TLabelframe")
        self.predict_tree = ttk.Treeview(
            rec,
            columns=("race_id", "track", "race_no", "bet_type", "bet_text", "confidence"),
            show="headings",
            height=10,
        )
        for col, text, width in [
            ("race_id", "race_id", 120),
            ("track", "競馬場", 80),
            ("race_no", "R", 50),
            ("bet_type", "形式", 140),
            ("bet_text", "買い目", 420),
            ("confidence", "信頼度", 90),
        ]:
            self.predict_tree.heading(col, text=text)
            self.predict_tree.column(col, width=width, anchor="w")
        tree_scroll = ttk.Scrollbar(rec, orient="vertical", command=self.predict_tree.yview)
        tree_scroll_x = ttk.Scrollbar(rec, orient="horizontal", command=self.predict_tree.xview)
        self.predict_tree.configure(yscrollcommand=tree_scroll.set, xscrollcommand=tree_scroll_x.set)
        self.predict_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.predict_tree.bind("<MouseWheel>", lambda e, w=self.predict_tree: self._on_mousewheel_windows(e, w))
        self.predict_tree.bind("<Shift-MouseWheel>", lambda e, w=self.predict_tree: self._on_shift_mousewheel_windows(e, w))
        self.predict_tree.bind("<Button-4>", lambda e, w=self.predict_tree: self._on_mousewheel_linux_up(e, w))
        self.predict_tree.bind("<Button-5>", lambda e, w=self.predict_tree: self._on_mousewheel_linux_down(e, w))
        view.add(rec, weight=1)

    def _clear_entry_selection(self, entry_widget):
        try:
            entry_widget.selection_clear()
        except Exception:
            pass
        try:
            entry_widget.icursor(tk.END)
        except Exception:
            pass

    def _bind_no_selection_behavior(self, entry_widget):
        def _clear_now(_event=None):
            self.after_idle(lambda: self._clear_entry_selection(entry_widget))

        entry_widget.bind("<FocusIn>", _clear_now, add="+")
        entry_widget.bind("<ButtonRelease-1>", _clear_now, add="+")
        entry_widget.bind("<KeyRelease>", _clear_now, add="+")
        self.after_idle(lambda: self._clear_entry_selection(entry_widget))

    def _create_date_field(self, parent, label_text, attr_name):
        wrap = ttk.Frame(parent, style="Card.TFrame")
        wrap.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(wrap, text=label_text, style="SectionTitle.TLabel").pack(anchor=tk.W)

        row = ttk.Frame(wrap, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(4, 0))

        entry = ttk.Entry(row)
        self._set_entry_value(entry, self._display_date(dt.date.today()))
        self._bind_no_selection_behavior(entry)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e, w=entry: self._normalize_date_entry(w), add="+")
        entry.bind("<FocusOut>", lambda _e, w=entry: self._normalize_date_entry(w, silent=True), add="+")

        button_group = ttk.Frame(row, style="Card.TFrame")
        button_group.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            button_group,
            text="日付",
            style="Secondary.TButton",
            command=lambda e=entry: self._open_calendar_popup(e),
        ).pack(side=tk.LEFT)
        ttk.Button(
            button_group,
            text="今日",
            style="Quick.TButton",
            command=lambda e=entry: self._set_entry_value(e, self._display_date(dt.date.today())),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            button_group,
            text="明日",
            style="Quick.TButton",
            command=lambda e=entry: self._set_entry_value(e, self._display_date(dt.date.today() + dt.timedelta(days=1))),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            button_group,
            text="クリア",
            style="Quick.TButton",
            command=lambda e=entry: self._set_entry_value(e, ""),
        ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(
            wrap,
            text="手入力は YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD に対応",
            style="FieldHelp.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        setattr(self, attr_name, entry)

    def _create_path_field(self, parent, label_text, default_value):
        wrap = ttk.Frame(parent, style="Card.TFrame")
        wrap.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(wrap, text=label_text, style="SectionTitle.TLabel").pack(anchor=tk.W)

        row = ttk.Frame(wrap, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(4, 0))

        entry = ttk.Entry(row)
        entry.insert(0, os.path.abspath(default_value))
        self._bind_no_selection_behavior(entry)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(
            row,
            text="参照",
            style="Secondary.TButton",
            command=lambda e=entry: self._browse_directory_to_entry(e),
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            row,
            text="開く",
            style="Quick.TButton",
            command=lambda e=entry: self._open_entry_path(e),
        ).pack(side=tk.LEFT, padx=(6, 0))

        return entry

    def _create_operation_widgets(self, parent, start_text, start_command):
        button_row = ttk.Frame(parent, style="Card.TFrame")
        button_row.pack(fill=tk.X)

        start_btn = ttk.Button(button_row, text=start_text, style="Primary.TButton", command=start_command)
        start_btn.pack(side=tk.LEFT)

        pause_btn = ttk.Button(button_row, text="一時停止", style="Secondary.TButton", state="disabled", command=self._toggle_pause_current)
        pause_btn.pack(side=tk.LEFT, padx=(8, 0))

        stop_btn = ttk.Button(button_row, text="停止", style="Danger.TButton", state="disabled", command=self._stop_current_operation)
        stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        progress = ttk.Progressbar(parent, orient="horizontal", mode="determinate", maximum=100, value=0)
        progress.pack(fill=tk.X, pady=(12, 6))

        info_row = ttk.Frame(parent, style="Card.TFrame")
        info_row.pack(fill=tk.X)
        status_label = ttk.Label(info_row, text="待機中", style="Muted.TLabel")
        status_label.pack(side=tk.LEFT)
        eta_label = ttk.Label(info_row, text="進捗 0.0% / 残り --:--", style="Value.TLabel")
        eta_label.pack(side=tk.RIGHT)

        return {
            "start_btn": start_btn,
            "pause_btn": pause_btn,
            "stop_btn": stop_btn,
            "progress": progress,
            "status_label": status_label,
            "eta_label": eta_label,
        }

    def _create_log_area(self, parent):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(frame, style="LogToolbar.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            toolbar,
            text="ログ欄はマウスホイールでスクロールできます。タブの余白部分では画面全体が縦スクロールします。",
            style="LogHint.TLabel",
        ).pack(side=tk.LEFT)

        text_font = tkfont.Font(family="Consolas", size=10)

        body = tk.Frame(frame, bg="#d8dee9", bd=1, highlightthickness=0)
        body.pack(fill=tk.BOTH, expand=True)

        text = tk.Text(
            body,
            height=18,
            wrap="word",
            state="disabled",
            bg="#0b1220",
            fg="#dbe7f3",
            insertbackground="#e2e8f0",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=12,
            spacing1=1,
            spacing2=1,
            spacing3=2,
            font=text_font,
            undo=False,
        )
        text._font = text_font
        text._wrap_mode = "word"

        v_scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        h_scrollbar = ttk.Scrollbar(body, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        text.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        action_row = ttk.Frame(frame, style="LogToolbar.TFrame")
        action_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(action_row, text="末尾へ", style="LogAction.TButton", command=lambda w=text: self._scroll_log_to_end(w)).pack(side=tk.RIGHT)
        ttk.Button(action_row, text="折返し", style="LogAction.TButton", command=lambda w=text: self._toggle_log_wrap(w)).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(action_row, text="文字＋", style="LogAction.TButton", command=lambda w=text: self._adjust_log_font_size(w, 1)).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(action_row, text="文字－", style="LogAction.TButton", command=lambda w=text: self._adjust_log_font_size(w, -1)).pack(side=tk.RIGHT, padx=(0, 6))

        text.tag_configure("info", foreground="#93c5fd")
        text.tag_configure("warn", foreground="#fbbf24")
        text.tag_configure("error", foreground="#fca5a5")
        text.tag_configure("success", foreground="#86efac")
        text.tag_configure("header", foreground="#f8fafc", font=("Consolas", 10, "bold"))
        text.tag_configure("muted", foreground="#94a3b8")

        text.bind("<MouseWheel>", lambda e, w=text: self._on_mousewheel_windows(e, w))
        text.bind("<Shift-MouseWheel>", lambda e, w=text: self._on_shift_mousewheel_windows(e, w))
        text.bind("<Button-4>", lambda e, w=text: self._on_mousewheel_linux_up(e, w))
        text.bind("<Button-5>", lambda e, w=text: self._on_mousewheel_linux_down(e, w))

        return text

    def _clear_treeview_direct(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def _update_prediction_table_direct(self, recommendations):
        self._clear_treeview_direct(self.predict_tree)
        for rec in recommendations:
            self.predict_tree.insert(
                "",
                tk.END,
                values=(
                    rec.get("race_id", ""),
                    rec.get("track", ""),
                    rec.get("race_no", ""),
                    rec.get("bet_type", ""),
                    rec.get("bet_text", ""),
                    f"{float(rec.get('confidence', 0.0)):.3f}",
                ),
            )

    def _selected_train_families(self):
        return [key for key, var in self.train_family_vars.items() if var.get()]

    def _selected_bet_types(self):
        return [name for name, var in self.bet_type_vars.items() if var.get()]

    def _read_self_learning_flag(self, model_dir):
        try:
            return os.path.exists(os.path.join(model_dir, ".self_learning_enabled"))
        except Exception:
            return False

    def _write_self_learning_flag(self, model_dir, enabled):
        try:
            os.makedirs(model_dir, exist_ok=True)
            flag_path = os.path.join(model_dir, ".self_learning_enabled")
            if enabled:
                with open(flag_path, "w", encoding="utf-8") as f:
                    f.write("1\n")
            elif os.path.exists(flag_path):
                os.remove(flag_path)
        except Exception:
            pass

    def _maybe_start_self_learning(self):
        model_dir = self.model_dir_entry.get().strip() if hasattr(self, "model_dir_entry") else self.model_dir_abs
        data_dir = self.train_data_dir_entry.get().strip() if hasattr(self, "train_data_dir_entry") else self.data_dir_abs
        model_dir = os.path.abspath(model_dir or self.model_dir_abs)
        data_dir = os.path.abspath(data_dir or self.data_dir_abs)
        if not self._read_self_learning_flag(model_dir):
            return
        if self.current_operation is not None:
            return
        result_files = sorted(glob.glob(os.path.join(data_dir, "result_*.csv")))
        model_files = sorted(glob.glob(os.path.join(model_dir, "*.joblib")))
        if not result_files:
            return
        latest_result = max(os.path.getmtime(p) for p in result_files)
        latest_model = max([os.path.getmtime(p) for p in model_files], default=0)
        if latest_result <= latest_model:
            return
        if not self._begin_operation("train"):
            return
        families = self._selected_train_families() if hasattr(self, "train_family_vars") else []
        self._run_thread(self.run_train, data_dir, model_dir, families, True)

    def _filter_prediction_dataframe(self, df, track_filter, race_from, race_to):
        work = df.copy()
        if track_filter and track_filter != "すべて":
            work = work[work["track"].astype(str) == track_filter].copy()
        if race_from is not None:
            work = work[pd.to_numeric(work["race_no"], errors="coerce") >= race_from].copy()
        if race_to is not None:
            work = work[pd.to_numeric(work["race_no"], errors="coerce") <= race_to].copy()
        return work.reset_index(drop=True)

    def _build_predict_summary_lines(self, result_df):
        lines = []
        if result_df is None or result_df.empty:
            return ["予測結果が空です。"]
        work_df = result_df.copy().sort_values(["race_id", "pred_rank", "horse_no"], ascending=[True, True, True])
        for race_id, race_df in work_df.groupby("race_id", sort=False):
            top_df = race_df.head(3)
            first = top_df.iloc[0]
            lines.append(f"[race_id={race_id}] {first.get('track','')} {int(first.get('race_no',0)) if pd.notna(first.get('race_no',0)) else '-'}R")
            for _, row in top_df.iterrows():
                lines.append(
                    f"  予測{int(row.get('pred_rank', 0))}位 馬番={int(row.get('horse_no', 0))} {row.get('horse_name', '')} "
                    f"score={float(row.get('score', 0.0)):.4f} 人気={row.get('popularity', '-')} 乖離={float(row.get('popularity_diff', 0.0)):.1f}"
                )
            lines.append("")
        return lines

    # ---------- context menu ----------
    def _create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="コピー", command=self._copy_focus_selection)
        self.context_menu.add_command(label="すべて選択", command=self._select_all_for_focus)
        self.bind_all("<Control-a>", self._on_ctrl_a)
        self.bind_all("<Control-A>", self._on_ctrl_a)
        self.bind_all("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        widget = event.widget
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            try:
                widget.focus_set()
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()

    def _copy_focus_selection(self):
        widget = self.focus_get()
        if widget is None:
            return
        try:
            if isinstance(widget, (tk.Entry, ttk.Entry)):
                text = widget.selection_get()
            elif isinstance(widget, tk.Text):
                text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            else:
                return
            self.clipboard_clear()
            self.clipboard_append(text)
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
        self._select_all_for_focus()
        return "break"

    def _clear_current_log(self):
        current_tab = self.notebook.select()
        if current_tab == str(self.collect_tab):
            self._clear_log_direct(self.collect_log)
        elif current_tab == str(self.train_tab):
            self._clear_log_direct(self.train_log)
        elif current_tab == str(self.predict_tab):
            self._clear_log_direct(self.predict_log)

    # ---------- mouse wheel ----------
    def _on_mousewheel_windows(self, event, widget):
        widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _on_shift_mousewheel_windows(self, event, widget):
        try:
            widget.xview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass
        return "break"

    def _on_mousewheel_linux_up(self, event, widget):
        widget.yview_scroll(-1, "units")
        return "break"

    def _on_mousewheel_linux_down(self, event, widget):
        widget.yview_scroll(1, "units")
        return "break"

    def _scroll_log_to_end(self, widget):
        try:
            widget.see(tk.END)
        except Exception:
            pass

    def _toggle_log_wrap(self, widget):
        current = getattr(widget, "_wrap_mode", "word")
        new_mode = "none" if current == "word" else "word"
        widget.configure(wrap=new_mode)
        widget._wrap_mode = new_mode

    def _adjust_log_font_size(self, widget, delta):
        font = getattr(widget, "_font", None)
        if font is None:
            return
        current = int(font.cget("size"))
        new_size = max(8, min(16, current + delta))
        font.configure(size=new_size)

    # ---------- property / config ----------
    def _open_properties_dialog(self):
        PropertiesDialog(self, self._save_properties)

    def _save_properties(self, cache_enabled):
        collector.set_html_cache_enabled(cache_enabled)
        self._persist_bool_setting("ENABLE_HTML_CACHE", cache_enabled)
        self.cache_status_note.configure(text="HTMLキャッシュ: " + ("ON" if cache_enabled else "OFF"))
        messagebox.showinfo("保存完了", "プロパティを保存しました。")

    def _persist_bool_setting(self, key, value):
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.py"))
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()

        replacement = f"{key} = {'True' if value else 'False'}"
        if re.search(rf"^{key}\s*=\s*(True|False)\s*$", text, flags=re.MULTILINE):
            text = re.sub(rf"^{key}\s*=\s*(True|False)\s*$", replacement, text, flags=re.MULTILINE)
        else:
            text = text.rstrip() + "\n" + replacement + "\n"

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(text)

    def _clear_html_cache_from_menu(self):
        removed = collector.clear_html_cache()
        messagebox.showinfo("完了", f"HTMLキャッシュを {removed} 件削除しました。")

    # ---------- path / date helpers ----------
    def _open_path(self, path):
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("エラー", str(exc))

    def _display_date(self, value):
        return value.strftime("%Y-%m-%d")

    def _compact_date(self, value):
        return value.strftime("%Y%m%d")

    def _parse_date(self, text):
        raw = (text or "").strip()
        if not raw:
            raise ValueError("日付が未入力です。")

        normalized = raw.replace("/", "-").replace(".", "-")
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return dt.datetime.strptime(normalized, fmt).date()
            except ValueError:
                pass
        raise ValueError(f"日付形式が不正です: {raw}（例: 2026-04-06）")

    def _set_entry_value(self, entry_widget, value):
        state = str(entry_widget.cget("state"))
        if state == "readonly":
            entry_widget.configure(state="normal")
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, value)
            entry_widget.configure(state="readonly")
        else:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, value)

        self.after_idle(lambda: self._clear_entry_selection(entry_widget))

    def _normalize_date_entry(self, entry_widget, silent=False):
        text = entry_widget.get().strip()
        if not text:
            return True
        try:
            value = self._parse_date(text)
        except Exception as exc:
            if not silent:
                messagebox.showerror("日付形式エラー", str(exc))
                entry_widget.focus_set()
            return False
        self._set_entry_value(entry_widget, self._display_date(value))
        return True

    def _open_calendar_popup(self, entry_widget):
        text = entry_widget.get().strip()
        try:
            initial = self._parse_date(text)
        except Exception:
            initial = dt.date.today()

        CalendarPopup(
            self,
            entry_widget,
            initial,
            lambda chosen: self._set_entry_value(entry_widget, self._display_date(chosen)),
        )

    def _browse_directory_to_entry(self, entry_widget):
        current = entry_widget.get().strip()
        if current and os.path.isdir(current):
            initialdir = current
        elif current:
            initialdir = os.path.dirname(current)
        else:
            initialdir = os.getcwd()

        selected = filedialog.askdirectory(initialdir=initialdir)
        if selected:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, os.path.abspath(selected))

    def _open_entry_path(self, entry_widget):
        raw = entry_widget.get().strip()
        if not raw:
            messagebox.showinfo("確認", "パスが未入力です。")
            return
        path = os.path.abspath(raw)
        if os.path.isdir(path):
            self._open_path(path)
            return
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent):
            self._open_path(parent)
            return
        messagebox.showerror("エラー", f"開けるフォルダが見つかりません: {path}")

    def _resolve_dates(self, mode, single_entry, start_entry, end_entry):
        if mode == "single":
            return [self._parse_date(single_entry.get().strip())]

        start_date = self._parse_date(start_entry.get().strip())
        end_date = self._parse_date(end_entry.get().strip())

        if start_date > end_date:
            raise ValueError("開始日と終了日が逆転しています。開始日を終了日以前にしてください。")

        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += dt.timedelta(days=1)

        return dates

    def _validate_predict_dates(self, date_list):
        today = dt.date.today()
        invalid = [d for d in date_list if d <= today]
        if invalid:
            sample = ", ".join(self._display_date(d) for d in invalid[:3])
            raise ValueError(f"予測では未来日のみ指定できます。当日以前が含まれています: {sample}")

    # ---------- queue / ui direct ----------
    def _process_ui_queue(self):
        try:
            while True:
                func, args = self.ui_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        self.after(100, self._process_ui_queue)

    def _queue_ui(self, func, *args):
        self.ui_queue.put((func, args))

    def _append_log_direct(self, widget, message):
        widget.configure(state="normal")
        tag = None
        upper = str(message).upper()
        if str(message).startswith("==="):
            tag = "header"
        elif "[STOP]" in upper or "[ERROR]" in upper or "TRACEBACK" in upper:
            tag = "error"
        elif "[WARN]" in upper or "警告" in str(message):
            tag = "warn"
        elif "完了" in str(message) or "成功" in str(message) or "保存:" in str(message):
            tag = "success"
        elif "開始" in str(message) or "[INFO]" in upper or "確認列:" in str(message):
            tag = "info"
        elif not str(message).strip():
            tag = "muted"
        if tag:
            widget.insert(tk.END, message + "\n", tag)
        else:
            widget.insert(tk.END, message + "\n")
        widget.see(tk.END)
        widget.configure(state="disabled")

    def _clear_log_direct(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.configure(state="disabled")

    def _reset_progress_direct(self, operation_name):
        op = self.operation_widgets[operation_name]
        op["progress"].configure(value=0, maximum=100, mode="determinate")
        op["status_label"].configure(text="待機中")
        op["eta_label"].configure(text="進捗 0.0% / 残り --:--")

    def _set_button_state_direct(self, operation_name, running):
        op = self.operation_widgets[operation_name]
        op["start_btn"].configure(state="disabled" if running else "normal")
        op["pause_btn"].configure(state="normal" if running else "disabled", text="一時停止")
        op["stop_btn"].configure(state="normal" if running else "disabled")

    def _update_progress_direct(self, operation_name, current, total, message, eta_text):
        op = self.operation_widgets[operation_name]
        total = max(total, 1)
        percent = (current / total) * 100.0
        op["progress"].configure(maximum=total, value=current)
        op["status_label"].configure(text=message)
        op["eta_label"].configure(text=f"進捗 {percent:.1f}% / 残り {eta_text}")

    def _set_pause_button_text_direct(self, operation_name, text):
        self.operation_widgets[operation_name]["pause_btn"].configure(text=text)

    # ---------- operation state ----------
    def _begin_operation(self, operation_name):
        if self.current_operation is not None:
            messagebox.showwarning("実行中", "別の処理が実行中です。完了または停止を待ってください。")
            return False

        self.current_operation = operation_name
        self.pause_event.clear()
        self.stop_event.clear()
        self._set_button_state_direct(operation_name, True)
        self._reset_progress_direct(operation_name)
        return True

    def _finish_operation(self, operation_name, reset_progress=False):
        self._set_button_state_direct(operation_name, False)
        if reset_progress:
            self._reset_progress_direct(operation_name)
        self.current_operation = None
        self.pause_event.clear()
        self.stop_event.clear()

    def _toggle_pause_current(self):
        if self.current_operation is None:
            return

        if self.pause_event.is_set():
            self.pause_event.clear()
            self._set_pause_button_text_direct(self.current_operation, "一時停止")
            self._queue_ui(
                self._append_log_direct,
                self.operation_logs[self.current_operation],
                "[INFO] 処理を再開します。",
            )
        else:
            self.pause_event.set()
            self._set_pause_button_text_direct(self.current_operation, "再開")
            self._queue_ui(
                self._append_log_direct,
                self.operation_logs[self.current_operation],
                "[INFO] 一時停止を要求しました。現在の処理区切りで停止します。",
            )

    def _stop_current_operation(self):
        if self.current_operation is not None:
            self.stop_event.set()
            self._queue_ui(
                self._append_log_direct,
                self.operation_logs[self.current_operation],
                "[STOP] 停止を要求しました。現在の処理区切りで停止します。",
            )

    def _wait_if_paused(self, operation_name, current, total, started_at):
        while self.pause_event.is_set():
            self._queue_ui(self._update_progress_direct, operation_name, current, total, "一時停止中", "--:--")
            time.sleep(0.2)
            if self.stop_event.is_set():
                raise OperationCancelled("ユーザーが停止しました。")

    def _checkpoint(self, operation_name, current, total, message, started_at):
        if self.stop_event.is_set():
            raise OperationCancelled("ユーザーが停止しました。")

        self._wait_if_paused(operation_name, current, total, started_at)

        eta_text = "--:--"
        if current > 0 and total > current:
            elapsed = max(0.0, time.time() - started_at)
            remaining_seconds = int((elapsed / current) * (total - current))
            minutes, seconds = divmod(remaining_seconds, 60)
            eta_text = f"{minutes:02d}:{seconds:02d}"

        self._queue_ui(self._update_progress_direct, operation_name, current, total, message, eta_text)

    # ---------- start handlers ----------
    def _start_collect(self):
        try:
            dates = self._resolve_dates(
                self.collect_mode_var.get(),
                self.collect_single_entry,
                self.collect_start_entry,
                self.collect_end_entry,
            )
            if len(dates) > 366:
                raise ValueError("期間指定が長すぎます。1年以内を目安にしてください。")
        except Exception as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        if not self._begin_operation("collect"):
            return

        self._run_thread(self.run_collect, dates)

    def _start_train(self):
        data_dir = self.train_data_dir_entry.get().strip() or self.data_dir_abs
        model_dir = self.model_dir_entry.get().strip() or self.model_dir_abs
        families = self._selected_train_families()

        try:
            data_dir = os.path.abspath(data_dir)
            model_dir = os.path.abspath(model_dir)
            if not os.path.isdir(data_dir):
                raise ValueError(f"学習元フォルダが存在しません: {data_dir}")
            if not glob.glob(os.path.join(data_dir, "result_*.csv")):
                raise ValueError(f"学習元フォルダに result_*.csv がありません: {data_dir}")
            if not families:
                raise ValueError("生成する学習モデルを1つ以上選択してください。")
            os.makedirs(model_dir, exist_ok=True)
            self._write_self_learning_flag(model_dir, self.self_learning_var.get())
        except Exception as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        if not self._begin_operation("train"):
            return

        self._run_thread(self.run_train, data_dir, model_dir, families, False)

    def _start_predict(self):
        model_dir = self.predict_model_dir_entry.get().strip() or self.model_dir_abs
        strategy = self.predict_model_strategy_var.get().strip() or "auto_best"
        track_filter = self.predict_track_var.get().strip() or "すべて"
        race_from_text = self.predict_race_from_entry.get().strip()
        race_to_text = self.predict_race_to_entry.get().strip()
        bet_types = self._selected_bet_types()

        try:
            dates = self._resolve_dates(
                self.predict_mode_var.get(),
                self.predict_single_entry,
                self.predict_start_entry,
                self.predict_end_entry,
            )
            self._validate_predict_dates(dates)
            if len(dates) > 366:
                raise ValueError("期間指定が長すぎます。1年以内を目安にしてください。")
            race_from = int(race_from_text) if race_from_text else None
            race_to = int(race_to_text) if race_to_text else None
            if race_from is not None and not (1 <= race_from <= 12):
                raise ValueError("R指定の開始値は 1〜12 にしてください。")
            if race_to is not None and not (1 <= race_to <= 12):
                raise ValueError("R指定の終了値は 1〜12 にしてください。")
            if race_from is not None and race_to is not None and race_from > race_to:
                raise ValueError("R指定の開始と終了が逆転しています。")
            if not bet_types:
                raise ValueError("買い目形式を1つ以上選択してください。")
            model_dir = os.path.abspath(model_dir)
            if not os.path.isdir(model_dir):
                raise ValueError(f"モデルフォルダが存在しません: {model_dir}")
            if not glob.glob(os.path.join(model_dir, "*.joblib")):
                raise ValueError(f"モデルフォルダに *.joblib がありません: {model_dir}")
        except Exception as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        if not self._begin_operation("predict"):
            return

        self._run_thread(self.run_predict, dates, model_dir, strategy, track_filter, race_from, race_to, bet_types)

    def _run_thread(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    # ---------- workers ----------
    def _filter_holding_dates(self, operation_name, date_list, started_at):
        total = max(len(date_list), 1)

        def progress_callback(current_value, total_count, message):
            self._checkpoint(operation_name, current_value, total_count, message, started_at)

        def log_callback(message):
            self._queue_ui(self._append_log_direct, self.operation_logs[operation_name], message)

        def wait_if_paused():
            self._wait_if_paused(operation_name, 0, total, started_at)

        def check_cancel():
            if self.stop_event.is_set():
                raise OperationCancelled("ユーザーが停止しました。")

        valid_batches, skipped_dates = resolve_holding_dates(
            date_list,
            date_to_str=self._compact_date,
            progress_callback=progress_callback,
            log_callback=log_callback,
            wait_if_paused=wait_if_paused,
            check_cancel=check_cancel,
        )

        if skipped_dates:
            self._queue_ui(
                self._append_log_direct,
                self.operation_logs[operation_name],
                f"[INFO] 非開催日をスキップ: {', '.join(skipped_dates)}",
            )

        self._checkpoint(operation_name, total, total, "開催日判定完了", started_at)
        return [(batch.date_obj, batch.race_ids) for batch in valid_batches]

    def run_collect(self, dates):
        started_at = time.time()
        try:
            self._queue_ui(self._clear_log_direct, self.collect_log)
            self._queue_ui(self._append_log_direct, self.collect_log, "データ取得を開始します。")

            valid_dates = self._filter_holding_dates("collect", dates, started_at)
            if not valid_dates:
                raise ValueError("指定範囲に開催日がありませんでした。")

            total_steps = sum(len(race_ids) * 2 + 2 for _, race_ids in valid_dates)
            current = 0

            def status_callback(message, current_value=None):
                current_step = current if current_value is None else current_value
                self._checkpoint("collect", current_step, total_steps, message, started_at)

            def wait_if_paused():
                self._wait_if_paused("collect", current, total_steps, started_at)

            def check_cancel():
                if self.stop_event.is_set():
                    raise OperationCancelled("ユーザーが停止しました。")

            for date_obj, race_ids in valid_dates:
                date_str = self._compact_date(date_obj)
                self._queue_ui(self._append_log_direct, self.collect_log, f"=== {date_str} 開始 ===")

                entry_rows = []
                result_rows = []

                for race_id in race_ids:
                    status_callback(f"出走表取得中 {race_id}")
                    entry_html = collector.fetch_race_page(
                        race_id,
                        mode="entry",
                        use_cache=True,
                        status_callback=status_callback,
                        wait_if_paused=wait_if_paused,
                        check_cancel=check_cancel,
                    )
                    entry_rows.extend(parser.parse_entry(entry_html, race_id))
                    current += 1
                    status_callback(f"出走表取得完了 {race_id}", current)

                    status_callback(f"結果取得中 {race_id}")
                    try:
                        result_html = collector.fetch_race_page(
                            race_id,
                            mode="result",
                            use_cache=True,
                            status_callback=status_callback,
                            wait_if_paused=wait_if_paused,
                            check_cancel=check_cancel,
                        )
                        result_rows.extend(parser.parse_result(result_html, race_id))
                    except Exception as exc:
                        self._queue_ui(self._append_log_direct, self.collect_log, f"[INFO] result未取得: race_id={race_id} / {exc}")
                    current += 1
                    status_callback(f"結果取得完了 {race_id}", current)

                if entry_rows:
                    entry_df = dataset.build_entry_df(entry_rows)
                    entry_path = os.path.join(self.data_dir_abs, ENTRY_FILE_PATTERN.format(date=date_str))
                    entry_df.to_csv(entry_path, index=False, encoding="utf-8-sig")
                    self._queue_ui(self._append_log_direct, self.collect_log, f"出走表保存: {entry_path} / {len(entry_df)}件")
                else:
                    self._queue_ui(self._append_log_direct, self.collect_log, "出走表データなし")
                current += 1
                status_callback(f"出走表CSV保存完了 {date_str}", current)

                if result_rows:
                    result_df = dataset.build_result_df(result_rows)
                    result_path = os.path.join(self.data_dir_abs, RESULT_FILE_PATTERN.format(date=date_str))
                    result_df.to_csv(result_path, index=False, encoding="utf-8-sig")
                    self._queue_ui(self._append_log_direct, self.collect_log, f"結果保存: {result_path} / {len(result_df)}件")
                else:
                    self._queue_ui(self._append_log_direct, self.collect_log, "結果データなし（未来日または未確定の可能性あり）")
                current += 1
                status_callback(f"結果CSV保存完了 {date_str}", current)

                self._queue_ui(self._append_log_direct, self.collect_log, f"=== {date_str} 完了 ===")
                self._queue_ui(self._append_log_direct, self.collect_log, "")

            self._queue_ui(self._update_progress_direct, "collect", total_steps, total_steps, "データ取得完了", "00:00")
            self._queue_ui(messagebox.showinfo, "完了", "データ取得が完了しました。")

        except OperationCancelled as exc:
            self._queue_ui(self._append_log_direct, self.collect_log, f"[STOP] {exc}")
            self._queue_ui(self._update_progress_direct, "collect", current if 'current' in locals() else 0, total_steps if 'total_steps' in locals() and total_steps > 0 else 1, "停止済み", "--:--")
        except Exception as exc:
            self._queue_ui(messagebox.showerror, "エラー", str(exc))
            self._queue_ui(self._update_progress_direct, "collect", current if 'current' in locals() else 0, total_steps if 'total_steps' in locals() and total_steps > 0 else 1, f"エラー: {exc}", "--:--")
        finally:
            self._queue_ui(self._finish_operation, "collect")


    def run_train(self, data_dir, model_dir, families, is_auto=False):
        try:
            self._queue_ui(self._clear_log_direct, self.train_log)
            self._queue_ui(self._append_log_direct, self.train_log, "自己学習開始..." if is_auto else "学習開始...")
            self._queue_ui(self._append_log_direct, self.train_log, f"対象モデル: {', '.join(families)}")
            summary = trainer.train_all_models(data_dir=data_dir, model_dir=model_dir, families=families)
            for item in summary.get("summaries", []):
                if item.get("error"):
                    self._queue_ui(
                        self._append_log_direct,
                        self.train_log,
                        f"[NG] {item.get('family','-')} / {item.get('target_col','-')} / scope={item.get('scope_type') or 'global'}:{item.get('scope_value') or '-'} : {item.get('error')}",
                    )
                    continue
                auc_text = "None" if item.get("auc") is None else f"{item['auc']:.4f}"
                self._queue_ui(
                    self._append_log_direct,
                    self.train_log,
                    f"[OK] {item.get('family','-')} / {item['target_col']} / scope={item.get('scope_type') or 'global'}:{item.get('scope_value') or '-'} "
                    f"rows={item.get('rows',0)} acc={item.get('accuracy',0):.4f} f1={item.get('f1',0):.4f} recall={item.get('recall',0):.4f} auc={auc_text} thr={item.get('threshold',0):.3f}",
                )
            self._queue_ui(self._append_log_direct, self.train_log, f"成功={summary.get('success_count', 0)} / 失敗={summary.get('error_count', 0)}")
            self._queue_ui(self._append_log_direct, self.train_log, f"summary保存: {os.path.join(model_dir, 'training_summary.json')}")
            self._queue_ui(messagebox.showinfo, "完了", "自己学習が完了しました。" if is_auto else "AI学習が完了しました。")
        except OperationCancelled as exc:
            self._queue_ui(self._append_log_direct, self.train_log, f"[STOP] {exc}")
        except Exception as exc:
            self._queue_ui(messagebox.showerror, "エラー", str(exc))
        finally:
            self._queue_ui(self._finish_operation, "train")

    def run_predict(self, dates, model_dir, strategy, track_filter, race_from, race_to, bet_types):
        started_at = time.time()
        try:
            self._queue_ui(self._clear_log_direct, self.predict_log)
            self._queue_ui(self._clear_treeview_direct, self.predict_tree)
            self._queue_ui(self._append_log_direct, self.predict_log, f"予測開始... strategy={strategy}")
            self._queue_ui(self._append_log_direct, self.predict_log, f"競馬場指定={track_filter} / R指定={race_from or '-'}〜{race_to or '-'}")
            self._queue_ui(self._append_log_direct, self.predict_log, f"買い目形式={', '.join(bet_types)}")

            valid_dates = self._filter_holding_dates("predict", dates, started_at)
            if not valid_dates:
                raise ValueError("指定範囲に開催予定日がありませんでした。")

            total_steps = sum(len(race_ids) + 2 for _, race_ids in valid_dates)
            current = 0
            all_recommendations = []

            for date_obj, race_ids in valid_dates:
                date_str = self._compact_date(date_obj)
                self._queue_ui(self._append_log_direct, self.predict_log, f"=== {date_str} 予測開始 ===")
                entry_rows = []
                for race_id in race_ids:
                    self._checkpoint("predict", current, total_steps, f"出走表取得中 {race_id}", started_at)
                    html = collector.fetch_race_page(race_id, mode="entry", use_cache=True)
                    entry_rows.extend(parser.parse_entry(html, race_id))
                    current += 1

                if not entry_rows:
                    self._queue_ui(self._append_log_direct, self.predict_log, f"{date_str}: 出走表データを取得できませんでした。")
                    current += 2
                    continue

                entry_df = dataset.build_entry_df(entry_rows)
                entry_path = os.path.join(self.data_dir_abs, ENTRY_FILE_PATTERN.format(date=date_str))
                entry_df.to_csv(entry_path, index=False, encoding="utf-8-sig")
                self._queue_ui(self._append_log_direct, self.predict_log, f"出走表保存: {entry_path}")
                current += 1
                self._checkpoint("predict", current, total_steps, f"予測計算中 {date_str}", started_at)

                result_df = predictor.predict_from_entry(entry_path, model_dir=model_dir, output_path=None, strategy=strategy)
                result_df = self._filter_prediction_dataframe(result_df, track_filter, race_from, race_to)
                if result_df.empty:
                    self._queue_ui(self._append_log_direct, self.predict_log, f"{date_str}: 条件に合うレースがありませんでした。")
                    current += 1
                    continue

                output_path = os.path.join(self.data_dir_abs, PREDICT_FILE_PATTERN.format(date=date_str))
                result_df.to_csv(output_path, index=False, encoding="utf-8-sig")

                self._queue_ui(self._append_log_direct, self.predict_log, f"予測保存: {output_path}")
                self._queue_ui(self._append_log_direct, self.predict_log, f"予測件数: {len(result_df)}")
                self._queue_ui(self._append_log_direct, self.predict_log, "確認列: score / pred_rank / popularity_diff / model_strategy")
                for line in self._build_predict_summary_lines(result_df):
                    self._queue_ui(self._append_log_direct, self.predict_log, line)

                recommendations = predictor.build_bet_recommendations(result_df, bet_types=bet_types)
                all_recommendations.extend(recommendations)
                for rec in recommendations:
                    self._queue_ui(
                        self._append_log_direct,
                        self.predict_log,
                        f"[買い目] {rec.get('track','')} {rec.get('race_no','')}R {rec.get('bet_type','')} -> {rec.get('bet_text','')} (信頼度={float(rec.get('confidence',0.0)):.3f})",
                    )

                self._queue_ui(self._append_log_direct, self.predict_log, f"=== {date_str} 予測完了 ===")
                self._queue_ui(self._append_log_direct, self.predict_log, "")
                current += 1
                self._checkpoint("predict", current, total_steps, f"予測計算中 {date_str}", started_at)

            self._queue_ui(self._update_prediction_table_direct, all_recommendations)
            self._queue_ui(messagebox.showinfo, "完了", "予測が完了しました。")

        except OperationCancelled as exc:
            self._queue_ui(self._append_log_direct, self.predict_log, f"[STOP] {exc}")
        except Exception as exc:
            self._queue_ui(messagebox.showerror, "エラー", str(exc))
        finally:
            self._queue_ui(self._finish_operation, "predict")

    # ---------- close ----------
    def _on_close(self):
        if self.current_operation is not None:
            if not messagebox.askyesno("確認", "処理が実行中です。停止して終了しますか？"):
                return
            self.stop_event.set()
        self.destroy()
