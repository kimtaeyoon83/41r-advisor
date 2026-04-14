# 41R Browser Testing Playbook

> **작성일**: 2026-04-12
> **버전**: v1.0
> **대응**: Constitution v1.0, Slice-H1
> **성격**: 에이전트가 브라우저에서 어떻게 관찰·판단·행동하는지에 대한 전문 지식. 프롬프트가 references로 주입하는 공용 지식 베이스.

---

## 0. 문서의 역할

이 Playbook은 **실행되는 코드가 아니다**. 프롬프트가 참조하는 지식이며, 에이전트가 "좋은 브라우저 테스트"와 "나쁜 브라우저 테스트"를 구분하는 기준이다.

- 프롬프트 frontmatter의 `references: [playbook/observation, playbook/timing, ...]` 필드로 연결
- 프롬프트 로더가 해당 섹션을 자동 주입
- 섹션 단위로 독립적 (일부만 주입 가능)
- Hot Zone (`prompts/_shared/`에 실제 스니펫 파일 존재)

---

## 1. 관찰 전략 (Observation)

### 원칙
유저가 실제로 인지하는 정보만 에이전트에게 준다. DOM 전체를 주면 토큰 낭비이자 페르소나 시뮬레이션의 오염.

### 3-레이어 스냅샷

| 레이어 | 내용 | 비용 | 사용 시점 |
|---|---|---|---|
| **L1 Meta** | URL, 페이지 타이틀, 로딩 상태 | 거의 0 | 매 턴 |
| **L2 A11y Tree** | Accessibility tree (visible + interactive) | 저 | 매 턴 |
| **L3 Screenshot** | 페이지 스크린샷 (vision 모델용) | 고 | 필요 시만 |

**기본 조합**: L1 + L2. L3는 다음 경우에만:
- 레이아웃/시각적 판단이 필요한 태스크 (예: "이 디자인이 매력적인가")
- A11y tree가 비어있거나 부실할 때 (SPA 초기 렌더링)
- 명시적 replan 필요 시 (왜 이탈했는가 진단)

### A11y Tree 우선 이유
- DOM 대비 10배 작음 (텍스트+역할만, 스타일/스크립트 제외)
- 의미적 구조 (`button`, `link`, `textbox` 등 역할 명시)
- 유저 인지와 가장 가까움 (스크린리더가 보는 것 = 인지 가능한 것)
- 셀렉터 안정성 (id가 아닌 role+name 기반)

### Viewport 한정
- 초기 관찰은 **현재 viewport 내 요소만**
- 스크롤 아래는 "아래 더 있음" 신호만
- 유저도 모든 걸 즉시 보지 않음. 페르소나의 스크롤 행동이 의미 가지려면 처음엔 viewport만 봐야 함

### 변화 감지 (Before/After Diff)
매 액션 후 A11y tree diff를 obs에 기록:
```
added:    ["alert: '쿠폰이 적용되었습니다'"]
removed:  ["button: '적용하기'"]
changed:  ["textbox 'email': value='user@..'"]
```
이게 **유저가 체감하는 피드백**. 페르소나 만족/불만 판정의 근거.

---

## 2. 액션 어휘 (Action Vocabulary)

### 원칙
에이전트는 **제한된 어휘**만 사용. Stagehand 원본 API는 외부 노출 금지 (M2 Browser Runner 래퍼 레이어).

### 9개 원시 액션

| 액션 | 시그니처 | 용도 | 주의 |
|---|---|---|---|
| `click` | `click(target: str)` | 버튼/링크 탭 | target은 텍스트+역할 기반 ("결제 버튼") |
| `fill` | `fill(target: str, text: str)` | 입력 필드 | 페르소나 특성 주입 지점 |
| `select` | `select(target: str, option: str)` | 드롭다운/옵션 | |
| `scroll` | `scroll(direction: up\|down, amount: screen\|px)` | 스크롤 | 시뮬레이션 핵심 |
| `wait` | `wait(condition: str, timeout: float)` | 로딩 대기 | patience가 여기 반영 |
| `read` | `read(region: str) -> str` | 텍스트 읽기 | **명시적 읽기 행동** |
| `navigate` | `navigate(url: str)` | URL 직접 이동 | 드물게. 보통 클릭 |
| `back` | `back()` | 뒤로가기 | 이탈 신호 |
| `close_tab` | `close_tab()` | 세션 종료 | 최종 이탈 |

