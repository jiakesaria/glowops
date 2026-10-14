"""Record bounded request metadata, never keys, headers, prompts or error bodies."""
import json
import time
from datetime import datetime, timezone


def record(root, service, model, started, *, usage=None, error=None, status_code=None):
    path = root / "results" / "api_calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    # Copy only numerical token counters; never arbitrary provider payloads.
    usage = {k: v for k, v in (usage or {}).items()
             if "token" in k and isinstance(v, (int, float)) and not isinstance(v, bool)}
    row = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "service": service,
           "model": model, "latency_seconds": round(time.monotonic() - started, 3),
           "usage": usage, "status": "error" if error else "ok",
           "error_type": type(error).__name__ if error else None, "http_status": status_code}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")


def completion(settings, client, **kwargs):
    started = time.monotonic()
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        record(settings.root, settings.provider, settings.model_id, started,
               error=exc, status_code=getattr(exc, "status_code", None))
        raise
    record(settings.root, settings.provider, settings.model_id, started,
           usage=getattr(response, "usage", None))
    return response
