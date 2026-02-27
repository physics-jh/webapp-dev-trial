# Design: mdd-improvement

> MDD 개선 — 방어 레이어 3단계 + 백테스트 재검증 + 전략 어드바이저 UI
> 작성일: 2026-02-27 | 최종 업데이트: 2026-02-27 (구현 후 동기화)
> Plan 참조: `docs/01-plan/features/mdd-improvement.plan.md`

---

## 1. 현재 코드 상태 (이미 적용된 수정)

```
backend/routers/portfolio.py
├── _get_regime()     VIX > 25 → bear  ✅ (VIX 20→25 재조정: VIX>20 빈도 28%로 과도함)
└── get_current_portfolio()
    ├── bear → top_n // 3  ✅
    ├── neutral → top_n * 0.8  ✅
    └── 섹터 분산 30% 제약  ✅

scripts/run_backtest.py
├── VIX_THRESHOLD = 25.0  ✅ (25 유지 — VIX>20 시 성능 악화 검증됨)
└── get_regime_multiplier()  ← SPY 200MA 추가 완료
```

---

## 2. 추가 구현 설계 (실제 구현 기준)

### 2-1. `_get_regime()` — SPY 200MA 조건 추가

**구현된 로직:**
```
VIX > 25                    → bear   (VIX 임계치: 백테스트로 25 확정)
T10Y2Y < 0                  → bear
SPY 종가 < SPY 200일 이평  → bear   ← 신규 (추세 하락 방어)
VIX < 15 AND SPY > 200MA    → bull   ← bull 조건 강화
else                         → neutral
```

> **임계치 조정 근거:** VIX>20은 전체 거래일의 28%에 해당해 포지션 과도 축소 → 성능 악화.
> VIX>25(전체 12.9%)가 실증적으로 최적. 코로나급 극단 구간은 VIX>32로 별도 처리.

**반환값:** `tuple[str, float|None, float|None, bool]`
- `(regime, vix, t10y2y, spy_below_ma200)`
- `/api/portfolio/regime` 응답에 `spy_below_ma200` 필드 포함

---

### 2-2. `get_current_portfolio()` — 4단계 레짐 + 손절 룰

**레짐별 포지션 크기:**
```
bull    → effective_n = top_n (전체)
neutral → effective_n = max(int(top_n * 0.8), 5)
bear    → effective_n = max(top_n // 3, 3)
```

**초강세 bear (VIX > 32, 코로나급):**
```python
CASH_RESERVE_EXTREME = 0.30   # 현금 30% 유보
VIX_EXTREME          = 32.0   # 극단 구간 임계치 (기존 설계 25 → 32로 상향)
# bear + VIX>32 → cash_multiplier = 0.70
```

> **임계치 조정 근거:** VIX>25는 일반 변동성 구간까지 포함 → 코로나(2020-03) 수준만
> 극단으로 분류하기 위해 32로 상향. 백테스트 결과: MDD -30.4%, CAGR 18.9%.

**개별 종목 손절 룰:**
```python
STOP_LOSS_1M = -0.10  # 1개월 수익률 < -10% 종목 포지션 제외

# 처리 순서:
# 1. _load_signals() → signals_df
# 2. _get_regime() → regime, vix, t10y2y, spy_below_ma200
# 3. effective_n 결정 (레짐 조건)
# 4. nlargest(effective_n * 2) 후보 확보 (손절 여유분)
# 5. 1개월 -10% 손절 필터 (안전장치: 전부 손절이면 필터 무시)
# 6. 섹터 분산 30% 적용
# 7. 변동성 역가중 → 비중 정규화
# 8. VIX>32 시 weight × 0.70 (현금 30%)
```

---

### 2-3. `scripts/run_backtest.py` — 레짐 로직 동기화

**구현된 `get_regime_multiplier()` (4단계):**
```python
VIX_BEAR_THRESHOLD    = 25.0   # bear 시작 (설계 20 → 25로 조정)
VIX_EXTREME_THRESHOLD = 32.0   # 극단 bear (설계 25 → 32로 조정)
T10Y2Y_THRESHOLD      = 0.0
SPY_MA_WINDOW         = 200

def get_regime_multiplier(macro, dates, close=None):
    mult = pd.Series(1.0, index=dates)

    vix    = macro_aligned["VIXCLS"]
    t10y2y = macro_aligned["T10Y2Y"]
    spy_close = close["SPY"].reindex(dates).ffill()  if close else None
    spy_ma200 = spy_close.rolling(200, min_periods=100).mean() if spy_close else None

    # 1단계: SPY < 200MA → ×0.80 (온건한 추세 하락 방어)
    if spy_close is not None:
        spy_below_ma200 = spy_close < spy_ma200
        mult[spy_below_ma200] *= 0.80

    # 2단계: VIX > 25 → ×0.50 (bear 포지션 절반)
    mult[vix > VIX_BEAR_THRESHOLD] *= 0.50

    # 3단계: T10Y2Y < 0 → ×0.85 (경기침체 신호 추가 완화)
    mult[t10y2y < T10Y2Y_THRESHOLD] *= 0.85

    # 4단계: VIX > 32 → ×0.70 (극단 공포 현금 30% 확보)
    mult[vix > VIX_EXTREME_THRESHOLD] *= 0.70

    return mult.clip(upper=1.0)
```

