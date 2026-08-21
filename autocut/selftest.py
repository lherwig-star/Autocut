"""Selbsttest: prüft, ob AutoCut auf diesem Rechner vollständig funktioniert.

Aufruf:  python autocut.py --selftest

Geprüft wird der Reihe nach:
1. Python-Version
2. alle benötigten Programmbausteine (Pakete) inklusive Version
3. ffmpeg und ffprobe
4. Erzeugen kleiner Testdaten (Song + drei Clips)
5. ein kompletter Durchlauf inklusive Rendern, danach Prüfung des Ergebnisses

Es wird nichts heruntergeladen und nichts dauerhaft gespeichert – die
Testdaten liegen in einem temporären Ordner und werden danach gelöscht.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from typing import Callable, List, Optional

MIN_PYTHON = (3, 9)

# (Importname, Anzeigename, Zweck)
REQUIRED_PACKAGES = [
    ("numpy", "numpy", "Berechnungen"),
    ("yaml", "pyyaml", "Vorlagen"),
    ("librosa", "librosa", "Musik- und Beat-Analyse"),
    ("soundfile", "soundfile", "Audiodateien lesen"),
    ("cv2", "opencv-python", "Video-Analyse"),
]

OK = "OK"
FEHLT = "FEHLT"
HINWEIS = "HINWEIS"


class Report:
    """Sammelt die Ergebnisse und gibt sie sauber ausgerichtet aus."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self.write = write
        self.failures: List[str] = []
        self.notes: List[str] = []

    LABEL_WIDTH = 36

    def line(self, label: str, status: str, detail: str = "") -> None:
        if len(label) > self.LABEL_WIDTH - 2:
            label = label[: self.LABEL_WIDTH - 3] + "…"
        punkte = "." * (self.LABEL_WIDTH - len(label))
        self.write(f"  {label} {punkte} {status:<7} {detail}".rstrip())
        if status == FEHLT:
            self.failures.append(f"{label}: {detail}")
        elif status == HINWEIS:
            self.notes.append(f"{label}: {detail}")

    def step(self, number: int, total: int, title: str) -> None:
        self.write("")
        self.write(f"[{number}/{total}] {title}")

    @property
    def ok(self) -> bool:
        return not self.failures


def run_selftest(write: Optional[Callable[[str], None]] = None,
                 keep_output: bool = False) -> bool:
    """Führt den kompletten Selbsttest aus. Rückgabe: True = alles in Ordnung."""
    write = write or (lambda text: print(text, flush=True))
    report = Report(write)

    write("=" * 72)
    write("AutoCut – Selbsttest")
    write("=" * 72)

    total = 5
    report.step(1, total, "Python")
    _check_python(report)

    report.step(2, total, "Programmbausteine (Python-Pakete)")
    pakete_ok = _check_packages(report)

    report.step(3, total, "ffmpeg")
    ffmpeg_ok = _check_ffmpeg(report)

    arbeitsordner = None
    try:
        if not (pakete_ok and ffmpeg_ok):
            report.step(4, total, "Testdaten erzeugen")
            report.line("übersprungen", HINWEIS, "erst die Punkte oben beheben")
            report.step(5, total, "Kompletter Durchlauf")
            report.line("übersprungen", HINWEIS, "erst die Punkte oben beheben")
        else:
            report.step(4, total, "Testdaten erzeugen")
            arbeitsordner = tempfile.mkdtemp(prefix="autocut_selbsttest_")
            daten = _make_testdata(report, arbeitsordner)

            report.step(5, total, "Kompletter Durchlauf (Analyse + Rendern)")
            _run_pipeline(report, daten, arbeitsordner)
    except Exception as fehler:  # nichts darf den Selbsttest sprengen
        report.line("unerwarteter Fehler", FEHLT, f"{type(fehler).__name__}: {fehler}")
    finally:
        if arbeitsordner and not keep_output:
            shutil.rmtree(arbeitsordner, ignore_errors=True)

    _summary(report, write)
    return report.ok


# ---------------------------------------------------------------------------
# Einzelne Prüfungen
# ---------------------------------------------------------------------------

