"""Workbench shell: four panes, platform config dir, proxy env, no home scan."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from continuum_history.gui.paths import config_dir
from continuum_history.gui.session import WORKBENCH_PANES, GuiSession

EXAMPLE = Path(__file__).parents[1] / "examples" / "synthetic.snapshot.json"


def test_empty_view_exposes_four_panes_without_writing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cli")),
    )
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    session = GuiSession(tmp_path / "index.db")
    view = session.view()
    assert view["panes"] == list(WORKBENCH_PANES)
    assert view["panes"] == ["navigator", "transcript", "coverage", "settings"]
    assert view["settings"]["proxy"] is None
    assert view["settings"]["index"] == str(tmp_path / "index.db")
    assert view["state"] == "empty"
    assert not home.exists()
    assert not (tmp_path / "index.db").exists()


def test_config_dir_uses_os_conventions_not_hardcoded_users() -> None:
    mac = config_dir(home=Path("/tmp/fake-home"), system="darwin")
    win = config_dir(
        home=Path("C:/fake-home"),
        system="win32",
        appdata=Path("C:/AppData/Roaming"),
    )
    linux = config_dir(home=Path("/tmp/fake-home"), system="linux")
    assert mac == Path("/tmp/fake-home") / "Library" / "Application Support" / "Continuum"
    assert win == Path("C:/AppData/Roaming") / "Continuum"
    assert linux == Path("/tmp/fake-home") / ".config" / "continuum"
    joined = "\n".join(str(path) for path in (mac, win, linux))
    assert "fake-home/Library" in str(mac)
    assert "Roaming" in str(win)
    assert ".config" in str(linux)
    assert "Application Support" in joined


def test_save_settings_writes_json_only_when_asked(tmp_path: Path) -> None:
    session = GuiSession(tmp_path / "index.db")
    session.set_proxy("http://127.0.0.1:7890")
    target = tmp_path / "app-support"
    assert not target.exists()
    path = session.save_settings(target)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["proxy"] == "http://127.0.0.1:7890"
    assert payload["index"] == str(tmp_path / "index.db")
    other = GuiSession(tmp_path / "other.db")
    loaded = other.load_settings(target)
    assert loaded["proxy"] == "http://127.0.0.1:7890"
    assert other.view()["settings"]["proxy"] == "http://127.0.0.1:7890"


def test_proxy_is_passed_as_env_on_argv_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[tuple[list[str], dict[str, str] | None]] = []
    real_run = subprocess.run

    def wrapped(
        command: object, *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env")
        env_map = {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else None
        if isinstance(command, (list, tuple)):
            recorded.append(([str(part) for part in command], env_map))
        return real_run(command, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", wrapped)
    session = GuiSession(tmp_path / "index.db")
    session.set_proxy("http://127.0.0.1:7890")
    session.select_source(EXAMPLE)
    session.import_selected()
    assert recorded
    for command, env in recorded:
        assert isinstance(command, list)
        assert env is not None
        assert env["HTTPS_PROXY"] == "http://127.0.0.1:7890"
        assert env["https_proxy"] == "http://127.0.0.1:7890"
        assert not any("7890" in part for part in command)


def test_clear_proxy_stops_overriding_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://inherited:1")
    captured: list[str | None] = []
    real_run = subprocess.run

    def wrapped(
        command: object, *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env")
        if isinstance(env, dict):
            captured.append(str(env.get("HTTPS_PROXY")))
        else:
            captured.append(os.environ.get("HTTPS_PROXY"))
        return real_run(command, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", wrapped)
    session = GuiSession(tmp_path / "index.db")
    session.set_proxy("http://127.0.0.1:7890")
    session.set_proxy(None)
    session.select_source(EXAMPLE)
    session.import_selected()
    assert captured
    assert all(value == "http://inherited:1" for value in captured)
