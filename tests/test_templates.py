"""Tests des Vorlagen-Systems inklusive der Fehlermeldungen."""

import pytest

from autocut.errors import TemplateError
from autocut.templates import (
    DEFAULTS, list_templates, load_all, load_template, templates_dir,
)

MITGELIEFERT = ["cinematic_vlog", "energetic", "travel_recap"]


def test_mitgelieferte_vorlagen_sind_da():
    vorhanden = list_templates()
    for name in MITGELIEFERT:
        assert name in vorhanden


def test_alle_vorlagen_laden_fehlerfrei():
    geladen = load_all()
    assert len(geladen) >= 3
    for template in geladen:
        assert template.name and template.description
        assert template.summary()


@pytest.mark.parametrize("name", MITGELIEFERT)
def test_vorlage_hat_alle_pflichtwerte(name):
    template = load_template(name)
    for schluessel in DEFAULTS:
        assert schluessel in template.data
    for kriterium in ("sharpness", "motion", "exposure", "stability"):
        assert kriterium in template.weights


def test_die_drei_vorlagen_unterscheiden_sich_wie_beschrieben():
    schnell = load_template("energetic")
    ruhig = load_template("cinematic_vlog")
    mix = load_template("travel_recap")

    # energetic: Schnitt auf jeden Beat, harte Schnitte, Bewegung bevorzugt
    assert schnell["beats_per_cut"] == 1
    assert schnell["transition"] == "hard_cut"
    assert schnell["prefer_motion"] > 0.8
    assert schnell["max_clip_length"] < ruhig["min_clip_length"]

    # cinematic_vlog: langsam, Crossfade, ruhige stabile Shots, Farb-Look
    assert ruhig["transition"] == "crossfade"
    assert ruhig["prefer_motion"] < 0.3
    assert ruhig.weights["stability"] > schnell.weights["stability"]
    assert ruhig.color["enabled"]

    # travel_recap: passt sich der Songenergie an
    assert mix["adaptive_to_energy"]
    assert mix["beats_per_cut_quiet"] > mix["beats_per_cut_loud"]


def test_eigene_vorlage_wird_automatisch_gefunden(tmp_path):
    (tmp_path / "meine_vorlage.yaml").write_text(
        "description: Test\nbeats_per_cut: 2\nmin_clip_length: 1.0\nmax_clip_length: 3.0\n",
        encoding="utf-8",
    )
    assert "meine_vorlage" in list_templates(str(tmp_path))
    template = load_template("meine_vorlage", str(tmp_path))
    assert template["beats_per_cut"] == 2
    # Nicht angegebene Werte kommen aus den Standardwerten.
    assert template["transition"] == DEFAULTS["transition"]


def test_unbekannte_vorlage_nennt_die_verfuegbaren():
    with pytest.raises(TemplateError) as fehler:
        load_template("gibt_es_nicht")
    assert "gibt_es_nicht" in fehler.value.message
    assert "cinematic_vlog" in fehler.value.hint


def test_unsinnige_werte_werden_verstaendlich_gemeldet(tmp_path):
    faelle = {
        "min_groesser_max.yaml": "min_clip_length: 5.0\nmax_clip_length: 2.0\n",
        "falscher_uebergang.yaml": "transition: zauberblende\n",
        "text_statt_zahl.yaml": "beats_per_cut: viele\n",
        "alle_gewichte_null.yaml": (
            "weights:\n  sharpness: 0\n  motion: 0\n  exposure: 0\n  stability: 0\n"),
    }
    for datei, inhalt in faelle.items():
        (tmp_path / datei).write_text(inhalt, encoding="utf-8")
        with pytest.raises(TemplateError) as fehler:
            load_template(datei[:-5], str(tmp_path))
        # Die Meldung muss den Dateinamen nennen, damit man weiß, wo man sucht.
        assert datei in fehler.value.message or datei[:-5] in fehler.value.message


def test_kaputtes_yaml_gibt_verstaendlichen_fehler(tmp_path):
    (tmp_path / "kaputt.yaml").write_text("weights:\n  sharpness: 1.0\n   motion: 2\n",
                                          encoding="utf-8")
    with pytest.raises(TemplateError) as fehler:
        load_template("kaputt", str(tmp_path))
    assert "Einrückung" in fehler.value.hint or "Format" in fehler.value.message


def test_uebergang_wird_nie_laenger_als_der_kuerzeste_clip(tmp_path):
    (tmp_path / "extrem.yaml").write_text(
        "min_clip_length: 0.5\nmax_clip_length: 2.0\n"
        "transition: crossfade\ntransition_duration: 4.0\n", encoding="utf-8")
    template = load_template("extrem", str(tmp_path))
    assert template["transition_duration"] <= 0.5 * 0.6 + 1e-9


def test_ungerade_bildgroesse_wird_korrigiert(tmp_path):
    (tmp_path / "ungerade.yaml").write_text(
        "output:\n  width: 1921\n  height: 1081\n", encoding="utf-8")
    template = load_template("ungerade", str(tmp_path))
    assert template.output["width"] % 2 == 0
    assert template.output["height"] % 2 == 0


def test_standardordner_wird_gefunden():
    import os
    assert os.path.isdir(templates_dir())
