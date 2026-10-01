"""Worker.

Claims queued jobs one at a time and runs the analyser. Safe to run several
copies: the claim uses FOR UPDATE SKIP LOCKED, so two workers never take the
same job.

The validation gate is the point of this process. Analyser output is validated
against both schemas and the semantic invariants BEFORE anything is written. A
document that fails produces a failed job with the reason retained, not a stored
row. Without that gate, the day perception starts emitting something incoherent
is the day the database quietly fills with wrong numbers.

Later this becomes an SQS consumer or a container task. Nothing about the loop
body changes - only where the job comes from.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

# Run either as a script (python worker/run.py) or as a module
# (python -m worker.run). A relative import would fail in the first case,
# because __main__ has no parent package.
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import db
from app.config import settings
from app.ports.analyser import get_analyser
from app.ports.storage import get_storage
from app.validation import ContractError, validate_pair

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_stop = False


class JsonFormatter(logging.Formatter):
    """Structured logs. Never log image bytes or storage paths carrying
    customer identifiers - the SHA is enough to correlate."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "worker": WORKER_ID,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("worker")
log.addHandler(handler)
log.setLevel(logging.INFO)


def _log(level: int, msg: str, **fields) -> None:
    log.log(level, msg, extra={"extra_fields": fields})


def _handle_signal(signum, _frame) -> None:
    global _stop
    _stop = True
    _log(logging.INFO, "shutdown requested, finishing current job", signal=signum)


def process_once() -> bool:
    """Claim and process a single job. Returns False when the queue is empty."""
    analyser, storage = get_analyser(), get_storage()

    with db.conn() as c:
        job = db.claim_job(c, WORKER_ID)
        if job is None:
            return False

        jid, iid = job["id"], job["image_id"]
        img = c.execute("SELECT * FROM images WHERE id=%s", (iid,)).fetchone()
        sha = img["sha256"]
        t0 = time.monotonic()

        try:
            data = storage.get(img["storage_key"])
            representation, assessment = analyser.analyse(data, img)

            # the gate: nothing is written unless both documents are coherent
            validate_pair(representation, assessment)

            rep = db.insert_representation(c, iid, representation)
            ass = db.insert_assessment(c, iid, rep["id"], assessment)
            c.commit()
            db.finish_job(c, jid)

            _log(logging.INFO, "assessed",
                 job_id=jid, image_sha256=sha,
                 verdict=assessment["verdict"]["value"],
                 rule=assessment["verdict"].get("rule_id"),
                 usable_free_u=assessment["measurements"]["usable_free_u"],
                 assessment_id=ass["id"],
                 review_required=assessment.get("review", {}).get("required", False),
                 ms=round((time.monotonic() - t0) * 1000))

        except ContractError as e:
            c.rollback()
            state = db.fail_job(c, jid, f"contract violation: {e}")
            _log(logging.ERROR, "contract violation, nothing written",
                 job_id=jid, image_sha256=sha, job_status=state, detail=str(e)[:800])

        except Exception as e:  # noqa: BLE001
            c.rollback()
            state = db.fail_job(c, jid, f"{type(e).__name__}: {e}")
            _log(logging.ERROR, "job failed",
                 job_id=jid, image_sha256=sha, job_status=state,
                 error=f"{type(e).__name__}: {e}")
    return True


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    applied = db.migrate()
    _log(logging.INFO, "worker started",
         analyser=get_analyser().describe(), storage=get_storage().describe(),
         model_provider=settings.model_provider, migrations_applied=applied,
         poll_s=settings.worker_poll_s)

    once = "--once" in sys.argv
    idle = 0
    while not _stop:
        try:
            did = process_once()
        except Exception as e:  # noqa: BLE001  keep the loop alive
            _log(logging.ERROR, "loop error", error=f"{type(e).__name__}: {e}")
            did = False
        if did:
            idle = 0
            continue
        if once:
            break
        idle += 1
        time.sleep(settings.worker_poll_s)
    _log(logging.INFO, "worker stopped", idle_polls=idle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
