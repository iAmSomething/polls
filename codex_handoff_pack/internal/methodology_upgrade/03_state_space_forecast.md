# 03. State-space Latent Trend Forecast

## Why
- 현재 예측은 감쇠 추세 기반이라 급변 시 과소/과대 반응 가능성이 있다.
- 잠재상태(로컬레벨/랜덤워크) 예측으로 전환하면 추세 잡음 분리가 좋아진다.

## Scope
- 대상: `src/forecast.py`
- 입력: 주간 합성 시계열

## Design
1. 모델
- Local Level:
- `y_t = mu_t + e_t`, `e_t ~ N(0, R)`
- `mu_t = mu_(t-1) + u_t`, `u_t ~ N(0, Q)`

2. 추정
- 칼만 필터/스무더로 `mu_t` 추정.
- `Q/R`는 파티별 최근 윈도우에서 MLE 또는 grid search.

3. 예측
- 1주 ahead 평균/표준편차 출력.

## Data Contract
- Output 확장: `forecast_next_week.xlsx`
- 컬럼 추가: `pred_sd`, `pred_lo_80`, `pred_hi_80`.

## Acceptance Criteria
- 8~16주 롤링 백테스트 MAE/RMSE 개선.
- 이벤트 구간에서 오차 스파이크 완화.

## Test Plan
- 시뮬레이션 데이터에서 필터 수렴 확인.
- 기존 포맷 하위호환 테스트.

## Risks
- 파라미터 과적합.
- 완화: party별 파라미터 범위 제한 + walk-forward 검증.

## Rollout
1. 기존 예측과 병렬 저장(`model=legacy|ssm`) 3주
2. 우수 시 default 전환
