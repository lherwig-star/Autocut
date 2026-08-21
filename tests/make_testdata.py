"""Erzeugt kleine Testdaten (Musik + Videoclips) ohne externe Downloads.

Aufruf:  python tests/make_testdata.py [zielordner]
"""

from __future__ import annotations

import os
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autocut import ffmpeg_tools  # noqa: E402


def make_click_track(path: str, bpm: float = 120.0, duration: float = 24.0,
                     sr: int = 22050, quiet_section=(8.0, 16.0)) -> str:
    """Schreibt eine WAV-Datei mit klarem Beat und einer leisen Passage.

    Der Song besteht aus kurzen Klick-Impulsen im Takt plus einem Bass-Ton.
    Zwischen ``quiet_section`` ist alles deutlich leiser -> die Energie-Kurve
    muss dort einbrechen.
    """
    import numpy as np

    n = int(duration * sr)
    t = np.arange(n) / sr
    audio = np.zeros(n, dtype=np.float64)

    beat_period = 60.0 / bpm
    beat_time = 0.0
    while beat_time < duration:
        start = int(beat_time * sr)
        length = int(0.06 * sr)
        end = min(n, start + length)
        if end > start:
            local = np.arange(end - start) / sr
            envelope = np.exp(-local * 60.0)
            # Betonter Downbeat alle 4 Beats
            is_downbeat = round(beat_time / beat_period) % 4 == 0
            freq = 180.0 if is_downbeat else 900.0
            audio[start:end] += envelope * np.sin(2 * np.pi * freq * local) * (
                1.0 if is_downbeat else 0.6
            )
        beat_time += beat_period

    # durchgehender leiser Basston, damit RMS nicht nur aus Klicks besteht
    audio += 0.15 * np.sin(2 * np.pi * 55.0 * t)

    # leise Passage
    q0, q1 = quiet_section
    mask = (t >= q0) & (t < q1)
    audio[mask] *= 0.18

    peak = float(np.max(np.abs(audio))) or 1.0
    pcm = (audio / peak * 0.9 * 32767).astype("<i2")

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())
    return path


def make_test_clip(path: str, kind: str, duration: float = 6.0, fps: int = 30,
                   size: str = "640x360") -> str:
    """Erzeugt einen Testclip mit ffmpeg.

    kind:
      * "sharp_motion" – scharfes Bild mit Bewegung
      * "blurry"       – stark weichgezeichnet (schlechte Schärfe)
      * "dark"         – deutlich unterbelichtet
      * "static"       – kaum Bewegung, scharf
      * "mixed"        – erste Hälfte unscharf/dunkel, zweite Hälfte gut
    """
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    w, h = size.split("x")
    common = ["-y", "-v", "error"]

    if kind == "sharp_motion":
        args = [ffmpeg, *common, "-f", "lavfi", "-i",
                f"testsrc2=size={size}:rate={fps}:duration={duration}"]
        vf = "hue=s=1.2"
    elif kind == "blurry":
        args = [ffmpeg, *common, "-f", "lavfi", "-i",
                f"testsrc2=size={size}:rate={fps}:duration={duration}"]
        vf = "gblur=sigma=8"
    elif kind == "dark":
        args = [ffmpeg, *common, "-f", "lavfi", "-i",
                f"testsrc2=size={size}:rate={fps}:duration={duration}"]
        vf = "eq=brightness=-0.55:contrast=0.4"
    elif kind == "static":
        args = [ffmpeg, *common, "-f", "lavfi", "-i",
                f"smptebars=size={size}:rate={fps}:duration={duration}"]
        vf = "null"
    elif kind == "mixed":
        # Erste Hälfte unscharf und dunkel, zweite Hälfte scharf und hell.
        half = duration / 2.0
        args = [ffmpeg, *common, "-f", "lavfi", "-i",
                f"testsrc2=size={size}:rate={fps}:duration={duration}"]
        vf = (f"gblur=sigma=9:enable='lt(t,{half})',"
              f"eq=brightness=-0.45:enable='lt(t,{half})'")
    else:
        raise ValueError(f"Unbekannte Clip-Art: {kind}")

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    args += ["-vf", vf, "-c:v", "libx264", "-preset", "ultrafast",
             "-pix_fmt", "yuv420p", "-r", str(fps), path]
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return path


def build_all(target_dir: str) -> dict:
    """Erzeugt einen kompletten Mini-Datensatz und liefert die Pfade."""
    clips_dir = os.path.join(target_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    music = make_click_track(os.path.join(target_dir, "testsong.wav"))
    clips = []
    for index, kind in enumerate(
        ["sharp_motion", "mixed", "static", "blurry", "dark"], start=1
    ):
        name = f"clip_{index:02d}_{kind}.mp4"
        clips.append(make_test_clip(os.path.join(clips_dir, name), kind))
    return {"music": music, "clips_dir": clips_dir, "clips": clips}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_data"
    )
    info = build_all(target)
    print("Testdaten erzeugt in:", target)
    print("  Musik:", info["music"])
    for clip in info["clips"]:
        print("  Clip: ", clip)
