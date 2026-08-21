"""Erzeugt das Programmsymbol AutoCut.ico – ohne Zusatzpakete.

Aufruf:  python tools/make_icon.py

Das Symbol wird bei der Desktop-Verknüpfung verwendet. Es besteht aus einer
dunklen abgerundeten Fläche, einem orangen Abspiel-Dreieck und Taktbalken
(Beats) darunter. Gezeichnet wird in vierfacher Auflösung und danach
heruntergerechnet – dadurch werden die Kanten weich.
"""

from __future__ import annotations

import os
import struct
import zlib

import numpy as np

GROESSEN = [16, 24, 32, 48, 64, 128, 256]
SUPERSAMPLING = 4

HINTERGRUND = (28, 32, 42)      # dunkles Blaugrau
AKZENT = (255, 138, 48)         # Orange
HELL = (238, 242, 248)          # fast weiß


def _rounded_rect(hoehe: int, breite: int, radius: float) -> np.ndarray:
    """Maske (0..1) einer abgerundeten Fläche."""
    y, x = np.mgrid[0:hoehe, 0:breite].astype(float)
    y += 0.5
    x += 0.5
    # Abstand zum inneren Rechteck, dessen Ecken um 'radius' eingerückt sind
    dx = np.maximum(np.maximum(radius - x, x - (breite - radius)), 0.0)
    dy = np.maximum(np.maximum(radius - y, y - (hoehe - radius)), 0.0)
    abstand = np.sqrt(dx ** 2 + dy ** 2)
    return (abstand <= radius).astype(float)


def _triangle(hoehe: int, breite: int, punkte) -> np.ndarray:
    """Maske eines Dreiecks über die Vorzeichen der Kantengleichungen."""
    y, x = np.mgrid[0:hoehe, 0:breite].astype(float)
    y += 0.5
    x += 0.5
    (x1, y1), (x2, y2), (x3, y3) = punkte

    def kante(xa, ya, xb, yb):
        return (x - xa) * (yb - ya) - (y - ya) * (xb - xa)

    a = kante(x1, y1, x2, y2)
    b = kante(x2, y2, x3, y3)
    c = kante(x3, y3, x1, y1)
    return (((a >= 0) & (b >= 0) & (c >= 0)) | ((a <= 0) & (b <= 0) & (c <= 0))).astype(float)


def _mische(bild: np.ndarray, maske: np.ndarray, farbe) -> None:
    """Zeichnet eine Farbe entsprechend der Maske in das Bild (an Ort und Stelle)."""
    for kanal in range(3):
        bild[:, :, kanal] = bild[:, :, kanal] * (1 - maske) + farbe[kanal] * maske


def zeichne(groesse: int) -> np.ndarray:
    """Zeichnet das Symbol als RGBA-Feld in der gewünschten Kantenlänge."""
    gross = groesse * SUPERSAMPLING
    rgb = np.zeros((gross, gross, 3), dtype=float)
    alpha = np.zeros((gross, gross), dtype=float)

    # Grundfläche
    flaeche = _rounded_rect(gross, gross, gross * 0.22)
    _mische(rgb, flaeche, HINTERGRUND)
    alpha = np.maximum(alpha, flaeche)

    # Abspiel-Dreieck, leicht oberhalb der Mitte
    mitte_y = gross * 0.44
    hoehe = gross * 0.34
    links = gross * 0.36
    rechts = gross * 0.68
    dreieck = _triangle(gross, gross, [
        (links, mitte_y - hoehe / 2),
        (links, mitte_y + hoehe / 2),
        (rechts, mitte_y),
    ])
    _mische(rgb, dreieck, AKZENT)

    # Taktbalken darunter: unterschiedlich hoch wie eine Beat-Anzeige
    hoehen = [0.30, 0.62, 0.44, 0.90, 0.52, 0.34]
    balken_breite = gross * 0.075
    abstand = gross * 0.042
    gesamt = len(hoehen) * balken_breite + (len(hoehen) - 1) * abstand
    start_x = (gross - gesamt) / 2
    unten = gross * 0.80
    max_hoehe = gross * 0.20

    for nummer, anteil in enumerate(hoehen):
        x0 = start_x + nummer * (balken_breite + abstand)
        y0 = unten - max_hoehe * anteil
        maske = np.zeros((gross, gross))
        maske[int(round(y0)):int(round(unten)), int(round(x0)):int(round(x0 + balken_breite))] = 1.0
        # Betonte Schläge in Orange, die übrigen hell
        _mische(rgb, maske, AKZENT if anteil > 0.6 else HELL)

    # Herunterrechnen (Kantenglättung)
    rgb = rgb.reshape(groesse, SUPERSAMPLING, groesse, SUPERSAMPLING, 3).mean(axis=(1, 3))
    alpha = alpha.reshape(groesse, SUPERSAMPLING, groesse, SUPERSAMPLING).mean(axis=(1, 3))

    bild = np.zeros((groesse, groesse, 4), dtype=np.uint8)
    bild[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    bild[:, :, 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return bild


def als_png(bild: np.ndarray) -> bytes:
    """Schreibt ein RGBA-Feld als PNG-Datei (ohne Zusatzpakete)."""
    hoehe, breite = bild.shape[:2]
    roh = b"".join(b"\x00" + bild[zeile].tobytes() for zeile in range(hoehe))

    def block(typ: bytes, daten: bytes) -> bytes:
        return (struct.pack(">I", len(daten)) + typ + daten
                + struct.pack(">I", zlib.crc32(typ + daten) & 0xFFFFFFFF))

    kopf = struct.pack(">IIBBBBB", breite, hoehe, 8, 6, 0, 0, 0)   # 8 Bit, RGBA
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", kopf)
            + block(b"IDAT", zlib.compress(roh, 9)) + block(b"IEND", b""))


def als_ico(pngs: list) -> bytes:
    """Packt mehrere PNG-Bilder in eine ICO-Datei (Windows Vista und neuer)."""
    anzahl = len(pngs)
    kopf = struct.pack("<HHH", 0, 1, anzahl)
    eintraege = b""
    daten = b""
    versatz = 6 + anzahl * 16
    for groesse, png in pngs:
        eintraege += struct.pack(
            "<BBBBHHII",
            groesse if groesse < 256 else 0,   # 0 bedeutet 256
            groesse if groesse < 256 else 0,
            0, 0, 1, 32, len(png), versatz + len(daten),
        )
        daten += png
    return kopf + eintraege + daten


def main() -> str:
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ziel = os.path.join(wurzel, "AutoCut.ico")
    pngs = [(groesse, als_png(zeichne(groesse))) for groesse in GROESSEN]
    with open(ziel, "wb") as datei:
        datei.write(als_ico(pngs))
    print(f"Symbol geschrieben: {ziel} ({os.path.getsize(ziel)} Bytes, "
          f"{len(GROESSEN)} Größen: {', '.join(str(g) for g in GROESSEN)})")
    return ziel


if __name__ == "__main__":
    main()
