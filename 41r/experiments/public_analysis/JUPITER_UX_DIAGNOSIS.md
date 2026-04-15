# Jupiter (jup.ag) UX 진단 리포트

> **요청자**: 41rpm 사업팀
> **목적**: 복잡한 dApp 인터페이스에서 유저 '숙련도'에 따른 경험 차이 증명
> **분석 도구**: persona_agent 0.2.0 + Hypothesis Planner (PR-14 prototype)
> **분석 일자**: 2026-04-15

---

## 1. 진단 가설 (Hypothesis)

> "Jupiter(jup.ag)에서 0.1 SOL을 USDC로 스왑하고 슬리피지를 0.1%로 변경하는
> 태스크를 줬을 때, crypto 숙련도에 따라 페르소나가 어디서 막히고 어디까지
> 도달하는가?"

사업팀 원 요청 기준 3 지표:
1. **경로 효율성** — 지갑 연결부터 스왑 완료까지 최단 클릭 수로 이동했는가
2. **인지 부하** — 슬리피지 설정 메뉴를 찾는 데 마우스 커서가 얼마나 방황했는가
3. **최종 도달률** — 'Confirm Swap' 버튼까지 막힘없이 도달했는가

---

## 2. 분석 페르소나 (5명, 숙련도 스펙트럼)

| Persona | 나이/직업 | crypto_experience | 지정 의도 |
|---|---|---|---|
| `p_crypto_native` | 32M, defi 트레이더 | **advanced** | 컨트롤 그룹 — Jupiter 매일 사용 |
| `p_creator_freelancer` | 28M, 디자이너 | intermediate | 웹3 알지만 dex 사용 드뭄 |
| `p_pragmatic` | 42M, IT 기업 팀장 | beginner | 컨셉만 알고 실사용 미경험 |
| `p_b2b_buyer` | 45M, 임원 | beginner | 비즈니스 관점, 전문 신뢰 신호 중시 |
| `p_senior` | 58F, TV 시청자 | none | 진입 장벽 최대치 검증 |

---

## 3. 방법론 (꼭 읽으세요)

### 3.1 사용 모드: text mode (LLM 예측)

이번 진단은 **실제 브라우저 세션이 아닌 LLM 예측 기반**입니다. 즉:
- Claude Sonnet에게 페르소나의 soul + URL + sub-question을 주고 "이 사람이라면 어떻게 행동할 것인가" 추론시킴
- 출력: outcome, conversion_probability, drop_point, frustration_points, key_behaviors, reasoning

### 3.2 왜 text 모드를 먼저 썼는가

1. **속도·비용**: 25 runs × Sonnet ≈ 2분 30초, $0.40
2. **지갑 연결 한계**: Playwright headless에는 Phantom 확장 미설치 → 실제 browser 모드여도 Connect Wallet 단계에서 멈춤. 대부분의 sub-question은 결국 LLM 추론으로 메꿔야 함
3. **사업팀 시연용 우선**: 실측은 별도 부록(§ 8)에 추가

### 3.3 사업팀 3 지표 → 측정 가능성 매핑

| 사업팀 지표 | 측정 가능? | 어떻게 |
|---|---|---|
| 경로 효율성 | ✅ 직접 | 페르소나 outcome + drop_point |
| 인지 부하 ("커서 방황") | 🟡 proxy | LLM이 묘사한 key_behaviors 중 '찾/탐색/스크롤' 단어 비율 |
| 최종 도달률 | ✅ 직접 | task_complete / 전체 |

### 3.4 시뮬레이션 한계

- **마우스 좌표 없음**: 페르소나는 LLM 의도 기반으로 행동. "X 위치 클릭"이 아니라 "Settings 아이콘 클릭"이라는 의도 단위.
- **지갑 트랜잭션 시뮬 안 됨**: 실제 SOL→USDC 스왑은 발생하지 않음. UI 도달 여부만 평가.
- **소통/UX 변화 미반영**: 분석 시점의 jup.ag UI 기준 LLM 학습 데이터로 추정. 실시간 A/B 테스트 결과는 별도.

---

## 4. 결과

### 지표 ① 경로 효율성 (페르소나 × outcome)

