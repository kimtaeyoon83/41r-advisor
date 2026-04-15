"""M5 Report Generator — 비즈니스 인사이트 리포트 + lineage.json 생성.

파이프라인: 세션 로그 → [분석 레이어] → 비즈니스 리포트
"""

from __future__ import annotations

import html
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from persona_agent._internal.core import events_log
from persona_agent._internal.core.workspace import get_workspace
from persona_agent._internal.reports.version_manager import get_lineage as get_prompt_lineage
from persona_agent._internal.reports.report_analyzer import analyze_sessions

logger = logging.getLogger(__name__)

_REPORTS_DIR = get_workspace().reports_dir


def generate_report(
    session_logs: list[dict],
    personas: list[str],
    comparison_mode: str = "ab",
) -> str:
    """리포트 생성.

    Returns: report_id
    """
    report_id = f"rpt_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
    report_dir = _REPORTS_DIR / report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    # 사이트별로 세션 그룹핑
    site_groups: dict[str, list[dict]] = {}
    for s in session_logs:
        url = s.get("url", "unknown")
        site_groups.setdefault(url, []).append(s)

    # 사이트별 LLM 분석
    analyses: dict[str, dict] = {}
    for url, sessions in site_groups.items():
        analyses[url] = analyze_sessions(sessions, url)

    # HTML 생성
    report_html = _render_report(report_id, generated_at, analyses, session_logs, personas)

    # 파일 저장
    html_path = report_dir / "report.html"
    html_path.write_text(report_html, encoding="utf-8")

    try:
        from weasyprint import HTML
        HTML(string=report_html).write_pdf(str(report_dir / "report.pdf"))
    except ImportError:
        logger.debug("weasyprint 미설치, PDF 생성 스킵 (HTML만 저장됨)")

    # lineage.json
    lineage = _build_lineage(report_id, generated_at, session_logs, personas)
    with open(report_dir / "lineage.json", "w") as f:
        json.dump(lineage, f, ensure_ascii=False, indent=2)

    # 분석 결과 원본 저장
    with open(report_dir / "analysis.json", "w") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)

    events_log.append({
        "type": "report_generated",
        "report_id": report_id,
        "personas": personas,
        "sessions": [s.get("session_id", "") for s in session_logs],
    })

    return report_id


