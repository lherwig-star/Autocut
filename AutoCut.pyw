#!/usr/bin/env python3
"""AutoCut per Doppelklick starten – ohne Konsolenfenster.

Diese Datei prüft beim Start, ob alle benötigten Python-Pakete vorhanden
sind, installiert fehlende automatisch nach und öffnet dann die Oberfläche.
Es muss also nie von Hand 'pip install' ausgeführt werden.

Die Endung .pyw sorgt unter Windows dafür, dass kein schwarzes
Konsolenfenster erscheint (Python startet sie mit pythonw.exe).
"""

from __future__ import annotations

import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Pakete, die AutoCut braucht: (Importname, pip-Name, Zweck)
REQUIRED = [
    ("numpy", "numpy", "Berechnungen"),
    ("yaml", "pyyaml", "Vorlagen"),
    ("librosa", "librosa", "Musik- und Beat-Analyse"),
    ("soundfile", "soundfile", "Audiodateien lesen"),
    ("cv2", "opencv-python", "Video-Analyse"),
]
# Optional: bringt ffmpeg mit, falls es nicht auf dem System installiert ist.
OPTIONAL = [("imageio_ffmpeg", "imageio-ffmpeg", "ffmpeg-Notfallversorgung")]
# Optional: erlaubt Drag & Drop von Ordnern in das Fenster.
OPTIONAL += [("tkinterdnd2", "tkinterdnd2", "Drag & Drop")]

MARKER_FILE = os.path.join(PROJECT_ROOT, ".autocut_setup_done")


def missing_packages(pakete):
    """Liefert alle Pakete aus der Liste, die sich nicht importieren lassen."""
    import importlib.util

    fehlend = []
    for import_name, pip_name, zweck in pakete:
        try:
            if importlib.util.find_spec(import_name) is None:
                fehlend.append((import_name, pip_name, zweck))
        except (ImportError, ValueError):
            fehlend.append((import_name, pip_name, zweck))
    return fehlend


def _no_window_kwargs() -> dict:
    if os.name == "nt":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": info, "creationflags": 0x08000000}
    return {}


def install(pip_names, on_progress=None, stop_on_error: bool = True):
    """Installiert Pakete mit pip. Liefert (Liste der gescheiterten, Ausgabe)."""
    ausgabe = []
    gescheitert = []
    for name in pip_names:
        if on_progress:
            on_progress(f"Installiere {name} ...")
        erfolg = False
        # Erst in den Benutzerordner (braucht keine Administratorrechte),
        # danach ohne --user (nötig in virtuellen Umgebungen).
        for zusatz in (["--user"], []):
            befehl = [sys.executable, "-m", "pip", "install", *zusatz, name]
            try:
                proc = subprocess.run(befehl, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=1200,
                                      **_no_window_kwargs())
                ausgabe.append(f"$ {' '.join(befehl)}\n"
                               + proc.stdout.decode("utf-8", "replace"))
                if proc.returncode == 0:
                    erfolg = True
                    break
            except Exception as fehler:   # kein Netz, kein pip, Zeitüberschreitung
                ausgabe.append(f"{name}: {fehler}")
        if not erfolg:
            gescheitert.append(name)
            if stop_on_error:
                return gescheitert, "\n".join(ausgabe)
    return gescheitert, "\n".join(ausgabe)


