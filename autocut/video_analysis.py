"""Lokale Video-Analyse mit OpenCV – ohne KI, ohne Internet.

Jeder Clip wird in festen Abständen abgetastet. Pro Abtastpunkt werden
messbare Kriterien bestimmt:

* **Schärfe**      – Varianz des Laplacian (unscharfe Bilder -> kleiner Wert)
* **Bewegung**     – mittlere Frame-Differenz + globale Bildverschiebung
* **Belichtung**   – mittlere Helligkeit, Abzug für ausgefressene/abgesoffene Bilder
* **Verwacklung**  – Streuung der globalen Verschiebung (ruckelig vs. sanfter Schwenk)
* **Szenenwechsel**– sehr große Frame-Differenz (harter Schnitt in der Quelle)

Alle Werte werden robust auf 0..1 normiert, damit sie unabhängig von Kamera
und Motiv vergleichbar sind.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from .errors import CancelledError, MissingDependencyError, VideoReadError
from .ffmpeg_tools import MediaInfo

# Analyse-Auflösung: klein genug für Tempo, groß genug für aussagekräftige Schärfe.
ANALYSIS_WIDTH = 320
# Abtastabstand in Sekunden (wird bei sehr langen Clips automatisch vergrößert).
DEFAULT_SAMPLE_INTERVAL = 0.30
MAX_SAMPLES_PER_CLIP = 900


@dataclass
class FrameSample:
    """Messwerte an einem Zeitpunkt des Clips (alle Rohwerte, unnormiert)."""

    time: float
    sharpness: float = 0.0
    brightness: float = 0.0
    clipping: float = 0.0      # Anteil ausgefressener/abgesoffener Pixel
    motion: float = 0.0        # mittlere Frame-Differenz
    shift: float = 0.0         # globale Bildverschiebung in Pixel
    shake: float = 0.0         # Ruckeligkeit der Verschiebung
    scene_change: bool = False


@dataclass
class ClipAnalysis:
    """Das Analyse-Ergebnis eines Clips inklusive normierter Einzelwerte."""

    path: str
    duration: float
    fps: float
    sample_interval: float
    times: List[float] = field(default_factory=list)
    sharpness: List[float] = field(default_factory=list)   # 0..1
    motion: List[float] = field(default_factory=list)      # 0..1
    exposure: List[float] = field(default_factory=list)    # 0..1
    stability: List[float] = field(default_factory=list)   # 0..1
    scene_changes: List[float] = field(default_factory=list)  # Zeitpunkte
    raw: List[FrameSample] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.times)

    def index_at(self, time_s: float) -> int:
        if not self.times or self.sample_interval <= 0:
            return 0
        idx = int(round((time_s - self.times[0]) / self.sample_interval))
        return max(0, min(idx, len(self.times) - 1))

    def average(self, values: Sequence[float]) -> float:
        return float(sum(values) / len(values)) if values else 0.0

    def criteria_means(self) -> dict:
        return {
            "sharpness": self.average(self.sharpness),
            "motion": self.average(self.motion),
            "exposure": self.average(self.exposure),
            "stability": self.average(self.stability),
        }


def analyze_clip(
    path: str,
    info: MediaInfo,
    sample_interval: float = DEFAULT_SAMPLE_INTERVAL,
    progress: Optional[Callable[[float, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ClipAnalysis:
    """Analysiert einen einzelnen Clip und liefert normierte Bewertungskurven."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise MissingDependencyError("opencv-python", "die Video-Analyse") from exc

    duration = max(0.0, float(info.duration))
    if duration <= 0:
        raise VideoReadError(
            f"Der Clip '{os.path.basename(path)}' hat keine erkennbare Länge.")

    # Bei langen Clips gröber abtasten, damit die Analyse zügig bleibt.
    interval = max(sample_interval, duration / MAX_SAMPLES_PER_CLIP)

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoReadError(
            f"Der Clip '{os.path.basename(path)}' konnte nicht geöffnet werden.",
            "Bitte prüfe, ob die Datei vollständig kopiert wurde.",
        )

    samples: List[FrameSample] = []
    previous_gray = None
    previous_shift = None
    fps = info.fps if info.fps > 0 else (cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_step = max(1, int(round(interval * fps)))

    try:
        frame_index = 0
        read_index = 0
        while True:
            if should_cancel and should_cancel():
                raise CancelledError()
            # Nicht benötigte Bilder nur "greifen" statt vollständig zu
            # dekodieren – das beschleunigt die Analyse langer Clips deutlich.
            if read_index % frame_step != 0:
                if not cap.grab():
                    break
                read_index += 1
                continue
            ok, frame = cap.read()
            if not ok:
                break
            timestamp = read_index / fps
            read_index += 1
            if timestamp > duration + 1.0:
                break

            gray = _to_gray_small(frame, cv2, np)
            sample = FrameSample(time=timestamp)

            # --- Schärfe: Varianz des Laplacian ---------------------------
            sample.sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())

            # --- Helligkeit / Belichtung ----------------------------------
            sample.brightness = float(gray.mean()) / 255.0
            dark = float((gray < 12).mean())
            bright = float((gray > 243).mean())
            sample.clipping = dark + bright

            # --- Bewegung + Verwacklung -----------------------------------
            if previous_gray is not None:
                diff = cv2.absdiff(gray, previous_gray)
                sample.motion = float(diff.mean()) / 255.0
                sample.scene_change = float((diff > 60).mean()) > 0.55

                # Globale Verschiebung (Schwenk/Kamerabewegung) per Phasenkorrelation
                shift_x, shift_y = _global_shift(previous_gray, gray, cv2, np)
                sample.shift = float((shift_x ** 2 + shift_y ** 2) ** 0.5)
                if previous_shift is not None:
                    # Ruckeln = plötzliche Richtungs-/Tempowechsel der Verschiebung
                    dx = shift_x - previous_shift[0]
                    dy = shift_y - previous_shift[1]
                    sample.shake = float((dx ** 2 + dy ** 2) ** 0.5)
                previous_shift = (shift_x, shift_y)

            samples.append(sample)
            previous_gray = gray
            frame_index += 1

            if progress and frame_index % 10 == 0 and duration > 0:
                progress(min(1.0, timestamp / duration),
                         f"Analysiere {os.path.basename(path)} ...")
    finally:
        cap.release()

    if len(samples) < 2:
        raise VideoReadError(
            f"Aus dem Clip '{os.path.basename(path)}' konnten keine Bilder gelesen werden.",
            "Die Datei ist möglicherweise beschädigt oder verwendet einen Codec, "
            "den OpenCV nicht öffnen kann. Wandle sie testweise in MP4 (H.264) um.",
        )

    # Erster Frame hat keinen Vorgänger -> Bewegungswerte übernehmen.
    samples[0].motion = samples[1].motion
    samples[0].shift = samples[1].shift
    samples[0].shake = samples[1].shake

    return _normalize(path, duration, fps, interval, samples)


