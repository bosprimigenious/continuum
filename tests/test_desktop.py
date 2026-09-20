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


def test_workbench_shell_has_four_panes_and_is_not_an_ide() -> None:
    app = (ROOT / "gui" / "src" / "App.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "gui" / "src" / "styles.css").read_text(encoding="utf-8")
    for pane in ("navigator", "transcript", "coverage", "settings"):
        assert f'data-pane="{pane}"' in app
    assert 'data-workbench="continuum"' in app
    assert "vscode" not in app.lower()
    assert "electron" not in app.lower()
    assert "monaco" not in app.lower()
    assert "/Users/" not in app
    assert "/Users/" not in styles
    assert ".workbench" in styles
    plugin = (ROOT / "gui" / "vite-plugin-continuum-cli.ts").read_text(encoding="utf-8")
    assert "HTTPS_PROXY" in plugin
    assert "shell: false" in plugin
    assert "shell: true" not in plugin


def test_desktop_gitignore_keeps_build_artifacts_out_of_git() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "gui/src-tauri/target/" in text
    assert "gui/src-tauri/binaries/" in text


def test_windows_nsis_bundle_smokes_sidecar_json_and_current_user_install() -> None:
    workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
    assert "windows-latest" in workflow
    assert "bundle: nsis" in workflow
    assert "scripts/smoke_sidecar.py" in workflow
    assert "scripts/smoke_desktop.py" in workflow
    assert "if: always()" in workflow
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    windows = conf["bundle"]["windows"]
    assert windows["nsis"]["installMode"] == "currentUser"
    assert windows["webviewInstallMode"]["type"] == "embedBootstrapper"
    bridge = (ROOT / "gui" / "src" / "bridge.ts").read_text(encoding="utf-8")
    assert '"--format", "json"' in bridge
    plugin = (ROOT / "gui" / "vite-plugin-continuum-cli.ts").read_text(encoding="utf-8")
    assert "--format" in plugin
    assert "json" in plugin
    python_bridge = (ROOT / "src" / "continuum_history" / "gui" / "bridge.py").read_text(
        encoding="utf-8"
    )
    assert '"--format", "json"' in python_bridge
    smoke = (ROOT / "scripts" / "smoke_desktop.py").read_text(encoding="utf-8")
    assert "数据库锁" in smoke
    assert "LOCALAPPDATA" in smoke
    assert "Programs" in smoke
    assert "continuum-gui.exe" in smoke
    assert 'names = ("Continuum.exe"' not in smoke
    assert "taskkill" in smoke
    assert "gui exited" in smoke or "start " in smoke
    sidecar_smoke = (ROOT / "scripts" / "smoke_sidecar.py").read_text(encoding="utf-8")
    assert '"--help"' in sidecar_smoke
    cli = (ROOT / "src" / "continuum_history" / "cli.py").read_text(encoding="utf-8")
    assert 'reconfigure(encoding="utf-8"' in cli
