from __future__ import annotations

import pydantic
import reflex as rx
from reflex_local_auth import LocalAuthState, routes

from . import chat_repo
from .dm_state import PresenceState


class AuthState(rx.State):
    """App-level authentication helpers (logout with redirect)."""

    @rx.event
    def logout(self):
        """Clear presence, destroy the auth session and return to login."""
        return [
            PresenceState.leave,
            LocalAuthState.do_logout,
            rx.redirect(routes.LOGIN_ROUTE),
        ]


class ContactRow(pydantic.BaseModel):
    """A contact as shown in the friends sidebar."""

    id: int
    username: str
    last_message_at: str = ""
    last_message_preview: str = ""


class LobbyState(rx.State):
    """Private state for the friends sidebar (contacts list)."""

    contacts: list[ContactRow] = []

    @rx.event
    async def load_contacts(self):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return rx.redirect(routes.LOGIN_ROUTE)
        me_id = int(auth.authenticated_user.id)
        self.contacts = [
            ContactRow(
                id=c.id,
                username=c.username,
                last_message_at=c.last_message_at,
                last_message_preview=c.last_message_preview,
            )
            for c in chat_repo.list_contacts_for(me_id)
        ]
