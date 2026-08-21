# AutoCut – Projektplan

Ziel: 100 % lokales, kostenloses Tool für automatischen Videoschnitt auf Musik.
Keine API-Calls, keine Cloud, nur Open-Source-Bibliotheken.

## Architektur

```
Autocut/
├── AutoCut.pyw            # Doppelklick-Start (ohne Konsolenfenster), Auto-Setup
├── AutoCut.bat            # Alternativ-Start mit Konsole (Diagnose)
├── autocut.py             # CLI-Einstieg
├── requirements.txt
├── README.md
├── templates/             # Vorlagen als YAML (frei erweiterbar)
│   ├── cinematic_vlog.yaml
│   ├── energetic.yaml
│   └── travel_recap.yaml
├── autocut/               # Verarbeitungslogik (GUI-unabhängig)
│   ├── errors.py          # verständliche Fehler (Titel + Klartext + Hilfe)
│   ├── ffmpeg_tools.py    # ffmpeg/ffprobe finden, proben, ausführen
│   ├── templates.py       # Vorlagen laden & validieren
│   ├── clips.py           # Clips finden + chronologisch sortieren
│   ├── audio_analysis.py  # librosa: Beats, Tempo, Energie-Kurve
│   ├── video_analysis.py  # OpenCV: Schärfe, Bewegung, Helligkeit, Verwacklung
│   ├── edit_plan.py       # Beat-Raster + Verteilung + Momentauswahl
│   ├── render.py          # ffmpeg: Segmente schneiden, Übergänge, Musik
│   ├── report.py          # Textreport der Auswahl
│   └── pipeline.py        # Orchestrierung + Fortschritts-Callback
├── gui/                   # Tkinter-Desktop-App (nur Bedienung)
│   ├── app.py
│   └── widgets.py
└── tests/                 # Tests mit selbst erzeugten Mini-Testdaten
```

## Trennung GUI / Logik
`gui/` importiert ausschließlich `autocut.pipeline.run_autocut(...)`.
Dadurch funktioniert der "Neu laden"-Button (Neustart des Prozesses) und
Weiterentwicklung der Logik ohne GUI-Anpassung.

## Verarbeitungskette
1. **Clips einlesen** – Sortierung nach Aufnahmedatum (Metadaten) bzw. Dateiname.
   Die Reihenfolge bleibt im gesamten Prozess unverändert.
2. **Musik-Analyse** (librosa) – Tempo, Beat-Zeitpunkte, Energie-Kurve (RMS+Onset).
3. **Video-Analyse** (OpenCV) – Sampling alle N ms je Clip:
   Schärfe (Varianz des Laplacian), Bewegung (Frame-Differenz + globale
   Verschiebung), Helligkeit/Belichtung (Mittelwert + Clipping-Strafe),
   Verwacklung (Streuung der globalen Verschiebung), Szenenwechsel-Marker.
4. **Beat-Raster** – Schnittzeitpunkte aus Beats, Schnittfrequenz und
   (optional) Energie-adaptiv: leise Passagen -> längere Clips.
5. **Verteilung** – Segmente chronologisch proportional zur Cliplänge verteilt.
6. **Momentauswahl** – je Clip die bestbewerteten, nicht überlappenden Fenster,
   innerhalb des Clips ebenfalls in zeitlicher Reihenfolge.
7. **Rendern** – Segmente normalisieren (Auflösung/FPS/Look), Hard Cut per
   concat oder Crossfade per xfade, Musik als Tonspur, Fade-out am Ende.
8. **Report** – Textübersicht: welcher Moment aus welchem Clip, mit Bewertung.

## Reihenfolge der Umsetzung
1. Grundgerüst, Fehlerklassen, ffmpeg-Erkennung, Templates + 3 Vorlagen
2. Musik-Analyse + Test mit erzeugtem Testsong
3. Video-Analyse + Test mit erzeugten Testclips (scharf/unscharf, hell/dunkel)
4. Schnittlogik + Tests der Invarianten (Reihenfolge, Längen, Beat-Treue)
5. Render + Report, CLI
6. GUI, Startdateien, README
