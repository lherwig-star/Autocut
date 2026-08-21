"""Tests der Oberfläche.

Diese Tests brauchen Tkinter und eine Bildschirmausgabe. Fehlt eines von
beidem (z.B. auf einem Server), werden sie automatisch übersprungen.
"""

import os
import sys

import pytest

tk = pytest.importorskip("tkinter", reason="Tkinter ist nicht installiert")

if sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"):
    pytest.skip("Keine Bildschirmausgabe verfügbar", allow_module_level=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    from gui.app import AutoCutApp
    from gui.widgets import create_root

    root = create_root()
    anwendung = AutoCutApp(root)
    root.update()
    yield anwendung
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_fenster_baut_sich_auf(app):
    assert "AutoCut" in app.root.title()
    assert app.tabs.index("end") == 2   # Verlauf + Report


def test_vorlagen_stehen_im_auswahlfeld(app):
    namen = list(app.template_box.cget("values"))
    for erwartet in ("cinematic_vlog", "energetic", "travel_recap"):
        assert erwartet in namen
    assert app.template_name.get() in namen


def test_neue_vorlage_erscheint_nach_neu_laden(app, tmp_path, monkeypatch):
    """Neue YAML-Datei im Vorlagenordner muss ohne Codeänderung auftauchen."""
    import autocut.templates as templates

    vorher = list(app.template_box.cget("values"))
    (tmp_path / "meine_test_vorlage.yaml").write_text(
        "description: Test\nbeats_per_cut: 3\n", encoding="utf-8")
    monkeypatch.setattr(templates, "templates_dir", lambda base=None: str(tmp_path))

    app.load_templates()
    app.root.update()
    assert "meine_test_vorlage" in list(app.template_box.cget("values"))
    assert vorher != list(app.template_box.cget("values"))


def test_startknopf_erst_bei_vollstaendiger_eingabe(app, testdata):
    app.clips_row.set("")
    app.music_row.set("")
    app.update_ready_state()
    assert str(app.start_button.cget("state")) == "disabled"

    app.clips_row.set(testdata["clips_dir"])
    app.music_row.set(testdata["music"])
    app.root.update()
    assert str(app.start_button.cget("state")) == "normal"


def test_zieldatei_wird_vorgeschlagen(app, testdata):
    app.clips_row.set(testdata["clips_dir"])
    vorschlag = app.suggest_output()
    assert vorschlag.endswith(".mp4")
    assert app.template_name.get() in vorschlag


def test_ergebnisknoepfe_sind_anfangs_gesperrt(app):
    for knopf in (app.open_video_button, app.open_folder_button, app.save_report_button):
        assert str(knopf.cget("state")) == "disabled"


def test_fehlender_ordner_zeigt_dialog_statt_absturz(app, monkeypatch, tmp_path):
    import gui.app as gui_app

    gezeigt = {}

    class DialogAttrappe:
        def __init__(self, parent, title, message, details=""):
            gezeigt["titel"] = title
            gezeigt["text"] = message

    monkeypatch.setattr(gui_app, "ErrorDialog", DialogAttrappe)
    app.clips_row.set(str(tmp_path / "gibt_es_nicht"))
    app.music_row.set(str(tmp_path / "auch_nicht.mp3"))
    app.output_row.set(str(tmp_path / "x.mp4"))
    app.start()

    assert "nicht gefunden" in gezeigt.get("titel", "")
    assert "Traceback" not in gezeigt.get("text", "")
    assert app.worker is None   # es wurde gar nicht erst gestartet


def test_verarbeitungsfehler_wird_als_dialog_gezeigt(app, monkeypatch):
    import gui.widgets as widgets
    from autocut.errors import MusicFileError

    gezeigt = {}

    class DialogAttrappe:
        def __init__(self, parent, title, message, details=""):
            gezeigt["titel"] = title

    monkeypatch.setattr(widgets, "ErrorDialog", DialogAttrappe)
    app.on_failed(MusicFileError("Datei unlesbar", "Nutze MP3 oder WAV."))
    assert gezeigt.get("titel") == "Musikdatei nicht lesbar"
    assert "Fehlgeschlagen" in app.status.cget("text")


def test_abbruch_setzt_die_oberflaeche_zurueck(app):
    from autocut.errors import CancelledError

    app.set_running(True)
    assert str(app.start_button.cget("state")) == "disabled"
    app.on_failed(CancelledError())
    assert "Abgebrochen" in app.status.cget("text")
    assert app.progress.cget("value") == 0


def test_einstellungen_werden_gespeichert_und_geladen(app, tmp_path, monkeypatch, testdata):
    import gui.app as gui_app

    monkeypatch.setattr(gui_app, "SETTINGS_FILE", str(tmp_path / "einstellungen.json"))
    app.clips_row.set(testdata["clips_dir"])
    app.music_row.set(testdata["music"])
    app.template_name.set("energetic")
    app.save_settings()

    app.clips_row.set("")
    app.load_settings()
    assert app.clips_row.get() == testdata["clips_dir"]
    assert app.template_name.get() == "energetic"


def test_abgelegte_pfade_werden_richtig_zerlegt():
    """Tk liefert mehrere abgelegte Dateien als eine Zeichenkette."""
    from gui.widgets import _split_drop_paths

    assert _split_drop_paths("/pfad/datei.mp4") == ["/pfad/datei.mp4"]
    assert _split_drop_paths("{C:/Meine Videos/clip 1.mp4} {C:/x/y.mp4}") == [
        "C:/Meine Videos/clip 1.mp4", "C:/x/y.mp4"]
    assert _split_drop_paths("/a/b.mp4 /c/d.mp4") == ["/a/b.mp4", "/c/d.mp4"]


def test_ordner_statt_datei_beim_ablegen(app, testdata):
    """Wird eine Datei auf das Ordnerfeld gezogen, wird ihr Ordner genommen."""
    app.clips_row._dropped([testdata["clips"][0]])
    assert app.clips_row.get() == os.path.dirname(testdata["clips"][0])
