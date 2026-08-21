"""Tests des Gesamtdurchlaufs inklusive Rendern (kleine Testdaten)."""

import os
import subprocess

import pytest

from autocut.errors import AutoCutError, CancelledError, NoClipsFoundError
from autocut.ffmpeg_tools import ffmpeg_path, probe
from autocut.pipeline import run_autocut


@pytest.fixture(scope="module")
def kleine_vorlagen(tmp_path_factory):
    """Kleine Ausgabegröße, damit die Tests schnell durchlaufen."""
    folder = tmp_path_factory.mktemp("vorlagen")
    gemeinsam = ("output:\n  width: 320\n  height: 180\n  fps: 30\n"
                 "  preset: ultrafast\n  audio_fade_out: 0.5\n")
    (folder / "test_hart.yaml").write_text(
        "beats_per_cut: 2\nmin_clip_length: 0.5\nmax_clip_length: 2.0\n"
        "transition: hard_cut\nskip_start: 0.1\nskip_end: 0.1\n"
        "min_gap_between_moments: 0.2\n" + gemeinsam, encoding="utf-8")
    (folder / "test_weich.yaml").write_text(
        "beats_per_cut: 4\nmin_clip_length: 1.0\nmax_clip_length: 3.0\n"
        "transition: crossfade\ntransition_duration: 0.5\n"
        "color:\n  enabled: true\n  saturation: 1.2\n  temperature: 0.2\n"
        + gemeinsam, encoding="utf-8")
    return str(folder)


def _durchlauf(testdata, vorlagen, name, ziel, **kwargs):
    return run_autocut(
        clips_folder=testdata["clips_dir"],
        music_path=testdata["music"],
        template_name=name,
        output_path=str(ziel),
        templates_folder=vorlagen,
        max_music_seconds=8.0,
        **kwargs,
    )


def test_kompletter_durchlauf_harter_schnitt(testdata, kleine_vorlagen, tmp_path):
    ziel = tmp_path / "fertig.mp4"
    meldungen = []
    ergebnis = _durchlauf(testdata, kleine_vorlagen, "test_hart", ziel,
                          progress=lambda f, m: meldungen.append((f, m)))

    assert os.path.isfile(ergebnis.output_path)
    info = probe(ergebnis.output_path)
    assert info.width == 320 and info.height == 180
    # Das Video muss ungefähr so lang sein wie geplant (max. 2 Bilder Abweichung).
    assert info.duration == pytest.approx(ergebnis.plan.total_duration, abs=0.1)
    assert ergebnis.plan.moments

    # Fortschritt muss von 0 nach 1 laufen und darf nie zurückspringen.
    werte = [f for f, _ in meldungen]
    assert werte == sorted(werte)
    assert werte[-1] == pytest.approx(1.0)


def test_tonspur_ist_im_fertigen_video(testdata, kleine_vorlagen, tmp_path):
    ziel = tmp_path / "mit_ton.mp4"
    ergebnis = _durchlauf(testdata, kleine_vorlagen, "test_hart", ziel)
    ausgabe = subprocess.run(
        [ffmpeg_path(), "-i", ergebnis.output_path, "-f", "null", "-"],
        capture_output=True, text=True).stderr
    assert "Audio: aac" in ausgabe
    assert "Video: h264" in ausgabe


def test_crossfade_und_farblook_rendern(testdata, kleine_vorlagen, tmp_path):
    ziel = tmp_path / "weich.mp4"
    ergebnis = _durchlauf(testdata, kleine_vorlagen, "test_weich", ziel)
    assert os.path.isfile(ergebnis.output_path)
    info = probe(ergebnis.output_path)
    assert info.duration == pytest.approx(ergebnis.plan.total_duration, abs=0.15)


def test_report_wird_geschrieben_und_ist_lesbar(testdata, kleine_vorlagen, tmp_path):
    ziel = tmp_path / "report.mp4"
    ergebnis = _durchlauf(testdata, kleine_vorlagen, "test_hart", ziel)

    assert os.path.isfile(ergebnis.report_path)
    text = open(ergebnis.report_path, encoding="utf-8").read()
    assert "AutoCut – Schnittprotokoll" in text
    assert "GEWÄHLTE MOMENTE" in text
    # Jeder verwendete Clip muss im Report auftauchen.
    for moment in ergebnis.plan.moments:
        assert moment.clip_name in text
    # Die Anzahl der aufgeführten Momente muss zum Plan passen.
    assert text.count("└─") == len(ergebnis.plan.moments)


def test_abbruch_wird_sauber_behandelt(testdata, kleine_vorlagen, tmp_path):
    ziel = tmp_path / "abgebrochen.mp4"
    zaehler = {"n": 0}

    def abbrechen():
        zaehler["n"] += 1
        return zaehler["n"] > 3   # nach ein paar Schritten abbrechen

    with pytest.raises(CancelledError):
        _durchlauf(testdata, kleine_vorlagen, "test_hart", ziel, should_cancel=abbrechen)
    assert not os.path.isfile(ziel)


def test_leerer_ordner_gibt_verstaendlichen_fehler(testdata, kleine_vorlagen, tmp_path):
    leer = tmp_path / "leer"
    leer.mkdir()
    with pytest.raises(NoClipsFoundError) as fehler:
        run_autocut(str(leer), testdata["music"], "test_hart", str(tmp_path / "x.mp4"),
                    templates_folder=kleine_vorlagen)
    assert "keine Videodateien" in fehler.value.message
    assert "MP4" in fehler.value.hint


def test_fehler_haben_immer_titel_und_klartext(testdata, kleine_vorlagen, tmp_path):
    with pytest.raises(AutoCutError) as fehler:
        run_autocut(str(tmp_path / "gibt_es_nicht"), testdata["music"], "test_hart",
                    str(tmp_path / "x.mp4"), templates_folder=kleine_vorlagen)
    assert fehler.value.title
    assert fehler.value.full_text()
    assert "Traceback" not in fehler.value.full_text()
