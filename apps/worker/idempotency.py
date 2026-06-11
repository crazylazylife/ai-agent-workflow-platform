"""
Idempotency store. A small key->result table that lets a retried or
resumed step return a prior result instead of re-running its side effect.

Each helper uses its OWN short transaction so the record is durable independently
of the engine's step transaction — that's what makes the guard survive a crash.
"""
from awp_shared.db import SessionLocal
from awp_shared.models import IdempotencyKey


def idempotent_get(key: str):
    """Return (found: bool, result). `found` distinguishes a stored None from a miss."""
    with SessionLocal() as db:
        row = db.get(IdempotencyKey, key)
        return (True, row.result_json) if row is not None else (False, None)


def idempotent_put(key: str, result) -> None:
    """Store the result under `key` (first writer wins; later calls are no-ops)."""
    with SessionLocal() as db:
        if db.get(IdempotencyKey, key) is None:
            db.add(IdempotencyKey(key=key, result_json=result))
            db.commit()