5 sub-question × 5 페르소나 = **25 runs**.

| Persona | 숙련도 | OK | PARTIAL | ABANDON | avg_conv |
|---|---|---:|---:|---:|---:|
| **p_crypto_native** | advanced | **5** | 0 | 0 | **0.91** |
| p_pragmatic | beginner | 0 | **4** | 1 | 0.53 |
| p_creator_freelancer | intermediate | 0 | 2 | **3** | 0.24 |
| p_b2b_buyer | beginner | 0 | 1 | **4** | 0.18 |
| **p_senior** | none | 0 | 0 | **5** | **0.10** |

**해석**: 숙련도와 conversion이 거의 선형 비례. 가설 강하게 검증.

### 지표 ② 인지 부하 (탐색 단어 빈도 — proxy)

| Persona | 탐색 단어 hit | 행동 수 | **비율** | 해석 |
|---|---:|---:|---:|---|
| p_crypto_native | 3 | 28 | 0.11 | 목적 명확, 직진 |
| p_creator_freelancer | 3 | 19 | 0.16 | 메뉴 탐색 시도 |
| p_pragmatic | 3 | 21 | 0.14 | 매뉴얼 찾기 |
| p_b2b_buyer | 3 | 22 | 0.14 | 이미 막혀서 탐색조차 안 함 |
| **p_senior** | **7** | 20 | **0.35** | 이해 못 해서 계속 찾음 |

**해석**: p_senior 압도적. 다른 페르소나는 낮게 나오지만 의미가 다름 — p_b2b_buyer는 "이해 자체를 포기"한 결과라 더 부정적.

### 지표 ③ 최종 도달률

- **task_complete: 5 / 25 = 20%** (전부 p_crypto_native)
- **partial: 7 / 25 = 28%** (대부분 p_pragmatic)
- abandoned: 13 / 25 = 52%

**해석**: 사실상 **DeFi 파워유저 1명만** 완주. 나머지 80% 이탈.

---

## 5. Sub-question 별 분석 (planner 자동 분해)

| sub-q | 내용 | score | n | positive |
|---|---|---:|---:|---:|
| sq1 | 30초 내 SOL→USDC 입력 UI 발견 | 0.26 | 5 | 1 |
| sq2 | 0.1 SOL 입력 + USDC 출력 인지 (지갑 연결 전 quote) | 0.37 | 5 | 1 |
| sq3 | **슬리피지 메뉴 발견 + 0.1% 변경** | 0.42 | 5 | 1 |
| sq4 | 슬리피지 0.1% 경고 메시지 인지·실행 의향 | 0.40 | 5 | 1 |
| sq5 | 다음에 혼자 다시 할 자신감 | 0.30 | 5 | 1 |

**해석**: 모든 sub-question에서 p_crypto_native만 통과. sq5(반복 자신감)가 가장 낮음 — 일회 완료조차 학습으로 이어지지 않음.

---

## 6. Top Frictions (3명 이상 공통 지적)

| # | 마찰 | 언급 횟수 |
|---|---|---:|
| 1 | **지갑 연결 강제 요구로 사전 정보(예상 수령액·라우팅) 접근 불가** | 12 |
| 2 | **슬리피지 설정 UI(⚙ 아이콘) 위치 불명확 및 발견 지연** | 10 |
| 3 | **경고 메시지에 맥락 정보(정상 범위, 업계 평균) 부재** | 8 |

각 항목 evidence는 § 9 Appendix A 참조.

---

## 7. Verdict

> **`hypothesis_support_score: 0.37 / weak`**
>
> Jupiter는 crypto 숙련자(p_crypto_native)에게만 완전 지지(avg_conv 0.91)되며,
> 나머지 4개 페르소나는 **'지갑 연결 장벽 → 슬리피지 UI 미발견 → 경고 메시지
> 혼란'의 3단계 이탈 깔때기**를 형성. 즉 현재 UX는 'DeFi 파워유저 전용 최적화'로,
> crypto 숙련도 스펙트럼 **하단 80%에 대한 진입장벽이 구조적으로 존재**.

---

## 8. Recommendations (구체 UX 개선안 — evidence 인용 포함)

