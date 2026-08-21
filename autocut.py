#!/usr/bin/env python3
"""AutoCut – automatischer Videoschnitt auf Musik (Kommandozeile).

Beispiel:
    python autocut.py --clips ./meine_clips --music song.mp3 \
        --template cinematic_vlog --output fertig.mp4

Die grafische Oberfläche startest du mit einem Doppelklick auf AutoCut.pyw
oder mit:  python autocut.py --gui
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Damit der Aufruf aus jedem Verzeichnis funktioniert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autocut import __version__
from autocut.errors import AutoCutError, CancelledError
from autocut.templates import list_templates, load_all


class ProgressBar:
    """Einfacher Fortschrittsbalken für das Terminal."""

    def __init__(self, width: int = 34, enabled: bool = True) -> None:
        self.width = width
        self.enabled = enabled and sys.stdout.isatty()
        self.last_message = ""
        self.last_draw = 0.0
        self.start = time.time()

    def update(self, fraction: float, message: str) -> None:
        if not self.enabled:
            # Ohne Terminal (z.B. Ausgabe in Datei) nur bei Textwechsel schreiben.
            if message != self.last_message:
                print(f"[{fraction * 100:5.1f}%] {message}", flush=True)
                self.last_message = message
            return
        now = time.time()
        if now - self.last_draw < 0.08 and fraction < 1.0:
            return
        self.last_draw = now
        filled = int(self.width * max(0.0, min(1.0, fraction)))
        bar = "█" * filled + "·" * (self.width - filled)
        elapsed = now - self.start
        text = f"\r  [{bar}] {fraction * 100:5.1f}%  {message[:48]:<48} {elapsed:5.1f}s"
        sys.stdout.write(text)
        sys.stdout.flush()

    def done(self) -> None:
        if self.enabled:
            sys.stdout.write("\n")
            sys.stdout.flush()


def print_templates(folder=None) -> None:
    templates = load_all(folder)
    if not templates:
        print("Keine Vorlagen gefunden. Erwartet werden YAML-Dateien im Ordner 'templates/'.")
        return
    print("Verfügbare Vorlagen:\n")
    for template in templates:
        print(f"  {template.name}")
        if template.description:
            print(f"      {template.description}")
        print(f"      {template.summary()}")
        print()
    print("Eigene Vorlage: einfach eine der YAML-Dateien in templates/ kopieren,")
    print("umbenennen und die Werte anpassen – sie erscheint dann automatisch hier.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocut",
        description="AutoCut – schneidet Videoclips automatisch auf die Beats eines Songs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python autocut.py --clips ./clips --music song.mp3 "
            "--template energetic --output fertig.mp4\n"
            "  python autocut.py --list-templates\n"
            "  python autocut.py --gui\n"
        ),
    )
    parser.add_argument("--clips", "-c", help="Ordner mit den Videoclips")
    parser.add_argument("--music", "-m", help="Musikdatei (MP3, WAV, M4A, FLAC, OGG)")
    parser.add_argument("--template", "-t", default="cinematic_vlog",
                        help="Name der Vorlage aus templates/ (Standard: cinematic_vlog)")
    parser.add_argument("--output", "-o", default="autocut_video.mp4",
                        help="Zieldatei (Standard: autocut_video.mp4)")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Auch Unterordner nach Clips durchsuchen")
    parser.add_argument("--order", choices=["auto", "name", "date"], default="auto",
                        help="Sortierung der Clips (Standard: auto = Aufnahmedatum, sonst Name)")
    parser.add_argument("--max-music-seconds", type=float, default=None,
                        help="Nur die ersten N Sekunden des Songs verwenden")
    parser.add_argument("--templates-dir", default=None,
                        help="Anderer Ordner mit Vorlagen")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur analysieren und Report zeigen, nichts rendern")
    parser.add_argument("--no-report-file", action="store_true",
                        help="Report nicht als Datei neben das Video speichern")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Report am Ende nicht auf dem Bildschirm ausgeben")
    parser.add_argument("--list-templates", "-l", action="store_true",
                        help="Alle verfügbaren Vorlagen anzeigen")
    parser.add_argument("--gui", action="store_true",
                        help="Die grafische Oberfläche starten")
    parser.add_argument("--selftest", action="store_true",
                        help="Prüfen, ob AutoCut auf diesem Rechner vollständig läuft")
    parser.add_argument("--version", "-V", action="version",
                        version=f"AutoCut {__version__}")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        from autocut.selftest import run_selftest

        return 0 if run_selftest() else 1

    if args.gui:
        from gui.app import launch

        return launch()

    if args.list_templates:
        print_templates(args.templates_dir)
        return 0

    missing = [name for name, value in (("--clips", args.clips), ("--music", args.music))
               if not value]
    if missing:
        parser.print_help()
        print("\nFehlende Angabe(n): " + ", ".join(missing))
        print("Verfügbare Vorlagen: " + ", ".join(list_templates(args.templates_dir)))
        return 2

    from autocut.pipeline import preview_plan, run_autocut

    print(f"AutoCut {__version__}")
    print(f"  Clips    : {args.clips}")
    print(f"  Musik    : {args.music}")
    print(f"  Vorlage  : {args.template}")
    if not args.dry_run:
        print(f"  Ausgabe  : {args.output}")
    print()

    bar = ProgressBar()
    try:
        if args.dry_run:
            report = preview_plan(
                args.clips, args.music, args.template, progress=bar.update,
                recursive=args.recursive, order=args.order,
                templates_folder=args.templates_dir,
            )
            bar.done()
            print("\n" + report)
            print("\nTestlauf – es wurde nichts gerendert. "
                  "Lass '--dry-run' weg, um das Video zu erzeugen.")
            return 0

        result = run_autocut(
            clips_folder=args.clips,
            music_path=args.music,
            template_name=args.template,
            output_path=args.output,
            progress=bar.update,
            recursive=args.recursive,
            order=args.order,
            templates_folder=args.templates_dir,
            write_report=not args.no_report_file,
            max_music_seconds=args.max_music_seconds,
        )
        bar.done()

        if not args.quiet:
            print("\n" + result.report_text)

        print(f"\nFertig in {result.elapsed:.1f}s")
        print(f"  Video  : {result.output_path}")
        if result.report_path:
            print(f"  Report : {result.report_path}")
        for warning in result.warnings:
            print(f"  Hinweis: {warning}")
        return 0

    except CancelledError:
        bar.done()
        print("\nAbgebrochen.")
        return 130
    except AutoCutError as error:
        bar.done()
        print(f"\n{'=' * 70}")
        print(f"FEHLER: {error.title}")
        print("=" * 70)
        print(error.full_text())
        return 1
    except KeyboardInterrupt:
        bar.done()
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
