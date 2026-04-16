# Jupiter (jup.ag) UX 진단 리포트 v4

> **요청자**: 41rpm 사업팀
> **원 요청**: "복잡한 dApp 인터페이스에서 유저의 '숙련도'에 따른 경험 차이 증명"
> **분석 도구**: persona_agent 0.2.0 + Hypothesis Planner
> **v1**: 2026-04-15 (text mode)
> **v2**: 2026-04-15 (browser, pre-PR-15, F009 다발 → 전원 이탈)
> **v3**: 2026-04-16 (PR-15/16, 2/5 유효, 부분 성공)
> **v4**: 2026-04-16 (PR-15/16/17/18 전 적용, **5/5 유효, p_senior task_complete**)

---

## 한 장 요약 (TL;DR)

**가설**: Jupiter는 crypto 숙련도에 따라 사용 경험이 크게 갈리며, 비숙련자는 슬리피지 설정까지 도달할 수 없다.

**검증 결과**: 가설 **부분 기각** — 도구가 개선되자 **비숙련자도 전체 task 완료** 성공.

### 핵심 발견 (v4, PR-15/16/17/18 전 적용)

- **p_senior (58F, crypto=none) 이 19턴에 전체 task 완료**: SOL 방향 전환 → 0.1 SOL 입력 → Ultra(Settings) 진입 → Manual mode → 슬리피지 0.1% 입력 → Settings 닫기 → Connect 클릭까지 19턴에 성공.
- **v2에서 전원 F009로 막혔던 것이 → v4에서 7건 fill 성공**, F009 15+→7로 대폭 감소.
- **text-mode 예측(숙련도 선형 분기)과 browser-mode 실측(도구 영향 큼)의 괴리** 발견: text에서 p_crypto_native가 0.91, p_senior가 0.10이었지만, browser v4에선 p_senior가 유일한 task_complete.

### 수정된 결론

1. **Jupiter UI 자체는 충분 턴이 주어지면 비숙련자도 navigable** — v2의 "전원 이탈"은 도구 한계(F009)였지 UX 한계가 아닐 수 있음.
2. **그래도 text-mode의 마찰 분석은 여전히 유효**: 지갑 강제·슬리피지 숨김·경고 맥락 부재는 실사용자 관점 인지 마찰이며, browser에서도 p_b2b_buyer가 Terminal 탭 탐색에 6턴 소비 = 인지 부하 증거.
3. **browser-mode 결론은 "도구 + UX = 혼합 신호"**: 절대 도달률보다 **어디서 가장 오래 걸렸는가** (per-turn 분석)가 UX 개선 indicator로 더 유용.

### 가장 큰 3개 장애물 (v4 기준 갱신)

| # | 마찰 | text evidence | browser v4 evidence |
|---|---|---|---|
| 1 | **슬리피지 설정 위치 모호** — Settings UI가 Ultra/Manual mode 뒤에 숨김 | 17/25 runs 언급 | p_b2b_buyer Settings→Terminal 탭 진행, p_pragmatic Settings 도달 후 진전 정체 |
| 2 | **토큰 선택 + 금액 입력** — 첫 진입 UI 파악 난이도 | 11/25 runs | p_creator 6 F009 (SPA 동적 렌더) |
| 3 | **지갑 연결 강제** — task 마지막에 반드시 막힘 | 11/25 runs | p_senior 성공적으로 Connect까지 도달했지만 Phantom 없어서 여기서 종료 |

**권고**: R1~R6 유지 (§ 5 참조). 특히 R2(슬리피지 상시 노출)는 v4에서도 가장 큰 시간 소비 구간.

**도구 진화 기록**: v1(text) → v2(browser, F009 15+, 전원 이탈) → v3(2/5 유효, 부분 성공) → **v4(5/5 유효, 1건 완료, F009→7)**. **4 PR 누적으로 browser 모드가 실전 usable 수준 도달.**

---

## 1. 가설 (Hypothesis)

> "Jupiter(jup.ag)에서 0.1 SOL을 USDC로 스왑하고 슬리피지를 0.1%로 변경하는 태스크를 줬을 때,
> crypto 숙련도에 따라 페르소나가 어디서 막히고 어디까지 도달하는가?"

