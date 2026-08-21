"""Tests des Windows-Einrichtungsskripts.

Hintergrund: Windows PowerShell 5.1 (auf Windows 10 vorinstalliert) baut aus
den Argumenten für ein externes Programm eine Kommandozeile zusammen, ohne
Anführungszeichen **innerhalb** eines Arguments zu schützen. Ein Aufruf wie

    & python -c 'import sys; print("hallo")'

kommt beim Programm deshalb zerlegt an und stürzt ab. PowerShell 7 macht es
richtig – ein Test unter PowerShell 7 findet den Fehler also nicht.

Diese Tests bilden das Verhalten von 5.1 nach und stellen sicher, dass das
Einrichtungsskript keine solchen Aufrufe mehr enthält.
"""

import os
import subprocess
import sys

import pytest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKRIPT = os.path.join(WURZEL, "setup_windows.ps1")
PROBE = os.path.join(WURZEL, "tools", "probe.py")
STARTER = os.path.join(WURZEL, "Setup.bat")


# ---------------------------------------------------------------------------
# Nachbildung der Argumentübergabe von Windows PowerShell 5.1
# ---------------------------------------------------------------------------

def powershell51_kommandozeile(argumente) -> str:
    """Baut die Kommandozeile so zusammen, wie es Windows PowerShell 5.1 tut.

    Entscheidend: Argumente mit Leerzeichen werden in Anführungszeichen
    gesetzt, aber bereits enthaltene Anführungszeichen bleiben ungeschützt.
    """
    teile = []
    for argument in argumente:
        if argument == "" or any(zeichen in argument for zeichen in " \t"):
            teile.append('"' + argument + '"')
        else:
            teile.append(argument)
    return " ".join(teile)


def windows_argumente(kommandozeile: str):
    """Zerlegt eine Kommandozeile nach den Regeln von CommandLineToArgvW."""
    argumente = []
    aktuell = ""
    in_anfuehrung = False
    hat_inhalt = False
    index = 0
    while index < len(kommandozeile):
        zeichen = kommandozeile[index]
        if zeichen == '"':
            in_anfuehrung = not in_anfuehrung
            hat_inhalt = True
        elif zeichen in " \t" and not in_anfuehrung:
            if hat_inhalt:
                argumente.append(aktuell)
                aktuell = ""
                hat_inhalt = False
        else:
            aktuell += zeichen
            hat_inhalt = True
        index += 1
    if hat_inhalt:
        argumente.append(aktuell)
    return argumente


def wie_powershell51(argumente):
    """Was kommt beim aufgerufenen Programm an, wenn 5.1 den Aufruf macht?"""
    return windows_argumente(powershell51_kommandozeile(argumente))


def test_nachbildung_laesst_einfache_argumente_unveraendert():
    assert wie_powershell51(["python", "skript.py", "version"]) == \
        ["python", "skript.py", "version"]


def test_nachbildung_haelt_pfade_mit_leerzeichen_zusammen():
    assert wie_powershell51(["python", r"C:\Meine Dateien\probe.py", "pfad"]) == \
        ["python", r"C:\Meine Dateien\probe.py", "pfad"]


def test_nachbildung_zeigt_den_bekannten_fehler():
    """Genau dieser Fall hat die Einrichtung zum Absturz gebracht."""
    original = 'import sys; print("%d.%d.%d" % sys.version_info[:3])'
    angekommen = wie_powershell51(["python", "-c", original])[-1]
    assert angekommen != original
    assert '"' not in angekommen          # die Anführungszeichen sind weg
    assert angekommen == "import sys; print(%d.%d.%d % sys.version_info[:3])"


def test_der_alte_aufruf_wuerde_wirklich_abstuerzen():
    """Beweis am echten Python: so zerlegt ist der Code ein Syntaxfehler."""
    original = 'import sys; print("%d.%d.%d" % sys.version_info[:3])'
    angekommen = wie_powershell51([sys.executable, "-c", original])[-1]
    ergebnis = subprocess.run([sys.executable, "-c", angekommen],
                              capture_output=True, text=True)
    assert ergebnis.returncode != 0
    # Die erste Zeile der Fehlerausgabe ist genau das, was das Skript als
    # vermeintliche Versionsnummer gelesen hat.
    assert ergebnis.stderr.splitlines()[0].strip().startswith('File "<string>", line 1')


