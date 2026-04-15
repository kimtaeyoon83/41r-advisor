## 실패 모드 카탈로그

| 코드 | 이름 | 대응 |
|---|---|---|
| F001 | Flaky Selector | 재시도 1회 → 실패 시 다른 경로 |
| F002 | Race Condition | 액션 전 wait(network_idle, 2s) 강제 |
| F003 | Modal Overlay | overlay 체크 → 먼저 처리 또는 차단 판정 |
| F004 | Infinite Scroll | 스크롤 상한 5회, 초과 시 포기 |
| F005 | Auth Wall | test credentials 또는 게스트 플로우 |
| F006 | Rate Limit | 세션 간 random sleep (2~10초) |
| F007 | Unexpected Redirect | obs 기록, plan 재평가 |
| F008 | Frame/Iframe | frame switching, 실패 시 스크린샷 fallback |
| F009 | Dynamic Content | wait(element_visible, 5s) |
| F010 | CAPTCHA | 즉시 세션 종료 |

환경 실패와 페르소나 판단 이탈을 구분하여 기록할 것.
