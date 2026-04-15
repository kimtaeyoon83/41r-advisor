"""Hallucination audit for JUPITER_UX_DIAGNOSIS.md.

Compares numeric claims in the MD against the underlying verdict JSONs.
Run locally against regenerated verdicts; diff against expected tolerances.

Usage:
    python3 experiments/public_analysis/jupiter_audit.py \
        --text /tmp/jupiter_verdict.json \
        --browser /tmp/jupiter_browser_verdict.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


# Expected values from the MD. Update when MD is regenerated.
EXPECTED_TEXT = {
    "wallet_mentions": (11, 2),            # (expected, ±tolerance)
    "slippage_mentions": (17, 2),
    "warning_mentions": (6, 2),
    "p_crypto_native_OK": (5, 0),
    "p_senior_abandoned": (5, 0),
    "avg_conv": {
        "p_crypto_native": (0.91, 0.02),
        "p_creator_freelancer": (0.24, 0.05),
        "p_pragmatic": (0.53, 0.05),
        "p_b2b_buyer": (0.18, 0.05),
        "p_senior": (0.10, 0.03),
    },
}
EXPECTED_BROWSER = {
    "f009_mentions": (16, 2),
    "task_complete": (0, 0),
    "abandoned": (24, 1),   # 25 total, 1 may be partial
}


def _text_contains_any(haystack: str, needles: list[str]) -> bool:
    return any(n in haystack for n in needles)


def audit_text_verdict(verdict: dict) -> dict[str, object]:
    out: dict[str, object] = {}
    runs = verdict.get("runs", [])

    wallet_count = 0
    slippage_count = 0
    warning_count = 0
    for r in runs:
        txt = " ".join([
            r.get("drop_point") or "",
            *(r.get("frustration_points") or []),
            r.get("reasoning") or "",
        ]).lower()
        if _text_contains_any(txt, ["지갑", "wallet"]):
            wallet_count += 1
        if _text_contains_any(txt, ["슬리피지", "slippage", "⚙", "settings"]):
            slippage_count += 1
        if _text_contains_any(txt, ["경고", "warning", "맥락"]):
            warning_count += 1

    out["wallet_mentions"] = wallet_count
    out["slippage_mentions"] = slippage_count
    out["warning_mentions"] = warning_count
    out["total_runs"] = len(runs)

    # Outcomes per persona
    by_p = defaultdict(list)
    for r in runs:
        by_p[r.get("persona_id", "")].append(r)

    out["outcomes"] = {}
    out["avg_conv"] = {}
    for pid, rs in by_p.items():
        outcomes = [r.get("outcome") for r in rs]
        out["outcomes"][pid] = {
            "OK": outcomes.count("task_complete"),
            "PART": outcomes.count("partial"),
            "ABAN": outcomes.count("abandoned"),
        }
        convs = [
            r.get("conversion_probability") for r in rs
            if isinstance(r.get("conversion_probability"), (int, float))
        ]
        out["avg_conv"][pid] = round(sum(convs) / len(convs), 2) if convs else 0.0

    return out


def audit_browser_verdict(verdict: dict) -> dict[str, object]:
    out: dict[str, object] = {}
    runs = verdict.get("runs", [])

    f009_count = 0
    sell_count = 0
    for r in runs:
        dump = json.dumps(r, ensure_ascii=False).lower()
        if "f009" in dump:
            f009_count += 1
        if "sell" in dump and ("입력" in dump or "input" in dump):
            sell_count += 1

    out["f009_mentions"] = f009_count
    out["sell_mentions"] = sell_count
    out["total_runs"] = len(runs)

    outcomes = [r.get("outcome") for r in runs]
    out["task_complete"] = outcomes.count("task_complete")
    out["partial"] = outcomes.count("partial")
    out["abandoned"] = outcomes.count("abandoned")

    return out


def compare(actual: int | float, expected: tuple[int | float, int | float]) -> bool:
    exp_val, tol = expected
    return abs(actual - exp_val) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=Path, required=True,
                    help="text-mode verdict JSON")
    ap.add_argument("--browser", type=Path, required=True,
                    help="browser-mode verdict JSON")
    args = ap.parse_args()

    text = json.loads(args.text.read_text())
    browser = json.loads(args.browser.read_text())

    text_audit = audit_text_verdict(text)
    browser_audit = audit_browser_verdict(browser)

    print("=" * 60)
    print("JUPITER DIAGNOSIS AUDIT")
    print("=" * 60)

    # Text mode checks
    print("\n[TEXT MODE]")
    failures: list[str] = []
    for key in ("wallet_mentions", "slippage_mentions", "warning_mentions"):
        actual = text_audit[key]
        exp = EXPECTED_TEXT[key]
        ok = compare(actual, exp)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {key}: actual={actual}, expected={exp[0]}±{exp[1]}")
        if not ok:
            failures.append(f"text.{key}")

    # Outcomes
    cn_ok = text_audit["outcomes"].get("p_crypto_native", {}).get("OK", 0)
    sn_ab = text_audit["outcomes"].get("p_senior", {}).get("ABAN", 0)
    for label, actual, exp_key in [
        ("p_crypto_native OK", cn_ok, "p_crypto_native_OK"),
        ("p_senior ABAN", sn_ab, "p_senior_abandoned"),
    ]:
        exp = EXPECTED_TEXT[exp_key]
        ok = compare(actual, exp)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}: actual={actual}, expected={exp[0]}±{exp[1]}")
        if not ok:
            failures.append(f"text.{exp_key}")

    for pid, exp in EXPECTED_TEXT["avg_conv"].items():
        actual = text_audit["avg_conv"].get(pid, 0.0)
        ok = compare(actual, exp)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {pid} avg_conv: actual={actual}, expected={exp[0]}±{exp[1]}")
        if not ok:
            failures.append(f"text.avg_conv.{pid}")

    # Browser mode checks
    print("\n[BROWSER MODE]")
    for key in ("f009_mentions", "task_complete", "abandoned"):
        actual = browser_audit[key]
        exp = EXPECTED_BROWSER[key]
        ok = compare(actual, exp)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {key}: actual={actual}, expected={exp[0]}±{exp[1]}")
        if not ok:
            failures.append(f"browser.{key}")

    print("\n" + "=" * 60)
    if failures:
        print(f"❌ AUDIT FAILED: {len(failures)} claim(s) out of tolerance")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    else:
        print("✅ AUDIT PASSED — all MD numeric claims within tolerance")
        sys.exit(0)


if __name__ == "__main__":
    main()
