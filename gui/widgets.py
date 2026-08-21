"""Bausteine für die Oberfläche: Dateiauswahl, Drag&Drop, Fehlerdialoge."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, List, Optional

PADDING = 8


# ---------------------------------------------------------------------------
# Drag & Drop (optional – funktioniert nur mit dem Paket tkinterdnd2)
# ---------------------------------------------------------------------------

def create_root() -> tk.Tk:
    """Erzeugt das Hauptfenster – mit Drag&Drop, falls verfügbar."""
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore

        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


def drag_and_drop_available(widget: tk.Misc) -> bool:
    return hasattr(widget, "drop_target_register") or hasattr(widget.winfo_toplevel(),
                                                              "drop_target_register")


def enable_drop(widget: tk.Misc, callback: Callable[[List[str]], None]) -> bool:
    """Macht ein Feld zur Ablagefläche für Dateien/Ordner. True bei Erfolg."""
    try:
        from tkinterdnd2 import DND_FILES  # type: ignore
    except Exception:
        return False
    if not hasattr(widget, "drop_target_register"):
        return False

    def on_drop(event):
        callback(_split_drop_paths(event.data))
        return event.action

    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", on_drop)
        return True
    except Exception:
        return False


def _split_drop_paths(data: str) -> List[str]:
    """Tk liefert abgelegte Pfade als eine Zeichenkette – hier zerlegt."""
    paths: List[str] = []
    current = ""
    in_braces = False
    for char in data:
        if char == "{":
            in_braces = True
        elif char == "}":
            in_braces = False
            if current:
                paths.append(current)
                current = ""
        elif char == " " and not in_braces:
            if current:
                paths.append(current)
                current = ""
        else:
            current += char
    if current:
        paths.append(current)
    return [p for p in paths if p]


# ---------------------------------------------------------------------------
# Auswahlzeile für Ordner/Dateien
# ---------------------------------------------------------------------------

class PathRow(ttk.Frame):
    """Beschriftung + Eingabefeld + Durchsuchen-Knopf, mit Drag&Drop."""

    def __init__(self, master, label: str, mode: str = "folder",
                 filetypes=None, hint: str = "", on_change: Optional[Callable] = None):
        super().__init__(master)
        self.mode = mode
        self.filetypes = filetypes or []
        self.on_change = on_change
        self.value = tk.StringVar()
        self.value.trace_add("write", lambda *_: self.on_change and self.on_change())

        self.columnconfigure(1, weight=1)
        ttk.Label(self, text=label, width=16).grid(row=0, column=0, sticky="w", pady=2)
        self.entry = ttk.Entry(self, textvariable=self.value)
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, PADDING), pady=2)
        ttk.Button(self, text="Durchsuchen ...", command=self.browse, width=16).grid(
            row=0, column=2, pady=2)

        self.hint_label = ttk.Label(self, text=hint, foreground="#666666")
        self.hint_label.grid(row=1, column=1, sticky="w", pady=(0, 4))

        if enable_drop(self.entry, self._dropped):
            self.hint_label.configure(
                text=(hint + "  –  oder hier hineinziehen").strip(" –"))

    def _dropped(self, paths: List[str]) -> None:
        if not paths:
            return
        path = paths[0]
        if self.mode == "folder" and os.path.isfile(path):
            path = os.path.dirname(path)   # Datei abgelegt -> Ordner nehmen
        self.value.set(path)

    def browse(self) -> None:
        start = self.get() or os.path.expanduser("~")
        if os.path.isfile(start):
            start = os.path.dirname(start)
        if self.mode == "folder":
            chosen = filedialog.askdirectory(title="Ordner auswählen", initialdir=start)
        elif self.mode == "save":
            chosen = filedialog.asksaveasfilename(
                title="Video speichern unter", initialdir=os.path.dirname(start) or start,
                initialfile=os.path.basename(start) or "AutoCut_Video.mp4",
                defaultextension=".mp4", filetypes=self.filetypes)
        else:
            chosen = filedialog.askopenfilename(
                title="Datei auswählen", initialdir=start, filetypes=self.filetypes)
        if chosen:
            self.value.set(chosen)

    def get(self) -> str:
        return self.value.get().strip().strip('"')

    def set(self, value: str) -> None:
        self.value.set(value or "")

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in self.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass


# ---------------------------------------------------------------------------
# Fehlerdialog in Klartext
# ---------------------------------------------------------------------------

class ErrorDialog(tk.Toplevel):
    """Verständliches Fehlerfenster: Titel, Klartext, optionale Details."""

    def __init__(self, parent, title: str, message: str, details: str = ""):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.minsize(520, 220)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(frame, text="⚠", font=("Segoe UI", 26)).grid(
            row=0, column=0, rowspan=2, sticky="n", padx=(0, 14))
        ttk.Label(frame, text=title, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=1, sticky="w")

        text = tk.Text(frame, wrap="word", height=9, width=64, relief="flat",
                       background=self.cget("background"), borderwidth=0)
        text.insert("1.0", message)
        text.configure(state="disabled")
        text.grid(row=1, column=1, sticky="nsew", pady=(8, 12))

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=1, sticky="e")
        if details:
            ttk.Button(buttons, text="Technische Details",
                       command=lambda: self._show_details(details)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Schließen", command=self.destroy).pack(side="left", padx=4)

        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self, parent)
        self.grab_set()

    def _show_details(self, details: str) -> None:
        window = tk.Toplevel(self)
        window.title("Technische Details")
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="none", height=22, width=100)
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll_y.set)
        text.insert("1.0", details)
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")
        center_window(window, self)


def show_error(parent, error: Exception) -> None:
    """Zeigt einen Fehler verständlich an – nie als roher Traceback."""
    from autocut.errors import AutoCutError

    if isinstance(error, AutoCutError):
        ErrorDialog(parent, error.title, error.full_text())
        return

    import traceback

    ErrorDialog(
        parent,
        "Unerwarteter Fehler",
        "Beim Verarbeiten ist ein unerwarteter Fehler aufgetreten:\n\n"
        f"{type(error).__name__}: {error}\n\n"
        "Bitte versuche es mit anderen Clips oder einer anderen Vorlage erneut.",
        details="".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )


def center_window(window: tk.Misc, parent: Optional[tk.Misc] = None) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
    else:
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 3
    window.geometry(f"+{max(0, x)}+{max(0, y)}")


# ---------------------------------------------------------------------------
# Dateien und Ordner im Betriebssystem öffnen
# ---------------------------------------------------------------------------

def open_in_explorer(path: str) -> None:
    """Öffnet den Ordner der Datei und markiert sie, wenn möglich."""
    path = os.path.abspath(path)
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if sys.platform == "win32":
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(folder)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R" if os.path.isfile(path) else folder, path])
    else:
        subprocess.Popen(["xdg-open", folder])


def open_file(path: str) -> None:
    """Öffnet eine Datei mit dem Standardprogramm des Systems."""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
