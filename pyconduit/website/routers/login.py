import hashlib
import hmac

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from pyconduit.models.user import ChangePasswordRequest, ConduitSettingsRequest, RegisterUser, User
from pyconduit.shared.datastore import datastore_manager
from pyconduit.shared.helpers import get_config
from pyconduit.website.decorators import RequireScope, create_access_token, find_user, flash_message, require_login

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


def default_hash(password: str) -> tuple[str, str]:
    salt = secrets["password_salt"]
    hasher = f"scrypt;{salt}"
    return hash_password(password, hasher), hasher


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
        flash_message(request, e.detail, "danger")
    else:
        request.session["access_token"] = token["access_token"]
    response.status_code = 302
    return "/"


@login_app.get("/logout", response_class=RedirectResponse)
async def logout(request: Request, response: Response):
    request.session.pop("access_token", None)
    response.status_code = 302
    return "/"


@login_app.post("/change-password")
async def change_password(user: User = Depends(require_login), password: ChangePasswordRequest = Body(...)):
    if len(password.new_password) < 6 or len(password.new_password) > 64:
        raise HTTPException(status_code=400, detail=locale["exceptions"]["invalid_password_length"])

    if password.new_password != password.new_password_confirm:
        raise HTTPException(status_code=400, detail=locale["exceptions"]["passwords_mismatch"])

    password_hash = hash_password(password.current_password, user.salt)
    if not hmac.compare_digest(password_hash, user.password):
        raise HTTPException(status_code=401, detail=locale["exceptions"]["invalid_credentials"])

    new_password, salt = default_hash(password.new_password)
    with datastore.operation():
        accounts = datastore.get("accounts", {})
        user_acc = accounts.get(user.login, {})
        user_acc["password"] = new_password
        user_acc["salt"] = salt
    return {"message": locale["pages"]["index"]["password_changed"]}


@login_app.post("/conduit-settings")
async def conduit_settings(user: User = Depends(require_login), settings: ConduitSettingsRequest = Body(...)):
    if not user.privileges.conduit_generation:
        raise HTTPException(status_code=400, detail=locale["exceptions"]["no_conduit_for_user"])

    password_hash = hash_password(settings.current_password, user.salt)
    if not hmac.compare_digest(password_hash, user.password):
        raise HTTPException(status_code=401, detail=locale["exceptions"]["invalid_credentials"])

    with datastore.operation():
        accounts = datastore.get("accounts", {})
        user_acc = accounts.get(user.login, {})
        user_acc["allow_conduit_view"] = settings.allow_conduit_view
    return {"message": locale["pages"]["index"]["conduit_settings_changed"]}


@login_app.post("/register", dependencies=[Depends(require_admin)])
async def register(user: RegisterUser):
    with datastore.operation():
        accounts = datastore.get("accounts", {})
        if user.login in accounts:
            raise HTTPException(status_code=400, detail=locale["exceptions"]["account_already_exists"])

        password_hash, salt = default_hash(user.password)
        accounts[user.login] = dict(user.dict(), password=password_hash, salt=salt)

    return {}
