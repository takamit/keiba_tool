import tkinter as tk
from tkinter import ttk

class LabeledEntry(ttk.Frame):
    def __init__(self, master, label_text: str, **kwargs):
        super().__init__(master, **kwargs)
        self.label = ttk.Label(self, text=label_text)
        self.label.pack(side=tk.LEFT, padx=(0, 6))
        self.entry = ttk.Entry(self)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
