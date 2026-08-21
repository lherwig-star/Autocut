"""Textreport: welcher Moment stammt aus welchem Clip – und warum.

Der Report ist bewusst als reiner Text gehalten: er wird neben dem Video
gespeichert und lässt sich in der App direkt anzeigen.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

from .audio_analysis import MusicAnalysis, format_time
from .clips import Clip
from .edit_plan import EditPlan
from .templates import Template
from .video_analysis import ClipAnalysis, quality_label

LINE = "=" * 78
THIN = "-" * 78


def build_report(
    plan: EditPlan,
    template: Template,
    music: MusicAnalysis,
    clips: List[Clip],
    analyses: Optional[Dict[str, ClipAnalysis]] = None,
    output_path: str = "",
    elapsed: Optional[float] = None,
) -> str:
    analyses = analyses or {}
    lines: List[str] = []
    add = lines.append

    add(LINE)
    add("AutoCut – Schnittprotokoll")
    add(LINE)
    add(f"Erstellt am      : {datetime.now().strftime('%d.%m.%Y um %H:%M:%S')}")
    if output_path:
        add(f"Videodatei       : {output_path}")
    add(f"Vorlage          : {template.name}"
        + (f" – {template.description}" if template.description else ""))
    add(f"Einstellungen    : {template.summary()}")
    add("")
    add(f"Musik            : {os.path.basename(music.path)}")
    add(f"  Länge          : {format_time(music.duration)} ({music.duration:.1f}s)")
    add(f"  Tempo          : {music.tempo:.1f} BPM  ({len(music.beats)} Beats erkannt)")
    add(f"  Beat-Abstand   : {music.beat_period:.3f}s")
    add("")
    add(f"Videolänge       : {format_time(plan.total_duration)} ({plan.total_duration:.1f}s)")
    add(f"Anzahl Schnitte  : {len(plan.moments)}")
    add(f"Verwendete Clips : {plan.clip_count} von {len(clips)}")
    if elapsed:
        add(f"Rechenzeit       : {elapsed:.1f}s")
    add("")

    # --- Übersicht der Eingangsclips ---------------------------------------
    add(THIN)
    add("EINGANGSCLIPS (in der verwendeten Reihenfolge)")
    add(THIN)
    add(f"{'Nr':>3}  {'Datei':<34} {'Länge':>8} {'Bildqualität':<14} Sortierung")
    for clip in clips:
        quality = plan.clip_quality.get(clip.path)
        quality_text = (f"{quality:.2f} ({quality_label(quality)})" if quality is not None
                        else "-")
        add(f"{clip.index + 1:>3}. {clip.name[:34]:<34} {clip.duration:7.1f}s "
            f"{quality_text:<14} {clip.sort_reason}")
    add("")

    # --- Die eigentliche Auswahl -------------------------------------------
    add(THIN)
    add("GEWÄHLTE MOMENTE")
    add(THIN)
    add("Video-Zeit = Position im fertigen Video, Quelle = Stelle im Originalclip")
    add("")
    add(f"{'#':>3}  {'Video-Zeit':<12} {'Dauer':>6}  {'Quelle (von-bis)':<18} "
        f"{'Note':>5}  Clip")
    for moment in plan.moments:
        add(f"{moment.order + 1:>3}. "
            f"{format_time(moment.timeline_start):<12} "
            f"{moment.duration:5.2f}s  "
            f"{format_time(moment.source_start)}-{format_time(moment.source_end):<8} "
            f"{moment.score:5.2f}  "
            f"{moment.clip_name}")
        add(f"     └─ {moment.reason}, Song-Energie {moment.energy:.2f}"
            + _explain(moment, analyses.get(moment.clip_path)))
    add("")

    # --- Zusammenfassung je Clip -------------------------------------------
    add(THIN)
    add("ZUSAMMENFASSUNG JE CLIP")
    add(THIN)
    for clip in clips:
        moments = plan.moments_of(clip.path)
        if not moments:
            reason = next((why for name, why in plan.skipped_clips if name == clip.name),
                          "nicht verwendet")
            add(f"{clip.index + 1:>3}. {clip.name:<38} –  {reason}")
            continue
        used = sum(m.duration for m in moments)
        share = 100.0 * used / plan.total_duration if plan.total_duration else 0.0
        best = max(moments, key=lambda m: m.score)
        add(f"{clip.index + 1:>3}. {clip.name:<38} {len(moments):>2} Schnitt(e), "
            f"{used:5.1f}s ({share:4.1f}% des Videos)")
        add(f"     bester Moment: {format_time(best.source_start)} "
            f"(Note {best.score:.2f})")
    add("")

    if plan.skipped_clips:
        add(THIN)
        add("NICHT VERWENDETE CLIPS")
        add(THIN)
        for name, reason in plan.skipped_clips:
            add(f"  • {name}: {reason}")
        add("")

    if plan.warnings:
        add(THIN)
        add("HINWEISE")
        add(THIN)
        for warning in plan.warnings:
            add(f"  • {warning}")
        add("")

    add(THIN)
    add("SO LIEST DU DIE NOTE")
    add(THIN)
    add("Die Note (0.00–1.00) ist der gewichtete Durchschnitt der gemessenen")
    add("Kriterien im gewählten Zeitfenster – nach den Gewichten der Vorlage:")
    weights = template.weights
    names = {"sharpness": "Schärfe", "motion": "Bewegung",
             "exposure": "Belichtung", "stability": "Ruhe im Bild"}
    total_weight = sum(weights.values()) or 1.0
    for key, value in weights.items():
        add(f"  {names.get(key, key):<14} Gewicht {value:.2f} "
            f"({100 * value / total_weight:.0f}%)")
    add(f"  Bewegungs-Geschmack: {float(template['prefer_motion']):.2f} "
        "(0 = ruhige Shots bevorzugt, 1 = viel Action bevorzugt)")
    add(LINE)
    return "\n".join(lines)


def _explain(moment, analysis: Optional[ClipAnalysis]) -> str:
    """Kurze Begründung aus den Messwerten der gewählten Stelle."""
    if analysis is None or not analysis.times:
        return ""
    first = analysis.index_at(moment.source_start)
    last = max(first + 1, analysis.index_at(moment.source_end))
    def mean(values):
        window = values[first:last]
        return sum(window) / len(window) if window else 0.0
    return (f" | Schärfe {mean(analysis.sharpness):.2f}, "
            f"Bewegung {mean(analysis.motion):.2f}, "
            f"Belichtung {mean(analysis.exposure):.2f}, "
            f"Ruhe {mean(analysis.stability):.2f}")


def save_report(text: str, video_path: str) -> str:
    """Speichert den Report neben der Videodatei und liefert den Pfad."""
    base = os.path.splitext(video_path)[0]
    path = base + "_report.txt"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
