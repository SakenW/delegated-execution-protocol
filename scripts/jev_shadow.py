"""Optional intent observation for the selector CLI."""

import http.client
import json
import re
import shlex
from pathlib import Path


CATEGORIES = {
    "deterministic": "Mechanical counting, exact matching or lookup.",
    "batch": "Repeatedly apply supplied semantic rules to independent items.",
    "ordinary_review": "Judge bounded low- or medium-impact correctness.",
    "high_risk_review": "Judge material billing, access, production, recovery or data-loss risks.",
    "unclear": "Insufficient context or none of these categories fits.",
}


def read_api_key():
    path = Path.home() / ".config/cloud-ops/env/typesafe.env"
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\s*(?:export\s+)?TYPESAFE_API_KEY\s*=\s*(.*)", line)
        if match:
            values = shlex.split(match[1], comments=True)
            if len(values) == 1 and re.fullmatch(r"[!-~]+", values[0]):
                return values[0]
    raise ValueError("missing credential")


def observe_intent(summary):
    summary = summary.strip()
    if not summary or len(summary) > 500 or "\n" in summary:
        return {"status": "skipped", "reason": "expected_short_summary"}
    try:
        key = read_api_key()
    except (OSError, ValueError):
        return {"status": "unavailable", "reason": "credential"}
    payload = {
        "model": "jev-latest",
        "state": summary,
        "questions": {"intent": {
            "type": "choice",
            "instructions": "Classify the requested work by its main purpose and consequences.",
            "criteria": CATEGORIES,
        }},
    }
    conn = http.client.HTTPSConnection("api.typesafe.ai", timeout=3)
    try:
        conn.request("POST", "/v1/systemone", json.dumps(payload).encode(), {
            "Content-Type": "application/json", "Authorization": "Bearer " + key,
        })
        response = conn.getresponse()
        if response.status != 200:
            return {"status": "unavailable", "reason": "http", "http_status": response.status}
        data = json.loads(response.read(65537))
        answer = data["answers"]["intent"]
        if answer["type"] != "choice" or answer["choice"] not in CATEGORIES:
            raise ValueError("unexpected classification")
        return {"status": "observed", "category": answer["choice"]}
    except (OSError, http.client.HTTPException):
        return {"status": "unavailable", "reason": "network"}
    except (ValueError, TypeError, KeyError, RecursionError):
        return {"status": "unavailable", "reason": "invalid_response"}
    finally:
        conn.close()
