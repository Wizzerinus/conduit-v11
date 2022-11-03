import hashlib
import hmac

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from pyconduit.models.user import RegisterUser
from pyconduit.shared.datastore import datastore_manager
from pyconduit.shared.helpers import get_config
from pyconduit.website.decorators import RequireScope, create_access_token, find_user, flash_message

login_app = FastAPI()
secrets = get_config("secrets")
locale = get_config("localization")
datastore = datastore_manager.get("accounts")
require_admin = RequireScope("admin")


def hash_password(password: str, hasher: str) -> str:
    algo, salt = hasher.split(";")
    if algo == "scrypt":
        return hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), n=2**14, r=8, p=1, dklen=64).hex()
    raise ValueError(f"Unknown hasher: {algo}")


@login_app.post("/token")
async def generate_token(init_user: OAuth2PasswordRequestForm = Depends()):
    user = find_user(init_user.username)
    if not user:
        raise HTTPException(status_code=401, detail=locale["exceptions"]["invalid_credentials"])

    password_hash = hash_password(init_user.password, user.salt)
    if not hmac.compare_digest(password_hash, user.password):
        raise HTTPException(status_code=401, detail=locale["exceptions"]["invalid_credentials"])

    access_token = create_access_token(dict(sub=f"user:{user.login}"))
    return {"access_token": access_token, "token_type": "bearer", "expires": 168 * 3600}


@login_app.post("/auth", response_class=RedirectResponse)
async def login(request: Request, response: Response, init_user: OAuth2PasswordRequestForm = Depends()):
    try:
        token = await generate_token(init_user)
    except HTTPException as e:
        flash_message(request, e.detail, "error")
    else:
        request.session["access_token"] = token["access_token"]
    response.status_code = 302
    return "/"


@login_app.get("/logout", response_class=RedirectResponse)
async def logout(request: Request, response: Response):
    request.session.pop("access_token", None)
    response.status_code = 302
    return "/"


@login_app.post("/register", dependencies=[Depends(require_admin)])
async def register(user: RegisterUser):
    with datastore.operation():
        accounts = datastore.get("accounts", {})
        if user.login in accounts:
            raise HTTPException(status_code=400, detail=locale["exceptions"]["account_already_exists"])

        salt = secrets["password_salt"]
        hasher = f"scrypt;{salt}"
        accounts[user.login] = dict(user.dict(), password=hash_password(user.password, hasher), salt=hasher)

    return {}
