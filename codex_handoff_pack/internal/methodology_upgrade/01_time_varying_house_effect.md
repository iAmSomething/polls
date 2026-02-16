# 01. Time-varying House Effect

## Why
- 현재 파이프라인은 `1/MAE` 고정 가중치 중심이라 정치 급변 국면에서 기관별 편향 변동을 즉시 반영하기 어렵다.
- 참고 문헌(여론M 매뉴얼)의 핵심 개선점도 시간가변 house effect다.

## Scope
- 대상: 정당지지도 합성(`src/pipeline.py`)
- 단위: `party x pollster x week`

## Design
1. 기준선 생성
- 기존 가중합으로 `blend_baseline[party, date]` 생성.

2. 기관 편향 잔차 계산
- `residual = pollster_value - blend_baseline`.

3. 시간가변 편향 추정
- 기관×정당별 residual에 EWMA 적용:
- `house_bias_t = lambda * house_bias_(t-1) + (1-lambda) * residual_t`
- 초기값 0, 기본 `lambda=0.8`.

4. 보정값 적용
- 관측치 보정: `adjusted_value = raw_value - house_bias_t`.
- 이후 기존 가중합 계산 수행.

## Data Contract
- Input: 기존 입력 + `date_end`, `조사기관`, 정당열.
- Output add-on:
- `outputs/house_effect_timeseries.csv`
- 컬럼: `date_end,pollster,party,house_bias,residual,n_obs`.

## Config
- `config/model_params.json` 추가:
- `house_effect_enabled`, `house_effect_lambda`, `house_effect_clip`.

## Acceptance Criteria
- 최근 12주 롤링 MAE 기준선 대비 3% 이상 개선 또는 동등 + 변동성 감소.
- 특정 기관 단기 쏠림 발생 시 합성치 과잉반응 완화 확인.

## Test Plan
- 단위 테스트: EWMA 업데이트 수식 검증.
- 회귀 테스트: 기존 산출물과 스키마 호환 확인.
- 백테스트: 이벤트 전후 2개 구간 분리 비교.

## Risks
- 과보정 시 실제 변화를 편향으로 오인할 수 있음.
- 완화: bias 절댓값 클립 + 최소 관측수 조건(`n_obs >= 3`).

## Rollout
1. shadow 모드(산출만, 반영 안 함) 2주
2. 반영 on + weekly 리포트 비교 4주
3. 성능 충족 시 기본값 on