def _check_python(report: Report) -> None:
    version = ".".join(str(t) for t in sys.version_info[:3])
    if sys.version_info < MIN_PYTHON:
        report.line("Version", FEHLT,
                    f"{version} ist zu alt – benötigt wird "
                    f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} oder neuer")
    else:
        report.line("Version", OK, version)
    report.line("Programmdatei", OK, sys.executable)

    import importlib.util

    if importlib.util.find_spec("tkinter") is not None:
        report.line("Tkinter (Oberfläche)", OK, "vorhanden")
    else:
        report.line("Tkinter (Oberfläche)", FEHLT,
                    "fehlt – Python neu installieren und dabei 'tcl/tk and IDLE' "
                    "aktivieren (die Kommandozeile funktioniert trotzdem)")


def _check_packages(report: Report) -> bool:
    alle_da = True
    for import_name, anzeige, zweck in REQUIRED_PACKAGES:
        try:
            modul = __import__(import_name)
            version = getattr(modul, "__version__", "")
            report.line(f"{anzeige} ({zweck})", OK, str(version))
        except Exception as fehler:
            alle_da = False
            report.line(f"{anzeige} ({zweck})", FEHLT,
                        f"nicht ladbar – 'pip install {anzeige}' ({fehler})")
    return alle_da


def _check_ffmpeg(report: Report) -> bool:
    from .ffmpeg_tools import ffprobe_path, have_ffmpeg, version_string

    if not have_ffmpeg():
        report.line("ffmpeg", FEHLT,
                    "nicht gefunden – im Terminal 'winget install ffmpeg' ausführen")
        return False

    from .ffmpeg_tools import ffmpeg_path

    report.line("ffmpeg", OK, version_string()[:52])
    report.line("ffmpeg-Pfad", OK, ffmpeg_path())

    probe = ffprobe_path()
    if probe:
        report.line("ffprobe", OK, probe)
    else:
        report.line("ffprobe", HINWEIS,
                    "nicht gefunden – AutoCut nutzt stattdessen OpenCV (funktioniert)")
    return True


# ---------------------------------------------------------------------------
# Testdaten: ein kurzer Klick-Track und drei winzige Clips
# ---------------------------------------------------------------------------

def _make_testdata(report: Report, ordner: str) -> dict:
    from .ffmpeg_tools import ffmpeg_path

    clips_ordner = os.path.join(ordner, "clips")
    os.makedirs(clips_ordner, exist_ok=True)

    song = _write_click_track(os.path.join(ordner, "testsong.wav"))
    report.line("Test-Song (120 BPM, 8s)", OK, os.path.basename(song))

    ffmpeg = ffmpeg_path()
    clips = []
    quellen = [("testsrc2", "null"), ("smptebars", "null"), ("testsrc2", "hue=s=1.4")]
    for nummer, (quelle, filter_kette) in enumerate(quellen, start=1):
        ziel = os.path.join(clips_ordner, f"clip_{nummer:02d}.mp4")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
             "-i", f"{quelle}=size=320x180:rate=30:duration=5",
             "-vf", filter_kette, "-c:v", "libx264", "-preset", "ultrafast",
             "-pix_fmt", "yuv420p", ziel],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **_no_window(),
        )
        clips.append(ziel)
    report.line("Testclips (3 x 5s)", OK, "erzeugt")
    return {"clips_dir": clips_ordner, "music": song, "clips": clips}


