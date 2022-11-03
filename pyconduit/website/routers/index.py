from fastapi import Depends, FastAPI
from starlette.requests import Request
from starlette.responses import HTMLResponse

from pyconduit.models.user import User
from pyconduit.website.decorators import get_current_user, make_template_data, templates

index_app = FastAPI()


@index_app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, user: None | User = Depends(get_current_user)):
    data = await make_template_data(request, user)

    if user:
        data["user"] = user
        return templates.TemplateResponse("modules/dashboard.html", data)
    else:
        return templates.TemplateResponse("modules/login.html", data)
