"""Versioned normalized snapshot contract, not a native vendor format."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[^\x00]+$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Event(Record):
    native_id: Identifier
    role: Literal["user", "assistant", "tool", "context"]
    text: Annotated[str, Field(max_length=1_000_000, pattern=r"^[^\x00]*$")]


class Session(Record):
    native_id: Identifier
    title: Annotated[str, Field(max_length=1024)]
    project: Annotated[str, Field(max_length=1024)] | None = None
    events: tuple[Event, ...]

    @model_validator(mode="after")
    def unique_events(self) -> Self:
        if len({event.native_id for event in self.events}) != len(self.events):
            raise ValueError("duplicate event identities")
        return self


class Snapshot(Record):
    schema_version: Literal[1]
    source_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")]
    sessions: tuple[Session, ...]

    @model_validator(mode="after")
    def unique_sessions(self) -> Self:
        if len({session.native_id for session in self.sessions}) != len(self.sessions):
            raise ValueError("duplicate session identities")
        return self
