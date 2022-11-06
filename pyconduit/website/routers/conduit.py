import logging

from fastapi import Body, Depends, FastAPI, HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse

from pyconduit.models.bundle import BundleDocument
from pyconduit.models.conduit import Conduit, ConduitContent
from pyconduit.models.user import User, UserSensitive
from pyconduit.shared.datastore import datastore_manager, deatomize
from pyconduit.shared.formulas import execute_formula
from pyconduit.shared.helpers import get_config
from pyconduit.website.decorators import RequireScope, make_template_data, templates
from pyconduit.website.routers.sheets import socket_manager

conduit_app = FastAPI()
datastore = datastore_manager.get("sheets")
accounts = datastore_manager.get("accounts")
locale = get_config("localization")
logger = logging.getLogger("pyconduit.website.conduit")


def calculate_with_formula(
    conduit: Conduit, file_id: str, filename: str, users: list[UserSensitive], formula: str
) -> ConduitContent:
    conduit_document = ConduitContent(
        id=file_id,
        conduit=dict(conduit.dict()),
        users=users,
        name=filename,
        real_indices=list(range(len(conduit.problem_names))),
    )
    try:
        data, answer = execute_formula(conduit_document, formula)
        if "Error" in answer or "Exception" in answer:
            logger.warning(answer)
            conduit_document.formula_error = answer
        else:
            conduit_document = ConduitContent.parse_obj(data)
            real_indices = []
            for problem in conduit_document.conduit.problem_names:
                try:
                    real_indices.append(conduit.problem_names.index(problem))
                except ValueError:
                    real_indices.append(-1)
            conduit_document.real_indices = real_indices
    except RuntimeError as e:
        logger.warning("Failed to execute formula for '%s': %s", file_id, e)
        conduit_document.formula_error = str(e)
    return conduit_document


def get_all_users(conduit: Conduit) -> list[UserSensitive]:
    users = {
        login: UserSensitive.parse_obj(deatomize(account))
        for login, account in accounts.accounts.items()
        if account["privileges"]["conduit_generation"]
    }

    for login in conduit.content.keys():
        if login not in users:
            if login in accounts.accounts:
                username = accounts.accounts[login].name
            else:
                username = login
            users[login] = UserSensitive(login=login, name=username)

    return sorted(users.values(), key=lambda user: user.name)


@conduit_app.get("/editor", response_class=HTMLResponse)
async def conduit_editor(request: Request, user: User = Depends(RequireScope("conduit_edit"))):
    data = await make_template_data(request, user)
    return templates.TemplateResponse("modules/conduit_editor.html", data)


# This one is sync because execute_formula can be quite slow if a malicious person puts an infinite loop there
@conduit_app.get("/content/{file_id}", dependencies=[Depends(RequireScope("conduit_edit"))])
def get_file(file_id: str) -> ConduitContent:
    if file_id not in datastore.sheets:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))

    try:
        document = BundleDocument.parse_obj(deatomize(datastore.sheets[file_id]))
    except ValidationError:
        logger.exception("Failed to parse document '%s'", file_id)
        raise HTTPException(status_code=500, detail=locale["exceptions"]["file_corrupted"] % dict(filename=file_id))

    if not document.conduit:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["no_conduit"] % dict(filename=file_id))

    users = get_all_users(document.conduit)
    for user in users:
        if user.login not in document.conduit.content:
            document.conduit.content[user.login] = ["" for _ in range(len(document.conduit.problem_names))]

    filename = document.latex.sheet_name if document.latex else file_id
    formula = datastore.formulas
    return calculate_with_formula(document.conduit, file_id, filename, users, formula)


@conduit_app.get("/formulas", dependencies=[Depends(RequireScope("formula_edit"))])
async def get_conduit_formulas() -> str:
    return datastore.formulas


@conduit_app.post("/formulas", dependencies=[Depends(RequireScope("formula_edit"))])
async def set_conduit_formulas(file_content: str = Body(..., embed=True)):
    with datastore.operation():
        datastore.formulas = file_content


@conduit_app.post("/edit/{file_id}", dependencies=[Depends(RequireScope("conduit_edit"))])
async def save_file(file_id: str, unsaved_changes: dict = Body(..., embed=True)):
    if file_id not in datastore.sheets:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))

    if "conduit" not in datastore.sheets[file_id]:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["no_conduit"] % dict(filename=file_id))

    try:
        with datastore.operation():
            conduit_data = datastore.sheets[file_id].conduit
            for username, problems in unsaved_changes.items():
                if not problems:
                    continue

                user_row = conduit_data.content.get(username, ["" for _ in conduit_data.problem_names])
                for problem, value in problems.items():
                    user_row[int(problem)] = value
    except ValueError:
        logger.exception("Failed to save conduit '%s'", file_id)
        raise HTTPException(status_code=400, detail=locale["exceptions"]["invalid_conduit_data"])
    else:
        conduit = Conduit.parse_obj(deatomize(conduit_data))
        formula = datastore.formulas
        users = get_all_users(conduit)
        conduit_doc = calculate_with_formula(
            conduit, file_id, datastore.sheets[file_id].latex.sheet_name, users, formula
        )

        # now we need to get any virtual rows/columns
        real_problem_names = set(conduit.problem_names)
        virtual_rows = {}
        real_rows = {}
        for user_login, row in conduit_doc.conduit.content.items():
            if user_login.startswith("_"):
                virtual_rows[user_login] = row
            else:
                data = []
                for problem_name, value in zip(conduit_doc.conduit.problem_names, row):
                    if problem_name not in real_problem_names:
                        data.append(value)
                real_rows[user_login] = data

        await socket_manager.broadcast(
            {
                "action": "ConduitUpdate",
                "changes": unsaved_changes,
                "styles": conduit_doc.styles,
                "virtual_rows": virtual_rows,
                "real_rows": real_rows,
            }
        )
    return {"success": True}
