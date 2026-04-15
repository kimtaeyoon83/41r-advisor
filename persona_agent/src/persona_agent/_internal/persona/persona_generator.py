"""Persona Generator — 세그먼트 사양으로부터 N명의 페르소나를 자동 생성.

주요 개념:
- **Segment Spec**: 나이 범위, 성별 분포, 직업 풀, 성향 축 평균/표준편차
- **Latin Hypercube Sampling**: 성향 5축을 균등하게 분산 (단순 random 대비 다양성 ↑)
- **Deterministic seeds**: 재현성 보장

생성 결과:
- personas/cohort_<run_id>/p_00_XXXX/soul/v001.md
- personas/cohort_<run_id>/cohort_meta.json

사용법:
    from modules.persona_generator import CohortSpec, generate_cohort
    spec = CohortSpec(
        segment_name="20대 여성 직장인",
        size=30,
        age_range=(22, 29),
        gender_dist={"F": 1.0},
        occupations=["직장인", "대학원생", "프리랜서"],
        region="KR-Seoul",
        impulsiveness=(0.5, 0.2),  # (mean, std)
        research_depth=(0.4, 0.2),
        privacy_sensitivity=(0.5, 0.2),
        price_sensitivity=(0.6, 0.2),
        visual_dependency=(0.6, 0.2),
    )
    run_id = generate_cohort(spec)
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from persona_agent._internal.core.workspace import get_workspace

logger = logging.getLogger(__name__)

_PERSONAS_DIR = get_workspace().personas_dir


@dataclass
class CohortSpec:
    """코호트 생성 스펙.

    성향 축은 (mean, std) 형태. 값은 [0, 1] 범위로 clip.
    """
    segment_name: str
    size: int
    age_range: tuple[int, int]
    gender_dist: dict[str, float]  # {"M": 0.3, "F": 0.7}
    occupations: list[str]
    region: str = "KR-Seoul"

    # 5축 성향 (mean, std)
    impulsiveness: tuple[float, float] = (0.5, 0.2)
    research_depth: tuple[float, float] = (0.5, 0.2)
    privacy_sensitivity: tuple[float, float] = (0.5, 0.2)
    price_sensitivity: tuple[float, float] = (0.5, 0.2)
    visual_dependency: tuple[float, float] = (0.5, 0.2)

    # 세대 특성
    tech_literacy: tuple[float, float] = (0.7, 0.15)
    social_proof_weight: tuple[float, float] = (0.5, 0.2)

    seed: int = 42

    def __post_init__(self) -> None:
        if not 1 <= self.size <= 200:
            raise ValueError(f"Cohort size out of range: {self.size}")
        if self.age_range[0] > self.age_range[1]:
            raise ValueError("Invalid age range")
        if abs(sum(self.gender_dist.values()) - 1.0) > 0.01:
            raise ValueError("gender_dist must sum to 1.0")


def _latin_hypercube_1d(n: int, mean: float, std: float, rng: random.Random) -> list[float]:
    """1차원 Latin hypercube — n 구간을 균등 분할하고 각 구간 내 랜덤.

    단순 normal sampling보다 분포 커버리지가 좋음.
    """
    segments = [(i / n, (i + 1) / n) for i in range(n)]
    rng.shuffle(segments)

    values = []
    for lo, hi in segments:
        # uniform → normal approximation via inverse CDF-ish
        u = lo + (hi - lo) * rng.random()
        # Box-Muller 간단 근사: u를 mean ± 2*std 범위로 매핑
        v = mean + (u - 0.5) * 4 * std
        v = max(0.0, min(1.0, v))  # clip
        values.append(round(v, 2))
    return values


def _sample_trust_signals(impulsiveness: float, research_depth: float) -> tuple[list[str], list[str]]:
    """성향에 따른 신뢰 신호 선택."""
    visual = impulsiveness > 0.5
    thorough = research_depth > 0.5

    important = []
    irrelevant = []

    if visual:
        important.extend(["별점 4.5+", "구매 후기 사진"])
        if impulsiveness > 0.7:
            important.append("할인 배너")
            irrelevant.extend(["회사 연혁", "인증서"])
    if thorough:
        important.extend(["환불 정책 명시", "고객 사례 3개+"])
        if research_depth > 0.7:
            important.append("회사 연혁 5년+")
            irrelevant.extend(["할인 배너", "한정 수량"])

    if not important:
        important = ["별점 4.0+", "후기"]
    if not irrelevant:
        irrelevant = ["과장된 카피"]

    return important, irrelevant


def _sample_frustration_triggers(impulsiveness: float, privacy: float, price: float) -> list[str]:
    triggers = []
    if impulsiveness > 0.6:
        triggers.extend(["3초 이상 로딩", "팝업 광고 2개 이상", "강제 회원가입"])
    if privacy > 0.6:
        triggers.append("과도한 개인정보 요구")
    if price > 0.6:
        triggers.extend(["가격 정보 숨김", "숨겨진 수수료"])
    if not triggers:
        triggers = ["불명확한 CTA"]
    return triggers


def _make_soul_text(
    *,
    name: str,
    age: int,
    gender: str,
    occupation: str,
    region: str,
    impulsiveness: float,
    research_depth: float,
    privacy_sensitivity: float,
    price_sensitivity: float,
    visual_dependency: float,
    tech_literacy: float,
    social_proof_weight: float,
) -> str:
    """성향 값들로부터 soul 문서 생성."""
    patience = round(2 + (1 - impulsiveness) * 13, 1)  # 2~15초
    decision_latency = round(0.5 + (1 - impulsiveness) * 4.5, 1)  # 0.5~5초

    important, irrelevant = _sample_trust_signals(impulsiveness, research_depth)
    triggers = _sample_frustration_triggers(impulsiveness, privacy_sensitivity, price_sensitivity)

    frontmatter = f"""---
