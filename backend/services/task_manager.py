"""
TaskManager — threading + SSE-based task execution.
Each task runs in a background thread; clients subscribe via SSE.
"""

import json
import time
import threading
import uuid
from datetime import datetime, timezone
from queue import Queue, Empty


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._queues: dict[str, list[Queue]] = {}
        self._lock = threading.Lock()

    # ─── Public: create & run ─────────────────────────────────────────────────

    def create_task(self, task_type: str, meta: dict | None = None) -> str:
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "status": "pending",
                "progress": 0,
                "message": "",
                "result": None,
                "error": None,
                "meta": meta or {},
                "created_at": _utcnow_iso(),
                "updated_at": _utcnow_iso(),
            }
            self._queues[task_id] = []
        return task_id

    def run(self, task_id: str, fn, *args, **kwargs):
        """Start fn(*args, **kwargs) in a background thread."""
        def _run():
            self._update(task_id, status="running", progress=0)
            try:
                result = fn(task_id, *args, **kwargs)
                self._update(task_id, status="completed", progress=100, result=result)
            except Exception as e:
                self._update(task_id, status="failed", error=str(e))

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    # ─── Public: status & SSE ────────────────────────────────────────────────

    def get(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def push_log(self, task_id: str, line: str, progress: int | None = None):
        """Called from inside a task to emit a log line."""
        update = {"message": line}
        if progress is not None:
            update["progress"] = progress
        self._update(task_id, **update)

    def subscribe(self, task_id: str) -> Queue:
        q: Queue = Queue(maxsize=200)
        with self._lock:
            if task_id not in self._queues:
                self._queues[task_id] = []
            self._queues[task_id].append(q)
        return q

    def unsubscribe(self, task_id: str, q: Queue):
        with self._lock:
            if task_id in self._queues:
                try:
                    self._queues[task_id].remove(q)
                except ValueError:
                    pass

    def sse_stream(self, task_id: str):
        """Generator: yields SSE-formatted lines until task is terminal."""
        task = self.get(task_id)
        if task is None:
            yield _sse({"error": "task not found"})
            return

        # Send current state immediately
        yield _sse(task)

        if task["status"] in ("completed", "failed"):
            return

        q = self.subscribe(task_id)
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield _sse(event)
                    if event.get("status") in ("completed", "failed"):
                        break
                except Empty:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                    # Check if task finished while we were waiting
                    current = self.get(task_id)
                    if current and current["status"] in ("completed", "failed"):
                        yield _sse(current)
                        break
        finally:
            self.unsubscribe(task_id, q)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _update(self, task_id: str, **fields):
        with self._lock:
            if task_id not in self._tasks:
                return
            task = self._tasks[task_id]
            task.update(fields)
            task["updated_at"] = _utcnow_iso()
            snapshot = dict(task)
            queues = list(self._queues.get(task_id, []))

        for q in queues:
            try:
                q.put_nowait(snapshot)
            except Exception:
                pass


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# Singleton
task_manager = TaskManager()
