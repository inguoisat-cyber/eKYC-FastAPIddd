import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .api import purge_expired, router
from .config import ROOT
from .db import Base, engine
from .face import face

log = logging.getLogger("ekyc")


async def _janitor():
    while True:
        await asyncio.sleep(600)
        try:
            await asyncio.to_thread(purge_expired)
        except Exception:
            log.exception("Dọn phiên hết hạn thất bại")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    await asyncio.to_thread(face.load)  # nạp model xong mới nhận request
    task = asyncio.create_task(_janitor())
    yield
    task.cancel()


app = FastAPI(title="eKYC", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)  # frontend cùng origin nên không cần CORS
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "OK"}


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="web")  # phải đặt cuối
