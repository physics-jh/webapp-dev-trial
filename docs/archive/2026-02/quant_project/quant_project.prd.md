# QuantVision Platform — PRD

> S&P 500 유니버스 기반 ML 팩터 전략 + 웹 대시보드  
> 개발환경: GitHub Codespaces + Claude Code CLI  
> 버전: v4.0 | 2026-02-27

---

## 1. 설계 원칙 (필독)

### 1-1. 추상화 레이어 — 교체 용이성

모든 외부 의존성(데이터 소스, DB, 분석 플러그인)은 추상 레이어를 통해서만 접근.  
교체 시 `config.py` 또는 `.env` 한 줄만 수정하면 전체 반영.

```python
# config.py
DATA_PROVIDER      = os.getenv("DATA_PROVIDER",      "yfinance")   # → "alpaca" → "polygon"
STORAGE_BACKEND    = os.getenv("STORAGE_BACKEND",    "parquet")    # → "postgres"
FUNDAMENTAL_SOURCE = os.getenv("FUNDAMENTAL_SOURCE", "plugin_free") # → "plugin_mcp"
SENTIMENT_SOURCE   = os.getenv("SENTIMENT_SOURCE",   "rss_vader")  # → "newsapi_finbert"
```

### 1-2. 레이어 구조 전체 그림

```
┌─────────────────────────────────────────────────────────────┐
│                   Frontend (Streamlit)                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼──────────────────────────────────┐
│                   Backend (FastAPI)                          │
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐                 │
│  │ DataProvider    │  │ StorageBackend   │                 │
│  │ (소스 교체)     │  │ (DB 교체)        │                 │
│  └────────┬────────┘  └────────┬─────────┘                 │
│           │                    │                            │
│  ┌────────▼────────────────────▼─────────┐                 │
│  │        AnalysisPlugin Layer           │  ← 신규 추가    │
│  │  (정성 분석 소스 교체)                 │                 │
│  │  free(Claude 자체) → MCP(FactSet 등)  │                 │
│  └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 1-3. API 키 관리

```bash
# .env (git 절대 커밋 X)

# 데이터 소스
DATA_PROVIDER=yfinance
STORAGE_BACKEND=parquet
FUNDAMENTAL_SOURCE=plugin_free
FRED_API_KEY=your_fred_key

# 감성분석 (프로토타입: RSS 무료)
# NEWS_API_KEY=          ← v2 유료 전환 시 활성화
REDDIT_CLIENT_ID=your_reddit_id
REDDIT_CLIENT_SECRET=your_reddit_secret

# 실전 전환 시 채울 키들 (지금은 빈 칸)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
POLYGON_API_KEY=
SHARADAR_API_KEY=

# financial-services-plugins MCP (유료 전환 시)
FACTSET_API_KEY=
MORNINGSTAR_API_KEY=
SP_GLOBAL_API_KEY=
```

### 1-4. 생존편향 & Look-Ahead Bias 체크리스트

- [ ] S&P 500 구성종목: 당시 기준 historical 리스트 사용 (현재 구성 X)
- [ ] 펀더멘털 데이터: 발표일 기준 +1영업일부터 적용 (PIT)
- [ ] Walk-Forward 검증: k-fold 절대 금지
- [ ] 스케일링: train set 통계만 사용, test에 leak 금지

---

## 2. financial-services-plugins 통합 설계

### 2-1. 이 플러그인이 하는 일

Anthropic 공식 금융 서비스 플러그인. **팩터 데이터를 수집하는 도구가 아니라**  
정량 ML 파이프라인이 선별한 종목에 대한 **정성 분석을 자동화**하는 도구.

```
[ML 파이프라인 — 정량]       [financial-services-plugins — 정성]
  팩터 랭킹 → 후보 150종목  →  /earnings, /one-pager 자동 실행
                             →  어닝스 분석, 투자 thesis 생성
                             →  Agent F가 양쪽 결과 종합
                             ↓
                        최종 10~15종목 선정
```

### 2-2. AnalysisPlugin 추상 레이어

정성 분석 소스도 교체 가능하도록 추상화.  
프로토타입(무료)에서 실전(MCP 유료)으로 전환 시 구현체만 교체.

```python
# services/analysis_plugin.py

