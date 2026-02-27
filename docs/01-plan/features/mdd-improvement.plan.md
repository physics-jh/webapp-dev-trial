# Plan: mdd-improvement

> MDD(최대 낙폭) 개선 — QuantVision 레짐 필터 강화 + 리스크 제어
> 작성일: 2026-02-27 | 담당: QuantVision 프로토타입 v2

---

## 1. 배경 및 목적

### 현재 상태 (P8 통합 테스트 결과)
| 지표 | 현재 값 | 목표 |
|------|---------|------|
| MDD | **-32.7%** | **-30% 이하** |
| Sharpe | 0.795 | 0.85 이상 |
| CAGR | 20.0% | 유지 (±2% 허용) |
| 레짐 감지 | VIX > 25 → bear | VIX > 20 → bear (이미 적용) |

### 문제점
- P8 통합 테스트에서 `MDD -32.7% > -30%` **WARNING** 발생
- 2020년 3월 코로나 충격 구간 최대 낙폭 집중
- VIX 임계치 25가 너무 높아 레짐 전환이 늦음 (이미 20으로 수정)
- Bear 레짐에서도 포지션 크기 축소만으로는 방어 부족
- 섹터 편중 (Tech 비중 과도) → 단일 섹터 충격에 취약

### 이미 적용된 수정 (이번 세션)
- VIX 임계치: 25 → 20
- Bear 포지션: `top_n // 2` → `top_n // 3`
- 섹터 분산 제약: 업종별 최대 30%

---

## 2. 목표

### 주목표
- **MDD -30% 이하** 달성 (백테스트 재검증 필요)
- CAGR 훼손 최소화 (18% 이상 유지)
- Sharpe 개선 (0.85 이상 목표)

### 부목표
- 레짐 전환 지연 문제 근본 해결
- 포트폴리오 섹터 분산 실효성 강화
- 개별 종목 손실 제한 (월간 -10% 손절 룰)

---

## 3. 구현 범위

### In Scope
1. **레짐 필터 개선** — `portfolio.py`
   - VIX 20 → 적용 완료
   - 추가: SPY 200일 이평 이하 시 bear 강제 (추세 확인)
   - 추가: bear + VIX>25 → 현금 비중 30% 확보 (초강세 방어)

2. **손절 룰 추가** — `portfolio.py`
   - 개별 종목 1개월 수익률 -10% 이하 → 포지션 제외
   - 포트폴리오 전체 1주 손실 -5% → 포지션 크기 50% 축소

3. **백테스트 재실행** — `scripts/run_backtest.py`
   - 개선된 파라미터로 재백테스트
   - 2020년 3월 코로나 구간 집중 분석
   - `backtest_summary.json` + `equity_curve.parquet` 갱신

4. **성과 비교 리포트** — `models/results/`
   - 개선 전/후 MDD, Sharpe, CAGR 비교 테이블
   - Streamlit 페이지 2 (백테스트 UI) 업데이트

### Out of Scope
- ML 모델 재학습 (팩터 변경 없음)
- 데이터 소스 교체 (yfinance 유지)
- Walk-Forward 구조 변경

---

## 4. 구현 전략

### 접근법: 방어 레이어 3단계

```
[1단계] 레짐 조기 감지 (거시 지표)
  VIX > 20 OR SPY < 200MA OR T10Y2Y < 0
  → bear 레짐 → top_n 1/3 축소

[2단계] 초강세 bear (VIX > 25)
  → 현금 비중 30% 강제
  → 남은 70%에서 최상위 신호 종목만

[3단계] 개별 손절 (종목 레벨)
  월간 수익률 < -10% 종목 제외
  → 실질적 포지션 정리 효과
```

### 백테스트 재검증
- `scripts/run_backtest.py`에 위 조건 반영
- walk-forward 5개 스텝으로 2020년 구간 포함 확인
- 파라미터 스윕: VIX 임계치 15/18/20/23 × bear 축소비율 1/3·1/4

---

## 5. 영향 범위

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/routers/portfolio.py` | 수정 | 레짐 필터 + 손절 룰 |
| `scripts/run_backtest.py` | 수정/신규 | 개선된 조건으로 재백테스트 |
| `models/results/backtest_summary.json` | 갱신 | 새 성과 지표 |
| `data/processed/equity_curve.parquet` | 갱신 | 새 수익 곡선 |
| `frontend/pages/2_backtest.py` | 수정 | 개선 전후 비교 표시 |
| `quant_project/review_log.md` | 추가 | Agent F 검증 기록 |

---

## 6. 수용 기준 (Acceptance Criteria)

- [ ] 백테스트 MDD ≤ -30.0%
- [ ] 백테스트 CAGR ≥ 18.0%
- [ ] 백테스트 Sharpe ≥ 0.80
- [ ] 손절 룰: 1개월 -10% 초과 종목 포지션에서 제외 확인
- [ ] Bear 레짐 포지션 수 = `top_n // 3` 이하 (API 응답 확인)
- [ ] SPY 200MA 이하 시 bear 레짐 강제 적용 확인
- [ ] Streamlit 페이지 2에서 개선 전후 Sharpe/MDD 비교 표 표시

---

## 7. 우선순위 및 일정

| 항목 | 우선순위 | 예상 복잡도 |
|------|---------|------------|
| 레짐 필터 추가 조건 (SPY 200MA) | 높음 | 낮음 |
| 손절 룰 구현 | 높음 | 낮음 |
| 백테스트 재실행 | 높음 | 중간 |
| 성과 비교 UI | 중간 | 낮음 |

---

## 8. 참고 사항

- `quant_project/phase_status.json` P8 결과: `mdd_check: "WARNING — MDD -32.7% > -30%"`
- 이미 적용된 수정:
  - VIX 임계치 20 (portfolio.py `_get_regime()`)
  - Bear → `top_n // 3` (portfolio.py `get_current_portfolio()`)
  - 섹터 분산 제약 30% (portfolio.py `get_current_portfolio()`)
- `scripts/run_backtest.py` 존재 여부 확인 필요
