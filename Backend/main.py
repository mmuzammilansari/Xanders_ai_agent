from contextlib import asynccontextmanager

from fastapi import FastAPI
from core.database.sqlite import init_database
from fastapi.middleware.cors import CORSMiddleware
# from fastapi import Request
from modules.middlewares.authenticate import api_authenticate_key

from modules.ai_agent.router import ai_agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "https://platform.ecochamp.app",
    "https://ecochamp.app",
]

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(api_authenticate_key)
app.include_router(
    ai_agent_router,
    tags=["AI Module"]
)

@app.get("/", status_code=200)
async def root():
    return {
        "message": "You're at Xander's backend."
    }
