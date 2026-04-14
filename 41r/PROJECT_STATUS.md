# 41R Persona Market — 프로젝트 현황 리포트

> **작성일**: 2026-04-13
> **대응 문서**: Constitution v1.0, Slice-H1
> **단계**: H1 검증 준비 완료, 아웃바운드 실행 전

---

## 1. 시스템 구현 현황

### 모듈 (7/7 완료)

| 모듈 | 상태 | 핵심 기능 |
|---|---|---|
| M1 Persona Store | **완료** | create/read/append_observation/persona_at + 콘텐츠 해시 ID |
| M2 Browser Runner | **완료** | Playwright 로컬 + Vision click fallback + 셀렉터 메모리 |
| M3 Agent Loop | **완료** | Plan→Decision(Vision)→Tool→Action 루프, MAX_TURNS=10 |
| M4 Provenance | stub | H1에서 불필요, v4-full |
| M5 Report Generator | **완료** | LLM 분석 레이어 + HTML 리포트 + lineage.json |
| M6 Review Agent | **완료** | inspect/evaluate/propose/compare + CLI |
| M7 Version Manager | **완료** | append-only + manifest + rollback |

### Cross-cutting (4/4 완료)

| 컴포넌트 | 상태 | 비고 |
|---|---|---|
| Provider Router | **완료** | 3-Tier (현재 Sonnet+Haiku만 사용, Opus/Advisor OFF) |
| Cache | **완료** | content hash + TTL + cache_disabled (thread-safe) |
| Events Log | **완료** | JSONL append |
| Hooks | **완료** | post_session_end → Review Agent auto-inspect |

### 핵심 개선 이력

| 버전 | 변경 | 효과 |
|---|---|---|
| v1 → Vision Mode | A11y tree → 스크린샷 기반 판단 | "봇 한계"가 아닌 "유저 관점" 관찰 |
| v1 → Vision Click | 텍스트 셀렉터 → 좌표 기반 클릭 fallback | 한국어/동적 렌더링 클릭 성공 |
| v1 → 셀렉터 메모리 | 실패 패턴 기록 + 성공 전략 우선 시도 | 사이트별 학습 |
| soul v001 → v002 | 2줄 → 구조화된 프로필(5개 성향+세대+트리거) | profile 수치 직접 인용한 판단 |
| Opus → Sonnet only | advisor OFF, plan도 Sonnet | 비용 90%+ 절감 |

---

## 2. 페르소나

### 현재 2명

| ID | 이름 | 핵심 특성 | soul 버전 |
|---|---|---|---|
| p_impulsive | 충동적 쇼퍼 민수 (28세, 마케터) | visual_dependency: 0.9, decision_speed: 0.95, privacy: 0.2 | v002 |
| p_cautious | 신중한 리서처 지영 (35세, 회계사) | research_depth: 0.95, privacy: 0.8, price_sensitivity: 0.6 | v002 |

### Soul v002 구조

```yaml
# 기본: name, age, age_group, region, occupation
# 타이밍: patience, reading_wpm, decision_latency, loading_tolerance
# 5개 성향: visual_dependency, decision_speed, research_depth, privacy_sensitivity, price_sensitivity
# 세대: tech_literacy, device_preference, social_proof_weight, brand_loyalty, ad_tolerance
# 트리거: frustration_triggers[], trust_signals.important[], trust_signals.irrelevant[]
# 서술: 10줄 voice_sample (구체적 행동 묘사)
```

---

## 3. 검증 결과

### 상황-반응 테스트 (최신)

| 파트 | 통과 | 비율 | 의미 |
|---|---|---|---|
| A. 방향성 | 8/11 | 73% | 세그먼트 간 차별화 일관 |
| B. 세밀함 | 8/8 | **100%** | 구체적 상황에서 올바른 반응 |
| **종합** | | **86% (A등급)** | |

