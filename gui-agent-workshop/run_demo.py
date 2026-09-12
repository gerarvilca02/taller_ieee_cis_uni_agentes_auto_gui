import argparse
import asyncio
import json
import os
import threading
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from automation.agent import DEFAULT_GOAL, run_agent
from automation.session_log import generate_session_id


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


class SessionRequest(BaseModel):
    goal: str = Field(min_length=10, max_length=2000)
    mode: str = "hybrid"
    model: str = "gpt-5.6-luna"
    headless: bool = False
    delay: int = Field(default=180, ge=0, le=1500)
    max_steps: int = Field(default=30, ge=1, le=30)


class SessionHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}

    def create(self, session_id, request):
        with self.lock:
            self.sessions[session_id] = {
                "session_id": session_id,
                "status": "starting",
                "request": request,
                "events": [],
            }

    def publish(self, session_id, event):
        enriched = dict(event)
        if enriched.get("screenshot"):
            enriched["screenshot_url"] = f"/artifacts/{session_id}/screenshots/{Path(enriched['screenshot']).name}"
        with self.lock:
            session = self.sessions[session_id]
            session["events"].append(enriched)
            if event["type"] == "session_started":
                session["status"] = "running"
            if event["type"] == "session_completed":
                session["status"] = "completed"
            if event["type"] == "session_error":
                session["status"] = "error"

    def snapshot(self, session_id):
        with self.lock:
            if session_id not in self.sessions:
                return None
            session = self.sessions[session_id]
            return {
                "session_id": session_id,
                "status": session["status"],
                "request": session["request"],
                "events": list(session["events"]),
            }


hub = SessionHub()
app = FastAPI(title="FlowDesk Agent Console")
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACTS)), name="artifacts")


@app.get("/")
def agent_console():
    return FileResponse(DIST / "agent.html")


@app.get("/target")
def target_gui():
    return FileResponse(DIST / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "default_goal": DEFAULT_GOAL}


@app.post("/api/sessions")
def create_session(request: SessionRequest):
    if request.mode not in {"dom", "screenshot", "hybrid"}:
        raise HTTPException(status_code=422, detail="El modo debe ser dom, screenshot o hybrid")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=400, detail="Falta OPENAI_API_KEY en el archivo .env")
    session_id = generate_session_id("agent")
    request_data = request.model_dump()
    hub.create(session_id, request_data)
    port = int(os.getenv("FLOWDESK_PORT", "8000"))
    target_url = os.getenv("GUI_URL", f"http://127.0.0.1:{port}/target")

    def worker():
        try:
            run_agent(
                url=target_url,
                mode=request.mode,
                goal=request.goal,
                model=request.model,
                max_steps=request.max_steps,
                headless=request.headless,
                delay=request.delay,
                session_id=session_id,
                event_callback=lambda event: hub.publish(session_id, event),
                artifacts_root=str(ARTIFACTS),
            )
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True, name=session_id).start()
    return {
        "session_id": session_id,
        "status": "starting",
        "events_url": f"/api/sessions/{session_id}/events",
        "memory_url": f"/api/sessions/{session_id}/memory",
    }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = hub.snapshot(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


@app.get("/api/sessions/{session_id}/memory")
def get_memory(session_id: str):
    memory_path = ARTIFACTS / session_id / "memory.json"
    if not memory_path.is_file():
        raise HTTPException(status_code=404, detail="La memoria todavía no está disponible")
    return FileResponse(memory_path, filename=f"{session_id}-memory.json", media_type="application/json")


@app.get("/api/sessions/{session_id}/events")
async def stream_events(session_id: str, request: Request):
    if not hub.snapshot(session_id):
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    async def generate():
        index = 0
        while True:
            if await request.is_disconnected():
                break
            session = hub.snapshot(session_id)
            events = session["events"]
            while index < len(events):
                yield f"data: {json.dumps(events[index], ensure_ascii=False)}\n\n"
                index += 1
            if session["status"] in {"completed", "error"} and index >= len(events):
                break
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Servidor local de FlowDesk Lab")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    os.environ["FLOWDESK_PORT"] = str(args.port)
    print(f"Consola del agente disponible en http://{args.host}:{args.port}")
    print(f"GUI objetivo disponible en http://{args.host}:{args.port}/target")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
