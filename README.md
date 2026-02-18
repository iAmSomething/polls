# 주간 여론 합성/예측 대시보드

정당 지지율 여론조사를 주간 단위로 통합(블렌딩)하고, 다음 주 예측과 백테스트 성능을 함께 공개하는 프로젝트입니다.  
배포는 GitHub Pages + GitHub Actions로 자동화되어 있으며, 데이터 업데이트부터 대시보드 생성까지 주기적으로 실행됩니다.
https://iamsomething.github.io/polls/#methodology-disclosure
## 1) 프로젝트 개요

이 프로젝트는 다음 문제를 해결하기 위해 만들어졌습니다.

- 여러 기관 여론조사 결과를 단일 지표로 통합하기 어렵다.
- 기관별 편향(하우스 이펙트), 표본수 차이, 시점별 변동성을 함께 고려해야 한다.
- 예측을 제시할 때 점추정만으로는 불확실성을 전달하기 어렵다.

따라서 본 시스템은:

- 기관 정확도 기반 가중합 + 시점별 편향 보정
- 상태공간(SSM) 기반 1주 예측
- 예측구간(80%) 및 legacy 대비 백테스트 개선율

을 한 화면에서 제공하도록 설계되었습니다.

## 2) 기획 의도

- `데이터 기반`: 단일 조사 결과가 아닌 다기관 통합 추세 제공
- `운영 자동화`: 매주 반복 작업(수집/갱신/배포) 자동 실행
- `투명성`: 방법론, 기관 가중치, 백테스트 지표를 함께 공개
- `확장성`: 이슈 인테이크(LLM), NESDC 주간 갱신, 확률 레이어까지 단계적 확장

## 3) 왜 필요한가 (필요성)

- 여론조사는 조사시점·표본·질문구성·조사방식 차이로 편차가 크며, 단건 해석은 과잉반응을 유발할 수 있습니다.
- 기관별 성향 차이와 급변 국면(정치 이벤트)에서는 고정 가중치만으로는 설명력이 떨어질 수 있습니다.
- 정기적으로 공개되는 공식 데이터(NESDC 누적 xlsx)를 자동으로 반영해야 운영 비용이 낮아집니다.

## 4) 방법론 요약

### 4.1 데이터 합성(블렌딩)

- 대상: 선정된 주요 9개 여론조사기관
- 기본 가중치: 기관별 `1/MAE` 정규화
- 보정 1: `time-varying house effect`  
  기관×정당별 잔차를 EWMA로 추적해 시점별 편향을 완화
- 보정 2: `sample-size-aware weighting`  
  조사별 표본수 기반 관측 분산(`p(1-p)/n`) 가중 반영

### 4.2 예측

- 모델: 로컬레벨 상태공간모형(SSM)
- 산출: `next_week_pred`, `pred_sd`, `pred_lo_80`, `pred_hi_80`
- 급변 대응: `regime shift guardrail`  
  최근 변동성 급등 시 process noise를 키워 적응성을 확보

### 4.3 검증(백테스트)

- 롤링 1-step 백테스트(legacy vs ssm)
- 산출물:
  - `outputs/backtest_predictions.csv`
  - `outputs/backtest_summary.csv`
  - `outputs/backtest_report.md`
- 대시보드에는 `legacy 대비 ssm MAE 개선율`을 표시

## 5) 데이터 및 출처

### 5.1 핵심 입력 데이터

- NESDC(중앙선거여론조사심의위원회) 공개 누적 xlsx
- 기관별 정확도(MAE) 파일  
  (`pollster_accuracy_clusters_2024_2025.xlsx`)
- 이슈 데이터(선택): `data/issues_input.csv`

### 5.2 기사 링크(하단 뉴스 카드) 기준

- 기사 본문에 `중앙선거여론조사심의위원회` 문구 포함을 필수 조건으로 사용
- 빌드 시점 수집 후 `docs/news_latest.json` 생성
- 수집 실패 시에도 페이지가 비지 않도록 fallback을 적용

### 5.3 참고/원문 링크

- NESDC 게시판:  
  `https://www.nesdc.go.kr/portal/bbs/B0000025/list.do?menuNo=200500`
- 프로젝트 대시보드(배포):  
  `https://iamsomething.github.io/polls/`

## 6) 시스템 구성

- 파이프라인: `codex_handoff_pack/src/pipeline.py`
- 예측: `codex_handoff_pack/src/forecast.py`
- 백테스트: `codex_handoff_pack/src/backtest_report.py`
- 사이트 생성: `codex_handoff_pack/src/generate_site.py`
- NESDC 수집/적용:
  - `codex_handoff_pack/src/fetch_nesdc_weekly.py`
  - `codex_handoff_pack/src/apply_nesdc_weekly_update.py`
  - `codex_handoff_pack/src/tuesday_18kst_runner.py`

## 7) 실행 방법 (로컬)

```bash
cd codex_handoff_pack
make setup
make smoke

# 메인 파이프라인
python src/pipeline.py
python src/forecast.py --model ssm --regime-guard on
python src/backtest_report.py --regime-guard on
python src/generate_site.py
```

생성 결과:

- 대시보드: `codex_handoff_pack/docs/index.html`
- 예측: `codex_handoff_pack/outputs/forecast_next_week.xlsx`
- 백테스트: `codex_handoff_pack/outputs/backtest_report.md`

## 8) 배포 및 자동화

- 워크플로우 파일: `.github/workflows/pages.yml`
- 배포 방식: GitHub Actions → GitHub Pages
- 정기 실행:
  - 월요일 09:00 KST 정기 빌드
  - 화요일 18:00 KST NESDC 갱신 체크(시간대 윈도우 재시도)

필수 GitHub 설정:

1. `Settings -> Pages -> Build and deployment`
2. `Source = GitHub Actions`
3. (선택) 이슈 평가 자동화를 사용할 경우 `PPLX_API_KEY` secret 등록

## 9) 프로젝트 범위와 한계

- 본 프로젝트는 통계적 보조지표를 제공하는 데이터 제품이며, 정치적 의사결정을 직접 대체하지 않습니다.
- 기사 수집/링크는 외부 소스 가용성에 영향을 받을 수 있습니다.
- 후보조합(menu effect) 모형은 정당 지지도 범위에서는 기본 비활성(향후 후보조사 확장 시 적용)입니다.
