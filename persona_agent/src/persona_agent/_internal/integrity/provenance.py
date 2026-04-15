"""M4 Provenance — Append-only HMAC-SHA256 chain for tamper-evident audit logs.

H2 단계에서 CPO 감사 요구 대응:
  - 모든 리포트/세션 결과를 시간 순으로 append-only 로그에 기록
  - 각 entry는 이전 entry의 hash를 포함 → 중간 조작 불가능
  - HMAC secret으로 외부 위조 차단

목적:
  - "이 리포트가 X 시점에 Y 데이터로 생성됐다"는 증명
  - 블록체인 없이 (Constitution §12: 벡터 DB / 블록체인 금지) tamper-evident 보장

사용:
    from modules.provenance import record, verify_chain

    entry_id = record({
        "type": "cohort_report",
        "report_id": "cohort_rpt_xxx",
        "n_personas": 20,
        "aggregation_hash": "sha256:...",
    })

    # 검증 (전체 체인 무결성)
    ok, broken_at = verify_chain()
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from persona_agent._internal.core.workspace import get_workspace

logger = logging.getLogger(__name__)

_LOG_PATH = get_workspace().cache_dir / "provenance_chain.jsonl"
_SECRET_ENV = "PROVENANCE_HMAC_SECRET"


def _get_secret() -> bytes:
    """HMAC secret. 환경변수 우선, 없으면 로컬 dev secret."""
    s = os.environ.get(_SECRET_ENV)
    if s:
        return s.encode()
    # dev fallback (production 환경에선 PROVENANCE_HMAC_SECRET 환경변수 필수)
    return b"dev-only-secret-set-PROVENANCE_HMAC_SECRET-in-production"


def _compute_hmac(prev_hash: str, payload_json: str) -> str:
    """이전 hash + payload → HMAC-SHA256."""
    msg = (prev_hash + "|" + payload_json).encode()
    return hmac.new(_get_secret(), msg, hashlib.sha256).hexdigest()


def _last_hash() -> str:
    """체인의 마지막 hash. 없으면 genesis (0x00...)."""
    if not _LOG_PATH.exists():
        return "0" * 64
    with open(_LOG_PATH, "rb") as f:
        try:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b"\n":
                f.seek(-2, os.SEEK_CUR)
        except OSError:
            f.seek(0)
        last_line = f.readline().decode()
    if not last_line.strip():
        return "0" * 64
    return json.loads(last_line)["hash"]


def record(data: dict) -> str:
    """체인에 새 entry 추가. tamper-evident, append-only.

    Args:
        data: 기록할 메타데이터 (type, report_id 등 — 자유 형식)

    Returns:
        entry_id (UUID hex)
    """
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry_id = uuid.uuid4().hex
    prev_hash = _last_hash()

    payload = {
        "id": entry_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "prev_hash": prev_hash,
        "data": data,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    entry_hash = _compute_hmac(prev_hash, payload_json)

    full_entry = {**payload, "hash": entry_hash}
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(full_entry, ensure_ascii=False) + "\n")

    logger.debug("Provenance: %s (prev=%s..., hash=%s...)",
                 entry_id[:8], prev_hash[:8], entry_hash[:8])
    return entry_id


def verify_chain() -> tuple[bool, int | None]:
    """전체 체인 무결성 검증.

    Returns:
        (ok, broken_at_line)
        ok=True면 broken_at_line=None.
        ok=False면 broken_at_line=처음 어긋난 line 번호 (1-based).
    """
    if not _LOG_PATH.exists():
        return True, None

    prev_hash = "0" * 64
    with open(_LOG_PATH, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return False, i

            stored_hash = entry.pop("hash", None)
            stored_prev = entry.get("prev_hash")

            if stored_prev != prev_hash:
                return False, i

            payload_json = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            recomputed = _compute_hmac(prev_hash, payload_json)
            if recomputed != stored_hash:
                return False, i

            prev_hash = stored_hash

    return True, None


def list_entries(limit: int = 20) -> list[dict]:
    """최근 entries 조회 (감사용)."""
    if not _LOG_PATH.exists():
        return []
    with open(_LOG_PATH, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    return lines[-limit:]


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"

    if cmd == "verify":
        ok, broken = verify_chain()
        if ok:
            print(f"✅ Provenance chain verified: {_LOG_PATH}")
            print(f"   Total entries: {len(list_entries(limit=10**9))}")
        else:
            print(f"🔴 Chain broken at line {broken}")
            sys.exit(1)
    elif cmd == "list":
        for e in list_entries():
            print(f"  {e['ts']} {e['id'][:8]} {e['data'].get('type', '?')}")
    elif cmd == "test":
        # smoke test
        eid = record({"type": "self_test", "ts": datetime.now(timezone.utc).isoformat()})
        ok, broken = verify_chain()
        print(f"recorded {eid[:8]}, verify={ok}")
    else:
        print("Usage: python -m modules.provenance [verify|list|test]")
