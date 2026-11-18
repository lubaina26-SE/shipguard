import os
import json
import psycopg2
import redis
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="ShipGuard API")

DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "shipguard")
DB_USER = os.getenv("DB_USER", "shipguard")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
REDIS_HOST = os.getenv("REDIS_HOST", "cache")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")


class Deployment(BaseModel):
    commit_sha: str
    image_tag: str
    tests_passed: bool
    vulnerabilities: int
    status: str  # success / failed / rolled_back


def get_db():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


def get_cache():
    return redis.Redis(host=REDIS_HOST, port=6379, socket_timeout=2)


@app.on_event("startup")
def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS deployments (
                id SERIAL PRIMARY KEY,
                commit_sha TEXT NOT NULL,
                image_tag TEXT NOT NULL,
                tests_passed BOOLEAN NOT NULL,
                vulnerabilities INT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )"""
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # /health will report the problem


@app.get("/health")
def health():
    db_ok, cache_ok = True, True
    try:
        get_db().close()
    except Exception:
        db_ok = False
    try:
        get_cache().ping()
    except Exception:
        cache_ok = False
    body = {"db": db_ok, "cache": cache_ok, "status": "ok" if db_ok else "unhealthy"}
    if not db_ok:
        raise HTTPException(status_code=503, detail=body)
    return body


@app.post("/api/deployments", status_code=201)
def add_deployment(d: Deployment, x_ingest_token: str = Header(default="")):
    if not INGEST_TOKEN or x_ingest_token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO deployments (commit_sha, image_tag, tests_passed, vulnerabilities, status) "
        "VALUES (%s, %s, %s, %s, %s)",
        (d.commit_sha, d.image_tag, d.tests_passed, d.vulnerabilities, d.status),
    )
    conn.commit()
    conn.close()
    try:
        get_cache().delete("stats")
    except Exception:
        pass
    return {"saved": True}


@app.get("/api/deployments")
def list_deployments():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT commit_sha, image_tag, tests_passed, vulnerabilities, status, created_at "
        "FROM deployments ORDER BY id DESC LIMIT 20"
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "commit_sha": r[0], "image_tag": r[1], "tests_passed": r[2],
            "vulnerabilities": r[3], "status": r[4], "created_at": str(r[5]),
        }
        for r in rows
    ]


@app.get("/api/stats")
def stats():
    try:
        cached = get_cache().get("stats")
        if cached:
            return json.loads(cached)
    except Exception:
        pass  # Redis down: still work, just uncached
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM deployments GROUP BY status")
    data = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    try:
        get_cache().setex("stats", 30, json.dumps(data))
    except Exception:
        pass
    return data