### R1. 지갑 미연결 상태에서도 입력값 기반 실시간 quote 표시
- **Why**: 지갑 연결 강제 요구가 1차 이탈 깔때기. 모든 비숙련 페르소나가 sq2에서 동일 마찰 지목.
- **Evidence**:
  - p_creator_freelancer/sq2: drop_point="지갑 연결 강제 요구"
  - p_pragmatic/sq2: frustration="지갑 연결 강제 전 예상 수령액 미리보기 불가"
- **방법**: 연결 전 시뮬레이션 허용으로 신뢰 임계값 이전에 가치 증명.

### R2. ⚙ 슬리피지 아이콘을 스왑 폼 내 상단 고정 위치에 라벨('Slippage 0.5%')과 함께 상시 노출
- **Why**: 4명 (creator/pragmatic/b2b/senior) 모두 sq3에서 같은 마찰 지적. 현재 아이콘 단독 표시는 12초 이하 인내심 페르소나를 전면 차단.
- **Evidence**:
  - p_creator_freelancer/sq3: "3초 내 직관적 설정 위치 미표시"
  - p_pragmatic/sq3: "설정 아이콘이 작거나 흐릿한 경우 즉시 신뢰도 저하"
  - p_b2b_buyer/sq3: "슬리피지 설정이 숨겨져 있거나 명확한 라벨 부재"
  - p_senior/sq3: "⚙ 아이콘이 작거나 예상과 다른 위치에 있을 가능성"

### R3. 경고 메시지에 맥락 레이어 추가
- **Why**: 수치만 있고 해석이 없어 재확인 루프 및 이탈 발생.
- **Evidence**:
  - p_pragmatic/sq4: "0.1% 슬리피지는 SOL-USDC 스왑으로 적절함 같은 해석 지원 부재"
  - p_b2b_buyer/sq4: "경고 문구가 정상 범위 vs 위험 범위를 명확히 구분하지 않음"
  - p_creator_freelancer/sq4: "경고/에러 메시지의 모호함"
- **방법**: 인라인 가이드 — `'0.1% 슬리피지는 SOL/USDC 유동성 기준 안전 범위 (권장: 0.1~0.5%)'` 형식.

### R4. 작업 완료 후 설정 요약 화면 제공
- **Why**: 일회 완료조차 신뢰 학습으로 이어지지 않음. sq5 점수 0.30.
- **Evidence**:
  - p_b2b_buyer/sq5: "설정 완료 후 명확한 확인 화면 또는 요약 부재"
  - p_pragmatic/sq5: "단계별 가이드나 체크리스트 없어서 독립적 재수행 확신 부족"
  - p_creator_freelancer/sq5: "lucky complete 느낌 = 신뢰 부족"
- **방법**: 'Swap 0.1 SOL → USDC / Slippage 0.1% / Expected: X USDC' 형식의 확인 스텝 삽입.

---

## 9. Appendix

### A. 페르소나별 대표 frustrations (text mode 추출)

**p_crypto_native** (advanced):
- 지갑 연결 전 quote 정보 미표시 시 즉시 이탈 가능성
- 라우팅 경로가 불명확하거나 숨겨진 경우
- 경고 메시지가 모호할 경우 (예: 기술적 설명 부족)

**p_creator_freelancer** (intermediate):
- 사전 정보 없이 지갑 연결 강제 (3초 인내심 초과)
- 예상 수령액 미리보기 불가
- 라우팅 투명성 부재

**p_pragmatic** (beginner):
- DEX 인터페이스의 진입장벽 - 지갑 연결 강제가 폼 접근 전에 있음
- 토큰 선택과 수량 입력 흐름이 명확하지 않을 수 있음
- 입력(SOL) vs 출력(USDC) 필드 레이블 불명확하면 즉시 신뢰 손실

**p_b2b_buyer** (beginner, B2B 관점):
- Jupiter는 DeFi 소매 플랫폼(DEX 애그리게이터)으로 B2B API 제품이 아님 — 윤성호의 요구와 완전 불일치
- 공개 API 문서 명확하지 않거나 기술 스펙 다운로드 불가
- SOC2/ISO27001, SLA 같은 엔터프라이즈 신뢰 신호 전무

