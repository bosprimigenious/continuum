"""OS config locations for the desktop shell. Never hardcode /Users/..."""

from __future__ import annotations

from pathlib import Path


def config_dir(
    *,
    home: Path,
    system: str,
    appdata: Path | None = None,
) -> Path:
    if system == "darwin":
        return home / "Library" / "Application Support" / "Continuum"
    if system.startswith("win"):
        base = appdata if appdata is not None else home / "AppData" / "Roaming"
        return base / "Continuum"
    return home / ".config" / "continuum"
