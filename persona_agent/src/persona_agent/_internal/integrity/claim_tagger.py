"""Claim Tagger — 리포트의 숫자에 자동 출처(data-src) 태그를 제안/적용.

작동:
1. 리포트의 모든 숫자 패턴 추출
2. ground truth JSON에서 정확 매치 찾기
3. <span data-src="path/file.json:field">값</span> 형태 태그 생성
4. --apply 옵션이면 in-place 적용, 기본은 dry-run

사용:
    .venv/bin/python3 -m modules.claim_tagger reports/EXECUTIVE_REPORT.html
    .venv/bin/python3 -m modules.claim_tagger reports/EXECUTIVE_REPORT.html --apply

목적: hallucination_guard.audit_tagged_claims가 리포트를 검증할 수 있게 함.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from persona_agent._internal.integrity.hallucination_guard import (
    _NUMBER_PATTERN,
    _find_sources,
    _load_ground_truth,
    _strip_html,
)
from persona_agent._internal.core.workspace import get_workspace

_BASE = get_workspace().root
_DEFAULT_GT_DIRS = [
    "reports/",
    "experiments/ablation/",
    "experiments/ab_validation/",
    "experiments/datasets/ga4_sample/",
    "experiments/datasets/open_bandit/",
]

# 태그 생성 시 무시할 안전 숫자
SAFE_INTEGERS = set(range(0, 21)) | {30, 40, 50, 60, 80, 100, 1000}
SAFE_YEARS = {2024, 2025, 2026, 2027}
SAFE_KNOWN = {0.5, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0}


def _is_inside_tag(text: str, pos: int) -> bool:
    """현재 위치가 이미 HTML attribute(data-src 등) 내부인지."""
    last_lt = text.rfind("<", 0, pos)
    last_gt = text.rfind(">", 0, pos)
    return last_lt > last_gt


def _is_already_tagged(text: str, pos: int, span: int = 200) -> bool:
    """현재 숫자가 이미 data-src 태그 안에 있는지."""
    start = max(0, pos - span)
    nearest_open = text.rfind("<span", start, pos)
    nearest_close = text.rfind("</span>", start, pos)
    if nearest_open > nearest_close:
        # 열린 span 내부에 있음
        chunk = text[nearest_open:pos]
        return "data-src" in chunk
    return False


def suggest_tags(report_path: str | Path,
                 ground_truth_dirs: list[str] | None = None) -> list[dict]:
    """리포트에 추가 가능한 태그 제안 목록 반환.

    Returns: [{value, position, context, src_file, src_field, src_value, confidence}]
    """
    report_path = Path(report_path)
    raw = report_path.read_text(encoding="utf-8")
    text_for_search = _strip_html(raw) if report_path.suffix.lower() in (".html", ".htm") else raw

    truth = _load_ground_truth(ground_truth_dirs or _DEFAULT_GT_DIRS)

    suggestions = []
    seen_keys = set()

    for match in _NUMBER_PATTERN.finditer(text_for_search):
        num_str, pct = match.group(1), match.group(2)
        try:
            value = float(num_str)
        except ValueError:
            continue

        if int(value) == value and (int(value) in SAFE_INTEGERS or int(value) in SAFE_YEARS):
            continue
        if value in SAFE_KNOWN:
            continue

        ctx_start = max(0, match.start() - 50)
        ctx_end = min(len(text_for_search), match.end() + 50)
        context = text_for_search[ctx_start:ctx_end].replace("\n", " ").strip()

        if any(m in context for m in ["$", "₩", "월", "년", "USD"]):
            continue

        sources = _find_sources(value, truth, context=context)
        exact = [s for s in sources if "exact" in s[3]]
        if not exact:
            continue

        top = exact[0]
        path, field, actual, quality = top

        # 프로젝트 루트 기준 상대 경로
        try:
            rel_path = str(Path(path).relative_to(_BASE))
        except ValueError:
            rel_path = path

        key = (round(value, 4), pct, field)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        suggestions.append({
            "value": f"{num_str}{pct}",
            "raw_value": value,
            "context": context[:120],
            "src_file": rel_path,
            "src_field": field,
            "src_value": actual,
            "confidence": "high" if len(exact) == 1 else f"medium ({len(exact)} matches)",
        })

    return suggestions


def apply_tags(report_path: str | Path,
               suggestions: list[dict],
               output_path: str | Path | None = None) -> tuple[int, str]:
    """제안된 태그를 리포트에 적용. 같은 숫자 첫 발생만 태그 (보수적).

    Returns: (적용된 개수, 새 텍스트 경로)
    """
    report_path = Path(report_path)
    text = report_path.read_text(encoding="utf-8")
    is_html = report_path.suffix.lower() in (".html", ".htm")

    applied = 0
    for sug in suggestions:
        value_str = sug["value"]
        # 각 value의 첫 번째 untagged 발생만 처리 (replace_first)
        # HTML 태그 attribute 내부, 이미 data-src 내부, <a href= 등 안전한 곳 회피

        # 패턴: 단어 경계 + 숫자 + 단어 경계 (이미 태그된 경우 건너뛰기)
        pattern = re.compile(r"(?<![A-Za-z\d_])" + re.escape(value_str) + r"(?![A-Za-z_\d])")
        positions = []
        for m in pattern.finditer(text):
            if _is_inside_tag(text, m.start()):
                continue
            if _is_already_tagged(text, m.start()):
                continue
            positions.append(m)
            break  # 첫 번째만

        if not positions:
            continue

        m = positions[0]
        if is_html:
            replacement = (
                f'<span data-src="{sug["src_file"]}:{sug["src_field"]}" '
                f'title="src={sug["src_value"]}">{value_str}</span>'
            )
        else:
            replacement = f'[{value_str}]{{src={sug["src_file"]}:{sug["src_field"]}}}'
        text = text[:m.start()] + replacement + text[m.end():]
        applied += 1

    out_path = Path(output_path) if output_path else report_path
    out_path.write_text(text, encoding="utf-8")
    return applied, str(out_path)


def coverage_report(report_path: str | Path,
                    ground_truth_dirs: list[str] | None = None) -> dict:
    """리포트의 태그 커버리지 측정."""
    report_path = Path(report_path)
    raw = report_path.read_text(encoding="utf-8")
    text_for_search = _strip_html(raw) if report_path.suffix.lower() in (".html", ".htm") else raw

    truth = _load_ground_truth(ground_truth_dirs or _DEFAULT_GT_DIRS)

    total = 0
    taggable = 0
    seen = set()

    for match in _NUMBER_PATTERN.finditer(text_for_search):
        num_str, pct = match.group(1), match.group(2)
        try:
            value = float(num_str)
        except ValueError:
            continue
        if int(value) == value and (int(value) in SAFE_INTEGERS or int(value) in SAFE_YEARS):
            continue
        if value in SAFE_KNOWN:
            continue
        ctx_start = max(0, match.start() - 50)
        ctx_end = min(len(text_for_search), match.end() + 50)
        context = text_for_search[ctx_start:ctx_end]
        if any(m in context for m in ["$", "₩", "월", "년", "USD"]):
            continue

        key = (round(value, 4), pct)
        if key in seen:
            continue
        seen.add(key)

        total += 1
        sources = _find_sources(value, truth, context=context)
        if any("exact" in s[3] for s in sources):
            taggable += 1

    existing_tags = len(re.findall(r'data-src="[^"]+"', raw))
    return {
        "total_unique_numbers": total,
        "ground_truth_matchable": taggable,
        "currently_tagged": existing_tags,
        "coverage_pct": round(existing_tags / total * 100, 1) if total else 0,
        "potential_coverage_pct": round(taggable / total * 100, 1) if total else 0,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  .venv/bin/python3 -m modules.claim_tagger <report> [--apply] [--coverage]")
        sys.exit(1)

    report = sys.argv[1]
    apply = "--apply" in sys.argv
    coverage_only = "--coverage" in sys.argv

    if coverage_only:
        cov = coverage_report(report)
        print(f"Coverage report: {report}")
        print(json.dumps(cov, indent=2))
        return

    suggestions = suggest_tags(report)
    cov = coverage_report(report)

    print(f"\n=== {report} ===")
    print(f"커버리지: {cov['currently_tagged']}/{cov['total_unique_numbers']} 태그됨 ({cov['coverage_pct']}%)")
    print(f"잠재 커버리지: {cov['potential_coverage_pct']}% ({cov['ground_truth_matchable']} 매치 가능)")
    print(f"\n신규 태그 제안: {len(suggestions)}개")

    for s in suggestions[:15]:
        print(f"  • {s['value']:>8s}  →  {s['src_file']}:{s['src_field']}  [{s['confidence']}]")
        print(f"    ctx: ...{s['context'][:80]}...")
    if len(suggestions) > 15:
        print(f"  ... 외 {len(suggestions) - 15}개")

    if apply and suggestions:
        # 안전: high-confidence (single exact match)만 자동 적용
        high_conf = [s for s in suggestions if s["confidence"] == "high"]
        applied, _ = apply_tags(report, high_conf)
        print(f"\n✅ {applied}/{len(high_conf)} high-confidence 태그 적용 완료 → {report}")
        if len(suggestions) - len(high_conf) > 0:
            print(f"⚠️  {len(suggestions) - len(high_conf)}개 medium-confidence 제안은 수동 검토 필요.")
    elif apply:
        print("\n적용할 제안 없음.")
    else:
        print("\n--apply 추가 시 in-place 적용.")


if __name__ == "__main__":
    main()
