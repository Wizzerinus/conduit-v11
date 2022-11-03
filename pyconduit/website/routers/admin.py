from fastapi import Depends, FastAPI
from starlette.requests import Request
from starlette.responses import HTMLResponse

from pyconduit.models.user import User
from pyconduit.website.decorators import RequireScope, get_current_user, make_template_data, templates

admin_app = FastAPI(dependencies=[Depends(RequireScope("admin"))])


@admin_app.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, user: User = Depends(get_current_user)):
    data = await make_template_data(request, user)
    return templates.TemplateResponse("modules/admin.html", data)
