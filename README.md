# Reflex Databricks Demo

A [Reflex](https://reflex.dev/) chat app (login + 1:1 direct messages), set up with the
same dev conventions as `codoc_in_md` (for publishing to the agentic app store).

## Features

- **Auth**: local username/password login and open registration (`reflex-local-auth`).
- **Friends sidebar + chat**: a two-column layout (contacts on the left, conversation on
  the right). On small screens the columns swap based on whether a chat is open.
- **1:1 chat** (`/dm/[peer_id]`): real-time messages, typing indicator and persistent
  history. Real-time delivery uses Reflex **`rx.SharedState`** (WebSocket broadcast).
  Contacts are ordered by most recent conversation and show a last-message preview.
- **Patients** (`/patients`): demo table backed by local SQLite (SQLModel).
- **Games** (`/games`): two-player battle games. The first is **Snake battle**
  (`/play/snake/[peer_id]`): invite a friend from the chat composer ("邀請遊戲"),
  they accept, and both snakes fight in real time over `rx.SharedState`. Tank
  battle / chess / bomberman are listed as coming soon.

## Getting Started

Requirements: **Python 3.11** and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                           # first time only (and after dependency changes)
cp .env.template .env             # first time only, then fill in your Databricks values
uv run reflex db init             # first time only: create alembic config + schema
uv run reflex db migrate          # apply migrations
uv run python seed.py             # first time only: demo users + sample chat
uv run ./reflex_rerun.sh          # start / restart the app
```

`.env` holds your Databricks connection (`DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH`). It is git-ignored, so never commit real values.

Then open http://localhost:3000

Demo accounts (created by `seed.py`, password `password123`): **alice** and **bob**.
Register a new account on `/register`, or log in as one of the demo users.

## Local SQLite (SQLModel ORM)

This project uses Reflex's built-in `rx.Model` (a `SQLModel`) backed by SQLite
(`sqlite:///reflex.db`, configured in `rxconfig.py`). Models live in
`reflex_databricks_demo/models.py` (`Patient`, `DirectMessage`); auth tables
(`LocalUser`, `LocalAuthSession`) come from `reflex-local-auth`. The `Patient` model
mirrors the `default.patients` table used by `databricks_client.py`.

After changing a model, generate and apply a migration:

```bash
uv run reflex db makemigrations --message "describe change"
uv run reflex db migrate
```

`reflex.db` is git-ignored; `alembic/` and `alembic.ini` are committed.

## Architecture notes

- `dm_state.py`: `PresenceState` (global online list) and `SharedDmState` (per
  conversation) are `rx.SharedState` subclasses linked by a token. Conversation tokens
  are `dm-{low}-{high}` (hyphens only — SharedState tokens may not contain `_`).
- `DmRoomState` is the private per-page state; it links the shared state on page load.
- Sender identity always comes from the authenticated session on the backend, never
  from client-supplied event arguments.
- Own messages align right, the peer's align left (see `message_bubble` in `pages.py`).
- `game_invite.py`: `GameInviteState` is a global `SharedState` channel (token
  `game-invites`) that carries invitations keyed by recipient id, so an invite
  reaches a friend even when they are not on the conversation page.
  `GameBusState` reads it per client and navigates both players to
  `/play/<game>/[peer_id]` once accepted. Add new games to `GAMES`.
- `snake_game.py`: `SnakeGameState` is the per-pair game room (token
  `game-{game}-{lo}-{hi}`). Player "a" is the lower user id (green), "b" the
  higher (blue); the lowest user id present drives the loop (`tick`). Keyboard
  input arrives through `rx.window_event_listener`. Games are in-memory only
  (no database rows).

## E2E Tests

```bash
uv run playwright install chromium   # first time only
uv run ./run_test_suite.sh smoke_home
uv run ./run_test_suite.sh auth_flow   # register -> login -> sidebar -> logout
uv run ./run_test_suite.sh dm_flow     # two users: broadcast, typing, alignment, persistence
uv run ./run_test_suite.sh snake_flow  # two users: invite -> accept -> snake battle -> winner
```

Add `HEADLESS=0` to watch the browser. See [testcases/README.md](testcases/README.md) for more options.

## Troubleshooting

If uv picks a Python other than 3.11:

```bash
uv python install 3.11
uv sync --python 3.11
```

## License

[MIT](LICENSE)
