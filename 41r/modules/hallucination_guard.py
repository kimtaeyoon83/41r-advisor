"""Hallucination Guard — 리포트의 모든 수치를 ground truth와 자동 대조.

작동:
1. 리포트 파일(HTML/MD)에서 모든 숫자/퍼센트/p-value 추출
2. ground truth JSON 디렉토리(aggregation.json, metric_*.json 등) 스캔
3. 각 추출된 숫자가 ground truth의 어느 값과도 매치 안 되면 경고
4. p-value 패턴 발견 시 원본 데이터로 scipy 재계산 후 비교

사용법:
    from modules.hallucination_guard import audit_report
    audit_report("reports/sample_report_v2.html",
                 ground_truth_dirs=["reports/", "experiments/ablation/"])
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    severity: str  # "critical" | "warning" | "info"
    location: str
    claim: str
    details: str


# 통계 패턴: 숫자, 퍼센트, p-value, ratio
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z\d_])(\d+\.\d+|\d+)(%?)(?![A-Za-z_])")
_PVALUE_PATTERN = re.compile(r"p\s*=\s*(\d*\.\d+)", re.IGNORECASE)
_RATIO_PATTERN = re.compile(r"(\d+\.\d+)\s*[×x]")


def _strip_html(text: str) -> str:
    """HTML 태그 제거. 간단한 텍스트 추출용."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&amp;|&lt;|&gt;", " ", text)
    return text


