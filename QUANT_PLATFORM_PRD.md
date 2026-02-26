# QuantVision Platform — PRD

> S&P 500 유니버스 기반 ML 팩터 전략 + 웹 대시보드  
> 개발환경: GitHub Codespaces + Claude Code CLI + bkit (PDCA)  
> 버전: v3.1 | 2026-02-24

---

## 1. 설계 원칙 (필독)

### 추상화 레이어
- `DataProvider`: 데이터 소스 교체 가능 → `config.py`의 `DATA_PROVIDER` 값만 변경
- `StorageBackend`: DB 교체 가능 → `config.py`의 `STORAGE_BACKEND` 값만 변경
- API 키: 코드 직접 작성 **절대 금지** → `.env` + `os.getenv()` 사용

```python
# config.py — 여기만 바꾸면 전체 교체
DATA_PROVIDER    = os.getenv("DATA_PROVIDER", "yfinance")   # → "alpaca" → "polygon"
STORAGE_BACKEND  = os.getenv("STORAGE_BACKEND", "parquet")  # → "postgres"
```

### 생존편향 & Look-Ahead Bias 방지
- [ ] S&P 500 구성종목: 당시 기준 historical 리스트 사용 (현재 구성 X)
- [ ] 펀더멘털 데이터: 발표일 기준 +1영업일부터 적용 (PIT)
- [ ] Walk-Forward 검증: k-fold 절대 금지
- [ ] 스케일링: train set 통계만 사용, test에 leak 금지

---

## 2. 시스템 아키텍처

```
Frontend  (Streamlit)
    │ REST API
Backend   (FastAPI)
    │
    ├── DataProvider Layer     services/data_provider.py
    │   yfinance → Alpaca → Polygon → Sharadar
    │
    └── StorageBackend Layer   services/storage.py
        Parquet → PostgreSQL → TimescaleDB
```

### DataProvider 구조

```python
class BaseDataProvider:
    def get_ohlcv(self, tickers, start, end) -> pd.DataFrame: ...
    def get_fundamentals(self, ticker) -> dict: ...
    def get_macro(self, series_id, start, end) -> pd.Series: ...

class YfinanceProvider(BaseDataProvider): ...   # 프로토타입
class AlpacaProvider(BaseDataProvider):   ...   # 실전 스텁
class PolygonProvider(BaseDataProvider):  ...   # 실전 스텁
class SharadarProvider(BaseDataProvider): ...   # PIT 펀더멘털 스텁
```

### StorageBackend 구조

```python
class BaseStorage:
    def save(self, df, table, **kwargs): ...
    def load(self, table, **filters) -> pd.DataFrame: ...
    def append(self, df, table): ...

class ParquetStorage(BaseStorage):   ...   # 프로토타입
class PostgresStorage(BaseStorage):  ...   # 실전 스텁
```

---

## 3. 프로젝트 구조

```
quant_project/
├── CLAUDE.md
├── QUANT_PLATFORM_PRD.md
├── phase_status.json          # Phase 진행 상태 추적
├── resume_note.md             # 중단/재개 메모
├── review_log.md              # Agent F 리뷰 기록
├── .env                       # API 키 (git 제외)
├── config.py                  # DATA_PROVIDER, STORAGE_BACKEND
│
├── services/
│   ├── data_provider.py       # DataProvider 추상 레이어
│   ├── storage.py             # StorageBackend 추상 레이어
│   └── sentiment_service.py
│
├── data/
│   ├── raw/
│   ├── processed/             # Parquet 저장
│   ├── constituents/          # S&P500 historical
│   └── checkpoints/           # 중단 대비 체크포인트
│
├── models/
│   ├── trained/
│   │   ├── v1_20260224/
│   │   └── latest -> v1_20260224/   # 심볼릭 링크
│   ├── results/
│   └── model_registry.json
│
├── backend/
│   └── routers/
│       ├── fundamentals.py
│       ├── backtest.py
│       ├── portfolio.py
│       └── sentiment.py
│
├── frontend/
│   └── pages/
│       ├── 1_fundamental_filter.py
│       ├── 2_backtest.py
│       ├── 3_portfolio_monitor.py
│       └── 4_sentiment.py
│
└── logs/
```

