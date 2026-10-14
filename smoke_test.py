"""One tiny request per service; logs only safe metadata, never keys."""
import json

from config import ROOT, create_client, get_config
from jev import ask
from run_tests import write_json
from telemetry import completion


def main():
    settings = get_config(provider="foundry")
    results = []
    for service in ("foundry", "jev"):
        try:
            if service == "foundry":
                with create_client(settings) as client:
                    response = completion(settings, client, model=settings.model_id,
                        messages=[{"role": "user", "content": "Reply with the word OK."}], max_tokens=64)
                if not response.choices or not response.choices[0].message.content:
                    raise ValueError("Empty completion")
                model = settings.model_id
            else:
                response = ask("The test record explicitly says: connection check passed.", {
                    "connection": {"type": "choice", "instructions": "Read the test record and classify its stated result.",
                                   "criteria": {"passed": "Record says passed", "failed": "Record says failed"}}})
                if response["answers"]["connection"]["choice"] != "passed":
                    raise ValueError("Unexpected test answer")
                model = response["model"]
            results.append({"service": service, "status": "ok", "model": model})
            print(f"{service}: connection succeeded ({model})", flush=True)
        except Exception as exc:
            results.append({"service": service, "status": "error", "error_type": type(exc).__name__})
            print(f"{service}: ERROR ({type(exc).__name__}); check key and safe API telemetry.", flush=True)
    write_json(ROOT / "results/connections.json", results)
    return int(any(r["status"] == "error" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
