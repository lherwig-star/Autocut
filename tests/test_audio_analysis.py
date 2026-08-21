"""Tests der Musik-Analyse gegen einen selbst erzeugten Klick-Track.

Der Testsong hat exakt 120 BPM (= 0.5s Beat-Abstand) und zwischen Sekunde
8 und 16 eine deutlich leisere Passage.
"""

import pytest

from autocut.audio_analysis import analyze_music, format_time
from autocut.errors import MusicFileError


def test_beat_abstand_passt_zu_120_bpm(music):
    # Der erkannte Beat-Abstand muss dem echten Takt entsprechen (+/- 5 ms).
    assert music.beat_period == pytest.approx(0.5, abs=0.005)


def test_beats_liegen_auf_dem_echten_raster(music):
    # Jeder erkannte Beat muss nahe an einem Vielfachen von 0.5s liegen.
    for beat in music.beats:
        offset = beat % 0.5
        abweichung = min(offset, 0.5 - offset)
        assert abweichung < 0.06, f"Beat bei {beat:.3f}s liegt neben dem Raster"


def test_beats_decken_den_ganzen_song_ab(music):
    assert len(music.beats) >= 40
    assert music.beats[0] < 0.6
    assert music.beats[-1] > music.duration - 0.7
    assert music.beats == sorted(music.beats)


def test_dauer_wird_korrekt_erkannt(music):
    assert music.duration == pytest.approx(24.0, abs=0.1)


def test_energie_erkennt_die_leise_passage(music):
    laut_vorher = music.energy_at(4.0)
    leise = music.energy_at(12.0)
    laut_nachher = music.energy_at(20.0)
    assert leise < 0.3
    assert laut_vorher > 0.6
    assert laut_nachher > 0.6
    assert laut_vorher - leise > 0.4


def test_energie_bleibt_im_gueltigen_bereich(music):
    for zeit in [i * 0.5 for i in range(48)]:
        assert 0.0 <= music.energy_at(zeit) <= 1.0
    # Auch außerhalb des Songs darf es keine Ausreißer geben.
    assert 0.0 <= music.energy_at(-5.0) <= 1.0
    assert 0.0 <= music.energy_at(999.0) <= 1.0


def test_energie_mittelwert_ueber_fenster(music):
    assert music.energy_between(9.0, 15.0) < music.energy_between(1.0, 7.0)


def test_fehlende_datei_gibt_verstaendlichen_fehler(tmp_path):
    with pytest.raises(MusicFileError) as fehler:
        analyze_music(str(tmp_path / "gibt_es_nicht.mp3"))
    assert "nicht gefunden" in fehler.value.message


def test_kaputte_datei_gibt_verstaendlichen_fehler(tmp_path):
    kaputt = tmp_path / "kaputt.wav"
    kaputt.write_bytes(b"das ist keine musik")
    with pytest.raises(MusicFileError):
        analyze_music(str(kaputt))


def test_zeitformat():
    assert format_time(0) == "00:00.0"
    assert format_time(65.4) == "01:05.4"
    assert format_time(-3) == "00:00.0"