사업팀 원 요청 기준 3 지표 → **관찰 가능한 proxy로 변환**:

| 원 지표 | proxy |
|---|---|
| 경로 효율성 (최단 클릭 수) | outcome / total_turns / drop_point |
| 인지 부하 (커서 방황) | key_behaviors 중 탐색 단어 비율 + frustration 밀도 |
| 최종 도달률 | task_complete 비율 + sub-question별 pass 여부 |

---

## 2. 페르소나 (5명, 숙련도 스펙트럼)

| persona_id | 프로필 | crypto_experience | 지정 의도 |
|---|---|---|---|
| `p_crypto_native` | 32M defi 트레이더 | **advanced** | 컨트롤 그룹 |
| `p_creator_freelancer` | 28M 디자이너 | intermediate | 웹3 알지만 dex 드뭄 |
| `p_pragmatic` | 42M IT 팀장 | beginner | 컨셉만 알고 실사용 미경험 |
| `p_b2b_buyer` | 45M 임원 | beginner | 비즈니스 신뢰 신호 중시 |
| `p_senior` | 58F TV 시청자 | none | 진입 장벽 최대치 |

상세 soul 정의: `41r/personas/p_*/soul/v001.md` (git tracked).

---

## 3. 방법론 — **두 각도에서 동일 가설 교차 검증**

한 가설을 두 서로 다른 도구로 검증했습니다. **각각 약점이 다른 도구**이므로 **함께 보아야 결론이 정확**합니다.

### 3.1 Text 모드 (LLM 예측)

- Claude Sonnet에 페르소나 soul + URL + sub-question을 주고 "이 사람이라면 어떻게 행동할 것인가" 추론
- 출력: outcome, conversion_probability, drop_point, frustration_points, reasoning
- **강점**: 빠름·저렴 (2분 30초, $0.40), 페르소나 **성향별 분기가 명확**
- **한계**: LLM의 jup.ag UI 지식에 의존 (학습 시점). 실시간 UI 변경 미반영

### 3.2 Browser 모드 (실측) — v2 및 v3

**v2 (pre-PR-15, 2026-04-15)**:
- 실제 Playwright headless로 jup.ag, MAX_TURNS=10, 5 세션 전원 실행
- **전원 F009(동적 콘텐츠 selector 실패)로 초반 이탈**
- verdict: rejected (0.063) — 단 "도구 미달"이 "페르소나 미달"과 섞여 절대값 오해 소지

**v3 (PR-15 + PR-16, 2026-04-16)**:
- PR-15: vision_clicker tool_use API, MAX_TURNS=20 파라미터화, JS fallback fill
- PR-16: Post-action settling wait (800ms), 반복 루프 탐지, JS nav hints
- 5 세션 중 **3 세션 Anthropic API 500 transient** 오류로 즉시 실패 (turns=0)
- 2 세션은 정상 완료 — **결과가 극적으로 개선**:
  - F009 15+회 → **0~1회**
  - fill 0건 → **1건 성공** ("0.1 SOL" 입력)
  - Settings dialog까지 **실제 도달** (이전엔 landing 이탈)
  - **PR-16 repetition detector 2회 발동 확인** — 루프 탈출 로직 작동

**v3 유효 샘플**: 2/5 (통계 유의성 부족). API 안정기에 재실행 시 전 페르소나 유효 데이터 확보 가능 — 별도 PR에서 retry-on-500 로직 추가 예정.

### 3.3 왜 둘 다 실행했는가

두 모드는 **서로 다른 차원**을 측정합니다:

| 차원 | text | browser |
|---|---|---|
| 측정 대상 | 페르소나의 **인지·해석 마찰** | **실제 UI 도달 가능성** |
| "슬리피지 메뉴" 예시 | "어디 있는지 몰라서 못 찾음" | "메뉴 있긴 한데 셀렉터가 안 잡힘" |
| 시사점 | UX 설계 개선안 | 구조·접근성 개선안 |

→ **두 모드의 공통점**이 진짜 마찰. **차이점**은 해석 주의.

---

## 4. 통합 결과