---

## 4. 팩터 설계

| 그룹 | 팩터 | ML 입력 |
|------|------|---------|
| 모멘텀 | ret_1m, ret_3m, mom_gap | ✅ |
| 변동성 | vol_20, downside_vol, natr, skew, kurt | ✅ |
| 유동성 | dol_vol, vol_zscore, mfi | ✅ |
| 추세/반전 | rsi, disparity_20, ma_cross | ✅ |
| 매크로 | VIX, TNX, DXY, 장단기금리차 | ❌ 레짐필터만 |
| 펀더멘털 | PER, PBR, EPS성장률, ROE, D/E | ❌ 스크리닝만 |

```python
target_next   = close.pct_change().shift(-1)       # 학습 타겟
target_smooth = target_next.rolling(5).mean()       # EDA 전용 — 학습 절대 사용 X
```

**팩터 유효성 검증 기준**
- IC_mean < 0.02 → 제거
- VIF > 10 → 제거
- 최종 선택: 10~15개

---

## 5. ML 모델

| 항목 | 설정 |
|------|------|
| Walk-Forward | 학습 3년 / 검증 6개월 / 스텝 3개월 |
| 후보 모델 | XGBoost, LightGBM, Ridge (베이스라인) |
| 튜닝 | Optuna n_trials=50, max_depth≤5, min_child_weight≥50 |
| 앙상블 | 상위 2개 모델 동일가중 |
| 모델 저장 | `models/trained/v{날짜}_{시각}/` + `latest` 심볼릭 링크 |
| 버전 추적 | `model_registry.json` |

---

## 6. 백테스트

| 항목 | 설정 |
|------|------|
| 라이브러리 | vectorbt |
| 리밸런싱 | 월 1회 |
| 거래비용 | 슬리피지 0.1% + 수수료 0.05% |
| 포지션 크기 | 변동성 역가중 |
| 펀더멘털 스크리닝 | 500 → 150종목 |
| 파라미터 스윕 | ml_weight(0.3~0.7) × top_n(5~20) → Sharpe Contour |
| 레짐 조정 | VIX / 금리차 기반 포지션 크기 조정 |

---

## 7. Subagent 구성

```
[오케스트레이터]
├── Agent A  Data Engineer      데이터 수집 / 파이프라인
├── Agent B  Quant Researcher   팩터 분석 / 모델 설계
├── Agent C  ML Engineer        학습 / 튜닝 / 버전 관리
├── Agent D  Backend Developer  FastAPI / 추상 레이어
├── Agent E  Frontend Developer Streamlit UI
└── Agent F  Quant Reviewer     편향 검증 (전 Phase 병렬 실행 → review_log.md)
```

---

## 8. 개발 Phase

### phase_status.json 구조
```json
{
  "phases": {
    "P0_setup":        { "status": "pending" },
    "P1_data":         { "status": "pending" },
    "P2_factor":       { "status": "pending" },
    "P3_backend_base": { "status": "pending" },
    "P4_ml":           { "status": "pending" },
    "P5_backtest":     { "status": "pending" },
    "P6_backend":      { "status": "pending" },
    "P7_frontend":     { "status": "pending" },
    "P8_integration":  { "status": "pending" }
  }
}
```

### Phase별 핵심 작업

**P0 환경세팅**
```bash
uv add xgboost lightgbm optuna vectorbt ta
uv add fastapi uvicorn streamlit plotly praw feedparser vaderSentiment
uv add python-dotenv sqlalchemy psycopg2-binary apscheduler
echo ".env" >> .gitignore
```

**P1 데이터** ← Claude 자동 (Agent A + F)
- S&P 500 historical constituents 2014~2024 (상장폐지 포함)
- OHLCV: 50종목 배치, 간격 1초, `checkpoints/ohlcv_progress.json`
- FRED 매크로: VIX, DXY, TNX, T10Y2Y
- 산출물: `ohlcv.parquet`, `macro.parquet`

**P2 팩터** ← Claude 자동 (Agent B + F)
- ta 라이브러리로 팩터 계산
- IC / VIF 검증 후 선택
- 산출물: `factors.parquet`, `selected_features.json`

