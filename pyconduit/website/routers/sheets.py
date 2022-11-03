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
from pyconduit.shared.datastore import datastore_manager, deatomize
from pyconduit.shared.helpers import get_config
from pyconduit.shared.latex.converter import build_latex, generate_html
from pyconduit.website.decorators import RequireScope, SocketManager, get_current_user, get_user_by_token, \
    make_template_data, templates

sheets_app = FastAPI()
datastore = datastore_manager.get("sheets")
socket_manager = SocketManager()
socket_context = {}
locale = get_config("localization")
logger = logging.getLogger("pyconduit.website.sheets")


@sheets_app.get("/editor", response_class=HTMLResponse)
async def index_page(request: Request, user: User = Depends(RequireScope("sheets_edit"))):
    data = await make_template_data(request, user)
    return templates.TemplateResponse("modules/sheet_editor.html", data)


@sheets_app.get("/viewer", response_class=HTMLResponse)
async def index_page(request: Request, user: None | User = Depends(get_current_user)):
    data = await make_template_data(request, user)
    return templates.TemplateResponse("modules/sheet_viewer.html", data)


@sheets_app.get("/list")
async def sheet_list():
    file_dict = [{"id": key, "name": value["latex"]["sheet_name"]} for key, value in datastore.items()]
    return list(reversed(file_dict))


@sheets_app.get("/content/{file_id}", response_class=PlainTextResponse)
async def get_latex_content(file_id: str):
    if file_id not in datastore:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))
    return datastore[file_id]["latex"]["orig_doc"]


@sheets_app.post("/edit", dependencies=[Depends(RequireScope("sheets_edit"))])
async def create_file(file_data: LatexRequest = Body(...)):
    try:
        compiled_latex = build_latex(file_data.file_content)
        html_content = generate_html(compiled_latex)
    except ValidationError:
        raise HTTPException(status_code=500, detail=locale["exceptions"]["latex_invariant_error"])
    except (TypeError, EOFError) as e:
        raise HTTPException(status_code=400, detail=locale["exceptions"]["latex_syntax_error"] % dict(message=e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=locale["exceptions"]["latex_semantic_error"] % dict(message=e))

    if file_data.expected_sheet and compiled_latex.sheet_id != file_data.expected_sheet:
        raise HTTPException(
            status_code=400,
            detail=locale["exceptions"]["latex_sheet_id_mismatch"] % dict(
                expected=file_data.expected_sheet, got=compiled_latex.sheet_id
            )
        )

    with datastore.operation():
        bundle = datastore.get(compiled_latex.sheet_id, {})
        if not bundle:
            await socket_manager.broadcast(
                {"action": "NewSheet", "id": compiled_latex.sheet_id, "name": compiled_latex.sheet_name}
            )
        bundle["latex"] = compiled_latex.dict()

    return {"success": True, "html_content": html_content, "sheet_id": compiled_latex.sheet_id}


@sheets_app.get("/file/{file_id}", response_class=HTMLResponse)
async def read_file(file_id: str):
    if file_id not in datastore:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))

    try:
        bundle_document = BundleDocument.parse_obj(deatomize(datastore[file_id]))
    except ValidationError as e:
        logger.error("Invalid bundle document: %s", e)
        raise HTTPException(status_code=500, detail=locale["exceptions"]["latex_invariant_error"])

    if bundle_document.latex is None:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["no_latex_sheet"] % dict(filename=file_id))
    return generate_html(bundle_document.latex)


@sheets_app.delete("/{file_id}", dependencies=[Depends(RequireScope("sheets_edit"))])
async def delete_file(file_id: str):
    if file_id not in datastore:
        raise HTTPException(status_code=404, detail=locale["exceptions"]["file_not_found"] % dict(filename=file_id))
    with datastore.operation():
        del datastore[file_id]
    await socket_manager.broadcast({"action": "DeleteSheet", "id": file_id})
    return {"success": True}


# Used to broadcast the currently edited file to prevent multiple users from editing the same file
@sheets_app.websocket("/editor")
async def editor_websocket(websocket: WebSocket):
    user = await get_user_by_token(websocket.session["access_token"])

    if user is None or not user.privileges.sheets_edit:
        raise WebSocketDisconnect(code=1008)

    handle = await socket_manager.connect(websocket)

    try:
        file_dict = [{"id": key, "name": value["latex"]["sheet_name"]} for key, value in datastore.items()]
        await websocket.send_json(
            {"action": "Init", "files": list(reversed(file_dict)), "open_sheets": socket_context}
        )
        while True:
            sheet = await handle.receive_text()
            await socket_manager.broadcast(
                {"client": user.name, "cid": handle.id, "sheet": sheet, "action": "SetSheet"},
                exclusions={websocket}
            )
            if sheet:
                socket_context[handle.id] = {"sheet": sheet, "client": user.name}
            else:
                socket_context.pop(handle.id, None)
    except (WebSocketDisconnect, WebSocketException):
        pass
    finally:
        socket_manager.disconnect(websocket)
        await socket_manager.broadcast({"client": user.name, "cid": handle.id, "sheet": None, "action": "SetSheet"})
        socket_context.pop(handle.id, None)
