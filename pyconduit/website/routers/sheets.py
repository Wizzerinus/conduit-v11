import logging

from fastapi import Body, Depends, FastAPI, HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.exceptions import WebSocketException

from pyconduit.models.bundle import BundleDocument
from pyconduit.models.latex import LatexRequest
from pyconduit.models.user import User
from pyconduit.shared.conduit_regeneration import regen_strategies
from pyconduit.shared.datastore import datastore_manager, deatomize
from pyconduit.shared.helpers import get_config
from pyconduit.shared.latex.converter import build_latex, generate_html
from pyconduit.website.decorators import (
    RequireScope,
    SocketManager,
    get_current_user,
    get_user_by_token,
    make_template_data,
    templates,
)

sheets_app = FastAPI()
datastore = datastore_manager.get("sheets")
socket_manager = SocketManager()
socket_context = {}
socket_current_sheet_per_user = {}
locale = get_config("localization")
logger = logging.getLogger("pyconduit.website.sheets")


@sheets_app.get("/editor", response_class=HTMLResponse)
async def index_page(request: Request, user: User = Depends(RequireScope("sheets_edit"))):
    data = await make_template_data(request, user)
    return templates.TemplateResponse("modules/sheet_editor.html", data)


@sheets_app.get("/viewer", response_class=HTMLResponse)
@sheets_app.get("/viewer/{sheet_id}", response_class=HTMLResponse)
async def index_page(request: Request, sheet_id: str = "", user: None | User = Depends(get_current_user)):
    data = await make_template_data(request, user)
    data["sheet"] = sheet_id
    return templates.TemplateResponse("modules/sheet_viewer.html", data)


@sheets_app.get("/list")
async def sheet_list():
    file_dict = [{"id": key, "name": value["latex"]["sheet_name"]} for key, value in datastore.sheets.items()]
    return list(reversed(file_dict))


@sheets_app.get("/content/{file_id}", response_class=PlainTextResponse)
async def get_latex_content(file_id: str):
    if file_id not in datastore.sheets:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))
    return datastore.sheets[file_id].latex.orig_doc


@sheets_app.post("/edit")
async def create_file(file_data: LatexRequest = Body(...), user: User = Depends(RequireScope("sheets_edit"))):
    new_conduit: None | dict = None
    warning = ""
    try:
        compiled_latex = build_latex(file_data.file_content)

        if compiled_latex.sheet_id in datastore.sheets:
            bundle_data = BundleDocument.parse_obj(deatomize(datastore.sheets[compiled_latex.sheet_id]))
        else:
            bundle_data = BundleDocument(latex=compiled_latex)

        if user.privileges.conduit_edit:
            if compiled_latex.conduit_strategy not in regen_strategies:
                raise ValueError("Invalid conduit strategy: %s" % compiled_latex.conduit_strategy)

            need_replace, warning = regen_strategies[compiled_latex.conduit_strategy](bundle_data, file_data)
            if need_replace:
                new_conduit = bundle_data.conduit.dict()

        html_content = generate_html(compiled_latex)
    except ValidationError:
        logger.exception("Latex invariant error")
        raise HTTPException(status_code=500, detail=locale["exceptions"]["latex_invariant_error"])
    except (TypeError, EOFError) as e:
        logger.exception("Latex syntax error")
        raise HTTPException(status_code=400, detail=locale["exceptions"]["latex_syntax_error"] % dict(message=e))
    except ValueError as e:
        logger.exception("Latex semantic error")
        raise HTTPException(status_code=422, detail=locale["exceptions"]["latex_semantic_error"] % dict(message=e))

    if file_data.expected_sheet and compiled_latex.sheet_id != file_data.expected_sheet:
        raise HTTPException(
            status_code=400,
            detail=locale["exceptions"]["latex_sheet_id_mismatch"]
            % dict(expected=file_data.expected_sheet, got=compiled_latex.sheet_id),
        )

    with datastore.operation():
        bundle = datastore.sheets.get(compiled_latex.sheet_id, {})
        if not bundle:
            await socket_manager.broadcast(
                {"action": "NewSheet", "id": compiled_latex.sheet_id, "name": compiled_latex.sheet_name}
            )
        bundle["latex"] = compiled_latex.dict()
        if new_conduit:
            bundle["conduit"] = new_conduit

    return {"success": True, "html_content": html_content, "sheet_id": compiled_latex.sheet_id, "warning": warning}


