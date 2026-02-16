# 04. Regime Shift Guardrail

## Why
- 대형 정치 이벤트 직후 과거 가중치/추세가 빠르게 무효화될 수 있다.
- 국면 전환 감지 후 감쇠를 강화하는 안전장치가 필요하다.

## Scope
- 대상: `src/pipeline.py`, `src/forecast.py`, `src/issues.py`

## Design
1. 감지 지표
- 합성 잔차 z-score 급등
- 기관 간 분산 급등
- 이슈 강도 합계 급등

2. 트리거
- 두 지표 이상 임계치 초과 시 `regime_shift=true`.

3. 대응
- house effect lambda 하향(빠른 적응)
- 예측 모델에서 process noise(Q) 상향
- 최근 4주 가중치 상향

## Data Contract
- `outputs/regime_status.json`
- 필드: `date,triggered,reasons,params_override`.

## Acceptance Criteria
- 전환기 오차 tail 감소(95p 절대오차).
- 평시 구간 성능 악화 최소화.

## Test Plan
- 과거 대형 이벤트 주차 리플레이 테스트.
- false positive 비율 점검.

## Risks
- 과민 트리거.
- 완화: 히스테리시스(연속 2주 조건) 적용.

## Rollout
1. 상태만 기록 2주
2. soft override 적용 2주
3. 임계치 재조정 후 상시 적용
