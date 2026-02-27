# Plan: ui-strategy-improvement

> QuantVision UI·전략 통합 고도화
> 작성일: 2026-02-27

---

## 1. 배경 및 목적

### 현재 상태
| 항목 | 문제점 |
|------|--------|
| app.py | 42줄 텍스트 나열, 디자인 없음, 워크플로우 안내 부재 |
| 백테스트 Contour | ml_weight 단일 차원 — 경사 안정성 시각적 확인 불가 |
| SPY 벤치마크 | equity_curve.parquet에 SPY 데이터 미저장 → 빈 차트 |
| 감성분석 | 디스플레이 전용 — 포트폴리오 선정에 전혀 미반영 |
| AI 해설 | 없음 — 각 지표의 의미·전략 근거 사용자 스스로 해석 필요 |

### 목표
1. 사이드바 단계별 워크플로우 (펀더멘털 필터 → 백테스트 검증 → 포트폴리오 → 실행) 안내
2. 백테스트: `rulebase_weight`를 독립 파라미터로 추가 → 3D Surface 히트맵
3. 감성점수를 ML 신호에 합산 (`sentiment_weight` 슬라이더)
4. 각 페이지에 Claude API 기반 실시간 AI 해설 패널

---

## 2. 구현 범위

### In Scope

#### A. app.py — UI 전체 리디자인
- 전문가용 다크 테마 CSS 주입
- 홈 대시보드: 레짐 배지 + 포트폴리오 요약 + AI 해설 요약
- 사이드바: 6단계 워크플로우 스테퍼 (번호 + 상태 배지)

#### B. run_backtest.py — 3D 파라미터 스윕
- `rule_score` 정의: 기존 factors.parquet의 기술적 지표 기반 룰베이스 신호
  ```
  rule_score = normalize(0.5×ret_3m + 0.3×ret_1m + 0.2×(1/vol_20))
  ```
- `run_single_backtest()` — `rule_weight` 파라미터 추가
  ```
  combined = (ml_w×ml_score + rb_w×rule_score) / (ml_w + rb_w)
  ```
- `param_sweep()` — 2D 스윕: `ml_weight[5]` × `rule_weight[5]` = 25 조합
- SPY buy-and-hold 수익률을 `equity_curve.parquet`에 두 번째 컬럼으로 추가

#### C. frontend/pages/2_backtest.py — 3D Surface + SPY 수정
- 기존 2D Contour → `go.Surface` 3D 차트 (x=ml_w, y=rule_w, z=Sharpe)
- SPY 벤치마크 라인 정상 표시

#### D. services/ai_advisor.py (신규) — Claude API 통합
- `get_page_insight(page, context_dict) -> str`
- `ANTHROPIC_API_KEY`를 `.env`에서 로드
- 페이지별 시스템 프롬프트 + 현재 지표값 → 한국어 해설 반환

#### E. backend/routers/ — `/api/advisor/insight` 엔드포인트 (신규)
- `POST /api/advisor/insight` — 페이지·지표값 수신 → AI 해설 반환
- 5분 캐싱 (동일 입력 반복 호출 방지)

#### F. frontend/pages/*.py — AI 해설 패널 추가 (전 페이지)
- 페이지 1: 필터 결과 기준으로 "현재 스크리닝 환경 해설"
- 페이지 2: Sharpe/MDD 지표 기준으로 "백테스트 성과 해설 + 파라미터 권장"
- 페이지 3: 레짐 + 포지션 기준 "현재 시장 상황 전략 해설"
- 페이지 4: 감성 점수 기준 "시장 심리 해설 + 전략 시사점"
- 페이지 6: 이미 전략 어드바이저 존재 → AI 해설 심화

#### G. backend/routers/portfolio.py — 감성 가중치 통합
- `sentiment_weight` 파라미터 추가 (기본 0.0, 범위 0.0~0.3)
- `sentiment_cache.json`에서 ticker별 점수 로드
- `adjusted_signal = ml_signal * (1 + sentiment_weight × clamp(sentiment, -1, 1))`

#### H. frontend/pages/3_portfolio_monitor.py — 감성 가중치 슬라이더
- 사이드바에 `sentiment_weight` 슬라이더 추가
- 포지션 테이블에 "감성 조정 신호" 컬럼 추가

### Out of Scope
- 백테스트 Walk-Forward 구조 변경
- 데이터 소스 교체 (yfinance 유지)
- ML 모델 재학습

---

## 3. 수용 기준 (Acceptance Criteria)

- [ ] app.py: 다크 테마 CSS 적용, 6단계 워크플로우 사이드바 표시
- [ ] 백테스트: 3D Surface 차트에서 `ml_weight × rule_weight × Sharpe` 시각화
- [ ] 백테스트: 누적수익 차트에서 SPY 벤치마크 라인 표시
- [ ] AI 해설: 각 페이지에서 "AI 해설 생성" 버튼 클릭 시 한국어 해설 출력
- [ ] 감성 통합: `sentiment_weight > 0` 설정 시 포트폴리오 구성 변화 확인
- [ ] 3D Surface: 25개 조합으로 파라미터 재스윕, `sharpe_contour.json` 갱신

---

## 4. 파일 영향 범위

| 파일 | 변경 유형 |
|------|-----------|
| `frontend/app.py` | 전면 수정 (CSS + 대시보드) |
| `frontend/pages/2_backtest.py` | 수정 (3D + SPY) |
| `frontend/pages/3_portfolio_monitor.py` | 수정 (감성 슬라이더) |
| `frontend/pages/1_fundamental_filter.py` | 수정 (AI 해설) |
| `frontend/pages/4_sentiment.py` | 수정 (AI 해설 + 통합 안내) |
| `scripts/run_backtest.py` | 수정 (rule_score + SPY + 2D 스윕) |
| `services/ai_advisor.py` | 신규 |
| `backend/routers/portfolio.py` | 수정 (sentiment_weight) |
| `backend/main.py` | 수정 (advisor 라우터 등록) |
| `data/processed/sharpe_contour.json` | 재생성 (25개 조합) |

---

## 5. 우선순위 및 구현 순서

| 단계 | 항목 | 이유 |
|------|------|------|
| 1 | run_backtest.py 수정 + 재스윕 | 3D 데이터 없으면 차트 불가 |
| 2 | services/ai_advisor.py 신규 | 모든 페이지가 의존 |
| 3 | backend (portfolio sentiment, advisor router) | 프론트 연결 전 완성 |
| 4 | frontend/app.py 리디자인 | 독립 작업 |
| 5 | frontend 각 페이지 AI 해설 + 감성 슬라이더 | 백엔드 완성 후 |

---

## 6. 환경 요구사항

```bash
# .env에 추가 필요
ANTHROPIC_API_KEY=your_key_here

# anthropic 패키지 설치
uv pip install anthropic
```
