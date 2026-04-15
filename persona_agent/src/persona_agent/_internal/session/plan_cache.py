"""Plan Cache — plan 전용 3단계 캐시 (exact → template → full generation).

3단계 조회:
1. Exact Match:    hash(persona_id + task + url) → 그대로 반환
2. Template Match: hash(persona_template + task) → 골격 재사용, LOW로 세부 조정
3. Full Generation: HIGH로 생성 + 캐시 저장
"""

from __future__ import annotations

import json

from persona_agent._internal.core.cache import content_hash, get as cache_get, put as cache_put
from persona_agent._internal.core import events_log

_NAMESPACE = "plans"


def get_or_generate(
    persona: dict,
    task: str,
    url: str,
    *,
    generate_fn=None,
    adjust_fn=None,
) -> dict:
    """Plan Cache 3단계 조회.

    Args:
        persona: 페르소나 상태 dict (persona_id, soul_text, soul_version 등)
        task: 수행할 태스크
        url: 대상 URL
        generate_fn: [HIGH] 전체 plan 생성 callable(persona, task, url) -> dict
        adjust_fn: [LOW] 템플릿 기반 세부 조정 callable(skeleton, persona, url) -> dict
    """
    persona_id = persona.get("persona_id", "")
    soul_text = persona.get("soul_text", "")

    # Stage 1: Exact Match
    exact_key = content_hash(json.dumps({
        "persona_id": persona_id,
        "task": task,
        "url": url,
    }, sort_keys=True))

    cached = cache_get(_NAMESPACE, exact_key)
    if cached:
        events_log.append({
            "type": "plan_generated",
            "source": "cache_exact",
            "persona": persona_id,
            "plan_key": exact_key,
        })
        return cached

    # Stage 2: Template Match
    template_key = content_hash(json.dumps({
        "soul_text": soul_text,
        "task": task,
    }, sort_keys=True))

    template_cached = cache_get(_NAMESPACE, template_key)
    if template_cached and adjust_fn:
        adjusted = adjust_fn(template_cached, persona, url)
        cache_put(_NAMESPACE, exact_key, adjusted)
        events_log.append({
            "type": "plan_generated",
            "source": "cache_template",
            "persona": persona_id,
            "plan_key": exact_key,
        })
        return adjusted

    # Stage 3: Full Generation
    if generate_fn is None:
        raise RuntimeError("Plan cache miss and no generate_fn provided")

    plan = generate_fn(persona, task, url)

    # 양쪽 캐시에 저장
    cache_put(_NAMESPACE, exact_key, plan)
    cache_put(_NAMESPACE, template_key, plan)

    events_log.append({
        "type": "plan_generated",
        "source": "generated",
        "persona": persona_id,
        "plan_key": exact_key,
    })

    return plan
