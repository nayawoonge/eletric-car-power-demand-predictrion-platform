# ProbabilityCostAnalysis UI 숫자 산정 근거 (개조식)

## 목적

- 대상: `ProbabilityCostAnalysis.svelte`
- 설명 범위
- 시나리오별 기본요금
- 과소/과다 계약 관련 비용
- 총 예상비용

## 1) 시나리오 생성 규칙 (`updateSimulations()`)

- 기본 구성
- 과소 계약: `최적 계약전력 - 10kW`
- 최적 계약: `recommendation.recommended_contract_kw`
- 과다 계약: `최적 계약전력 + 10kW`
- 조건부 추가
- 현재 계약: `currentContractKw`가 있고 최적값과 다를 때
- 사용자 지정: `customContractKw`가 유효하고 최적값과 다를 때
- 결론
- 기본 3개(과소/최적/과다) + 필요 시 현재/사용자 시나리오 확장

## 2) 비용 계산 공식 (`createSimulation()`)

- 기본요금
- `basicCost = contractKw * 8320`
- 예상 초과요금
- `expectedOverageCost = basicCost * 1.5 * (overageProbability / 100)`
- 예상 낭비비용
- `expectedWasteCost = basicCost * (wasteProbability / 100)`
- 총 예상비용
- `totalExpectedCost = basicCost + expectedOverageCost + expectedWasteCost`
- 사용 상수
- `BASIC_RATE_PER_KW = 8320`
- `OVERAGE_PENALTY_MULTIPLIER = 1.5`
- `CONTRACT_STEP = 10`

## 3) 과소/과다 비용이 다르게 보이는 이유

- 화면 표시
- 예상 초과요금: `+ ...원` (빨간색)
- 예상 낭비비용: `- ...원` (노란색)
- 표시 의도 (UX)
- 초과요금: 추가 부담(페널티) 강조
- 낭비비용: 비효율 지출 강조
- 계산상 주의점
- `totalExpectedCost`에서는 두 항목 모두 "더해짐"
- 즉, `expectedWasteCost`도 총비용 증가 항목

## 4) 확률 값 출처

- 데이터 소스: `recommendation.candidate_analysis_data`
- 매칭 키: `contract_kw`
- 적용 규칙
- 후보 존재: `overage_probability`, `waste_probability` 사용
- 후보 없음: 각 확률 `0` 처리
- 해석 포인트
- 특정 시나리오가 0%면 해당 계약전력 후보 데이터 부재/누락 가능성 확인

## 5) 고급 표(상세 확률 분포) 기준

- 데이터: `sortedCandidates`
- 정렬: `contract_kw` 오름차순
- 분류
- `contract_kw < optimal` -> `⚠️ 과소`
- `contract_kw > optimal` -> `📊 과다`
- `contract_kw === optimal` -> `✅ 최적` (강조)
- 표의 `예상비용`
- 후보 데이터의 `annual_cost`를 그대로 사용

## 6) 월간/연간 토글 영향 (`formatCurrency()`)

- `annual`
- 계산값 그대로 표시
- `monthly`
- 표시 시 `12`로 나눠 표시
- 핵심
- 내부 계산 로직은 동일
- 화면의 표시 단위만 변경

## 7) 점검 체크리스트

- 숫자가 예상과 다를 때 우선 확인
- 해당 계약전력의 후보 데이터 존재 여부
- `overage_probability`, `waste_probability` 값 범위
- `annual_cost`(백엔드 제공값)와 프런트 계산값 기준 차이

## 한 줄 요약

- 시나리오 생성(최적 기준 ±10kW) + 확률 기반 비용 계산(기본 + 초과 + 낭비) + 후보 데이터 분류/표시 규칙으로 현재 UI 숫자가 결정됨
