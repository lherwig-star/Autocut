"""Schnittlogik: Beat-Raster bauen, auf Clips verteilen, beste Momente wählen.

Wichtigste Regel, die hier durchgängig eingehalten wird:
**Die chronologische Reihenfolge der Clips wird nie verändert.**
Jeder Clip bekommt einen zusammenhängenden Block der Songzeit, und zwar in
genau der Reihenfolge, in der die Clips eingelesen wurden. Auch innerhalb
eines Clips laufen die gewählten Momente vorwärts.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .audio_analysis import MusicAnalysis
from .clips import Clip
from .templates import Template
from .video_analysis import ClipAnalysis, score_curve, window_score


@dataclass
class BeatSegment:
    """Ein Zeitfenster im Song zwischen zwei Schnitten."""

    start: float
    end: float
    beat_index: int
    energy: float
    beats_used: int

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Moment:
    """Ein gewählter Moment: Stelle im Quellclip -> Stelle im fertigen Video."""

    order: int
    clip_index: int
    clip_name: str
    clip_path: str
    source_start: float
    source_end: float
    timeline_start: float
    timeline_end: float
    score: float
    energy: float
    beat_index: int
    reason: str = ""

    @property
    def duration(self) -> float:
        return self.source_end - self.source_start


@dataclass
class EditPlan:
    """Der komplette Schnittplan – Grundlage für Rendern und Report."""

    moments: List[Moment] = field(default_factory=list)
    template_name: str = ""
    music_path: str = ""
    music_duration: float = 0.0
    tempo: float = 0.0
    beat_count: int = 0
    total_duration: float = 0.0
    skipped_clips: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    clip_quality: Dict[str, float] = field(default_factory=dict)

    @property
    def clip_count(self) -> int:
        return len({m.clip_path for m in self.moments})

    def moments_of(self, clip_path: str) -> List[Moment]:
        return [m for m in self.moments if m.clip_path == clip_path]

    def check_order(self) -> None:
        """Sicherheitsnetz: prüft die Reihenfolge-Garantien des Plans."""
        last_clip = -1
        last_time = -1.0
        per_clip: Dict[str, float] = {}
        for moment in self.moments:
            if moment.clip_index < last_clip:
                raise AssertionError(
                    "Interner Fehler: Clip-Reihenfolge wurde verändert "
                    f"({moment.clip_name} nach Clip-Index {last_clip})."
                )
            last_clip = moment.clip_index
            if moment.timeline_start < last_time - 1e-6:
                raise AssertionError("Interner Fehler: Zeitachse läuft rückwärts.")
            last_time = moment.timeline_start
            previous_end = per_clip.get(moment.clip_path)
            if previous_end is not None and moment.source_start < previous_end - 1e-6:
                raise AssertionError(
                    f"Interner Fehler: Momente in '{moment.clip_name}' nicht chronologisch."
                )
            per_clip[moment.clip_path] = moment.source_end


# ---------------------------------------------------------------------------
# 1. Beat-Raster
# ---------------------------------------------------------------------------

def build_beat_segments(
    music: MusicAnalysis,
    template: Template,
    max_duration: Optional[float] = None,
    max_segment_length: Optional[float] = None,
) -> List[BeatSegment]:
    """Zerlegt den Song entlang der Beats in Schnitt-Fenster.

    Bei ``adaptive_to_energy`` steuert die Energie-Kurve, wie viele Beats ein
    Fenster umfasst: leise Passagen -> mehr Beats (lange Clips),
    Drop/Refrain -> wenige Beats (schnelle Schnitte).
    """
    beats = list(music.beats)
    if len(beats) < 2:
        return _fallback_segments(music, template, max_duration, max_segment_length)

    fps = float(template.output.get("fps", 30)) or 30.0
    frame = 1.0 / fps
    min_len = float(template["min_clip_length"])
    max_len = float(template["max_clip_length"])
    if max_segment_length:
        # Ein Schnitt kann nie länger sein als das längste vorhandene Material.
        max_len = min(max_len, max(max_segment_length, 0.2))
        min_len = min(min_len, max_len * 0.9)
    limit = min(music.duration, max_duration) if max_duration else music.duration

    segments: List[BeatSegment] = []
    index = 0
    # Video und Musik starten gemeinsam bei 0: Ein kurzes Intro vor dem
    # ersten Beat wird dem ersten Fenster zugeschlagen.
    cursor = 0.0

    while index < len(beats) - 1 and cursor < limit - 0.05:
        energy = music.energy_at(cursor)
        wanted = _beats_for_energy(template, energy)

        # Passenden Endbeat suchen und dabei min/max-Länge einhalten.
        next_index = _advance_to_beat(beats, index, cursor, wanted, min_len, max_len)
        end = beats[next_index] if next_index < len(beats) else limit

        if end - cursor > max_len:
            end = cursor + max_len
        if end > limit:
            end = limit

        # Auf ganze Bilder runden: sonst summieren sich pro Schnitt Bruchteile
        # eines Bildes auf und die späteren Schnitte lägen neben dem Beat.
        end = cursor + max(frame, round((end - cursor) / frame) * frame)
        if end > limit:
            end = cursor + max(frame, int((limit - cursor) / frame) * frame)

        duration = end - cursor
        if duration < min_len * 0.5 and segments:
            # Zu kurzer Rest: an das vorherige Fenster anhängen.
            segments[-1].end = end
            break

        segments.append(BeatSegment(
            start=cursor,
            end=end,
            beat_index=index,
            energy=energy,
            beats_used=max(1, next_index - index),
        ))
        cursor = end
        if next_index < len(beats) and abs(beats[next_index] - cursor) <= frame:
            # Normalfall: der Schnitt liegt auf diesem Beat (bis auf Bildrundung).
            # Wichtig: die Beat-Position NICHT aus dem gerundeten Cursor neu
            # ableiten – sonst würde durch die Rundung ein Beat übersprungen.
            index = next_index
        else:
            # Die maximale Cliplänge hat vor dem nächsten Beat gegriffen:
            # Position im Beat-Raster neu bestimmen.
            index = max(0, min(bisect.bisect_right(beats, cursor) - 1, len(beats) - 1))

    if not segments:
        return _fallback_segments(music, template, max_duration, max_len)
    return segments


def _beats_for_energy(template: Template, energy: float) -> int:
    """Wie viele Beats umfasst ein Schnitt bei dieser Song-Energie?"""
    if not template["adaptive_to_energy"]:
        return int(template["beats_per_cut"])
    quiet = float(template["beats_per_cut_quiet"])
    loud = float(template["beats_per_cut_loud"])
    value = quiet + (loud - quiet) * max(0.0, min(1.0, energy))
    return max(1, int(round(value)))


def _advance_to_beat(
    beats: Sequence[float], index: int, cursor: float,
    wanted: int, min_len: float, max_len: float,
) -> int:
    """Index des Beats, an dem geschnitten wird – unter Beachtung min/max-Länge."""
    target = min(index + wanted, len(beats) - 1)
    # Zu kurz -> weitere Beats dazunehmen
    while target < len(beats) - 1 and beats[target] - cursor < min_len:
        target += 1
    # Zu lang -> Beats wegnehmen (aber mindestens einen Beat weiter)
    while target > index + 1 and beats[target] - cursor > max_len:
        target -= 1
    return max(target, index + 1)


def _fallback_segments(music, template, max_duration, max_len=None) -> List[BeatSegment]:
    """Ohne brauchbare Beats: gleichmäßiges Raster aus min/max-Länge."""
    upper = min(float(template["max_clip_length"]), max_len or float("inf"))
    length = min(float(template["min_clip_length"]), upper) / 2.0 + upper / 2.0
    limit = min(music.duration, max_duration) if max_duration else music.duration
    fps = float(template.output.get("fps", 30)) or 30.0
    frame = 1.0 / fps
    length = max(frame, round(length / frame) * frame)
    segments, cursor, i = [], 0.0, 0
    while cursor < limit - 0.05:
        end = min(cursor + length, limit)
        if end - cursor < length * 0.4 and segments:
            segments[-1].end = end
            break
        segments.append(BeatSegment(cursor, end, i, music.energy_at(cursor), 1))
        cursor, i = end, i + 1
    return segments


# ---------------------------------------------------------------------------
# 2. Verteilung der Segmente auf die Clips (chronologisch)
# ---------------------------------------------------------------------------

def _usable_range(clip: Clip, template: Template) -> Tuple[float, float]:
    """Nutzbarer Bereich eines Clips (Anfang/Ende laut Vorlage abgeschnitten)."""
    skip_start = float(template["skip_start"])
    skip_end = float(template["skip_end"])
    start = min(skip_start, clip.duration * 0.25)
    end = clip.duration - min(skip_end, clip.duration * 0.25)
    if end - start < 0.2:  # sehr kurzer Clip: nichts abschneiden
        start, end = 0.0, clip.duration
    return start, end


def _fits(durations: Sequence[float], usable: float, gap: float) -> bool:
    if not durations:
        return True
    return sum(durations) + gap * (len(durations) - 1) <= usable + 1e-6


def _spread_selection(active: List[int], count: int, quality: Dict[str, float],
                      clips: List[Clip]) -> List[int]:
    """Wählt ``count`` Clips gleichmäßig über die Zeitachse verteilt aus.

    Innerhalb jedes Abschnitts gewinnt der Clip mit der besten Bildqualität.
    """
    if count >= len(active):
        return list(active)
    chosen: List[int] = []
    for slot in range(count):
        lo = int(slot * len(active) / count)
        hi = max(lo + 1, int((slot + 1) * len(active) / count))
        block = active[lo:hi]
        best = max(block, key=lambda i: quality.get(clips[i].path, 0.5))
        chosen.append(best)
    return sorted(set(chosen))


def _blocks_for(counts: List[int], segments: List[BeatSegment]) -> Dict[int, List[BeatSegment]]:
    """Ordnet jedem Clip seinen zusammenhängenden Block von Segmenten zu.

    Clip 0 bekommt die ersten Segmente, Clip 1 die nächsten usw. – dadurch
    ist die chronologische Reihenfolge bereits durch den Aufbau garantiert.
    """
    blocks: Dict[int, List[BeatSegment]] = {}
    cursor = 0
    for i, count in enumerate(counts):
        blocks[i] = segments[cursor:cursor + count]
        cursor += count
    return blocks


def distribute_segments(
    segments: List[BeatSegment],
    clips: List[Clip],
    template: Template,
    quality: Optional[Dict[str, float]] = None,
) -> Tuple[List[int], List[Tuple[str, str]], List[str], float]:
    """Verteilt die Song-Segmente chronologisch auf die Clips.

    Rückgabe: (Anzahl Segmente je Clip, übersprungene Clips, Hinweise, Abstand).

    Die Anzahl ist proportional zur nutzbaren Cliplänge. Passt ein Block nicht
    in seinen Clip, wandern Segmente zum nächsten Clip mit freier Zeit. Reicht
    das Material insgesamt nicht, wird das Video am Ende gekürzt (die Musik
    blendet dann aus) – niemals werden Segmente aus der Mitte entfernt, weil
    sonst alle folgenden Schnitte neben dem Beat lägen.
    """
    gap_wanted = float(template["min_gap_between_moments"])
    quality = quality or {}
    warnings: List[str] = []
    skipped: List[Tuple[str, str]] = []

    usable = [max(0.0, e - s) for s, e in (_usable_range(c, template) for c in clips)]
    min_needed = min((s.duration for s in segments), default=0.0)
    active = [i for i, u in enumerate(usable) if u >= min_needed - 1e-6]
    for i, clip in enumerate(clips):
        if i not in active:
            skipped.append((clip.name, "Clip ist kürzer als die kürzeste Schnittlänge"))

    if not active:
        return [0] * len(clips), skipped, [
            "Kein Clip ist lang genug für diese Vorlage. Nimm eine Vorlage mit "
            "kürzerer minimaler Cliplänge (z.B. 'energetic')."
        ], gap_wanted

    if len(segments) < len(active):
        # Mehr Clips als Schnittplätze: gleichmäßig über die Zeitachse verteilte
        # Clips auswählen, damit die ganze Reise vorkommt (Reihenfolge bleibt).
        counts = [0] * len(clips)
        chosen = _spread_selection(active, len(segments), quality, clips)
        for i in active:
            if i not in chosen:
                skipped.append((clips[i].name,
                                "Song zu kurz – für diesen Clip war kein Platz mehr"))
        for i in chosen:
            counts[i] = 1
        warnings.append(
            f"Der Song reicht nur für {len(segments)} Schnitte, es liegen aber "
            f"{len(active)} Clips vor. {len(active) - len(chosen)} Clips wurden "
            "ausgelassen (siehe Report). Ein längerer Song oder eine Vorlage mit "
            "kürzeren Clips nimmt mehr Material auf."
        )
        return counts, skipped, warnings, gap_wanted

    # Zuerst versuchen, ALLE Segmente unterzubringen. Klappt das nicht, wird
    # der Mindestabstand schrittweise verkleinert, bevor gekürzt wird.
    used = len(segments)
    while used >= len(active):
        # Reihenfolge der Notlösungen: erst den Mindestabstand verkleinern,
        # und erst wenn auch das nicht reicht, das Video hinten kürzen.
        for gap in _gap_candidates(gap_wanted):
            counts = _allocate(used, usable, active)
            repaired = _repair_capacity(counts, segments[:used], usable, gap, active)
            if repaired is not None:
                if gap < gap_wanted - 1e-6:
                    warnings.append(
                        f"Der Mindestabstand zwischen zwei Momenten desselben Clips "
                        f"wurde von {gap_wanted:.2f}s auf {gap:.2f}s verkleinert, "
                        "damit das Material für den ganzen Song reicht."
                    )
                if used < len(segments):
                    warnings.append(
                        f"Das Filmmaterial reicht nicht für den ganzen Song: "
                        f"{len(segments) - used} von {len(segments)} Schnitten "
                        "entfallen am Ende. Das Video wird entsprechend kürzer."
                    )
                return repaired, skipped, warnings, gap
        used -= max(1, used // 40)

    # Sollte praktisch nie eintreten – dann bekommt jeder aktive Clip einen Schnitt.
    counts = [1 if i in active else 0 for i in range(len(clips))]
    warnings.append("Das Material reicht nur für einen kurzen Zusammenschnitt.")
    return counts, skipped, warnings, 0.0


def _gap_candidates(gap: float) -> List[float]:
    """Mindestabstände, die nacheinander probiert werden (großzügig -> knapp)."""
    values = [gap, gap * 0.5, gap * 0.25, 0.0]
    result: List[float] = []
    for value in values:
        value = max(0.0, round(value, 3))
        if value not in result:
            result.append(value)
    return result


def _allocate(total: int, usable: List[float], active: List[int]) -> List[int]:
    """Verteilt ``total`` Segmente proportional zur nutzbaren Cliplänge."""
    counts = [0] * len(usable)
    total_usable = sum(usable[i] for i in active) or 1.0
    exact = {i: total * usable[i] / total_usable for i in active}
    for i in active:
        counts[i] = max(1, int(exact[i]))
    remaining = total - sum(counts)
    order = sorted(active, key=lambda i: exact[i] - int(exact[i]), reverse=True)
    while remaining > 0:
        for i in order:
            if remaining <= 0:
                break
            counts[i] += 1
            remaining -= 1
    while remaining < 0:
        candidates = [i for i in active if counts[i] > 1]
        if not candidates:
            break
        biggest = max(candidates, key=lambda i: counts[i])
        counts[biggest] -= 1
        remaining += 1
    return counts


def _repair_capacity(counts: List[int], segments: List[BeatSegment],
                     usable: List[float], gap: float,
                     active: List[int]) -> Optional[List[int]]:
    """Verschiebt überzählige Segmente zu Clips mit freier Zeit.

    Liefert ``None``, wenn die Segmente nicht vollständig untergebracht werden
    können – dann probiert der Aufrufer es mit weniger Segmenten erneut.
    """
    counts = list(counts)
    for _ in range(500):
        blocks = _blocks_for(counts, segments)
        overflow = next(
            (i for i in active
             if counts[i] > 0 and not _fits([s.duration for s in blocks[i]], usable[i], gap)),
            None,
        )
        if overflow is None:
            return counts

        counts[overflow] -= 1
        moved = False
        # Empfänger: Clip mit der meisten freien Zeit, der das Segment auch fasst.
        for candidate in sorted(
            (j for j in active if j != overflow),
            key=lambda j: usable[j] - _used_time(_blocks_for(counts, segments)[j], gap),
            reverse=True,
        ):
            trial = list(counts)
            trial[candidate] += 1
            trial_blocks = _blocks_for(trial, segments)
            if _fits([s.duration for s in trial_blocks[candidate]], usable[candidate], gap):
                counts = trial
                moved = True
                break
        if not moved:
            return None
    return None


def _used_time(block: List[BeatSegment], gap: float) -> float:
    if not block:
        return 0.0
    return sum(s.duration for s in block) + gap * (len(block) - 1)


# ---------------------------------------------------------------------------
# 3. Beste Momente innerhalb eines Clips wählen
# ---------------------------------------------------------------------------

def select_moments_in_clip(
    clip: Clip,
    analysis: ClipAnalysis,
    durations: List[float],
    template: Template,
    gap: Optional[float] = None,
) -> List[Tuple[float, float, float]]:
    """Wählt für die gewünschten Längen die besten Stellen im Clip.

    Rückgabe: Liste aus (start, ende, bewertung) – aufsteigend nach Zeit.
    Es wird immer vorwärts gesucht, damit die Momente eines Clips in ihrer
    natürlichen Reihenfolge im fertigen Video landen.
    """
    if not durations:
        return []

    scores = score_curve(analysis, template.weights, float(template["prefer_motion"]))
    penalty = float(template["scene_cut_penalty"])
    if gap is None:
        gap = float(template["min_gap_between_moments"])
    usable_start, usable_end = _usable_range(clip, template)

    # Suchschrittweite: fein genug für gute Treffer, grob genug für Tempo.
    step = max(0.05, min(analysis.sample_interval, 0.5))

    picks: List[Tuple[float, float, float]] = []
    cursor = usable_start
    for position, wanted in enumerate(durations):
        remaining = durations[position + 1:]
        # Platz für die noch folgenden Momente freihalten -> Momente verteilen sich.
        reserve = sum(remaining) + gap * len(remaining)
        latest_start = usable_end - wanted - reserve
        if latest_start < cursor - 1e-6:
            # Notfall (sollte durch die Kapazitätsprüfung nicht vorkommen):
            # niemals zurückspringen, notfalls den abgeschnittenen Rand mitnutzen.
            latest_start = max(cursor, min(clip.duration - wanted, cursor))

        best_start, best_score = cursor, -1.0
        candidate = cursor
        while candidate <= latest_start + 1e-6:
            value = window_score(scores, analysis, candidate, candidate + wanted, penalty)
            if value > best_score + 1e-9:
                best_start, best_score = candidate, value
            candidate += step

        # Nie vor den Cursor zurück – das sichert die Reihenfolge im Clip.
        best_start = max(cursor, best_start)
        end = min(best_start + wanted, clip.duration)
        if end - best_start < wanted - 1e-3 and best_start > 0:
            # Am Clipende: so weit nach vorn schieben, dass die geplante Länge
            # erhalten bleibt (sonst würde alles Folgende neben dem Beat liegen).
            best_start = max(cursor if cursor + wanted <= clip.duration else 0.0,
                             clip.duration - wanted)
            end = min(best_start + wanted, clip.duration)
        picks.append((best_start, end, max(0.0, best_score)))
        cursor = end + gap

    return picks


# ---------------------------------------------------------------------------
# 4. Gesamtplan
# ---------------------------------------------------------------------------

def build_plan(
    clips: List[Clip],
    analyses: Dict[str, ClipAnalysis],
    music: MusicAnalysis,
    template: Template,
    quality: Optional[Dict[str, float]] = None,
) -> EditPlan:
    """Setzt Beat-Raster, Verteilung und Momentauswahl zum Schnittplan zusammen."""
    longest_usable = max(
        (end - start for start, end in (_usable_range(c, template) for c in clips)),
        default=0.0,
    )
    segments = build_beat_segments(music, template, max_segment_length=longest_usable)
    counts, skipped, warnings, gap = distribute_segments(segments, clips, template, quality)
    used = sum(counts)
    blocks = _blocks_for(counts, segments[:used])

    plan = EditPlan(
        template_name=template.name,
        music_path=music.path,
        music_duration=music.duration,
        tempo=music.tempo,
        beat_count=len(music.beats),
        skipped_clips=list(skipped),
        warnings=list(warnings),
        clip_quality=dict(quality or {}),
    )

    order = 0
    timeline_cursor = 0.0
    for clip in clips:  # Reihenfolge: exakt wie eingelesen
        block = blocks.get(clip.index, [])
        if not block:
            if all(clip.name != name for name, _ in plan.skipped_clips):
                plan.skipped_clips.append((clip.name, "kein Schnittplatz übrig"))
            continue
        analysis = analyses.get(clip.path)
        if analysis is None:
            plan.skipped_clips.append((clip.name, "Analyse fehlgeschlagen"))
            continue

        durations = [segment.duration for segment in block]
        picks = select_moments_in_clip(clip, analysis, durations, template, gap=gap)

        for segment, (start, end, score) in zip(block, picks):
            actual = end - start
            plan.moments.append(Moment(
                order=order,
                clip_index=clip.index,
                clip_name=clip.name,
                clip_path=clip.path,
                source_start=start,
                source_end=end,
                timeline_start=timeline_cursor,
                timeline_end=timeline_cursor + actual,
                score=score,
                energy=segment.energy,
                beat_index=segment.beat_index,
                reason=_reason_for(segment, template),
            ))
            timeline_cursor += actual
            order += 1

    plan.total_duration = timeline_cursor
    if plan.total_duration < music.duration - 1.0:
        plan.warnings.append(
            f"Das Video ist {music.duration - plan.total_duration:.1f}s kürzer als der Song. "
            "Die Musik wird passend ausgeblendet."
        )
    plan.check_order()
    return plan


def _reason_for(segment: BeatSegment, template: Template) -> str:
    """Kurzbegründung für den Report."""
    if not template["adaptive_to_energy"]:
        return f"{segment.beats_used} Beat(s)"
    if segment.energy >= 0.66:
        level = "lauter Songteil"
    elif segment.energy <= 0.33:
        level = "leiser Songteil"
    else:
        level = "mittlere Energie"
    return f"{segment.beats_used} Beat(s), {level}"
