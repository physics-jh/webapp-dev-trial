# Resume Note — 2026-02-26

## 현재 상태

P0~P5 완료, P6 시작 상태에서 중단.

## 완료된 Phase

| Phase | 핵심 결과 |
|-------|---------|
| P0 환경 | 패키지 전체 설치, .gitignore |
| P1 데이터 | ohlcv.parquet (475종목 × 2,767일), macro.parquet |
| P2 팩터 | factors.parquet (130만 행), 팩터 10개 선택 |
| P3 백엔드 뼈대 | FastAPI 16개 엔드포인트 (빈 값 반환 상태) |
| P4 ML 학습 | LightGBM + Ridge 앙상블, WF 평균 IC 0.0224 |
| P5 백테스트 | CAGR 20.0%, Sharpe 0.795, MDD -32.7% |

## 다음에 할 일 (P6~)

### P6 백엔드 완성
- `backend/routers/fundamentals.py` → yfinance 펀더멘털 실제 연결
- `backend/routers/backtest.py` → backtest_summary.json, sharpe_contour.json 파일 읽어서 반환
- `backend/routers/portfolio.py` → 모델 예측으로 포트폴리오 구성, 레짐 반환
- `backend/routers/sentiment.py` → RSS feedparser + VADER + Reddit PRAW 연결
- `services/sentiment_service.py` 신규 작성
- APScheduler 일일 갱신 (18:00 KST)

### P7 프론트엔드
- `frontend/pages/1_fundamental_filter.py` — 슬라이더 필터
- `frontend/pages/2_backtest.py` — Plotly Sharpe Contour + 수익률 차트
- `frontend/pages/3_portfolio_monitor.py` — 30초 자동 갱신
- `frontend/pages/4_sentiment.py` — 뉴스 피드

### P8 통합 테스트
- look-ahead bias 날짜 검증
- Sharpe Contour 과적합 확인
- 업종 편중 확인

## 재개 명령어

```
phase_status.json 확인하고 마지막 완료 Phase 이후부터 이어서 진행해줘.
중단된 작업은 checkpoints/에서 불러와서 재개할 것.
```

## 실행 중인 서비스

- FastAPI 서버: 세션 종료 시 자동 중단됨 (재시작 필요)
  ```bash
  cd quant_project && nohup .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 > logs/uvicorn.log 2>&1 &
  ```
