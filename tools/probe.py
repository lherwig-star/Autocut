"""Auskunftsstelle für das Einrichtungsskript.

Das Setup-Skript darf Python **nicht** mit ``-c "code"`` aufrufen: Windows
PowerShell 5.1 reicht Anführungszeichen innerhalb eines Arguments unverändert
weiter, wodurch der Code beim Programm zerlegt ankommt. Deshalb liegen alle
Abfragen hier in einer Datei – aufgerufen wird nur mit einzelnen Wörtern:

    python tools/probe.py version    -> z.B. 3.12.4
    python tools/probe.py pfad       -> vollständiger Pfad zu python.exe
    python tools/probe.py tkinter    -> "ja" / "nein"   (Rückgabewert 0 / 1)
    python tools/probe.py pakete     -> Liste aller Pakete (Rückgabewert 0 / 1)
    python tools/probe.py ffmpeg     -> Pfad des ffmpeg, das AutoCut benutzt

Diese Datei kommt mit einem nackten Python aus – sie braucht selbst keine
zusätzlichen Pakete, sonst könnte sie ja nicht prüfen, ob welche fehlen.
"""

from __future__ import annotations

import os
import sys

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (Importname, Anzeigename) – dieselbe Liste wie in autocut/selftest.py
PFLICHT = [
    ("numpy", "numpy"),
    ("yaml", "pyyaml"),
    ("librosa", "librosa"),
    ("soundfile", "soundfile"),
    ("cv2", "opencv-python"),
]
OPTIONAL = [
    ("imageio_ffmpeg", "imageio-ffmpeg"),
    ("tkinterdnd2", "tkinterdnd2"),
]


def frage_version() -> int:
    print("%d.%d.%d" % sys.version_info[:3])
    return 0


def frage_pfad() -> int:
    print(sys.executable or "")
    return 0


def frage_tkinter() -> int:
    import importlib.util

    vorhanden = importlib.util.find_spec("tkinter") is not None
    print("ja" if vorhanden else "nein")
    return 0 if vorhanden else 1


def frage_pakete() -> int:
    import importlib

    fehlt = []
    for modul, name in PFLICHT:
        try:
            geladen = importlib.import_module(modul)
            version = getattr(geladen, "__version__", "")
            print("  OK    %-16s %s" % (name, version))
        except Exception as fehler:
            fehlt.append(name)
            print("  FEHLT %-16s %s" % (name, fehler))
    for modul, name in OPTIONAL:
        try:
            importlib.import_module(modul)
            print("  OK    %-16s (optional)" % name)
        except Exception:
            print("  ---   %-16s (optional, nicht vorhanden)" % name)
    return 1 if fehlt else 0


def frage_ffmpeg() -> int:
    """Welches ffmpeg würde AutoCut benutzen? (auch das per pip mitgelieferte)"""
    if PROJEKT not in sys.path:
        sys.path.insert(0, PROJEKT)
    try:
        from autocut.ffmpeg_tools import ffmpeg_path, have_ffmpeg
    except Exception as fehler:
        print("", file=sys.stdout)
        print("AutoCut-Module nicht ladbar: %s" % fehler, file=sys.stderr)
        return 1
    if not have_ffmpeg():
        print("")
        return 1
    print(ffmpeg_path())
    return 0


ABFRAGEN = {
    "version": frage_version,
    "pfad": frage_pfad,
    "tkinter": frage_tkinter,
    "pakete": frage_pakete,
    "ffmpeg": frage_ffmpeg,
}


def main(argv) -> int:
    wunsch = argv[1].lower() if len(argv) > 1 else ""
    if wunsch not in ABFRAGEN:
        print("Bekannte Abfragen: " + ", ".join(sorted(ABFRAGEN)), file=sys.stderr)
        return 2
    return ABFRAGEN[wunsch]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
