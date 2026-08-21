"""AutoCut – Desktop-Oberfläche.

Bedienung ohne Kommandozeile: Ordner wählen, Musik wählen, Vorlage wählen,
auf "Video erstellen" klicken. Die Verarbeitung läuft in einem eigenen
Thread, damit das Fenster jederzeit bedienbar bleibt.

Diese Datei enthält NUR Bedienung und Anzeige. Die gesamte Verarbeitung
steckt in ``autocut.pipeline`` – deshalb genügt nach Änderungen an der
Logik ein Klick auf "Neu laden".
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Optional

# Projektordner in den Suchpfad, damit der Start per Doppelklick funktioniert.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gui.widgets import (  # noqa: E402
    PADDING, ErrorDialog, PathRow, center_window, create_root, open_file,
    open_in_explorer, show_error,
)

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".autocut_settings.json")
MUSIC_TYPES = [("Musikdateien", "*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.wma"),
               ("Alle Dateien", "*.*")]
VIDEO_TYPES = [("MP4-Video", "*.mp4"), ("Alle Dateien", "*.*")]


class AutoCutApp:
    """Das Hauptfenster."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.messages: queue.Queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.result = None
        self.started_at = 0.0
        self.templates = []

        root.title("AutoCut – automatischer Videoschnitt")
        # Fenstergröße an den Bildschirm anpassen: auf kleinen Notebooks soll
        # das Fenster nicht über den Bildschirmrand hinausragen.
        breite = min(940, max(760, root.winfo_screenwidth() - 120))
        hoehe = min(880, max(600, root.winfo_screenheight() - 120))
        root.geometry(f"{breite}x{hoehe}")
        root.minsize(740, 560)
        self._setup_style()

        container = ttk.Frame(root, padding=(PADDING + 2, PADDING))
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(5, weight=1)   # Reiterbereich wächst mit

        self._build_header(container)
        self._build_inputs(container)
        self._build_action(container)
        self._build_progress(container)
        self._build_output(container)
        self._build_footer(container)

        self.load_templates()
        self.load_settings()
        self.check_environment()
        self.update_ready_state()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(80, self.poll_messages)

    # -- Aufbau der Oberfläche ------------------------------------------

    def _setup_style(self) -> None:
        style = ttk.Style()
        # "vista" unter Windows, sonst das jeweils beste verfügbare Thema.
        for theme in ("vista", "winnative", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=10)
        style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("Sub.TLabel", foreground="#555555")
        style.configure("Status.TLabel", font=("Segoe UI", 10))

    def _build_header(self, parent) -> None:
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(0, PADDING))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="AutoCut", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, style="Sub.TLabel",
                  text="Schneidet deine Videoclips automatisch auf die Beats "
                       "eines Songs – alles offline auf deinem Rechner."
                  ).grid(row=1, column=0, sticky="w")

        self.warning_label = ttk.Label(header, foreground="#a04000", wraplength=820)
        self.warning_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.warning_label.grid_remove()   # belegt keinen Platz, solange leer

    def _build_inputs(self, parent) -> None:
        box = ttk.LabelFrame(parent, text=" 1. Dateien auswählen ", padding=PADDING)
        box.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        box.columnconfigure(0, weight=1)

        self.clips_row = PathRow(
            box, "Clip-Ordner:", mode="folder",
            hint="Ordner mit deinen Videoclips", on_change=self.on_input_change)
        self.clips_row.grid(row=0, column=0, sticky="ew")

        self.music_row = PathRow(
            box, "Musik:", mode="file", filetypes=MUSIC_TYPES,
            hint="MP3, WAV, M4A, FLAC oder OGG", on_change=self.on_input_change)
        self.music_row.grid(row=1, column=0, sticky="ew")

        self.output_row = PathRow(
            box, "Zieldatei:", mode="save", filetypes=VIDEO_TYPES,
            hint="wird beim Erstellen automatisch vorgeschlagen",
            on_change=self.on_input_change)
        self.output_row.grid(row=2, column=0, sticky="ew")

        options = ttk.Frame(box)
        options.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Auch Unterordner durchsuchen",
                        variable=self.recursive).pack(side="left", padx=(0, 20))
        ttk.Label(options, text="Reihenfolge:").pack(side="left", padx=(0, 6))
        self.order = tk.StringVar(value="auto")
        order_box = ttk.Combobox(options, textvariable=self.order, width=10,
                                 state="readonly", values=["auto", "name", "date"])
        order_box.pack(side="left")
        self.order_hint = ttk.Label(options, style="Sub.TLabel", text="")
        self.order_hint.pack(side="left", padx=(10, 0))
        order_box.bind("<<ComboboxSelected>>", lambda _e: self.update_order_hint())
        self.update_order_hint()

        # --- Vorlage ---
        template_box = ttk.LabelFrame(parent, text=" 2. Vorlage wählen ", padding=PADDING)
        template_box.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        template_box.columnconfigure(1, weight=1)

        ttk.Label(template_box, text="Vorlage:", width=16).grid(row=0, column=0, sticky="w")
        self.template_name = tk.StringVar()
        self.template_box = ttk.Combobox(template_box, textvariable=self.template_name,
                                         state="readonly")
        self.template_box.grid(row=0, column=1, sticky="ew", padx=(0, PADDING))
        self.template_box.bind("<<ComboboxSelected>>", lambda _e: self.update_template_info())
        ttk.Button(template_box, text="Vorlagen neu laden", width=18,
                   command=self.load_templates).grid(row=0, column=2)

        self.template_desc = ttk.Label(template_box, style="Sub.TLabel", wraplength=760,
                                       justify="left")
        self.template_desc.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 0))

    def _build_action(self, parent) -> None:
        row = ttk.Frame(parent)
        row.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        row.columnconfigure(0, weight=1)

        self.start_button = ttk.Button(row, text="🎬  Video erstellen",
                                       style="Big.TButton", command=self.start)
        self.start_button.grid(row=0, column=0, sticky="ew")

        self.cancel_button = ttk.Button(row, text="Abbrechen", width=14,
                                        command=self.cancel, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(PADDING, 0))

    def _build_progress(self, parent) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=1000)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.status = ttk.Label(frame, text="Bereit.", style="Status.TLabel")
        self.status.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.timer_label = ttk.Label(frame, text="", style="Sub.TLabel")
        self.timer_label.grid(row=1, column=1, sticky="e", pady=(3, 0))

    def _build_output(self, parent) -> None:
        self.tabs = ttk.Notebook(parent)
        self.tabs.grid(row=5, column=0, sticky="nsew", pady=(PADDING, 6))

        self.log_text = self._make_text_tab("Verlauf")
        self.report_text = self._make_text_tab("Report (welche Momente wurden gewählt?)")
        self.log("AutoCut ist bereit.")
        self.log("Wähle einen Clip-Ordner, eine Musikdatei und eine Vorlage.")

    def _make_text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=title)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        text = tk.Text(frame, wrap="none", height=6, font=("Consolas", 9),
                       background="#fbfbfb", relief="flat", borderwidth=1)
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set,
                       state="disabled")
        text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        return text

    def _build_footer(self, parent) -> None:
        footer = ttk.Frame(parent)
        footer.grid(row=6, column=0, sticky="ew")

        self.open_video_button = ttk.Button(footer, text="▶  Video öffnen", width=18,
                                            command=self.open_video, state="disabled")
        self.open_video_button.pack(side="left")
        self.open_folder_button = ttk.Button(footer, text="📁  Ordner öffnen", width=18,
                                             command=self.open_folder, state="disabled")
        self.open_folder_button.pack(side="left", padx=PADDING)
        self.save_report_button = ttk.Button(footer, text="Report speichern", width=18,
                                             command=self.save_report, state="disabled")
        self.save_report_button.pack(side="left")

        ttk.Button(footer, text="Beenden", width=12,
                   command=self.on_close).pack(side="right")
        ttk.Button(footer, text="🔄  Neu laden", width=14,
                   command=self.reload_app).pack(side="right", padx=PADDING)
        ttk.Button(footer, text="Hilfe", width=10,
                   command=self.show_help).pack(side="right")

    # -- Zustand und Hilfsfunktionen ------------------------------------

    def update_order_hint(self) -> None:
        texte = {
            "auto": "Aufnahmedatum, sonst Dateiname",
            "name": "streng nach Dateiname",
            "date": "streng nach Aufnahmedatum",
        }
        self.order_hint.configure(text=texte.get(self.order.get(), ""))

    def load_templates(self) -> None:
        """Liest den Ordner templates/ neu ein – neue Dateien erscheinen sofort."""
        from autocut.templates import load_all, templates_dir

        vorher = self.template_name.get()
        try:
            self.templates = load_all()
        except Exception as error:  # pragma: no cover - Anzeige im Fehlerfall
            show_error(self.root, error)
            self.templates = []

        namen = [t.name for t in self.templates]
        self.template_box.configure(values=namen)
        if vorher in namen:
            self.template_name.set(vorher)
        elif namen:
            self.template_name.set(namen[0])
        else:
            self.template_name.set("")
            self.show_warning(
                f"Es wurden keine Vorlagen gefunden. Erwartet werden "
                f"YAML-Dateien im Ordner: {templates_dir()}")
        self.update_template_info()
        self.log(f"{len(namen)} Vorlage(n) geladen: {', '.join(namen) or '–'}")

    def update_template_info(self) -> None:
        template = self.current_template()
        if template is None:
            self.template_desc.configure(text="")
            return
        self.template_desc.configure(
            text=f"{template.description}\n{template.summary()}")
        self.update_ready_state()

    def current_template(self):
        name = self.template_name.get()
        return next((t for t in self.templates if t.name == name), None)

    def on_input_change(self) -> None:
        self.update_ready_state()

    def update_ready_state(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        ready = bool(self.clips_row.get() and self.music_row.get()
                     and self.template_name.get())
        self.start_button.configure(state="normal" if ready else "disabled")

    def suggest_output(self) -> str:
        """Schlägt einen Dateinamen neben dem Clip-Ordner vor."""
        clips = self.clips_row.get()
        base = os.path.dirname(clips.rstrip("\\/")) if clips else os.path.expanduser("~")
        if not os.path.isdir(base):
            base = os.path.expanduser("~")
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        name = f"AutoCut_{self.template_name.get() or 'video'}_{stamp}.mp4"
        return os.path.join(base, name)

    def show_warning(self, text: str) -> None:
        """Zeigt die Warnzeile – sie belegt nur Platz, wenn sie etwas sagt."""
        self.warning_label.configure(text=text)
        if text:
            self.warning_label.grid()
        else:
            self.warning_label.grid_remove()

    def check_environment(self) -> None:
        """Prüft beim Start, ob ffmpeg vorhanden ist."""
        from autocut.ffmpeg_tools import have_ffmpeg

        if not have_ffmpeg():
            self.show_warning(
                "⚠ ffmpeg wurde nicht gefunden. Ohne ffmpeg kann AutoCut kein "
                "Video erzeugen. Installiere es im Windows-Terminal mit:  "
                "winget install ffmpeg   (danach AutoCut neu starten)")
            self.log("WARNUNG: ffmpeg nicht gefunden.")
        else:
            self.log("ffmpeg gefunden.")

    # -- Verarbeitung ----------------------------------------------------

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        clips = self.clips_row.get()
        music = self.music_row.get()
        if not os.path.isdir(clips):
            ErrorDialog(self.root, "Ordner nicht gefunden",
                        f"Den Ordner '{clips}' gibt es nicht.\n\n"
                        "Bitte wähle über 'Durchsuchen ...' den Ordner mit deinen "
                        "Videoclips aus.")
            return
        if not os.path.isfile(music):
            ErrorDialog(self.root, "Musikdatei nicht gefunden",
                        f"Die Datei '{music}' gibt es nicht.\n\n"
                        "Bitte wähle über 'Durchsuchen ...' eine MP3- oder WAV-Datei aus.")
            return

        output = self.output_row.get()
        if not output:
            output = self.suggest_output()
            self.output_row.set(output)
        if os.path.isdir(output):
            output = os.path.join(output, os.path.basename(self.suggest_output()))
            self.output_row.set(output)
        if os.path.exists(output):
            if not messagebox.askyesno(
                    "Datei überschreiben?",
                    f"Die Datei\n\n{output}\n\nexistiert bereits. Soll sie "
                    "überschrieben werden?", parent=self.root):
                return

        self.set_running(True)
        # Ergebnis des vorherigen Laufs verwerfen, damit die Knöpfe unten
        # nie auf ein altes Video zeigen.
        self.result = None
        for knopf in (self.open_video_button, self.open_folder_button,
                      self.save_report_button):
            knopf.configure(state="disabled")
        self.clear_text(self.report_text)
        self.log("")
        self.log("=" * 60)
        self.log(f"Start: {datetime.now().strftime('%H:%M:%S')}")
        self.log(f"  Clips   : {clips}")
        self.log(f"  Musik   : {music}")
        self.log(f"  Vorlage : {self.template_name.get()}")
        self.log(f"  Ziel    : {output}")

        self.cancel_event.clear()
        self.started_at = time.time()
        self.worker = threading.Thread(
            target=self._work,
            args=(clips, music, self.template_name.get(), output,
                  self.recursive.get(), self.order.get()),
            daemon=True,
        )
        self.worker.start()

    def _work(self, clips, music, template, output, recursive, order) -> None:
        """Läuft im Hintergrund-Thread – fasst niemals Widgets an."""
        from autocut.pipeline import run_autocut

        try:
            result = run_autocut(
                clips_folder=clips,
                music_path=music,
                template_name=template,
                output_path=output,
                progress=lambda f, m: self.messages.put(("progress", (f, m))),
                should_cancel=self.cancel_event.is_set,
                recursive=recursive,
                order=order,
            )
            self.messages.put(("done", result))
        except BaseException as error:  # an die Oberfläche weiterreichen
            self.messages.put(("error", error))

    def poll_messages(self) -> None:
        """Holt Meldungen des Hintergrund-Threads ab (läuft im GUI-Thread)."""
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "progress":
                    fraction, message = payload
                    self.progress.configure(value=int(fraction * 1000))
                    self.status.configure(text=f"{message}   ({fraction * 100:.0f} %)")
                    if message != getattr(self, "_last_log", None):
                        self.log(f"  {message}")
                        self._last_log = message
                elif kind == "done":
                    self.on_finished(payload)
                elif kind == "error":
                    self.on_failed(payload)
        except queue.Empty:
            pass

        if self.worker and self.worker.is_alive():
            self.timer_label.configure(text=f"{time.time() - self.started_at:.0f}s")
        self.root.after(80, self.poll_messages)

    def on_finished(self, result) -> None:
        self.result = result
        self.set_running(False)
        self.progress.configure(value=1000)
        self.status.configure(text=f"Fertig! Video erstellt in {result.elapsed:.0f} Sekunden.")
        self.timer_label.configure(text=f"{result.elapsed:.0f}s")

        self.set_text(self.report_text, result.report_text)
        self.tabs.select(1)
        self.log("")
        self.log(f"FERTIG in {result.elapsed:.1f}s")
        self.log(f"  Video : {result.output_path}")
        if result.report_path:
            self.log(f"  Report: {result.report_path}")
        for warning in result.warnings:
            self.log(f"  Hinweis: {warning}")

        for button in (self.open_video_button, self.open_folder_button,
                       self.save_report_button):
            button.configure(state="normal")

        hinweise = ("\n\nHinweise:\n• " + "\n• ".join(result.warnings)
                    if result.warnings else "")
        messagebox.showinfo(
            "Video fertig",
            f"Das Video wurde erstellt:\n\n{result.output_path}\n\n"
            f"Länge: {result.duration:.1f} Sekunden, "
            f"{len(result.plan.moments)} Schnitte\n"
            f"Dauer der Verarbeitung: {result.elapsed:.0f} Sekunden{hinweise}",
            parent=self.root)

    def on_failed(self, error: BaseException) -> None:
        from autocut.errors import CancelledError

        self.set_running(False)
        self.progress.configure(value=0)
        if isinstance(error, CancelledError):
            self.status.configure(text="Abgebrochen.")
            self.log("Abgebrochen.")
            return
        self.status.configure(text="Fehlgeschlagen – siehe Meldung.")
        self.log(f"FEHLER: {error}")
        show_error(self.root, error)

    def cancel(self) -> None:
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self.status.configure(text="Wird abgebrochen ...")
            self.cancel_button.configure(state="disabled")

    def set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        for row in (self.clips_row, self.music_row, self.output_row):
            row.set_enabled(not running)
        self.template_box.configure(state="disabled" if running else "readonly")
        if not running:
            self.update_ready_state()
            self.save_settings()

    # -- Ergebnis-Aktionen ------------------------------------------------

    def open_video(self) -> None:
        if self.result and os.path.isfile(self.result.output_path):
            try:
                open_file(self.result.output_path)
            except Exception as error:
                ErrorDialog(self.root, "Video lässt sich nicht öffnen",
                            f"Windows konnte das Video nicht öffnen.\n\n{error}")

    def open_folder(self) -> None:
        if self.result:
            try:
                open_in_explorer(self.result.output_path)
            except Exception as error:
                ErrorDialog(self.root, "Ordner lässt sich nicht öffnen", str(error))

    def save_report(self) -> None:
        from tkinter import filedialog

        if not self.result:
            return
        ziel = filedialog.asksaveasfilename(
            title="Report speichern", defaultextension=".txt",
            initialfile=os.path.basename(self.result.report_path or "autocut_report.txt"),
            filetypes=[("Textdatei", "*.txt"), ("Alle Dateien", "*.*")])
        if ziel:
            with open(ziel, "w", encoding="utf-8") as handle:
                handle.write(self.result.report_text)
            self.log(f"Report gespeichert: {ziel}")

    # -- Neu laden --------------------------------------------------------

    def reload_app(self) -> None:
        """Startet AutoCut neu – übernimmt Code- und Vorlagenänderungen."""
        if self.worker and self.worker.is_alive():
            messagebox.showwarning(
                "Verarbeitung läuft",
                "Es wird gerade ein Video erstellt. Bitte warte, bis es fertig ist, "
                "oder klicke auf 'Abbrechen'.", parent=self.root)
            return
        if not messagebox.askyesno(
                "AutoCut neu laden",
                "AutoCut wird neu gestartet. Dabei werden Programmänderungen und "
                "neue Vorlagen übernommen.\n\nJetzt neu starten?", parent=self.root):
            return

        self.save_settings()
        command = [sys.executable] + sys.argv
        try:
            subprocess.Popen(command, cwd=PROJECT_ROOT, close_fds=True)
        except Exception as error:
            ErrorDialog(self.root, "Neustart fehlgeschlagen",
                        "AutoCut konnte sich nicht selbst neu starten.\n\n"
                        "Bitte schließe das Fenster und starte AutoCut.pyw erneut.",
                        details=str(error))
            return
        self.root.destroy()

    # -- Einstellungen merken --------------------------------------------

    def load_settings(self) -> None:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return
        self.clips_row.set(data.get("clips", ""))
        self.music_row.set(data.get("music", ""))
        if data.get("template") in [t.name for t in self.templates]:
            self.template_name.set(data["template"])
            self.update_template_info()
        self.recursive.set(bool(data.get("recursive", False)))
        if data.get("order") in ("auto", "name", "date"):
            self.order.set(data["order"])
            self.update_order_hint()

    def save_settings(self) -> None:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
                json.dump({
                    "clips": self.clips_row.get(),
                    "music": self.music_row.get(),
                    "template": self.template_name.get(),
                    "recursive": bool(self.recursive.get()),
                    "order": self.order.get(),
                }, handle, indent=2)
        except Exception:
            pass   # Einstellungen sind Komfort – ein Fehler darf nie stören.

    # -- Sonstiges --------------------------------------------------------

    def show_help(self) -> None:
        from autocut.templates import templates_dir

        ErrorDialog(
            self.root, "So funktioniert AutoCut",
            "1. Clip-Ordner wählen – alle Videos darin werden verwendet.\n"
            "   Die Reihenfolge bleibt immer chronologisch erhalten.\n\n"
            "2. Musikdatei wählen (MP3 oder WAV).\n\n"
            "3. Vorlage wählen – sie bestimmt Schnitttempo, Übergänge und Look.\n\n"
            "4. Auf 'Video erstellen' klicken. Die Verarbeitung dauert je nach\n"
            "   Materialmenge einige Minuten.\n\n"
            "Eigene Vorlagen: Kopiere eine YAML-Datei im Ordner\n"
            f"{templates_dir()}\n"
            "unter neuem Namen und passe die Werte an. Über 'Vorlagen neu laden'\n"
            "erscheint sie sofort in der Liste.\n\n"
            "Der Report zeigt für jeden Schnitt, aus welchem Clip er stammt und\n"
            "wie er bewertet wurde.")

    def log(self, text: str) -> None:
        self.append_text(self.log_text, text + "\n")

    def append_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", text)
        widget.see("end")
        widget.configure(state="disabled")

    def set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def clear_text(self, widget: tk.Text) -> None:
        self.set_text(widget, "")

    def on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                    "AutoCut beenden?",
                    "Es wird gerade ein Video erstellt. Wirklich beenden?",
                    parent=self.root):
                return
            self.cancel_event.set()
        self.save_settings()
        self.root.destroy()


def launch() -> int:
    """Startet die Oberfläche. Rückgabewert ist der Beendigungscode."""
    try:
        root = create_root()
    except tk.TclError as error:
        print("Die grafische Oberfläche konnte nicht gestartet werden:", error)
        print("Nutze stattdessen die Kommandozeile: python autocut.py --help")
        return 1

    app = AutoCutApp(root)
    center_window(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_close()
    return 0


if __name__ == "__main__":
    sys.exit(launch())
