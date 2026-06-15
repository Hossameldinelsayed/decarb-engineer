"""JSON persistence for scenarios, results and the expert decision log."""

from __future__ import annotations

import json
from pathlib import Path

from .models.roadmap import Roadmap
from .models.site import SiteProfile


def load_site(path: str | Path) -> SiteProfile:
    return SiteProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_site(site: SiteProfile, path: str | Path) -> None:
    Path(path).write_text(site.model_dump_json(indent=2), encoding="utf-8")


def save_roadmap(roadmap: Roadmap, path: str | Path) -> None:
    Path(path).write_text(roadmap.model_dump_json(indent=2), encoding="utf-8")


def load_roadmap(path: str | Path) -> Roadmap:
    return Roadmap.model_validate_json(Path(path).read_text(encoding="utf-8"))


def append_decision_log(entry: dict, path: str | Path = "decision_log.json") -> None:
    """Append an expert decision to a JSON-lines-ish log (a JSON array)."""
    p = Path(path)
    log: list[dict] = []
    if p.exists():
        try:
            log = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log = []
    log.append(entry)
    p.write_text(json.dumps(log, indent=2), encoding="utf-8")
