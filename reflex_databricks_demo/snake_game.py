from __future__ import annotations

import random
import time

import reflex as rx
from reflex_local_auth import LocalAuthState, routes

from . import chat_repo
from .game_invite import game_key

# Board geometry.
GRID_W = 20
GRID_H = 20
EMPTY = "."

# Game loop tuning (milliseconds unless noted).
TICK_MS = 170
PULSE_MS = 2000
STALE_SECONDS = 8.0
COUNTDOWN_START = 3

# Keyboard -> direction vector. Arrow keys and WASD are both supported.
DIR_VECTORS: dict[str, tuple[int, int]] = {
    "ArrowUp": (0, -1),
    "ArrowDown": (0, 1),
    "ArrowLeft": (-1, 0),
    "ArrowRight": (1, 0),
    "w": (0, -1),
    "s": (0, 1),
    "a": (-1, 0),
    "d": (1, 0),
}


class SnakeGameState(rx.SharedState):
    """Shared real-time state for a 2-player snake battle.

    Player "a" is the lower user id (green), player "b" the higher (blue).
    Each client controls its own snake with the arrow keys / WASD. Only the
    host client (lowest user id present) drives the game loop via ``tick``.
    """

    status: str = "waiting"  # waiting | countdown | running | over
    board: list[str] = []
    food: list[int] = [0, 0]
    snake_a: list[list[int]] = []
    snake_b: list[list[int]] = []
    dir_a: list[int] = [1, 0]
    dir_b: list[int] = [-1, 0]
    score_a: int = 0
    score_b: int = 0
    winner: str = ""  # a | b | draw
    countdown: int = 0
    _members: dict[str, dict] = {}

    # ---- lifecycle -------------------------------------------------------

    @rx.event
    async def join(self, peer_id: int):
        auth = await self.get_state(LocalAuthState)
        if not auth.is_authenticated:
            return
        me = auth.authenticated_user
        try:
            peer_id = int(peer_id)
        except (TypeError, ValueError):
            return
        key = game_key("snake", int(me.id), peer_id)
        linked = await self._link_to(key)
        token = self.router.session.client_token
        members = dict(linked._members)
        members[token] = {
            "user_id": int(me.id),
            "username": me.username,
            "peer_id": peer_id,
            "last_seen": time.time(),
        }
        linked._members = members
        players = {int(m["user_id"]) for m in members.values()}
        # Only auto-start a fresh match; a finished game waits for "再玩一次"
        # so page reloads/re-joins cannot restart it mid-result.
        if linked.status == "waiting" and len(players) >= 2:
            linked._reset()

    @rx.event
    async def leave(self):
        if self._linked_to:
            members = dict(self._members)
            members.pop(self.router.session.client_token, None)
            self._members = members
            return await self._unlink()

    @rx.event
    async def tick(self, date: str):
        """Advance the game loop (host client only)."""
        if self.status == "countdown":
            self.countdown = max(0, self.countdown - 1)
            if self.countdown == 0:
                self.status = "running"
            return
        if self.status != "running":
            return
        self._advance()

    @rx.event
    async def pulse(self, date: str):
        """Per-client liveness beacon so disconnects can be detected."""
        token = self.router.session.client_token
        if token not in self._members:
            return
        members = dict(self._members)
        members[token] = {**members[token], "last_seen": time.time()}
        self._members = members

    @rx.event
    async def handle_key(self, key: str, key_info: dict):
        if self.status != "running":
            return
        vector = DIR_VECTORS.get(key)
        if vector is None:
            return
        member = self._members.get(self.router.session.client_token)
        if member is None:
            return
        role = self._role_of(int(member["user_id"]))
        if role is None:
            return
        current = self.dir_a if role == "a" else self.dir_b
        if (int(current[0]), int(current[1])) == (-vector[0], -vector[1]):
            return  # no 180-degree turns
        if role == "a":
            self.dir_a = [vector[0], vector[1]]
        else:
            self.dir_b = [vector[0], vector[1]]

    @rx.event
    async def restart(self):
        if self.status == "over":
            self._reset()

    # ---- game logic ------------------------------------------------------

    def _reset(self):
        # Start on separate rows moving toward opposite walls so the snakes do
        # not collide immediately; players must steer to survive.
        self.snake_a = [[4, 8], [3, 8], [2, 8]]
        self.snake_b = [[15, 12], [16, 12], [17, 12]]
        self.dir_a = [1, 0]
        self.dir_b = [-1, 0]
        self.score_a = 0
        self.score_b = 0
        self.winner = ""
        self.food = self._spawn_food()
        self.countdown = COUNTDOWN_START
        self.status = "countdown"
        self._rebuild_board()

    def _advance(self):
        all_users = {int(m["user_id"]) for m in self._members.values()}
        now = time.time()
        active_users = {
            int(m["user_id"])
            for m in self._members.values()
            if now - m["last_seen"] < STALE_SECONDS
        }
        if len(active_users) == 1 and len(all_users) >= 2:
            survivor = next(iter(active_users))
            self.winner = "a" if survivor == min(all_users) else "b"
            self.status = "over"
            self._rebuild_board()
            return

        head_a = [
            self.snake_a[0][0] + self.dir_a[0],
            self.snake_a[0][1] + self.dir_a[1],
        ]
        head_b = [
            self.snake_b[0][0] + self.dir_b[0],
            self.snake_b[0][1] + self.dir_b[1],
        ]
        occupied: set[tuple[int, int]] = {
            (int(cell[0]), int(cell[1]))
            for cell in [*self.snake_a, *self.snake_b]
        }
        dead_a = self._is_dead(head_a, occupied)
        dead_b = self._is_dead(head_b, occupied)
        if tuple(head_a) == tuple(head_b):
            dead_a = True
            dead_b = True
        if dead_a or dead_b:
            if dead_a and dead_b:
                self.winner = "draw"
            else:
                self.winner = "b" if dead_a else "a"
            self.status = "over"
            self._rebuild_board()
            return

        ate_a = head_a == self.food
        ate_b = head_b == self.food
        self.snake_a = [head_a] + (self.snake_a if ate_a else self.snake_a[:-1])
        self.snake_b = [head_b] + (self.snake_b if ate_b else self.snake_b[:-1])
        if ate_a:
            self.score_a += 1
            self.food = self._spawn_food()
        elif ate_b:
            self.score_b += 1
            self.food = self._spawn_food()
        self._rebuild_board()

    @staticmethod
    def _is_dead(head: list[int], occupied: set[tuple[int, int]]) -> bool:
        x, y = head
        if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
            return True
        return (x, y) in occupied

    def _spawn_food(self) -> list[int]:
        occupied = {tuple(cell) for cell in self.snake_a} | {
            tuple(cell) for cell in self.snake_b
        }
        free = [
            (x, y)
            for x in range(GRID_W)
            for y in range(GRID_H)
            if (x, y) not in occupied
        ]
        if not free:
            return [0, 0]
        x, y = random.choice(free)
        return [x, y]

    def _rebuild_board(self):
        cells = [EMPTY] * (GRID_W * GRID_H)
        fx, fy = self.food
        cells[fy * GRID_W + fx] = "f"
        for index, (x, y) in enumerate(self.snake_a):
            cells[y * GRID_W + x] = "A" if index == 0 else "a"
        for index, (x, y) in enumerate(self.snake_b):
            cells[y * GRID_W + x] = "B" if index == 0 else "b"
        self.board = cells

    def _users(self) -> set[int]:
        return {int(m["user_id"]) for m in self._members.values()}

    def _role_of(self, user_id: int) -> str | None:
        users = self._users()
        if len(users) < 2:
            return None
        return "a" if user_id == min(users) else "b"

    def _name_for_role(self, role: str) -> str:
        users = self._users()
        if len(users) < 2:
            return ""
        target = min(users) if role == "a" else max(users)
        for member in self._members.values():
            if int(member["user_id"]) == target:
                return str(member["username"])
        return ""

    # ---- computed vars ---------------------------------------------------

    @rx.var
    def i_am_host(self) -> bool:
        users = self._users()
        member = self._members.get(self.router.session.client_token)
        if not users or member is None:
            return False
        return int(member["user_id"]) == min(users)

    @rx.var
    def name_a(self) -> str:
        return self._name_for_role("a")

    @rx.var
    def name_b(self) -> str:
        return self._name_for_role("b")

    @rx.var
    def winner_text(self) -> str:
        if self.status != "over":
            return ""
        if self.winner == "draw":
            return "平手！"
        if self.winner in ("a", "b"):
            return f"{self._name_for_role(self.winner)} 獲勝！"
        return ""


class SnakeRoomState(rx.State):
    """Private per-page state for a snake battle room."""

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
        return SnakeGameState.join(peer_id)