class BaseAnalysisPlugin:
    """정성 분석 추상 인터페이스"""
    def analyze_earnings(self, ticker: str, quarter: str) -> dict:
        raise NotImplementedError
    def get_one_pager(self, ticker: str) -> dict:
        raise NotImplementedError
    def run_comps(self, ticker: str) -> dict:
        raise NotImplementedError
    def get_investment_thesis(self, ticker: str) -> str:
        raise NotImplementedError

class FreeAnalysisPlugin(BaseAnalysisPlugin):
    """프로토타입 — Claude 자체 지식 + 공개 정보 기반
    MCP 없이 동작, API 키 불필요"""
    def analyze_earnings(self, ticker, quarter):
        # Claude가 공개 실적 정보로 분석
        ...
    def get_one_pager(self, ticker):
        # Claude가 공개 정보로 요약
        ...

class MCPAnalysisPlugin(BaseAnalysisPlugin):
    """실전 — financial-services-plugins MCP 연결
    FactSet / Morningstar / S&P Global 데이터 활용"""
    def analyze_earnings(self, ticker, quarter):
        # /earnings 커맨드 → MCP 데이터 기반 분석
        ...
    def get_one_pager(self, ticker):
        # /one-pager 커맨드 → MCP 데이터 기반 요약
        ...
```

### 2-3. 프로토타입 vs 실전 비교

| 항목 | 프로토타입 (FreeAnalysisPlugin) | 실전 (MCPAnalysisPlugin) |
|------|--------------------------------|--------------------------|
| 데이터 소스 | Claude 자체 지식 + 공개 정보 | FactSet, Morningstar, S&P Global |
| API 키 | 불필요 | 각 제공업체 구독 필요 |
| 분석 품질 | 참고용 | 전문 리서치 수준 |
| 비용 | 무료 | 제공업체별 유료 |
| 전환 방법 | `.env` FUNDAMENTAL_SOURCE 변경만 | — |

### 2-4. 슬래시 커맨드 활용 계획

```bash
# Claude Code에서 사용 가능한 커맨드 (플러그인 설치 후)
/comps AAPL           # 유사기업 비교 분석 → 밸류에이션 참고
/dcf MSFT             # DCF 모델 → 내재가치 추정
/earnings NVDA Q4     # 어닝스 분석 → 모멘텀 판단 보조
/one-pager TSLA       # 종목 원페이저 → 포트폴리오 모니터링 보조
```

### 2-5. 파이프라인에서의 위치

```
[P5 백테스트] 펀더멘털 스크리닝 단계

기존:
  500종목 → [ROE, D/E, FCF 룰베이스] → 150종목

개선 후:
  500종목
    → [ROE, D/E, FCF 룰베이스 필터]   ← 정량 (자동)
    → 150종목
    → [AnalysisPlugin.get_one_pager()]  ← 정성 자동화 (FreePlugin or MCPPlugin)
    → Agent F 종합 코멘트 (정량 + 정성)
    → 최종 10~15종목
```

---

## 3. 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│                   Frontend (Streamlit)                    │
│  [펀더멘털 필터] [백테스트 UI] [포트폴리오 모니터]         │
│  [Sharpe Contour] [감성분석] [종목 정성 리포트]           │
└─────────────────────┬────────────────────────────────────┘
                      │ REST API
┌─────────────────────▼────────────────────────────────────┐
│                   Backend (FastAPI)                       │
│  /api/fundamentals  /api/backtest  /api/portfolio         │
│  /api/signals  /api/sentiment  /api/analysis/{ticker}    │
└──┬──────────┬──────────────┬────────────────┬────────────┘
   │          │              │                │
[DataProvider] [StorageBackend] [AnalysisPlugin] [SentimentService]
yfinance       Parquet          FreePlugin        RSS+VADER
→ Alpaca       → PostgreSQL     → MCPPlugin       → NewsAPI+FinBERT
→ Polygon      → TimescaleDB    (FactSet 등)
→ Sharadar
```

---

## 4. 프로젝트 구조

