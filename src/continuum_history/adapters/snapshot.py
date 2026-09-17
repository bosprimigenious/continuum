import os
from pathlib import Path

from pydantic import ValidationError

from continuum_history.errors import HistoryError
from continuum_history.models import Snapshot

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024


def load_snapshot(path: Path) -> Snapshot:
    """Read one explicitly selected, bounded snapshot without modifying its source."""
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, f) != getattr(stat, f) for stat in (after, current) for f in fields):
        raise HistoryError("source_changed: retry with a stable snapshot")
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise HistoryError("snapshot_too_large: maximum is 16 MiB")
    try:
        return Snapshot.model_validate_json(raw)
    except ValidationError as exc:
        # Pydantic's default error text includes user input. Do not leak it into logs.
        raise HistoryError("invalid_snapshot: use schema v1 with unique session/event IDs") from exc