**P3 백엔드 뼈대** ← Claude 자동 (Agent D + F)
- `services/data_provider.py` 추상 레이어 + 구현체
- `services/storage.py` 추상 레이어 + 구현체
- FastAPI 엔드포인트 뼈대 (구현은 P6에서)
- 검증: `uvicorn backend.main:app --reload` → `/docs` 확인

**P4 ML 학습** ← Claude 자동 (Agent B + C + F)
- Walk-Forward + Optuna 튜닝
- `checkpoints/wf_results/` 스텝별 저장
- 산출물: `model_registry.json`, `models/trained/latest/`

**P5 백테스트** ← Claude 자동 (Agent B + C + F)
- vectorbt 백테스트
- 파라미터 스윕 → `sharpe_contour.json`
- 산출물: `backtest_summary.json`

**P6 백엔드 완성** ← Claude 자동 (Agent D + F)
- 엔드포인트 실제 데이터 연결
- `sentiment_service.py`: RSS + VADER + Reddit PRAW
- APScheduler 일일 갱신 (18:00~18:30 KST)

**P7 프론트엔드** ← Claude 자동 (Agent E + F)
- 페이지 1: 펀더멘털 필터 (슬라이더)
- 페이지 2: 백테스트 + Sharpe Contour (Plotly)
- 페이지 3: 포트폴리오 모니터 (30초 자동 갱신)
- 페이지 4: 감성분석 피드

**P8 통합테스트** ← 본인 직접 판단
- Look-ahead bias 날짜 검증
- Contour sharp peak 여부 → 과적합 의심
- 업종 편중 확인
- APScheduler 수동 1회 실행

---

## 9. 중단 · 재개

**재개 프롬프트**
```
phase_status.json 확인하고 마지막 완료 Phase 이후부터 이어서 진행해줘.
중단된 작업은 checkpoints/에서 불러와서 재개할 것.
```

**중단 전 정리 프롬프트**
```
현재 상태를 phase_status.json에 업데이트하고
중간 결과물을 data/checkpoints/에 저장해줘.
resume_note.md에 현재 상태와 다음 할 일 정리해줘.
```

---

## 10. 데이터 소스 로드맵

### 프로토타입 (완전 무료)

| 항목 | 소스 | 비고 |
|------|------|------|
| OHLCV | yfinance | Rate limit 주의 |
| 매크로 | FRED API | — |
| 펀더멘털 | yfinance | PIT 보장 X |
| S&P500 구성종목 | Wikipedia 스크래핑 | 수동 보정 필요 |
| 뉴스 | Yahoo Finance / Reuters RSS | API 키 불필요 |
| 감성 엔진 | VADER | — |
| Storage | Parquet | — |

### 실전 전환 (유료)

| 단계 | 소스 | 비용 | 용도 |
|------|------|------|------|
| 실전 v1 | Alpaca | ~$99/월 | 실시간 OHLCV + 주문 |
| 실전 v2 | Polygon.io | $29~199/월 | 틱데이터, 옵션, 뉴스 |
| 퀀트 고도화 | Sharadar | $50~/월 | PIT 펀더멘털 **필수** |
| 감성 고도화 | NewsAPI Pro + FinBERT | $449/월 | 전문 경제 매체 |

> 교체 방법: `.env`의 `DATA_PROVIDER` 값 변경 → `config.py` 자동 반영

---

## 11. bkit 실행 프롬프트 (복붙용)

```bash
# 세션 시작
cd /workspaces/webapp-dev-trial/quant_project
source .venv/bin/activate
claude

# 초기화
/plan QuantVision 퀀트 플랫폼 — S&P500 ML 팩터 전략 + 웹 대시보드

# Phase 실행
/do [Phase 작업 내용]

# 검증
/check 현재 단계 편향 검증

# 이어서 진행
> phase_status.json 확인하고 다음 Phase 이어서 진행해줘

# 소스 교체 테스트
> config.py DATA_PROVIDER를 "alpaca"로 바꾸고 AlpacaProvider 구현 완성해줘
```

---

*⚠️ 실전 운용 전 Sharadar(PIT 펀더멘털) 교체 필수*