def _flatten_json(obj, prefix="") -> dict[str, float]:
    """중첩 JSON에서 모든 숫자 값을 평탄화. {경로: 값} 반환."""
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            result.update(_flatten_json(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            result.update(_flatten_json(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)):
        result[prefix] = float(obj)
    return result


def _load_ground_truth(dirs: list[str | Path]) -> dict[str, dict[str, float]]:
    """디렉토리들에서 모든 .json 파일을 로드 → {파일경로: {필드경로: 값}}."""
    truth = {}
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for path in d.rglob("*.json"):
            if any(p in str(path) for p in [".venv", "node_modules", "__pycache__"]):
                continue
            try:
                with open(path) as f:
                    data = json.load(f)
                truth[str(path)] = _flatten_json(data)
            except (json.JSONDecodeError, OSError):
                continue
    return truth


def _all_truth_values(truth: dict[str, dict[str, float]]) -> set[float]:
    """모든 ground truth 값들을 단일 set으로."""
    values = set()
    for fields in truth.values():
        for v in fields.values():
            values.add(round(v, 4))
            # 퍼센트 변환 (0.3 ↔ 30, 0.83 ↔ 83 등)
            values.add(round(v * 100, 2))
            values.add(round(v / 100, 4))
    return values


def _is_close_match(value: float, truth_values: set[float], tol: float = 0.02) -> bool:
    """값이 ground truth set에 가까운지 (절대오차 또는 상대오차 2%).

    부호 무시 매칭도 포함 (ground truth -0.575 vs 텍스트 0.575).
    """
    candidates = [value, -value, abs(value)]
    for v in candidates:
        if v in truth_values:
            return True
        for tv in truth_values:
            if abs(v - tv) < tol:
                return True
            if tv != 0 and abs(v - tv) / abs(tv) < 0.02:
                return True
    return False


def _find_sources(
    value: float,
    truth: dict[str, dict[str, float]],
    context: str = "",
    tol: float = 0.001,
) -> list[tuple[str, str, float, str]]:
    """값과 매치되는 ground truth 위치 찾기. 정확도/관련성 순 정렬.

    개선 v2:
    - 컨텍스트의 사이트명/회사명 매치는 5점
    - 메트릭 도메인 키워드 (conversion, abandoned, divergence 등) 2점
    - 일반 매치 1점

    Returns: [(file_path, field_path, actual_value, match_quality), ...]
    match_quality: "exact", "scaled", "approx"
    """
    matches = []

    # 정확 매치 우선 (절대오차 0.001 이내, 같은 단위)
    for path, fields in truth.items():
        for field, tv in fields.items():
            if abs(value - tv) < tol:
                matches.append((path, field, tv, "exact"))
            elif abs(-value - tv) < tol:
                matches.append((path, field, tv, "exact (sign)"))

    # 사이트/회사명 화이트리스트 (도메인 지식)
    SITE_KEYWORDS = {
        "29cm": ["29cm", "649058"],
        "클래스101": ["class101", "31ef68"],
        "오늘의집": ["ohou", "ohouse", "26ffd3"],
        "webflow": ["webflow", "27edb8"],
        "glossier": ["glossier", "3df81f"],
        "figma": ["figma"],
        "shopify": ["shopify"],
        "pricecharting": ["pricecharting"],
    }
    METRIC_KEYWORDS = ["conversion", "abandoned", "partial", "engagement", "turn",
                       "divergence", "specificity", "entropy", "correlation",
                       "impulsive", "cautious", "research", "price", "social", "visual"]

    # 정확 매치 있으면 그것만 반환
    if matches:
        ctx_lower = context.lower()

        def relevance(m):
            path, field, _, _ = m
            score = 0
            path_lower = path.lower()
            field_lower = field.lower()

            # 사이트 키워드 매치 (가장 강한 신호)
            for site, keywords in SITE_KEYWORDS.items():
                if site in ctx_lower:
                    for kw in keywords:
                        if kw in path_lower:
                            score += 5

            # 메트릭 키워드 매치
            for kw in METRIC_KEYWORDS:
                if kw in ctx_lower and (kw in path_lower or kw in field_lower):
                    score += 2

            # 일반 단어 매치
            for kw in re.findall(r"[A-Za-z가-힣_]{4,}", ctx_lower):
                if kw in path_lower or kw in field_lower:
                    score += 1

            return -score  # 큰 점수 먼저

        matches.sort(key=relevance)
        return matches

    # 정확 매치 없으면 scale 변환 시도 (0.3 ↔ 30%)
    for path, fields in truth.items():
        for field, tv in fields.items():
            if abs(value / 100 - tv) < tol:
                matches.append((path, field, tv, "scaled (×100)"))
            elif abs(value * 100 - tv) < tol:
                matches.append((path, field, tv, "scaled (÷100)"))

    if matches:
        return matches

    # 마지막으로 근사 매치 (2% 오차)
    for path, fields in truth.items():
        for field, tv in fields.items():
            for c in [value, -value]:
                if tv != 0 and abs(c - tv) / abs(tv) < 0.02:
                    matches.append((path, field, tv, "approx"))
                    break

    return matches


def _check_ratio(value: float, truth_values: set[float], tol: float = 0.05) -> bool:
    """ratio 값(2.2×, 2.14× 등)이 ground truth 값들 간 비율로 설명 가능한지."""
    truth_list = sorted(truth_values)
    for i, a in enumerate(truth_list):
        if a == 0:
            continue
        for b in truth_list[i:]:
            if b == 0:
                continue
            r = b / a if a != 0 else 0
            if abs(r - value) < tol or (value > 0 and abs(r - value) / value < 0.05):
                return True
    return False


def audit_numbers(report_path: str | Path, ground_truth_dirs: list[str | Path]) -> list[Finding]:
    """리포트의 모든 숫자를 ground truth와 대조."""
    report_path = Path(report_path)
    text = report_path.read_text(encoding="utf-8")

    if report_path.suffix.lower() in (".html", ".htm"):
        text = _strip_html(text)

    truth = _load_ground_truth(ground_truth_dirs)
    truth_values = _all_truth_values(truth)

    findings = []
    seen = set()

    # 일반적으로 안전한 숫자들 (작은 정수, 연도, 일반 표현)
    SAFE_INTEGERS = set(range(0, 21)) | {30, 40, 50, 60, 80, 100, 1000}
    SAFE_YEARS = {2024, 2025, 2026, 2027}
    SAFE_KNOWN = {0.5, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0}

    for match in _NUMBER_PATTERN.finditer(text):
        num_str, pct = match.group(1), match.group(2)
        try:
            value = float(num_str)
        except ValueError:
            continue

        # 안전 목록 스킵
        if int(value) == value and (
            int(value) in SAFE_INTEGERS or int(value) in SAFE_YEARS
        ):
            continue
        if value in SAFE_KNOWN:
            continue

        key = (value, pct)
        if key in seen:
            continue
        seen.add(key)

        # 컨텍스트 추출 (앞뒤 40자)
        ctx_start = max(0, match.start() - 40)
        ctx_end = min(len(text), match.end() + 40)
        context = text[ctx_start:ctx_end].replace("\n", " ").strip()

        # 외부 reference (가격, URL 등) 화이트리스트
        if any(marker in context for marker in ["$", "₩", "월", "년", "/년", "/월", "USD", "원/", "K+", "Mbps", "GB"]):
            continue

        # ratio 패턴 (×, x, 배) — 원본 text의 매치 직후 3자 검사
        next_chars = text[match.end():match.end() + 3]
        is_ratio = "×" in next_chars or "x " in next_chars or "배" in next_chars

        if is_ratio:
            if _check_ratio(value, truth_values):
                continue
            findings.append(Finding(
                severity="warning",
                location=str(report_path),
                claim=f"{num_str}× (ratio)",
                details=f"비율값이 ground truth로 설명 안 됨. 컨텍스트: ...{context}..."
            ))
            continue

        if not _is_close_match(value, truth_values):
            findings.append(Finding(
                severity="warning",
                location=str(report_path),
                claim=f"{num_str}{pct}",
                details=f"매칭되는 ground truth 값 없음. 컨텍스트: ...{context}..."
            ))

    return findings


def audit_pvalues(report_path: str | Path, recompute_targets: dict[str, dict] | None = None) -> list[Finding]:
    """p-value 패턴 발견 시 (recompute_targets 제공되면) 재계산 후 비교.

    recompute_targets: {"keyword_in_context": {"data_path": "...", "type": "ttest|binomial|fisher"}}
    """
    report_path = Path(report_path)
    text = report_path.read_text(encoding="utf-8")
    if report_path.suffix.lower() in (".html", ".htm"):
        text = _strip_html(text)

    findings = []

    for match in _PVALUE_PATTERN.finditer(text):
        claimed_p = float(match.group(1))
        ctx_start = max(0, match.start() - 80)
        ctx_end = min(len(text), match.end() + 80)
        context = text[ctx_start:ctx_end].replace("\n", " ").strip()

        # 위험 신호: p < 0.001인데 검증 불가
        if claimed_p < 0.001 and recompute_targets is None:
            findings.append(Finding(
                severity="info",
                location=str(report_path),
                claim=f"p={claimed_p}",
                details=f"매우 낮은 p-value 주장. 재계산 검증 권장. 컨텍스트: ...{context}..."
            ))

        if recompute_targets:
            # 컨텍스트에 키워드가 있으면 해당 데이터로 재계산
            for keyword, spec in recompute_targets.items():
                if keyword.lower() in context.lower():
                    actual_p = _recompute_pvalue(spec)
                    if actual_p is not None:
                        diff_ratio = abs(claimed_p - actual_p) / max(claimed_p, actual_p, 1e-6)
                        if diff_ratio > 0.5:  # 50% 이상 차이
                            findings.append(Finding(
                                severity="critical",
                                location=str(report_path),
                                claim=f"p={claimed_p}",
                                details=f"키워드 '{keyword}' 매치. 재계산값 p={actual_p:.4f} (차이 {diff_ratio*100:.0f}%). 컨텍스트: ...{context[:80]}..."
                            ))
    return findings


def _recompute_pvalue(spec: dict) -> float | None:
    """spec에 따라 p-value 재계산.

    spec 예시:
        {"data_path": "experiments/ablation/metric_4_variance.json",
         "type": "ttest_paired",
         "field_a": "arm_a_demo_only.case_entropies",
         "field_b": "arm_b_41r.case_entropies"}
    """
    try:
        from scipy import stats
    except ImportError:
        return None

    try:
        with open(spec["data_path"]) as f:
            data = json.load(f)

        def get_field(d, path):
            for p in path.split("."):
                d = d[p]
            return d

        if spec["type"] == "ttest_paired":
            a = get_field(data, spec["field_a"])
            b = get_field(data, spec["field_b"])
            _, p = stats.ttest_rel(b, a)
            return float(p)

        if spec["type"] == "binomial":
            k = get_field(data, spec["field_k"])
            n = get_field(data, spec["field_n"])
            alt = spec.get("alternative", "two-sided")
            return float(stats.binomtest(int(k), int(n), p=0.5, alternative=alt).pvalue)

        if spec["type"] == "fisher":
            a, b, c, d = (get_field(data, spec[f"field_{x}"]) for x in ["a", "b", "c", "d"])
            return float(stats.fisher_exact([[int(a), int(b)], [int(c), int(d)]]).pvalue)
    except Exception:
        logger.debug("p-value recompute failed", exc_info=True)
        return None

    return None


def audit_report(
    report_path: str | Path,
    ground_truth_dirs: list[str | Path],
    pvalue_recomputes: dict | None = None,
) -> list[Finding]:
    """전체 감사. 발견된 이슈 리스트 반환."""
    findings = []
    findings.extend(audit_numbers(report_path, ground_truth_dirs))
    findings.extend(audit_pvalues(report_path, pvalue_recomputes))
    findings.extend(audit_tagged_claims(report_path))
    return findings


# 명시적 claim 태그 패턴
# HTML: <span data-src="path/file.json:field.path">표시값</span>
# MD: [표시값]{src=path/file.json:field.path}
_HTML_CLAIM_PATTERN = re.compile(
    r'<[^>]+data-src="([^"]+)"[^>]*>([^<]+)</[^>]+>',
    re.IGNORECASE,
)
_MD_CLAIM_PATTERN = re.compile(
    r'\[([^\]]+)\]\{src=([^\}]+)\}',
)


def audit_tagged_claims(report_path: str | Path) -> list[Finding]:
    """명시적 claim 태그 (data-src) 검증.

    각 태그된 값을 ground truth 파일의 실제 값과 비교.
    """
    report_path = Path(report_path)
    text = report_path.read_text(encoding="utf-8")
    findings = []

    for pattern, html_format in [(_HTML_CLAIM_PATTERN, True), (_MD_CLAIM_PATTERN, False)]:
        for match in pattern.finditer(text):
            if html_format:
                src_spec, displayed = match.group(1), match.group(2)
            else:
                displayed, src_spec = match.group(1), match.group(2)

            if ":" not in src_spec:
                findings.append(Finding(
                    severity="warning",
                    location=str(report_path),
                    claim=displayed.strip(),
                    details=f"잘못된 src 형식: {src_spec} (file:field 필요)",
                ))
                continue

            file_part, field_part = src_spec.split(":", 1)
            file_path = Path(file_part)
            if not file_path.is_absolute():
                file_path = report_path.parent / file_part
                if not file_path.exists():
                    # 프로젝트 루트 기준 시도
                    file_path = Path(file_part)

            if not file_path.exists():
                findings.append(Finding(
                    severity="critical",
                    location=str(report_path),
                    claim=displayed.strip(),
                    details=f"src 파일 없음: {file_part}",
                ))
                continue

            try:
                with open(file_path) as f:
                    data = json.load(f)
                # field_path 따라가기
                actual = data
                for part in field_part.split("."):
                    if "[" in part and part.endswith("]"):
                        key, idx = part.split("[")
                        idx = int(idx[:-1])
                        actual = actual[key][idx] if key else actual[idx]
                    else:
                        actual = actual[part]
            except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
                findings.append(Finding(
                    severity="critical",
                    location=str(report_path),
                    claim=displayed.strip(),
                    details=f"src field 추적 실패 ({field_part}): {e}",
                ))
                continue

            # 표시값에서 숫자 추출
            displayed_clean = displayed.strip().rstrip("%").replace(",", "")
            try:
                displayed_num = float(displayed_clean)
            except ValueError:
                # 숫자 아님 → 문자열 비교
                if str(actual).strip() != displayed.strip():
                    findings.append(Finding(
                        severity="critical",
                        location=str(report_path),
                        claim=displayed.strip(),
                        details=f"src 값 '{actual}'와 표시값 '{displayed.strip()}' 불일치",
                    ))
                continue

            # 숫자 비교 (퍼센트 자동 변환)
            actual_num = float(actual)
            candidates = [actual_num, actual_num * 100, actual_num / 100]
            matched = any(abs(displayed_num - c) < 0.02 or
                          (c != 0 and abs(displayed_num - c) / abs(c) < 0.02)
                          for c in candidates)
            if not matched:
                findings.append(Finding(
                    severity="critical",
                    location=str(report_path),
                    claim=displayed.strip(),
                    details=f"태그된 출처값({actual_num}) ≠ 표시값({displayed_num}). src={src_spec}",
                ))
    return findings


def generate_audit_trail(
    report_path: str | Path,
    ground_truth_dirs: list[str | Path],
    output_path: str | Path | None = None,
) -> str:
    """리포트의 각 숫자 → 매치된 ground truth 위치 audit trail 생성.

    Returns: markdown 형식 audit trail. output_path 주면 파일 저장.
    """
    report_path = Path(report_path)
    text = report_path.read_text(encoding="utf-8")
    if report_path.suffix.lower() in (".html", ".htm"):
        text = _strip_html(text)

    truth = _load_ground_truth(ground_truth_dirs)

    SAFE_INTEGERS = set(range(0, 21)) | {30, 40, 50, 60, 80, 100, 1000}
    SAFE_YEARS = {2024, 2025, 2026, 2027}
    SAFE_KNOWN = {0.5, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0}

    rows = []
    seen = set()

    for match in _NUMBER_PATTERN.finditer(text):
        num_str, pct = match.group(1), match.group(2)
        try:
            value = float(num_str)
        except ValueError:
            continue

        if int(value) == value and (int(value) in SAFE_INTEGERS or int(value) in SAFE_YEARS):
            continue
        if value in SAFE_KNOWN:
            continue
        key = (value, pct)
        if key in seen:
            continue
        seen.add(key)

        ctx_start = max(0, match.start() - 30)
        ctx_end = min(len(text), match.end() + 30)
        context = text[ctx_start:ctx_end].replace("\n", " ").strip()

        if any(marker in context for marker in ["$", "₩", "월", "년", "K+", "Mbps", "GB"]):
            continue

        sources = _find_sources(value, truth, context=context)

        # 컨텍스트 단축
        if len(context) > 60:
            context = context[:57] + "..."

        if not sources:
            status = "❌ 출처 불명"
            src_str = "없음"
        else:
            # 정확 매치 우선
            exact_matches = [s for s in sources if "exact" in s[3]]
            if exact_matches:
                top = exact_matches[0]  # 컨텍스트 가장 관련 있는 1순위
                p, f, v, q = top
                if len(exact_matches) == 1:
                    status = "✓"
                else:
                    status = f"✓ ({len(exact_matches)}개 정확 매치)"
                src_str = f"`{Path(p).parent.name}/{Path(p).name}` → `{f}` = {v}"
                if len(exact_matches) > 1:
                    src_str += f" (+{len(exact_matches)-1}개 동일값)"
            else:
                status = f"⚠️ {len(sources)}개 근사 매치"
                src_str = "; ".join(
                    f"`{Path(p).parent.name}:{f.split('.')[-1] if '.' in f else f}` ({q})"
                    for p, f, v, q in sources[:2]
                )
                if len(sources) > 2:
                    src_str += f" ... 외 {len(sources)-2}개"

        rows.append({
            "value": f"{num_str}{pct}",
            "context": context,
            "status": status,
            "sources": src_str,
        })

    # Markdown 생성
    out_lines = [
        f"# Audit Trail — {report_path.name}",
        "",
        f"**리포트**: `{report_path}`",
        f"**감사일**: {Path(__file__).stat().st_mtime}",
        f"**총 검증 숫자**: {len(rows)}",
        f"**출처 매칭 성공**: {sum(1 for r in rows if r['status'].startswith('✓'))}",
        f"**다중 매치(애매)**: {sum(1 for r in rows if '⚠️' in r['status'])}",
        f"**출처 불명**: {sum(1 for r in rows if '❌' in r['status'])}",
        "",
        "| 값 | 컨텍스트 | 상태 | 출처 |",
        "|---|---|---|---|",
    ]
    for r in rows:
        ctx = r["context"].replace("|", "\\|")
        src = r["sources"].replace("|", "\\|")
        out_lines.append(f"| `{r['value']}` | {ctx} | {r['status']} | {src} |")

    out = "\n".join(out_lines)

    if output_path:
        Path(output_path).write_text(out, encoding="utf-8")

    return out


def print_audit_report(findings: list[Finding]) -> None:
    if not findings:
        print("✓ 발견된 이슈 없음.")
        return
    by_severity = {"critical": [], "warning": [], "info": []}
    for f in findings:
        by_severity.setdefault(f.severity, []).append(f)

    for sev in ["critical", "warning", "info"]:
        items = by_severity.get(sev, [])
        if not items:
            continue
        marker = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}[sev]
        print(f"\n{marker} {sev.upper()} ({len(items)}건)")
        for f in items[:20]:  # 최대 20건
            print(f"  - 주장: '{f.claim}'")
            print(f"    {f.details[:200]}")
        if len(items) > 20:
            print(f"  ... 외 {len(items) - 20}건")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m modules.hallucination_guard <report_path>            # check only")
        print("  python -m modules.hallucination_guard <report_path> --trail    # generate audit trail")
        sys.exit(1)

    report = sys.argv[1]

    # --trail 모드
    if len(sys.argv) > 2 and sys.argv[2] == "--trail":
        trail = generate_audit_trail(
            report,
            ground_truth_dirs=["reports/", "experiments/ablation/", "experiments/ab_validation/"],
            output_path=Path(report).with_suffix(".audit.md"),
        )
        print(trail[:3000])
        print(f"\n... full audit trail saved to {Path(report).with_suffix('.audit.md')}")
        sys.exit(0)

    # 기본 ground truth: reports/, experiments/
    findings = audit_report(
        report,
        ground_truth_dirs=[
            "reports/",
            "experiments/ablation/",
            "experiments/ab_validation/",
            "experiments/datasets/ga4_sample/",
            "experiments/datasets/open_bandit/",
        ],
        pvalue_recomputes={
            "엔트로피": {
                "data_path": "experiments/ablation/metric_4_variance.json",
                "type": "ttest_paired",
                "field_a": "arm_a_demo_only.case_entropies",
                "field_b": "arm_b_41r.case_entropies",
            },
            "구체성": {
                "data_path": "experiments/ablation/metric_3_specificity.json",
                "type": "binomial",
                "field_k": "head_to_head.arm_b_wins",
                "field_n": "total_cases",
                "alternative": "greater",
            },
        },
    )
    print_audit_report(findings)
    sys.exit(1 if any(f.severity == "critical" for f in findings) else 0)
