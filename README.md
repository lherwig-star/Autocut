# AutoCut

**Automatischer Videoschnitt auf Musik – komplett offline auf deinem eigenen Rechner.**

AutoCut nimmt einen Ordner voller Videoclips und einen Song, findet die Beats
der Musik, bewertet jeden Clip nach Bildqualität und schneidet daraus
automatisch ein fertiges Video – die Schnitte liegen dabei exakt auf den Beats.

* **Keine Internetverbindung nötig** – nichts wird hochgeladen, nichts an eine KI geschickt.
* **Keine laufenden Kosten, keine Anmeldung, kein Abo.** Nur freie Open-Source-Bibliotheken.
* **Die Reihenfolge deiner Clips bleibt immer erhalten** (chronologisch).
* **Nachvollziehbar:** Ein Textreport zeigt für jeden Schnitt, woher er stammt und warum.

---

## Inhalt

1. [Installation unter Windows](#1-installation-unter-windows)
2. [Desktop-Verknüpfung anlegen](#2-desktop-verknüpfung-anlegen)
3. [Bedienung der App](#3-bedienung-der-app)
4. [Bedienung über die Kommandozeile](#4-bedienung-über-die-kommandozeile)
5. [Vorlagen](#5-vorlagen)
6. [Eigene Vorlagen bauen](#6-eigene-vorlagen-bauen)
7. [Wie AutoCut entscheidet](#7-wie-autocut-entscheidet)
8. [Der Report](#8-der-report)
9. [Probleme und Lösungen](#9-probleme-und-lösungen)
10. [Für Entwickler](#10-für-entwickler)

---

## 1. Installation unter Windows

### Der schnelle Weg: ein Doppelklick

1. Projekt herunterladen (grüner Knopf *Code* → *Download ZIP*) und entpacken,
   zum Beispiel nach `C:\Users\DeinName\AutoCut`.
2. **Doppelklick auf `Setup.bat`**.

Das Skript erledigt alles allein:

| Schritt | Was passiert |
|---|---|
| 1 | Prüft Python – fehlt es, wird es über `winget` installiert |
| 2 | Prüft ffmpeg und ffprobe – fehlen sie, werden sie über `winget` installiert |
| 3 | Installiert alle Python-Pakete und prüft, ob sich jedes laden lässt |
| 4 | Macht einen echten Funktionstest: erzeugt Testclips und einen Test-Song und rendert daraus ein Video |
| 5 | Startet die Oberfläche einmal zur Kontrolle |
| 6 | Legt die Desktop-Verknüpfung **AutoCut** an (mit eigenem Symbol) |

Am Ende steht in einfacher Sprache, was eingerichtet wurde und was noch fehlt.
Fragt Windows während der Installation nach Erlaubnis, bitte mit **Ja** bestätigen.

> Wenn du magst, kannst du auch einzelne Schritte auslassen:
> `Setup.bat -NoGuiTest`, `Setup.bat -NoShortcut` oder `Setup.bat -SkipSelfTest`.

**Später jederzeit prüfen, ob noch alles läuft:**

```bat
python autocut.py --selftest
```

Der Selbsttest erzeugt Testdaten, rendert ein kleines Video, prüft das Ergebnis
und löscht danach alles wieder. Am Ende steht entweder *„AutoCut funktioniert auf
diesem Rechner"* oder genau, was fehlt.

---

### Der Weg von Hand

Falls du lieber selbst installierst: Du brauchst genau zwei Dinge – **Python**
und **ffmpeg**. Beides ist kostenlos.

### Schritt 1: Python installieren

1. Öffne <https://www.python.org/downloads/> und lade die aktuelle Version
   für Windows herunter (3.10 oder neuer).
2. Starte die heruntergeladene Datei.
3. **Wichtig:** Setze im ersten Fenster unten den Haken bei
   **„Add python.exe to PATH"**, erst dann auf *Install Now* klicken.
4. Lass die Option **„tcl/tk and IDLE"** aktiviert – daraus besteht die
   Programmoberfläche von AutoCut.

Zum Prüfen: Drücke `Windows-Taste`, tippe `cmd`, öffne die Eingabeaufforderung
und gib ein:

```
python --version
```

Es sollte etwa `Python 3.12.4` erscheinen.

### Schritt 2: ffmpeg installieren

ffmpeg ist das Programm, das im Hintergrund schneidet und rendert.
Öffne die Eingabeaufforderung (oder das Windows-Terminal) und gib ein:

```
winget install ffmpeg
```

Danach das Terminalfenster **schließen und neu öffnen**, dann prüfen:

```
ffmpeg -version
```

<details>
<summary>Falls <code>winget</code> nicht funktioniert (Alternativen)</summary>

**Variante A – ffmpeg als Python-Paket** (einfachste Lösung, AutoCut findet es automatisch):

```
pip install imageio-ffmpeg
```

**Variante B – von Hand**

1. Lade <https://www.gyan.dev/ffmpeg/builds/> → *ffmpeg-release-essentials.zip*.
2. Entpacke das Archiv nach `C:\ffmpeg`.
   Es muss danach die Datei `C:\ffmpeg\bin\ffmpeg.exe` geben.
3. AutoCut sucht dort automatisch. Wer ffmpeg auch in anderen Programmen
   nutzen will, fügt `C:\ffmpeg\bin` zusätzlich der PATH-Variable hinzu
   (Windows-Suche → „Umgebungsvariablen für dieses Konto bearbeiten" →
   *Path* → *Bearbeiten* → *Neu*).
</details>

### Schritt 3: AutoCut herunterladen und starten

1. Lade dieses Projekt herunter (grüner Knopf *Code* → *Download ZIP*) und
   entpacke es, zum Beispiel nach `C:\Users\DeinName\AutoCut`.
2. Öffne den Ordner und mache einen **Doppelklick auf `AutoCut.pyw`**.

Beim **ersten Start** installiert AutoCut die benötigten Programmbausteine
selbst nach (ein kleines Fenster zeigt den Fortschritt, das dauert einige
Minuten). Danach öffnet sich die Oberfläche. **Du musst nie selbst `pip`
ausführen.**

> Falls beim Doppelklick nichts passiert, klicke stattdessen doppelt auf
> **`AutoCut.bat`** – dort siehst du in einem Konsolenfenster, woran es liegt.

---

## 2. Desktop-Verknüpfung anlegen

`Setup.bat` legt die Verknüpfung bereits an. Falls das nicht geklappt hat oder
du sie noch einmal brauchst, geht es auch von Hand:

1. Öffne den AutoCut-Ordner im Explorer.
2. **Rechtsklick** auf die Datei `AutoCut.pyw`.
3. Wähle **„Weitere Optionen anzeigen"** (nur bei Windows 11) →
   **„Senden an"** → **„Desktop (Verknüpfung erstellen)"**.
4. Auf dem Desktop liegt jetzt eine Verknüpfung namens *AutoCut.pyw – Verknüpfung*.
   Mit `F2` kannst du sie in **AutoCut** umbenennen.

**Eigenes Symbol vergeben (optional):** Rechtsklick auf die Verknüpfung →
*Eigenschaften* → *Anderes Symbol...* → ein Symbol auswählen → *OK*.

**An die Taskleiste anheften:** Rechtsklick auf die Verknüpfung →
*An „Start" anheften* bzw. *In Taskleiste anheften*.

---

## 3. Bedienung der App

> Eine Übersicht des gesamten Ablaufs steht in [docs/ablauf.md](docs/ablauf.md).

1. **Clip-Ordner wählen** – auf *Durchsuchen...* klicken oder den Ordner
   einfach in das Feld ziehen.
2. **Musik wählen** – MP3, WAV, M4A, FLAC oder OGG.
3. **Vorlage wählen** – bestimmt Schnitttempo, Übergänge und Farb-Look.
   Unter der Auswahl steht, was die Vorlage macht.
4. **„Video erstellen"** klicken. Der Balken zeigt den Fortschritt; das
   Fenster bleibt dabei bedienbar und lässt sich jederzeit abbrechen.
5. Nach dem Rendern:
   * **„Video öffnen"** startet das Ergebnis im Standard-Player.
   * **„Ordner öffnen"** zeigt die Datei im Explorer.
   * Im Reiter **„Report"** steht, welcher Moment aus welchem Clip stammt.

### Die Knöpfe im Einzelnen

| Knopf | Wirkung |
|---|---|
| **Video erstellen** | Startet die Verarbeitung im Hintergrund |
| **Abbrechen** | Stoppt die laufende Verarbeitung sauber |
| **Vorlagen neu laden** | Liest den Ordner `templates/` neu ein |
| **🔄 Neu laden** | Startet AutoCut neu und übernimmt dabei **Programmänderungen und neue Vorlagen** – ohne PowerShell |
| **Report speichern** | Speichert das Schnittprotokoll als Textdatei |
| **Hilfe** | Kurzanleitung im Programm |

> **Zum Weiterentwickeln:** Wenn du AutoCut später mit Claude Code änderst,
> genügt danach ein Klick auf **„Neu laden"** – die App startet sich selbst
> neu und arbeitet mit dem geänderten Code weiter.

AutoCut merkt sich deine letzten Eingaben (Ordner, Musik, Vorlage) in der
Datei `.autocut_settings.json` in deinem Benutzerordner.

---

## 4. Bedienung über die Kommandozeile

Alles, was die App kann, geht auch im Terminal:

```bat
python autocut.py --clips ./meine_clips --music song.mp3 --template cinematic_vlog --output fertig.mp4
```

| Option | Bedeutung |
|---|---|
| `--clips`, `-c` | Ordner mit den Videoclips |
| `--music`, `-m` | Musikdatei |
| `--template`, `-t` | Name der Vorlage (Standard: `cinematic_vlog`) |
| `--output`, `-o` | Zieldatei (Standard: `autocut_video.mp4`) |
| `--recursive`, `-r` | Auch Unterordner durchsuchen |
| `--order` | `auto` (Standard), `name` oder `date` |
| `--dry-run` | Nur analysieren und Report anzeigen, nichts rendern |
| `--max-music-seconds` | Nur die ersten N Sekunden des Songs verwenden |
| `--list-templates`, `-l` | Alle Vorlagen anzeigen |
| `--gui` | Die grafische Oberfläche öffnen |
| `--quiet`, `-q` | Report am Ende nicht im Terminal ausgeben |

**Erst schauen, dann rendern** – das spart Zeit beim Ausprobieren:

```bat
python autocut.py -c .\clips -m song.mp3 -t energetic --dry-run
```

---

## 5. Vorlagen

Die mitgelieferten Vorlagen liegen als YAML-Dateien im Ordner `templates/`:

| Vorlage | Charakter |
|---|---|
| **cinematic_vlog** | Ruhige, lange Einstellungen (Schnitt alle 6–12 Beats), bevorzugt scharfe und stabile Bilder, weiche Crossfades, leicht warmer filmischer Look |
| **energetic** | Schnitt auf **jeden** Beat, bevorzugt Bewegung und Action, harte Schnitte, kräftigere Farben |
| **travel_recap** | Mischung: in leisen Songpassagen ruhige lange Clips, im Drop/Refrain Schnitt auf jeden Beat |

---

## 6. Eigene Vorlagen bauen

1. Kopiere eine Datei aus `templates/`, zum Beispiel `energetic.yaml`.
2. Benenne die Kopie um, etwa `hochzeit.yaml`.
3. Ändere die Werte und speichere.
4. In der App auf **„Vorlagen neu laden"** klicken – fertig, sie steht in der Liste.

Alle Einstellungen einer Vorlage:

```yaml
name: hochzeit                 # optional, sonst wird der Dateiname genommen
description: "Ruhig und weich" # erscheint in der App unter der Auswahl

# --- Schnittfrequenz ---------------------------------------------------
beats_per_cut: 4        # Schnitt alle N Beats (1 = jeder Beat)
min_clip_length: 1.0    # kürzester Schnitt in Sekunden
max_clip_length: 4.0    # längster Schnitt in Sekunden

adaptive_to_energy: true  # Schnittlänge folgt der Lautstärke des Songs
beats_per_cut_quiet: 8    # leise Passage  -> lange Clips
beats_per_cut_loud: 2     # Drop/Refrain   -> kurze Clips

# --- Gewichtung der Bildbewertung (0 = egal, höher = wichtiger) --------
weights:
  sharpness: 1.4   # Schärfe
  motion: 0.6      # Bewegungsintensität
  exposure: 1.0    # Helligkeit / Belichtung
  stability: 1.5   # Ruhe im Bild (Gegenteil von Verwacklung)

prefer_motion: 0.3      # 0.0 = ruhige Shots bevorzugt, 1.0 = viel Action
scene_cut_penalty: 0.8  # Abzug, wenn im Ausschnitt ein harter Szenenwechsel liegt

# --- Übergänge ---------------------------------------------------------
transition: crossfade      # hard_cut oder crossfade
transition_duration: 0.6   # Sekunden (nur bei crossfade)

# --- Farb-Look ---------------------------------------------------------
color:
  enabled: true
  brightness: 0.02     # -1.0 bis 1.0
  contrast: 1.05       #  0.0 bis 3.0
  saturation: 0.95     #  0.0 bis 3.0
  gamma: 1.0           #  0.1 bis 3.0
  temperature: 0.15    # -1 (kühl/blau) bis 1 (warm/orange)
  vignette: true       # dunklere Ecken
  lut: ""              # optional: voller Pfad zu einer .cube-Datei

# --- Ausgabe -----------------------------------------------------------
output:
  width: 1920
  height: 1080
  fps: 30
  video_bitrate: "14M"
  audio_bitrate: "192k"
  audio_fade_out: 2.0   # Sekunden Musik-Ausblendung am Ende
  preset: medium        # ultrafast ... veryslow (schnell vs. kleine Datei)

# --- Feinheiten --------------------------------------------------------
min_gap_between_moments: 0.5  # Mindestabstand zweier Momente aus demselben Clip
skip_start: 0.3               # Sekunden am Clipanfang ignorieren
skip_end: 0.3                 # Sekunden am Clipende ignorieren
```

Fehlende Werte werden automatisch mit sinnvollen Standardwerten ergänzt –
eine Vorlage darf also auch nur aus zwei Zeilen bestehen. Bei einem Tippfehler
zeigt AutoCut eine verständliche Meldung mit Dateinamen statt eines Absturzes.

**Eigene LUT verwenden:** Trage bei `color.lut` den vollständigen Pfad zu
einer `.cube`-Datei ein, z.B. `lut: "C:/Looks/teal_orange.cube"`, und setze
`enabled: true`.

---

## 7. Wie AutoCut entscheidet

### Musik-Analyse (librosa)
Aus dem Song werden das Tempo, alle Beat-Zeitpunkte und eine Energie-Kurve
berechnet (Lautstärke + Anschlagstärke, geglättet über ca. 1,5 Sekunden).
Die Energie-Kurve unterscheidet leise Strophen von lauten Refrains.

### Video-Analyse (OpenCV, ohne KI)
Jeder Clip wird etwa alle 0,3 Sekunden abgetastet. Pro Abtastpunkt werden
gemessen:

| Kriterium | Messverfahren |
|---|---|
| **Schärfe** | Varianz des Laplacian-Operators – unscharfe Bilder liefern kleine Werte |
| **Bewegung** | Mittlere Differenz zum Vorbild plus globale Bildverschiebung |
| **Belichtung** | Mittlere Helligkeit, Abzug für abgesoffene und ausgefressene Bereiche |
| **Verwacklung** | Streuung der globalen Bildverschiebung (ruckelig ≠ sanfter Schwenk) |
| **Szenenwechsel** | Sehr große Bildunterschiede = harter Schnitt schon im Original |

Alle Werte werden robust auf 0–1 normiert und nach den Gewichten der Vorlage
zu einer Note zusammengefasst.

### Schnittlogik
1. Der Song wird entlang der Beats in Fenster zerlegt. Bei
   `adaptive_to_energy` bestimmt die Energie-Kurve, wie viele Beats ein
   Fenster umfasst.
2. Jede Fenstergrenze wird auf ganze Einzelbilder gerundet – dadurch bleiben
   die Schnitte über die volle Videolänge auf dem Beat (Abweichung unter
   einem halben Bild) statt sich langsam zu verschieben.
3. Die Fenster werden **chronologisch** auf die Clips verteilt, im Verhältnis
   zu deren Länge. Clip 1 bekommt die ersten Fenster, Clip 2 die nächsten usw.
   – die Reihenfolge kann sich nie ändern.
4. Passt ein Block nicht in seinen Clip, wandern Fenster zum nächsten Clip
   mit freier Zeit. Reicht das Material insgesamt nicht, wird am Ende gekürzt
   und die Musik ausgeblendet (steht dann als Hinweis im Report).
5. Innerhalb jedes Clips wird für jede benötigte Länge die bestbewertete
   Stelle gesucht – immer vorwärts, sodass auch die Momente eines Clips in
   ihrer natürlichen Reihenfolge erscheinen.

---

## 8. Der Report

Neben jedem Video entsteht eine Datei `<videoname>_report.txt`
(in der App auch im Reiter *Report* zu sehen):

```
GEWÄHLTE MOMENTE
------------------------------------------------------------------------------
Video-Zeit = Position im fertigen Video, Quelle = Stelle im Originalclip

  #  Video-Zeit    Dauer  Quelle (von-bis)    Note  Clip
  1. 00:00.0        3.03s 00:02.5-00:05.5     0.64  IMG_0431.MOV
     └─ 6 Beat(s), lauter Songteil, Song-Energie 0.81 | Schärfe 0.72, Bewegung 0.31, ...
```

Dazu kommen: eine Liste aller Eingangsclips mit Bildqualität und
Sortiergrund, eine Zusammenfassung je Clip (wie viele Sekunden davon im
Video gelandet sind), nicht verwendete Clips mit Begründung und alle Hinweise.

---

## 9. Probleme und Lösungen

| Meldung / Problem | Lösung |
|---|---|
| **„ffmpeg nicht gefunden"** | Im Terminal `winget install ffmpeg` ausführen, Terminal neu öffnen, AutoCut neu starten. Alternativ `pip install imageio-ffmpeg`. |
| **Doppelklick auf `AutoCut.pyw` bewirkt nichts** | `AutoCut.bat` starten – dort steht die Ursache im Fenster. Meist fehlt Python im PATH. |
| **„Keine Videoclips gefunden"** | Liegen die Videos in Unterordnern? Dann in der App *„Auch Unterordner durchsuchen"* aktivieren. Unterstützt: MP4, MOV, AVI, MKV, MTS, M2TS, WMV, WEBM, MPG, 3GP, FLV. |
| **Video ist kürzer als der Song** | Es gibt zu wenig Filmmaterial. Mehr Clips nehmen oder eine Vorlage mit kürzeren Clips (`energetic`) wählen. |
| **Clips erscheinen in falscher Reihenfolge** | In der App bei *Reihenfolge* auf `name` oder `date` umstellen. `auto` nimmt das Aufnahmedatum aus den Metadaten, sonst den Dateinamen. |
| **Verarbeitung dauert lange** | Normal: die Analyse liest jeden Clip einmal komplett. Für Tests `--max-music-seconds 30` nutzen oder in der Vorlage `preset: ultrafast` setzen. |
| **Setup.bat meldet „kann nicht in den Typ System.Int32 konvertiert werden"** | Alte Fassung des Skripts. Bitte das Projekt neu herunterladen – seit Version 1.0.1 werden alle Python-Abfragen über `tools/probe.py` gestellt, wodurch das Problem nicht mehr auftreten kann. |
| **Setup.bat bricht ab: „winget nicht verfügbar"** | Älteres Windows 10. Python von python.org und ffmpeg von gyan.dev von Hand installieren (siehe oben), danach `Setup.bat` erneut starten. |
| **„Die Ausführung von Skripts ist auf diesem System deaktiviert"** | Nicht die `.ps1` direkt starten, sondern `Setup.bat` – die setzt die nötige Ausnahme nur für diesen einen Aufruf. |
| **Drag & Drop funktioniert nicht** | Optional: `pip install tkinterdnd2`. Ohne dieses Paket funktioniert weiterhin alles über *Durchsuchen...*. |
| **Hochkant-Videos haben schwarze Ränder** | Das Bild wird ins Zielformat eingepasst statt verzerrt. Für Hochkant-Videos in der Vorlage `output: width: 1080, height: 1920` setzen. |

---

## 10. Für Entwickler

### Aufbau

```
Setup.bat           Einrichtung per Doppelklick (ruft setup_windows.ps1)
setup_windows.ps1   prüft/installiert alles, testet, legt die Verknüpfung an
AutoCut.pyw         Programmstart ohne Konsolenfenster
AutoCut.ico         Symbol für die Verknüpfung (erzeugt mit tools/make_icon.py)
autocut/            Verarbeitungslogik (kennt keine Oberfläche)
  selftest.py         Selbsttest: prüft diesen Rechner von Python bis Rendern
  audio_analysis.py   Beats, Tempo, Energie-Kurve (librosa)
  video_analysis.py   Schärfe, Bewegung, Belichtung, Verwacklung (OpenCV)
  edit_plan.py        Beat-Raster, Verteilung, Momentauswahl
  render.py           ffmpeg: schneiden, überblenden, Musik einbetten
  templates.py        Vorlagen laden und prüfen
  clips.py            Clips finden und chronologisch sortieren
  report.py           Textreport
  pipeline.py         Orchestrierung – einzige Schnittstelle für GUI und CLI
  ffmpeg_tools.py     ffmpeg finden und aufrufen
  errors.py           Fehler mit verständlichem Klartext
gui/                Oberfläche (nutzt nur autocut.pipeline)
templates/          Vorlagen als YAML
tests/              Tests inklusive Erzeugung eigener Testdaten
```

GUI und Logik sind strikt getrennt: `gui/` ruft ausschließlich
`autocut.pipeline.run_autocut(...)` auf und übergibt dabei eine
Fortschritts-Funktion und eine Abbruch-Prüfung.

### Tests

```bat
pip install pytest
python -m pytest tests -q
```

Die Tests erzeugen ihre Testdaten selbst mit ffmpeg (Klick-Track mit exakt
120 BPM, Clips mit bekannten Eigenschaften: scharf, unscharf, dunkel,
unbewegt, halb gut). Geprüft werden unter anderem:

* Beat-Erkennung trifft das echte Raster,
* die Energie-Kurve erkennt die leise Passage,
* unscharfe/dunkle Clips werden messbar schlechter bewertet,
* aus einem halb-guten Clip wird die gute Hälfte gewählt,
* die Clip-Reihenfolge bleibt in jedem Fall erhalten,
* Schnitte liegen unter einem halben Bild neben dem Beat,
* Crossfades blenden wirklich über und verändern die Gesamtlänge nicht,
* Fehler kommen als Klartext und nie als Traceback.

### Verwendete Bibliotheken

| Paket | Wofür | Lizenz |
|---|---|---|
| [librosa](https://librosa.org/) | Beat- und Energieanalyse | ISC |
| [OpenCV](https://opencv.org/) | Bildbewertung | Apache 2.0 |
| [NumPy](https://numpy.org/) | Berechnungen | BSD |
| [PyYAML](https://pyyaml.org/) | Vorlagen | MIT |
| [ffmpeg](https://ffmpeg.org/) | Schneiden und Rendern | LGPL/GPL |
| Tkinter | Oberfläche (Teil von Python) | PSF |
