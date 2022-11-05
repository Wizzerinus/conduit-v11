import asyncio
import secrets
import subprocess
import sys
from functools import wraps

import click
import yaml


def asynchronous(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.group()
def cli():
    pass


@cli.command()
def generate_salts():
    password_salt = secrets.token_hex(16)
    session_salt = secrets.token_hex(24)
    jwt_salt = secrets.token_hex(24)
    with open("config/secrets.yml", "w") as f:
        yaml.dump({"password_salt": password_salt, "session_salt": session_salt, "jwt_salt": jwt_salt}, f)


@cli.command()
def cleanup():
    subprocess.run([sys.executable, "-m", "isort", "-l", "120", "--profile", "black", "."])
    subprocess.run([sys.executable, "-m", "black", "-l", "120", "."])


@cli.command()
@asynchronous
async def create_admin():
    from pyconduit.models.user import Privileges, RegisterUser
    from pyconduit.shared.datastore import datastore_manager
    from pyconduit.website.routers.login import register

    datastore = datastore_manager.get("accounts")
    username = input("Username: ")
    with datastore.operation():
        accounts = datastore.accounts
        if username in accounts:
            del accounts[username]

    password = input("Password: ")
    privileges = Privileges(admin=True, conduit_edit=True, sheets_edit=True, conduit_generation=False)
    await register(RegisterUser(login=username, password=password, name="Administrator", privileges=privileges))


if __name__ == "__main__":
    cli()
