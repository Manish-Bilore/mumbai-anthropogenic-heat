"""Config loading. Single source of truth = config/params.yaml."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "params.yaml"


class Config(dict):
    """dict with dotted access: cfg['stock']['min_floors'] or cfg.get_path('paths.loads')."""

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG) -> "Config":
        path = Path(path)
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        cfg = cls(raw)
        cfg._path = path
        cfg._hash = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        return cfg

    @property
    def hash(self) -> str:
        return getattr(self, "_hash", "nohash")

    def get_in(self, dotted: str, default: Any = None) -> Any:
        node: Any = self
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def path(self, key: str) -> Path:
        """Resolve a path from the paths: block, relative to repo root."""
        rel = self["paths"][key]
        return (ROOT / rel).resolve()
