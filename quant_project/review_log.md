# Agent F — Quant Reviewer Log

> Walk-Forward 검증, 편향 체크, 전략 강건성 평가 기록

---

## 2026-02-27 P8 통합 테스트 최종 리뷰

### ✅ Look-Ahead Bias 검증 (5/5 PASS)

| 검증 항목 | 결과 | 비고 |
|-----------|------|------|
| WF Split 날짜 경계 | PASS | 학습 3년 / 검증 6개월 고정 |
| 스케일러 leak | PASS | train 통계만 fit, val에 transform만 적용 |
| target_smooth 사용 | PASS | EDA 전용, 학습 타겟 미사용 확인 |
| 펀더멘털 PIT | WARNING | yfinance 발표일 정확도 제한 → Sharadar 전환 권장 |
| 구성종목 생존편향 | PASS | historical constituents 사용 |

### ✅ Sharpe Contour 분석

- **최적 파라미터**: ml_weight=0.5, top_n=10
- **Peak Ratio**: 1.28 (넓은 plateau) — 과적합 아님
- **강건 구간**: ml_weight 0.4~0.6 × top_n 8~15

### ⚠️ MDD 경고 (-32.7% > -30% 임계치)

**원인 분석**:
- 2020년 3월 코로나 충격 구간에서 최대 낙폭 발생
- VIX 25 이상 → bear 레짐 감지 → top_n 절반 축소 적용되었으나
  시장 하락 속도가 레짐 전환보다 빨라 충분한 방어 미흡

**권장 조치** (우선순위순):
1. VIX 임계치 하향: 25 → 20 (조기 감지)
2. 레짐 bear 시 포지션 축소 비율 강화: top_n // 2 → max(top_n // 3, 3)
3. 개별 종목 손절 룰 추가: 월간 손실 -10% 초과 시 청산
4. 섹터 분산 제약 도입: 업종별 최대 30% (현재 Tech 편중 관찰)

---

## 2026-02-27 P6/P7 구현 리뷰

### 백엔드 구현 평가

| 항목 | 상태 | 비고 |
|------|------|------|
| AnalysisPlugin 추상 레이어 | ✅ 완성 | FreePlugin 동작, MCPPlugin 스텁 준비됨 |
| APScheduler 일일 파이프라인 | ✅ 구현 | 18:00~18:30 KST 4단계 |
| 감성분석 RSS+VADER | ✅ 구현 | RSS 50건 수집 확인 |
| /api/analysis/{ticker} | ✅ 동작 | AAPL 원페이저 정상 생성 |
| Portfolio sentiment 연동 | ✅ 수정됨 | 포지션 테이블 감성점수 컬럼 추가 |

### 프론트엔드 구현 평가

| 페이지 | 상태 | 비고 |
|--------|------|------|
| 1. 펀더멘털 필터 | ✅ | yfinance 실시간 조회 (속도 제한 주의) |
| 2. 백테스트 UI | ✅ | Sharpe Contour + 누적수익 차트 |
| 3. 포트폴리오 모니터 | ✅ | 30초 자동갱신 + 레짐 뱃지 |
| 4. 감성분석 피드 | ✅ | RSS 헤드라인 + TF-IDF 키워드 |
| 5. 종목 정성 리포트 | ✅ | FreePlugin 원페이저 (신규) |

---

## 2026-02-26 P4/P5 리뷰

### ML 모델 평가

- **WF IC**: 0.0224 (IC 0.02 임계치 근접 — 모니터링 필요)
- **앙상블**: LightGBM + Ridge (XGBoost IC 미달로 제외)
- **Train/Test IC 갭**: 정상 범위 내

### 백테스트 성과

| 지표 | 값 | 평가 |
|------|----|------|
| CAGR | 20.0% | ✅ 양호 |
| Sharpe | 0.795 | ✅ 수용 가능 |
| MDD | -32.7% | ⚠️ 임계치 초과 |
| Hit Rate | 51.5% | ✅ 양호 |

### 팩터 품질 참고사항

- IC 기준(0.02) 미달 팩터 제거 후 10개 선택
- `build_factors.log` 기록: IC 통과 팩터 수 제한적
- 추가 팩터 발굴 여지 있음 (earnings momentum, short interest 등)

---

## 다음 이터레이션 권장 사항

### 우선순위 높음
1. **MDD 개선**: VIX 임계치 20으로 하향 + bear 포지션 축소 강화
2. **IC 개선**: 팩터 추가 발굴 (Sharadar 전환 시 PIT 펀더멘털 팩터 활용)
3. **섹터 분산**: 업종별 최대 30% 제약 추가

### 우선순위 중간
4. **데이터소스 전환**: yfinance → Alpaca (실시간 PIT 보장)
5. **MCPPlugin 전환**: FreePlugin → FactSet MCPPlugin (정성 분석 품질 향상)
6. **PostgreSQL 전환**: Parquet → 실시간 업데이트 지원

---
*Agent F — QuantVision Quant Reviewer*
*최종 업데이트: 2026-02-27*
