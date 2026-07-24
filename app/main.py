from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.database import init_db, get_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Deploy Tracker API",
    description="Registra despliegues y calcula metricas de entrega",
    version="1.0.0",
    lifespan=lifespan,
)


class DeploymentIn(BaseModel):
    service: str
    version: str
    status: Literal["success", "failed"]


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/deployments", status_code=201)
def create_deployment(deployment: DeploymentIn):
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO deployments (service, version, status, timestamp) VALUES (?, ?, ?, ?)",
            (deployment.service, deployment.version, deployment.status, timestamp),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "service": deployment.service,
            "version": deployment.version,
            "status": deployment.status,
            "timestamp": timestamp,
        }


@app.get("/deployments")
def list_deployments(service: str | None = None):
    query = "SELECT * FROM deployments"
    params = ()
    if service:
        query += " WHERE service = ?"
        params = (service,)
    query += " ORDER BY id DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


@app.get("/metrics")
def get_metrics():
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM deployments").fetchone()["c"]

        if total == 0:
            return {
                "total_deployments": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": None,
                "services": [],
            }

        successful = conn.execute(
            "SELECT COUNT(*) AS c FROM deployments WHERE status = 'success'"
        ).fetchone()["c"]

        services = conn.execute(
            "SELECT service, COUNT(*) AS deployments FROM deployments GROUP BY service"
        ).fetchall()

        return {
            "total_deployments": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": round(successful / total * 100, 2),
            "services": [dict(row) for row in services],
        }
