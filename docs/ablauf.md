# Ablauf einer Verarbeitung

```
   Clip-Ordner              Musikdatei
        |                        |
        v                        v
 [1] Clips einlesen        [2] Musik analysieren
     chronologisch              Tempo, Beats, Energie-Kurve
     sortieren                  (librosa)
        |                        |
        v                        |
 [3] Video-Analyse               |
     Schärfe, Bewegung,          |
     Belichtung, Verwacklung     |
     (OpenCV)                    |
        |                        |
        +-----------+------------+
                    v
            [4] Schnittplan
                Beat-Raster (energieabhängig)
                -> chronologisch auf Clips verteilen
                -> beste Momente je Clip wählen
                    |
                    v
            [5] Rendern (ffmpeg)
                Segmente schneiden + vereinheitlichen
                Hard Cut (concat) oder Crossfade (xfade)
                Farb-Look, Musik + Ausblendung
                    |
        +-----------+------------+
        v                        v
   fertiges Video           Textreport
```

Fortschrittsanteile in der Oberfläche:

| Schritt | Anteil |
|---|---|
| Clips einlesen | 5 % |
| Musik analysieren | 8 % |
| Video-Analyse | 37 % |
| Schnittplan | 3 % |
| Rendern | 47 % |
