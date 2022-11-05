import os

from fastapi import Body, Depends, FastAPI, HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse

from pyconduit.models.user import BulkRegister, Privileges, User, UserSensitive
from pyconduit.shared.datastore import datastore_manager
from pyconduit.shared.helpers import get_config, partition, transform_to_login
from pyconduit.website.decorators import RequireScope, get_current_user, make_template_data, templates
from pyconduit.website.routers.login import default_hash

admin_app = FastAPI(dependencies=[Depends(RequireScope("admin"))])
accounts = datastore_manager.get("accounts")
locale = get_config("localization")


def get_key(user: UserSensitive) -> int:
    if user.privileges.admin:
        return 0
    if user.privileges.conduit_generation:
        return 2
    if user.privileges.conduit_edit or user.privileges.sheets_edit:
        return 1
    return 3


@admin_app.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, user: User = Depends(get_current_user)):
    data = await make_template_data(request, user)
    return templates.TemplateResponse("modules/admin.html", data)


@admin_app.get("/users")
async def get_users():
    all_users = accounts.accounts
    user_list = [UserSensitive.parse_obj(user) for user in all_users.values()]
    admins, teachers, students, misc = partition(user_list, 3, get_key)
    users = [
        {"name": locale["user_category"]["admin"], "users": admins},
        {"name": locale["user_category"]["teacher"], "users": teachers},
        {"name": locale["user_category"]["student"], "users": students},
    ]
    users = [user for user in users if user["users"]]
    return {"partition": users}


@admin_app.post("/update-user")
async def update_privileges(user_data: UserSensitive = Body(...)):
    with accounts.operation():
        all_users = accounts.accounts
        old_data = dict(all_users.get(user_data.login, {}))
        old_data.update(user_data.dict())
        all_users[user_data.login] = old_data
    return {"success": True}


@admin_app.post("/reset-password/{login}")
async def reset_password(login: str):
    if login not in accounts.accounts:
        raise HTTPException(status_code=404, detail="User not found")

    new_password = os.urandom(10).hex()
    password, salt = default_hash(new_password)
    with accounts.operation():
        accounts.accounts[login].password = password
        accounts.accounts[login].salt = salt
    return {"success": True, "password": new_password}


@admin_app.post("/create-users", response_class=PlainTextResponse)
def create_users(users: BulkRegister = Body(...)):
    # using sync here to ensure scrypt stuff is done in a separate thread as scrypt is slow
    account_dict = accounts.accounts
    usernames = users.users.split("\n")
    if not users.teachers:
        privilege_doc = Privileges()
    else:
        privilege_doc = Privileges(conduit_generation=False, conduit_edit=True, sheets_edit=True)

    users: list[dict] = []
    return_text = []
    for user in usernames:
        user = user.strip()
        if not user:
            continue

        login = transform_to_login(user)
        if login in account_dict:
            return_text.append(f"{user} (already exists)")
            continue

        password_base = os.urandom(10).hex()
        password, salt = default_hash(password_base)
        return_text.append(f"{user} (login: {login}, password: {password_base})")
        users.append(User(login=login, password=password, salt=salt, name=user, privileges=privilege_doc).dict())

    with accounts.operation():
        for user in users:
            account_dict[user["login"]] = user

    return "\n".join(return_text)
