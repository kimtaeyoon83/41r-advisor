# persona_agent API Guide

persona_agent 라이브러리를 HTTP API로 래핑한 FastAPI 서버.
AI 페르소나 기반 세그먼트 분기 진단을 외부 서비스에서 호출할 수 있다.

---

## 1. 빠른 시작

### 로컬 실행

```bash
cd persona_agent

# 의존성 설치
pip install -e ".[server,analysis]"

# 서버 시작
ANTHROPIC_API_KEY=sk-... uvicorn persona_agent.server.app:app --port 8000
```

### Docker 실행

```bash
cd persona_agent

# .env 파일에 ANTHROPIC_API_KEY=sk-... 설정 후
ANTHROPIC_API_KEY=sk-... docker compose up
```

서버가 뜨면 Swagger UI에서 전체 API를 확인할 수 있다: `http://localhost:8000/docs`

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | (필수) | Anthropic API 키 |
| `PA_WORKSPACE_DIR` | `/data/persona_workspace` | 페르소나/세션/리포트 저장 경로 |
| `PERSONA_AGENT_MAX_TURNS` | `10` | 세션 최대 턴 수 |
| `PERSONA_AGENT_ACTION_TIMEOUT` | `60` | 액션별 타임아웃 (초) |

---

## 2. 핵심 개념

### 비동기 Job 패턴

모든 분석 요청은 **즉시 반환 + 백그라운드 실행** 구조다.

```
POST /sessions → 202 {"job_id": "job_abc123", "status": "queued"}
                      ↓ (백그라운드 실행)
GET /jobs/job_abc123 → {"status": "running", ...}
                      ↓ (완료)
GET /jobs/job_abc123 → {"status": "completed", "result": {...}}
```

세션 1건은 text mode 기준 ~2분, browser mode ~15분 소요.

### 모드

| 모드 | 용도 | 비용 | 시간 |
|------|------|------|------|
| `text` | 페르소나 인지 경험 예측 (primary) | ~$0.40 | ~2분 |
| `browser` | 실제 브라우저 접근성 감사 (secondary) | ~$1.70 | ~45분 |

**text를 기본으로 사용하고, browser는 접근성 보조 감사용으로만.**

---

## 3. API 레퍼런스

### 시스템

#### `GET /health`

서버 상태 확인.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "version": "0.2.0",
  "active_jobs": 2
}
```

---

### 페르소나 관리

#### `GET /personas` — 목록 조회

```bash
curl http://localhost:8000/personas
```

```json
[
  {"persona_id": "p_cautious", "soul_version": "v002"},
  {"persona_id": "p_impulsive", "soul_version": "v001"},
  {"persona_id": "p_genz_mobile", "soul_version": "v001"}
]
```

#### `POST /personas` — 커스텀 페르소나 생성

```bash
curl -X POST http://localhost:8000/personas \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "p_enterprise_buyer",
    "soul_text": "---\nname: Enterprise Buyer\ntraits:\n  risk_tolerance: 0.2\n  decision_speed: 0.3\n  price_sensitivity: 0.4\n  tech_literacy: 0.8\n  brand_loyalty: 0.7\ngeneration: millennial\nfrustration_triggers:\n  - unclear pricing\n  - no enterprise plan visible\ntrust_signals:\n  - SOC2 badge\n  - customer logos\npredicates:\n  - id: reads_pricing\n    type: rule\n    rule: \"action_count('read') >= 2\"\n---\nEnterprise SaaS 구매 담당자. 보안과 규모에 민감하며, 명확한 가격 정책과 엔터프라이즈 기능이 보이지 않으면 빠르게 이탈한다."
  }'