# ---------------------------------------------------------------------------
# Die Abfragedatei überlebt die Übergabe von PowerShell 5.1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("abfrage", ["version", "pfad", "tkinter", "pakete", "ffmpeg"])
def test_abfragen_funktionieren_auch_ueber_powershell51(abfrage):
    argumente = wie_powershell51([sys.executable, PROBE, abfrage])
    ergebnis = subprocess.run(argumente, capture_output=True, text=True)
    # tkinter/ffmpeg dürfen "fehlt" melden (Rückgabewert 1), aber niemals abstürzen.
    assert "Traceback" not in ergebnis.stderr, ergebnis.stderr
    assert ergebnis.returncode in (0, 1)


def test_versionsabfrage_liefert_eine_echte_nummer():
    ergebnis = subprocess.run(wie_powershell51([sys.executable, PROBE, "version"]),
                              capture_output=True, text=True)
    ausgabe = ergebnis.stdout.strip()
    teile = ausgabe.split(".")
    assert len(teile) == 3
    assert all(teil.isdigit() for teil in teile), f"unerwartete Ausgabe: {ausgabe!r}"
    assert int(teile[0]) == sys.version_info[0]
    assert int(teile[1]) == sys.version_info[1]


def test_pfadabfrage_liefert_diesen_python():
    ergebnis = subprocess.run(wie_powershell51([sys.executable, PROBE, "pfad"]),
                              capture_output=True, text=True)
    assert os.path.exists(ergebnis.stdout.strip())


def test_unbekannte_abfrage_meldet_die_moeglichkeiten():
    ergebnis = subprocess.run([sys.executable, PROBE, "quatsch"],
                              capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "version" in ergebnis.stderr and "pakete" in ergebnis.stderr


def test_abfragedatei_braucht_keine_zusatzpakete():
    """Sie muss auch dann laufen, wenn noch gar nichts installiert ist."""
    quelltext = open(PROBE, encoding="utf-8").read()
    kopf = quelltext.split("def frage_version")[0]
    for paket in ("numpy", "librosa", "cv2", "yaml", "soundfile"):
        assert f"import {paket}" not in kopf, \
            f"{paket} darf nicht beim Start importiert werden"


# ---------------------------------------------------------------------------
# Das Skript selbst
# ---------------------------------------------------------------------------

def _skript_text() -> str:
    return open(SKRIPT, encoding="utf-8-sig").read()


def test_skript_ruft_python_nie_mit_c_auf():
    """Die Regel, die den Fehler von damals dauerhaft ausschliesst."""
    text = _skript_text()
    for zeile in text.splitlines():
        blank = zeile.strip()
        if blank.startswith("#"):
            continue
        assert "'-c'" not in blank, f"verbotener -c-Aufruf: {blank}"
        assert " -c $" not in blank, f"verbotener -c-Aufruf: {blank}"


def test_skript_ist_utf8_mit_bom():
    """Ohne BOM liest Windows PowerShell 5.1 die Datei als ANSI."""
    rohdaten = open(SKRIPT, "rb").read()
    assert rohdaten[:3] == b"\xef\xbb\xbf"


def test_skript_hat_windows_zeilenenden():
    rohdaten = open(SKRIPT, "rb").read()
    assert b"\r\n" in rohdaten
    assert rohdaten.replace(b"\r\n", b"").count(b"\n") == 0


def test_starter_ist_reines_ascii():
    """cmd.exe stellt Sonderzeichen je nach Codepage falsch dar."""
    rohdaten = open(STARTER, "rb").read()
    rohdaten.decode("ascii")   # wirft bei Sonderzeichen
    assert b"\r\n" in rohdaten


def test_starter_umgeht_die_ausfuehrungssperre():
    text = open(STARTER, encoding="ascii").read()
    assert "-ExecutionPolicy Bypass" in text
    assert "setup_windows.ps1" in text


def test_skript_prueft_ob_die_abfragedatei_vorhanden_ist():
    assert "Test-Path -LiteralPath $Probe" in _skript_text()


def test_versionspruefung_vertraegt_unsinnige_ausgaben():
    """Statt [int]-Umwandlung wird auf ein Zahlenmuster geprüft."""
    text = _skript_text()
    assert "-notmatch" in text
    assert "[int]$teile[0]" not in text
