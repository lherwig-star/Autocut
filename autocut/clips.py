"""Videoclips finden und chronologisch sortieren.

Die Reihenfolge wird hier einmal festgelegt und danach NIE mehr verändert –
alle weiteren Schritte arbeiten mit dieser Liste in genau dieser Reihenfolge.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .errors import NoClipsFoundError
from .ffmpeg_tools import MediaInfo, probe

VIDEO_EXTENSIONS = (
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".wmv", ".webm", ".3gp", ".flv",
)

# Dateinamen wie IMG_20240715_183000.mp4 oder VID-20240715-WA0002.mp4
_DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_ T]?(\d{2})?(\d{2})?(\d{2})?")


@dataclass
class Clip:
    """Ein Eingangsclip mit allem, was für die Sortierung nötig ist."""

    path: str
    index: int
    info: MediaInfo
    sort_key: str
    sort_reason: str

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def duration(self) -> float:
        return self.info.duration


def find_video_files(folder: str, recursive: bool = False) -> List[str]:
    """Alle Videodateien in einem Ordner (optional inkl. Unterordner)."""
    if not os.path.isdir(folder):
        raise NoClipsFoundError(
            f"Der Ordner '{folder}' existiert nicht.",
            "Bitte wähle den Ordner aus, in dem deine Videoclips liegen.",
        )
    files: List[str] = []
    if recursive:
        for root, _dirs, names in os.walk(folder):
            files += [os.path.join(root, n) for n in names
                      if n.lower().endswith(VIDEO_EXTENSIONS) and not n.startswith(".")]
    else:
        files = [os.path.join(folder, n) for n in os.listdir(folder)
                 if n.lower().endswith(VIDEO_EXTENSIONS) and not n.startswith(".")]
    return [f for f in files if os.path.isfile(f)]


def _creation_time_key(info: MediaInfo, path: str) -> tuple[Optional[str], str]:
    """Aufnahmezeitpunkt aus Metadaten, sonst aus dem Dateinamen, sonst None."""
    raw = info.creation_time
    if raw:
        cleaned = str(raw).replace("Z", "+00:00")
        try:
            stamp = datetime.fromisoformat(cleaned)
            return stamp.strftime("%Y%m%d%H%M%S"), "Aufnahmedatum (Metadaten)"
        except ValueError:
            pass

    match = _DATE_IN_NAME.search(os.path.basename(path))
    if match:
        parts = [p or "00" for p in match.groups()]
        return "".join(parts), "Datum aus Dateiname"
    return None, ""


def load_clips(
    folder: str,
    recursive: bool = False,
    order: str = "auto",
    progress=None,
) -> List[Clip]:
    """Liest alle Clips ein und sortiert sie chronologisch.

    order:
      * "auto"     – Aufnahmedatum aus den Metadaten, sonst Dateiname
      * "name"     – nur nach Dateiname (natürliche Sortierung: 2 vor 10)
      * "date"     – nur nach Aufnahmedatum/Änderungsdatum
    """
    files = find_video_files(folder, recursive=recursive)
    if not files:
        raise NoClipsFoundError(
            f"Im Ordner '{folder}' wurden keine Videodateien gefunden.",
            "Unterstützte Formate: " + ", ".join(e.lstrip(".").upper() for e in VIDEO_EXTENSIONS)
            + "\n\nLiegen die Videos in Unterordnern? Dann aktiviere die Option "
              "'Unterordner einbeziehen'.",
        )

    files.sort(key=lambda p: _natural_key(os.path.basename(p)))

    # Schritt 1: alle Dateien einlesen und ihre möglichen Sortierschlüssel bestimmen.
    entries = []
    skipped: List[str] = []
    total = len(files)
    for i, path in enumerate(files):
        if progress:
            progress(i / max(1, total), f"Lese Clip {i + 1}/{total}: {os.path.basename(path)}")
        try:
            info = probe(path)
        except Exception:
            skipped.append(os.path.basename(path))
            continue
        if not info.is_valid:
            skipped.append(os.path.basename(path))
            continue
        date_key, reason = _creation_time_key(info, path)
        entries.append((path, info, date_key, reason))

    if not entries:
        raise NoClipsFoundError(
            f"Im Ordner '{folder}' konnte keine der {len(files)} Dateien gelesen werden.",
            "Die Dateien sind eventuell beschädigt oder in einem Format, das ffmpeg "
            "auf diesem Computer nicht unterstützt.",
        )

    # Schritt 2: EINE Sortierart für alle Clips festlegen.
    # Wichtig: Aufnahmedatum und Dateiname dürfen nicht gemischt werden – sonst
    # kämen alle Clips mit Datum vor allen anderen, unabhängig davon, wann sie
    # tatsächlich aufgenommen wurden.
    alle_mit_datum = all(eintrag[2] for eintrag in entries)
    if order == "date":
        modus = "date"
    elif order == "name":
        modus = "name"
    else:  # auto: Datum nur, wenn es für ALLE Clips vorliegt
        modus = "date" if alle_mit_datum else "name"

    clips: List[Clip] = []
    for path, info, date_key, reason in entries:
        if modus == "date":
            key = date_key or datetime.fromtimestamp(
                os.path.getmtime(path)).strftime("%Y%m%d%H%M%S")
            why = reason or "Änderungsdatum der Datei"
        else:
            key = _natural_key_string(os.path.basename(path))
            why = ("Dateiname" if alle_mit_datum or order == "name"
                   else "Dateiname (nicht alle Clips haben ein Aufnahmedatum)")
        clips.append(Clip(path=path, index=0, info=info, sort_key=key, sort_reason=why))

    # Chronologisch sortieren. Bei gleichem Schlüssel entscheidet der Dateiname,
    # damit die Reihenfolge bei jedem Lauf identisch (deterministisch) ist.
    clips.sort(key=lambda c: (c.sort_key, _natural_key_string(c.name)))
    for position, clip in enumerate(clips):
        clip.index = position

    if progress:
        note = f" ({len(skipped)} übersprungen)" if skipped else ""
        progress(1.0, f"{len(clips)} Clips eingelesen{note}")
    return clips


def _natural_key(name: str):
    """Sortierschlüssel, bei dem 'clip2' vor 'clip10' kommt."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name)]


def _natural_key_string(name: str) -> str:
    """Wie _natural_key, aber als vergleichbarer String (Zahlen aufgefüllt)."""
    parts = re.split(r"(\d+)", name.lower())
    return "".join(p.zfill(10) if p.isdigit() else p for p in parts)


def total_duration(clips: List[Clip]) -> float:
    return sum(c.duration for c in clips)
