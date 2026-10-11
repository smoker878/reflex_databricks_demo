from typing import Sequence

import pydantic
import reflex as rx
import sqlmodel
from reflex_local_auth import LocalUser

from .models import DirectMessage, conversation_key

MESSAGE_PAGE_SIZE = 200
CONTACT_SCAN_LIMIT = 1000


class ContactInfo(pydantic.BaseModel):
    """A contact (other user) plus their most recent message with the viewer."""

    id: int
    username: str
    last_message_at: str = ""
    last_message_preview: str = ""


def list_users() -> Sequence[LocalUser]:
    """Return all registered users ordered by username."""
    with rx.session() as session:
        return session.exec(
            sqlmodel.select(LocalUser).order_by(LocalUser.username)
        ).all()


def list_contacts_for(user_id: int) -> list[ContactInfo]:
    """Return other users ordered by most recent conversation with ``user_id``.

    Users with no conversation come last, ordered by username.
    """
    with rx.session() as session:
        users = session.exec(
            sqlmodel.select(LocalUser).where(LocalUser.id != user_id)
        ).all()
        messages = session.exec(
            sqlmodel.select(DirectMessage)
            .where(
                sqlmodel.or_(
                    DirectMessage.sender_id == user_id,
                    DirectMessage.recipient_id == user_id,
                )
            )
            .order_by(DirectMessage.created_at.desc())
            .limit(CONTACT_SCAN_LIMIT)
        ).all()

    latest: dict[int, DirectMessage] = {}
    for message in messages:
        peer_id = (
            message.recipient_id
            if message.sender_id == user_id
            else message.sender_id
        )
        latest.setdefault(int(peer_id), message)

    contacts = [
        ContactInfo(
            id=int(user.id),
            username=user.username,
            last_message_at=(
                latest[int(user.id)].created_at.isoformat()
                if int(user.id) in latest
                else ""
            ),
            last_message_preview=(
                latest[int(user.id)].content if int(user.id) in latest else ""
            ),
        )
        for user in users
    ]

    with_messages = [c for c in contacts if c.last_message_at]
    without_messages = [c for c in contacts if not c.last_message_at]
    with_messages.sort(key=lambda c: c.last_message_at, reverse=True)
    without_messages.sort(key=lambda c: c.username)
    return with_messages + without_messages


def get_user(user_id: int) -> LocalUser | None:
    """Return a single user by id, or None."""
    with rx.session() as session:
        return session.exec(
            sqlmodel.select(LocalUser).where(LocalUser.id == user_id)
        ).one_or_none()


def list_messages(
    key: str, limit: int = MESSAGE_PAGE_SIZE
) -> Sequence[DirectMessage]:
    """Return the most recent messages of a conversation, oldest first."""
    with rx.session() as session:
        rows = session.exec(
            sqlmodel.select(DirectMessage)
            .where(DirectMessage.conversation_key == key)
            .order_by(DirectMessage.created_at.desc())
            .limit(limit)
        ).all()
    return list(reversed(rows))


def add_message(
    sender_id: int,
    sender_name: str,
    recipient_id: int,
    content: str,
) -> DirectMessage:
    """Persist a direct message and return it."""
    message = DirectMessage(
        conversation_key=conversation_key(sender_id, recipient_id),
        sender_id=sender_id,
        sender_name=sender_name,
        recipient_id=recipient_id,
        content=content,
    )
    with rx.session() as session:
        session.add(message)
        session.commit()
        session.refresh(message)
    return message