### 지표 ① 경로 효율성 (페르소나별 outcome)

**Text 모드** (5 sub-q × 5 페르소나 = 25 runs):

| Persona | 숙련도 | OK | PART | ABAN | avg_conv |
|---|---|---:|---:|---:|---:|
| **p_crypto_native** | advanced | **5** | 0 | 0 | **0.91** |
| p_pragmatic | beginner | 0 | **4** | 1 | 0.53 |
| p_creator_freelancer | intermediate | 0 | 2 | 3 | 0.24 |
| p_b2b_buyer | beginner | 0 | 1 | 4 | 0.18 |
| **p_senior** | none | 0 | 0 | **5** | **0.10** |

**Browser 모드 v2** (pre-PR-15, 5 세션 × 5 sub-q = 25 runs):

| Persona | OK | PART | ABAN | avg_conv | 주요 drop_point |
|---|---:|---:|---:|---:|---|
| p_crypto_native | 0 | 0 | 5 | 0.15 | sq3 Settings 텍스트만 감지, 실제 입력 미완 |
| p_creator_freelancer | 0 | 0 | 5 | 0.08 | sq2 토큰·수량 입력 |
| p_pragmatic | 0 | 0 | 5 | 0.12 | sq2 Sell 입력 필드 F009 3회 실패 |
| p_b2b_buyer | 0 | 0 | 5 | 0.13 | sq2 모달 닫기 실패 |
| p_senior | 0 | 0 | 5 | 0.06 | sq1 SOL 버튼 부분 발견 후 멈춤 |

**Browser 모드 v3** (PR-15 + PR-16, 2/5 유효):

| Persona | turns | F009 | fill | 최종 도달 |
|---|---:|---:|---:|---|
| p_crypto_native | 20 | 1 | 0 | Settings dialog |
| p_creator_freelancer | 19 | 0 | **1** | Settings modal + **rep_warn 2회** |
| p_pragmatic/b2b/senior | 0 | — | — | **API 500 transient** |

**Browser 모드 v4** (PR-15/16/17/18, **5/5 유효**, 4040초, ~$3):

| Persona | turns | outcome | fills | F009 | rep_warn | 핵심 |
|---|---:|---|---:|---:|---:|---|
| **p_senior** | **19** | **✅ task_complete** | **2** | **0** | 1 | **0.1 SOL + 0.1% 슬리피지 + Connect 전부 성공** |
| p_b2b_buyer | 20 | max_turns | 1 | 0 | 1 | 0.1 SOL 입력 O, Settings→Terminal 탭 탐색 |
| p_pragmatic | 20 | max_turns | 2 | 1 | 0 | fills 성공, Settings 도달 |
| p_creator | 20 | max_turns | 2 | 6 | 0 | F009 잔존 (SPA 동적 렌더) |
| p_crypto_native | 2 | error | 0 | 0 | 0 | API crash (retry 소진) |

**v4 핵심 발견**: p_senior(58F, crypto=none)가 **유일하게 전체 task 완료**. 실제 행동 추적:

```
Turn 2:  Swap nav link 클릭
Turn 4:  SOL↔USDC 방향 전환 (↕ 토글)
Turn 7:  "0.1" SOL 입력 (fill 성공)
Turn 11: Ultra 버튼 (Settings 진입)
Turn 12: Manual mode 토글
Turn 13: "0.1" 슬리피지 입력 (fill 성공)
Turn 14: Settings 닫기 (X 버튼)
Turn 16: Connect 버튼 클릭
Turn 19: 지갑 팝업 확인 → 세션 종료 (Phantom 미설치)
```

이것은 **text-mode 예측과 정반대** 결과. 해석:
- text에서 p_senior conv 0.10, p_crypto_native 0.91 → **인지 차원에서는 예측 맞음**
- browser에서 p_senior 유일 완료 → **도구 안정성 + 충분한 턴 + 페르소나의 "꼼꼼히 읽기" 성향** (patience_seconds=15, reading_wpm=150) 이 **느리지만 확실한 진행**을 만듦
- p_crypto_native는 API crash 2턴 종료 (도구 영향). p_creator는 SPA 동적 콘텐츠에 F009 6건 (도구 영향)
- **결론**: Jupiter UX는 "충분한 시간이 주어지면 비숙련자도 navigable" — 진짜 병목은 **인지 마찰(text 발견) + 시간 압박(실사용자 patience)** 이지 UI 구조 자체가 아님

