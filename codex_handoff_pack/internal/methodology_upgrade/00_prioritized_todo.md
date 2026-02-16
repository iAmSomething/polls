# Methodology Upgrade TODO (Prioritized)

Updated: 2026-02-16

## Priority 1 (Immediate Impact)
1. Time-varying House Effect (정당×기관 시계열 편향 보정)
- Goal: 고정 MAE 가중치 한계를 보완하고, 시점별 기관 편향 변동을 반영.
- Doc: `docs/methodology_upgrade/01_time_varying_house_effect.md`

2. Sample-size-aware Observation Variance (표본수 기반 관측 가중)
- Goal: 동일 기관이라도 조사마다 신뢰도를 표본수 기반으로 차등 반영.
- Doc: `docs/methodology_upgrade/02_sample_size_variance_weighting.md`

## Priority 2 (Forecast Accuracy)
3. State-space Latent Trend Forecast (로컬레벨/랜덤워크 기반 예측)
- Goal: 급변 구간에서 단순 추세 예측의 한계를 보완.
- Doc: `docs/methodology_upgrade/03_state_space_forecast.md`

4. Regime Shift Guardrail (정치 이벤트 국면 전환 감지)
- Goal: 큰 사건 직후 과거 데이터의 과신을 줄이는 적응형 감쇠.
- Doc: `docs/methodology_upgrade/04_regime_shift_guardrail.md`

## Priority 3 (Scope Expansion)
5. Menu Effect Model (후보 조합 효과)
- Goal: 후보 포함/제외에 따른 지지율 왜곡을 분리 추정.
- Doc: `docs/methodology_upgrade/05_menu_effect_model.md`

6. Uncertainty & Probability Layer (불확실성/승리확률 공개)
- Goal: 점추정 중심 화면을 구간/확률 중심으로 확장.
- Doc: `docs/methodology_upgrade/06_uncertainty_probability_layer.md`

## Execution Order (Recommended)
1. P1-1 -> 2. P1-2 -> 3. P2-3 -> 4. P2-4 -> 5. P3-5 -> 6. P3-6

## Definition of Done (Program-level)
- Weekly backtest MAE가 기준선 대비 유의미하게 개선.
- 최근 8주 구간에서 방향성(hit rate) 악화 없음.
- GitHub Pages 대시보드에 방법론/가중치/신뢰구간 반영.