@sheets_app.get("/file/{file_id}", response_class=HTMLResponse)
async def read_file(file_id: str):
    if file_id not in datastore.sheets:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))

    try:
        bundle_document = BundleDocument.parse_obj(deatomize(datastore.sheets[file_id]))
    except ValidationError as e:
        logger.error("Invalid bundle document: %s", e)
        raise HTTPException(status_code=500, detail=locale["exceptions"]["latex_invariant_error"])

    if bundle_document.latex is None:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["no_latex_sheet"] % dict(filename=file_id))
    return generate_html(bundle_document.latex)


@sheets_app.delete("/{file_id}", dependencies=[Depends(RequireScope("sheets_edit"))])
async def delete_file(file_id: str):
    if file_id not in datastore.sheets:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))
    with datastore.sheets.operation():
        del datastore.sheets[file_id]
    await socket_manager.broadcast({"action": "DeleteSheet", "id": file_id})
    return {"success": True}


# Used to broadcast the currently edited file to prevent multiple users from editing the same file
@sheets_app.websocket("/editor")
async def editor_websocket(websocket: WebSocket):
    """
    Editor Websocket is used as a Mutex mechanism to prevent multiple people from editing the same file
    at the same time. However, the conduits are atomized and ARE useful to have multiple people editing,
    so here are the mechanics:
    * A file can be edited in either file mode or conduit mode.
    * Up to 1 editor in file mode, any number of editors in conduit mode.
    * Someone can also edit a virtual file named '__formulas', only in file mode.
    """

    try:
        user = await get_user_by_token(websocket.session["access_token"])
    except KeyError:
        await websocket.close(code=1008)
        return

    if user is None or (not user.privileges.sheets_edit and not user.privileges.conduit_edit):
        raise WebSocketDisconnect(code=1008)

    handle = await socket_manager.connect(websocket)

    try:
        file_dict = [
            {"id": key, "name": value["latex"]["sheet_name"], "has_conduit": "conduit" in value}
            for key, value in datastore.sheets.items()
        ]

        await websocket.send_json(
            {"action": "Init", "files": list(reversed(file_dict)), "open_sheets": socket_context, "handle": handle.id}
        )
        while True:
            sheet = await handle.receive_json()
            action, sheet_id = sheet.get("action"), sheet.get("id")
            if sheet_id is None:
                continue

            socket_context.setdefault(sheet_id, {"method": None, "users": {}})

            if action == "Open":
                current_sheet_id = socket_current_sheet_per_user.get(handle.id)
                if current_sheet_id is not None:
                    await socket_manager.broadcast({"action": "Close", "id": handle.id, "sheet_id": current_sheet_id})
                socket_context[sheet_id]["method"] = sheet.get("method", "sheet")
                socket_context[sheet_id]["users"][handle.id] = user.name
                socket_current_sheet_per_user[handle.id] = sheet_id
                await socket_manager.broadcast(
                    {"action": "Open", "sheet_id": sheet_id, "sheet": socket_context[sheet_id]}
                )
            elif action == "Close":
                socket_context[sheet_id]["users"].pop(handle.id, None)
                if not socket_context[sheet_id]["users"]:
                    socket_context.pop(sheet_id, None)
                socket_current_sheet_per_user.pop(handle.id, None)
                await socket_manager.broadcast({"action": "Close", "id": handle.id, "sheet_id": sheet_id})

    except (WebSocketDisconnect, WebSocketException):
        pass
    finally:
        socket_manager.disconnect(websocket)
        if formula_data := socket_context.get("__formulas", None):
            formula_data["users"].pop(handle.id, None)
            if not formula_data["users"]:
                socket_context.pop("__formulas", None)
        sheet = socket_current_sheet_per_user.pop(handle.id, None)
        if sheet is not None:
            socket_context[sheet]["users"].pop(handle.id, None)
            if not socket_context[sheet]["users"]:
                socket_context.pop(sheet, None)
            await socket_manager.broadcast({"action": "Close", "id": handle.id, "sheet_id": sheet})
