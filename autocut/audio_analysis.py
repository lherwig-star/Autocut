"""Musik-Analyse mit librosa: Tempo, Beat-Zeitpunkte und Energie-Kurve.

Läuft vollständig offline. Ergebnis ist ein ``MusicAnalysis``-Objekt, das
die Schnittlogik braucht:

* ``beats``   – Zeitpunkte aller Beats in Sekunden
* ``energy_at(t)`` – Energie des Songs an Stelle t, normiert auf 0..1
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .errors import MissingDependencyError, MusicFileError

# Analyse-Abtastrate: für Beat-Erkennung völlig ausreichend und schnell.
ANALYSIS_SR = 22050


@dataclass
class MusicAnalysis:
    path: str
    duration: float
    tempo: float
    beats: List[float] = field(default_factory=list)
    energy_times: List[float] = field(default_factory=list)
    energy_values: List[float] = field(default_factory=list)
    sample_rate: int = ANALYSIS_SR

    # -- Energie ---------------------------------------------------------
    def energy_at(self, time_s: float) -> float:
        """Energie (0..1) an der Stelle ``time_s`` – linear interpoliert."""
        if not self.energy_values:
            return 0.5
        if time_s <= self.energy_times[0]:
            return self.energy_values[0]
        if time_s >= self.energy_times[-1]:
            return self.energy_values[-1]
        # Gleichmäßiges Raster -> direkter Index statt Suche.
        step = self.energy_times[1] - self.energy_times[0]
        idx = int(time_s / step) if step > 0 else 0
        idx = max(0, min(idx, len(self.energy_values) - 2))
        t0, t1 = self.energy_times[idx], self.energy_times[idx + 1]
        if t1 <= t0:
            return self.energy_values[idx]
        frac = (time_s - t0) / (t1 - t0)
        return (1.0 - frac) * self.energy_values[idx] + frac * self.energy_values[idx + 1]

    def energy_between(self, start: float, end: float) -> float:
        """Mittlere Energie im Zeitfenster [start, end]."""
        if end <= start:
            return self.energy_at(start)
        steps = max(2, min(24, int((end - start) * 8)))
        values = [self.energy_at(start + (end - start) * i / (steps - 1)) for i in range(steps)]
        return sum(values) / len(values)

    # -- Beats -----------------------------------------------------------
    @property
    def beat_period(self) -> float:
        """Durchschnittlicher Abstand zweier Beats in Sekunden."""
        if len(self.beats) >= 2:
            return (self.beats[-1] - self.beats[0]) / (len(self.beats) - 1)
        return 60.0 / self.tempo if self.tempo > 0 else 0.5

    def next_beat_index(self, time_s: float) -> int:
        """Index des ersten Beats, der nicht vor ``time_s`` liegt."""
        import bisect

        return bisect.bisect_left(self.beats, time_s)

    def summary(self) -> str:
        return (f"{os.path.basename(self.path)}: {self.duration:.1f}s, "
                f"{self.tempo:.1f} BPM, {len(self.beats)} Beats")


def analyze_music(
    path: str,
    max_duration: Optional[float] = None,
    progress=None,
) -> MusicAnalysis:
    """Analysiert eine Musikdatei (MP3/WAV/M4A/FLAC/OGG...) lokal mit librosa."""
    if not os.path.isfile(path):
        raise MusicFileError(
            f"Die Musikdatei '{path}' wurde nicht gefunden.",
            "Bitte wähle eine vorhandene MP3- oder WAV-Datei aus.",
        )
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise MissingDependencyError("librosa", "die Musik-Analyse") from exc

    if progress:
        progress(0.05, "Musik wird geladen ...")

    try:
        y, sr = librosa.load(path, sr=ANALYSIS_SR, mono=True, duration=max_duration)
    except Exception as exc:
        raise MusicFileError(
            f"Die Musikdatei '{os.path.basename(path)}' konnte nicht gelesen werden.",
            "Unterstützt werden MP3, WAV, M4A, FLAC und OGG. Bei MP3 muss ffmpeg "
            "installiert sein.\n\nTechnische Meldung: " + str(exc),
        ) from exc

    if y is None or len(y) < sr * 0.5:
        raise MusicFileError(
            f"Die Musikdatei '{os.path.basename(path)}' ist zu kurz oder leer.",
            "Bitte nutze einen Song von mindestens einer Sekunde Länge.",
        )

    duration = float(len(y) / sr)

    if progress:
        progress(0.4, "Beats werden erkannt ...")

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, trim=False, units="frames"
    )
    tempo = float(np.atleast_1d(tempo)[0])
    beats = [float(t) for t in librosa.frames_to_time(beat_frames, sr=sr)]

    # Notfallraster: Wenn die Beat-Erkennung versagt (z.B. reine Ambient-Musik),
    # wird ein gleichmäßiges Raster aus dem Tempo erzeugt, damit AutoCut
    # trotzdem ein Ergebnis liefert.
    if len(beats) < 4:
        period = 60.0 / tempo if tempo and tempo > 0 else 0.5
        count = max(4, int(duration / period))
        beats = [i * period for i in range(count + 1) if i * period < duration]
        if tempo <= 0:
            tempo = 60.0 / period

    beats = _extend_beats_to_end(beats, duration)

    if progress:
        progress(0.75, "Energie-Kurve wird berechnet ...")

    energy_times, energy_values = _energy_curve(y, sr, onset_env, duration)

    if progress:
        progress(1.0, "Musik-Analyse fertig")

    return MusicAnalysis(
        path=path,
        duration=duration,
        tempo=float(tempo),
        beats=beats,
        energy_times=energy_times,
        energy_values=energy_values,
        sample_rate=sr,
    )


def _extend_beats_to_end(beats: List[float], duration: float) -> List[float]:
    """Setzt das Beat-Raster bis zum Songende fort (librosa endet oft früher)."""
    if len(beats) < 2:
        return beats
    period = (beats[-1] - beats[0]) / (len(beats) - 1)
    if period <= 0:
        return beats
    out = list(beats)
    # nach hinten
    t = out[-1] + period
    while t < duration:
        out.append(t)
        t += period
    # nach vorne (Intro vor dem ersten erkannten Beat)
    t = out[0] - period
    while t > 0.0:
        out.insert(0, t)
        t -= period
    return out


def _energy_curve(y, sr, onset_env, duration: float):
    """Kombiniert Lautstärke (RMS) und Onset-Stärke zu einer 0..1-Kurve.

    Die Kurve entscheidet später, ob eine Songstelle 'leise' (lange Clips)
    oder 'laut/Drop' (kurze Clips) ist.
    """
    import librosa  # type: ignore
    import numpy as np  # type: ignore

    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]

    onset = np.asarray(onset_env, dtype=float)
    if len(onset) != len(rms):
        # auf gemeinsame Länge bringen
        target = min(len(onset), len(rms))
        if target == 0:
            times = [0.0, max(duration, 0.1)]
            return times, [0.5, 0.5]
        onset = np.interp(
            np.linspace(0, len(onset) - 1, target), np.arange(len(onset)), onset
        )
        rms = rms[:target]

    def norm(values):
        values = np.asarray(values, dtype=float)
        low = float(np.percentile(values, 5))
        high = float(np.percentile(values, 95))
        if high - low < 1e-9:
            return np.full_like(values, 0.5)
        return np.clip((values - low) / (high - low), 0.0, 1.0)

    combined = 0.65 * norm(rms) + 0.35 * norm(onset)

    # Glätten über ca. 1.5 Sekunden, damit einzelne Schläge die Kurve
    # nicht als "lauten Abschnitt" erscheinen lassen.
    window = max(3, int(1.5 * sr / hop))
    if window % 2 == 0:
        window += 1
    if len(combined) > window:
        kernel = np.hanning(window)
        kernel /= kernel.sum()
        padded = np.pad(combined, window // 2, mode="edge")
        combined = np.convolve(padded, kernel, mode="valid")[: len(rms)]

    combined = norm(combined)
    times = librosa.frames_to_time(np.arange(len(combined)), sr=sr, hop_length=hop)
    return [float(t) for t in times], [float(v) for v in combined]


def format_time(seconds: float) -> str:
    """Sekunden als mm:ss.s – für Report und Oberfläche."""
    if seconds is None or (isinstance(seconds, float) and math.isnan(seconds)):
        return "--:--"
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    return f"{minutes:02d}:{seconds - minutes * 60:04.1f}"
