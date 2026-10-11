import reflex as rx
import reflex_local_auth

from . import pages
from .dm_state import DmRoomState
from .auth import LobbyState
from .snake_game import SnakeRoomState

app = rx.App()

app.add_page(
    pages.lobby_page,
    route="/",
    title="聊天",
    on_load=LobbyState.load_contacts,
)
app.add_page(
    pages.dm_page,
    route="/dm/[peer_id]",
    title="聊天",
    on_load=[LobbyState.load_contacts, DmRoomState.on_load],
)
app.add_page(
    pages.patients_page,
    route="/patients",
    title="Patients",
    on_load=pages.PatientsState.load,
)
app.add_page(pages.games_page, route="/games", title="遊戲")
app.add_page(
    pages.snake_page,
    route="/play/snake/[peer_id]",
    title="貪食蛇",
    on_load=SnakeRoomState.on_load,
)
app.add_page(
    reflex_local_auth.pages.login_page,
    route=reflex_local_auth.routes.LOGIN_ROUTE,
    title="登入",
)
app.add_page(
    reflex_local_auth.pages.register_page,
    route=reflex_local_auth.routes.REGISTER_ROUTE,
    title="註冊",
)
