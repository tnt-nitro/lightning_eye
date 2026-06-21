"""Configuration loader for Lightning Eye."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def _expand_path(value: str) -> str:
    return os.path.expanduser(value)


def default_install_dir() -> Path:
    return Path(_expand_path("~/lightning_eye"))


def config_path(install_dir: Path | None = None) -> Path:
    base = install_dir or default_install_dir()
    return base / "config.yaml"


def load_config(install_dir: Path | None = None) -> dict[str, Any]:
    path = config_path(install_dir)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        data = _parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError("Invalid config format")
    if "install_dir" in data:
        data["install_dir"] = _expand_path(str(data["install_dir"]))
    return data


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML parser fallback when PyYAML is unavailable."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, value = line.strip().partition(":")
        key = key.strip()
        value = value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if not value:
            node: dict[str, Any] = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            if value.lower() in ("true", "false"):
                parent[key] = value.lower() == "true"
            else:
                try:
                    if "." in value:
                        parent[key] = float(value)
                    else:
                        parent[key] = int(value)
                except ValueError:
                    parent[key] = value.strip('"').strip("'")

    return root


def get_gpio(config: dict[str, Any]) -> dict[str, int]:
    return {k: int(v) for k, v in config.get("gpio", {}).items()}


def get_data_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("install_dir", str(default_install_dir()))) / "data"


def get_logs_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("install_dir", str(default_install_dir()))) / "logs"
