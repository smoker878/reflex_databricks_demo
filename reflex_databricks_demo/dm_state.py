from __future__ import annotations

import time

import pydantic
import reflex as rx
from reflex_local_auth import LocalAuthState, routes

from . import chat_repo
from .models import conversation_key

# How long a client is considered "online" after its last heartbeat.
ONLINE_TTL_SECONDS = 15.0
# How long a "typing" signal stays true after the last keystroke.
TYPING_TTL_SECONDS = 4.0
# Presence heartbeat interval (milliseconds).
HEARTBEAT_INTERVAL_MS = 5000


class DmMessage(pydantic.BaseModel):
    """A serializable direct message sent to the frontend."""

    sender_id: int
    sender_name: str
    content: str
    created_at: str


class PresenceState(rx.SharedState):
    """Global presence: which users are currently online.

    Every authenticated client links to the shared token ``online`` and sends a
    heartbeat every few seconds. User identity comes from the authenticated
    session on the backend, never from client-supplied arguments.
    """

    _online: dict[str, dict] = {}

    @rx.event
    async def heartbeat(self, date: str):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        user = auth.authenticated_user
        linked = await self._link_to("online")
        linked._online[self.router.session.client_token] = {
            "user_id": int(user.id),
            "username": user.username,
            "last_seen": time.time(),
        }

    @rx.event
    async def leave(self):
        if self._linked_to:
            self._online.pop(self.router.session.client_token, None)
            return await self._unlink()

    @rx.var
    def online_user_ids(self) -> list[int]:
        """User ids seen within the online TTL window."""
        now = time.time()
        return sorted(
            {
                int(entry["user_id"])
                for entry in self._online.values()
                if now - float(entry["last_seen"]) < ONLINE_TTL_SECONDS
            }
        )


class SharedDmState(rx.SharedState):
    """Shared, broadcast state for the conversation between two users."""

    messages: list[DmMessage] = []
    _members: dict[str, dict] = {}
    _typing: dict[str, float] = {}

    @rx.event
    async def join(self, peer_id: int):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        me = auth.authenticated_user
        key = conversation_key(int(me.id), int(peer_id))
        linked = await self._link_to(key)
        linked._members[self.router.session.client_token] = {
            "user_id": int(me.id),
            "username": me.username,
            "peer_id": int(peer_id),
        }
        linked.messages = [
            DmMessage(
                sender_id=m.sender_id,
                sender_name=m.sender_name,
                content=m.content,
                created_at=m.created_at.isoformat(),
            )
            for m in chat_repo.list_messages(key)
        ]

    @rx.event
    async def send_message(self, content: str):
        content = (content or "").strip()
        if not content:
            return
        token = self.router.session.client_token
        member = self._members.get(token)
        if member is None:
            return
        saved = chat_repo.add_message(
            sender_id=int(member["user_id"]),
            sender_name=member["username"],
            recipient_id=int(member["peer_id"]),
            content=content,
        )
        self.messages = [
            *self.messages,
            DmMessage(
                sender_id=saved.sender_id,
                sender_name=saved.sender_name,
                content=saved.content,
                created_at=saved.created_at.isoformat(),
            ),
        ]
        self._typing[token] = 0.0

    @rx.event
    async def set_typing(self):
        self._typing[self.router.session.client_token] = time.time()

    @rx.event
    async def leave(self):
        if self._linked_to:
            self._members.pop(self.router.session.client_token, None)
            self._typing.pop(self.router.session.client_token, None)
            return await self._unlink()


class DmRoomState(rx.State):
    """Private state for a single 1:1 conversation page."""

    draft: str = ""
    peer_name: str = ""

    @rx.event
    async def on_load(self):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return rx.redirect(routes.LOGIN_ROUTE)
        try:
            peer_id = int(self.peer_id)
        except (TypeError, ValueError):
            return rx.redirect("/")
        if peer_id == int(auth.authenticated_user.id):
            return rx.redirect("/")
        peer = chat_repo.get_user(peer_id)
        if peer is None:
            return rx.redirect("/")
        self.peer_name = peer.username
        return SharedDmState.join(peer_id)

    @rx.var
    async def peer_typing(self) -> bool:
        shared = await self.get_state(SharedDmState)
        now = time.time()
        my_token = self.router.session.client_token
        return any(
            token != my_token and now - last < TYPING_TTL_SECONDS
            for token, last in shared._typing.items()
        )

    @rx.event
    def set_draft(self, value: str):
        self.draft = value
        if value:
            return SharedDmState.set_typing

    @rx.event
    def send(self):
        content = self.draft.strip()
        if not content:
            return
        self.draft = ""
        return SharedDmState.send_message(content)