### 실패 항목
- A3: Shopify에서 read 비율 역전 (측정 방법 한계)
- A4: 충동형 reason에 신뢰 키워드 맥락상 등장 (키워드 매칭 한계)

### Ground Truth 대조 (공개 벤치마크)

| 출처 | 검증 항목 | 결과 |
|---|---|---|
| Baymard (이탈률 70%) | 충동형 이탈률 67% | **일치** |
| NNGroup (20~28% 읽음) | 충동형 read 20%, 신중형 40% | **방향 일치** |
| Think with Google (Messy Middle) | 충동형=즉시성, 신중형=권위/소셜프루프 | **일치** |
| Baymard (이탈 이유) | 충동형=마찰, 신중형=둘러보기 | **일치** |

### A/B 역검증 (PriceCharting)
- 실제: "Price Guide" 버튼이 "Download" 대비 +620.9% CTR
- 41R: 충동형은 CTA 미도달(시각 트리거 부재), 신중형은 CTA 도달 후 정보 부족으로 미클릭
- 판정: **방향성 일치**, 정량 재현은 H2 과제

---

## 4. H1 체크리스트

| 항목 | 상태 |
|---|---|
| Golden session 5~10개 | **5개 완료** (리포트 미생성, 세션 데이터 있음) |
| 공개 A/B 역검증 | **1건 완료** (PriceCharting) |
| Sample report | **완료** (3사이트, UX 이슈+개선 제안) |
| lineage.json | **완료** |
| CPO 30명 리스트업 | **완료** (한국 15 + 글로벌 15) |
| 아웃바운드 템플릿 | **완료** (3종 + follow-up) |
| 피드백 폼 | **완료** (kill criteria 매핑) |
| 페르소나 검증 | **완료** (86% A등급) |

---

## 5. 비용

### LLM 라우팅 (현재 설정)

| 역할 | 모델 | 용도 |
|---|---|---|
| plan_generation | Sonnet | 세션 계획 (1회/세션) |
| decision_judge | Sonnet | 매 턴 판단 (Vision 입력) |
| page_summarizer | Haiku | 페이지 요약 |
| tool_selector | Haiku | 도구 선택 |
| vision_clicker | Haiku | 셀렉터 실패 시 좌표 식별 |
| report_analyzer | Sonnet | 세션 분석→인사이트 |

### 세션당 예상 비용: ~$0.3~0.5 (Sonnet only)

---

## 6. 알려진 한계

1. **MAX_TURNS=10**: 신중형이 항상 max_turns_hit → 턴 늘리면 비용 증가
2. **Vision click 좌표 정확도**: Haiku의 좌표 추정은 ±20px 오차 가능
3. **Cloudflare/CAPTCHA**: 봇 탐지 사이트에서 전환 불가 (실제 유저 문제 아님)
4. **soul v002 토큰**: 상세 프로필로 인해 매 턴 입력 토큰 증가 → 속도 저하
5. **통계적 유의성**: 6세션으로는 부족, 최소 30+ 필요
6. **정량 예측 불가**: "전환율 X%"는 아직 예측 못 함 (H2 과제)

---

## 7. 다음 단계

### 즉시 (H1 아웃바운드)
1. CPO 리스트에서 1순위 타겟 5개 선정
2. 각 타겟 사이트를 41R로 분석 (템플릿 C — 선행 리포트 제공)
3. 콜드 이메일 발송
4. 피드백 수집 → kill criteria 판단 (유료 전환율 5% 이상?)

### 단기 (H1 내)
- 페르소나 3~5명 추가 (가격민감형, Gen Z, 시니어)
- 상황-반응 테스트 자동화 스크립트
- Golden session 30+ 확보

### 중기 (H2)
- Opus advisor 재활성화 + 비용 대비 정확도 측정
- 실제 고객 GA 데이터와 예측 대조
- 페르소나 정확도 정량 검증 (Seed only vs Full memory)

---

*이 문서는 Constitution v1.0의 Sprint 1 종료 시점 현황을 기록한다.*
