# 06. Uncertainty & Probability Layer

## Why
- 현재는 점추정 위주라 불확실성 전달이 약하다.
- 예측구간/순위확률 공개로 해석 리스크를 줄일 수 있다.

## Scope
- 대상: `src/forecast.py`, `src/generate_site.py`

## Design
1. 예측 분포
- 파티별 `mean, sd` 기반 정규 근사 또는 샘플링.

2. 지표
- 80/95% 구간
- 1위 확률
- 정당 간 격차가 0 이상일 확률

3. UI
- 랭킹 카드에 구간 폭 배지
- 방법론 영역에 확률 해석 주의문 추가

## Data Contract
- `outputs/forecast_distribution.csv`
- 컬럼: `party,pred_mean,pred_sd,p10,p50,p90,p_win`.

## Acceptance Criteria
- 주간 리포트에 구간/확률 자동 포함.
- 과거 적중률 대비 과신(calibration) 완화.

## Test Plan
- calibration curve(예측확률 vs 실제빈도).
- extreme week 구간 폭 확대 여부 확인.

## Risks
- 사용자가 확률을 과도하게 단정적으로 해석할 수 있음.
- 완화: UI에 신뢰구간 정의와 한계 문구 명시.

## Rollout
1. 내부 리포트 공개
2. 대시보드 확장 공개