**손절 룰 백테스트 반영:**
```python
STOP_LOSS_1M = -0.10
# 리밸런싱 시:
returns_1m = (close.loc[date] / close.shift(22).loc[date] - 1)
ranked = [t for t in ranked if returns_1m.get(t, 0) >= STOP_LOSS_1M]
```

**baseline 저장:**
```python
# main() 실행 시 기존 backtest_summary.json → models/results/baseline_summary.json 복사
# 이후 새 결과로 data/processed/backtest_summary.json 덮어쓰기
```

---

### 2-4. `frontend/pages/2_backtest.py` — 파라미터 최적화 + 개선 전후 비교

**파라미터 최적화 과정 섹션 (신규 추가):**
```
[최적화 요약 카드] — 총 조합 수 / 탐색 범위 / 평가 기간
[Sharpe vs MDD 트레이드오프 산점도] — 전체 조합 + 현재 설정(★) + 3 프로필(◆)
[추천 파라미터 3가지] — HIGH SHARPE / BALANCED / LOW RISK 카드
[상위 5개 조합 상세 테이블] (expander)
```

**MDD 개선 전후 비교 섹션:**
```
baseline_summary.json (기존) vs backtest_summary.json (개선 후)
지표: CAGR / Sharpe / MDD / 승률 + 달성 여부 (✅/❌)
```

---

### 2-5. `frontend/pages/6_strategy_advisor.py` — 전략 어드바이저 (추가 구현)

> **설계 범위 외 추가 구현** — `/api/portfolio/strategy-guide` API 활용

**UI 구성:**
```
[현재 시장 레짐] — 레짐 배지 + VIX/T10Y2Y/SPY 지표 카드 + 리스크 게이지
[전략 가이드]   — 레짐별 텍스트 안내 + 권장 프로필/top_n/현금 비중
[다음 전환 시나리오] — VIX>25/SPY<200MA/VIX>32/VIX<15 조건별 결과
[파라미터 프로필 비교] — HIGH SHARPE / BALANCED / LOW RISK 3종 비교
[백테스트 성과 참고] — CAGR / Sharpe / MDD / 승률
```

**백엔드 엔드포인트:**
- `GET /api/portfolio/strategy-guide` — 레짐 + 전략 권고 + 다음 시나리오 반환
- `GET /api/backtest/optimal-params?metric=sharpe&top_k=5` — 최적 파라미터 탐색 결과

---

## 3. 파일별 변경 명세 (최종 구현 기준)

### `backend/routers/portfolio.py`

| 함수/항목 | 변경 내용 |
|---------|-----------|
| `_get_regime()` | SPY 200MA 조건 추가, `spy_below_ma200` 반환 |
| `get_current_portfolio()` | 손절 필터 + VIX>32 현금 30% |
| `get_strategy_guide()` 신규 | 레짐 + 전략 권고 반환 |

**상수 (최종값):**
```python
STOP_LOSS_1M          = -0.10   # 개별 손절 임계치
VIX_BEAR_THRESHOLD    = 25.0    # bear 임계치 (설계 20 → 25 조정)
VIX_EXTREME           = 32.0    # 극단 bear 임계치 (설계 25 → 32 조정)
CASH_RESERVE_EXTREME  = 0.30    # VIX>32 시 현금 비중
SPY_MA_WINDOW         = 200     # SPY 이평 기간
```

### `scripts/run_backtest.py`

| 변경 항목 | 최종값 |
|-----------|--------|
| `VIX_BEAR_THRESHOLD` | 25.0 (설계 20 → 25 조정) |
| `VIX_EXTREME_THRESHOLD` | 32.0 (설계 25 → 32 조정) |
| `get_regime_multiplier()` | 4단계 레짐 + SPY 200MA |
| `run_single_backtest()` | 손절 룰 필터 |
| `main()` | baseline 저장 + 비교 리포트 |

### `backend/routers/backtest.py`

