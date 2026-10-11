from __future__ import annotations

import time

import reflex as rx
from reflex_local_auth import LocalAuthState

from . import chat_repo

# How long a pending/accepted invitation stays valid (seconds).
INVITE_TTL_SECONDS = 30.0
# After the recipient accepts, the sender is auto-navigated within this window.
REDIRECT_WINDOW_SECONDS = 10.0

# Games that can be invited to. Extend this as more 2-player games are added.
GAMES: dict[str, str] = {
    "snake": "貪食蛇",
}


def game_title(game: str) -> str:
    """Return the display name of a game id."""
    return GAMES.get(game, game)


def game_key(game: str, user_a: int, user_b: int) -> str:
    """Deterministic SharedState token for a 2-player game room.

    Uses hyphens only (SharedState tokens may not contain underscores).
    """
    low, high = sorted((int(user_a), int(user_b)))
    return f"game-{game}-{low}-{high}"


class GameInviteState(rx.SharedState):
    """Global invitation channel reachable from every page.

    ``_invites`` is keyed by the *recipient's* user id so a recipient can find
    their invitation without knowing the conversation. Sender identity always
    comes from the authenticated session on the backend.
    """

    _invites: dict[int, dict] = {}

    @rx.event
    async def heartbeat(self, date: str):
        """Link this client to the global invite channel."""
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        await self._link_to("game-invites")

    @rx.event
    async def send_invite(self, game: str, peer_id: int):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated or game not in GAMES:
            return
        me = auth.authenticated_user
        try:
            peer_id = int(peer_id)
        except (TypeError, ValueError):
            return
        if peer_id == int(me.id):
            return
        linked = await self._link_to("game-invites")
        now = time.time()
        invites = {
            key: value
            for key, value in linked._invites.items()
            if now - value["ts"] < INVITE_TTL_SECONDS
        }
        invites[peer_id] = {
            "from_id": int(me.id),
            "from_name": me.username,
            "game": game,
            "ts": now,
            "status": "pending",
        }
        linked._invites = invites

    @rx.event
    async def accept_invite(self):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        me = int(auth.authenticated_user.id)
        linked = await self._link_to("game-invites")
        invite = linked._invites.get(me)
        if invite is None or invite["status"] != "pending":
            return
        invites = dict(linked._invites)
        invites[me] = {**invite, "status": "accepted", "accepted_at": time.time()}
        linked._invites = invites
        # Navigate the recipient immediately.
        return rx.redirect(f"/play/{invite['game']}/{int(invite['from_id'])}")

    @rx.event
    async def decline_invite(self):
        await self._set_status("declined")

    @rx.event
    async def clear_invite(self):
        """Dismiss my incoming invitation and any invitation I sent."""
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        me = int(auth.authenticated_user.id)
        linked = await self._link_to("game-invites")
        linked._invites = {
            key: value
            for key, value in linked._invites.items()
            if key != me and int(value["from_id"]) != me
        }

    async def _set_status(self, status: str):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        me = int(auth.authenticated_user.id)
        linked = await self._link_to("game-invites")
        invite = linked._invites.get(me)
        if invite is None or invite["status"] != "pending":
            return
        invites = dict(linked._invites)
        invites[me] = {**invite, "status": status}
        linked._invites = invites


class GameBusState(rx.State):
    """Per-client view over :class:`GameInviteState`.

    Computes the invitation addressed to (or sent by) the current user and
    triggers navigation once an invitation is accepted.
    """

    async def _me(self) -> int | None:
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return None
        return int(auth.authenticated_user.id)

    async def _incoming(self) -> dict | None:
        me = await self._me()
        if me is None:
            return None
        shared = await self.get_state(GameInviteState)
        now = time.time()
        invite = shared._invites.get(me)
        if (
            invite
            and invite["status"] == "pending"
            and now - invite["ts"] < INVITE_TTL_SECONDS
        ):
            return dict(invite)
        return None

    async def _outgoing(self) -> dict | None:
        me = await self._me()
        if me is None:
            return None
        shared = await self.get_state(GameInviteState)
        now = time.time()
        best: tuple[int, dict] | None = None
        for peer_id, invite in shared._invites.items():
            if int(invite["from_id"]) != me:
                continue
            if now - invite["ts"] >= INVITE_TTL_SECONDS:
                continue
            if best is None or invite["ts"] > best[1]["ts"]:
                best = (int(peer_id), dict(invite))
        if best is None:
            return None
        return {"peer_id": best[0], **best[1]}

    async def _redirect_route(self) -> str:
        me = await self._me()
        if me is None:
            return ""
        shared = await self.get_state(GameInviteState)
        now = time.time()
        for peer_id, invite in shared._invites.items():
            if invite["status"] != "accepted":
                continue
            accepted_at = invite.get("accepted_at", invite["ts"])
            if now - accepted_at >= REDIRECT_WINDOW_SECONDS:
                continue
            participants = (int(invite["from_id"]), int(peer_id))
            if me not in participants:
                continue
            other = participants[0] if me == participants[1] else participants[1]
            return f"/play/{invite['game']}/{other}"
        return ""

    @rx.var
    async def has_incoming(self) -> bool:
        return await self._incoming() is not None

    @rx.var
    async def incoming_from(self) -> str:
        invite = await self._incoming()
        return invite["from_name"] if invite else ""

    @rx.var
    async def incoming_game_title(self) -> str:
        invite = await self._incoming()
        return game_title(invite["game"]) if invite else ""

    @rx.var
    async def sent_status(self) -> str:
        invite = await self._outgoing()
        return invite["status"] if invite else ""

    @rx.var
    async def sent_target(self) -> str:
        invite = await self._outgoing()
        if not invite:
            return ""
        peer = chat_repo.get_user(int(invite["peer_id"]))
        return peer.username if peer else f"使用者 {invite['peer_id']}"

    @rx.var
    async def sent_game_title(self) -> str:
        invite = await self._outgoing()
        return game_title(invite["game"]) if invite else ""

    @rx.event
    async def poll(self):
        """Redirect the sender into the game once the invitation is accepted."""
        if self.router.url.path.startswith("/play/"):
            return
        route = await self._redirect_route()
        if route:
            return rx.redirect(route)
