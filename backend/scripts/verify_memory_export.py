#!/usr/bin/env python3
"""
Verify a Memory Lock export OFFLINE, with no server, database or secret.

    python scripts/verify_memory_export.py memory-export.json

Download the export from  GET /api/v1/memory/export  (admin). The file
carries the public keys and the starting hash. Prints VERIFIED or
INTEGRITY_FAILURE with the first failing sequence, and exits 0 or 1.
Only the `cryptography` package is needed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import memory_core as mc  # noqa: E402


def main(path: str) -> int:
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    keys = mc.public_keys_from_b64(
        bundle["public_keys"]["ed25519"], bundle["public_keys"].get("ml_dsa_65")
    )
    result = mc.verify_chain(
        bundle["records"],
        keys,
        start_previous_hash=bundle["start_previous_hash"],
        start_sequence=bundle["from_sequence"],
    )
    print(f"{result.status}: {result.checked} record(s) checked")
    if result.status != "VERIFIED":
        print(f"First failure at sequence {result.first_failure_sequence}: {result.failure_reason}")
        print(f"expected={result.expected} actual={result.actual}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: verify_memory_export.py <export.json>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
