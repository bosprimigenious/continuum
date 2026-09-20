"""Terminal query: CONTINUUM_DB, implicit search, text format. No home scan."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).parents[1] / "examples" / "synthetic.snapshot.json"


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.pop("CONTINUUM_DB", None)
    if env and "CONTINUUM_DB" in env:
        merged["CONTINUUM_DB"] = env["CONTINUUM_DB"]
    return subprocess.run(
        [sys.executable, "-m", "continuum_history", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
        env=merged,
    )


def test_help_without_db_does_not_create_files(tmp_path: Path) -> None:
    result = run_cli("--help")
    assert result.returncode == 0, result.stderr
    assert "search" in result.stdout
    assert not any(tmp_path.iterdir())


def test_search_without_db_is_json_error_not_usage_and_creates_nothing(
    tmp_path: Path,
) -> None:
    result = run_cli("search", "数据库锁")
    assert result.returncode == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert "invalid_import" in payload["error"]
    assert not any(tmp_path.iterdir())


def test_continuum_db_env_allows_search_without_flag(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    assert run_cli("--db", str(db), "import", str(EXAMPLE)).returncode == 0
    result = run_cli("search", "数据库锁", env={"CONTINUUM_DB": str(db)})
    assert result.returncode == 0, result.stderr
    hit = json.loads(result.stdout)["items"][0]
    assert "数据库锁" in hit["preview"]
    assert hit["session_id"]


def test_db_flag_overrides_continuum_db_env(tmp_path: Path) -> None:
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    other = tmp_path / "other.json"
    other.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_id": "other-source",
                "sessions": [
                    {
                        "native_id": "s",
                        "title": "Other",
                        "events": [{"native_id": "1", "role": "user", "text": "另一来源"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert run_cli("--db", str(first), "import", str(EXAMPLE)).returncode == 0
    assert run_cli("--db", str(second), "import", str(other)).returncode == 0
    result = run_cli(
        "--db",
        str(second),
        "search",
        "另一来源",
        env={"CONTINUUM_DB": str(first)},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["items"][0]["source_id"] == "other-source"


def test_bare_query_is_implicit_search(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    assert run_cli("--db", str(db), "import", str(EXAMPLE)).returncode == 0
    result = run_cli("数据库锁", env={"CONTINUUM_DB": str(db)})
    assert result.returncode == 0, result.stderr
    assert "数据库锁" in json.loads(result.stdout)["items"][0]["preview"]
    flagged = run_cli("--db", str(db), "数据库锁")
    assert flagged.returncode == 0, flagged.stderr
    assert json.loads(flagged.stdout)["items"]


def test_text_format_prints_preview_not_json_object(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    assert run_cli("--db", str(db), "import", str(EXAMPLE)).returncode == 0
    result = run_cli("--format", "text", "--db", str(db), "search", "数据库锁")
    assert result.returncode == 0, result.stderr
    assert "数据库锁" in result.stdout
    assert result.stdout.lstrip()[:1] != "{"
    session_id = json.loads(run_cli("--db", str(db), "search", "数据库锁").stdout)["items"][0][
        "session_id"
    ]
    read = run_cli("--format", "text", "--db", str(db), "read", session_id, "--limit", "1")
    assert read.returncode == 0, read.stderr
    assert "SQLite" in read.stdout
    assert "user" in read.stdout


def test_text_format_empty_search_and_equals_flag(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    assert run_cli("--db", str(db), "import", str(EXAMPLE)).returncode == 0
    missing = run_cli("--format=text", "--db", str(db), "search", "xyzzy-not-in-fixture")
    assert missing.returncode == 0, missing.stderr
    assert missing.stdout.strip() == "no matches"
    listed = run_cli("--format", "text", "--db", str(db), "list")
    assert listed.returncode == 0, listed.stderr
    assert "Synthetic example" in listed.stdout
    sources = run_cli("--format", "text", "--db", str(db), "sources")
    assert "synthetic-demo" in sources.stdout
    imported = run_cli("--format", "text", "--db", str(db), "import", str(EXAMPLE))
    assert "changed=" in imported.stdout


def test_piped_search_stays_json_for_gui_bridge(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    assert run_cli("--db", str(db), "import", str(EXAMPLE)).returncode == 0
    result = run_cli("--db", str(db), "search", "数据库锁")
    payload = json.loads(result.stdout)
    assert payload["items"][0]["session_id"]
