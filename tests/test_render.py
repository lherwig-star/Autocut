"""Tests des Renderns: Übergänge, Farb-Look, Beat-Genauigkeit."""

import subprocess

import pytest

from autocut.edit_plan import EditPlan, Moment
from autocut.ffmpeg_tools import ffmpeg_path, probe
from autocut.render import build_color_filter, build_scale_filter, render
from autocut.templates import load_template


@pytest.fixture(scope="module")
def farbclips(tmp_path_factory):
    """Zwei einfarbige Clips + Stille – ideal, um Überblendungen zu messen."""
    folder = tmp_path_factory.mktemp("farben")
    ffmpeg = ffmpeg_path()
    pfade = {}
    for name, farbe in (("rot", "red"), ("gruen", "green"), ("grau", "gray")):
        ziel = folder / f"{name}.mp4"
        subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi",
                        "-i", f"color=c={farbe}:s=320x180:r=30:d=5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(ziel)], check=True)
        pfade[name] = str(ziel)
    stille = folder / "stille.wav"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo", "-t", "12", str(stille)], check=True)
    pfade["musik"] = str(stille)
    return pfade


def _plan(farbclips, dauer=3.0):
    plan = EditPlan(template_name="test", music_path=farbclips["musik"],
                    music_duration=12.0, total_duration=dauer * 2)
    plan.moments = [
        Moment(0, 0, "rot.mp4", farbclips["rot"], 0, dauer, 0, dauer, 0.9, 0.5, 0),
        Moment(1, 1, "gruen.mp4", farbclips["gruen"], 0, dauer, dauer, dauer * 2, 0.9, 0.5, 1),
    ]
    return plan


def _kleine_vorlage(uebergang, dauer=1.0, farbe=False):
    template = load_template("cinematic_vlog")
    template.data["transition"] = uebergang
    template.data["transition_duration"] = dauer
    template.data["color"]["enabled"] = farbe
    template.data["output"].update(width=320, height=180, fps=30,
                                   audio_fade_out=0.0, preset="ultrafast")
    return template


def _pixelfarben(video, zeiten):
    import cv2

    cap = cv2.VideoCapture(video)
    bilder = []
    while True:
        ok, bild = cap.read()
        if not ok:
            break
        bilder.append(bild[90, 160].astype(int))   # Mittelpunkt, BGR
    cap.release()
    return {t: bilder[int(t * 30)] for t in zeiten if int(t * 30) < len(bilder)}, len(bilder)


def test_harter_schnitt_hat_keine_ueberblendung(farbclips, tmp_path):
    ziel = tmp_path / "hart.mp4"
    render(_plan(farbclips), _kleine_vorlage("hard_cut"), farbclips["musik"], str(ziel))
    farben, anzahl = _pixelfarben(str(ziel), [1.0, 2.9, 3.1, 5.0])
    assert farben[2.9][2] > 200 and farben[2.9][1] < 60      # vorher rot
    assert farben[3.1][1] > 100 and farben[3.1][2] < 60      # danach grün
    assert anzahl == pytest.approx(180, abs=2)               # 6.0s bei 30 fps


def test_crossfade_blendet_wirklich_ueber(farbclips, tmp_path):
    ziel = tmp_path / "weich.mp4"
    render(_plan(farbclips), _kleine_vorlage("crossfade", 1.0), farbclips["musik"], str(ziel))
    farben, anzahl = _pixelfarben(str(ziel), [1.0, 2.95, 3.5, 4.2, 5.5])

    # Vor dem Übergang rein rot, danach rein grün ...
    assert farben[2.95][2] > 200 and farben[2.95][1] < 60
    assert farben[4.2][1] > 100 and farben[4.2][2] < 40
    # ... und in der Mitte des Übergangs eine echte Mischung aus beidem.
    mitte = farben[3.5]
    assert 40 < mitte[2] < 200, f"Rot-Anteil in der Mitte: {mitte[2]}"
    assert 30 < mitte[1] < 120, f"Grün-Anteil in der Mitte: {mitte[1]}"


def test_crossfade_veraendert_die_gesamtlaenge_nicht(farbclips, tmp_path):
    """Entscheidend für die Beat-Treue: die Überblendung darf nichts verschieben."""
    ziel = tmp_path / "laenge.mp4"
    plan = _plan(farbclips, dauer=2.0)
    render(plan, _kleine_vorlage("crossfade", 0.8), farbclips["musik"], str(ziel))
    info = probe(str(ziel))
    assert info.duration == pytest.approx(plan.total_duration, abs=0.07)


def test_farblook_wird_angewendet(farbclips, tmp_path):
    """Mit warmem Look muss dasselbe Bild messbar wärmer werden.

    Gemessen wird an neutralem Grau – bei reinem Rot wäre der Rotkanal
    schon am Anschlag und eine Änderung nicht messbar.
    """
    def grauplan():
        plan = EditPlan(template_name="test", music_path=farbclips["musik"],
                        music_duration=12.0, total_duration=4.0)
        plan.moments = [
            Moment(0, 0, "grau.mp4", farbclips["grau"], 0, 2.0, 0, 2.0, 0.9, 0.5, 0),
            Moment(1, 0, "grau.mp4", farbclips["grau"], 2.0, 4.0, 2.0, 4.0, 0.9, 0.5, 1),
        ]
        return plan

    neutral, warm = tmp_path / "neutral.mp4", tmp_path / "warm.mp4"
    render(grauplan(), _kleine_vorlage("hard_cut"), farbclips["musik"], str(neutral))

    template = _kleine_vorlage("hard_cut", farbe=True)
    template.data["color"].update(temperature=0.8, saturation=1.0, brightness=0.0,
                                  contrast=1.0, gamma=1.0, vignette=False, lut="")
    render(grauplan(), template, farbclips["musik"], str(warm))

    import cv2
    import numpy as np

    def mittelwert(pfad):
        cap = cv2.VideoCapture(pfad)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
        _ok, bild = cap.read()
        cap.release()
        return np.mean(bild.reshape(-1, 3), axis=0)   # BGR

    blau_n, _gruen_n, rot_n = mittelwert(str(neutral))
    blau_w, _gruen_w, rot_w = mittelwert(str(warm))
    assert rot_w > rot_n, "Der warme Look muss den Rotanteil anheben"
    assert blau_w < blau_n, "Der warme Look muss den Blauanteil senken"
    assert (rot_w - blau_w) > (rot_n - blau_n)


def test_farbfilter_wird_korrekt_gebaut():
    template = _kleine_vorlage("hard_cut", farbe=True)
    template.data["color"].update(brightness=0.05, contrast=1.1, saturation=0.9,
                                  gamma=1.0, temperature=0.2, vignette=True, lut="")
    filterkette = build_color_filter(template)
    assert "eq=" in filterkette
    assert "colorchannelmixer=" in filterkette
    assert "vignette" in filterkette

    template.data["color"]["enabled"] = False
    assert build_color_filter(template) == ""


def test_fehlende_lut_datei_wird_verstaendlich_gemeldet():
    from autocut.errors import RenderError

    template = _kleine_vorlage("hard_cut", farbe=True)
    template.data["color"]["lut"] = "C:/gibt/es/nicht.cube"
    with pytest.raises(RenderError) as fehler:
        build_color_filter(template)
    assert ".cube" in fehler.value.hint


def test_hochkant_material_wird_eingepasst_nicht_verzerrt():
    template = _kleine_vorlage("hard_cut")
    filterkette = build_scale_filter(template)
    assert "force_original_aspect_ratio=decrease" in filterkette
    assert "pad=320:180" in filterkette
    assert "setsar=1" in filterkette
