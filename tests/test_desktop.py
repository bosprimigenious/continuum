"""Desktop shell must spawn the continuum CLI sidecar, not a Continuum HTTP API."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAURI_CONF = ROOT / "gui" / "src-tauri" / "tauri.conf.json"


def test_tauri_bundles_continuum_cli_sidecar_not_http() -> None:
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    assert conf["identifier"] == "com.github.bosprimigenious.continuum"
    assert conf["bundle"]["externalBin"] == ["binaries/continuum"]
    dumped = json.dumps(conf)
    assert "/__continuum" not in dumped
    rust = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "gui" / "src-tauri" / "src").glob("*.rs"))
    )
    assert rust
    assert "axum" not in rust
    assert "warp::" not in rust
    assert "hyper::" not in rust
    assert "tauri_plugin_shell" in rust


def test_desktop_gitignore_keeps_build_artifacts_out_of_git() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "gui/src-tauri/target/" in text
    assert "gui/src-tauri/binaries/" in text
