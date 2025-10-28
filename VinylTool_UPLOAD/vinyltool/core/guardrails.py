"""
VinylTool Guardrails
====================
Dry-run, preflight checks, retry logic, and JSONL logging.
"""
import os
import sys
import json
import uuid
import datetime
import random
import time

class Guardrails:
    def __init__(self):
        self.dry_run = False
        self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
        self.logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.log_path = os.path.join(self.logs_dir, f"{datetime.datetime.now().strftime('%Y-%m-%d')}_{self.run_id}.jsonl")

    def set_dry_run(self, val: bool):
        self.dry_run = bool(val)

    def log(self, event: str, **data):
        payload = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), "run": self.run_id, "event": event}
        payload.update(data)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\\n")
        except Exception as e:
            try:
                sys.stderr.write(f"[guardrails/log] {e}\\n")
            except Exception:
                pass

    def preflight(self, platform: str, payload: dict):
        problems = []
        if not isinstance(payload, dict) or not payload:
            problems.append("Empty or invalid payload")
        title = (payload.get("title") or payload.get("listingTitle") or "").strip()
        if not title:
            problems.append("Missing title/listingTitle")
        desc = (payload.get("listingDescription") or payload.get("description") or "")
        if isinstance(desc, str) and len(desc) > 500000:
            problems.append("Description exceeds 500000 chars")
        if problems:
            raise ValueError(f"Preflight failed for {platform}: " + "; ".join(problems))

    def retryable(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return any(tok in text for tok in ["timeout", "timed out", "connection", "429", "503", "502", "500"])

_guardrails_singleton = Guardrails()

def with_retries(max_attempts=3, base_sleep=0.6):
    import time, random
    def deco(fn):
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts or not _guardrails_singleton.retryable(e):
                        raise
                    jitter = base_sleep * (1.0 + random.random())
                    time.sleep(jitter)
        return wrapper
    return deco
# ==== /PHASE0/1 ====