### `read()` 의 특별한 위치
유저의 의사결정은 "무엇을 읽었는가"에 의해 결정되는데, 에이전트는 이걸 명시하지 않으면 페이지 전체를 읽은 것처럼 행동한다. **읽기는 명시적 행동**으로 다룬다.

```
read("main product description")   → 설명 읽음, 이후 판단에 반영
read("reviews top 3")               → 리뷰 3개 스캔
# 명시하지 않은 영역은 "보지 않음"
```

페르소나 차별성의 핵심:
- 꼼꼼한 페르소나: read() 많이 호출, 읽은 내용이 길다
- 충동적 페르소나: read() 거의 없음, 제목만 보고 click
- 신중한 페르소나: read(reviews) 필수, 부정 리뷰 발견 시 이탈

### 셀렉터 규칙
- **허용**: 텍스트+역할 기반 ("결제하기 버튼", "이메일 입력창")
- **금지**: XPath, CSS 선택자, id 직접 지정
- Stagehand의 자연어 타겟팅 활용

이유: A/B 테스트 대상 사이트들은 id가 매 배포마다 바뀐다. 의미 기반 셀렉터만 세션 간 재현성 있음.

---

## 3. 타이밍 모델 (Timing)

### 원칙
페르소나는 **시간 축에서 다르다**. 같은 페이지에서 다른 시간을 쓰고, 다른 로딩을 참는다.

### 페르소나 시간 필드 (필수)

```yaml
# personas/p_XXX/soul/v001.md frontmatter
timing:
  patience_seconds: 3.0        # 로딩 대기 상한
  reading_wpm: 250             # 분당 단어 수
  decision_latency_sec: 2.0    # 선택지당 고민 시간
  loading_tolerance: strict    # strict | normal | patient
```

### 네 가지 시간 변수

**Patience budget**
페이지 로딩 대기 상한. 초과 시 자동 이탈 판정.
- strict: 2초
- normal: 5초
- patient: 15초

**Reading speed**
`read(region)` 호출 시 반환 텍스트 길이 × wpm → 읽는 시간 계산.
이 시간이 지나야 다음 액션 유효. 페르소나가 짧은 설명을 "읽었다"는 주장은 불가.

**Decision latency**
여러 선택지가 있는 페이지에서 선택지 수 × latency = 고민 시간.
빠른 페르소나: 0.5초 × 선택지 수
신중한 페르소나: 3초 × 선택지 수

**Loading tolerance**
네트워크 대기(스피너/스켈레톤) 허용치. Patience와 별개로 "로딩 퀄리티" 기준:
- strict: 로딩 0.5초 넘으면 불만 증가
- normal: 2초까지 허용
- patient: 5초까지 수용

### events log 시간 기록
```json
{
  "turn": 7,
  "action": "wait",
  "wait_duration_sec": 3.2,
  "patience_remaining": -0.2,
  "outcome": "patience_exhausted"
}
```

### H2 정확도와의 연결
시간 모델이 없으면 페르소나 간 차이가 "어떤 버튼을 눌렀는가"로만 나타난다. 시간 모델이 있으면 **"같은 버튼을 누르기까지 걸린 시간"과 "안 누른 이유"**가 차별화된다. 실제 A/B 결과(평균 체류 시간, 이탈률)와 맞춰볼 숫자가 생긴다.

---

## 4. 실패 모드 카탈로그 (Failure Modes)

### 원칙
브라우저 테스트는 에이전트의 판단 오류가 아니라 **환경의 문제**로 실패하는 경우가 많다. 이걸 구분해서 로그해야 Review Agent가 페르소나 개선과 환경 대응을 분리할 수 있다.

### 카탈로그

| 코드 | 이름 | 증상 | 대응 |
|---|---|---|---|
| F001 | Flaky Selector | 같은 텍스트 요소가 매 세션 다른 위치 | 재시도 1회 → 실패 시 observation 기록, 다른 경로 시도 |
| F002 | Race Condition | 액션 전 페이지 로딩 미완 | 모든 액션 전 `wait(network_idle, 2s)` 강제 |
| F003 | Modal Overlay | 쿠키 배너/팝업이 가림 | 액션 전 overlay 체크, 있으면 먼저 처리 또는 차단 판정 |
| F004 | Infinite Scroll | 스크롤 끝 없음 | 스크롤 상한 5회, 초과 시 "콘텐츠 탐색 포기" |
| F005 | Auth Wall | 로그인 필요 화면 | test credentials 주입 또는 게스트 플로우 우선 |
| F006 | Rate Limit | 반복 접근으로 차단 | 세션 간 random sleep (2~10초) |
| F007 | Unexpected Redirect | 의도와 다른 URL 이동 | obs 기록, plan 재평가 |
| F008 | Frame/Iframe | 콘텐츠가 iframe 내부 | Stagehand frame switching, 실패 시 스크린샷 fallback |
| F009 | Dynamic Content | 요소가 천천히 나타남 | `wait(element_visible, 5s)` |
| F010 | CAPTCHA | 자동화 탐지 | 즉시 세션 종료, 태스크 불가 판정 |

