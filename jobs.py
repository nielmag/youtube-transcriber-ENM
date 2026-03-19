"""In-memory job state (thread-safe)."""
import threading
import time
import uuid

_jobs: dict = {}
_lock = threading.Lock()


def create(url: str) -> str:
    job_id = str(uuid.uuid4())[:8]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": url,
            "status": "queued",
            "progress": 0,
            "message": "Queued...",
            "title": None,
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def update(job_id: str, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def get(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def get_safe(job_id: str) -> dict | None:
    """Returns job dict without the docx_bytes payload."""
    job = get(job_id)
    if job:
        job.pop("docx_bytes", None)
    return job
