# 05. Menu Effect Model (Candidate Polls)

## Why
- 후보 조합이 다르면 지지율 비교가 왜곡된다.
- 대선 국면 확장 시 메뉴 효과는 필수 보정 요소다.

## Scope
- 대상: 후보 지지도 모듈(신규)
- 정당지지도 메인 파이프라인과 분리 운영

## Design
1. 데이터 스키마
- 각 조사에 후보 포함 더미 벡터 `D_t` 생성.

2. 모형
- `y_ijt = alpha_jt + house_ijt + D_t * beta_j + error`

3. 산출
- 메뉴 보정 전/후 지지율 동시 공개.

## Data Contract
- 신규 파일: `data/candidate_poll_input.csv`
- 필수 컬럼: `date,pollster,sample_n,candidate_set,...`

## Acceptance Criteria
- 동일 시점 이질 후보조합 조사간 편차 감소.
- 후보조합 변경 주차의 불연속 완화.

## Test Plan
- 후보 포함/미포함 synthetic 실험.
- 실제 과거 후보조합 사례 백테스트.

## Risks
- 후보 메타데이터 정합성 문제.
- 완화: 입력 검증기 + 누락 후보 자동 플래그.

## Rollout
1. 연구 브랜치에서 별도 대시보드
2. 검증 후 메인 사이트 서브탭으로 편입
