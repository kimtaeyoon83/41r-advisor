"""Benchmark Loader — 외부 공개 데이터셋의 실제 수치를 41R 시뮬과 비교 가능하게 로드.

지원 데이터셋:
- GA4 Sample (Google Merchandise Store): funnel, device, session metrics
- Open Bandit (ZOZOTOWN): item-level CTR 분포

사용:
    from persona_agent.analysis import get_baseline
    bl = get_baseline()
    print(bl.expected_pageviews_per_session(device='mobile'))  # 3.74
    print(bl.expected_conversion_rate(device='mobile'))        # 0.01393
    print(bl.add_to_cart_rate())  # 0.047 (전체 page_view의 4.7%)
    bl.compare_to_sim(sim_conversion=0.30)
    # → "Sim 30% vs GA4 1.7% — 17.7배 over (절대 수치 사용 금지)"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from persona_agent.errors import MissingExtraError
from persona_agent._internal.core.workspace import get_workspace

if TYPE_CHECKING:
    import pandas as pd


def _pd():
    """Lazy pandas import — raises MissingExtraError if not installed."""
    try:
        import pandas as pd  # noqa: F401
    except ImportError as e:
        raise MissingExtraError(
            "benchmark", "pip install persona-agent[benchmark]"
        ) from e
    return pd

logger = logging.getLogger(__name__)

_GA4_DIR: Path | None = None
_OBP_DIR: Path | None = None


def _get_ga4_dir() -> Path:
    global _GA4_DIR
    if _GA4_DIR is None:
        _GA4_DIR = get_workspace().experiments_dir / "datasets" / "ga4_sample"
    return _GA4_DIR


def _get_obp_dir() -> Path:
    global _OBP_DIR
    if _OBP_DIR is None:
        _OBP_DIR = get_workspace().experiments_dir / "datasets" / "open_bandit"
    return _OBP_DIR


@dataclass
class BaselineMetrics:
    """모든 외부 데이터셋에서 추출한 baseline 수치 모음."""
    # GA4
    funnel_user_pct: dict[str, float] = field(default_factory=dict)  # event_name → % of session_start
    device_conversion: dict[str, float] = field(default_factory=dict)  # device → conversion rate (decimal)
    session_pageviews: dict[str, float] = field(default_factory=dict)  # device → avg pageviews
    session_bounce: dict[str, float] = field(default_factory=dict)  # device → bounce rate (decimal)
    country_conversion_range: tuple[float, float] = (0, 0)
    hour_conversion_range: tuple[float, float] = (0, 0)
    # Open Bandit (ZOZOTOWN)
    item_ctr_mean: float = 0.0
    item_ctr_max: float = 0.0
    # Meta
    sources: list[str] = field(default_factory=list)


def load_ga4() -> dict:
    """GA4 5개 쿼리 결과 로드. 각 결과 파일이 있으면 dict로 묶어 반환."""
    result = {}
    for stem in ["q1_funnel_drop", "q2_device_metrics", "q3_country_conversion",
                 "q4_session_metrics", "q5_hour_conversion"]:
        path = _get_ga4_dir() / f"{stem}.csv"
        if path.exists():
            result[stem] = _pd().read_csv(path)
        else:
            logger.warning("GA4 데이터 없음: %s", path)
    return result


def load_open_bandit() -> Optional["pd.DataFrame"]:
    """Open Bandit sample CSV 로드."""
    path = _get_obp_dir() / "sample_all.csv"
    if not path.exists():
        return None
    return _pd().read_csv(path, index_col=0)


def get_baseline() -> BaselineMetrics:
    """모든 가용 baseline 한꺼번에 로드."""
    bl = BaselineMetrics()

    ga4 = load_ga4()
    if ga4:
        bl.sources.append("GA4 Merchandise Store (2020-11~2021-01)")

        if "q1_funnel_drop" in ga4:
            df = ga4["q1_funnel_drop"]
            ss_users = df[df["event_name"] == "session_start"]["users"].iloc[0]
            for _, row in df.iterrows():
                bl.funnel_user_pct[row["event_name"]] = round(row["users"] / ss_users, 4)

        if "q2_device_metrics" in ga4:
            for _, row in ga4["q2_device_metrics"].iterrows():
                bl.device_conversion[row["device"]] = row["conversion_pct"] / 100

        if "q3_country_conversion" in ga4:
            df = ga4["q3_country_conversion"]
            bl.country_conversion_range = (
                round(df["conversion_pct"].min() / 100, 4),
                round(df["conversion_pct"].max() / 100, 4),
            )

        if "q4_session_metrics" in ga4:
            for _, row in ga4["q4_session_metrics"].iterrows():
                bl.session_pageviews[row["device"]] = row["avg_pageviews"]
                bl.session_bounce[row["device"]] = row["bounce_rate_pct"] / 100

        if "q5_hour_conversion" in ga4:
            df = ga4["q5_hour_conversion"]
            bl.hour_conversion_range = (
                round(df["conversion_pct"].min() / 100, 4),
                round(df["conversion_pct"].max() / 100, 4),
            )

    obp = load_open_bandit()
    if obp is not None:
        bl.sources.append("Open Bandit ZOZOTOWN sample")
        item_ctrs = obp.groupby("item_id")["click"].mean()
        bl.item_ctr_mean = round(item_ctrs.mean(), 4)
        bl.item_ctr_max = round(item_ctrs.max(), 4)

    return bl


def reality_check(sim_value: float, real_value: float, label: str = "") -> dict:
    """시뮬 값 vs 실제 값 비교 — gap factor + 신뢰도 등급."""
    if real_value == 0:
        return {"label": label, "gap": "real=0", "trust": "unverifiable"}
    factor = sim_value / real_value
    if factor < 1.5:
        trust = "✅ 신뢰 가능"
    elif factor < 3:
        trust = "⚠️ 약간 over"
    elif factor < 10:
        trust = "🔶 상당히 over (참고용)"
    else:
        trust = "🔴 매우 over (절대 수치 사용 금지)"
    return {
        "label": label,
        "sim": round(sim_value, 4),
        "real": round(real_value, 4),
        "factor": round(factor, 1),
        "trust": trust,
    }


def diagnose_cohort(cohort_aggregation: dict, baseline: Optional[BaselineMetrics] = None) -> dict:
    """코호트 결과를 baseline과 비교 — sample_report에 통합용.

    Args:
        cohort_aggregation: cohort_report.aggregate_cohort 결과
        baseline: get_baseline() 결과, 없으면 자동 로드
    """
    if baseline is None:
        baseline = get_baseline()

    diagnoses = []

    # 전환율 (converted = task_complete) vs GA4
    sim_conversion = cohort_aggregation.get("conversion_rate", 0)
    if baseline.device_conversion:
        # mobile 평균을 reference (가장 흔한 케이스)
        real_conversion = baseline.device_conversion.get("mobile", 0.014)
        diagnoses.append(reality_check(sim_conversion, real_conversion, "전환율 (vs GA4 mobile)"))

    # 평균 turn vs avg pageviews
    sim_turns = cohort_aggregation.get("engagement", {}).get("avg_turns", 0)
    if baseline.session_pageviews:
        real_pv = baseline.session_pageviews.get("mobile", 3.74)
        diagnoses.append(reality_check(sim_turns, real_pv, "평균 페이지뷰 (vs GA4 mobile)"))

    # add_to_cart 비율 (단순 비교: partial+converted를 add_to_cart-ish로)
    n_total = cohort_aggregation.get("n_total", 1)
    n_partial_or_converted = cohort_aggregation.get("n_partial", 0) + cohort_aggregation.get("n_converted", 0)
    sim_atc = n_partial_or_converted / n_total if n_total > 0 else 0
    if baseline.funnel_user_pct.get("add_to_cart"):
        real_atc = baseline.funnel_user_pct["add_to_cart"]
        diagnoses.append(reality_check(sim_atc, real_atc, "장바구니 도달률 (vs GA4)"))

    return {
        "baseline_sources": baseline.sources,
        "comparisons": diagnoses,
        "summary_text": _summary_text(diagnoses),
    }


def _summary_text(comparisons: list[dict]) -> str:
    if not comparisons:
        return "비교 불가 (baseline 없음)"
    over_count = sum(1 for c in comparisons if "over" in c.get("trust", ""))
    if over_count == 0:
        return "✅ 시뮬 수치가 실제 데이터와 일치"
    return f"⚠️ {over_count}/{len(comparisons)} 메트릭이 실제보다 over-estimate. 절대 수치 사용 시 disclaimer 필수."


if __name__ == "__main__":
    import sys
    bl = get_baseline()
    print("=== Baseline Sources ===")
    for s in bl.sources:
        print(f"  - {s}")
    print(f"\nFunnel %: {bl.funnel_user_pct}")
    print(f"Device conversion: {bl.device_conversion}")
    print(f"Session pageviews: {bl.session_pageviews}")
    print(f"Country conv range: {bl.country_conversion_range}")
    print(f"OBP item CTR: mean={bl.item_ctr_mean}, max={bl.item_ctr_max}")

    if len(sys.argv) > 1:
        # 코호트 결과 파일 비교
        import json
        with open(sys.argv[1]) as f:
            agg = json.load(f)
        diag = diagnose_cohort(agg, bl)
        print("\n=== Diagnosis ===")
        print(json.dumps(diag, ensure_ascii=False, indent=2))
