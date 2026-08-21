"""Tests der Szenenbewertung gegen Clips mit bekannten Eigenschaften.

Die Testclips sind absichtlich extrem: einer ist scharf, einer stark
weichgezeichnet, einer sehr dunkel, einer unbewegt und einer wechselt
zur Hälfte von schlecht auf gut.
"""

import statistics

import pytest

from autocut.video_analysis import (
    SHARPNESS_REFERENCE, absolute_quality, analyze_clip, quality_label,
    score_curve, window_score,
)


def _by_name(clips, teil):
    return next(c for c in clips if teil in c.name)


def _rohwert(analyse, feld):
    return statistics.mean(getattr(s, feld) for s in analyse.raw)


def test_schaerfe_erkennt_unschaerfe(clips, analyses):
    result, _ = analyses
    scharf = _rohwert(result[_by_name(clips, "sharp_motion").path], "sharpness")
    unscharf = _rohwert(result[_by_name(clips, "blurry").path], "sharpness")
    # Weichgezeichnet muss um ein Vielfaches schlechter sein.
    assert unscharf < scharf / 10
    assert unscharf < SHARPNESS_REFERENCE
    assert scharf > SHARPNESS_REFERENCE


def test_helligkeit_erkennt_unterbelichtung(clips, analyses):
    result, _ = analyses
    dunkel = _rohwert(result[_by_name(clips, "dark").path], "brightness")
    normal = _rohwert(result[_by_name(clips, "sharp_motion").path], "brightness")
    assert dunkel < 0.25
    assert normal > 0.4


def test_belichtungsnote_bestraft_dunkles_bild(clips, analyses):
    result, _ = analyses
    dunkel = result[_by_name(clips, "dark").path]
    hell = result[_by_name(clips, "sharp_motion").path]
    assert statistics.mean(dunkel.exposure) < statistics.mean(hell.exposure)


def test_bewegung_erkennt_stillstand(clips, analyses):
    result, _ = analyses
    ruhig = _rohwert(result[_by_name(clips, "static").path], "motion")
    bewegt = _rohwert(result[_by_name(clips, "sharp_motion").path], "motion")
    assert ruhig < 0.005
    assert bewegt > ruhig * 5


def test_gesamtqualitaet_ordnet_clips_richtig(clips, analyses):
    _, quality = analyses
    gut = quality[_by_name(clips, "sharp_motion").path]
    unscharf = quality[_by_name(clips, "blurry").path]
    dunkel = quality[_by_name(clips, "dark").path]
    assert gut > 0.7
    assert unscharf < 0.5
    assert dunkel < 0.5
    assert gut > unscharf and gut > dunkel


def test_gute_stelle_im_gemischten_clip_wird_besser_bewertet(clips, analyses):
    """Der 'mixed'-Clip ist in der ersten Hälfte schlecht, in der zweiten gut."""
    result, _ = analyses
    analyse = result[_by_name(clips, "mixed").path]
    gewichte = {"sharpness": 1.0, "motion": 0.5, "exposure": 1.0, "stability": 1.0}
    noten = score_curve(analyse, gewichte, prefer_motion=0.5)
    mitte = len(noten) // 2
    erste = statistics.mean(noten[:mitte])
    zweite = statistics.mean(noten[mitte:])
    assert zweite > erste + 0.2, "Die gute Hälfte muss deutlich besser bewertet werden"


def test_fensterbewertung_findet_die_gute_haelfte(clips, analyses):
    result, _ = analyses
    analyse = result[_by_name(clips, "mixed").path]
    gewichte = {"sharpness": 1.0, "motion": 0.5, "exposure": 1.0, "stability": 1.0}
    noten = score_curve(analyse, gewichte, 0.5)
    schlecht = window_score(noten, analyse, 0.5, 2.5)
    gut = window_score(noten, analyse, 3.5, 5.5)
    assert gut > schlecht


def test_bewegungs_geschmack_dreht_die_bewertung(clips, analyses):
    """prefer_motion=0 muss ruhige Stellen bevorzugen, 1.0 bewegte."""
    result, _ = analyses
    bewegt = result[_by_name(clips, "sharp_motion").path]
    gewichte = {"sharpness": 0.0, "motion": 1.0, "exposure": 0.0, "stability": 0.0}
    action = statistics.mean(score_curve(bewegt, gewichte, prefer_motion=1.0))
    ruhe = statistics.mean(score_curve(bewegt, gewichte, prefer_motion=0.0))
    assert action == pytest.approx(1.0 - ruhe, abs=0.02)


def test_alle_noten_liegen_zwischen_null_und_eins(clips, analyses):
    result, _ = analyses
    for analyse in result.values():
        for feld in (analyse.sharpness, analyse.motion, analyse.exposure, analyse.stability):
            assert all(0.0 <= v <= 1.0 for v in feld)
        assert analyse.count > 5


def test_klartext_bewertung():
    assert quality_label(0.9) == "sehr gut"
    assert quality_label(0.1) == "sehr schwach"


def test_kaputte_datei_gibt_verstaendlichen_fehler(tmp_path):
    from autocut.errors import VideoReadError
    from autocut.ffmpeg_tools import MediaInfo

    datei = tmp_path / "kaputt.mp4"
    datei.write_bytes(b"kein video")
    info = MediaInfo(str(datei), duration=5.0, width=320, height=240, fps=30, has_audio=False)
    with pytest.raises(VideoReadError):
        analyze_clip(str(datei), info)