name: {name}
age: {age}
gender: {gender}
age_group: {"young_adult" if age < 30 else "adult" if age < 50 else "senior"}
region: {region}
occupation: {occupation}

timing:
  patience_seconds: {patience}
  decision_latency_sec: {decision_latency}
  loading_tolerance: {"strict" if impulsiveness > 0.7 else "moderate" if impulsiveness > 0.4 else "patient"}

profile:
  visual_dependency: {visual_dependency}
  decision_speed: {impulsiveness}
  research_depth: {research_depth}
  privacy_sensitivity: {privacy_sensitivity}
  price_sensitivity: {price_sensitivity}

generation:
  tech_literacy: {tech_literacy}
  device_preference: {"mobile" if age < 35 else "desktop"}
  social_proof_weight: {social_proof_weight}

frustration_triggers:
{chr(10).join(f'  - "{t}"' for t in triggers)}

trust_signals:
  important: {json.dumps(important, ensure_ascii=False)}
  irrelevant: {json.dumps(irrelevant, ensure_ascii=False)}
---

{age}세 {gender}, {region} 거주, {occupation}.

{_narrative(impulsiveness, research_depth, price_sensitivity)}"""

    return frontmatter


def _narrative(impulsiveness: float, research: float, price: float) -> str:
    """성향 기반 짧은 내러티브."""
    parts = []
    if impulsiveness > 0.7:
        parts.append("빠르게 결정하고 행동하는 편이다. 시각적 자극에 즉시 반응한다.")
    elif impulsiveness < 0.3:
        parts.append("결정하기 전에 시간을 들인다. 충동구매는 거의 하지 않는다.")
    else:
        parts.append("상황에 따라 빠르게 결정할 때도, 꼼꼼히 따질 때도 있다.")

    if research > 0.7:
        parts.append("제품 정보를 끝까지 읽고, 리뷰의 부정적 내용을 먼저 찾는다.")
    elif research < 0.3:
        parts.append("긴 설명은 잘 읽지 않는다. 핵심 정보만 빠르게 확인한다.")

    if price > 0.7:
        parts.append("가격에 민감하다. 할인, 수수료, 환불 정책을 반드시 확인한다.")
    elif price < 0.3:
        parts.append("가격보다 편의성과 품질을 우선한다.")

    return " ".join(parts)


def generate_cohort(spec: CohortSpec) -> str:
    """코호트 생성. run_id 반환.

    Returns:
        run_id (예: 'cohort_20260414_abc123')
    """
    rng = random.Random(spec.seed)

    # 축별로 Latin hypercube로 값 생성
    axes = {
        "impulsiveness": _latin_hypercube_1d(spec.size, *spec.impulsiveness, rng),
        "research_depth": _latin_hypercube_1d(spec.size, *spec.research_depth, rng),
        "privacy_sensitivity": _latin_hypercube_1d(spec.size, *spec.privacy_sensitivity, rng),
        "price_sensitivity": _latin_hypercube_1d(spec.size, *spec.price_sensitivity, rng),
        "visual_dependency": _latin_hypercube_1d(spec.size, *spec.visual_dependency, rng),
        "tech_literacy": _latin_hypercube_1d(spec.size, *spec.tech_literacy, rng),
        "social_proof_weight": _latin_hypercube_1d(spec.size, *spec.social_proof_weight, rng),
    }

    # 각자 셔플하여 독립성 확보
    for k in axes:
        rng.shuffle(axes[k])

    # 성별 샘플링
    genders = []
    for g, p in spec.gender_dist.items():
        genders.extend([g] * int(round(spec.size * p)))
    while len(genders) < spec.size:
        genders.append(list(spec.gender_dist.keys())[0])
    genders = genders[:spec.size]
    rng.shuffle(genders)

    # run_id
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"cohort_{ts}_{uuid.uuid4().hex[:6]}"
    cohort_dir = _PERSONAS_DIR / run_id
    cohort_dir.mkdir(parents=True, exist_ok=True)

    persona_ids = []
    personas_meta = []

    for i in range(spec.size):
        age = rng.randint(*spec.age_range)
        gender = genders[i]
        occupation = rng.choice(spec.occupations)

        pid = f"p_{i:03d}_{uuid.uuid4().hex[:4]}"
        name = f"{spec.segment_name} #{i+1}"

        soul_text = _make_soul_text(
            name=name,
            age=age,
            gender=gender,
            occupation=occupation,
            region=spec.region,
            impulsiveness=axes["impulsiveness"][i],
            research_depth=axes["research_depth"][i],
            privacy_sensitivity=axes["privacy_sensitivity"][i],
            price_sensitivity=axes["price_sensitivity"][i],
            visual_dependency=axes["visual_dependency"][i],
            tech_literacy=axes["tech_literacy"][i],
            social_proof_weight=axes["social_proof_weight"][i],
        )

        persona_dir = cohort_dir / pid
        (persona_dir / "soul").mkdir(parents=True, exist_ok=True)
        (persona_dir / "history").mkdir(parents=True, exist_ok=True)
        (persona_dir / "reflections").mkdir(parents=True, exist_ok=True)
        (persona_dir / "snapshots").mkdir(parents=True, exist_ok=True)

        soul_path = persona_dir / "soul" / "v001.md"
        soul_path.write_text(soul_text, encoding="utf-8")

        manifest = f"""current: v001