```
quant_project/
├── CLAUDE.md
├── QUANT_PLATFORM_PRD.md
├── phase_status.json
├── resume_note.md
├── review_log.md
├── .env                          # API 키 (git 제외)
├── .gitignore                    # .env, .venv, data/raw/ 포함
├── config.py                     # 소스 교체 설정
│
├── services/
│   ├── data_provider.py          # DataProvider 추상 레이어
│   ├── storage.py                # StorageBackend 추상 레이어
│   ├── analysis_plugin.py        # AnalysisPlugin 추상 레이어 ← 신규
│   └── sentiment_service.py      # 감성분석 서비스
│
├── plugins/                      # financial-services-plugins ← 신규
│   ├── financial-analysis/       # 설치된 플러그인 (스킬 파일)
│   ├── equity-research/
│   └── README.md                 # 플러그인 버전 및 커스터마이징 기록
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── constituents/
│   └── checkpoints/
│
├── models/
│   ├── trained/
│   │   ├── v1_20260224/
│   │   └── latest -> v1_20260224/
│   ├── results/
│   └── model_registry.json
│
├── backend/
│   ├── main.py
│   └── routers/
│       ├── fundamentals.py
│       ├── backtest.py
│       ├── portfolio.py
│       ├── sentiment.py
│       └── analysis.py           # 정성 분석 엔드포인트 ← 신규
│
├── frontend/
│   └── pages/
│       ├── 1_fundamental_filter.py
│       ├── 2_backtest.py
│       ├── 3_portfolio_monitor.py
│       ├── 4_sentiment.py
│       └── 5_analysis_report.py  # 종목 정성 리포트 ← 신규
│
└── logs/
```

---

## 5. 팩터 설계

| 그룹 | 팩터 | ML 입력 |
|------|------|---------|
| 모멘텀 | ret_1m, ret_3m, mom_gap | ✅ |
| 변동성 | vol_20, downside_vol, natr, skew, kurt | ✅ |
| 유동성 | dol_vol, vol_zscore, mfi | ✅ |
| 추세/반전 | rsi, disparity_20, ma_cross | ✅ |
| 매크로 | VIX, TNX, DXY, 장단기금리차 | ❌ 레짐필터만 |
| 펀더멘털 | PER, PBR, EPS성장률, ROE, D/E | ❌ 스크리닝만 |

```python
target_next   = close.pct_change().shift(-1)   # 학습 타겟
target_smooth = target_next.rolling(5).mean()  # EDA 전용 — 학습 절대 사용 X
```

**팩터 유효성 기준**: IC_mean < 0.02 제거 / VIF > 10 제거 / 최종 10~15개

---

## 6. ML 모델

| 항목 | 설정 |
|------|------|
| Walk-Forward | 학습 3년 / 검증 6개월 / 스텝 3개월 |
| 후보 모델 | XGBoost, LightGBM, Ridge (베이스라인) |
| 튜닝 | Optuna n_trials=50, max_depth≤5, min_child_weight≥50 |
| 앙상블 | 상위 2개 모델 동일가중 |
| 버전 관리 | `models/trained/v{날짜}/` + `latest` 심볼릭 링크 + `model_registry.json` |

---

## 7. 백테스트

| 항목 | 설정 |
|------|------|
| 라이브러리 | vectorbt |
| 리밸런싱 | 월 1회 |
| 거래비용 | 슬리피지 0.1% + 수수료 0.05% |
| 포지션 | 변동성 역가중 |
| 스크리닝 | 500 → 150종목 (정량 룰베이스 + AnalysisPlugin 정성) |
| 파라미터 스윕 | ml_weight(0.3~0.7) × top_n(5~20) → Sharpe Contour |
| 레짐 조정 | VIX / 금리차 기반 포지션 크기 조정 |

---

## 8. Subagent 구성

```
[오케스트레이터]
├── Agent A  Data Engineer      데이터 수집 / 파이프라인
├── Agent B  Quant Researcher   팩터 분석 / 모델 설계
├── Agent C  ML Engineer        학습 / 튜닝 / 버전 관리
├── Agent D  Backend Developer  FastAPI / 추상 레이어 / analysis.py 라우터
├── Agent E  Frontend Developer Streamlit UI (5페이지)
├── Agent F  Quant Reviewer     편향 검증 (전 Phase 병렬 → review_log.md)
└── Agent G  Financial Analyst  정성 분석 실행  ← 신규
                                (AnalysisPlugin 호출, /earnings, /one-pager)
                                FreePlugin → MCPPlugin 전환 담당
```

---

## 9. 개발 Phase

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

---

### P0 — 환경 세팅
> 🧑 본인 직접 | ⏱ 30분~1시간

