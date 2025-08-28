from fastapi import FastAPI, WebSocket, Depends, HTTPException, status, Request
from fastapi import Body
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
from .config import settings
from jwt import PyJWKClient, decode as jwt_decode, get_unverified_header
from typing import Dict, Any
import os
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, Session as DbSession, ResearchRun, RunEvent
from app.memory.service import store_memory, retrieve_memory
from app.agents.graph import build_graph
import anyio
import asyncio
from fastapi.responses import Response, JSONResponse
from datetime import datetime

app = FastAPI(title="AI Research Assistant Backend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.websocket("/ws/echo")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            await ws.send_text(data)
    except WebSocketDisconnect:
        pass

# --- Auth0 JWT verification ---
class AuthError(HTTPException):
    def __init__(self, detail: str, code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(status_code=code, detail=detail)


async def verify_jwt(request: Request) -> Dict[str, Any]:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise AuthError("Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid Authorization header")
    token = parts[1]

    domain = settings.auth0_domain or os.getenv("AUTH0_DOMAIN", "")
    audience = settings.auth0_audience or os.getenv("AUTH0_AUDIENCE", "")
    if not domain or not audience:
        raise AuthError("Auth0 env vars not configured")

    jwks_url = f"https://{domain}/.well-known/jwks.json"
    jwks_client = PyJWKClient(jwks_url)
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    try:
        payload = jwt_decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{domain}/",
        )
    except Exception as e:
        raise AuthError(f"Token validation failed: {e}")

    return payload


@app.get("/api/protected")
async def protected_route(payload: Dict[str, Any] = Depends(verify_jwt)):
    return {"message": "ok", "sub": payload.get("sub")}


def _get_or_create_user(db: Session, sub: str, email: str | None = None) -> int:
    user = db.query(User).filter(User.auth0_sub == sub).first()
    if user:
        return user.id
    user = User(auth0_sub=sub, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.id


def _get_or_create_default_session(db: Session, user_id: int) -> int:
    sess = db.query(DbSession).filter(DbSession.user_id == user_id).order_by(DbSession.id.asc()).first()
    if sess:
        return sess.id
    sess = DbSession(user_id=user_id, title="Default")
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess.id


@app.post("/api/memories")
async def api_store_memory(
    payload: Dict[str, Any] = Depends(verify_jwt),
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    user_id = _get_or_create_user(db, sub=payload.get("sub", ""), email=payload.get("email"))
    content: str = body.get("content", "")
    metadata: Dict[str, Any] | None = body.get("metadata")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    memory_id = store_memory(user_id=user_id, content=content, metadata=metadata)
    return {"id": memory_id}


@app.get("/api/memories/search")
async def api_search_memory(
    q: str,
    k: int = 5,
    payload: Dict[str, Any] = Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    user_id = _get_or_create_user(db, sub=payload.get("sub", ""), email=payload.get("email"))
    results = retrieve_memory(user_id=user_id, query=q, k=k)
    return {"results": results}


@app.get("/api/runs")
async def list_runs(
    payload: Dict[str, Any] = Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    user_id = _get_or_create_user(db, sub=payload.get("sub", ""), email=payload.get("email"))
    # List runs for the user's default session for now
    session_id = _get_or_create_default_session(db, user_id)
    runs = (
        db.query(ResearchRun)
        .filter(ResearchRun.session_id == session_id)
        .order_by(ResearchRun.id.desc())
        .all()
    )
    return {
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ]
    }


@app.get("/api/runs/{run_id}/events")
async def get_run_events(
    run_id: int,
    payload: Dict[str, Any] = Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    run = db.query(ResearchRun).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    events = (
        db.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.id.asc())
        .all()
    )
    return {
        "events": [
            {
                "event": e.type,
                "data": e.payload or {},
                "created_at": e.created_at.isoformat() if getattr(e, "created_at", None) else None,
            }
            for e in events
        ]
    }


@app.post("/api/research")
async def start_research(
    payload: Dict[str, Any] = Depends(verify_jwt),
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    user_id = _get_or_create_user(db, sub=payload.get("sub", ""), email=payload.get("email"))
    query = body.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    session_id = _get_or_create_default_session(db, user_id)
    run = ResearchRun(session_id=session_id, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": str(run.id), "query": query}


@app.websocket("/ws/research/{run_id}")
async def research_stream(ws: WebSocket, run_id: str, q: str = "demo", user_id: int = 0):
    await ws.accept()
    try:
        events_q: asyncio.Queue = asyncio.Queue()

        # DB context and run lookup
        db = next(get_db())
        run = db.query(ResearchRun).get(int(run_id))
        if not run:
            await ws.send_json({"event": "error", "data": {"detail": "run not found"}})
            return
        session = db.query(DbSession).get(run.session_id)
        user_id = user_id or (session.user_id if session else 0)

        def emit(event: str, data: Dict[str, Any]):
            # Called from sync graph thread: persist and enqueue
            try:
                db.add(RunEvent(run_id=run.id, type=event, payload=data))
                db.commit()
            except Exception:
                db.rollback()
            events_q.put_nowait({"event": event, "data": data})

        graph = build_graph(emit)

        async def sender():
            while True:
                msg = await events_q.get()
                if msg is None:
                    break
                await ws.send_json(msg)

        sender_task = asyncio.create_task(sender())

        # Run graph in a worker thread so we can stream concurrently
        state = {"user_id": user_id, "query": q}
        # Persist an event for start
        db.add(RunEvent(run_id=run.id, type="start", payload={"query": q}))
        db.commit()
        await asyncio.to_thread(graph.invoke, state)
        # Mark completed
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        db.add(RunEvent(run_id=run.id, type="done", payload={}))
        db.commit()
        db.close()
        await events_q.put(None)
        await sender_task
        await ws.send_json({"event": "done"})
    except WebSocketDisconnect:
        pass


@app.post("/api/export/pdf")
async def export_pdf(
    payload: Dict[str, Any] = Depends(verify_jwt),
    body: Dict[str, Any] = Body(...),
):
    title = body.get("title", "Research Report")
    sections = body.get("sections", [])  # [{heading, body}]
    # Try WeasyPrint first
    try:
        from weasyprint import HTML  # lazy import
        parts = [f"<h1 style='font-family: system-ui'>{title}</h1>"]
        for s in sections:
            h = s.get("heading", "")
            b = s.get("body", "")
            parts.append(f"<h2 style='font-family: system-ui'>{h}</h2>")
            parts.append(f"<p style='white-space: pre-wrap; font-family: system-ui'>{b}</p>")
        html = "".join(parts)
        pdf_bytes = HTML(string=html).write_pdf()
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=report.pdf"})
    except Exception:
        # Fallback to ReportLab (plain text layout)
        from io import BytesIO
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=LETTER)
        width, height = LETTER
        x = 1 * inch
        y = height - 1 * inch
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x, y, title[:90])
        y -= 0.5 * inch
        c.setFont("Helvetica", 10)
        for s in sections:
            h = (s.get("heading") or "")[:90]
            b = (s.get("body") or "")
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x, y, h)
            y -= 0.3 * inch
            c.setFont("Helvetica", 10)
            for line in b.splitlines():
                for chunk in [line[i:i+100] for i in range(0, len(line), 100)]:
                    if y < 1 * inch:
                        c.showPage()
                        y = height - 1 * inch
                        c.setFont("Helvetica", 10)
                    c.drawString(x, y, chunk)
                    y -= 0.2 * inch
            y -= 0.3 * inch
            if y < 1 * inch:
                c.showPage()
                y = height - 1 * inch
        c.showPage()
        c.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=report.pdf"})
