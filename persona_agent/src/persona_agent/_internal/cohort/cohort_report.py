"""Cohort Report — 코호트 세션 결과를 분포 지표로 집계.

출력:
- 전환율 (± 95% CI)
- 평균 턴 수 (engagement proxy)
- 이탈 지점 히스토그램
- 세그먼트 하위 cluster (성향 축 기반)
- Trait × Outcome 상관 분석
"""

from __future__ import annotations

import html
import json
import logging
import math
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from persona_agent._internal.analysis.benchmark_loader import diagnose_cohort
    _BENCHMARK_AVAILABLE = True
except ImportError as e:
    logger.warning("benchmark_loader 사용 불가 (%s) — Reality Check 비활성화", e)
    _BENCHMARK_AVAILABLE = False

from persona_agent._internal.core.workspace import get_workspace

_REPORTS_DIR: Path | None = None


def _get_reports_dir() -> Path:
    global _REPORTS_DIR
    if _REPORTS_DIR is None:
        _REPORTS_DIR = get_workspace().reports_dir
    return _REPORTS_DIR


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion.

    k = 성공 수, n = 전체, z = 1.96 → 95% CI
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _classify_outcome(outcome: str) -> str:
    """outcome을 표준 bucket으로 정규화."""
    outcome = (outcome or "").lower()
    if "complete" in outcome:
        return "converted"
    if "abandon" in outcome or "drop" in outcome or "error" in outcome or "timeout" in outcome:
        return "abandoned"
    if "partial" in outcome or "max_turns" in outcome:
        return "partial"
    return "unknown"


def _bucket_histogram(values: list, labels: list[str]) -> dict[str, int]:
    """값 리스트 → {label: count}."""
    hist = {k: 0 for k in labels}
    for v in values:
        if v in hist:
            hist[v] += 1
        else:
            hist.setdefault("other", 0)
            hist["other"] += 1
    return hist


def _trait_outcome_correlation(results: list[dict]) -> dict:
    """각 trait와 outcome/전환확률의 피어슨 상관계수.

    1순위: conversion_probability (연속 변수)
    2순위: converted 이진화
    """
    # conversion_probability 우선 사용 (세밀한 신호)
    probs = []
    has_probs = True
    for r in results:
        p = r.get("conversion_probability")
        if p is None:
            has_probs = False
            break
        probs.append(float(p))

    if has_probs and len(set(probs)) > 1:
        target_values = probs
        target_label = "conversion_probability"
    else:
        converted = [1 if _classify_outcome(r.get("outcome", "")) == "converted" else 0 for r in results]
        if len(set(converted)) == 1:
            return {"note": "outcome/probability variance=0, correlation undefined"}
        target_values = converted
        target_label = "converted_binary"

    traits = {}
    for r in results:
        t = r.get("persona_traits", {}) or {}
        for k, v in t.items():
            traits.setdefault(k, []).append(float(v))

    correlations = {"_target": target_label}
    for trait, values in traits.items():
        if len(values) != len(target_values):
            continue
        correlations[trait] = round(_pearson(values, target_values), 3)
    return correlations


