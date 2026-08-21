"""Orchestrierung: von den Eingaben zum fertigen Video.

Dieses Modul ist die einzige Schnittstelle, die GUI und CLI benutzen.
Dadurch bleiben Oberfläche und Verarbeitungslogik sauber getrennt.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .audio_analysis import MusicAnalysis, analyze_music
from .clips import Clip, load_clips
from .edit_plan import EditPlan, build_plan
from .errors import AutoCutError, CancelledError
from .ffmpeg_tools import have_ffmpeg
from .render import RenderResult, render
from .report import build_report, save_report
from .templates import Template, load_template
from .video_analysis import ClipAnalysis, absolute_quality, analyze_clip

# Gewichtung der Arbeitsschritte für den Fortschrittsbalken (Summe = 1.0)
STAGE_WEIGHTS = {
    "clips": 0.05,
    "music": 0.08,
    "video": 0.37,
    "plan": 0.03,
    "render": 0.47,
}

ProgressCallback = Callable[[float, str], None]


@dataclass
class AutoCutResult:
    """Alles, was nach einem Durchlauf interessant ist."""

    output_path: str
    report_path: str
    report_text: str
    plan: EditPlan
    duration: float
    elapsed: float
    warnings: List[str] = field(default_factory=list)


class _Progress:
    """Rechnet den Fortschritt der Einzelschritte auf einen Gesamtwert um."""

    def __init__(self, callback: Optional[ProgressCallback]) -> None:
        self.callback = callback
        self.base = 0.0

    def stage(self, name: str):
        weight = STAGE_WEIGHTS[name]
        base = self.base

        def report(fraction: float, message: str) -> None:
            if self.callback:
                value = base + weight * max(0.0, min(1.0, fraction))
                self.callback(max(0.0, min(1.0, value)), message)

        self.base = base + weight
        return report

    def message(self, text: str) -> None:
        if self.callback:
            self.callback(self.base, text)


def run_autocut(
    clips_folder: str,
    music_path: str,
    template_name: str = "cinematic_vlog",
    output_path: str = "autocut_video.mp4",
    progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    recursive: bool = False,
    order: str = "auto",
    templates_folder: Optional[str] = None,
    write_report: bool = True,
    max_music_seconds: Optional[float] = None,
) -> AutoCutResult:
    """Kompletter Durchlauf: Analyse -> Schnittplan -> Rendern -> Report.

    Alle Fehler kommen als :class:`AutoCutError` mit verständlichem Text zurück.
    ``progress`` wird mit (0.0–1.0, Statustext) aufgerufen.
    """
    start_time = time.time()
    steps = _Progress(progress)

    if not have_ffmpeg():
        from .errors import FFmpegNotFoundError

        raise FFmpegNotFoundError()

    template = (template_name if isinstance(template_name, Template)
                else load_template(str(template_name), templates_folder))

    # --- 1. Clips einlesen und chronologisch ordnen -------------------------
    steps.message("Suche Videoclips ...")
    clips: List[Clip] = load_clips(
        clips_folder, recursive=recursive, order=order, progress=steps.stage("clips")
    )
    _raise_if_cancelled(should_cancel)

    # --- 2. Musik analysieren ----------------------------------------------
    music: MusicAnalysis = analyze_music(
        music_path, max_duration=max_music_seconds, progress=steps.stage("music")
    )
    _raise_if_cancelled(should_cancel)

    # --- 3. Videoclips bewerten --------------------------------------------
    video_progress = steps.stage("video")
    analyses: Dict[str, ClipAnalysis] = {}
    quality: Dict[str, float] = {}
    failed: List[str] = []
    for position, clip in enumerate(clips):
        _raise_if_cancelled(should_cancel)
        base = position / len(clips)
        span = 1.0 / len(clips)

        def clip_progress(fraction: float, message: str, _b=base, _s=span) -> None:
            video_progress(_b + _s * fraction, message)

        clip_progress(0.0, f"Analysiere Clip {position + 1}/{len(clips)}: {clip.name}")
        try:
            analysis = analyze_clip(
                clip.path, clip.info, progress=clip_progress, should_cancel=should_cancel
            )
        except CancelledError:
            raise
        except AutoCutError:
            failed.append(clip.name)
            continue
        analyses[clip.path] = analysis
        quality[clip.path] = absolute_quality(analysis)
    video_progress(1.0, f"{len(analyses)} Clips analysiert")

    usable_clips = [c for c in clips if c.path in analyses]
    if not usable_clips:
        from .errors import NoClipsFoundError

        raise NoClipsFoundError(
            "Keiner der gefundenen Clips konnte analysiert werden.",
            "Wandle die Dateien testweise in MP4 (H.264) um – dieses Format "
            "wird am zuverlässigsten unterstützt.",
        )

    # --- 4. Schnittplan bauen ----------------------------------------------
    plan_progress = steps.stage("plan")
    plan_progress(0.2, "Berechne den Schnittplan ...")
    plan: EditPlan = build_plan(usable_clips, analyses, music, template, quality)
    for name in failed:
        plan.skipped_clips.append((name, "Datei konnte nicht analysiert werden"))
    plan_progress(1.0, f"{len(plan.moments)} Schnitte geplant")
    _raise_if_cancelled(should_cancel)

    # --- 5. Rendern ---------------------------------------------------------
    render_result: RenderResult = render(
        plan, template, music.path, output_path,
        progress=steps.stage("render"), should_cancel=should_cancel,
    )

    # --- 6. Report ----------------------------------------------------------
    elapsed = time.time() - start_time
    report_text = build_report(
        plan, template, music, usable_clips, analyses,
        output_path=render_result.output_path, elapsed=elapsed,
    )
    report_path = save_report(report_text, render_result.output_path) if write_report else ""

    if progress:
        progress(1.0, "Fertig!")

    return AutoCutResult(
        output_path=render_result.output_path,
        report_path=report_path,
        report_text=report_text,
        plan=plan,
        duration=render_result.duration,
        elapsed=elapsed,
        warnings=list(plan.warnings),
    )


def _raise_if_cancelled(should_cancel) -> None:
    if should_cancel and should_cancel():
        raise CancelledError()


def preview_plan(
    clips_folder: str,
    music_path: str,
    template_name: str = "cinematic_vlog",
    progress: Optional[ProgressCallback] = None,
    recursive: bool = False,
    order: str = "auto",
    templates_folder: Optional[str] = None,
) -> str:
    """Nur analysieren und den Report erzeugen – ohne zu rendern (Testlauf)."""
    template = load_template(template_name, templates_folder)
    clips = load_clips(clips_folder, recursive=recursive, order=order)
    music = analyze_music(music_path, progress=progress)
    analyses, quality = {}, {}
    for clip in clips:
        try:
            analysis = analyze_clip(clip.path, clip.info)
        except AutoCutError:
            continue
        analyses[clip.path] = analysis
        quality[clip.path] = absolute_quality(analysis)
    usable = [c for c in clips if c.path in analyses]
    plan = build_plan(usable, analyses, music, template, quality)
    return build_report(plan, template, music, usable, analyses)