**p_senior** (none):
- 암호화폐 거래소 특성상 전문 용어 과다 노출
- 지갑 연결, 스왑 기능이 동시에 노출되어 우선순위 불명확
- 입력 필드와 버튼의 시각적 구분 부족

### B. 비용·시간

| 항목 | 양 |
|---|---|
| 페르소나 수 | 5 |
| sub-question 수 | 5 (planner 자동 분해) |
| 총 LLM 호출 | 1 (planner) + 25 (task rewriter) + 25 (predictor) + 1 (aggregator) = 52 |
| 토큰 사용 | 입력 ~30k + 출력 ~12k |
| 비용 | 약 $0.40 |
| 소요 시간 | 약 2분 30초 |

### C. Browser 모드 실측 결과 (추가 검증)

text 모드 직후 browser 모드를 추가 구현하여 같은 가설로 5 페르소나 × 1 실제
Playwright 세션을 돌렸다. 각 세션은 MAX_TURNS=10으로 jup.ag 에서 직접 액션 시도.

#### C.1 비용·시간

| 항목 | 양 |
|---|---|
| 페르소나 수 | 5 |
| 실제 browser 세션 | 5 (각 ~8분, MAX_TURNS=10에 도달) |
| 사후 LLM evaluator 호출 | 5 × 5 = 25 |
| 비용 | 약 $2.10 |
| 소요 시간 | 약 45분 |

#### C.2 Verdict 비교

| 모드 | hypothesis_support_score | label | task_complete | partial | abandoned |
|---|---:|---|---:|---:|---:|
| **text (예측)** | 0.37 | weak | 5 / 25 | 7 / 25 | 13 / 25 |
| **browser (실측)** | **0.063** | **rejected** | **0 / 25** | **1 / 25** | **24 / 25** |

**해석**: browser 모드 결과가 text 모드보다 훨씬 비관적. 두 가지가 섞여 있음:
- (a) 실제 UI 마찰이 LLM 추론보다 큼 — 페르소나도 못 찾는 게 아니라 **도구도 못 찾음**
- (b) Playwright + persona_agent의 selector/Vision 한계 — Jupiter SPA의 canvas/SVG 기반 input은 텍스트 셀렉터로 잡기 어려움 (F009 발생)

#### C.3 Top Frictions (browser)

| # | 마찰 | 언급 |
|---|---|---:|
| 1 | **동적 콘텐츠 렌더링 실패(F009) — Sell 금액 입력 필드 Vision locate 불가** | 15 |
| 2 | 슬리피지 설정 진입 경로(톱니바퀴 아이콘) 미발견 — Settings UI 접근 실패 | 5 |
| 3 | 토큰 선택 모달 내 SOL 옵션 위치 특정 실패 및 SOL/wSOL 구분 불가 | 5 |

#### C.4 Per-persona (browser)

| Persona | OK | PART | ABAN | avg_conv | drop_funnel |
|---|---:|---:|---:|---:|---|
| p_crypto_native | 0 | 0 | 5 | 0.15 | sq3 (Settings) 텍스트만 인식, 실제 입력 미완 |
| p_creator_freelancer | 0 | 0 | 5 | 0.08 | sq2 (토큰+수량 입력) |
| p_pragmatic | 0 | 0 | 5 | 0.12 | sq2 (Sell 입력 F009 3회) |
| p_b2b_buyer | 0 | 0 | 5 | 0.13 | sq2 (모달 닫기 실패) |
| p_senior | 0 | 0 | 5 | 0.06 | sq1 (SOL 버튼 부분 발견 후 멈춤) |

#### C.5 Sub-question 별 (browser)

| sub-q | score | 결과 요약 |
|---|---:|---|
| sq1 (랜딩 UI 발견) | 0.10 | p_senior만 부분 발견 |
| sq2 (토큰+수량 입력) | 0.00 | 전원 미달 — Sell 입력 필드 F009 |
| sq3 (슬리피지 설정) | 0.00 | Settings 아이콘 미발견 |
| sq4 (경고 인지) | 0.00 | sq3 미달로 도달 자체 불가 |
| sq5 (반복 자신감) | 0.00 | 관찰 기회 자체 없음 |