```bash
uv add xgboost lightgbm optuna vectorbt ta
uv add fastapi uvicorn streamlit plotly praw feedparser vaderSentiment
uv add sqlalchemy psycopg2-binary apscheduler python-dotenv

# financial-services-plugins 설치
claude plugin marketplace add anthropics/financial-services-plugins
claude plugin install financial-analysis@financial-services-plugins
claude plugin install equity-research@financial-services-plugins

# 설치된 플러그인 스킬 파일을 plugins/ 폴더로 복사 (로컬 커스터마이징용)
cp -r ~/.claude/plugins/financial-analysis plugins/
cp -r ~/.claude/plugins/equity-research plugins/

echo ".env" >> .gitignore
echo "data/raw/" >> .gitignore
```

**완료 확인**
- [ ] `python -c "import xgboost, streamlit, fastapi"` 오류 없음
- [ ] `claude plugin list` → financial-analysis, equity-research 확인
- [ ] `.env` 생성 및 보유 키 입력

---

### P1 — 데이터 파이프라인
> 🤖 Claude 자동 (Agent A + F) | ⏱ 1~3시간 | 🛋 자리 비워도 됨

```
data-pipeline skill 참고해서 다음을 수행해줘.
Agent A (Data Engineer)와 Agent F 병렬 실행.

[설계 원칙]
- services/data_provider.py: BaseDataProvider + YfinanceProvider 구현
  AlpacaProvider, PolygonProvider, SharadarProvider는 스텁으로만 생성
- services/storage.py: BaseStorage + ParquetStorage 구현
  PostgresStorage는 스텁으로만 생성
- 모든 키는 os.getenv() 사용

[작업]
1. S&P 500 historical constituents (2014~2024, 상장폐지 포함)
   → data/constituents/sp500_historical.csv

2. OHLCV 수집 (50종목 배치, 1초 간격)
   → logs/data_collection.log 실시간 기록
   → checkpoints/ohlcv_progress.json (중단 대비)
   → data/processed/ohlcv.parquet

3. FRED 매크로: VIX, DXY, TNX, T10Y2Y
   → data/processed/macro.parquet

4. phase_status.json P1_data → done
   Agent F: 데이터 품질 리포트 → review_log.md
```

**중단 후 재개**
```
checkpoints/ohlcv_progress.json 확인해서 미수집 종목만 이어서 수집해줘.
```

**🧑 본인 확인**
- [ ] `pd.read_parquet("data/processed/ohlcv.parquet").shape` 확인
- [ ] 상장폐지 종목 포함 여부 샘플 확인

---

### P2 — 팩터 생성 & 분석
> 🤖 Claude 자동 (Agent B + F) | ⏱ 30분~1시간 | 🛋 자리 비워도 됨

```
factor-analysis skill 참고해서 다음을 수행해줘.
Agent B (Quant Researcher)와 Agent F 병렬 실행.

1. ta 라이브러리로 전체 팩터 계산
   - target_next = t+1 수익률 (학습용)
   - target_smooth = 5일 평균 (EDA 전용, 학습 절대 사용 X)
   → data/processed/factors.parquet

2. IC (spearmanr) / VIF 검증
   → data/processed/selected_features.json
   → notebooks/02_factor_analysis.ipynb

3. phase_status.json P2_factor → done
   Agent F: 팩터 선택 타당성 → review_log.md
```

**🧑 본인 확인**
- [ ] selected_features.json 팩터 수 (10~15개) 확인
- [ ] IC_mean < 0.02 팩터 제거 확인

---

### P3 — 백엔드 뼈대 + 추상 레이어
> 🤖 Claude 자동 (Agent D + F) | ⏱ 30분~1시간 | 🛋 자리 비워도 됨

```
Agent D (Backend Developer)와 Agent F 병렬 실행.

[핵심: 추상 레이어 3개 모두 구현]

1. services/data_provider.py
   - BaseDataProvider 추상 클래스
   - YfinanceProvider 구현체
   - AlpacaProvider, PolygonProvider, SharadarProvider 스텁

2. services/storage.py
   - BaseStorage 추상 클래스
   - ParquetStorage 구현체
   - PostgresStorage 스텁

3. services/analysis_plugin.py   ← 신규
   - BaseAnalysisPlugin 추상 클래스
   - FreeAnalysisPlugin 구현체 (Claude 자체 분석, API 키 불필요)
   - MCPAnalysisPlugin 스텁 (financial-services-plugins MCP 연결용)
   config.py FUNDAMENTAL_SOURCE="plugin_free" → "plugin_mcp" 전환 가능

4. FastAPI 뼈대
   - 기존 엔드포인트 + GET /api/analysis/{ticker} 추가
   구현은 P6에서 채움

5. phase_status.json P3_backend_base → done
```

