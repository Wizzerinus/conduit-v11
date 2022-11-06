import functools
import json
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from starlette.websockets import WebSocket

from pyconduit.models.user import User
from pyconduit.shared.datastore import datastore_manager, deatomize
from pyconduit.shared.helpers import get_config

templates = Jinja2Templates(directory="templates")


def get_flashed_messages(request: Request) -> None | dict:
    if "flash" in request.session:
        flash = request.session["flash"]
        request.session["flash"] = []
        return flash
    return None


templates.env.globals["get_flashed_messages"] = get_flashed_messages
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
user_datastore = datastore_manager.get("accounts")
locale = get_config("localization")


def find_user(username: str) -> None | User:
    user_dict = user_datastore.accounts
    if username not in user_dict:
        return None

    user_obj = User.parse_obj(deatomize(user_dict[username]))
    if not user_obj.privileges.login:
        raise HTTPException(status_code=401, detail=locale["exceptions"]["account_disabled"])

    return user_obj


def flash_message(request: Request, message: str, level: str = "info"):
    if not (flash_list := request.session.get("flash")):
        flash_list = []
        request.session["flash"] = flash_list
    flash_list.append({"message": message, "level": level})


async def get_user_by_token(token: str) -> None | User:
    try:
        payload = jwt.decode(token, get_config("secrets")["jwt_salt"], algorithms=["HS256"])
    except jwt.JWTError:
        return None

    subject: str = payload.get("sub")
    if not subject:
        return None

    username_pair = subject.split(":")
    if len(username_pair) != 2 or username_pair[0] != "user":
        return None

    return find_user(username_pair[1])


async def get_current_user(request: Request = None, token: str | None = Depends(oauth2_scheme)) -> None | User:
    if request is not None and token is None:
        token = request.session.get("access_token")
        if token is None:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
    if token is None:
        return None
    return await get_user_by_token(token)


async def require_login(user: None | User = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=locale["exceptions"]["bad_jwt"],
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


class RequireScope:
    def __init__(self, scope: str):
        self.scope = scope

    def __call__(self, user: User = Depends(require_login)) -> User:
        if not user.privileges.has_scope(self.scope):
            raise HTTPException(status_code=403, detail=locale["exceptions"]["insufficient_scope"])
        return user


def create_access_token(data: dict, expire: timedelta = timedelta(hours=168)) -> str:
    to_encode = data.copy()
    expire_time = datetime.utcnow() + expire
    to_encode.update({"exp": expire_time})
    encoded_jwt = jwt.encode(to_encode, get_config("secrets")["jwt_salt"], algorithm="HS256")
    return encoded_jwt


async def make_template_data(request: Request, user: None | User = None, **kwargs) -> dict:
    def check_scope(scope: str):
        if user is None:
            return False
        return user.privileges.has_scope(scope)

    return dict(
        kwargs,
        request=request,
        locale=get_config("localization"),
        webcfg=get_config("website"),
        user=user,
        check_scope=check_scope,
    )


class SocketHandle:
    def __init__(self, mgr: "SocketManager", ws: WebSocket, alloc: int):
        self.mgr = mgr
        self.ws = ws
        self.id = alloc

    async def receive_text(self) -> str:
        while True:
            text = await self.ws.receive_text()
            if text == "__ping":
                await self.ws.send_text("__pong")
            else:
                return text

    async def receive_json(self) -> dict:
        return json.loads(await self.receive_text())


class SocketManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self.allocated = 0

    async def connect(self, websocket: WebSocket) -> SocketHandle:
        await websocket.accept()
        self.active_connections.add(websocket)
        self.allocated += 1
        return SocketHandle(self, websocket, self.allocated)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def __broadcast(self, message: str, exclusions: set[WebSocket] = None):
        for connection in self.active_connections:
            if not exclusions or connection not in exclusions:
                await connection.send_text(message)

    @functools.singledispatchmethod
    async def broadcast(self, message, exclusions: set[WebSocket] = None):
        pass

    @broadcast.register
    async def _(self, message: str, exclusions: set[WebSocket] = None):
        await self.__broadcast(message, exclusions)

    @broadcast.register
    async def _(self, message: dict, exclusions: set[WebSocket] = None):
        await self.__broadcast(json.dumps(message), exclusions)