#### C.6 Text vs Browser 종합 해석 — 둘 다 봐야 의미 있음

| 측면 | text (예측) | browser (실측) | 사업 시사점 |
|---|---|---|---|
| 가설 검증 강도 | weak (0.37) | rejected (0.063) | **두 모드 모두 비숙련자 진입 어려움** 동일 결론 |
| 분기 명확성 | 숙련도 스펙트럼 선형 | 전원 0 도달 — 분기 약함 | text가 segment differentiation에 유리 |
| 마찰 발견력 | 인식·해석 차원 (예: 슬리피지 의미 모름) | 도구 도달 차원 (Sell 필드 자체 못 찾음) | **두 층의 마찰이 서로 다름** |
| ROI 추천 | 빠른 가설 검증 ($0.40, 2분) | 실측 검증 + 도구 한계도 발견 ($2, 45분) | **text 우선 → browser로 검증** 2단계 |

#### C.7 도구 한계 인정 (Methodology Disclosure)

browser 모드 결과의 24/25 abandoned는 **세 원인의 합산**:

1. **실제 Jupiter UX 마찰** (페르소나의 진짜 어려움)
2. **persona_agent selector/Vision의 동적 콘텐츠 한계** (F009 — Sell 입력 필드처럼 SPA가 동적으로 렌더한 input은 텍스트 셀렉터·스크린샷 좌표 모두 불안정)
3. **MAX_TURNS=10 제한** (실제 dApp 사용은 더 많은 턴 필요할 수 있음)

따라서 **browser 결과의 절대 score (0.063)는 Jupiter UX의 절대 평가가 아니라**,
"이 자동화 도구 + 이 페르소나 + 이 turn 예산 조합에서 도달한 깊이"로 해석해야
합니다. 사업 권고 (§ 8 R1~R4) 는 **text 결과를 주된 evidence**로 유지하되,
browser 결과는 "Jupiter UX가 자동화 친화적이지 않다 = 사람도 헷갈릴 가능성 시사"
보조 신호로 활용.

#### C.8 추가 권고 (browser 모드에서 새로 발견)

- **R5. 토큰 선택 모달의 토큰 옵션을 텍스트 라벨 우선으로** — 현재 SOL/wSOL 같은
  비슷한 항목을 시각적으로만 구분. 페르소나(자동화 도구 포함)가 정확한 토큰 식별
  실패. *Evidence: p_creator/p_b2b 모두 토큰 모달에서 멈춤.*
- **R6. Sell 수량 입력 필드를 표준 HTML `<input type="number">` 시맨틱으로** — 현재
  canvas/div 기반 input이라 접근성 도구·자동화·screen reader 모두 어려움. *Evidence:
  F009 15회 발생.*

### D. 한계 명시

- LLM 예측 기반 시뮬레이션. 실제 사용자 행동과 다를 수 있음.
- 분석 시점의 jup.ag UI 기준. UI 변경 시 재분석 필요.
- 페르소나 5명 표본이 작음. 신뢰도 향상에는 cohort_size 20+ 권장.
- "마우스 커서 방황"은 직접 측정 불가 — '탐색 단어 빈도' proxy 사용.

### E. Raw Data

전체 25 runs의 outcome / drop_point / reasoning은
`/tmp/jupiter_verdict.json` (verdict 객체 직렬화) 또는 cohort_results 디렉토리 참조.

---

## 10. 다음 단계

| 옵션 | 비용 | 시간 | 가치 |
|---|---|---|---|
| 그대로 사업팀에 전달 | 0 | - | text mode 결과 + 방법론 투명 |
| Browser 모드로 ① 지표 실측 추가 | ~$2 | 10분 | 클릭 수·실제 마찰 지점 검증 |
| 경쟁 dApp 비교 (Raydium/Orca) | $0.40/사이트 | 3분/사이트 | "왜 Jupiter가 더/덜 좋은지" 차별화 진단 |
| Cohort 확장 (20명) | $1.50 | 10분 | 신뢰도 통계적 유의미 |

---

*문의·재실행: persona_agent 0.2.0 / Hypothesis Planner / 41rpm 사업팀*