def _to_gray_small(frame, cv2, np):
    """Bild verkleinern und in Graustufen wandeln (schnell + rauschärmer)."""
    height, width = frame.shape[:2]
    if width > ANALYSIS_WIDTH:
        scale = ANALYSIS_WIDTH / float(width)
        frame = cv2.resize(frame, (ANALYSIS_WIDTH, max(2, int(height * scale))),
                           interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _global_shift(previous_gray, gray, cv2, np):
    """Globale Bildverschiebung zwischen zwei Frames (Phasenkorrelation)."""
    try:
        a = np.float32(previous_gray)
        b = np.float32(gray)
        (shift_x, shift_y), _response = cv2.phaseCorrelate(a, b)
        return float(shift_x), float(shift_y)
    except Exception:
        return 0.0, 0.0


def _robust_normalize(values, np, low_pct: float = 5.0, high_pct: float = 95.0):
    """Auf 0..1 skalieren, unempfindlich gegen einzelne Ausreißer."""
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return array
    low = float(np.percentile(array, low_pct))
    high = float(np.percentile(array, high_pct))
    if high - low < 1e-9:
        return np.full_like(array, 0.5)
    return np.clip((array - low) / (high - low), 0.0, 1.0)


def _normalize(path, duration, fps, interval, samples) -> ClipAnalysis:
    """Rechnet die Rohmesswerte in vergleichbare 0..1-Bewertungen um."""
    import numpy as np  # type: ignore

    times = [s.time for s in samples]

    # Schärfe: logarithmisch, weil die Laplacian-Varianz über Größenordnungen streut.
    sharp_raw = np.log1p(np.asarray([s.sharpness for s in samples], dtype=float))
    sharpness = _robust_normalize(sharp_raw, np)

    # Bewegung: Frame-Differenz und Kameraschwenk gemeinsam betrachten.
    motion_raw = (np.asarray([s.motion for s in samples], dtype=float) * 0.75
                  + _robust_normalize([s.shift for s in samples], np) * 0.25 * 0.1)
    motion = _robust_normalize(motion_raw, np)

    # Belichtung: ideal ist mittlere Helligkeit ohne ausgefressene Bereiche.
    brightness = np.asarray([s.brightness for s in samples], dtype=float)
    clipping = np.asarray([s.clipping for s in samples], dtype=float)
    # Glockenkurve um 0.45 herum: 1.0 bei guter Belichtung, 0 bei sehr dunkel/hell.
    exposure = np.exp(-((brightness - 0.45) ** 2) / (2 * 0.20 ** 2))
    exposure = np.clip(exposure - np.clip(clipping - 0.02, 0.0, 1.0) * 1.5, 0.0, 1.0)

    # Stabilität: wenig Ruckeln = hoher Wert.
    shake = np.asarray([s.shake for s in samples], dtype=float)
    shake_norm = _robust_normalize(shake, np, 5.0, 95.0)
    stability = np.clip(1.0 - shake_norm, 0.0, 1.0)

    # Leichte Glättung, damit einzelne Ausreißer-Frames die Auswahl nicht kippen.
    def smooth(values, window: int = 3):
        if len(values) < window:
            return values
        kernel = np.ones(window) / window
        padded = np.pad(values, window // 2, mode="edge")
        return np.convolve(padded, kernel, mode="valid")[: len(values)]

    scene_changes = [s.time for s in samples if s.scene_change]

    return ClipAnalysis(
        path=path,
        duration=duration,
        fps=fps,
        sample_interval=interval,
        times=times,
        sharpness=[float(v) for v in smooth(sharpness)],
        motion=[float(v) for v in smooth(motion)],
        exposure=[float(v) for v in smooth(exposure)],
        stability=[float(v) for v in smooth(stability)],
        scene_changes=scene_changes,
        raw=samples,
    )


def score_curve(analysis: ClipAnalysis, weights: dict, prefer_motion: float = 0.5) -> List[float]:
    """Gesamtbewertung je Abtastpunkt nach den Gewichten der Vorlage.

    ``prefer_motion`` verschiebt den Geschmack zwischen ruhigen Shots (0.0)
    und Action (1.0), zusätzlich zu den Gewichten.
    """
    import numpy as np  # type: ignore

    motion = np.asarray(analysis.motion, dtype=float)
    # Bei prefer_motion=0 zählt wenig Bewegung als gut, bei 1.0 viel Bewegung.
    motion_pref = prefer_motion * motion + (1.0 - prefer_motion) * (1.0 - motion)

    total = sum(max(0.0, float(w)) for w in weights.values()) or 1.0
    score = (
        weights.get("sharpness", 0.0) * np.asarray(analysis.sharpness, dtype=float)
        + weights.get("motion", 0.0) * motion_pref
        + weights.get("exposure", 0.0) * np.asarray(analysis.exposure, dtype=float)
        + weights.get("stability", 0.0) * np.asarray(analysis.stability, dtype=float)
    ) / total
    return [float(v) for v in np.clip(score, 0.0, 1.0)]


def window_score(
    scores: Sequence[float],
    analysis: ClipAnalysis,
    start: float,
    end: float,
    scene_cut_penalty: float = 0.5,
) -> float:
    """Bewertung eines Zeitfensters: Mittelwert der Einzelwerte minus Abzüge."""
    if end <= start or not scores:
        return 0.0
    first = analysis.index_at(start)
    last = analysis.index_at(end)
    if last <= first:
        last = min(first + 1, len(scores) - 1)
    window = scores[first:last + 1]
    if not window:
        return 0.0
    mean = sum(window) / len(window)
    # Gleichmäßige Qualität ist besser als "halb top, halb Schrott".
    spread = (max(window) - min(window)) * 0.15
    penalty = 0.0
    if any(start < t < end for t in analysis.scene_changes):
        penalty = scene_cut_penalty * 0.2
    return max(0.0, mean - spread - penalty)


# ---------------------------------------------------------------------------
# Absolute Qualität (clip-übergreifend vergleichbar)
# ---------------------------------------------------------------------------
# Die Kurven oben sind pro Clip normiert – das ist richtig, um INNERHALB eines
# Clips die besten Stellen zu finden. Um Clips MITEINANDER zu vergleichen
# (z.B. wenn mehr Clips als Schnittplätze da sind), braucht es feste Maßstäbe.

# Referenzwert für "scharf genug" (Laplacian-Varianz bei 320px Analysebreite).
SHARPNESS_REFERENCE = 120.0


def absolute_quality(analysis: ClipAnalysis) -> float:
    """Gesamtqualität eines Clips auf fester Skala 0..1 (nicht clip-normiert)."""
    import numpy as np  # type: ignore

    if not analysis.raw:
        return 0.5

    sharp_raw = np.asarray([s.sharpness for s in analysis.raw], dtype=float)
    # Sättigungskurve: ab dem Referenzwert gilt ein Bild als scharf.
    sharp = float(np.mean(sharp_raw / (sharp_raw + SHARPNESS_REFERENCE)))

    brightness = np.asarray([s.brightness for s in analysis.raw], dtype=float)
    clipping = np.asarray([s.clipping for s in analysis.raw], dtype=float)
    exposure = float(np.mean(np.exp(-((brightness - 0.45) ** 2) / (2 * 0.20 ** 2))))
    exposure = max(0.0, exposure - float(np.mean(clipping)) * 1.2)

    return float(np.clip(0.6 * sharp + 0.4 * exposure, 0.0, 1.0))


def quality_label(value: float) -> str:
    """Klartext-Bewertung für den Report."""
    if value >= 0.75:
        return "sehr gut"
    if value >= 0.6:
        return "gut"
    if value >= 0.45:
        return "brauchbar"
    if value >= 0.3:
        return "schwach"
    return "sehr schwach"