### 실패 모드 기록 형식
```json
{
  "type": "failure",
  "code": "F003",
  "name": "ModalOverlay",
  "detected_at_turn": 3,
  "recovery": "dismissed_cookie_banner",
  "continued": true
}
```

### Modal 처리 규칙
쿠키 배너/뉴스레터 팝업 같은 것은 **페르소나마다 다르게 처리**:
- 신중한 페르소나: 쿠키 설정 읽고 수락
- 급한 페르소나: "X" 버튼으로 즉시 닫기 또는 그냥 무시 (가능하면)
- 프라이버시 민감: 거부 후 진행

이것도 페르소나 차별성의 표현. 일괄 무시하지 말 것.

---

## 5. 세션 품질 기준 (Quality Gate)

### 좋은 세션의 최소 조건

- [ ] 최소 3턴 이상
- [ ] 최소 1회 의미 있는 상호작용 (네비게이션 또는 폼 제출)
- [ ] 종료 이유 명시적 (`task_complete` | `abandoned:<code>` | `max_turns_hit`)
- [ ] 모든 액션에 observation 짝 존재 (누락 0)
- [ ] 시간 정보 완전 (모든 turn에 timestamp)
- [ ] 실패 모드는 카탈로그 코드로 분류됨 (미분류 failure = 0)
- [ ] 종료 시점의 페르소나 감정/평가 1줄 이상 (`outcome.persona_verdict`)

이 기준 미달 세션은 Review Agent가 자동 플래그 → H1 데모 리포트에서 제외.

### 이탈 이유 분류 (abandon codes)

| 코드 | 의미 |
|---|---|
| A001 | 로딩 지연 (patience 초과) |
| A002 | 가격/조건 불만족 |
| A003 | 정보 부족 (원하는 내용 못 찾음) |
| A004 | 혼란/복잡성 (플로우 이해 실패) |
| A005 | 신뢰 부족 (리뷰/평판 우려) |
| A006 | 대안 탐색 (비교 목적으로 이탈) |
| A007 | 기술 오류 (환경 실패) |
| A008 | 결제 직전 주저 |

각 이탈이 분류돼야 "이 A/B 시안은 A001 이탈이 20%" 같은 의미 있는 리포트가 나온다.

---

## 6. 프롬프트 연결 방식

### Frontmatter references

```markdown
---
name: decision_judge
version: v001
references:
  - playbook/observation
  - playbook/action_vocab
  - playbook/timing
  - playbook/failure_modes
---

# Decision Judge
당신은 페르소나 특성과 현재 페이지 상태를 읽고 다음 액션을 결정한다.
[references에 명시된 playbook 스니펫이 여기 자동 주입됨]

## 작업
...
```

### 공용 스니펫 파일

```
prompts/_shared/
  playbook_observation.md     § 1 내용을 프롬프트용으로 압축
  playbook_action_vocab.md    § 2 내용 (액션 어휘 표)
  playbook_timing.md          § 3 내용 (시간 모델 규칙)
  playbook_failure_modes.md   § 4 내용 (카탈로그)
  playbook_quality_gate.md    § 5 내용 (세션 품질)
```

각 스니펫은 본 Playbook의 해당 섹션을 **프롬프트 주입용으로 압축한 버전**. 본 문서는 인간 레퍼런스, 스니펫은 LLM 주입용.

### 프롬프트별 권장 references

| 프롬프트 | 권장 references |
|---|---|
| plan_generator | observation, timing |
| decision_judge | observation, action_vocab, timing, failure_modes |
| tool_selector | action_vocab |
| page_summarizer | observation |
| replan_trigger | timing, failure_modes |
| review/persona_consistency | timing, quality_gate |

---

## 7. Stagehand 래퍼 레이어 (M2 구현 지침)

### 원칙
Stagehand 원본 API는 M2 내부에만. 에이전트는 § 2의 9개 액션만 사용.

### 구현 윤곽

