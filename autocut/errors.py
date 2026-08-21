"""Fehlerklassen mit verständlichen Meldungen für Nicht-Techniker.

Jeder Fehler hat einen kurzen Titel, eine Klartext-Erklärung und optional
einen konkreten Lösungsvorschlag. Die GUI zeigt das als Dialogfenster,
die CLI als sauber formatierten Text – niemals als roher Traceback.
"""

from __future__ import annotations


class AutoCutError(Exception):
    """Basisklasse für alle erwarteten Fehler."""

    title = "AutoCut-Fehler"

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def full_text(self) -> str:
        if self.hint:
            return f"{self.message}\n\n{self.hint}"
        return self.message


class FFmpegNotFoundError(AutoCutError):
    title = "ffmpeg nicht gefunden"

    def __init__(self) -> None:
        super().__init__(
            "AutoCut braucht ffmpeg zum Schneiden und Rendern von Videos, "
            "konnte es auf diesem Computer aber nicht finden.",
            "So installierst du es (eine der Varianten genügt):\n\n"
            "1) Windows-Terminal öffnen und eingeben:\n"
            "     winget install ffmpeg\n"
            "   danach AutoCut neu starten.\n\n"
            "2) Oder in AutoCut selbst installieren lassen:\n"
            "     pip install imageio-ffmpeg\n"
            "   (bringt ffmpeg als fertige Datei mit)\n\n"
            "3) Oder ffmpeg von https://www.gyan.dev/ffmpeg/builds/ laden, "
            "entpacken und den Ordner 'bin' zur PATH-Variable hinzufügen.",
        )


class NoClipsFoundError(AutoCutError):
    title = "Keine Videoclips gefunden"


class MusicFileError(AutoCutError):
    title = "Musikdatei nicht lesbar"


class TemplateError(AutoCutError):
    title = "Vorlage fehlerhaft"


class VideoReadError(AutoCutError):
    title = "Video nicht lesbar"


class RenderError(AutoCutError):
    title = "Rendern fehlgeschlagen"


class CancelledError(AutoCutError):
    title = "Abgebrochen"

    def __init__(self, message: str = "Die Verarbeitung wurde abgebrochen.") -> None:
        super().__init__(message)


class MissingDependencyError(AutoCutError):
    title = "Programmbaustein fehlt"

    def __init__(self, package: str, purpose: str) -> None:
        super().__init__(
            f"Das Python-Paket '{package}' wird für {purpose} benötigt, "
            "ist aber nicht installiert.",
            f"Installiere es mit:\n\n    pip install {package}\n\n"
            "Oder starte AutoCut über die Datei 'AutoCut.pyw' – "
            "die installiert fehlende Pakete automatisch.",
        )