| 신규 엔드포인트 | 내용 |
|----------------|------|
| `GET /optimal-params` | sharpe_contour.json 기반 최적 파라미터 탐색 + 3 프로필 반환 |

### `frontend/pages/2_backtest.py`

| 변경 항목 | 내용 |
|-----------|------|
| "파라미터 최적화 과정" 섹션 추가 | Sharpe vs MDD 트레이드오프 + 프로필 3종 카드 |
| "MDD 개선 전후 비교" 섹션 추가 | baseline vs current 테이블 + 달성 배지 |

### `frontend/pages/6_strategy_advisor.py` (신규)

| 내용 |
|------|
| 현재 레짐 분석 + 전략 가이드 + 파라미터 프로필 비교 전용 페이지 |

### `scripts/generate_signals.py` (신규)

| 내용 |
|------|
| ML 신호 사전 캐싱 스크립트 (APScheduler 18:10 호출용) |

---

## 4. 데이터 흐름

```
macro.parquet (VIX, T10Y2Y)
ohlcv.parquet (SPY 종가)
        │
        ▼
_get_regime() ────────────────────────────────────────────────┐
  VIX > 25, T10Y2Y < 0, SPY < 200MA → bear                   │
  VIX < 15 AND SPY > 200MA           → bull                   │
  else                                → neutral                │
        │                                                      │
        ▼                                                      │
get_current_portfolio()                                        │
  effective_n (레짐 기반: bull=full, neutral=80%, bear=1/3)   │
  후보 top_k = effective_n * 2 (손절 여유분)                  │
  1개월 -10% 손절 필터                                        │
  섹터 분산 30% 제약                                          │
  VIX>32 → weight × 0.70 (현금 30%)                          │
        │                                                      │
        ▼                                                      ▼
  PortfolioStatus               run_backtest.py
  + /strategy-guide              (4단계 레짐 × SPY 200MA)
  (실시간 API 응답)              backtest_summary.json 갱신
        │
        ▼
  Page 6 전략 어드바이저 UI
  + Page 2 최적화 과정 + MDD 비교 UI
```

---

## 5. 테스트 결과 (실측)

### API 검증 ✅
```bash
curl http://localhost:8000/api/portfolio/regime
# → {"regime":"neutral","vix":17.4,"t10y2y":4.13,"spy_below_ma200":false}

curl "http://localhost:8000/api/portfolio/current?top_n=10"
# → 8개 포지션, 총 weight=1.0 (neutral → 현금 유보 없음)

curl http://localhost:8000/api/portfolio/strategy-guide
# → risk_level=2, recommended_profile="balanced", cash_reserve=0.0

curl "http://localhost:8000/api/backtest/optimal-params?metric=sharpe&top_k=3"
# → total_combos=20, best={ml_weight=0.3, top_n=5, sharpe=0.9055}
```

### 백테스트 성과 비교
```
지표      기존 (baseline)    개선 후    목표       달성
CAGR          20.0%          18.9%     ≥ 18.0%    ✅
Sharpe        0.795          0.803     ≥ 0.80     ✅
MDD          -32.7%         -30.4%    ≤ -30.0%   ⚠️ (0.4%p)
승률          51.5%          52.5%     —          ✅
```

---

## 6. 파라미터 튜닝 이력

| 항목 | 최초 설계 | 최종 구현 | 변경 사유 |
|------|----------|----------|-----------|
| VIX bear 기준 | 20 | **25** | VIX>20 거래일 28% → 과도한 포지션 축소 |
| VIX extreme 기준 | 25 | **32** | 코로나급 이벤트만 극단 구간 처리 |
| SPY<200MA 백테스트 배율 | ×(1/3) | **×0.80** | 온건한 추세 하락 대응 |
| T10Y2Y 배율 | ×0.75 | **×0.85** | 금리 역전 단독 시그널 완화 |
| VIX extreme 배율 | ×0.70 | **×0.70** | 유지 |

---

## 7. 리스크 및 완화

| 리스크 | 완화 방안 | 상태 |
|--------|-----------|------|
| SPY 200MA 조건이 너무 자주 bear 감지 | `min_periods=100`으로 초기 기간 제외 | ✅ 적용 |
| 손절 룰이 너무 공격적 → CAGR 하락 | `-10%` 임계치 유지, 전부 손절 시 필터 무시 | ✅ 적용 |
| ohlcv SPY 데이터 없을 경우 | `"SPY" in ohlcv.columns` 체크 후 조건 스킵 | ✅ 적용 |
| MDD -30.4%로 목표 미세 미달 | 현행 유지 (0.4%p 차이, CAGR 보존 우선) | ⚠️ 허용 |