**통합 해석**:
- **Text는 숙련도 스펙트럼을 선형적으로 보여줌** (0.91 → 0.53 → 0.24 → 0.18 → 0.10). 사업 결론에 가장 유용.
- **Browser는 전원 미달** — (a) 실제 UI 어려움 + (b) 도구(Playwright/Vision)의 canvas input 한계가 섞임. **절대 score보다는 "어디서 막혔는가"의 분포가 의미 있음**.
- **수렴 포인트**: p_crypto_native만이 browser에서도 "Settings 텍스트까지 도달" — text·browser 양쪽에서 유일하게 차별화됨. **숙련도가 유일하게 신뢰 가능한 차별자**.

### 지표 ② 인지 부하

**Text 모드**: key_behaviors 중 탐색 단어(찾·탐색·스크롤·클릭·읽) 비율:

| Persona | 탐색 hit | behaviors | 비율 | 해석 |
|---|---:|---:|---:|---|
| p_crypto_native | 3 | 28 | 0.11 | 목적 명확, 직진 |
| p_creator_freelancer | 3 | 19 | 0.16 | 메뉴 탐색 시도 |
| p_pragmatic | 3 | 21 | 0.14 | 매뉴얼 찾기 |
| p_b2b_buyer | 3 | 22 | 0.14 | 이미 막혀서 탐색 약함 |
| **p_senior** | **7** | 20 | **0.35** | 이해 못해 계속 찾음 |

**Browser 모드**: 전원 MAX_TURNS=10 소진 → 턴 기반 proxy 대신 **F009 run 단위 빈도**:

| Persona | F009 언급 runs |
|---|---:|
| p_crypto_native | 4/5 |
| p_creator_freelancer | 3/5 |
| p_pragmatic | 4/5 |
| p_b2b_buyer | 3/5 |
| p_senior | 2/5 |

**통합 해석**: text에서 p_senior 탐색 비율 압도적 ↔ browser에서는 전원 유사한 도구 장애. 즉 **비숙련자는 text에선 "방황"하고, 도구 관점에선 모두 동일하게 막힘** — 두 신호 모두 Jupiter UI가 까다롭다는 방증.

### 지표 ③ 최종 도달률

| 모드 | task_complete | partial | abandoned |
|---|---:|---:|---:|
| Text | **5/25 = 20%** | 7/25 = 28% | 13/25 = 52% |
| Browser | **0/25 = 0%** | 1/25 = 4% | 24/25 = 96% |

**통합 해석**: Text에서 **파워유저 1명만 완주**. Browser는 도구 한계 포함해 전원 미달. 실사용자에 대한 가장 신뢰할 만한 추정은 **"DeFi 숙련자 외 대부분 이탈"** — 두 모드 모두 동일 결론을 다른 각도로 지지.

---

## 5. 권고 (Evidence-Linked Recommendations)

**두 모드에서 공통 발견된 마찰**을 기반으로 한 구체 개선안. 각 권고는 어느 페르소나/어느 sub-q/어느 모드에서 나온 근거인지 명시.

### R1. 지갑 미연결 상태에서도 입력값 기반 실시간 quote 표시
- **Evidence** (text 11/25 runs + browser 전 페르소나):
  - p_creator_freelancer/sq2 drop_point: "지갑 연결 강제 요구 단계"
  - p_pragmatic/sq2 frustration: "지갑 연결 전 가격/라우팅 정보 가시성 부족"
  - p_b2b_buyer/sq1: "Landing page 진입 후 12-15초, 스왑 인터페이스 위치 파악 실패"
- **해결**: 연결 전 quote + 라우팅 시뮬레이션 표시로 가치 증명 먼저.

