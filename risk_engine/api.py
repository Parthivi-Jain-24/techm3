from __future__ import annotations

from pathlib import Path
from typing import Any

from risk_engine import RiskEngine
from risk_engine.governance import GovernanceStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app() -> Any:
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with: pip install -e .[api]") from exc

    app = FastAPI(title="Continuous KYC Governance Console", version="0.4.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:8001",
            "http://localhost:8001",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = RiskEngine()
    governance = GovernanceStore(engine=engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/risk/assess")
    def assess(payload: dict[str, Any]) -> dict[str, Any]:
        return engine.assess(payload).to_dict()

    @app.get("/governance/summary")
    def governance_summary() -> dict[str, Any]:
        return governance.summary()

    @app.get("/governance/cases")
    def governance_cases(role: str = Query(default="compliance")) -> list[dict[str, Any]]:
        return governance.cases(role)

    @app.get("/governance/cases/{customer_id}")
    def governance_case(customer_id: str, role: str = Query(default="compliance")) -> dict[str, Any]:
        try:
            return governance.case_detail(customer_id, role)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/governance/cases/{customer_id}/live-news")
    def governance_live_news(customer_id: str) -> dict[str, Any]:
        try:
            return governance.live_news(customer_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/governance/cases/{customer_id}/review")
    def governance_review(customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return governance.submit_review(customer_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/governance/cases/{customer_id}/sar-signoff")
    def governance_sar_signoff(customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return governance.signoff_sar(customer_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/governance/audit")
    def governance_audit() -> list[dict[str, Any]]:
        return governance.audit()

    if FRONTEND_DIR.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        def dashboard() -> Any:
            return FileResponse(FRONTEND_DIR / "index.html")

        @app.get("/{asset_name}", include_in_schema=False)
        def frontend_asset(asset_name: str) -> Any:
            asset_path = FRONTEND_DIR / asset_name
            if asset_path.exists() and asset_path.is_file():
                return FileResponse(asset_path)
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()