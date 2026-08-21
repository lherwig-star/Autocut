"""Tests der Schnittlogik – vor allem der Reihenfolge-Garantien.

Die wichtigste Zusage des Programms: die chronologische Reihenfolge der Clips
wird nie verändert. Das wird hier für alle mitgelieferten Vorlagen geprüft.
"""

import bisect

import pytest

from autocut.edit_plan import (
    build_beat_segments, build_plan, distribute_segments, select_moments_in_clip,
)
from autocut.templates import list_templates, load_template

VORLAGEN = list_templates()


@pytest.fixture(params=VORLAGEN)
def template(request):
    return load_template(request.param)


@pytest.fixture
def plan(clips, analyses, music, template):
    result, quality = analyses
    return build_plan(clips, result, music, template, quality)


# --- Beat-Raster ----------------------------------------------------------

def test_segmente_liegen_auf_beats(music, template):
    """Jede Schnittgrenze muss auf einem Beat liegen (max. halbes Bild daneben)."""
    segmente = build_beat_segments(music, template, max_segment_length=5.2)
    zeit = 0.0
    for segment in segmente[:-1]:
        zeit += segment.duration
        stelle = bisect.bisect_left(music.beats, zeit)
        nachbarn = music.beats[max(0, stelle - 1):stelle + 1]
        abweichung = min(abs(b - zeit) for b in nachbarn)
        assert abweichung < 0.035, (
            f"Schnitt bei {zeit:.3f}s liegt {abweichung * 1000:.0f} ms neben dem Beat")


def test_segmente_halten_min_und_max_laenge_ein(music, template):
    segmente = build_beat_segments(music, template, max_segment_length=5.2)
    obergrenze = min(float(template["max_clip_length"]), 5.2)
    for segment in segmente[:-1]:
        assert segment.duration <= obergrenze + 0.05
        assert segment.duration > 0.1


def test_segmente_sind_lueckenlos_und_aufsteigend(music, template):
    segmente = build_beat_segments(music, template, max_segment_length=5.2)
    for vorher, nachher in zip(segmente, segmente[1:]):
        assert nachher.start == pytest.approx(vorher.end, abs=1e-6)
    assert segmente[0].start == 0.0
    assert segmente[-1].end <= music.duration + 1e-6


def test_segmentlaengen_sind_ganze_bilder(music, template):
    """Sonst würden sich über das Video Bruchteile zu einer Drift aufsummieren."""
    bild = 1.0 / float(template.output["fps"])
    for segment in build_beat_segments(music, template, max_segment_length=5.2):
        rest = segment.duration % bild
        assert min(rest, bild - rest) < 1e-6


def test_energie_steuert_die_schnittlaenge(music):
    """travel_recap: leise Passage muss längere Clips bekommen als der Drop."""
    template = load_template("travel_recap")
    segmente = build_beat_segments(music, template, max_segment_length=8.0)
    leise = [s.duration for s in segmente if s.start >= 9.0 and s.end <= 16.0]
    laut = [s.duration for s in segmente if s.end <= 8.0 or s.start >= 17.0]
    assert leise and laut
    assert sum(leise) / len(leise) > sum(laut) / len(laut) * 1.5


def test_ohne_energie_anpassung_sind_alle_segmente_gleich_lang(music):
    template = load_template("energetic")
    segmente = build_beat_segments(music, template, max_segment_length=8.0)
    laengen = [s.duration for s in segmente[:-1]]
    assert max(laengen) - min(laengen) < 0.15


# --- Reihenfolge (die zentrale Zusage) ------------------------------------

def test_clip_reihenfolge_bleibt_erhalten(plan):
    reihenfolge = [m.clip_index for m in plan.moments]
    assert reihenfolge == sorted(reihenfolge), "Die Clips wurden umsortiert!"