def _write_click_track(pfad: str, bpm: float = 120.0, dauer: float = 8.0,
                       sr: int = 22050) -> str:
    """Erzeugt einen kurzen Song mit klarem Takt – ohne Zusatzpakete."""
    import numpy as np

    anzahl = int(dauer * sr)
    zeit = np.arange(anzahl) / sr
    ton = 0.15 * np.sin(2 * np.pi * 55.0 * zeit)

    takt = 60.0 / bpm
    schlag = 0.0
    while schlag < dauer:
        start = int(schlag * sr)
        ende = min(anzahl, start + int(0.06 * sr))
        if ende > start:
            lokal = np.arange(ende - start) / sr
            huelle = np.exp(-lokal * 60.0)
            betont = round(schlag / takt) % 4 == 0
            ton[start:ende] += huelle * np.sin(
                2 * np.pi * (180.0 if betont else 900.0) * lokal) * (1.0 if betont else 0.6)
        schlag += takt

    spitze = float(np.max(np.abs(ton))) or 1.0
    pcm = (ton / spitze * 0.9 * 32767).astype("<i2")
    with wave.open(pfad, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(sr)
        datei.writeframes(pcm.tobytes())
    return pfad


# ---------------------------------------------------------------------------
# Kompletter Durchlauf
# ---------------------------------------------------------------------------

def _run_pipeline(report: Report, daten: dict, ordner: str) -> None:
    from .pipeline import run_autocut
    from .templates import load_template

    vorlage = load_template("energetic")
    # Klein und schnell – es geht nur darum, dass die Kette durchläuft.
    vorlage.data["output"].update(width=480, height=270, fps=30, preset="ultrafast")

    ziel = os.path.join(ordner, "selbsttest_video.mp4")
    letzte_meldung = {"text": ""}

    def fortschritt(anteil: float, text: str) -> None:
        letzte_meldung["text"] = text

    start = time.time()
    ergebnis = run_autocut(
        clips_folder=daten["clips_dir"],
        music_path=daten["music"],
        template_name=vorlage,
        output_path=ziel,
        progress=fortschritt,
        write_report=False,
    )
    gebraucht = time.time() - start

    report.line("Analyse und Rendern", OK,
                f"{len(ergebnis.plan.moments)} Schnitte in {gebraucht:.1f}s")
    _verify_output(report, ergebnis)


def _verify_output(report: Report, ergebnis) -> None:
    from .ffmpeg_tools import ffmpeg_path, probe

    pfad = ergebnis.output_path
    if not os.path.isfile(pfad):
        report.line("Videodatei", FEHLT, "wurde nicht geschrieben")
        return
    groesse = os.path.getsize(pfad)
    report.line("Videodatei", OK, f"{groesse / 1024:.0f} KB")

    info = probe(pfad)
    report.line("Bildformat", OK, f"{info.width}x{info.height}, {info.fps:.0f} Bilder/s")

    erwartet = ergebnis.plan.total_duration
    abweichung = abs(info.duration - erwartet)
    if abweichung > 0.5:
        report.line("Länge", HINWEIS,
                    f"{info.duration:.2f}s statt geplanter {erwartet:.2f}s")
    else:
        report.line("Länge", OK, f"{info.duration:.2f}s wie geplant")

    # Tonspur prüfen (ohne ffprobe: über die Meldungen von ffmpeg)
    ausgabe = subprocess.run(
        [ffmpeg_path(), "-i", pfad, "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_no_window(),
    ).stderr.decode("utf-8", "replace")
    if "Audio:" in ausgabe:
        report.line("Tonspur (Musik)", OK, "vorhanden")
    else:
        report.line("Tonspur (Musik)", FEHLT, "im fertigen Video fehlt die Musik")

    # Reihenfolge-Zusage noch einmal am echten Ergebnis prüfen
    try:
        ergebnis.plan.check_order()
        report.line("Reihenfolge der Clips", OK, "chronologisch, unverändert")
    except AssertionError as fehler:
        report.line("Reihenfolge der Clips", FEHLT, str(fehler))


def _no_window() -> dict:
    if os.name == "nt":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": info, "creationflags": 0x08000000}
    return {}


# ---------------------------------------------------------------------------
# Zusammenfassung
# ---------------------------------------------------------------------------

def _summary(report: Report, write) -> None:
    write("")
    write("=" * 72)
    if report.ok:
        write("ERGEBNIS: AutoCut funktioniert auf diesem Rechner.")
        if report.notes:
            write("")
            write("Hinweise (kein Problem, nur zur Information):")
            for note in report.notes:
                write(f"  • {note}")
        write("")
        write("Nächster Schritt: AutoCut.pyw doppelklicken und loslegen.")
    else:
        write("ERGEBNIS: Es fehlt noch etwas.")
        write("")
        write("Bitte zuerst beheben:")
        for fehler in report.failures:
            write(f"  • {fehler}")
        write("")
        write("Danach den Selbsttest erneut ausführen:")
        write("    python autocut.py --selftest")
    write("=" * 72)
