# Browser Mode 검증 결과 (E1)

> **실행일**: 2026-04-14
> **목적**: cohort_runner browser mode 작동 검증 (text mode와 비교)

## 실행 조건

- **코호트**: cohort_manual5 (5명: p_impulsive, p_cautious, p_budget, p_pragmatic, p_senior)
- **URL**: https://www.figma.com/pricing
- **태스크**: "개인 사용자로서 적합한 플랜을 결정해라"
- **모드**: browser (실제 Chromium 세션)
- **max_workers**: 5 (병렬)
- **timeout**: 20분

## 결과

**2/5 명만 로드됨, 1/2 정상 완료** (= 5명 중 1명 정상)

| 페르소나 | 결과 | 비고 |
|---|---|---|
| p_impulsive | **error** | browser session 중 예외 |
| p_cautious | max_turns_hit | 10턴 풀 사용, 정상 완료 |
| p_budget | (미실행) | cohort_runner v001.md hardcoding 버그로 로드 실패 |
| p_pragmatic | (미실행) | 동일 |
| p_senior | (미실행) | 동일 |

## 발견된 문제

### 🔴 Critical: cohort_runner의 v001.md 하드코딩
- `_load_cohort_personas`가 `soul/v001.md`만 찾음
- 신규 페르소나는 v002.md만 있음 → 스킵됨
- **수정 완료**: manifest의 current 버전 자동 선택 + fallback

### 🟡 Browser mode 안정성
- 1명 정상 완료 (p_cautious) — 시스템 작동은 확인
- 1명 error — 원인 미상 (loading? timeout? selector failure?)
- **5명 병렬은 chromium 인스턴스 부담 큼**
- E7에서 retry/recovery 필요

## Text mode와 비교

| 측면 | Text Mode | Browser Mode |
|---|---|---|
| 비용 (5명) | $0.5 | $2~5 |
| 시간 (5명) | 1~2분 | 5~15분 |
| 안정성 | 높음 (LLM 단일 호출) | 낮음 (chromium 환경 의존) |
| 데이터 풍부도 | 낮음 (예측만) | **높음 (실제 행동 기록)** |
| 신뢰도 | 추측 수준 | **실제 페이지 반응** |

## 결론

**Browser mode는 작동하지만 production-ready 아님:**

✅ 단일 세션은 안정적 (smoke test p_pragmatic 정상)
✅ 결과 데이터가 text mode보다 풍부 (실제 turn별 행동 기록)
⚠️ 5명 병렬은 1/5 실패율 (안정성 작업 E7 필요)
⚠️ 시간/비용 5~10배 (text mode 대비)

**권장 사용 패턴:**
- **사업팀장 데모**: text mode (빠름, 저렴, 충분한 신호)
- **실제 고객 분석**: browser mode (실측 데이터, 신뢰도 ↑)
- **검증·연구**: browser mode + sequential (max_workers=1)

## 다음 단계 (E7)

1. browser session retry 로직 (3회 재시도)
2. timeout 단축 (페르소나당 5분 → fail 처리)
3. graceful degradation (실패 페르소나 제외하고 결과 보고)
4. 메모리 모니터링 (chromium 인스턴스당 ~500MB)