**🧑 본인 확인**
```bash
uvicorn backend.main:app --reload --port 8000
# /docs에서 /api/analysis/{ticker} 포함 확인
```

---

### P4 — ML 모델 학습
> 🤖 Claude 자동 (Agent B + C + F) | ⏱ 2~6시간 | 🛋 자리 비워도 됨

```
ml-training skill 참고해서 다음을 수행해줘.
Agent C (ML Engineer), Agent B, Agent F 병렬 실행.

1. Walk-Forward (학습 3년 / 검증 6개월 / 스텝 3개월)
   k-fold 절대 금지
   특성: selected_features.json 기준

2. 후보 모델: XGBoost, LightGBM, Ridge
   Optuna 튜닝 (n_trials=50)
   앙상블: 상위 2개 동일가중

3. 진행 기록
   → logs/training.log (스텝별)
   → checkpoints/wf_results/ (중단 대비)

4. 모델 저장
   → models/trained/v{날짜}/
   → models/trained/latest/ (심볼릭 링크)
   → model_registry.json 업데이트

5. phase_status.json P4_ml → done
   Agent F: 과적합 징후 (train/test 갭) → review_log.md
```

**중단 후 재개**
```
checkpoints/wf_results/ 확인해서 완료 스텝 이후부터 이어서 학습해줘.
```

**🧑 본인 확인**
- [ ] model_registry.json OOS IC 확인
- [ ] Train/Test IC 갭 0.05 이하

---

### P5 — 백테스트
> 🤖 Claude 자동 (Agent B + C + F) | ⏱ 30분~2시간 | 🛋 자리 비워도 됨

```
backtest skill 참고해서 다음을 수행해줘.
Agent B, Agent C, Agent G (Financial Analyst), Agent F 병렬 실행.

1. vectorbt 백테스트
   - 리밸런싱 월 1회, 슬리피지 0.1% + 수수료 0.05%
   - 포지션: 변동성 역가중

2. 펀더멘털 스크리닝 (개선된 2단계)
   [1단계 — 정량] ROE, D/E, FCF, 매출성장률 룰베이스 → 500 → 150종목
   [2단계 — 정성] Agent G가 FreeAnalysisPlugin.get_one_pager() 실행
                  150종목 원페이저 자동 생성 → Agent F 종합
                  → 최종 후보 선별

3. 매크로 레짐 조정 (VIX / 금리차)

4. 파라미터 스윕
   - ml_weight: 0.3~0.7 / top_n: 5~20
   → data/processed/sharpe_contour.json

5. 성과 지표
   - Sharpe, Sortino, MDD, Calmar, Hit Rate
   → models/results/backtest_summary.json

6. phase_status.json P5_backtest → done
   Agent F: 전략 강건성 + 정성/정량 일치도 평가 → review_log.md
```

**🧑 본인 확인**
- [ ] Contour에서 최적 영역 분포 확인 (sharp peak → 과적합)
- [ ] MDD -30% 초과 시 레짐 필터 강화
- [ ] 정성 분석 결과가 정량 랭킹과 심하게 괴리된 종목 검토

---

### P6 — 백엔드 완성
> 🤖 Claude 자동 (Agent D + G + F) | ⏱ 30분~1시간 | 🛋 자리 비워도 됨

```
Agent D, Agent G, Agent F 병렬 실행.

1. 기존 엔드포인트 실제 데이터 연결
   - /api/fundamentals, /api/backtest, /api/portfolio, /api/signals

2. /api/analysis/{ticker} 구현   ← 신규
   - FreeAnalysisPlugin.analyze_earnings() 호출
   - FreeAnalysisPlugin.get_one_pager() 호출
   - 결과를 data/processed/analysis_{ticker}.json 캐싱

3. services/sentiment_service.py
   - RSS (Yahoo Finance / Reuters) + feedparser
   - Reddit PRAW
   - VADER 감성 점수
   - TF-IDF top 10 키워드
   - APScheduler: 18:30 KST 일 1회

4. APScheduler 전체 파이프라인
   18:00 OHLCV 갱신
   18:10 팩터 재계산 + ML 신호 업데이트
   18:20 정성 분석 캐시 갱신 (변경 종목 위주)
   18:30 감성분석 갱신

5. phase_status.json P6_backend → done
```

