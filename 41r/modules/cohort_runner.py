"""Cohort Runner — N명 페르소나 코호트에 대해 동일 URL/task로 병렬 실행.

모드:
- text: LLM이 페르소나 프로필 + URL/task로 행동을 예측 (fast, cheap)
- browser: 각 페르소나에 대해 실제 브라우저 세션 (slow, expensive)

Usage:
    from modules.cohort_runner import run_cohort

    result = run_cohort(
        cohort_run_id="cohort_20260414_abc",
        url="https://figma.com/pricing",
        task="개인 사용자 플랜 선택",
        mode="text",
        max_workers=5,
    )
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import multiprocessing as mp
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.provider_router import call as llm_call
from modules.persona_store import read_persona

# multiprocessing fork 시 41r 모듈 path 보장
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_PERSONAS_DIR = _BASE_DIR / "personas"
_COHORT_RESULTS_DIR = _BASE_DIR / "cohort_results"


TEXT_MODE_SYSTEM = """당신은 UX 행동 예측 전문가입니다.

주어진 AI 페르소나가 특정 URL의 제품을 사용하며 주어진 태스크를 수행할 때의 행동을 예측하세요.

## 출력 (JSON만)
```json
{
  "outcome": "task_complete" | "abandoned" | "partial",
  "predicted_turns": 정수 (1~15, engagement proxy),
  "drop_point": "이탈한 단계 또는 null",
  "key_behaviors": ["주요 행동 1", "주요 행동 2"],
  "frustration_points": ["마찰 1"],
  "conversion_probability": 0.0~1.0,
  "reasoning": "2~3문장 근거"
}
```"""


def _load_cohort_personas(cohort_run_id: str) -> list[tuple[str, dict]]:
    """코호트 메타 + 각 페르소나 soul 텍스트 로드."""
    cohort_dir = _PERSONAS_DIR / cohort_run_id
    meta_path = cohort_dir / "cohort_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Cohort not found: {cohort_run_id}")

    with open(meta_path) as f:
        meta = json.load(f)

    personas = []
    for p in meta["personas"]:
        pid = p["persona_id"]
        soul_dir = cohort_dir / pid / "soul"
        # manifest의 current 버전 사용, 없으면 가장 최신 v*.md
        soul_text = None
        manifest_path = soul_dir / "manifest.yaml"
        if manifest_path.exists():
            try:
                import yaml
                with open(manifest_path) as mf:
                    m = yaml.safe_load(mf) or {}
                current = m.get("current")
                if current:
                    soul_path = soul_dir / f"{current}.md"
                    if soul_path.exists():
                        soul_text = soul_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("manifest 읽기 실패 (%s): %s", pid, e)

        if soul_text is None:
            # fallback: 가장 큰 버전 번호 자동 선택
            candidates = sorted(soul_dir.glob("v*.md"), reverse=True)
            if candidates:
                soul_text = candidates[0].read_text(encoding="utf-8")

        if soul_text is None:
            logger.warning("페르소나 %s soul 파일 없음, 스킵", pid)
            continue

        personas.append((pid, {
            **p,
            "soul_text": soul_text,
            "cohort_run_id": cohort_run_id,
        }))
    return personas


def _run_text_prediction(persona_id: str, persona: dict, url: str, task: str) -> dict:
    """text mode: LLM이 페르소나 프로필로 행동 예측."""
    user_msg = f"""## 페르소나
{persona["soul_text"]}

## URL
{url}

## 태스크
{task}