```python
# modules/browser_runner.py

class BrowserRunner:
    def __init__(self):
        self._stagehand = Stagehand(...)  # 내부 전용
    
    def click(self, target: str) -> ActionResult:
        self._wait_network_idle()
        self._check_overlay()
        result = self._stagehand.act(f"click {target}")
        diff = self._compute_a11y_diff()
        return ActionResult(ok=..., diff=diff, failure=None)
    
    def read(self, region: str) -> str:
        text = self._stagehand.extract(region)
        return text
    
    def observe(self) -> PageState:
        return PageState(
            url=...,
            title=...,
            a11y_tree=self._stagehand.observe(),  # L2
            viewport_only=True,
            scroll_hint="more below" if ... else None
        )
    
    # 원시 Stagehand 메서드는 외부 노출 금지 (underscore prefix)
```

### 관찰 기본값
`observe()`는 A11y tree만 반환. Screenshot은 명시적 `observe(include_screenshot=True)` 호출 시만.

---

## 8. Review Agent와의 연결

Review Agent는 Playbook 기준으로 세션을 평가한다.

### session_inspection 프롬프트가 체크할 것
- 액션 어휘 위반 여부 (9개 외 액션 사용)
- read() 호출 없는데 리뷰 내용 언급한 decision
- 시간 정보 누락 turn
- 분류 안 된 failure
- Quality Gate 미달 항목

### persona_consistency 프롬프트가 체크할 것
- 페르소나 timing 필드와 실제 wait 시간의 일치
- Reading speed 위반 (긴 텍스트를 너무 빨리 "읽음")
- Decision latency 패턴
- 이탈 코드가 페르소나 특성과 맞는가 (충동적 페르소나가 A001 이탈 = 부자연)

### revision_proposer의 재료
- "이 프롬프트 버전에서 F003 (Modal) 미처리가 N번" → decision_judge에 modal 체크 강화 제안
- "꼼꼼한 페르소나의 read() 호출이 부족" → plan_generator에 reading 단계 명시 제안

---

## 9. 의도적으로 하지 않을 것

- ❌ Playwright/Cypress 같은 일반 E2E 프레임워크 직접 사용
- ❌ DOM 전체 크롤링 후 LLM에 덤프
- ❌ 픽셀 좌표 기반 클릭 (좌표는 레이아웃 변화에 취약)
- ❌ 하드코딩된 sleep (모든 대기는 condition-based)
- ❌ 스크린샷을 기본 관찰 수단으로 사용 (비용)
- ❌ 여러 페르소나를 병렬 실행 시 동일 IP (F006 유발)
- ❌ CAPTCHA 우회 시도 (F010은 즉시 종료)

---

## 10. 확장 로드맵 (v4-full 이후)

현 Playbook은 H1에 필요한 최소 기준. 이후 단계:

- **Multi-tab**: 비교 쇼핑 페르소나를 위한 탭 간 이동
- **Mobile viewport**: 모바일 전용 A/B 시뮬레이션
- **Network throttling**: 느린 연결 유저 시뮬레이션
- **Locale/Geo**: 지역별 행동 차이 (쿠키 배너 대응 등)
- **Accessibility 페르소나**: 스크린리더 유저, 색맹 등
- **Emotion tracking**: 세션 중 감정 변화 추적 (현재는 종료 시점만)

---

## Appendix — 프롬프트 스니펫 초안

### prompts/_shared/playbook_action_vocab.md (주입용 압축본)

```markdown
## 사용 가능한 액션 (9개만)

- `click(target)` — 버튼/링크. target은 "결제 버튼"처럼 자연어.
- `fill(target, text)` — 입력 필드.
- `select(target, option)` — 드롭다운.
- `scroll(direction, amount)` — 스크롤.
- `wait(condition, timeout)` — 로딩 대기.
- `read(region)` — 텍스트 명시적 읽기. 읽지 않은 내용은 판단에 사용 금지.
- `navigate(url)` — URL 직접 이동. 드물게.
- `back()` — 뒤로. 이탈 신호.
- `close_tab()` — 세션 종료.

## 규칙
- 셀렉터는 텍스트+역할 기반만 (XPath/CSS/id 금지)
- read()로 명시하지 않은 텍스트는 페르소나가 보지 않은 것
- 모든 페이지 변화 후 wait 암묵적 호출됨
```

(나머지 스니펫은 Slice-H1 작업 시 본 문서에서 추출하여 작성)

---

*본 Playbook은 에이전트의 브라우저 행동 품질 기준을 제공한다. 프롬프트는 이 지식을 references로 참조하여 페르소나 시뮬레이션의 전문성을 확보한다.*