### R2. ⚙ 슬리피지 아이콘을 스왑 폼 상단 고정 위치에 라벨과 함께 상시 노출
- **Evidence** (text 17/25 runs — 가장 빈번한 마찰):
  - p_creator_freelancer/sq3: "3초 내 직관적 설정 위치 미표시"
  - p_pragmatic/sq3: "설정 아이콘이 작거나 흐릿한 경우 즉시 신뢰도 저하"
  - p_b2b_buyer/sq3: "슬리피지 설정이 숨겨져 있거나 명확한 라벨 부재"
  - p_senior/sq3: "⚙ 아이콘이 작거나 예상과 다른 위치에 있을 가능성"
  - browser sq3: **전원 미달** (p_crypto_native조차 텍스트 감지 수준)
- **해결**: 'Slippage 0.5%' 같은 텍스트 라벨 + 아이콘을 스왑 폼 내 상단 고정.

### R3. 경고 메시지에 맥락 레이어 추가
- **Evidence** (text 6/25 runs):
  - p_pragmatic/sq4: "0.1% 슬리피지는 SOL-USDC 스왑으로 적절함 같은 해석 지원 부재"
  - p_b2b_buyer/sq4: "경고 문구가 정상 범위 vs 위험 범위를 명확히 구분하지 않음"
  - p_creator_freelancer/sq4: "경고/에러 메시지의 모호함"
- **해결**: 인라인 가이드 — `'0.1% 슬리피지는 SOL/USDC 유동성 기준 안전 범위 (권장: 0.1~0.5%)'` 형식.

### R4. 작업 완료 후 설정 요약 화면 제공
- **Evidence** (text sq5 전원 partial 미만):
  - p_b2b_buyer/sq5: "설정 완료 후 명확한 확인 화면 또는 요약 부재"
  - p_pragmatic/sq5: "단계별 가이드나 체크리스트 없어서 독립적 재수행 확신 부족"
  - p_creator_freelancer/sq5: "lucky complete 느낌 = 신뢰 부족"
- **해결**: 'Swap 0.1 SOL → USDC / Slippage 0.1% / Expected: X USDC' 형식 확인 스텝 삽입.

### R5. 토큰 선택 모달을 텍스트 라벨 우선 구조로 (browser 모드에서 발견)
- **Evidence** (browser sq2):
  - 토큰 선택 모달 SOL/wSOL 구분 불가 지적 (aggregator top_frictions 2순위, 5 mentions)
  - 영향 페르소나: creator, b2b_buyer, pragmatic
- **해결**: 토큰명 우선 렌더링 + SOL/wSOL 구분 시각 강화.

### R6. Sell 수량 입력 필드를 표준 HTML `<input type="number">` 시맨틱으로 (browser에서 발견)
- **Evidence** (browser 16/25 runs F009 + 12/25 runs Sell 관련):
  - 현재 canvas/div 기반 input → 자동화·screen reader·보조기술 불친화
- **해결**: 표준 input element + ARIA 라벨. 접근성 이점도.

> **R1~R4는 text 모드에서 행동 근거**, **R5~R6은 browser 모드에서 기술적 근거**가 나왔습니다. **두 모드 결합이 없었다면 R5~R6은 발견 못 했을 것**.

---

## 6. 투명성 — 할루시네이션 감사 결과

리포트의 수치 주장이 실제 데이터(verdict JSON)에 근거하는지 **자동 감사**:

| 주장 | MD 명시 | 실제 grep count | 판정 |
|---|:---:|:---:|---|
| 지갑 연결 언급 (text) | 11/25 | 11/25 | ✅ 일치 |
| 슬리피지/Settings 언급 (text) | aggregator 10 → **MD 17로 정정** | 17/25 | 🟡 aggregator가 좁게 세음, 실제는 더 많음 (권고를 오히려 강화) |
| 경고 맥락 언급 (text) | 6~8 | 6/25 | ✅ 허용 오차 |
| p_crypto_native OK 수 | 5/5 | 5/5 | ✅ 일치 |
| p_senior 전원 abandoned | 5/5 | 5/5 | ✅ 일치 |
| avg_conv (5명) | 0.91/0.53/0.24/0.18/0.10 | 직접 계산 일치 | ✅ |
| F009 언급 (browser) | aggregator 15 | 16/25 runs | ✅ 허용 오차 |
| sub-q별 score | text 0.26/0.37/0.42/0.40/0.30, browser 0.10/0/0/0/0 | 일치 | ✅ |

