import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.query_router import query_router
from app.core.context import request_id_ctx_var
from app.core.lifespan import lifespan

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(query_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id_ctx_var.set(str(uuid.uuid4()))
    response = await call_next(request)
    return response