def setup_window(fehlend):
    """Kleines Fenster, das den Installationsfortschritt zeigt."""
    import tkinter as tk
    from tkinter import ttk

    fenster = tk.Tk()
    fenster.title("AutoCut – Ersteinrichtung")
    fenster.geometry("560x230")
    fenster.resizable(False, False)

    rahmen = ttk.Frame(fenster, padding=18)
    rahmen.pack(fill="both", expand=True)
    ttk.Label(rahmen, text="AutoCut wird eingerichtet",
              font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(rahmen, wraplength=520, justify="left",
              text="Beim ersten Start werden die benötigten Programmbausteine "
                   "einmalig heruntergeladen. Das dauert je nach Internet-"
                   "verbindung ein paar Minuten.\n\nBenötigt werden:\n  • "
                   + "\n  • ".join(f"{p[1]} ({p[2]})" for p in fehlend)
              ).pack(anchor="w", pady=(8, 12))

    status = ttk.Label(rahmen, text="Vorbereitung ...")
    status.pack(anchor="w")
    balken = ttk.Progressbar(rahmen, mode="indeterminate")
    balken.pack(fill="x", pady=(6, 0))
    balken.start(12)
    return fenster, status


def ensure_packages() -> bool:
    """Sorgt dafür, dass alle Pflichtpakete da sind.

    Rückgabe ``True``  = alles vorhanden, die Oberfläche kann starten.
    Rückgabe ``False`` = es wurde installiert (AutoCut startet sich neu)
    oder die Einrichtung ist gescheitert.

    Die optionalen Pakete werden nur beim allerersten Start versucht. So
    wartet AutoCut später nicht bei jedem Start erneut auf einen Download,
    der vielleicht gar nicht klappt.
    """
    fehlend = missing_packages(REQUIRED)
    erster_start = not os.path.exists(MARKER_FILE)
    optional_fehlend = missing_packages(OPTIONAL) if erster_start else []

    if not fehlend and not optional_fehlend:
        return True

    # Ohne Tkinter ist überhaupt keine Oberfläche möglich.
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("AutoCut braucht Tkinter, das in dieser Python-Installation fehlt.")
        print("Installiere Python von python.org neu und aktiviere dabei die")
        print("Option 'tcl/tk and IDLE'.")
        try:
            input("Zum Beenden Eingabetaste drücken ...")
        except EOFError:
            pass
        return False

    import threading

    fenster, status = setup_window(fehlend or optional_fehlend)
    ergebnis = {}

    def arbeit():
        melden = lambda text: status.configure(text=text)  # noqa: E731
        # Pflichtpakete: bei einem Fehler sofort abbrechen und melden.
        gescheitert, ausgabe = install([p[1] for p in fehlend], melden,
                                       stop_on_error=True)
        # Optionale Pakete: ein Fehler ist kein Beinbruch, einfach weiter.
        if not gescheitert and optional_fehlend:
            install([p[1] for p in optional_fehlend], melden, stop_on_error=False)
        ergebnis["gescheitert"] = gescheitert
        ergebnis["ausgabe"] = ausgabe
        fenster.after(0, fenster.quit)

    threading.Thread(target=arbeit, daemon=True).start()
    fenster.mainloop()
    fenster.destroy()

    # Merken, dass die Ersteinrichtung gelaufen ist – auch wenn optionale
    # Pakete gescheitert sind, damit es beim nächsten Start zügig weitergeht.
    try:
        with open(MARKER_FILE, "w", encoding="utf-8") as handle:
            handle.write("Ersteinrichtung erledigt – diese Datei darf gelöscht werden.\n")
    except OSError:
        pass

    if ergebnis.get("gescheitert"):
        import tkinter as tk
        from tkinter import messagebox

        wurzel = tk.Tk()
        wurzel.withdraw()
        messagebox.showerror(
            "Einrichtung fehlgeschlagen",
            "Diese Programmbausteine konnten nicht installiert werden:\n\n    "
            + "\n    ".join(ergebnis["gescheitert"])
            + "\n\nMögliche Ursachen:\n"
              "  • keine Internetverbindung\n"
              "  • eine Firewall blockiert den Download\n\n"
              "Du kannst sie auch von Hand installieren. Öffne dazu das "
              "Windows-Terminal und gib ein:\n\n    pip install "
            + " ".join(ergebnis["gescheitert"]))
        wurzel.destroy()
        return False

    # Neu starten, damit die frisch installierten Pakete geladen werden.
    subprocess.Popen([sys.executable] + sys.argv, cwd=PROJECT_ROOT, close_fds=True)
    return False


def main() -> int:
    if not ensure_packages():
        return 1
    from gui.app import launch

    return launch()


if __name__ == "__main__":
    sys.exit(main())
