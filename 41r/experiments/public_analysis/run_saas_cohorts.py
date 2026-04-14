"""3 SaaS Pricing Pages — 공개 분석용 코호트 시뮬.

타겟: Notion / Linear / Figma 가격 페이지.
페르소나: PM/디자이너/개발자 segment가 어떻게 다르게 반응하는지.

비용 추정: 3 사이트 × 20 페르소나 × text mode = ~$1.5
시간: ~3분

사용:
    .venv/bin/python3 experiments/public_analysis/run_saas_cohorts.py
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
_OUT = _BASE / "saas_cohorts_summary.json"

TARGETS = [
    {
        "slug": "notion",
        "company": "Notion",
        "url": "https://www.notion.so/pricing",
        "task": "팀(5~10명)을 위한 협업 도구를 찾는다. Notion 가격 페이지를 보고 어느 플랜이 우리에게 맞는지 결정해라. 무료 vs 유료 vs Business 비교.",
        "spec": CohortSpec(
            segment_name="Notion 타겟 (팀 도입 결정자: PM/PO/팀장)",
            size=20,
            age_range=(28, 42),
            gender_dist={"M": 0.55, "F": 0.45},
            occupations=["프로덕트 매니저", "PO", "스타트업 팀장", "디자인 디렉터", "엔지니어링 매니저"],
            region="KR-Seoul",
            impulsiveness=(0.4, 0.2),
            research_depth=(0.7, 0.15),
            price_sensitivity=(0.65, 0.2),
            visual_dependency=(0.5, 0.2),
            tech_literacy=(0.85, 0.1),
            social_proof_weight=(0.55, 0.2),
            seed=201,
        ),
    },
    {
        "slug": "linear",
        "company": "Linear",
        "url": "https://linear.app/pricing",
        "task": "엔지니어링팀 이슈 트래커를 찾는다. Jira에서 옮길지 검토 중. Linear 가격 페이지를 보고 우리 팀(5~15명)에 적합한지 판단해라.",
        "spec": CohortSpec(
            segment_name="Linear 타겟 (엔지니어링 도입 결정자)",
            size=20,
            age_range=(26, 40),
            gender_dist={"M": 0.7, "F": 0.3},
            occupations=["엔지니어링 매니저", "테크 리드", "CTO", "스타트업 개발자", "프로덕트 엔지니어"],
            region="KR-Seoul",
            impulsiveness=(0.35, 0.2),
            research_depth=(0.8, 0.15),
            price_sensitivity=(0.5, 0.2),
            visual_dependency=(0.55, 0.2),
            tech_literacy=(0.95, 0.05),
            social_proof_weight=(0.5, 0.2),
            seed=202,
        ),
    },
    {
        "slug": "figma",
        "company": "Figma",
        "url": "https://www.figma.com/pricing",
        "task": "디자인팀(3~8명) 협업 도구를 찾는다. Figma 가격 페이지를 보고 Professional vs Organization 중 우리에게 맞는 플랜을 결정해라.",
        "spec": CohortSpec(
            segment_name="Figma 타겟 (디자인 도입 결정자)",
            size=20,
            age_range=(25, 40),
            gender_dist={"M": 0.45, "F": 0.55},
            occupations=["프로덕트 디자이너", "디자인 리드", "디자인 디렉터", "UX 매니저", "프리랜서 디자이너"],
            region="KR-Seoul",
            impulsiveness=(0.5, 0.2),
            research_depth=(0.6, 0.2),
            price_sensitivity=(0.55, 0.2),
            visual_dependency=(0.85, 0.1),
            tech_literacy=(0.8, 0.15),
            social_proof_weight=(0.6, 0.2),
            seed=203,
        ),
    },
]


def run_all():
    summaries = []
    for t in TARGETS:
        logger.info("=" * 70)
        logger.info("%s — Generating cohort", t["company"])
        cohort_id = generate_cohort(t["spec"])

        logger.info("Running %s simulation...", t["company"])
        cohort_result = run_cohort(
            cohort_id, t["url"], t["task"],
            mode="text", max_workers=5,
        )
        result_path = cohort_result["output_path"]

        logger.info("Generating report...")
        report_id = generate_cohort_report(result_path)

        summaries.append({
            "slug": t["slug"],
            "company": t["company"],
            "url": t["url"],
            "cohort_id": cohort_id,
            "result_path": result_path,
            "report_id": report_id,
            "report_html": f"reports/{report_id}/cohort_report.html",
            "aggregation_json": f"reports/{report_id}/aggregation.json",
        })

    with open(_OUT, "w") as f:
        json.dump({"phase": "public_analysis_v1", "targets": summaries},
                  f, ensure_ascii=False, indent=2)

    logger.info("=" * 70)
    logger.info("DONE. Summary → %s", _OUT)
    for s in summaries:
        logger.info("  %s: %s", s["company"], s["report_html"])


if __name__ == "__main__":
    with cache_disabled():
        run_all()