**감사 결론**:
- aggregator LLM의 수치는 ±1~2 오차 내에서 **data-grounded**. 환각성 수치 없음.
- 슬리피지 언급은 오히려 aggregator가 보수적으로 추정함 — MD에서는 실제 검증치(17/25)로 업데이트.
- `mentions` 같은 빈도 수치는 집계 범위에 따라 소폭 다를 수 있음 → **절대값보다 상대 순위로 해석** 권장.

감사 로직은 `41r/experiments/public_analysis/jupiter_audit.py`에 스크립트화 (별도 PR 예정).

---

## 7. 한계 (Known Limitations)

**Text 모드**:
- LLM의 jup.ag UI 지식은 학습 시점 기준. UI 변경 시 재분석 필요.
- "페르소나가 이렇게 행동할 것"은 추론이지 관찰이 아님.

**Browser 모드**:
- Phantom 확장 없음 → 실제 swap 실행 불가.
- Jupiter의 canvas/SVG 기반 UI로 F009 빈발 → "페르소나 미달"과 "도구 미달" 섞임.
- MAX_TURNS=10 제한.

**공통**:
- 페르소나 5명 표본 작음 (통계 유의 기준 20+). 대규모 검증 시 cohort 확장 필요.
- "마우스 커서 방황"은 직접 측정 불가 — 탐색 단어 + F009 빈도로 proxy.
- 실제 사용자 A/B 테스트 대체는 아님. **세그먼트 분기 진단** 단계에 특화.

---

## 8. 다음 단계 (사업팀 선택)

| 옵션 | 비용 | 시간 | 가치 |
|---|---:|---|---|
| 리포트 그대로 Jupiter팀 공유 | 0 | - | 현재 상태로 actionable |
| Cohort 20명으로 확장 (text) | ~$1.60 | 10분 | 통계 신뢰도 ↑ |
| 경쟁 dApp 비교 (Raydium, Orca) | ~$1/사이트 | 5분/사이트 | Jupiter 차별 진단 |
| 동일 cohort × [Jupiter + Raydium + Orca] (text) → reflection 자동 합성 | ~$3.50 | 20분 | **페르소나가 dex 공통 마찰 패턴 학습** — 진화 실증 |

---

## 9. Appendix

### A. Raw data

- Text 모드 verdict JSON: `/tmp/jupiter_verdict.json` (25 runs)
- Browser 모드 verdict JSON: `/tmp/jupiter_browser_verdict.json` (25 runs)
- Browser session logs: `41r/sessions/s_*.json` (5 sessions — runtime artifact, gitignored)

### B. 재현

```bash
cd 41r
export ANTHROPIC_API_KEY=...
.venv/bin/python3 -c "
from persona_agent.lowlevel import plan_and_run_hypothesis
v = plan_and_run_hypothesis(
    hypothesis='[원 가설]',
    url='https://jup.ag',
    target_cohort=['p_crypto_native','p_creator_freelancer','p_pragmatic','p_b2b_buyer','p_senior'],
    mode='text',  # or 'browser'
    task='0.1 SOL을 USDC로 스왑하고 슬리피지 0.1%로 변경'  # browser 모드만 활용
)
"
```

### C. 비용·시간

| 단계 | 비용 | 시간 |
|---|---:|---:|
| Text mode: planner + 25 rewriter + 25 predictor + verdict | $0.40 | ~2분 30초 |
| Browser mode: 5 sessions + 25 evaluators + verdict | $1.70 | ~45분 |
| **전체** | **$2.10** | **~48분** |

### D. 참고 문헌

- persona_agent 아키텍처: `persona_agent/ARCHITECTURE.md`
- Hypothesis Planner: `persona_agent/_internal/hypothesis/orchestrator.py`
- 진화 해네스: `persona_agent/EVOLUTION_HARNESS.md`
- 이전 검증: `41r/experiments/ablation/` (n=200 Upworthy, p<0.001)

---

*문의·재실행: persona_agent 0.2.0 / Hypothesis Planner / 41rpm 사업팀*