**🧑 본인 확인**
```bash
uvicorn backend.main:app --reload --port 8000
# /api/analysis/AAPL 호출 → 분석 결과 JSON 확인
```

---

### P7 — 프론트엔드 (5페이지)
> 🤖 Claude 자동 (Agent E + F) | ⏱ 30분~1시간 | 🛋 자리 비워도 됨

```
Agent E (Frontend Developer)와 Agent F 병렬 실행. 5페이지 구축.

[페이지 1] 펀더멘털 필터
- ROE, D/E, FCF, 매출성장률, EPS성장률 슬라이더
- 필터 결과 종목 테이블
- /api/fundamentals 호출

[페이지 2] 백테스트 & 파라미터 최적화
- ml_weight × top_n Sharpe Contour (Plotly)
- 누적수익 라인차트 (전략 vs SPY)
- Sharpe, MDD, Calmar 카드
- /api/backtest 호출

[페이지 3] 포트폴리오 모니터
- 종목 테이블: 가격, 당일수익, ML신호, RSI, 감성점수
- 30초 자동 갱신
- 사이드바: review_log.md 최신 Agent F 코멘트
- /api/portfolio, /api/signals 호출

[페이지 4] 감성분석 피드
- ticker별 감성점수 바 차트 (-1~1)
- 최신 기사 헤드라인 + TF-IDF 키워드
- Reddit 키워드
- /api/sentiment 호출

[페이지 5] 종목 정성 리포트   ← 신규
- 종목 선택 → 원페이저 자동 생성 (FreePlugin / MCPPlugin)
- 어닝스 분석 요약
- ML 정량 신호 + 정성 분석 병렬 표시
- "MCP 고도화 시 더 정확한 데이터 제공" 안내 배너 표시
- /api/analysis/{ticker} 호출

5. phase_status.json P7_frontend → done
```

**🧑 본인 확인**
```bash
streamlit run frontend/app.py --server.port 8501
```
- [ ] 5페이지 모두 오류 없이 로딩
- [ ] 페이지 5에서 종목 선택 시 분석 결과 표시 확인

---

### P8 — 통합 테스트
> 🧑 본인 직접 판단 | ⏱ 반나절~1일 | 자리 비울 수 없음

```
[ ] Look-ahead bias 날짜 검증
    → 2020-03-01 기준: 모델이 그 이후 데이터 사용했는지 체크

[ ] Contour sharp peak 여부
    → "파라미터 범위 확장해서 재스윕해줘 (ml_weight 0.2~0.8, top_n 3~25)"

[ ] 포트폴리오 업종 편중
    → "섹터 분산 제약 추가해줘 (업종별 최대 30%)"

[ ] 정성/정량 결과 괴리 종목 확인
    → ML 상위 랭킹인데 FreePlugin 분석이 부정적이면 사유 검토

[ ] APScheduler 수동 1회 실행 테스트
    → "일일 갱신 파이프라인 수동으로 1회 실행해줘"

[ ] FreePlugin → MCPPlugin 전환 테스트 (선택)
    → .env FUNDAMENTAL_SOURCE=plugin_mcp 변경 후 /api/analysis/AAPL 재호출
```

---

## 10. 중단 · 재개

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

## 11. 데이터 소스 로드맵

### 프로토타입 — 완전 무료

| 항목 | 소스 | 비고 |
|------|------|------|
| OHLCV | yfinance | Rate limit 주의 |
| 매크로 | FRED API | — |
| 펀더멘털 | yfinance | PIT 보장 X |
| S&P500 구성종목 | Wikipedia 스크래핑 | 수동 보정 필요 |
| 정성 분석 | FreeAnalysisPlugin (Claude 자체) | 참고용 수준 |
| 뉴스 | Yahoo Finance / Reuters RSS | API 키 불필요 |
| 감성 엔진 | VADER | — |
| Storage | Parquet | — |

