"""Tests für das Einlesen und die chronologische Sortierung der Clips."""

import os
import shutil

import pytest

from autocut.clips import (
    VIDEO_EXTENSIONS, find_video_files, load_clips, total_duration,
)
from autocut.errors import NoClipsFoundError


@pytest.fixture
def ordner(tmp_path, testdata):
    """Kopiert die Testclips unter neuen Namen in einen frischen Ordner."""
    def bauen(namen):
        ziel = tmp_path / ("ordner_" + str(abs(hash(tuple(namen)))))
        ziel.mkdir()
        for i, name in enumerate(namen):
            shutil.copy(testdata["clips"][i % len(testdata["clips"])], ziel / name)
        return str(ziel)
    return bauen


def test_findet_alle_videoformate(tmp_path):
    for endung in (".mp4", ".MOV", ".mkv", ".txt", ".jpg"):
        (tmp_path / f"datei{endung}").write_bytes(b"x")
    gefunden = [os.path.basename(p) for p in find_video_files(str(tmp_path))]
    assert "datei.mp4" in gefunden
    assert "datei.MOV" in gefunden      # Groß-/Kleinschreibung egal
    assert "datei.mkv" in gefunden
    assert "datei.txt" not in gefunden
    assert "datei.jpg" not in gefunden


def test_versteckte_dateien_werden_ignoriert(tmp_path):
    (tmp_path / ".versteckt.mp4").write_bytes(b"x")
    (tmp_path / "sichtbar.mp4").write_bytes(b"x")
    gefunden = [os.path.basename(p) for p in find_video_files(str(tmp_path))]
    assert gefunden == ["sichtbar.mp4"]


def test_zahlen_im_namen_werden_natuerlich_sortiert(ordner):
    """clip2 muss vor clip10 kommen – nicht danach wie bei reiner Textsortierung."""
    pfad = ordner(["clip10.mp4", "clip2.mp4", "clip1.mp4"])
    namen = [c.name for c in load_clips(pfad)]
    assert namen == ["clip1.mp4", "clip2.mp4", "clip10.mp4"]


def test_datum_im_dateinamen_wird_erkannt(ordner):
    pfad = ordner(["VID_20240715_180000.mp4", "VID_20240101_090000.mp4",
                   "VID_20240715_120000.mp4"])
    namen = [c.name for c in load_clips(pfad)]
    assert namen == ["VID_20240101_090000.mp4", "VID_20240715_120000.mp4",
                     "VID_20240715_180000.mp4"]
    assert all("Datum" in c.sort_reason for c in load_clips(pfad))


def test_gemischte_quellen_werden_nicht_vermischt(ordner):
    """Haben nicht alle Clips ein Datum, entscheidet für ALLE der Dateiname.

    Sonst kämen die Clips mit Datum immer zuerst – unabhängig davon, wann
    sie wirklich aufgenommen wurden.
    """
    pfad = ordner(["a_ohne_datum.mp4", "b_VID_20200101_120000.mp4", "c_ohne_datum.mp4"])
    clips = load_clips(pfad)
    assert [c.name for c in clips] == ["a_ohne_datum.mp4",
                                       "b_VID_20200101_120000.mp4",
                                       "c_ohne_datum.mp4"]
    assert all("Dateiname" in c.sort_reason for c in clips)


def test_sortierung_nach_name_erzwingen(ordner):
    pfad = ordner(["z_VID_20200101_120000.mp4", "a_VID_20240101_120000.mp4"])
    namen = [c.name for c in load_clips(pfad, order="name")]
    assert namen[0].startswith("a_")


def test_sortierung_ist_bei_jedem_lauf_gleich(ordner):
    pfad = ordner(["b.mp4", "a.mp4", "c.mp4"])
    erste = [c.name for c in load_clips(pfad)]
    for _ in range(3):
        assert [c.name for c in load_clips(pfad)] == erste


def test_index_entspricht_der_reihenfolge(ordner):
    clips = load_clips(ordner(["c.mp4", "a.mp4", "b.mp4"]))
    assert [c.index for c in clips] == [0, 1, 2]
    assert [c.name for c in clips] == ["a.mp4", "b.mp4", "c.mp4"]


def test_unterordner_nur_auf_wunsch(tmp_path, testdata):
    unten = tmp_path / "unterordner"
    unten.mkdir()
    shutil.copy(testdata["clips"][0], unten / "tief.mp4")
    shutil.copy(testdata["clips"][1], tmp_path / "oben.mp4")

    assert [c.name for c in load_clips(str(tmp_path))] == ["oben.mp4"]
    namen = sorted(c.name for c in load_clips(str(tmp_path), recursive=True))
    assert namen == ["oben.mp4", "tief.mp4"]


def test_kaputte_dateien_werden_uebersprungen(tmp_path, testdata):
    shutil.copy(testdata["clips"][0], tmp_path / "gut.mp4")
    (tmp_path / "kaputt.mp4").write_bytes(b"kein echtes video")
    clips = load_clips(str(tmp_path))
    assert [c.name for c in clips] == ["gut.mp4"]


def test_leerer_ordner_meldet_verstaendlich(tmp_path):
    with pytest.raises(NoClipsFoundError) as fehler:
        load_clips(str(tmp_path))
    assert "keine Videodateien" in fehler.value.message


def test_nicht_vorhandener_ordner_meldet_verstaendlich(tmp_path):
    with pytest.raises(NoClipsFoundError) as fehler:
        load_clips(str(tmp_path / "gibt_es_nicht"))
    assert "existiert nicht" in fehler.value.message


def test_nur_kaputte_dateien_meldet_verstaendlich(tmp_path):
    (tmp_path / "kaputt.mp4").write_bytes(b"nichts")
    with pytest.raises(NoClipsFoundError) as fehler:
        load_clips(str(tmp_path))
    assert "konnte keine" in fehler.value.message


def test_eckdaten_werden_gelesen(clips):
    for clip in clips:
        assert clip.duration > 0
        assert clip.info.width > 0 and clip.info.height > 0
        assert clip.info.fps > 0
    assert total_duration(clips) == pytest.approx(30.0, abs=0.5)


def test_alle_endungen_sind_kleingeschrieben():
    assert all(e == e.lower() for e in VIDEO_EXTENSIONS)
