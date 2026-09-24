from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app import auth
from app.db import init_db
from app.routers import analytics, budgets, categories, export, goals, imports, places, receipts, recurring, transactions, wallets

STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TracepAI", lifespan=lifespan)

api = APIRouter(prefix="/api")
for module in (auth, transactions, wallets, categories, budgets, goals, recurring, analytics, places, receipts, imports, export):
    api.include_router(module.router)
app.include_router(api)

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
