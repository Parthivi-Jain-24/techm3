from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import investigation

app = FastAPI(
    title="Continuous KYC — Autonomous Investigation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigation.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