versions:
  v001:
    created: "{datetime.now(timezone.utc).isoformat()}"
    author: persona_generator
    message: "Auto-generated cohort member — {spec.segment_name}"
"""
        (persona_dir / "soul" / "manifest.yaml").write_text(manifest, encoding="utf-8")

        personas_meta.append({
            "persona_id": pid,
            "name": name,
            "age": age,
            "gender": gender,
            "occupation": occupation,
            "traits": {
                k: axes[k][i] for k in axes
            },
        })
        persona_ids.append(pid)

    # cohort_meta.json
    meta = {
        "run_id": run_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "spec": {
            "segment_name": spec.segment_name,
            "size": spec.size,
            "age_range": list(spec.age_range),
            "gender_dist": spec.gender_dist,
            "occupations": spec.occupations,
            "region": spec.region,
            "seed": spec.seed,
            "axes_means": {
                k: getattr(spec, k)[0] for k in
                ["impulsiveness", "research_depth", "privacy_sensitivity",
                 "price_sensitivity", "visual_dependency", "tech_literacy", "social_proof_weight"]
            },
        },
        "personas": personas_meta,
    }
    with open(cohort_dir / "cohort_meta.json", "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info("Generated cohort %s with %d personas", run_id, spec.size)
    return run_id


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    # 데모: 20대 여성 직장인 20명
    spec = CohortSpec(
        segment_name="20대 여성 직장인",
        size=20,
        age_range=(22, 29),
        gender_dist={"F": 1.0},
        occupations=["스타트업 마케터", "대기업 사무직", "프리랜서 디자이너", "대학원생", "초등 교사"],
        region="KR-Seoul",
        # 이 세그먼트의 일반적 특성 (문헌 기반 추정)
        impulsiveness=(0.65, 0.2),  # 20대는 평균보다 충동적
        research_depth=(0.4, 0.2),
        privacy_sensitivity=(0.5, 0.2),
        price_sensitivity=(0.7, 0.15),  # 직장 초년 → 가격 민감
        visual_dependency=(0.7, 0.15),
        tech_literacy=(0.85, 0.1),  # 디지털 네이티브
    )
    run_id = generate_cohort(spec)
    print(f"Generated: {run_id}")
    print(f"Location: personas/{run_id}/")
