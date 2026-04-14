"""타겟 5곳 × 20명 코호트 시뮬 + 리포트 일괄 생성.

사용법:
    ANTHROPIC_API_KEY=... python3 experiments/outbound/run_target_cohorts.py
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.cache import cache_disabled
from modules.persona_generator import CohortSpec, generate_cohort
from modules.cohort_runner import run_cohort
from modules.cohort_report import generate_cohort_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_OUT = _BASE / "cohort_results_summary.json"

TARGETS = [
    {
        "slug": "29cm",
        "company": "29CM",
        "url": "https://www.29cm.co.kr",
        "task": "새로운 봄 의류를 둘러보고, 마음에 드는 상품 1~2개를 찾아 장바구니 담기까지 결정해라",
        "spec": CohortSpec(
            segment_name="29CM 타겟 (25~34세 여성, 디자인 브랜드 관심)",
            size=20,
            age_range=(25, 34),
            gender_dist={"F": 1.0},
            occupations=["스타트업 마케터", "대기업 사무직", "프리랜서 디자이너", "MD", "콘텐츠 크리에이터"],
            region="KR-Seoul",
            impulsiveness=(0.65, 0.2),
            research_depth=(0.45, 0.2),
            price_sensitivity=(0.55, 0.2),
            visual_dependency=(0.8, 0.15),
            social_proof_weight=(0.65, 0.2),
            seed=101,
        ),
    },
    {
        "slug": "class101",
        "company": "클래스101",
        "url": "https://class101.net",
        "task": "관심 분야의 클래스를 찾고, 구독할지 결정해라. 가격과 커리큘럼을 비교해봐라",
        "spec": CohortSpec(
            segment_name="클래스101 타겟 (28~39세 직장인·프리랜서, 자기계발 관심)",
            size=20,
            age_range=(28, 39),
            gender_dist={"M": 0.4, "F": 0.6},
            occupations=["스타트업 개발자", "대기업 사무직", "프리랜서 디자이너", "마케터", "교사"],
            region="KR-Seoul",
            impulsiveness=(0.45, 0.2),
            research_depth=(0.65, 0.2),
            price_sensitivity=(0.7, 0.15),
            visual_dependency=(0.5, 0.2),
            seed=102,
        ),
    },
    {
        "slug": "ohouse",
        "company": "오늘의집",
        "url": "https://ohou.se",
        "task": "거실에 둘 러그 또는 조명을 찾아 구매 결정까지 진행해라. 콘텐츠/리뷰를 참고해라",
        "spec": CohortSpec(
            segment_name="오늘의집 타겟 (28~42세, 1~2인 가구, 홈스타일링 관심)",
            size=20,
            age_range=(28, 42),
            gender_dist={"M": 0.3, "F": 0.7},
            occupations=["사무직", "프리랜서", "교사", "간호사", "주부"],
            region="KR-Seoul",
            impulsiveness=(0.5, 0.2),
            research_depth=(0.6, 0.2),
            price_sensitivity=(0.6, 0.2),
            visual_dependency=(0.75, 0.15),
            social_proof_weight=(0.7, 0.15),
            seed=103,
        ),
    },
    {
        "slug": "webflow",
        "company": "Webflow",
        "url": "https://webflow.com/pricing",
        "task": "개인 프리랜서로 웹사이트 제작 도구를 찾고 있다. 가격 페이지를 검토하고 적합한 플랜을 결정해라",
        "spec": CohortSpec(
            segment_name="Webflow 타겟 (28~40세 프로덕트 디자이너/프리랜서)",
            size=20,
            age_range=(28, 40),
            gender_dist={"M": 0.55, "F": 0.45},
            occupations=["프리랜서 디자이너", "프로덕트 디자이너", "웹 개발자", "스타트업 PM", "에이전시 디렉터"],
            region="KR-Seoul",
            impulsiveness=(0.4, 0.2),
            research_depth=(0.75, 0.15),
            price_sensitivity=(0.6, 0.2),
            visual_dependency=(0.6, 0.2),
            tech_literacy=(0.9, 0.1),
            seed=104,
        ),
    },
    {
        "slug": "glossier",
        "company": "Glossier",
        "url": "https://www.glossier.com",
        "task": "해외 뷰티 브랜드의 메인 제품을 둘러보고, 마음에 드는 상품을 체크아웃까지 가는지 결정해라",
        "spec": CohortSpec(
            segment_name="Glossier 타겟 (22~34세 여성, 글로벌 브랜드 관심, 해외직구 경험)",
            size=20,
            age_range=(22, 34),
            gender_dist={"F": 1.0},
            occupations=["스타트업 마케터", "프리랜서 디자이너", "대학원생", "콘텐츠 크리에이터", "유학생"],
            region="KR-Seoul",
            impulsiveness=(0.6, 0.2),
            research_depth=(0.5, 0.2),
            price_sensitivity=(0.55, 0.2),
            visual_dependency=(0.8, 0.15),
            social_proof_weight=(0.75, 0.15),
            seed=105,
        ),
    },
]


def run_all() -> dict:
    results_summary = []

    for t in TARGETS:
        logger.info("=" * 70)
        logger.info("%s — Generating cohort of %d personas", t["company"], t["spec"].size)
        logger.info("=" * 70)

        # 1. 코호트 생성
        cohort_id = generate_cohort(t["spec"])

        # 2. 시뮬 실행 (text mode)
        logger.info("Running cohort simulation for %s...", t["company"])
        cohort_result = run_cohort(
            cohort_id,
            t["url"],
            t["task"],
            mode="text",
            max_workers=5,
        )

        # 3. 리포트 생성
        result_path = cohort_result["output_path"]
        logger.info("Generating report for %s...", t["company"])
        report_id = generate_cohort_report(result_path)

        results_summary.append({
            "slug": t["slug"],
            "company": t["company"],
            "url": t["url"],
            "cohort_id": cohort_id,
            "result_path": result_path,
            "report_id": report_id,
            "report_html": f"reports/{report_id}/cohort_report.html",
            "aggregation_json": f"reports/{report_id}/aggregation.json",
        })

    summary = {
        "phase": "D2",
        "targets": results_summary,
    }
    with open(_OUT, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 70)
    logger.info("ALL DONE. Summary → %s", _OUT)
    for r in results_summary:
        logger.info("  %s: %s", r["company"], r["report_html"])

    return summary


if __name__ == "__main__":
    with cache_disabled():
        run_all()
