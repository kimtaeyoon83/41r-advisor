"""41R E2E 테스트 — 실제 LLM + 로컬 브라우저로 전체 파이프라인 실행."""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 로드
load_dotenv()

from modules.persona_store import create_persona, read_persona, list_personas
from modules.browser_runner import get_runner
from modules.agent_loop import run_session
from modules.report_gen import generate_report
from modules.review_agent import inspect, evaluate
from core.events_log import read_events


def setup_personas():
    """테스트용 페르소나 2명 생성."""
    personas = list_personas()

    if "p_impulsive" not in personas:
        create_persona("p_impulsive", """---
name: 충동적 쇼퍼 민수
age: 28
occupation: 마케터
timing:
  patience_seconds: 2.0
  reading_wpm: 400
  decision_latency_sec: 0.5
  loading_tolerance: strict
---

나는 빠르게 결정하고 빠르게 행동한다.
페이지가 2초 안에 안 뜨면 바로 닫아버린다.
리뷰는 거의 안 보고, 가격과 메인 이미지만 보고 바로 결정한다.
장바구니에 넣고 결제까지 3번 이상 클릭해야 하면 귀찮아서 이탈한다.
할인 배너가 눈에 띄면 바로 클릭한다.
""")
        print("[+] Created persona: p_impulsive (충동적 쇼퍼)")

    if "p_cautious" not in personas:
        create_persona("p_cautious", """---
name: 신중한 리서처 지영
age: 35
occupation: 회계사
timing:
  patience_seconds: 10.0
  reading_wpm: 200
  decision_latency_sec: 3.0
  loading_tolerance: patient
---

나는 구매 전에 꼼꼼하게 조사한다.
상품 설명을 끝까지 읽고, 리뷰를 최소 3개는 확인한다.
가격 비교를 위해 다른 사이트도 확인하는 편이다.
반품 정책과 배송 정보를 반드시 확인한다.
성급하게 결제하지 않고, 장바구니에 담아두고 하루 정도 고민한다.
의심스러운 사이트에서는 절대 결제하지 않는다.
""")
        print("[+] Created persona: p_cautious (신중한 리서처)")


def test_browser_basic():
    """브라우저 기본 동작 확인."""
    print("\n=== 1. Browser Basic Test ===")
    runner = get_runner()

    handle = runner.start_session("https://example.com", {"persona_id": "p_impulsive"})
    state = runner.get_state(handle)
    print(f"  URL: {state.url}")
    print(f"  Title: {state.title}")
    print(f"  A11y elements: {len(state.a11y_tree)}")

    # click
    result = runner.run_action(handle, {"tool": "click", "params": {"target": "Learn more 링크"}})
    print(f"  Click: ok={result.ok}, dur={result.duration_ms:.0f}ms")

    state2 = runner.get_state(handle)
    print(f"  Navigated: {state2.url}")

    runner.end_session(handle)
    print("  PASS")


def test_llm_integration():
    """LLM 호출 기본 테스트."""
    print("\n=== 2. LLM Integration Test ===")
    from core.provider_router import call

    # LOW tier (Haiku)
    response = call(
        "page_summarizer",
        [{"role": "user", "content": '{"url": "https://example.com", "title": "Example", "a11y_tree": [{"role": "heading", "name": "Example Domain"}]}'}],
        system="You are a page summarizer. Return JSON.",
        max_tokens=500,
    )
    print(f"  LOW (Haiku): model={response['model']}, tokens={response['usage']}")
    print(f"  Response: {response['content'][:150]}")
    print("  PASS")


def test_e2e_session():
    """전체 E2E 세션 — 페르소나가 실제 사이트를 탐색."""
    print("\n=== 3. E2E Session Test ===")
    print("  Running session with p_impulsive on https://example.com ...")

    try:
        log = run_session(
            persona_id="p_impulsive",
            url="https://example.com",
            task="이 웹사이트를 탐색하고 유용한 정보를 찾아라. 메인 페이지를 읽고, 링크를 클릭하고, 사이트의 목적을 파악해라.",
        )
        print(f"  Session: {log.session_id}")
        print(f"  Outcome: {log.outcome}")
        print(f"  Turns: {log.total_turns}")
        for t in log.turns[:3]:
            tool = t.get("tool", {})
            dec = t.get("decision", {})
            print(f"    Turn {t['turn']}: {tool.get('tool','')} — {dec.get('reason','')[:60]}")
        return log
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_review(session_id: str):
    """Review Agent로 세션 분석."""
    print(f"\n=== 4. Review Agent Test (session: {session_id}) ===")

    view = inspect(session_id)
    print(f"  Issues: {len(view['issues'])}")
    print(f"  Quality Gate: {'PASS' if view['quality_gate']['pass'] else 'FAIL'}")
    for k, v in view["quality_gate"].items():
        if k != "pass":
            print(f"    {k}: {'✓' if v else '✗'}")

    score = evaluate(session_id)
    print(f"  Consistency Score: {score['scores']['overall']:.2f}")
    if score["findings"]:
        for f in score["findings"]:
            print(f"    Finding: {f}")
    print("  PASS")


def test_report(session_log):
    """리포트 생성."""
    print("\n=== 5. Report Generation Test ===")

    log_dict = {
        "session_id": session_log.session_id,
        "persona_id": session_log.persona_id,
        "url": session_log.url,
        "task": session_log.task,
        "outcome": session_log.outcome,
        "total_turns": session_log.total_turns,
        "turns": session_log.turns,
    }

    report_id = generate_report([log_dict], ["p_impulsive"], "single")
    print(f"  Report: {report_id}")

    report_dir = Path("reports") / report_id
    files = list(report_dir.glob("*"))
    print(f"  Files: {[f.name for f in files]}")

    lineage = json.loads((report_dir / "lineage.json").read_text())
    print(f"  Lineage prompts: {list(lineage['stack_versions'].keys())}")
    print(f"  Model routing: {lineage['model_routing']}")
    print("  PASS")


def test_events():
    """이벤트 로그 확인."""
    print("\n=== 6. Events Log Check ===")
    events = read_events()
    types = {}
    for e in events:
        t = e.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    print(f"  Total events: {len(events)}")
    for t, c in sorted(types.items()):
        print(f"    {t}: {c}")
    print("  PASS")


if __name__ == "__main__":
    print("=" * 60)
    print("41R E2E Test Suite")
    print("=" * 60)

    setup_personas()
    test_browser_basic()
    test_llm_integration()

    session_log = test_e2e_session()

    if session_log:
        test_review(session_log.session_id)
        test_report(session_log)

    test_events()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)
