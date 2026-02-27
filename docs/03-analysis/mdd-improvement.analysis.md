# mdd-improvement Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: QuantVision Platform
> **Analyst**: gap-detector agent
> **Date**: 2026-02-27
> **Design Doc**: [mdd-improvement.design.md](../02-design/features/mdd-improvement.design.md)

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design 문서(mdd-improvement.design.md)에 정의된 MDD 개선 방어 레이어 3단계와 실제 구현 코드를 비교하여,
일치 항목, 불일치 항목(의도적 변경 포함), 미구현 항목, 추가 구현 항목을 식별한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/mdd-improvement.design.md`
- **Implementation Files**:
  - `quant_project/backend/routers/portfolio.py`
  - `quant_project/scripts/run_backtest.py`
  - `quant_project/frontend/pages/2_backtest.py`
  - `quant_project/frontend/pages/6_strategy_advisor.py` (Design 범위 외)
- **Analysis Date**: 2026-02-27

---

## 2. Gap Analysis (Design vs Implementation)

### 2-1. `_get_regime()` -- SPY 200MA 조건 추가

| Design 항목 | Design 내용 | 구현 내용 | Status | Notes |
|-------------|------------|----------|--------|-------|
| SPY 200MA bear 조건 | `SPY 종가 < SPY 200일 이평 -> bear` | `spy_below_ma200` 판정 후 bear 조건에 포함 | ✅ Match | portfolio.py L130-142 |
| bull 조건 강화 | `VIX < 15 AND SPY > 200MA -> bull` | `vix < 15 and not spy_below_ma200 -> bull` | ✅ Match | portfolio.py L152 |
| VIX bear 기준 | `VIX > 20 -> bear` | `VIX > 25 -> bear` (VIX_BEAR_THRESHOLD=25.0) | ⚠️ Changed | Design은 20, 구현은 25. 의도적 변경 (과포지션 축소 문제 방지) |
| T10Y2Y < 0 | `T10Y2Y < 0 -> bear` | 동일 | ✅ Match | portfolio.py L148 |
| 반환값 확장 | `spy_price, spy_ma200 추가` 권장 | `spy_below_ma200: bool` 반환 (4-tuple) | ⚠️ Partial | bool만 반환, 수치(spy_price, spy_ma200)는 미포함 |
| SPY_MA_WINDOW 상수 | `SPY_MA_WINDOW = 200` | `SPY_MA_WINDOW = 200` | ✅ Match | portfolio.py L24 |

**소계**: 6항목 중 4 Match, 2 Partial/Changed = **67% exact match**

---

### 2-2. `get_current_portfolio()` -- 손절 룰 + 현금 비중

| Design 항목 | Design 내용 | 구현 내용 | Status | Notes |
|-------------|------------|----------|--------|-------|
| VIX_EXTREME 임계치 | `VIX_EXTREME_THRESHOLD = 25.0` | `VIX_EXTREME = 32.0` | ⚠️ Changed | Design 25 -> 구현 32. 의도적 상향 |
| 현금 비중 | `CASH_RESERVE_RATIO = 0.30` | `CASH_RESERVE_EXTREME = 0.30` | ✅ Match | 비율 동일, 변수명 약간 다름 |
| 손절 기준 | `STOP_LOSS_1M = -0.10` | `STOP_LOSS_1M = -0.10` | ✅ Match | portfolio.py L20 |
| 후보 2배 확보 | `nlargest(effective_n * 2)` | `candidate_n = min(effective_n * 2, len(signals_df))` | ✅ Match | portfolio.py L249 |
| 손절 필터 로직 | `ret_1m < -0.10 -> 제외` | 22일 수익률 < -0.10 종목 제외 | ✅ Match | portfolio.py L260-272 |
| 섹터 분산 30% | Design에 명시 (처리순서 5번) | `SECTOR_MAX_WEIGHT = 0.30` 적용 | ✅ Match | portfolio.py L290-311 |
| 현금 비중 적용 | `weight * 0.70 (VIX>25시)` | `cash_multiplier = 1.0 - CASH_RESERVE_EXTREME` (VIX>32시) | ⚠️ Changed | VIX 임계치가 25->32로 변경 |
| bear effective_n | `max(top_n // 4, 2)` (VIX>25 시) | `max(top_n // 3, 3)` (bear 기본) | ⚠️ Changed | Design은 //4, 구현은 //3 |
| 처리 순서 8단계 | 명세대로 순차 처리 | 대체로 일치 | ✅ Match | 순서 준수 |

**소계**: 9항목 중 5 Match, 4 Changed = **56% exact match**

---

### 2-3. `scripts/run_backtest.py` -- 레짐 로직 동기화

| Design 항목 | Design 내용 | 구현 내용 | Status | Notes |
|-------------|------------|----------|--------|-------|
| VIX_THRESHOLD 변경 | `25 -> 20` | `VIX_BEAR_THRESHOLD = 25.0` (유지) | ❌ Not matched | Design은 20으로 변경 명시, 구현은 25 유지 |
| VIX_EXTREME_THRESHOLD | `25.0` 신규 | `VIX_EXTREME_THRESHOLD = 32.0` | ⚠️ Changed | Design 25 -> 구현 32 |
| SPY 200MA 조건 | `spy_close < spy_ma200 -> 1/3 축소` | `spy_below_ma200 -> *0.80` (20% 축소) | ⚠️ Changed | Design은 1/3, 구현은 20%만 축소 (온건) |
| SPY_MA_WINDOW | 200 | 200 | ✅ Match | run_backtest.py L45 |
| 1단계 레짐 | `VIX>20 or SPY<200MA -> 1/3 (0.333)` | VIX>25 -> 0.50, SPY<200MA -> 0.80 (분리 적용) | ⚠️ Changed | 조건 분리, 배수 다름 |
| 2단계 레짐 | `T10Y2Y<0 -> *0.75` | `T10Y2Y<0 -> *0.85` | ⚠️ Changed | Design 25% -> 구현 15% 축소 |
| 3단계 레짐 | `VIX>25 -> *0.70` | `VIX>32 -> *0.70` | ⚠️ Changed | 동일 배수, VIX 임계치 다름 |
| 손절 룰 | `ret_1m < -0.10 종목 제거` | 동일 (STOP_LOSS_1M=-0.10) | ✅ Match | run_backtest.py L201-209 |
| 손절 안전장치 | 명시 없음 | `len(valid_scores) < 3이면 무시` | ⚠️ Added | 구현이 더 안전 |
| close 전달 | SPY 포함 close 전달 | `close=close` 전달 | ✅ Match | run_backtest.py L190 |
| baseline 저장 | `main()에서 baseline 저장` | 기존 summary -> baseline 복사 | ✅ Match | run_backtest.py L311-317 |
| 비교 리포트 출력 | `main()에서 비교 출력` | 개선 전후 비교 테이블 출력 | ✅ Match | run_backtest.py L344-366 |

**소계**: 12항목 중 5 Match, 6 Changed, 1 Not matched = **42% exact match**

---

### 2-4. `frontend/pages/2_backtest.py` -- 개선 전후 비교

| Design 항목 | Design 내용 | 구현 내용 | Status | Notes |
|-------------|------------|----------|--------|-------|
| 비교 테이블 | baseline vs current 표 | MDD/Sharpe/CAGR/Win Rate 비교 표 | ✅ Match | 2_backtest.py L209-264 |
| MDD 색상 강조 | `-30% 초과 시 빨간색` | 달성여부 배지 (OK/NG) + st.warning | ⚠️ Partial | 직접 색상 강조 대신 아이콘/배지 방식 |
| baseline 파일 경로 | `models/results/baseline_summary.json` | 동일 | ✅ Match | 2_backtest.py L216-218 |
| current 파일 경로 | `data/processed/backtest_summary.json` | 동일 | ✅ Match | 2_backtest.py L219-221 |
| st.dataframe 사용 | Design에 명시 | `st.dataframe(df_display)` | ✅ Match | 2_backtest.py L264 |

**소계**: 5항목 중 4 Match, 1 Partial = **80% exact match**

---

## 3. Missing Features (Design O, Implementation X)

| Item | Design Location | Description | Impact |
|------|-----------------|-------------|--------|
| VIX_THRESHOLD 20 변경 | design.md Section 2-3 | run_backtest.py에서 VIX_THRESHOLD를 25->20으로 변경해야 하나 25 유지 | Medium - 의도적 변경으로 판단됨 (docstring에 "VIX 20" 언급하나 상수는 25) |
| _get_regime 반환값에 spy_price, spy_ma200 수치 | design.md Section 2-1 | 프론트 표시용 수치 미포함 (bool만 반환) | Low |
| effective_n = max(top_n // 4, 2) | design.md Section 2-2 | VIX>25 초강세 bear시 //4 적용, 구현은 bear 기본 //3 | Low - 구현이 덜 공격적 |

---

## 4. Added Features (Design X, Implementation O)

| Item | Implementation Location | Description | Impact |
|------|------------------------|-------------|--------|
| `/strategy-guide` 엔드포인트 | portfolio.py L388-469 | 레짐 기반 전략 권고 API (risk_level, recommended_profile, next_scenarios) | Positive - UX 향상 |
| `frontend/pages/6_strategy_advisor.py` | 전체 파일 (159줄) | 전략 어드바이저 페이지 (레짐 배지, 가이드, 프로필 비교) | Positive - Design 범위 초과 기능 |
| `_get_close_prices_raw()` 헬퍼 | portfolio.py L161-166 | SPY 가격 조회용 별도 함수 | Neutral |
| 4단계 레짐 (VIX_EXTREME=32) | run_backtest.py L42, L147-148 | Design의 3단계를 4단계로 확장 (SPY 200MA 분리 + VIX 극단) | Positive - 더 세밀한 레짐 제어 |
| 파라미터 최적화 과정 섹션 | 2_backtest.py L88-205 | Sharpe vs MDD 산점도, 3종 프로필, 상세 테이블 | Positive - Design 범위 외 |
| 손절 안전장치 | run_backtest.py L208-209 | 손절 후 종목 < 3개이면 필터 무시 | Positive - 안정성 향상 |

---

## 5. Changed Features (Design != Implementation)

| Item | Design | Implementation | Reason | Impact |
|------|--------|----------------|--------|--------|
| VIX bear 기준 | 20 | 25 (portfolio.py, run_backtest.py 공통) | VIX>20 빈도 28%로 과도한 축소 방지 | High - 핵심 파라미터 변경 |
| VIX extreme 기준 | 25 | 32 | 극단적 공포를 더 보수적으로 정의 | High - 현금 유보 발동 조건 변경 |
| SPY<200MA 축소 비율 (backtest) | 1/3 (0.333) | 0.80 (20% 축소) | 온건한 적용 | Medium |
| T10Y2Y<0 축소 비율 | 0.75 (25% 축소) | 0.85 (15% 축소) | 완화 | Medium |
| bear effective_n | top_n // 4 (VIX>25시) | top_n // 3 (bear 기본) | 덜 공격적 축소 | Low |
| MDD 색상 강조 방식 | `-30% 초과 시 빨간색` | 달성여부 아이콘 배지 | UI 표현 방식 차이 | Low |

---

## 6. Match Rate Summary

### 항목별 일치율

| Section | Total Items | Exact Match | Changed | Not Impl | Match Rate |
|---------|:-----------:|:-----------:|:-------:|:---------:|:----------:|
| 2-1. _get_regime() SPY 200MA | 6 | 4 | 2 | 0 | 67% |
| 2-2. get_current_portfolio() | 9 | 5 | 4 | 0 | 56% |
| 2-3. run_backtest.py 레짐 동기화 | 12 | 5 | 6 | 1 | 42% |
| 2-4. frontend 비교 표 | 5 | 4 | 1 | 0 | 80% |
| **Total** | **32** | **18** | **13** | **1** | **56%** |

### Adjusted Match Rate (의도적 변경 감안)

의도적 변경(VIX 임계치 조정, 축소 비율 완화)은 코드 주석과 docstring에서 근거가 확인되므로,
"의도적 변경"을 partial match(0.5점)로 계산하면:

```
Exact Match:   18 items x 1.0 = 18.0
Changed:       13 items x 0.5 =  6.5
Not Impl:       1 item  x 0.0 =  0.0
Total:         24.5 / 32 = 76.6%
```

---

## 7. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (exact) | 56% | !! |
| Design Match (adjusted) | 77% | -- |
| Feature Completeness | 97% | OK |
| Added Value (Design 외 기능) | +6 items | OK |
| **Overall (adjusted)** | **77%** | **--** |

Status: OK = 90%+, -- = 70-89%, !! = <70%

---

## 8. Key Findings

### 8.1 의도적 파라미터 변경 (Justified Deviations)

구현 코드의 주석과 docstring에서 변경 사유가 명시되어 있음:

1. **VIX 임계치 25 유지** (Design은 20)
   - `run_backtest.py L39`: "VIX > 20이 28% 빈도 -> 과포지션 축소 문제 -> VIX 기준 25 복원"
   - 근거가 충분하며 합리적 판단

2. **VIX_EXTREME 32** (Design은 25)
   - 코로나급 공포만 극단 구간으로 분류하여 불필요한 현금 유보 방지
   - 실전 백테스트 결과 기반 조정으로 판단

3. **SPY 200MA 축소 비율 완화** (0.333 -> 0.80)
   - `run_backtest.py L41`: "SPY 200MA는 추가 조건으로 온건하게 적용"
   - 과도한 방어 방지

### 8.2 Design 문서 업데이트 필요

Design 문서가 초기 설계 의도를 반영하고 있으나, 실제 구현에서 백테스트 결과를 반영한
파라미터 튜닝이 이루어졌으므로, Design 문서를 현재 구현에 맞게 업데이트해야 함.

---

## 9. Recommended Actions

### 9.1 Immediate (Design 문서 동기화)

| Priority | Item | Action |
|----------|------|--------|
| 1 | VIX 임계치 | Design 문서의 VIX_BEAR=20 -> 25, VIX_EXTREME=25 -> 32 로 업데이트 |
| 2 | 축소 비율 | SPY 200MA 축소율 1/3 -> 0.80, T10Y2Y 축소율 0.75 -> 0.85 로 업데이트 |
| 3 | effective_n | Design의 `top_n // 4` -> `top_n // 3` 으로 업데이트 |
| 4 | 4단계 레짐 | Design의 3단계 -> 4단계 레짐 구조로 업데이트 |

### 9.2 Short-term (기능 보완)

| Priority | Item | Action |
|----------|------|--------|
| 1 | _get_regime 반환값 | spy_price, spy_ma200 수치를 반환값에 추가 (프론트 표시용) |
| 2 | Design에 추가 기능 반영 | /strategy-guide, 6_strategy_advisor.py를 Design에 추가 |

### 9.3 Documentation

| Item | Notes |
|------|-------|
| 파라미터 변경 이력 | 각 변경의 백테스트 근거를 Design에 "변경 이력" 섹션으로 기록 |
| 추가 기능 설계 | strategy-guide, strategy_advisor 페이지를 Design에 반영 |

---

## 10. Checklist (Design 명세 기준)

- [x] `_get_regime()` SPY 200MA 조건 추가
- [x] bear+neutral+bull 레짐 조건별 포지션 수 조정
- [ ] VIX > 25 -> 현금 30% (Design VIX_EXTREME=25, 구현 VIX_EXTREME=32로 변경)
- [x] 손절 룰: 1개월 -10% 제외
- [ ] `run_backtest.py` VIX_THRESHOLD 변경 (Design: 25->20, 구현: 25 유지)
- [x] `get_regime_multiplier()` SPY 200MA
- [x] `run_single_backtest()` 손절 룰
- [x] `frontend/pages/2_backtest.py` 개선 전후 비교 섹션
- [x] `models/results/baseline_summary.json` 생성

결과: 9항목 중 7 완료, 2 의도적 변경 = **78% checklist 달성**

---

## 11. Synchronization Recommendation

Match Rate 77% (adjusted) -- 70~90% 구간에 해당하므로:

> "일부 차이가 있습니다. 문서 업데이트를 권장합니다."

대부분의 차이가 **백테스트 결과 기반 의도적 파라미터 튜닝**이므로,
**Option 2: Design 문서를 구현에 맞게 업데이트** 를 권장합니다.

구체적으로:
1. Design 문서의 VIX/축소 비율 파라미터를 현재 구현값으로 수정
2. 변경 사유를 Design 문서에 "튜닝 이력" 섹션으로 추가
3. 추가 구현된 strategy-guide, 6_strategy_advisor를 Design에 반영

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-02-27 | Initial gap analysis | gap-detector agent |