```

```json
{
  "persona_id": "p_enterprise_buyer",
  "soul_version": "v001",
  "soul_text": "---\nname: Enterprise Buyer\n...",
  "observations": [],
  "reflections": []
}
```

**Soul 구조** (YAML frontmatter):
- `traits`: 5개 성향 프로필 (0.0~1.0)
- `generation`: 세대 특성
- `frustration_triggers`: 좌절 트리거 목록
- `trust_signals`: 신뢰 기준 목록
- `predicates`: 세션 충실도 검증 규칙 (선택)

#### `GET /personas/{persona_id}` — 상세 조회

```bash
curl http://localhost:8000/personas/p_cautious
```

```json
{
  "persona_id": "p_cautious",
  "soul_version": "v002",
  "soul_text": "---\nname: 신중한 비교자\n...",
  "observations": [
    {"content": "pricing 페이지에서 3분 이상 체류", "timestamp": "..."}
  ],
  "reflections": [
    {"content": "가격 비교에 시간을 많이 쓰는 경향 확인", "timestamp": "..."}
  ]
}
```

#### `PUT /personas/{persona_id}` — Soul 업데이트

새 버전이 자동 생성된다 (v001 → v002). 이전 버전은 보존.

```bash
curl -X PUT http://localhost:8000/personas/p_enterprise_buyer \
  -H "Content-Type: application/json" \
  -d '{
    "soul_text": "---\nname: Enterprise Buyer v2\ntraits:\n  risk_tolerance: 0.15\n..."
  }'
```

#### `DELETE /personas/{persona_id}` — 삭제

```bash
curl -X DELETE http://localhost:8000/personas/p_enterprise_buyer
# 204 No Content
```

---

### 세션 실행

#### `POST /sessions` — 단일 페르소나 세션

하나의 페르소나가 하나의 URL에서 태스크를 수행한다.

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "p_cautious",
    "url": "https://your-product.com/pricing",
    "task": "적절한 요금제를 찾아 가입 시도"
  }'
```

```json
{"job_id": "job_a1b2c3d4e5f6", "status": "queued", "message": "Job queued"}
```

**완료 후 결과** (`GET /jobs/{job_id}`):

```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "kind": "session",
  "status": "completed",
  "result": {
    "session_id": "s_f8e2a1b3",
    "persona_id": "p_cautious",
    "url": "https://your-product.com/pricing",
    "task": "적절한 요금제를 찾아 가입 시도",
    "outcome": "task_complete",
    "total_turns": 7,
    "plan": {
      "steps": ["pricing 페이지 확인", "플랜 비교", "가입 버튼 클릭"]
    },
    "turns": [
      {
        "turn": 1,
        "observation": "3개 플랜이 보임: Free, Pro, Enterprise",
        "decision": "각 플랜의 기능 차이를 읽겠다",
        "tool": {"tool": "read", "params": {"region": "pricing-table"}}
      }
    ]
  }
}
```

---

### 코호트 분석

#### `POST /cohorts` — 기존 코호트로 분석

사전에 생성된 코호트(페르소나 그룹)로 분석을 실행한다.

```bash
curl -X POST http://localhost:8000/cohorts \
  -H "Content-Type: application/json" \
  -d '{
    "cohort_id": "cohort_20260417_demo",
    "url": "https://your-product.com",
    "task": "회원가입 플로우 완료",
    "mode": "text",
    "max_workers": 5
  }'
```

#### `POST /cohorts/generate` — 페르소나 자동 생성 + 분석

세그먼트만 지정하면 페르소나를 자동 생성하고 바로 분석까지 실행한다.

```bash
curl -X POST http://localhost:8000/cohorts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "segment_name": "20대 여성 직장인",
    "size": 15,
    "url": "https://your-product.com",
    "task": "첫 구매까지의 여정 평가",
    "mode": "text",
    "age_range": [22, 29]
  }'
```

내부 동작:
1. Latin Hypercube sampling으로 15명 페르소나 자동 생성
2. 각 페르소나별 세션 병렬 실행
3. 코호트 결과 집계

**완료 후 결과**에는 페르소나별 verdict 배열이 포함된다.

---

### 리포트 생성

#### `POST /reports` — 완료된 코호트에서 HTML 리포트 생성

```bash
# 코호트 job이 completed 상태여야 함
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job_a1b2c3d4e5f6"}'
```

---

### Job 관리

#### `GET /jobs/{job_id}` — 상태 조회

```bash
curl http://localhost:8000/jobs/job_a1b2c3d4e5f6
```

상태값: `queued` → `running` → `completed` / `failed`

