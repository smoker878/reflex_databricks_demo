import datetime as dt

import reflex as rx
import sqlmodel


def conversation_key(user_a: int, user_b: int) -> str:
    """Return the deterministic SharedState token for a 1:1 conversation.

    Uses hyphens (never underscores) because SharedState tokens may not contain
    underscore characters.
    """
    low, high = sorted((int(user_a), int(user_b)))
    return f"dm-{low}-{high}"


class Patient(rx.Model, table=True):
    """A patient record stored in the local SQLite database.

    Mirrors the ``default.patients`` table used by ``databricks_client``.
    """

    patient_id: str = sqlmodel.Field(index=True, unique=True)
    name: str
    department: str
    priority: int
    status: str = "waiting"


class DirectMessage(rx.Model, table=True):
    """A direct message exchanged between two users."""

    conversation_key: str = sqlmodel.Field(index=True)
    sender_id: int = sqlmodel.Field(index=True)
    sender_name: str
    recipient_id: int = sqlmodel.Field(index=True)
    content: str
    created_at: dt.datetime = sqlmodel.Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