def test_jeder_clip_bildet_einen_zusammenhaengenden_block(plan):
    """Ein Clip darf nicht später noch einmal auftauchen."""
    gesehen, letzter = [], None
    for moment in plan.moments:
        if moment.clip_index != letzter:
            assert moment.clip_index not in gesehen, "Clip taucht zweimal getrennt auf"
            gesehen.append(moment.clip_index)
            letzter = moment.clip_index


def test_momente_innerhalb_eines_clips_laufen_vorwaerts(plan):
    letzte_position = {}
    for moment in plan.moments:
        vorher = letzte_position.get(moment.clip_path)
        if vorher is not None:
            assert moment.source_start >= vorher - 1e-6
        letzte_position[moment.clip_path] = moment.source_end


def test_zeitachse_ist_lueckenlos(plan):
    for vorher, nachher in zip(plan.moments, plan.moments[1:]):
        assert nachher.timeline_start == pytest.approx(vorher.timeline_end, abs=1e-6)
    if plan.moments:
        assert plan.moments[0].timeline_start == 0.0


def test_interne_pruefung_laeuft_durch(plan):
    plan.check_order()  # wirft AssertionError, wenn etwas nicht stimmt


# --- Auswahl und Grenzen --------------------------------------------------

def test_momente_liegen_innerhalb_der_clips(plan, clips):
    laengen = {c.path: c.duration for c in clips}
    for moment in plan.moments:
        assert moment.source_start >= -1e-6
        assert moment.source_end <= laengen[moment.clip_path] + 1e-6
        assert moment.duration > 0


def test_video_ist_nie_laenger_als_der_song(plan, music):
    assert plan.total_duration <= music.duration + 0.5


def test_beste_stelle_wird_gewaehlt(clips, analyses):
    """Aus dem 'mixed'-Clip muss die gute zweite Hälfte gewählt werden."""
    result, _ = analyses
    clip = next(c for c in clips if "mixed" in c.name)
    template = load_template("cinematic_vlog")
    picks = select_moments_in_clip(clip, result[clip.path], [2.0], template)
    start, ende, note = picks[0]
    assert start >= 2.5, f"Es wurde die schlechte Hälfte gewählt (Start {start:.2f}s)"
    assert note > 0.4


def test_mehrere_momente_verteilen_sich_ueber_den_clip(clips, analyses):
    result, _ = analyses
    clip = clips[0]
    template = load_template("energetic")
    picks = select_moments_in_clip(clip, result[clip.path], [0.5, 0.5, 0.5], template)
    starts = [p[0] for p in picks]
    assert starts == sorted(starts)
    assert starts[-1] - starts[0] > 1.0, "Alle Momente kleben am Clipanfang"


def test_zu_wenige_schnittplaetze_laesst_clips_aus(clips, music, analyses):
    """Weniger Segmente als Clips: es müssen trotzdem gültige Pläne entstehen."""
    result, quality = analyses
    template = load_template("cinematic_vlog")
    segmente = build_beat_segments(music, template, max_segment_length=5.2)[:2]
    counts, skipped, warnings, gap = distribute_segments(segmente, clips, template, quality)
    assert sum(counts) == len(segmente)
    assert len(skipped) >= len(clips) - 2
    assert warnings


def test_verteilung_ueberschreitet_nie_die_cliplaenge(clips, music, analyses, template):
    result, quality = analyses
    segmente = build_beat_segments(music, template, max_segment_length=5.2)
    counts, _skipped, _warnings, gap = distribute_segments(segmente, clips, template, quality)
    stelle = 0
    for clip, anzahl in zip(clips, counts):
        block = segmente[stelle:stelle + anzahl]
        stelle += anzahl
        if not block:
            continue
        gebraucht = sum(s.duration for s in block) + gap * (len(block) - 1)
        assert gebraucht <= clip.duration + 1e-6, f"{clip.name} ist überbucht"


def test_report_daten_sind_vollstaendig(plan):
    for moment in plan.moments:
        assert moment.clip_name and moment.reason
        assert 0.0 <= moment.score <= 1.0
        assert 0.0 <= moment.energy <= 1.0
