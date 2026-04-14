"""Golden Session 실행 스크립트 — H1 검증용.

실제 사이트에 페르소나를 투입하여 golden session을 생성한다.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# .env 로드
from dotenv import load_dotenv
load_dotenv()

from modules.persona_store import create_persona, list_personas
from modules.agent_loop import run_session
from modules.report_gen import generate_report
from modules.review_agent import inspect, evaluate


# === 페르소나 정의 ===

PERSONAS = {
    "p_impulsive": """---
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
모바일 쇼핑을 선호하고 긴 설명은 스킵한다.
""",

    "p_cautious": """---
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
신뢰 지표(리뷰 수, 평점, 인증 마크)를 중요하게 본다.
""",

    "p_bargain": """---
name: 가격 민감 소비자 현우
age: 42
occupation: 공무원
timing:
  patience_seconds: 5.0
  reading_wpm: 300
  decision_latency_sec: 2.0
  loading_tolerance: normal
---

나는 가격이 가장 중요하다.
첫 화면에서 가격 정보를 바로 찾는다.
할인율, 쿠폰, 무료배송 여부를 먼저 확인한다.
비슷한 제품이 더 싸게 있을 것 같으면 바로 이탈한다.
가격 대비 가치가 명확하지 않으면 구매하지 않는다.
리뷰는 가격 관련 언급만 빠르게 스캔한다.
""",
}


# === 테스트 대상 사이트 ===

GOLDEN_SITES = [
    # A/B 역검증 케이스 1: SmartWool — 상품 그리드 레이아웃
    # 결과: 균일 그리드 +17.1% 매출 (Optimizely case study)
    {
        "id": "ab_01_smartwool",
        "url": "https://www.smartwool.com/collections/mens-socks",
        "task": "이 아웃도어 의류 사이트의 양말 카테고리를 탐색해라. 상품 목록의 레이아웃을 살펴보고, 관심 있는 상품을 클릭해서 상세 페이지를 확인해라. 가격과 상품 설명을 읽고 구매 의사를 결정해라.",
        "category": "ecommerce",
        "ab_context": "Grid layout test: uniform vs varied sizes. Uniform won +17.1% RPV.",
    },
    # A/B 역검증 케이스 2: PriceCharting — CTA 버튼 텍스트
    # 결과: "Price Guide" 버튼이 "Download" 대비 +620.9% CTR (VWO case study)
    {
        "id": "ab_02_pricecharting",
        "url": "https://www.pricecharting.com",
        "task": "이 게임/카드 가격 비교 사이트를 탐색해라. 메인 페이지를 읽고, 어떤 서비스인지 파악해라. 가격 가이드나 다운로드 버튼이 있다면 클릭할지 결정해라.",
        "category": "marketplace",
        "ab_context": "CTA text test: 'Download' vs 'Price Guide'. Price Guide won +620.9% CTR.",
    },
    # Golden 3: Shopify — SaaS 랜딩 페이지
    {
        "id": "golden_03_shopify",
        "url": "https://www.shopify.com",
        "task": "이 이커머스 플랫폼의 랜딩 페이지를 탐색해라. 서비스가 무엇인지 파악하고, 가격과 기능을 확인한 뒤 가입할지 결정해라.",
        "category": "saas",
    },
    # Golden 4: Figma — SaaS 가격 페이지
    {
        "id": "golden_04_figma_pricing",
        "url": "https://www.figma.com/pricing",
        "task": "이 디자인 도구의 가격 페이지를 분석해라. 각 요금제의 차이점을 파악하고, 개인 사용자로서 어떤 플랜이 적합한지 결정해라.",
        "category": "saas_pricing",
    },
    # Golden 5: Notion — SaaS 랜딩
    {
        "id": "golden_05_notion",
        "url": "https://www.notion.so",
        "task": "이 SaaS 제품의 랜딩 페이지를 탐색하고, 제품이 무엇인지 파악해라. 가격 페이지를 찾아 요금제를 확인하고, 무료 체험을 시작할지 결정해라.",
        "category": "saas",
    },
]


def setup_personas():
    """페르소나 생성 (이미 있으면 스킵)."""
    existing = list_personas()
    for pid, soul in PERSONAS.items():
        if pid not in existing:
            create_persona(pid, soul)
            print(f"  [+] Created {pid}")
        else:
            print(f"  [=] {pid} already exists")


def run_golden_session(site: dict, persona_id: str) -> dict | None:
    """단일 golden session 실행."""
    print(f"\n  Running: {persona_id} on {site['url']}")
    try:
        log = run_session(
            persona_id=persona_id,
            url=site["url"],
            task=site["task"],
        )
        print(f"    Outcome: {log.outcome}, Turns: {log.total_turns}")

        # Review
        view = inspect(log.session_id)
        score = evaluate(log.session_id)
        print(f"    Quality: {'PASS' if view['quality_gate']['pass'] else 'FAIL'}, Score: {score['scores']['overall']:.2f}")

        return {
            "session_id": log.session_id,
            "persona_id": log.persona_id,
            "url": log.url,
            "task": log.task,
            "outcome": log.outcome,
            "total_turns": log.total_turns,
            "turns": log.turns,
            "quality_pass": view["quality_gate"]["pass"],
            "consistency_score": score["scores"]["overall"],
            "site_id": site["id"],
            "category": site["category"],
        }

    except Exception as e:
        print(f"    ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_golden(session_data: dict):
    """Golden session으로 저장."""
    golden_dir = Path("experiments/golden_sessions")
    golden_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{session_data['site_id']}_{session_data['persona_id']}.json"
    path = golden_dir / filename
    with open(path, "w") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    print(f"    Saved golden: {filename}")


def generate_comparison_report(sessions: list[dict], personas: list[str]):
    """A/B 비교 리포트 생성."""
    report_id = generate_report(sessions, personas, "ab")
    print(f"\n  Report generated: {report_id}")
    return report_id


def main():
    print("=" * 60)
    print("41R Golden Session Runner")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. 페르소나 셋업
    print("\n[1/4] Setting up personas...")
    setup_personas()

    # 2. 사이트 수 제한 (첫 실행은 2개만)
    sites = GOLDEN_SITES[:2]
    persona_ids = ["p_impulsive", "p_cautious"]

    # 3. 세션 실행
    print(f"\n[2/4] Running sessions ({len(sites)} sites x {len(persona_ids)} personas)...")
    all_sessions = []

    for site in sites:
        print(f"\n--- Site: {site['id']} ({site['url']}) ---")
        for pid in persona_ids:
            result = run_golden_session(site, pid)
            if result:
                save_golden(result)
                all_sessions.append(result)

    # 4. 리포트 생성
    print(f"\n[3/4] Generating reports...")
    if all_sessions:
        report_id = generate_comparison_report(all_sessions, persona_ids)

    # 5. 요약
    print(f"\n[4/4] Summary")
    print(f"  Sessions: {len(all_sessions)}")
    completed = sum(1 for s in all_sessions if s["outcome"] == "task_complete")
    print(f"  Completed: {completed}/{len(all_sessions)}")
    avg_score = sum(s["consistency_score"] for s in all_sessions) / max(len(all_sessions), 1)
    print(f"  Avg consistency: {avg_score:.2f}")
    quality_pass = sum(1 for s in all_sessions if s["quality_pass"])
    print(f"  Quality pass: {quality_pass}/{len(all_sessions)}")

    print("\n" + "=" * 60)
    print("GOLDEN SESSIONS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
