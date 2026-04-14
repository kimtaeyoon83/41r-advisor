## 관찰 규칙

- **3-레이어**: L1 Meta (매 턴) + L2 A11y Tree (매 턴) + L3 Screenshot (필요 시만)
- 기본 조합은 L1 + L2. L3는 레이아웃 판단, A11y tree 부실, replan 진단 시만
- A11y tree 우선: DOM 대비 10배 작고, 의미적 구조, 유저 인지와 가장 가까움
- **viewport 한정**: 현재 viewport 내 요소만. 스크롤 아래는 "아래 더 있음" 신호만
- **Before/After Diff**: 매 액션 후 A11y tree diff 기록 (added/removed/changed)
