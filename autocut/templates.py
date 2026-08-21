"""Vorlagen (Templates) laden, prüfen und mit Standardwerten auffüllen.

Eine Vorlage ist eine einzelne YAML-Datei im Ordner ``templates/``.
Neue Dateien tauchen automatisch in CLI und GUI auf – ohne Codeänderung.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .errors import TemplateError

TEMPLATES_DIRNAME = "templates"

VALID_TRANSITIONS = ("hard_cut", "crossfade")

# Alle Vorlagen-Optionen mit Standardwert und erlaubtem Bereich.
DEFAULTS: Dict[str, Any] = {
    "name": "",
    "description": "",
    # --- Schnittfrequenz -------------------------------------------------
    "beats_per_cut": 4,          # Schnitt alle N Beats (1 = jeder Beat)
    "min_clip_length": 0.8,      # Sekunden
    "max_clip_length": 6.0,      # Sekunden
    "adaptive_to_energy": False,  # leise Passagen -> längere Clips
    "beats_per_cut_quiet": 8,    # nur bei adaptive_to_energy
    "beats_per_cut_loud": 2,     # nur bei adaptive_to_energy
    # --- Gewichtung der Analyse-Kriterien (Summe wird normiert) ----------
    "weights": {
        "sharpness": 1.0,    # Schärfe (Laplacian-Varianz)
        "motion": 1.0,       # Bewegungsintensität
        "exposure": 1.0,     # Helligkeit / Belichtung
        "stability": 1.0,    # Ruhe im Bild (Gegenteil von Verwacklung)
    },
    "prefer_motion": 0.5,     # 0 = ruhige Shots, 1 = viel Action bevorzugt
    "scene_cut_penalty": 0.5,  # Abzug, wenn im Segment ein harter Szenenwechsel liegt
    # --- Übergänge -------------------------------------------------------
    "transition": "hard_cut",
    "transition_duration": 0.5,   # Sekunden (nur bei crossfade)
    # --- Farb-Look -------------------------------------------------------
    "color": {
        "enabled": False,
        "brightness": 0.0,   # -1.0 .. 1.0
        "contrast": 1.0,     # 0.0 .. 3.0
        "saturation": 1.0,   # 0.0 .. 3.0
        "gamma": 1.0,        # 0.1 .. 3.0
        "temperature": 0.0,  # -1 (kühl/blau) .. 1 (warm/orange)
        "vignette": False,
        "lut": "",           # optionaler Pfad zu einer .cube-Datei
    },
    # --- Ausgabe ---------------------------------------------------------
    "output": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "video_bitrate": "12M",
        "audio_bitrate": "192k",
        "audio_fade_out": 2.0,   # Sekunden Ausblenden am Ende
        "preset": "medium",
    },
    # --- Sonstiges -------------------------------------------------------
    "min_gap_between_moments": 0.4,  # Mindestabstand gewählter Momente im selben Clip
    "skip_start": 0.0,               # Sekunden am Clipanfang ignorieren
    "skip_end": 0.0,                 # Sekunden am Clipende ignorieren
}


@dataclass
class Template:
    """Eine geladene, geprüfte Vorlage."""

    name: str
    description: str
    path: str
    data: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def weights(self) -> Dict[str, float]:
        return self.data["weights"]

    @property
    def color(self) -> Dict[str, Any]:
        return self.data["color"]

    @property
    def output(self) -> Dict[str, Any]:
        return self.data["output"]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.data)

    def summary(self) -> str:
        d = self.data
        if d["adaptive_to_energy"]:
            freq = (f"{d['beats_per_cut_quiet']} Beats (leise) bis "
                    f"{d['beats_per_cut_loud']} Beats (laut)")
        else:
            freq = f"jeder {d['beats_per_cut']}. Beat" if d["beats_per_cut"] > 1 else "jeder Beat"
        trans = "Crossfade" if d["transition"] == "crossfade" else "Hard Cut"
        return (f"Schnitt: {freq} | Länge {d['min_clip_length']:.1f}-"
                f"{d['max_clip_length']:.1f}s | Übergang: {trans}"
                f"{' | Farb-Look' if d['color']['enabled'] else ''}")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def templates_dir(base_dir: Optional[str] = None) -> str:
    if base_dir:
        return base_dir
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, TEMPLATES_DIRNAME)


def list_templates(base_dir: Optional[str] = None) -> List[str]:
    """Alle verfügbaren Vorlagennamen (Dateiname ohne Endung), alphabetisch."""
    folder = templates_dir(base_dir)
    if not os.path.isdir(folder):
        return []
    names = [
        os.path.splitext(f)[0]
        for f in os.listdir(folder)
        if f.lower().endswith((".yaml", ".yml")) and not f.startswith("_")
    ]
    return sorted(names)


def load_all(base_dir: Optional[str] = None) -> List[Template]:
    """Lädt alle Vorlagen; fehlerhafte werden übersprungen statt zu blockieren."""
    result = []
    for name in list_templates(base_dir):
        try:
            result.append(load_template(name, base_dir))
        except TemplateError:
            continue
    return result


def load_template(name_or_path: str, base_dir: Optional[str] = None) -> Template:
    """Lädt eine Vorlage über ihren Namen oder einen direkten Dateipfad."""
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        from .errors import MissingDependencyError

        raise MissingDependencyError("pyyaml", "das Laden der Vorlagen") from exc

    path = _resolve_path(name_or_path, base_dir)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise TemplateError(f"Die Vorlage '{path}' konnte nicht gelesen werden.") from exc
    except Exception as exc:  # yaml.YAMLError
        raise TemplateError(
            f"Die Vorlage '{os.path.basename(path)}' enthält einen Formatfehler.",
            f"Details: {exc}\n\nBitte prüfe die Einrückungen in der YAML-Datei.",
        ) from exc

    if not isinstance(raw, dict):
        raise TemplateError(
            f"Die Vorlage '{os.path.basename(path)}' hat kein gültiges Format.",
            "Erwartet werden Zeilen der Form 'einstellung: wert'.",
        )

    data = _deep_merge(DEFAULTS, raw)
    data["name"] = raw.get("name") or os.path.splitext(os.path.basename(path))[0]
    _validate(data, os.path.basename(path))
    return Template(
        name=data["name"],
        description=str(data.get("description", "")),
        path=path,
        data=data,
    )


def _resolve_path(name_or_path: str, base_dir: Optional[str]) -> str:
    if os.path.isfile(name_or_path):
        return name_or_path
    folder = templates_dir(base_dir)
    for ext in (".yaml", ".yml"):
        candidate = os.path.join(folder, name_or_path + ext)
        if os.path.isfile(candidate):
            return candidate
    available = ", ".join(list_templates(base_dir)) or "(keine gefunden)"
    raise TemplateError(
        f"Die Vorlage '{name_or_path}' gibt es nicht.",
        f"Verfügbare Vorlagen im Ordner '{folder}':\n  {available}",
    )


def _need_number(data: Dict[str, Any], key: str, low: float, high: float, where: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TemplateError(
            f"In der Vorlage '{where}' ist '{key}' keine Zahl.",
            f"Erlaubt ist eine Zahl zwischen {low} und {high}.",
        )
    if not (low <= float(value) <= high):
        raise TemplateError(
            f"In der Vorlage '{where}' liegt '{key}' ({value}) außerhalb des erlaubten Bereichs.",
            f"Erlaubt ist {low} bis {high}.",
        )
    return float(value)


def _validate(data: Dict[str, Any], where: str) -> None:
    data["beats_per_cut"] = int(_need_number(data, "beats_per_cut", 1, 64, where))
    data["beats_per_cut_quiet"] = int(_need_number(data, "beats_per_cut_quiet", 1, 64, where))
    data["beats_per_cut_loud"] = int(_need_number(data, "beats_per_cut_loud", 1, 64, where))
    data["min_clip_length"] = _need_number(data, "min_clip_length", 0.1, 60, where)
    data["max_clip_length"] = _need_number(data, "max_clip_length", 0.2, 120, where)
    if data["min_clip_length"] >= data["max_clip_length"]:
        raise TemplateError(
            f"In der Vorlage '{where}' ist 'min_clip_length' nicht kleiner als 'max_clip_length'.",
            "Bitte passe die beiden Werte an, z.B. min 1.0 und max 4.0.",
        )
    data["prefer_motion"] = _need_number(data, "prefer_motion", 0.0, 1.0, where)
    data["scene_cut_penalty"] = _need_number(data, "scene_cut_penalty", 0.0, 5.0, where)
    data["min_gap_between_moments"] = _need_number(data, "min_gap_between_moments", 0.0, 30, where)
    data["skip_start"] = _need_number(data, "skip_start", 0.0, 60, where)
    data["skip_end"] = _need_number(data, "skip_end", 0.0, 60, where)
    data["adaptive_to_energy"] = bool(data.get("adaptive_to_energy"))

    if data["transition"] not in VALID_TRANSITIONS:
        raise TemplateError(
            f"In der Vorlage '{where}' ist '{data['transition']}' kein gültiger Übergang.",
            "Erlaubt sind: " + ", ".join(VALID_TRANSITIONS),
        )
    data["transition_duration"] = _need_number(data, "transition_duration", 0.05, 5.0, where)
    # Ein Übergang darf nie länger sein als der kürzeste Clip.
    data["transition_duration"] = min(
        data["transition_duration"], max(0.05, data["min_clip_length"] * 0.6)
    )

    weights = data.get("weights")
    if not isinstance(weights, dict):
        raise TemplateError(f"In der Vorlage '{where}' ist 'weights' kein Block mit Werten.")
    clean: Dict[str, float] = {}
    for key in ("sharpness", "motion", "exposure", "stability"):
        value = weights.get(key, DEFAULTS["weights"][key])
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise TemplateError(
                f"In der Vorlage '{where}' ist weights.{key} keine Zahl >= 0.")
        clean[key] = float(value)
    if sum(clean.values()) <= 0:
        raise TemplateError(
            f"In der Vorlage '{where}' sind alle Gewichte 0.",
            "Mindestens ein Kriterium muss ein Gewicht größer 0 haben.",
        )
    data["weights"] = clean

    color = data.get("color", {})
    if not isinstance(color, dict):
        raise TemplateError(f"In der Vorlage '{where}' ist 'color' kein Block mit Werten.")
    color["enabled"] = bool(color.get("enabled"))
    for key, low, high in (
        ("brightness", -1.0, 1.0), ("contrast", 0.0, 3.0), ("saturation", 0.0, 3.0),
        ("gamma", 0.1, 3.0), ("temperature", -1.0, 1.0),
    ):
        color[key] = _need_number(color, key, low, high, where)
    color["vignette"] = bool(color.get("vignette"))
    color["lut"] = str(color.get("lut") or "")
    data["color"] = color

    out = data.get("output", {})
    if not isinstance(out, dict):
        raise TemplateError(f"In der Vorlage '{where}' ist 'output' kein Block mit Werten.")
    out["width"] = int(_need_number(out, "width", 128, 7680, where))
    out["height"] = int(_need_number(out, "height", 128, 4320, where))
    out["fps"] = _need_number(out, "fps", 10, 120, where)
    out["audio_fade_out"] = _need_number(out, "audio_fade_out", 0.0, 30.0, where)
    # ffmpeg braucht gerade Kantenlängen für yuv420p.
    out["width"] -= out["width"] % 2
    out["height"] -= out["height"] % 2
    data["output"] = out


def describe_defaults() -> str:
    """Für die Dokumentation: alle Optionen mit Standardwerten."""
    import json

    return json.dumps(DEFAULTS, indent=2, ensure_ascii=False)
