from typing import TypedDict, List, Dict, Any, Callable, Optional

from langgraph.graph import StateGraph, END
import httpx
from duckduckgo_search import DDGS
import trafilatura

from app.memory.service import store_memory


class ResearchState(TypedDict, total=False):
    user_id: int
    query: str
    findings: List[Dict[str, Any]]  # {url, title, text}
    summary: str
    validated: bool
    recommendations: List[str]


async def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    # normalize
    return [{"title": r.get("title"), "url": r.get("href") or r.get("url") } for r in results]


async def fetch_and_extract(url: str, client: httpx.AsyncClient) -> str:
    try:
        r = await client.get(url, timeout=15)
        r.raise_for_status()
        extracted = trafilatura.extract(r.text, include_comments=False) or ""
        return extracted.strip()
    except Exception:
        return ""


async def research_agent(state: ResearchState, emit: Callable[[str, Dict[str, Any]], None], client: httpx.AsyncClient) -> ResearchState:
    query = state.get("query", "")
    hits = await web_search(query, max_results=5)
    emit("search", {"hits": hits})

    findings: List[Dict[str, Any]] = []
    for hit in hits:
        text = await fetch_and_extract(hit.get("url", ""), client)
        if not text:
            continue
        doc = {"title": hit.get("title"), "url": hit.get("url"), "text": text[:5000]}
        findings.append(doc)
        emit("extract", {"doc": {"title": doc["title"], "url": doc["url"], "chars": len(doc["text"])}})

    user_id = state.get("user_id") or 0
    if user_id:
        for f in findings:
            store_memory(user_id=user_id, content=f["text"], metadata={"type": "doc", "url": f["url"], "title": f["title"]})

    return {**state, "findings": findings}


def summarizer_agent(state: ResearchState, emit: Callable[[str, Dict[str, Any]], None]) -> ResearchState:
    # naive summary: first N sentences across docs
    texts = [f["text"] for f in state.get("findings", [])]
    joined = "\n\n".join(t[:1000] for t in texts)  # trim each
    summary = joined[:4000] if joined else "No content"
    emit("summary", {"length": len(summary)})
    return {**state, "summary": summary}


def validator_agent(state: ResearchState, emit: Callable[[str, Dict[str, Any]], None]) -> ResearchState:
    # trivial: validate if we have >=2 sources
    ok = len(state.get("findings", [])) >= 2 and bool(state.get("summary"))
    emit("validated", {"ok": ok})
    return {**state, "validated": ok}


def recommendation_agent(state: ResearchState, emit: Callable[[str, Dict[str, Any]], None]) -> ResearchState:
    q = state.get("query", "")
    recs = [
        f"Draft a focused brief on: {q}",
        "Queue follow-up search with site:gov and site:edu",
        "Store top 3 sources to memory and schedule periodic refresh",
    ]
    emit("recommendations", {"count": len(recs)})
    return {**state, "recommendations": recs}


def build_graph(emit: Callable[[str, Dict[str, Any]], None]):
    g = StateGraph(ResearchState)

    # wrap async nodes for langgraph sync graph via simple runner
    def research_node(s: ResearchState):
        import anyio
        async def run():
            async with httpx.AsyncClient(follow_redirects=True) as client:
                return await research_agent(s, emit, client)
        return anyio.run(run)

    g.add_node("research", research_node)
    g.add_node("summarize", lambda s: summarizer_agent(s, emit))
    g.add_node("validate", lambda s: validator_agent(s, emit))
    g.add_node("recommend", lambda s: recommendation_agent(s, emit))

    g.set_entry_point("research")
    g.add_edge("research", "summarize")
    g.add_edge("summarize", "validate")
    g.add_edge("validate", "recommend")
    g.add_edge("recommend", END)

    return g.compile()


