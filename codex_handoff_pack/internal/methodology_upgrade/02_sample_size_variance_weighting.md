# 02. Sample-size-aware Observation Variance Weighting

## Why
- 동일 기관이라도 조사마다 표본수가 다르며, 관측 신뢰도가 다르다.
- 표본수 정보를 가중치에 반영하면 잡음을 더 안정적으로 줄일 수 있다.

## Scope
- 대상: 합성 가중치 계산(`src/pipeline.py`)
- 단위: 조사 레코드 단위 가중치

## Design
1. 기본 기관가중치
- `w_pollster = normalized(1/MAE)` 유지.

2. 조사별 관측가중치
- 근사 분산: `var_obs = p*(1-p)/n`.
- 조사별 신뢰가중: `w_obs = 1/max(var_obs, eps)`.
- 정당별 p는 해당 조사의 정당 지지율.

3. 최종 가중치
- `w_final = w_pollster * w_obs`.
- 날짜/정당 그룹 내 정규화.

## Data Contract
- Input required: `표본수` 파싱 정확도 개선 필요.
- Output add-on: `outputs/weights_diagnostic.csv`
- 컬럼: `date_end,party,pollster,w_pollster,w_obs,w_final,sample_n`.

## Implementation Notes
- 표본수 결측 시 fallback: 기관가중치만 사용.
- 극단적 p(0/1) 보호용 epsilon 적용.

## Acceptance Criteria
- 백테스트 RMSE 개선(전체 및 상위 2정당).
- 표본수 큰 조사 반영 비중이 직관적으로 증가.

## Test Plan
- 단위 테스트: 가중치 정규화 합=1.
- 엣지 테스트: n 결측/0, p 결측/0/1.

## Risks
- n값 파싱 오류가 모델 왜곡으로 직결.
- 완화: 원본 문자열 로그 및 이상치 경고 출력.

## Rollout
1. 진단 리포트만 생성 1주
2. 합성 계산 반영 + 성능 비교 2주
