"""Versioned normalized snapshot contract, not a native vendor format."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[^\x00]+$")]
Timestamp = Annotated[str, Field(max_length=64, pattern=r"^[^\x00]*$")]
AdapterName = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageIssue(Record):
    code: Literal[
        "malformed_record",
        "missing_bubble",
        "duplicate_event",
        "unsupported_block",
        "unsupported_bubble_type",
        "invalid_composer",
        "unknown_shape",
        "unusable_timestamp",
        "illegal_identity",
        "unrecognized_version",
    ]
    native_session_id: Identifier | None = None
    native_event_id: Identifier | None = None


class SnapshotCoverage(Record):
    adapter: Literal["cursor-state-vscdb-v1"]
    format: Literal["cursor.global_state.vscdb.cursorDiskKV"]
    observed_composer_data_version: int | None = None
    observed_bubble_version: int | None = None
    sessions_seen: int
    sessions_imported: int
    events_seen: int
    events_imported: int
    issues: tuple[CoverageIssue, ...]
    complete: bool


class Event(Record):
    native_id: Identifier
    role: Literal["user", "assistant", "tool", "context"]
    text: Annotated[str, Field(max_length=1_000_000, pattern=r"^[^\x00]*$")]
    created_at: Timestamp | None = None


class Session(Record):
    native_id: Identifier
    title: Annotated[str, Field(max_length=1024)]
    project: Annotated[str, Field(max_length=1024)] | None = None
    events: tuple[Event, ...]
    created_at: Timestamp | None = None
    updated_at: Timestamp | None = None

    @model_validator(mode="after")
    def unique_events(self) -> Self:
        if len({event.native_id for event in self.events}) != len(self.events):
            raise ValueError("duplicate event identities")
        return self


class Snapshot(Record):
    schema_version: Literal[1]
    source_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")]
    adapter: AdapterName = "continuum-snapshot-v1"
    sessions: tuple[Session, ...]
    coverage: SnapshotCoverage | None = None

    @model_validator(mode="after")
    def unique_sessions(self) -> Self:
        if len({session.native_id for session in self.sessions}) != len(self.sessions):
            raise ValueError("duplicate session identities")
        return self