def _pearson(x: list[float], y: list[int]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den_x = math.sqrt(sum((v - mean_x) ** 2 for v in x))
    den_y = math.sqrt(sum((v - mean_y) ** 2 for v in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def aggregate_cohort(cohort_result: dict) -> dict:
    """코호트 실행 결과를 집계 지표로 변환."""
    results = cohort_result.get("results", [])
    n = len(results)

    if n == 0:
        return {"error": "empty results"}

    # 전환율
    buckets = [_classify_outcome(r.get("outcome", "")) for r in results]
    converted = buckets.count("converted")
    abandoned = buckets.count("abandoned")
    partial = buckets.count("partial")
    unknown = buckets.count("unknown")

    conv_rate = converted / n
    ci_lo, ci_hi = _wilson_ci(converted, n)

    # 평균 턴 수 (engagement)
    turns = [r.get("predicted_turns") or r.get("total_turns") or 0 for r in results]
    turns = [t for t in turns if t and t > 0]
    avg_turns = statistics.mean(turns) if turns else 0
    median_turns = statistics.median(turns) if turns else 0

    # 이탈 지점 히스토그램
    drop_points = [r.get("drop_point") for r in results if r.get("drop_point")]
    drop_hist: dict[str, int] = {}
    for dp in drop_points:
        if dp:
            drop_hist[dp] = drop_hist.get(dp, 0) + 1

    # Frustration points 빈도
    frustration_freq: dict[str, int] = {}
    for r in results:
        for fp in (r.get("frustration_points") or []):
            frustration_freq[fp] = frustration_freq.get(fp, 0) + 1

    # Trait × outcome 상관
    correlations = _trait_outcome_correlation(results)

    # 예측 확률 분포 (text mode만)
    probs = [r.get("conversion_probability") for r in results if r.get("conversion_probability") is not None]
    probs = [float(p) for p in probs]
    prob_stats = {}
    if probs:
        prob_stats = {
            "mean": round(statistics.mean(probs), 3),
            "median": round(statistics.median(probs), 3),
            "stdev": round(statistics.stdev(probs), 3) if len(probs) > 1 else 0,
            "min": round(min(probs), 3),
            "max": round(max(probs), 3),
        }

    aggregation = {
        "n_total": n,
        "n_converted": converted,
        "n_abandoned": abandoned,
        "n_partial": partial,
        "n_unknown": unknown,
        "conversion_rate": round(conv_rate, 3),
        "conversion_rate_ci95": (round(ci_lo, 3), round(ci_hi, 3)),
        "engagement": {
            "avg_turns": round(avg_turns, 2),
            "median_turns": round(median_turns, 2),
            "sample_n": len(turns),
        },
        "drop_point_histogram": dict(sorted(drop_hist.items(), key=lambda x: -x[1])),
        "frustration_frequency": dict(sorted(frustration_freq.items(), key=lambda x: -x[1])[:10]),
        "trait_outcome_correlations": correlations,
        "conversion_probability_dist": prob_stats,
    }

    # Reality Check 자동 첨부 (외부 baseline과 비교) — 절대 수치 신뢰도 표시
    if _BENCHMARK_AVAILABLE:
        try:
            aggregation["reality_check"] = diagnose_cohort(aggregation)
        except Exception:
            logger.warning("Reality Check 생성 실패 (외부 데이터 없음 또는 형식 오류)", exc_info=True)
            aggregation["reality_check"] = {"baseline_sources": [], "comparisons": [],
                                            "summary_text": "Reality Check 비활성화 (baseline 로드 실패)"}
    else:
        aggregation["reality_check"] = {"baseline_sources": [], "comparisons": [],
                                        "summary_text": "Reality Check 비활성화 (benchmark_loader 미사용)"}

    return aggregation


def _try_llm_analysis(cohort_result: dict) -> str | None:
    """opt-in: LLM이 cohort 결과를 인사이트 텍스트로 변환. 비용 ~$0.05.

    cohort_result.get('analyze') is True 일 때만 호출.
    """
    if not cohort_result.get("analyze"):
        return None
    try:
        from persona_agent._internal.reports.report_analyzer import analyze_sessions
        sessions = cohort_result.get("sessions") or cohort_result.get("results", [])
        site_url = cohort_result.get("url", "")
        if not sessions:
            return None
        result = analyze_sessions(sessions, site_url)
        # report_analyzer 결과를 짧은 텍스트로
        if isinstance(result, dict):
            summary = result.get("summary") or result.get("insights") or json.dumps(result, ensure_ascii=False)[:500]
            return str(summary)
        return str(result)[:1000]
    except Exception as e:
        logger.warning("LLM 분석 실패: %s", e)
        return None


def render_cohort_html(
    cohort_result: dict,
    aggregation: dict,
    report_id: str | None = None,
) -> tuple[str, str]:
    """코호트 리포트 HTML 렌더. Returns: (report_id, report_dir path)."""
    if report_id is None:
        report_id = f"cohort_rpt_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"

    report_dir = _get_reports_dir() / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    _e = html.escape

    ci_lo, ci_hi = aggregation["conversion_rate_ci95"]
    conv_pct = round(aggregation["conversion_rate"] * 100, 1)
    ci_lo_pct = round(ci_lo * 100, 1)
    ci_hi_pct = round(ci_hi * 100, 1)

    # Segment divergence 계산: correlations 절댓값 평균 (숫자 값만)
    corrs = aggregation.get("trait_outcome_correlations", {})
    numeric_corrs = {k: v for k, v in corrs.items() if isinstance(v, (int, float))}
    if numeric_corrs and "note" not in corrs:
        avg_abs_corr = sum(abs(v) for v in numeric_corrs.values()) / len(numeric_corrs)
    else:
        avg_abs_corr = 0

    if avg_abs_corr > 0.3:
        divergence_label = "높음"
        divergence_css = "signal-low"
        divergence_advice = "세그먼트별 variant 설계 필수"
    elif avg_abs_corr > 0.15:
        divergence_label = "중간"
        divergence_css = "signal-medium"
        divergence_advice = "A/B 테스트 + 세그먼트 분석"
    else:
        divergence_label = "낮음"
        divergence_css = "signal-high"
        divergence_advice = "단일 A/B 테스트로 충분"

    # Drop points rows
    drop_rows = "".join(
        f"<tr><td>{_e(dp)}</td><td>{cnt}</td><td>{round(cnt / aggregation['n_total'] * 100, 1)}%</td></tr>"
        for dp, cnt in aggregation["drop_point_histogram"].items()
    ) or "<tr><td colspan='3' style='color:#64748b'>기록된 이탈 지점 없음</td></tr>"

    # Frustration rows
    frust_rows = "".join(
        f"<tr><td>{_e(fp)}</td><td>{cnt}</td><td>{round(cnt / aggregation['n_total'] * 100, 1)}%</td></tr>"
        for fp, cnt in aggregation["frustration_frequency"].items()
    ) or "<tr><td colspan='3' style='color:#64748b'>기록된 마찰 포인트 없음</td></tr>"

    # Correlation rows
    if "note" in corrs:
        corr_rows = f"<tr><td colspan='3' style='color:#64748b'>{corrs['note']}</td></tr>"
    else:
        target_label = corrs.get("_target", "outcome")
        corr_rows = "".join(
            f"<tr><td>{_e(k)}</td><td>{v:+.3f}</td><td>{'강한 상관' if abs(v) > 0.5 else '보통' if abs(v) > 0.3 else '약한 상관'}</td></tr>"
            for k, v in sorted(numeric_corrs.items(), key=lambda x: -abs(x[1]))
        )
        corr_rows = f"<tr><td colspan='3' style='background:#f1f5f9; font-size:12px; color:#64748b;'>Target: {_e(target_label)}</td></tr>" + corr_rows

    # LLM analyzer (opt-in via cohort_result["analyze"]=True)
    llm_insight = _try_llm_analysis(cohort_result)
    llm_html = ""
    if llm_insight:
        llm_html = f"""
        <div class="section">
          <h2>AI 해석 (report_analyzer)</h2>
          <div class="exec" style="white-space:pre-wrap; font-size:14px;">{_e(llm_insight)}</div>
          <p style="font-size:12px; color:#94a3b8;">※ LLM 생성 인사이트 — 정성 분석. 통계 수치는 위 표 참조.</p>
        </div>"""

    # Reality Check (외부 baseline 비교)
    rc = aggregation.get("reality_check", {})
    rc_html = ""
    if rc.get("comparisons"):
        rc_rows = "".join(
            f"<tr><td>{_e(c.get('label',''))}</td>"
            f"<td>{c.get('sim','-')}</td>"
            f"<td>{c.get('real','-')}</td>"
            f"<td>{c.get('factor','-')}×</td>"
            f"<td>{_e(c.get('trust','-'))}</td></tr>"
            for c in rc["comparisons"]
        )
        sources_str = "; ".join(_e(s) for s in rc.get("baseline_sources", []))
        rc_html = f"""
        <div class="section">
          <h2>Reality Check (외부 baseline 비교)</h2>
          <div class="exec">{_e(rc.get('summary_text',''))}</div>
          <table>
            <tr><th>지표</th><th>시뮬</th><th>실제</th><th>비율</th><th>신뢰도</th></tr>
            {rc_rows}
          </table>
          <p style="color:#64748b; font-size:13px; margin-top:8px;">
            Baseline 출처: {sources_str}<br>
            ⚠️ Baseline은 Google Merchandise Store / ZOZOTOWN 데이터로, 본 사이트와 사용자 구성이 다릅니다.
            절대 수치가 아닌 <strong>상대 비교</strong> 용도로만 사용하세요.
          </p>
        </div>
        """

    # Probability stats
    prob_stats = aggregation.get("conversion_probability_dist", {})
    prob_html = ""
    if prob_stats:
        prob_html = f"""
        <h3>개인별 전환 확률 분포</h3>
        <div class="stats">
          <div class="stat-card"><div class="stat-number">{prob_stats['mean']}</div><div class="stat-label">평균 확률</div></div>
          <div class="stat-card"><div class="stat-number">{prob_stats['median']}</div><div class="stat-label">중앙값</div></div>
          <div class="stat-card"><div class="stat-number">{prob_stats['stdev']}</div><div class="stat-label">표준편차</div></div>
        </div>
        <p style="color:#64748b; font-size:14px;">분포 폭 {prob_stats['min']} ~ {prob_stats['max']}. 표준편차가 클수록 세그먼트 분기가 강함.</p>
        """

    html_out = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>41R Cohort Report — {_e(report_id)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; color: #1a1a1a; line-height: 1.7; background: #f8fafc; }}
  .cover {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); color: white; padding: 60px 40px; text-align: center; }}
  .cover h1 {{ font-size: 30px; margin-bottom: 10px; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 32px 24px; }}
  .section {{ background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 28px; margin-bottom: 20px; }}
  h2 {{ font-size: 20px; color: #1e293b; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }}
  h3 {{ font-size: 16px; color: #374151; margin: 20px 0 10px; }}
  .exec {{ background: #f0f9ff; border-left: 4px solid #2563eb; padding: 18px 20px; border-radius: 0 8px 8px 0; margin: 14px 0; font-size: 15px; }}
  .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 16px 0; }}
  .stat-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center; }}
  .stat-number {{ font-size: 26px; font-weight: 800; color: #2563eb; }}
  .stat-label {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
  th {{ background: #f1f5f9; padding: 10px 14px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #e2e8f0; }}
  .signal {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 600; }}
  .signal-high {{ background: #dcfce7; color: #166534; }}
  .signal-medium {{ background: #fef3c7; color: #92400e; }}
  .signal-low {{ background: #fee2e2; color: #991b1b; }}
</style>
</head>
<body>
<div class="cover">
  <h1>Cohort Simulation Report</h1>
  <p>Segment: <strong>{_e(cohort_result.get('task', '')[:60])}</strong></p>
  <p style="color:#94a3b8; margin-top:8px;">URL: {_e(cohort_result.get('url', ''))}</p>
</div>
<div class="container">

<div class="section">
  <h2>핵심 지표</h2>
  <div class="exec">
    <strong>N={aggregation['n_total']}명 코호트 시뮬레이션 결과</strong><br>
    전환율 <strong>{conv_pct}%</strong> (95% CI: {ci_lo_pct}~{ci_hi_pct}%) · 평균 {aggregation['engagement']['avg_turns']}턴 engagement ·
    세그먼트 분기 <span class="signal {divergence_css}">{divergence_label}</span> → {divergence_advice}
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-number">{conv_pct}%</div>
      <div class="stat-label">전환율 ({aggregation['n_converted']}/{aggregation['n_total']})</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{aggregation['engagement']['avg_turns']}</div>
      <div class="stat-label">평균 턴 수</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{round(aggregation['n_abandoned'] / aggregation['n_total'] * 100, 1)}%</div>
      <div class="stat-label">이탈률 ({aggregation['n_abandoned']}명)</div>
    </div>
  </div>
</div>

<div class="section">
  <h2>이탈 분석</h2>
  <h3>이탈 지점 히스토그램</h3>
  <table><tr><th>이탈 지점</th><th>건수</th><th>비율</th></tr>{drop_rows}</table>

  <h3>좌절 포인트 빈도 (Top 10)</h3>
  <table><tr><th>마찰 지점</th><th>언급 수</th><th>비율</th></tr>{frust_rows}</table>
</div>

<div class="section">
  <h2>성향 × 전환 상관 분석</h2>
  <p style="color:#64748b; font-size:14px;">각 성향 축이 전환 여부와 얼마나 상관 있는지. 절댓값 > 0.3 이면 의미 있는 상관, > 0.5면 강한 상관.</p>
  <table><tr><th>성향 축</th><th>상관계수</th><th>강도</th></tr>{corr_rows}</table>

  {prob_html}
</div>

{llm_html}

{rc_html}

<div class="section">
  <h2>세그먼트 분기 진단</h2>
  <div class="exec">
    평균 성향 상관 절댓값 <strong>{avg_abs_corr:.3f}</strong> → 분기 <strong>{divergence_label}</strong><br>
    권고: <strong>{divergence_advice}</strong>
  </div>
</div>

<div class="section" style="color:#64748b; font-size:13px;">
  <p>Report ID: {_e(report_id)} · Generated: {datetime.now(timezone.utc).isoformat()[:19]} UTC</p>
  <p>Cohort: {_e(cohort_result.get('cohort_run_id', ''))} · Mode: {_e(cohort_result.get('mode', ''))} · Personas: {aggregation['n_total']}</p>
</div>

</div>
</body>
</html>"""

    out_path = report_dir / "cohort_report.html"
    out_path.write_text(html_out, encoding="utf-8")

    # aggregation.json 저장
    agg_path = report_dir / "aggregation.json"
    with open(agg_path, "w") as f:
        json.dump(aggregation, f, ensure_ascii=False, indent=2)

    logger.info("Cohort report → %s", out_path)
    return report_id, str(report_dir)


def generate_cohort_report(cohort_result_path: str | Path) -> str:
    """코호트 결과 JSON → 리포트 생성 (one-shot)."""
    with open(cohort_result_path) as f:
        result = json.load(f)
    agg = aggregate_cohort(result)
    report_id, report_dir = render_cohort_html(result, agg)
    return report_id


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python -m modules.cohort_report <cohort_result.json>")
        sys.exit(1)
    rid = generate_cohort_report(sys.argv[1])
    print(f"Report: {rid}")
