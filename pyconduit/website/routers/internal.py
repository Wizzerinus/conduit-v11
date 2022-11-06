import subprocess
from pathlib import Path

import anyio
from fastapi import Depends, FastAPI

from pyconduit.website.decorators import RequireScope

internal_app = FastAPI(dependencies=[Depends(RequireScope("technical_operations"))])


async def shutdown_task():
    await anyio.sleep(2)
    subprocess.run(["killall", "uvicorn"])


@internal_app.get("/update")
async def update_server():
    subprocess.run(["git", "pull"])
    # cron job will pick the server back up if it dies
    async with anyio.create_task_group() as tg:
        tg.start_soon(shutdown_task)
    return {}


@internal_app.get("/maintenance")
async def start_maintenance():
    Path("PIDlock").touch()
    async with anyio.create_task_group() as tg:
        tg.start_soon(shutdown_task)
    return {}
