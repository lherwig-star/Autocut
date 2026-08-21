"""Rendern mit ffmpeg: Segmente schneiden, Übergänge setzen, Musik einbetten.

Ablauf:
1. Jeder gewählte Moment wird einzeln herausgeschnitten und dabei auf ein
   einheitliches Format gebracht (Auflösung, Bildrate, Farb-Look).
2. Die Teile werden zusammengesetzt – als harter Schnitt (schnell, verlustfrei
   aneinandergehängt) oder mit Crossfade (xfade-Filter).
3. Zum Schluss kommt die Musik als Tonspur dazu, inklusive Ausblendung.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Callable, List, Optional

from .edit_plan import EditPlan, Moment
from .errors import CancelledError, RenderError
from .ffmpeg_tools import ffmpeg_path, run_cancellable
from .templates import Template

# Wie viele Segmente ein Crossfade-Durchlauf am Stück verarbeitet.
# Verhindert überlange ffmpeg-Filterketten bei sehr vielen Schnitten.
XFADE_GROUP_SIZE = 20


@dataclass
class RenderResult:
    output_path: str
    duration: float
    segment_count: int


def build_color_filter(template: Template) -> str:
    """Baut die Farb-Look-Filterkette der Vorlage (leer, wenn deaktiviert)."""
    color = template.color
    if not color.get("enabled"):
        return ""

    parts: List[str] = []

    lut = str(color.get("lut") or "").strip()
    if lut:
        if not os.path.isfile(lut):
            raise RenderError(
                f"Die LUT-Datei '{lut}' aus der Vorlage '{template.name}' wurde nicht gefunden.",
                "Trage in der Vorlage unter color.lut den vollständigen Pfad zu einer "
                ".cube-Datei ein – oder lass den Wert leer.",
            )
        parts.append(f"lut3d={_escape_path(lut)}")

    brightness = float(color.get("brightness", 0.0))
    contrast = float(color.get("contrast", 1.0))
    saturation = float(color.get("saturation", 1.0))
    gamma = float(color.get("gamma", 1.0))
    if any(abs(v - d) > 1e-6 for v, d in
           ((brightness, 0.0), (contrast, 1.0), (saturation, 1.0), (gamma, 1.0))):
        parts.append(
            f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}"
            f":saturation={saturation:.4f}:gamma={gamma:.4f}"
        )

    temperature = float(color.get("temperature", 0.0))
    if abs(temperature) > 1e-6:
        # positiv = wärmer (mehr Rot, weniger Blau), negativ = kühler.
        # colorchannelmixer statt colorbalance: wirkt gleichmäßig über den
        # ganzen Helligkeitsbereich und verhält sich in allen ffmpeg-Versionen
        # gleich (colorbalance lässt neutrale Mitteltöne teils unverändert).
        red_gain = 1.0 + 0.22 * temperature
        blue_gain = 1.0 - 0.22 * temperature
        parts.append(f"colorchannelmixer=rr={red_gain:.4f}:bb={blue_gain:.4f}")

    if color.get("vignette"):
        parts.append("vignette=PI/5")

    return ",".join(parts)


def _escape_path(path: str) -> str:
    """Pfad für ffmpeg-Filter maskieren (Windows-Laufwerksbuchstaben!)."""
    escaped = path.replace("\\", "/")
    escaped = escaped.replace(":", "\\:").replace("'", "\\'")
    return f"'{escaped}'"


def build_scale_filter(template: Template) -> str:
    """Einheitliches Bildformat: hineinskalieren, Rest schwarz auffüllen."""
    out = template.output
    width, height = int(out["width"]), int(out["height"])
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=bicubic,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def render(
    plan: EditPlan,
    template: Template,
    music_path: str,
    output_path: str,
    progress: Optional[Callable[[float, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    keep_temp: bool = False,
) -> RenderResult:
    """Rendert den Schnittplan zu einer fertigen Videodatei."""
    if not plan.moments:
        raise RenderError(
            "Es wurde kein einziger Moment für das Video gefunden.",
            "Prüfe, ob im gewählten Ordner lesbare Videoclips liegen.",
        )

    output_path = os.path.abspath(output_path)
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    crossfade = template["transition"] == "crossfade" and len(plan.moments) > 1
    fade = float(template["transition_duration"]) if crossfade else 0.0

    temp_dir = tempfile.mkdtemp(prefix="autocut_")
    try:
        parts = _extract_segments(
            plan, template, temp_dir, fade, progress, should_cancel
        )
        if progress:
            progress(0.62, "Setze die Teile zusammen ...")

        if crossfade:
            silent_video = _join_with_crossfade(
                parts, plan, fade, template, temp_dir, progress, should_cancel
            )
        else:
            silent_video = _join_hard_cut(parts, temp_dir, should_cancel)

        if progress:
            progress(0.85, "Füge die Musik hinzu ...")
        _add_music(silent_video, music_path, output_path, plan, template, should_cancel)

        if progress:
            progress(1.0, "Fertig")
        return RenderResult(output_path, plan.total_duration, len(plan.moments))
    finally:
        if not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Schritt 1: Segmente herausschneiden und vereinheitlichen
# ---------------------------------------------------------------------------

def _extract_segments(plan, template, temp_dir, fade, progress, should_cancel) -> List[str]:
    ffmpeg = ffmpeg_path()
    out = template.output
    filters = [build_scale_filter(template), f"fps={float(out['fps']):g}"]
    color = build_color_filter(template)
    if color:
        filters.append(color)

    paths: List[str] = []
    total = len(plan.moments)
    for index, moment in enumerate(plan.moments):
        if should_cancel and should_cancel():
            raise CancelledError()

        # Bei Crossfades braucht jedes Teil etwas Überlänge für den Übergang.
        duration = moment.duration + (fade if fade > 0 else 0.0)
        # Exakte Bildanzahl statt Zeitangabe: nur so liegt jeder Schnitt
        # bildgenau auf dem Beat und es entsteht keine Drift über das Video.
        frames = max(1, int(round(duration * float(out["fps"]))))
        chain = list(filters)
        if fade > 0:
            # Falls das Quellmaterial zu kurz ist: letztes Bild anhalten,
            # damit die Übergangslängen exakt aufgehen.
            chain.append(f"tpad=stop_mode=clone:stop_duration={fade:.3f}")
        part = os.path.join(temp_dir, f"part_{index:05d}.mp4")

        args = [
            ffmpeg, "-y", "-v", "error", "-nostdin",
            "-ss", f"{moment.source_start:.3f}",
            "-i", moment.clip_path,
            "-t", f"{duration + 1.0:.3f}",
            "-an", "-sn", "-dn",
            "-vf", ",".join(chain),
            "-c:v", "libx264", "-preset", str(out.get("preset", "medium")),
            "-crf", "18", "-pix_fmt", "yuv420p",
            "-r", f"{float(out['fps']):g}",
            "-frames:v", str(frames),
            "-video_track_timescale", "90000",
            part,
        ]
        run_cancellable(args, f"Schnitt {index + 1} aus '{moment.clip_name}'", should_cancel)
        if not os.path.isfile(part) or os.path.getsize(part) < 512:
            raise RenderError(
                f"Aus '{moment.clip_name}' konnte der Abschnitt bei "
                f"{moment.source_start:.1f}s nicht geschnitten werden.",
                "Die Datei ist eventuell beschädigt oder wurde während der "
                "Verarbeitung verschoben.",
            )
        paths.append(part)

        if progress:
            progress(0.02 + 0.58 * (index + 1) / total,
                     f"Schneide Abschnitt {index + 1} von {total} ...")
    return paths


# ---------------------------------------------------------------------------
# Schritt 2a: harter Schnitt
# ---------------------------------------------------------------------------

def _join_hard_cut(parts: List[str], temp_dir: str, should_cancel) -> str:
    """Alle Teile ohne Neucodierung aneinanderhängen (sehr schnell)."""
    if len(parts) == 1:
        return parts[0]
    list_file = os.path.join(temp_dir, "concat.txt")
    with open(list_file, "w", encoding="utf-8") as handle:
        for path in parts:
            handle.write("file '%s'\n" % path.replace("\\", "/").replace("'", "'\\''"))
    output = os.path.join(temp_dir, "joined.mp4")
    run_cancellable(
        [ffmpeg_path(), "-y", "-v", "error", "-nostdin", "-f", "concat", "-safe", "0",
         "-i", list_file, "-c", "copy", "-movflags", "+faststart", output],
        "Zusammenfügen der Abschnitte", should_cancel,
    )
    return output


# ---------------------------------------------------------------------------
# Schritt 2b: Crossfade
# ---------------------------------------------------------------------------

def _join_with_crossfade(parts, plan, fade, template, temp_dir,
                         progress, should_cancel) -> str:
    """Teile mit weichen Überblendungen verbinden.

    Jedes Teil ist um die Übergangsdauer verlängert. Der Übergang beginnt genau
    auf dem Beat, dadurch bleibt die Gesamtlänge exakt auf dem Beat-Raster.
    Sehr viele Schnitte werden in Gruppen verarbeitet, damit die ffmpeg-
    Filterkette handhabbar bleibt.
    """
    durations = [moment.duration for moment in plan.moments]
    groups: List[tuple[List[str], List[float]]] = []
    for start in range(0, len(parts), XFADE_GROUP_SIZE):
        groups.append((parts[start:start + XFADE_GROUP_SIZE],
                       durations[start:start + XFADE_GROUP_SIZE]))

    rendered: List[str] = []
    rendered_durations: List[float] = []
    for index, (group_parts, group_durations) in enumerate(groups):
        if should_cancel and should_cancel():
            raise CancelledError()
        if len(group_parts) == 1:
            rendered.append(group_parts[0])
        else:
            target = os.path.join(temp_dir, f"group_{index:03d}.mp4")
            _xfade_chain(group_parts, group_durations, fade, template, target, should_cancel)
            rendered.append(target)
        rendered_durations.append(sum(group_durations))
        if progress:
            progress(0.62 + 0.2 * (index + 1) / len(groups),
                     f"Überblendungen {index + 1}/{len(groups)} ...")

    if len(rendered) == 1:
        return rendered[0]

    output = os.path.join(temp_dir, "joined_xfade.mp4")
    _xfade_chain(rendered, rendered_durations, fade, template, output, should_cancel)
    return output


def _xfade_chain(parts: List[str], durations: List[float], fade: float,
                 template: Template, output: str, should_cancel) -> None:
    """Baut die xfade-Filterkette für eine Gruppe von Teilen."""
    out = template.output
    args = [ffmpeg_path(), "-y", "-v", "error", "-nostdin"]
    for path in parts:
        args += ["-i", path]

    steps: List[str] = []
    label = "0:v"
    offset = 0.0
    for index in range(1, len(parts)):
        offset += durations[index - 1]
        target = f"x{index}"
        steps.append(
            f"[{label}][{index}:v]xfade=transition=fade:duration={fade:.3f}"
            f":offset={offset:.3f}[{target}]"
        )
        label = target

    total = sum(durations)
    steps.append(f"[{label}]fps={float(out['fps']):g},format=yuv420p[vout]")
    args += [
        "-filter_complex", ";".join(steps),
        "-map", "[vout]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", str(out.get("preset", "medium")),
        "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", output,
    ]
    run_cancellable(args, "Überblendungen", should_cancel)


# ---------------------------------------------------------------------------
# Schritt 3: Musik einbetten
# ---------------------------------------------------------------------------

def _add_music(video_path, music_path, output_path, plan, template, should_cancel) -> None:
    out = template.output
    duration = plan.total_duration
    fade_out = min(float(out.get("audio_fade_out", 0.0)), max(0.0, duration - 0.5))

    audio_filters = []
    if fade_out > 0.05:
        audio_filters.append(f"afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}")
    audio_filters.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")

    args = [
        ffmpeg_path(), "-y", "-v", "error", "-nostdin",
        "-i", video_path,
        "-i", music_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-af", ",".join(audio_filters),
        "-c:a", "aac", "-b:a", str(out.get("audio_bitrate", "192k")),
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]
    run_cancellable(args, "Musik hinzufügen", should_cancel)

    if not os.path.isfile(output_path) or os.path.getsize(output_path) < 1024:
        raise RenderError(
            "Die fertige Videodatei konnte nicht geschrieben werden.",
            f"Zielort: {output_path}\n\nPrüfe, ob genug Speicherplatz frei ist und "
            "ob die Datei gerade in einem anderen Programm geöffnet ist.",
        )