#### `GET /jobs` — 전체 목록

```bash
# 전체
curl http://localhost:8000/jobs

# 실행 중인 것만
curl "http://localhost:8000/jobs?status=running"

# 최근 10개
curl "http://localhost:8000/jobs?limit=10"
```

---

## 4. 실전 워크플로우 예시

### 시나리오: "우리 가격 페이지에서 어떤 유저 타입이 이탈하는지 진단"

```bash
# 1. 세그먼트 자동 생성 + 분석 실행
curl -X POST http://localhost:8000/cohorts/generate \
  -d '{
    "segment_name": "SaaS 구매 검토자",
    "size": 15,
    "url": "https://your-product.com/pricing",
    "task": "적절한 플랜을 선택하고 가입 시도",
    "mode": "text"
  }'
# → {"job_id": "job_001"}

# 2. 완료 대기 (폴링)
curl http://localhost:8000/jobs/job_001
# → status: "running" ... → "completed"

# 3. 리포트 생성
curl -X POST http://localhost:8000/reports \
  -d '{"job_id": "job_001"}'
# → {"job_id": "job_002"}

# 4. 리포트 결과 확인
curl http://localhost:8000/jobs/job_002
# → result에 HTML 리포트 포함
```

### 시나리오: "커스텀 페르소나로 특정 플로우 테스트"

```bash
# 1. 커스텀 페르소나 생성
curl -X POST http://localhost:8000/personas \
  -d '{
    "persona_id": "p_cto_startup",
    "soul_text": "---\nname: 스타트업 CTO\ntraits:\n  risk_tolerance: 0.8\n  decision_speed: 0.9\n  price_sensitivity: 0.6\n  tech_literacy: 0.95\n  brand_loyalty: 0.2\ngeneration: millennial\nfrustration_triggers:\n  - 기술 문서 부족\n  - API 없음\ntrust_signals:\n  - GitHub 오픈소스\n  - 기술 블로그\n---\n빠른 판단을 선호하는 스타트업 CTO. API와 기술 문서가 없으면 즉시 이탈."
  }'

# 2. 세션 실행
curl -X POST http://localhost:8000/sessions \
  -d '{
    "persona_id": "p_cto_startup",
    "url": "https://your-product.com",
    "task": "API 문서를 찾고 통합 가능성 평가"
  }'
# → {"job_id": "job_003"}

# 3. 결과 확인
curl http://localhost:8000/jobs/job_003
```

---

## 5. 에러 처리

| HTTP 코드 | 의미 |
|-----------|------|
| `201` | 리소스 생성 성공 (페르소나) |
| `202` | Job 접수됨 (비동기 실행 시작) |
| `204` | 삭제 성공 |
| `404` | 페르소나/Job을 찾을 수 없음 |
| `409` | 충돌 (페르소나 ID 중복, Job 미완료 상태에서 리포트 요청) |

Job 실패 시 `GET /jobs/{id}`의 `error` 필드에 원인이 담긴다:

```json
{
  "status": "failed",
  "error": "Persona p_nonexistent not found"
}
```

---

## 6. 비용 가이드

| 작업 | 예상 비용 | 소요 시간 |
|------|----------|----------|
| 단일 세션 (text) | ~$0.30~0.50 | ~2분 |
| 단일 세션 (browser) | ~$1.70 | ~15~45분 |
| 코호트 15명 (text) | ~$5~8 | ~10분 |
| 코호트 15명 (browser) | ~$25 | ~2시간+ |

text mode를 기본으로 사용하는 것을 권장한다.

---

## 7. 제약 및 주의사항

- **MVP 한계**: Job store가 in-memory — 서버 재시작 시 진행 중인 job 유실
- **동시성**: `max_workers`로 병렬 세션 수 제어 (browser mode는 3 이하 권장)
- **인증**: 현재 인증/인가 없음 — 프로덕션에서는 API 키 또는 OAuth 추가 필요
- **결과 영속성**: 세션 로그/리포트는 `PA_WORKSPACE_DIR` 파일시스템에 저장됨
- **LLM 모델**: Sonnet 사용 (Opus 금지, 비용 최적화)
