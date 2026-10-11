from __future__ import annotations

import reflex as rx
from reflex_local_auth import LocalAuthState, routes

from .auth import AuthState, ContactRow, LobbyState
from .dm_state import (
    HEARTBEAT_INTERVAL_MS,
    DmRoomState,
    PresenceState,
    SharedDmState,
)
from .game_invite import GameBusState, GameInviteState
from .models import Patient
from .patient_repo import list_patients
from .snake_game import (
    GRID_W,
    PULSE_MS,
    TICK_MS,
    SnakeGameState,
    SnakeRoomState,
)

# Layout constants.
NAVBAR_HEIGHT = "57px"
SIDEBAR_WIDTH = "300px"
CHAT_HEIGHT = f"calc(100vh - {NAVBAR_HEIGHT})"


class PatientsState(rx.State):
    """Demo state for the /patients page (local SQLite via SQLModel)."""

    patients: list[Patient] = []

    @rx.event
    def load(self):
        self.patients = list(list_patients())


def invite_button() -> rx.Component:
    """Dropdown in the conversation composer to invite the peer to a game."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                rx.icon("gamepad-2", size=16),
                "邀請遊戲",
                variant="soft",
                color_scheme="violet",
            ),
        ),
        rx.menu.content(
            rx.menu.item(
                "貪食蛇（雙人對戰）",
                on_select=DmRoomState.invite("snake"),
            ),
            rx.menu.item("坦克大戰（即將推出）", disabled=True),
            rx.menu.item("西洋棋（即將推出）", disabled=True),
            rx.menu.item("炸彈超人（即將推出）", disabled=True),
        ),
    )


def invite_overlays() -> rx.Component:
    """Global invitation dialog, sender status and background pollers."""
    return rx.fragment(
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.dialog.title("遊戲邀請"),
                    rx.dialog.description(
                        f"{GameBusState.incoming_from} 邀請你玩 {GameBusState.incoming_game_title}"
                    ),
                    rx.hstack(
                        rx.button(
                            "接受",
                            color_scheme="green",
                            on_click=GameInviteState.accept_invite,
                        ),
                        rx.button(
                            "拒絕",
                            variant="soft",
                            color_scheme="red",
                            on_click=GameInviteState.decline_invite,
                        ),
                        spacing="3",
                        justify="end",
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                max_width="24em",
            ),
            open=GameBusState.has_incoming,
        ),
        rx.cond(
            GameBusState.sent_status == "pending",
            rx.box(
                rx.callout(
                    f"已邀請 {GameBusState.sent_target} 玩 {GameBusState.sent_game_title}，等待回應…",
                    icon="send",
                    color_scheme="violet",
                ),
                position="fixed",
                bottom="1.5em",
                right="1.5em",
                z_index="1000",
                max_width="20em",
            ),
        ),
        rx.cond(
            GameBusState.sent_status == "declined",
            rx.box(
                rx.callout(
                    f"{GameBusState.sent_target} 拒絕了遊戲邀請。",
                    icon="x",
                    color_scheme="red",
                ),
                position="fixed",
                bottom="1.5em",
                right="1.5em",
                z_index="1000",
                max_width="20em",
                on_click=GameInviteState.clear_invite,
            ),
        ),
        # Keep every client linked to the global invitation channel.
        rx.moment(
            interval=2000,
            on_change=GameInviteState.heartbeat,
            style={"display": "none"},
        ),
        # Redirect both players once an invitation is accepted.
        rx.moment(
            interval=1000,
            on_change=GameBusState.poll,
            style={"display": "none"},
        ),
    )


def navbar() -> rx.Component:
    """Top navigation bar, shared across pages."""
    return rx.hstack(
        rx.link("聊天", href="/", font_weight="bold"),
        rx.link("Patients", href="/patients"),
        rx.link("遊戲", href="/games"),
        rx.spacer(),
        rx.cond(
            LocalAuthState.is_authenticated,
            rx.hstack(
                rx.text(LocalAuthState.authenticated_user.username),
                rx.button(
                    "登出",
                    variant="soft",
                    on_click=AuthState.logout,
                ),
                spacing="3",
                align="center",
            ),
            rx.link("登入", href=routes.LOGIN_ROUTE),
        ),
        # Periodic heartbeat keeps the presence list fresh.
        rx.cond(
            LocalAuthState.is_authenticated,
            rx.moment(
                interval=HEARTBEAT_INTERVAL_MS,
                on_change=PresenceState.heartbeat,
                style={"display": "none"},
            ),
            rx.fragment(),
        ),
        invite_overlays(),
        width="100%",
        height=NAVBAR_HEIGHT,
        padding="0.75em 1em",
        align="center",
        border_bottom=f"1px solid {rx.color('gray', 5)}",
    )


def online_dot(is_online) -> rx.Component:
    return rx.box(
        width="9px",
        height="9px",
        border_radius="full",
        flex_shrink="0",
        background_color=rx.cond(
            is_online, rx.color("green", 9), rx.color("gray", 6)
        ),
    )


def friend_row(contact: ContactRow) -> rx.Component:
    selected = contact.id.to_string() == rx.State.peer_id
    return rx.link(
        rx.hstack(
            rx.avatar(fallback=contact.username[0].upper(), radius="full", size="3"),
            rx.vstack(
                rx.hstack(
                    rx.text(contact.username, font_weight="bold"),
                    online_dot(PresenceState.online_user_ids.contains(contact.id)),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    contact.last_message_preview != "",
                    rx.hstack(
                        rx.text(
                            contact.last_message_preview,
                            font_size="0.78em",
                            color_scheme="gray",
                            max_width="150px",
                            overflow="hidden",
                            white_space="nowrap",
                            text_overflow="ellipsis",
                        ),
                        rx.spacer(),
                        rx.moment(
                            contact.last_message_at,
                            from_now=True,
                            font_size="0.68em",
                            color="gray",
                            flex_shrink="0",
                        ),
                        width="100%",
                        spacing="2",
                        align="center",
                    ),
                    rx.text("尚未對話", font_size="0.78em", color_scheme="gray"),
                ),
                spacing="1",
                align_items="start",
                flex="1",
                min_width="0",
            ),
            width="100%",
            padding="0.5em",
            border_radius="8px",
            align="center",
            spacing="3",
            background_color=rx.cond(selected, rx.color("accent", 3), "transparent"),
            _hover={"background_color": rx.color("gray", 3)},
        ),
        href=f"/dm/{contact.id}",
        width="100%",
        text_decoration="none",
        color="inherit",
    )


def friends_sidebar() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("好友", size="5"),
            rx.spacer(),
            rx.text(
                LocalAuthState.authenticated_user.username,
                font_size="0.78em",
                color_scheme="gray",
            ),
            width="100%",
            align="center",
        ),
        rx.scroll_area(
            rx.vstack(
                rx.foreach(LobbyState.contacts, friend_row),
                spacing="1",
                width="100%",
            ),
            flex="1",
            width="100%",
        ),
        # Refresh ordering/previews periodically.
        rx.moment(
            interval=HEARTBEAT_INTERVAL_MS,
            on_change=LobbyState.load_contacts,
            style={"display": "none"},
        ),
        width=rx.breakpoints(initial="100%", md=SIDEBAR_WIDTH),
        flex_shrink="0",
        height="100%",
        padding="1em",
        spacing="3",
        align="start",
        border_right=rx.breakpoints(
            initial="none", md=f"1px solid {rx.color('gray', 5)}"
        ),
        # On small screens: show only when no conversation is selected.
        display=rx.breakpoints(
            initial=rx.cond(rx.State.peer_id == "", "flex", "none"),
            md="flex",
        ),
    )


def empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon("messages-square", size=48, color=rx.color("gray", 8)),
            rx.text("選擇左邊的使用者開始聊天", color_scheme="gray"),
            align="center",
            spacing="3",
        ),
        height="100%",
        width="100%",
    )


def message_bubble(message) -> rx.Component:
    mine = message.sender_id == LocalAuthState.authenticated_user.id
    return rx.hstack(
        rx.cond(
            mine,
            rx.fragment(),
            rx.avatar(
                fallback=message.sender_name[0].upper(),
                radius="full",
                size="2",
                flex_shrink="0",
            ),
        ),
        rx.vstack(
            rx.cond(
                mine,
                rx.fragment(),
                rx.text(
                    message.sender_name,
                    font_size="0.72em",
                    font_weight="bold",
                    color_scheme="gray",
                ),
            ),
            rx.text(message.content, white_space="pre-wrap"),
            rx.moment(
                message.created_at,
                from_now=True,
                font_size="0.62em",
                color="gray",
            ),
            spacing="1",
            align_items=rx.cond(mine, "end", "start"),
            padding="0.5em 0.85em",
            border_radius="12px",
            background_color=rx.cond(mine, rx.color("accent", 3), rx.color("gray", 3)),
            max_width="70%",
            margin_left=rx.cond(mine, "auto", "0"),
            margin_right=rx.cond(mine, "0", "auto"),
        ),
        width="100%",
        spacing="2",
        align="start",
    )


def conversation() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.link(
                "←",
                href="/",
                font_size="1.3em",
                display=rx.breakpoints(initial="flex", md="none"),
            ),
            rx.heading(f"與 {DmRoomState.peer_name} 的對話", size="5"),
            rx.spacer(),
            rx.cond(
                DmRoomState.peer_typing,
                rx.text("對方正在輸入…", font_style="italic", color="gray", font_size="0.8em"),
                rx.fragment(),
            ),
            width="100%",
            align="center",
            spacing="3",
        ),
        rx.auto_scroll(
            rx.vstack(
                rx.foreach(SharedDmState.messages, message_bubble),
                spacing="3",
                width="100%",
                id="dm-messages",
            ),
            flex="1",
            width="100%",
            padding="0.5em",
            border=f"1px solid {rx.color('gray', 4)}",
            border_radius="12px",
        ),
        rx.hstack(
            rx.input(
                value=DmRoomState.draft,
                on_change=DmRoomState.set_draft,
                placeholder="輸入訊息…",
                width="100%",
            ),
            invite_button(),
            rx.button("送出", on_click=DmRoomState.send),
            width="100%",
            spacing="3",
        ),
        width="100%",
        height="100%",
        padding=rx.breakpoints(initial="0.5em", md="1em"),
        spacing="3",
        align="start",
        # On small screens: show only when a conversation is selected.
        display=rx.breakpoints(
            initial=rx.cond(rx.State.peer_id == "", "none", "flex"),
            md="flex",
        ),
    )


def chat_shell(main: rx.Component) -> rx.Component:
    return rx.hstack(
        friends_sidebar(),
        main,
        width="100%",
        height=CHAT_HEIGHT,
        spacing="0",
        align="stretch",
        overflow="hidden",
    )


def lobby_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        chat_shell(empty_state()),
        width="100%",
        spacing="0",
        align="stretch",
    )


def dm_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        chat_shell(conversation()),
        width="100%",
        spacing="0",
        align="stretch",
    )


def patients_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        rx.container(
            rx.vstack(
                rx.heading("Patients", size="7"),
                rx.text(
                    "本地 SQLite（SQLModel ORM）中的病人資料。",
                    color_scheme="gray",
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("ID"),
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("Department"),
                            rx.table.column_header_cell("Priority"),
                            rx.table.column_header_cell("Status"),
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(
                            PatientsState.patients,
                            lambda patient: rx.table.row(
                                rx.table.cell(patient.patient_id),
                                rx.table.cell(patient.name),
                                rx.table.cell(patient.department),
                                rx.table.cell(patient.priority),
                                rx.table.cell(patient.status),
                            ),
                        ),
                    ),
                ),
                spacing="4",
                width="100%",
                align="start",
            ),
            padding="1.5em",
            max_width="48em",
        ),
        width="100%",
    )


def game_card(
    title: str,
    description: str,
    badge: str = "即將推出",
    color: str = "amber",
) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading(title, size="5"),
            rx.text(description, color_scheme="gray"),
            rx.badge(badge, color_scheme=color, variant="soft"),
            spacing="2",
            align="start",
        ),
        width="100%",
    )


def games_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        rx.container(
            rx.vstack(
                rx.heading("小遊戲", size="7"),
                rx.text(
                    "所有遊戲都是雙人對戰。到聊天視窗底部按「邀請遊戲」，"
                    "對方接受後即可開戰。",
                    color_scheme="gray",
                ),
                game_card(
                    "貪食蛇",
                    "經典雙人對戰：吃果實讓身體變長，先撞到牆或蛇身的人就輸了。",
                    badge="可邀請對戰",
                    color="green",
                ),
                game_card("坦克大戰", "即時對戰的坦克射擊遊戲。"),
                game_card("西洋棋", "經典的雙人西洋棋對局。"),
                game_card("炸彈超人", "放置炸彈、炸開障礙、擊敗對手。"),
                spacing="4",
                width="100%",
                align="start",
            ),
            padding="1.5em",
            max_width="48em",
        ),
        width="100%",
    )


def cell_color(cell) -> rx.Component:
    return rx.cond(
        cell == "A",
        rx.color("green", 11),
        rx.cond(
            cell == "a",
            rx.color("green", 8),
            rx.cond(
                cell == "B",
                rx.color("blue", 11),
                rx.cond(
                    cell == "b",
                    rx.color("blue", 8),
                    rx.cond(
                        cell == "f",
                        rx.color("orange", 9),
                        rx.color("gray", 4),
                    ),
                ),
            ),
        ),
    )


def board_cell(cell, index) -> rx.Component:
    return rx.box(
        key=index,
        width="100%",
        aspect_ratio="1",
        border_radius="2px",
        background_color=cell_color(cell),
    )


def snake_board() -> rx.Component:
    return rx.box(
        rx.foreach(SnakeGameState.board, board_cell),
        id="snake-board",
        style={
            "display": "grid",
            "grid_template_columns": f"repeat({GRID_W}, 1fr)",
            "gap": "2px",
            "width": "100%",
            "aspect_ratio": "1",
            "padding": "0.5em",
            "background_color": rx.color("gray", 2),
            "border_radius": "12px",
        },
    )


def player_score(name, score, color: str) -> rx.Component:
    return rx.badge(
        f"{name}：{score}",
        color_scheme=color,
        variant="soft",
        size="3",
    )


def snake_status() -> rx.Component:
    return rx.cond(
        SnakeGameState.status == "waiting",
        rx.callout("等待對手加入…", icon="clock", color_scheme="gray"),
        rx.cond(
            SnakeGameState.status == "countdown",
            rx.center(
                rx.heading(SnakeGameState.countdown, size="9"),
                width="100%",
                min_height="4em",
            ),
            rx.cond(
                SnakeGameState.status == "over",
                rx.vstack(
                    rx.heading(SnakeGameState.winner_text, size="6", id="snake-winner"),
                    rx.button(
                        "再玩一次",
                        on_click=SnakeGameState.restart,
                        color_scheme="green",
                    ),
                    align="center",
                    spacing="3",
                ),
                rx.text("對戰中！吃到果實可讓身體變長。", color_scheme="gray"),
            ),
        ),
    )


def snake_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        rx.container(
            rx.vstack(
                rx.hstack(
                    rx.link(
                        "← 返回聊天",
                        href="/",
                        font_size="0.9em",
                        display=rx.breakpoints(initial="flex", md="none"),
                    ),
                    rx.heading(f"貪食蛇：{SnakeRoomState.peer_name}", size="6"),
                    width="100%",
                    align="center",
                    spacing="3",
                ),
                rx.hstack(
                    player_score(SnakeGameState.name_a, SnakeGameState.score_a, "green"),
                    rx.text("VS", font_weight="bold", color_scheme="gray"),
                    player_score(SnakeGameState.name_b, SnakeGameState.score_b, "blue"),
                    spacing="3",
                    align="center",
                ),
                snake_status(),
                snake_board(),
                rx.text(
                    "用方向鍵（或 WASD）移動你的蛇。撞牆、撞到自己或對手就輸了。",
                    font_size="0.8em",
                    color_scheme="gray",
                ),
                spacing="4",
                width="100%",
                align="center",
            ),
            padding="1.5em",
            max_width="34em",
        ),
        # Capture keyboard input for the local player's snake.
        rx.window_event_listener(on_key_down=SnakeGameState.handle_key),
        # Only the host client drives the game loop.
        rx.cond(
            SnakeGameState.i_am_host & (SnakeGameState.status != "over"),
            rx.moment(
                interval=TICK_MS,
                on_change=SnakeGameState.tick,
                style={"display": "none"},
            ),
            rx.fragment(),
        ),
        # Per-client liveness beacon so disconnects are detected.
        rx.moment(
            interval=PULSE_MS,
            on_change=SnakeGameState.pulse,
            style={"display": "none"},
        ),
        width="100%",
    )
