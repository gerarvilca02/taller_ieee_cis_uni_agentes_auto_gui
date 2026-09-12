import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def generate_session_id(prefix="agent"):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


class SessionRecorder:
    def __init__(self, session_id, kind, mode, goal, model=None, artifacts_root="artifacts", callback=None):
        self.session_id = session_id
        self.directory = Path(artifacts_root) / session_id
        self.screenshots_dir = self.directory / "screenshots"
        self.memory_path = self.directory / "memory.json"
        self.callback = callback
        self.lock = threading.Lock()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.document = {
            "schema_version": 1,
            "session_id": session_id,
            "kind": kind,
            "mode": mode,
            "model": model,
            "goal": goal,
            "status": "running",
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "plan": None,
            "response_ids": [],
            "events": [],
        }
        self._write()

    def screenshot_path(self, index):
        return self.screenshots_dir / f"observacion_{index:02d}.png"

    def emit(self, event_type, **payload):
        with self.lock:
            event = {
                "sequence": len(self.document["events"]) + 1,
                "timestamp": utc_now(),
                "type": event_type,
                **payload,
            }
            self.document["events"].append(event)
            self.document["updated_at"] = event["timestamp"]
            if event_type == "plan":
                self.document["plan"] = payload
            if event_type == "response":
                self.document["response_ids"].append(payload["response_id"])
            if event_type == "session_completed":
                self.document["status"] = "completed"
                self.document["finished_at"] = event["timestamp"]
            if event_type == "session_error":
                self.document["status"] = "error"
                self.document["finished_at"] = event["timestamp"]
            self._write()
        if self.callback:
            self.callback(event)
        return event

    def _write(self):
        temporary_path = self.memory_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(self.document, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(self.memory_path)