이 페르소나가 위 URL에서 태스크를 수행할 때의 행동과 결과를 예측해주세요.
페르소나의 성향 프로필에 근거한 구체적 예측이 필요합니다."""

    try:
        response = llm_call(
            "review_proposer",  # MID tier
            [{"role": "user", "content": user_msg}],
            system=TEXT_MODE_SYSTEM,
            max_tokens=1024,
        )
        raw = response.get("content", "")
        # JSON 추출
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(raw[start:end])
        else:
            result = {"outcome": "error", "reasoning": raw[:200], "conversion_probability": 0}

        result["persona_id"] = persona_id
        result["persona_traits"] = persona.get("traits", {})
        result["persona_age"] = persona.get("age")
        result["persona_gender"] = persona.get("gender")
        result["tokens"] = response.get("usage", {})
        return result
    except Exception as e:
        logger.warning("Persona %s failed: %s", persona_id, e)
        return {
            "persona_id": persona_id,
            "outcome": "error",
            "error": str(e),
            "conversion_probability": 0,
        }


def _browser_worker(args: tuple) -> dict:
    """multiprocessing worker — 별도 프로세스에서 단일 세션 실행.

    각 프로세스는 자체 Python interpreter + event loop를 가지므로
    asyncio/Playwright 충돌 없음.

    Args: (persona_id, url, task, max_retries)
    """
    persona_id, url, task, max_retries = args

    # 자식 프로세스의 sys.path 보장
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)

    import logging as _lg
    _lg.basicConfig(level=_lg.INFO, format="%(asctime)s [%(processName)s] %(message)s")
    _logger = _lg.getLogger(__name__)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            from modules.agent_loop import run_session
            log = run_session(persona_id, url, task)
            result = {
                "persona_id": persona_id,
                "session_id": log.session_id,
                "outcome": log.outcome,
                "total_turns": log.total_turns,
                "turns": log.turns,
                "attempts": attempt + 1,
            }
            if attempt > 0:
                _logger.info("Persona %s 성공 (재시도 %d회 후)", persona_id, attempt)
            return result
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                _logger.warning("Persona %s 시도 %d 실패 (%s), 재시도", persona_id, attempt + 1, e)
            else:
                _logger.exception("Persona %s 최종 실패 (%d회 시도 후)", persona_id, attempt + 1)

    return {
        "persona_id": persona_id,
        "outcome": "error",
        "error": str(last_error) if last_error else "unknown",
        "attempts": max_retries + 1,
    }


def _run_browser_session(persona_id: str, url: str, task: str, max_retries: int = 2) -> dict:
    """단일 호출용 (text mode와 호환). 동일 프로세스에서 실행.

    병렬 코호트 실행은 _browser_worker + multiprocessing.Pool 사용.
    """
    return _browser_worker((persona_id, url, task, max_retries))


def run_cohort(
    cohort_run_id: str,
    url: str,
    task: str,
    *,
    mode: str = "text",
    max_workers: int = 5,
) -> dict:
    """코호트 실행.

    Args:
        cohort_run_id: persona_generator로 생성한 코호트 ID
        url: 테스트 URL
        task: 태스크 설명
        mode: "text" (빠름) or "browser" (실제 세션)
        max_workers: 동시 실행 스레드 수

    Returns:
        결과 dict. cohort_results/<run_id>_<timestamp>.json 에도 저장.
    """
    if mode not in ("text", "browser"):
        raise ValueError(f"Unknown mode: {mode}")

    logger.info("Loading cohort %s...", cohort_run_id)
    personas = _load_cohort_personas(cohort_run_id)
    logger.info("Loaded %d personas", len(personas))

    # Browser mode: 안정성을 위해 max_workers 자동 제한 (Chromium 메모리 부담)
    if mode == "browser" and max_workers > 3:
        logger.warning("Browser mode max_workers=%d → 3으로 제한 (RAM/Chromium 부담)", max_workers)
        max_workers = 3

    started_at = datetime.now(timezone.utc).isoformat()
    results = []

    if mode == "browser":
        # multiprocessing.Pool — 각 프로세스가 독립 event loop, asyncio 충돌 없음
        worker_args = [(pid, url, task, 2) for pid, _ in personas]
        # spawn 컨텍스트 (fork보다 안전, asyncio 호환)
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=max_workers) as pool:
            for i, result in enumerate(pool.imap_unordered(_browser_worker, worker_args), 1):
                results.append(result)
                logger.info("[%d/%d] %s → %s", i, len(personas),
                            result.get("persona_id"), result.get("outcome", "?"))
    else:
        # text mode: ThreadPoolExecutor (LLM API 호출만, asyncio 안 씀)
        run_fn = _run_text_prediction
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_fn, pid, p, url, task): pid
                for pid, p in personas
            }
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                pid = futures[future]
                try:
                    result = future.result(timeout=180)
                    results.append(result)
                    logger.info("[%d/%d] %s → %s", i, len(personas), pid,
                                result.get("outcome", "?"))
                except concurrent.futures.TimeoutError:
                    logger.warning("Timeout for %s", pid)
                    results.append({"persona_id": pid, "outcome": "timeout"})
                except Exception as e:
                    logger.exception("Error for %s", pid)
                    results.append({"persona_id": pid, "outcome": "error", "error": str(e)})

    finished_at = datetime.now(timezone.utc).isoformat()

    summary = {
        "cohort_run_id": cohort_run_id,
        "mode": mode,
        "url": url,
        "task": task,
        "started_at": started_at,
        "finished_at": finished_at,
        "n_personas": len(personas),
        "n_completed": sum(1 for r in results if r.get("outcome") not in ("error", "timeout")),
        "results": results,
    }

    # 결과 저장
    _COHORT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_id = f"{cohort_run_id}_{datetime.now(timezone.utc).strftime('%H%M%S')}_{uuid.uuid4().hex[:4]}"
    out_path = _COHORT_RESULTS_DIR / f"{out_id}.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    summary["output_path"] = str(out_path)
    logger.info("Cohort complete. Results → %s", out_path)
    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if len(sys.argv) < 4:
        print("Usage: python -m modules.cohort_runner <cohort_run_id> <url> <task> [mode]")
        sys.exit(1)

    cohort_id = sys.argv[1]
    url = sys.argv[2]
    task = sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else "text"

    result = run_cohort(cohort_id, url, task, mode=mode)
    print(f"\nN completed: {result['n_completed']}/{result['n_personas']}")
    print(f"Output: {result['output_path']}")
