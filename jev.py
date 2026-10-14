"""Typed Jev assessments. No OpenAI-style messages or free-text answers are assumed."""
import json
import math
import os
import time

import httpx
from dotenv import dotenv_values

from config import ROOT, ConfigurationError
from telemetry import record

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"


class JevError(RuntimeError):
    pass


def ask(state, questions, *, root=ROOT, client=None):
    values = {**dotenv_values(root / ".env"), **os.environ}
    key = values.get("TYPESAFE_API_KEY", "")
    model = values.get("JEV_MODEL") or MODEL
    if not key:
        raise ConfigurationError("Set TYPESAFE_API_KEY in the local .env file or shell environment.")
    if model != MODEL:
        raise ConfigurationError(f"Use the team's pinned Jev model: {MODEL}")
    if len(json.dumps(state)) > 100000:
        raise ValueError("Jev state exceeds this prototype's conservative size limit.")
    timeout = float(values.get("API_TIMEOUT_SECONDS") or 45)
    if not 0 < timeout <= 180:
        raise ConfigurationError("API_TIMEOUT_SECONDS must be between 0 and 180.")
    owned = client is None
    client = client or httpx.Client(timeout=timeout)
    started = time.monotonic()
    status = None
    try:
        response = client.post(URL, headers={"Authorization": f"Bearer {key}"},
                               json={"model": model, "state": state, "questions": questions},
                               timeout=timeout)
        status = response.status_code
        response.raise_for_status()
        result = response.json()
        answers = result.get("answers", {})
        for name, question in questions.items():
            answer = answers.get(name, {})
            if answer.get("type") != question["type"]:
                raise JevError("Missing or invalid typed Jev answer")
            if question["type"] == "choice" and answer.get("choice") not in question["criteria"]:
                raise JevError("Jev returned an unknown choice")
            if question["type"] == "noul":
                value = answer.get("noul")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise JevError("Jev returned an invalid noul value")
        record(root, "jev", model, started, usage=result.get("usage"), status_code=status)
        return {"model": model, "answers": answers, "usage": result.get("usage", {})}
    except Exception as exc:
        record(root, "jev", model, started, error=exc, status_code=status)
        # Do not include provider bodies, headers or credentials in error messages.
        raise JevError(f"Jev request failed ({type(exc).__name__}, HTTP {status or 'unavailable'})") from None
    finally:
        if owned:
            client.close()
