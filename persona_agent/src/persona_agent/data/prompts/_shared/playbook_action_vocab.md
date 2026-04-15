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
