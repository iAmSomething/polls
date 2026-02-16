# Poll Project TODO

Updated: 2026-02-16

## Done
- [x] GitHub Pages + Actions 배포 파이프라인 구축 (`.github/workflows/pages.yml`)
- [x] NESDC 화요일 18:00 KST 수집/적용 흐름 연결 (`src/tuesday_18kst_runner.py`)
- [x] 뉴스 섹션 안정화: 빌드 타임 `docs/news_latest.json` 생성 + fallback
- [x] 뉴스 필터 우선순위 적용
  - 1) `중앙선거여론조사심의위원회`
  - 2) 지정 여론조사기관명
  - 3) `여론조사`
- [x] 뉴스 중복 제거: 동일 날짜/동일 언론사 1건 유지
- [x] 대시보드 리디자인 반영 + tooltip 가독성 개선 + `x unified` hover
- [x] 대통령 지지율 파이프라인 추가
  - `src/president_approval_pipeline.py`
  - `outputs/president_approval_weekly.csv`
  - `outputs/president_approval_quality_report.csv`
- [x] 예측 모델 외생변수 옵션 추가 (`src/forecast.py --exog-approval on`)
- [x] 백테스트 비교 확장 (`ssm_exog`) (`src/backtest_report.py`)
- [x] 차트에 대통령 raw 시계열(긍정/부정) 오버레이 + 캡션 추가
- [x] 메인 컬러를 라이트 고가독성 팔레트로 변경
- [x] 2025-06-04~2026-02-16 주간 대통령 지표 백필 실행
  - 현재 채움: 37주 중 33주
  - 결과: `data/president_approval.csv`, `outputs/president_approval_weekly*.csv/xlsx`

## In Progress
- [ ] 대통령 raw 값 품질 고도화
  - 현재 결측 4주는 후처리에서 선형 보완 완료
  - 다음 단계: 후보 기사 원문 기반으로 보완값 대체 검토

## Next (High)
- [x] 대통령 raw 이상치 규칙 검토 및 리포트 추가
  - 산출물: `outputs/president_approval_outlier_report.csv`
- [x] 대통령 주간 표(approve/disapprove + 조사기관 + 조사기간 + 출처 URL)를 사이트에 별도 섹션으로 노출
- [ ] `run-pres-approval` 결과를 Pages 빌드에 포함할지 운영 정책 확정
  - 수동 실행만 허용 vs 주간 자동 실행

## Next (Medium)
- [ ] `src/weekly_run.py` 스캐폴드 TODO 구현
  - `scrape_latest_public_points()`
  - `update_weights()` constrained optimization
  - 주간 리포트 출력
- [ ] 회귀 테스트 추가
  - date parsing / blending / forecast I/O schema 검증

## Backlog
- [ ] 기사 보조 파서 고도화 (Gallup/Realmeter/NBS 소스별 파서 분리)
- [ ] 확률 레이어 고도화 (`p_win`, `gap>0` 확률 UI)