def _render_report(
    report_id: str,
    generated_at: str,
    analyses: dict[str, dict],
    session_logs: list[dict],
    personas: list[str],
) -> str:
    """분석 결과를 비즈니스 리포트 HTML로 렌더링."""

    sections = []
    for url, analysis in analyses.items():
        sections.append(_render_site_section(url, analysis, session_logs))

    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>41R Predictive Report — {report_id}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 40px 24px; }}
  h1 {{ font-size: 28px; color: #111; margin-bottom: 8px; }}
  h2 {{ font-size: 22px; color: #2563eb; margin: 40px 0 16px; padding-bottom: 8px; border-bottom: 2px solid #2563eb; }}
  h3 {{ font-size: 18px; color: #374151; margin: 24px 0 12px; }}
  .meta {{ color: #6b7280; font-size: 14px; margin-bottom: 32px; }}
  .exec-summary {{ background: #f0f9ff; border-left: 4px solid #2563eb; padding: 20px; margin: 24px 0; border-radius: 0 8px 8px 0; font-size: 16px; }}
  .prediction-box {{ background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 20px; margin: 16px 0; }}
  .prediction-box.low {{ background: #fef2f2; border-color: #fca5a5; }}
  .prediction-box.medium {{ background: #fffbeb; border-color: #fcd34d; }}
  .segment {{ background: #fafafa; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 12px 0; }}
  .segment-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
  .segment-name {{ font-weight: 700; font-size: 16px; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: 600; }}
  .badge-complete {{ background: #dcfce7; color: #166534; }}
  .badge-abandoned {{ background: #fee2e2; color: #991b1b; }}
  .badge-max {{ background: #fef3c7; color: #92400e; }}
  .issue {{ padding: 12px 16px; margin: 8px 0; border-radius: 6px; }}
  .issue-critical {{ background: #fef2f2; border-left: 4px solid #ef4444; }}
  .issue-high {{ background: #fff7ed; border-left: 4px solid #f97316; }}
  .issue-medium {{ background: #fffbeb; border-left: 4px solid #eab308; }}
  .issue-low {{ background: #f0f9ff; border-left: 4px solid #3b82f6; }}
  .recommendation {{ padding: 12px 16px; margin: 8px 0; background: #f0fdf4; border-left: 4px solid #22c55e; border-radius: 0 6px 6px 0; }}
  .priority {{ font-weight: 700; color: #166534; margin-right: 8px; }}
  .funnel {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
  .funnel th {{ background: #f3f4f6; padding: 10px 14px; text-align: left; font-weight: 600; border-bottom: 2px solid #d1d5db; }}
  .funnel td {{ padding: 10px 14px; border-bottom: 1px solid #e5e7eb; }}
  .footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 13px; color: #9ca3af; }}
  .actions-list {{ list-style: none; padding: 0; }}
  .actions-list li {{ padding: 4px 0; }}
  .actions-list li::before {{ content: "→ "; color: #6b7280; }}
</style>
</head>
<body>

<h1>41R Predictive A/B Report</h1>
<div class="meta">
  Report ID: {report_id} | Generated: {generated_at[:19]} UTC | Personas: {', '.join(personas)}
</div>

{body}

<div class="footer">
  <p>Generated by 41R Persona Market. 모든 관찰은 콘텐츠 해시로 추적 가능합니다.</p>
  <p>Lineage: {report_id}/lineage.json | Analysis: {report_id}/analysis.json</p>
</div>

</body>
</html>"""


def _render_site_section(url: str, analysis: dict, session_logs: list[dict]) -> str:
    """사이트 하나의 분석 결과 렌더링."""
    if analysis.get("raw"):
        return f"""<h2>{_e(url)}</h2><div class="exec-summary">{_e(analysis.get('executive_summary', ''))}</div>"""

    parts = []

    # Executive Summary
    summary = analysis.get("executive_summary", "")
    parts.append(f'<h2>{_e(url)}</h2>')
    parts.append(f'<div class="exec-summary">{_e(summary)}</div>')

    # Prediction
    pred = analysis.get("prediction", {})
    if pred:
        signal = pred.get("estimated_conversion_signal", "보통")
        css_class = "low" if signal == "낮음" else ("medium" if signal == "보통" else "")
        parts.append(f"""
        <div class="prediction-box {css_class}">
          <h3>전환 예측</h3>
          <p><strong>전환 신호:</strong> {_e(signal)} | <strong>신뢰도:</strong> {_e(pred.get('confidence', ''))}</p>
          <p>{_e(pred.get('reasoning', ''))}</p>
        </div>""")

    # Segment Analysis
    segments = analysis.get("segment_analysis", [])
    if segments:
        parts.append("<h3>세그먼트별 행동 분석</h3>")
        for seg in segments:
            outcome = seg.get("outcome", "")
            badge_class = "badge-complete" if "완료" in outcome else ("badge-abandoned" in outcome and "badge-abandoned" or "badge-max")
            parts.append(f"""
            <div class="segment">
              <div class="segment-header">
                <span class="segment-name">{_e(seg.get('segment', ''))}</span>
                <span class="badge {badge_class}">{_e(outcome)} · {seg.get('turns_used', '?')}턴</span>
              </div>
              <p>{_e(seg.get('behavior_summary', ''))}</p>
              <p><strong>주요 행동:</strong></p>
              <ul class="actions-list">
                {''.join(f'<li>{_e(a)}</li>' for a in seg.get('key_actions', []))}
              </ul>
              {f'<p><strong>마찰 지점:</strong> {", ".join(_e(f) for f in seg.get("friction_points", []))}</p>' if seg.get('friction_points') else ''}
              {f'<p><strong>감정:</strong> {_e(seg.get("sentiment", ""))}</p>' if seg.get('sentiment') else ''}
            </div>""")

    # UX Issues
    issues = analysis.get("ux_issues", [])
    if issues:
        parts.append("<h3>발견된 UX 문제</h3>")
        for issue in issues:
            sev = issue.get("severity", "medium")
            parts.append(f"""
            <div class="issue issue-{sev}">
              <strong>[{sev.upper()}]</strong> {_e(issue.get('issue', ''))}
              <br><em>근거:</em> {_e(issue.get('evidence', ''))}
              <br><em>개선:</em> {_e(issue.get('recommendation', ''))}
            </div>""")

    # Conversion Funnel
    funnel = analysis.get("conversion_funnel", [])
    if funnel:
        parts.append("<h3>전환 퍼널</h3>")
        parts.append("""<table class="funnel">
          <tr><th>단계</th><th>도달</th><th>이탈</th><th>이탈 이유</th></tr>""")
        for stage in funnel:
            reached = ", ".join(stage.get("reached_by", []))
            dropped = ", ".join(stage.get("dropped_at", []))
            parts.append(f"""<tr>
              <td>{_e(stage.get('stage', ''))}</td>
              <td>{_e(reached)}</td>
              <td>{_e(dropped)}</td>
              <td>{_e(stage.get('drop_reason', ''))}</td>
            </tr>""")
        parts.append("</table>")

    # Recommendations
    recs = analysis.get("actionable_recommendations", [])
    if recs:
        parts.append("<h3>개선 제안 (우선순위순)</h3>")
        for rec in recs:
            parts.append(f"""
            <div class="recommendation">
              <span class="priority">#{rec.get('priority', '?')}</span>
              {_e(rec.get('recommendation', ''))}
              <br><em>예상 효과:</em> {_e(rec.get('expected_impact', ''))} | <em>난이도:</em> {_e(rec.get('effort', ''))}
            </div>""")

    return "\n".join(parts)


def _e(text: str) -> str:
    """HTML escape."""
    return html.escape(str(text)) if text else ""


def _build_lineage(
    report_id: str,
    generated_at: str,
    session_logs: list[dict],
    personas: list[str],
) -> dict:
    """lineage.json — 재현성 정보."""
    prompt_lineage = get_prompt_lineage(report_id)

    persona_snapshots = {}
    for pid in personas:
        try:
            from persona_agent._internal.persona.persona_store import read_persona
            state = read_persona(pid)
            last_obs = state.observations[-1].get("obs_id") if state.observations else None
            active_reflections = [
                r.get("refl_id", "") for r in state.reflections
                if r.get("status") != "deprecated"
            ]
            persona_snapshots[pid] = {
                "soul_version": state.soul_version,
                "observation_count": len(state.observations),
                "reflection_count": len(state.reflections),
                "last_observation": last_obs,
                "active_reflections": active_reflections,
            }
        except Exception:
            logger.debug("Failed to build persona snapshot for %s", pid, exc_info=True)
            persona_snapshots[pid] = {"error": "could not load"}

    return {
        "report_id": report_id,
        "generated_at": generated_at,
        "stack_versions": prompt_lineage,
        "persona_snapshots": persona_snapshots,
        "model_routing": _get_model_routing_summary(),
        "sessions": [s.get("session_id", "") for s in session_logs],
    }


def _get_model_routing_summary() -> dict:
    try:
        from core.provider_router import get_tier_config
        roles = ["plan_generation", "decision_judge", "tool_selection", "page_summarizer"]
        summary = {}
        for role in roles:
            config = get_tier_config(role)
            entry = config["model"]
            if config.get("advisor"):
                entry += f" (+{config['advisor']['model']} advisor)"
            summary[role] = entry
        return summary
    except Exception:
        return {}
