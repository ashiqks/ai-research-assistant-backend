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
from app.db.models import User
from app.memory.service import store_memory, retrieve_memory
from app.agents.graph import build_graph
import anyio

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

    domain = os.getenv("AUTH0_DOMAIN", "")
    audience = os.getenv("AUTH0_AUDIENCE", "")
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
    # Return ephemeral run id for now (could persist)
    run_id = f"run-{user_id}-{abs(hash(query))%100000}"
    return {"run_id": run_id, "query": query}


@app.websocket("/ws/research/{run_id}")
async def research_stream(ws: WebSocket, run_id: str, q: str = "demo", user_id: int = 0):
    await ws.accept()
    try:
        async def send(event: str, data: Dict[str, Any]):
            await ws.send_json({"event": event, "data": data})

        graph = build_graph(lambda e, d: anyio.from_thread.run(send, e, d))
        # Use provided query and user_id
        state = {"user_id": user_id, "query": q}
        graph.invoke(state)
        await ws.send_json({"event": "done"})
    except WebSocketDisconnect:
        pass