### 실전 전환 — 유료

| 단계 | 소스 | 비용 | 교체 방법 |
|------|------|------|-----------|
| 실전 v1 | Alpaca | ~$99/월 | `DATA_PROVIDER=alpaca` |
| 실전 v2 | Polygon.io | $29~199/월 | `DATA_PROVIDER=polygon` |
| 퀀트 고도화 | Sharadar | $50~/월 | `DATA_PROVIDER=sharadar` |
| 정성 고도화 | MCPAnalysisPlugin (FactSet 등) | 제공업체별 | `FUNDAMENTAL_SOURCE=plugin_mcp` |
| 감성 고도화 | NewsAPI Pro + FinBERT | $449/월 | `SENTIMENT_SOURCE=newsapi_finbert` |

---

## 12. financial-services-plugins MCP 전환 가이드 (실전 시)

```bash
# 1. .env에 MCP 제공업체 키 추가
FACTSET_API_KEY=your_key
FUNDAMENTAL_SOURCE=plugin_mcp

# 2. plugins/financial-analysis/.mcp.json 에서
#    사용할 제공업체 활성화 (나머지는 주석 처리)

# 3. MCPAnalysisPlugin 구현체 완성
> services/analysis_plugin.py의 MCPAnalysisPlugin을
  FactSet MCP 연결로 구현 완성해줘.
  .env의 FACTSET_API_KEY 사용.

# 4. config.py 자동 반영 확인
> FUNDAMENTAL_SOURCE=plugin_mcp 설정 후
  /api/analysis/AAPL 재호출해서 MCPPlugin 동작 확인해줘.
```

**MCP 제공업체별 특화 용도**

| 제공업체 | MCP URL | 주요 용도 |
|----------|---------|-----------|
| FactSet | `https://mcp.factset.com/mcp` | 실시간 재무 데이터, Comps |
| Morningstar | `https://mcp.morningstar.com/mcp` | 펀드/ETF 분석, 밸류에이션 |
| S&P Global | `https://kfinance.kensho.com/integrations/mcp` | 신용등급, 기업 프로파일 |
| MT Newswires | `https://vast-mcp.blueskyapi.com/mtnewswires` | 실시간 뉴스 (감성분석 고도화) |

---

## 13. 치트시트 (복붙용)

```bash
# 세션 시작
cd /workspaces/webapp-dev-trial/quant_project
source .venv/bin/activate
claude

# 이어서 진행
> phase_status.json 확인하고 다음 Phase 이어서 진행해줘

# 중단 전 정리
> 현재 상태 phase_status.json 업데이트하고 resume_note.md 정리해줘

# 정성 분석 테스트
> FreeAnalysisPlugin으로 AAPL 원페이저 생성해줘

# MCP 전환 (실전)
> FUNDAMENTAL_SOURCE=plugin_mcp 으로 MCPAnalysisPlugin 구현 완성해줘

# 소스 교체
> DATA_PROVIDER=alpaca 로 AlpacaProvider 구현 완성해줘

# 플러그인 슬래시 커맨드
/earnings AAPL Q4
/one-pager MSFT
/comps NVDA
```

---

## 14. 확장 로드맵 (v2)

| 기능 | 방법 | 우선순위 |
|------|------|---------|
| Alpaca 전환 | AlpacaProvider 구현 + `DATA_PROVIDER=alpaca` | 높 |
| MCPPlugin 전환 | MCPAnalysisPlugin 구현 + FactSet 구독 | 중 |
| PostgreSQL 전환 | PostgresStorage 구현 + `STORAGE_BACKEND=postgres` | 중 |
| Russell 1000 확장 | Sharadar 구독 + SharadarProvider 구현 | 중 |
| FinBERT 전환 | `SENTIMENT_SOURCE=newsapi_finbert` | 중 |
| 멀티팩터 최적화 | 리스크 기여도 기반 포트폴리오 최적화 | 높 |
| 실시간 알림 | Slack MCP 연동 → 리밸런싱 신호 푸시 | 중 |
| 자동 주문 연동 | Alpaca 브로커 API | 낮 |

---

*⚠️ 실전 운용 전 Sharadar(PIT 펀더멘털) 교체 필수*  
*버전: v4.0 | 2026-02-27*
