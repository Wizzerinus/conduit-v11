import os
import secrets
import subprocess
import sys
import time
from datetime import timedelta

import click
import yaml

from pyconduit.website.decorators import create_access_token


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
def create_admin():
    from pyconduit.models.user import Privileges, RegisterUser
    from pyconduit.shared.datastore import datastore_manager
    from pyconduit.shared.init import init_databases
    from pyconduit.website.routers.login import register

    generate_salts.callback()
    init_databases()

    datastore = datastore_manager.get("accounts")
    username = input("Username: ")
    with datastore.operation():
        accounts = datastore.accounts
        if username in accounts:
            del accounts[username]

    password = input("Password: ")
    privileges = Privileges(
        admin=True, conduit_edit=True, sheets_edit=True, conduit_generation=False, formula_edit=True
    )
    register(RegisterUser(login=username, password=password, name="Administrator", privileges=privileges))


@cli.command()
def backup_database():
    backup_folder = "backups/"
    os.makedirs(backup_folder, exist_ok=True)
    current_backups = os.listdir(backup_folder)
    if len(current_backups) > 5:
        current_backups.sort()
        os.remove(backup_folder + current_backups[0])

    new_path = backup_folder + "backup_" + str(int(time.time()))
    subprocess.run(["cp", "-r", "json-db", new_path])


@cli.command()
@click.argument("sheet_id")
@click.argument("user_order_file")
@click.argument("conduit_tsv")
def import_conduits(sheet_id: str, user_order_file: str, conduit_tsv: str):
    from pyconduit.shared.datastore import datastore_manager

    accounts = datastore_manager.get("accounts")
    with open(user_order_file) as f:
        user_order = [line.strip() for line in f]

    username_dict = {x.name: x.login for x in accounts.accounts.values() if not x.virtual}
    user_order = [username_dict[x] for x in user_order]

    with open(conduit_tsv) as f:
        conduit_data = [line.replace(" ", "").replace("\n", "").split("\t") for line in f]

    with datastore_manager.get("sheets").operation() as ds:
        sheets = ds.sheets
        if sheet_id not in sheets:
            click.echo(f"Sheet {sheet_id} not found")
            return

        sheet = sheets[sheet_id]
        if not sheet.conduit:
            click.echo(f"Sheet {sheet_id} has no conduit")
            return

        conduit = sheet.conduit
        for user_login, conduit_data in zip(user_order, conduit_data):
            conduit.content[user_login] = conduit_data + [""] * (len(conduit.problem_names) - len(conduit_data))


@cli.command()
def create_techops_bot():
    from pyconduit.models.user import Privileges
    from pyconduit.shared.datastore import datastore_manager

    datastore = datastore_manager.get("accounts")

    username = "_techops_bot"
    privileges = Privileges(conduit_generation=False, technical_operations=True)
    with datastore.operation():
        accounts = datastore.accounts
        if username in accounts:
            del accounts[username]

        accounts[username] = dict(
            login=username, password="", salt="nologin;", name="Techops Bot", privileges=privileges.dict(), virtual=True
        )

    token = create_access_token(dict(sub=f"user:{username}"), expire=timedelta(hours=8760))
    print(f"Access token = '{token}'")


if __name__ == "__main__":
    cli()
