"""Append a validated verdict envelope to the local JSON Lines audit trail."""

from pathlib import Path
from threading import Lock

from config import ROOT
from contracts.schema import LedgerRecord

_LOCK = Lock()


def append_record(record: LedgerRecord, path: Path | None = None) -> None:
    """Log one line; propagate write errors rather than silently lose results."""
    validated = LedgerRecord.model_validate(record.model_dump())
    path = Path(path) if path is not None else ROOT / "data" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, path.open("a", encoding="utf-8") as stream:
        stream.write(validated.model_dump_json() + "\n")
        stream.flush()
