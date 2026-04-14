## 타이밍 모델

페르소나는 시간 축에서 다르다. 4가지 시간 변수:

- **Patience budget**: 페이지 로딩 대기 상한. strict=2초, normal=5초, patient=15초
- **Reading speed**: read(region) 반환 텍스트 × wpm → 읽는 시간. 이 시간 전에 다음 액션 불가
- **Decision latency**: 선택지 수 × latency = 고민 시간 (빠른: 0.5초, 신중: 3초)
- **Loading tolerance**: 네트워크 대기 허용치. strict=0.5초, normal=2초, patient=5초

페르소나 soul의 timing 필드에서 로드.
