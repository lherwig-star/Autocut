"""ffmpeg/ffprobe finden und ausführen – ohne Netzwerk, rein lokal."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

from .errors import FFmpegNotFoundError, RenderError, VideoReadError

_CACHE: dict[str, str] = {}

# Typische Windows-Installationsorte, falls PATH nicht gesetzt wurde.
_WINDOWS_HINTS = [
    r"C:\Program Files\ffmpeg\bin",
    r"C:\ffmpeg\bin",
    r"C:\Program Files (x86)\ffmpeg\bin",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
    os.path.expandvars(r"%USERPROFILE%\scoop\shims"),
    os.path.expandvars(r"%ProgramData%\chocolatey\bin"),
]


def _no_window_kwargs() -> dict:
    """Verhindert aufblitzende Konsolenfenster unter Windows (pythonw/.pyw)."""
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": startupinfo, "creationflags": 0x08000000}
    return {}


def _looks_executable(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _find_tool(name: str) -> Optional[str]:
    """Sucht ffmpeg bzw. ffprobe: PATH -> Windows-Standardpfade -> imageio-ffmpeg."""
    exe = name + (".exe" if os.name == "nt" else "")

    found = shutil.which(exe)
    if found:
        return found

    for folder in _WINDOWS_HINTS:
        candidate = os.path.join(folder, exe)
        if _looks_executable(candidate):
            return candidate

    # Neben der eigenen Anwendung mitgeliefertes ffmpeg (Ordner "bin").
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", exe)
    if _looks_executable(local):
        return local

    # Letzte Rettung: das Paket imageio-ffmpeg bringt ein fertiges ffmpeg mit.
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg  # type: ignore

            path = imageio_ffmpeg.get_ffmpeg_exe()
            if os.path.isfile(path):
                return path
        except Exception:
            pass
    return None


def ffmpeg_path() -> str:
    if "ffmpeg" not in _CACHE:
        path = _find_tool("ffmpeg")
        if not path:
            raise FFmpegNotFoundError()
        _CACHE["ffmpeg"] = path
    return _CACHE["ffmpeg"]


def ffprobe_path() -> Optional[str]:
    """ffprobe ist optional – ohne es weicht AutoCut auf OpenCV aus."""
    if "ffprobe" not in _CACHE:
        _CACHE["ffprobe"] = _find_tool("ffprobe") or ""
    return _CACHE["ffprobe"] or None


def have_ffmpeg() -> bool:
    try:
        ffmpeg_path()
        return True
    except FFmpegNotFoundError:
        return False


def run(args: Sequence[str], desc: str = "ffmpeg", timeout: Optional[float] = None) -> str:
    """Führt ffmpeg/ffprobe aus und liefert stdout. Wirft RenderError bei Fehlern."""
    try:
        proc = subprocess.run(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            **_no_window_kwargs(),
        )
    except FileNotFoundError as exc:  # pragma: no cover - abhängig vom System
        raise FFmpegNotFoundError() from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"{desc} hat zu lange gebraucht und wurde abgebrochen.",
            "Versuche es mit weniger oder kürzeren Clips erneut.",
        ) from exc

    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-12:]
        raise RenderError(
            f"{desc} ist fehlgeschlagen.",
            "Technische Details (letzte Zeilen von ffmpeg):\n\n" + "\n".join(tail),
        )
    return proc.stdout.decode("utf-8", "replace")


@dataclass
class MediaInfo:
    """Technische Eckdaten einer Videodatei."""

    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    creation_time: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.duration > 0.05 and self.width > 0 and self.height > 0


def probe(path: str) -> MediaInfo:
    """Liest Dauer, Auflösung, FPS – bevorzugt per ffprobe, sonst per OpenCV."""
    probe_exe = ffprobe_path()
    if probe_exe:
        try:
            raw = run(
                [
                    probe_exe, "-v", "error", "-print_format", "json",
                    "-show_format", "-show_streams", path,
                ],
                desc=f"Analyse von {os.path.basename(path)}",
                timeout=60,
            )
            data = json.loads(raw)
            return _media_info_from_ffprobe(path, data)
        except Exception:
            pass  # Fallback unten
    return _media_info_from_opencv(path)


def _parse_fraction(value: str) -> float:
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _media_info_from_ffprobe(path: str, data: dict) -> MediaInfo:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise VideoReadError(
            f"In der Datei '{os.path.basename(path)}' ist keine Videospur enthalten.",
            "Bitte entferne die Datei aus dem Clip-Ordner oder wandle sie in MP4 um.",
        )
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    fps = _parse_fraction(video.get("avg_frame_rate") or "0") or _parse_fraction(
        video.get("r_frame_rate") or "0"
    )
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    # Hochkant gedrehte Handyvideos: Rotation berücksichtigen.
    rotation = _rotation_of(video)
    if rotation in (90, 270):
        width, height = height, width
    tags = {**fmt.get("tags", {}), **video.get("tags", {})}
    return MediaInfo(
        path=path,
        duration=duration,
        width=width,
        height=height,
        fps=fps if fps > 0 else 30.0,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        creation_time=tags.get("creation_time"),
    )


def _rotation_of(video_stream: dict) -> int:
    tags = video_stream.get("tags", {})
    try:
        rot = int(float(tags.get("rotate", 0)))
    except (TypeError, ValueError):
        rot = 0
    for side in video_stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                rot = int(float(side["rotation"]))
            except (TypeError, ValueError):
                pass
    return abs(rot) % 360


def _media_info_from_opencv(path: str) -> MediaInfo:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        from .errors import MissingDependencyError

        raise MissingDependencyError("opencv-python", "die Video-Analyse") from exc

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoReadError(
            f"Die Datei '{os.path.basename(path)}' konnte nicht geöffnet werden.",
            "Möglicherweise ist das Format nicht unterstützt oder die Datei beschädigt.",
        )
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    duration = frames / fps if fps > 0 else 0.0
    return MediaInfo(path, duration, width, height, fps or 30.0, has_audio=False)


def version_string() -> str:
    try:
        out = run([ffmpeg_path(), "-version"], desc="ffmpeg-Version", timeout=20)
        return out.splitlines()[0] if out else "ffmpeg"
    except Exception:
        return "unbekannt"


if __name__ == "__main__":  # kleine Selbstprüfung
    print("ffmpeg:", _find_tool("ffmpeg"))
    print("ffprobe:", _find_tool("ffprobe"))
    print(version_string(), file=sys.stderr)


def run_cancellable(args: Sequence[str], desc: str = "ffmpeg",
                    should_cancel=None, poll: float = 0.2) -> None:
    """Wie ``run``, lässt sich aber jederzeit sauber abbrechen (für die GUI)."""
    import time

    from .errors import CancelledError

    try:
        proc = subprocess.Popen(
            list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **_no_window_kwargs()
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise FFmpegNotFoundError() from exc

    while proc.poll() is None:
        if should_cancel and should_cancel():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                proc.kill()
            raise CancelledError()
        time.sleep(poll)

    if proc.returncode != 0:
        stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        tail = stderr.strip().splitlines()[-12:]
        raise RenderError(
            f"{desc} ist fehlgeschlagen.",
            "Technische Details (letzte Zeilen von ffmpeg):\n\n" + "\n".join(tail),
        )
