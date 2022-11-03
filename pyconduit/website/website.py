from fastapi import Depends, FastAPI
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from pyconduit.shared.helpers import get_config
from pyconduit.website.decorators import get_current_user
from pyconduit.website.routers.admin import admin_app
from pyconduit.website.routers.sheets import sheets_app
from pyconduit.website.routers.index import index_app
from pyconduit.website.routers.login import login_app

cfg = get_config("secrets")

app = FastAPI(
    dependencies=[Depends(get_current_user)],
    middleware=[Middleware(SessionMiddleware, secret_key=cfg["session_salt"])],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/login", login_app)
app.mount("/admin", admin_app)
app.mount("/sheets", sheets_app)
app.mount("/", index_app)
