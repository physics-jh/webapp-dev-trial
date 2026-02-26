# QuantVision — 작업 전체 흐름 정리

> 작성일: 2026-02-26
> 목적: 지금까지 무슨 작업을 했고, 각 스크립트가 어떻게 연결되는지 파악하기 위한 문서
> 대상: 데이터 사이언스 배경 + 약간의 퀀트 지식 보유자

---

## 한 줄 요약

> **"S&P 500 주식 500개의 10년치 데이터를 모아서 → 가격 패턴을 수치화하고 → 머신러닝이 내일 오를 주식을 예측하게 훈련시키고 → 그 결과를 웹 API로 서비스한다"**

---

## 전체 구조 한눈에 보기

```
[원본 데이터]          [가공]              [예측]             [서비스]
   yfinance          팩터 계산           ML 모델              FastAPI
   FRED    ──────►  (가격 패턴을   ────► (오를 주식      ────► (웹에서
(주가·금리)           숫자로 정리)         순위 예측)           조회 가능)
                         │                   │
                    factors.parquet    models/trained/
                    (130만 행)           latest/
```

---

## Phase별 완료 현황

| Phase | 이름 | 상태 | 핵심 산출물 |
|-------|------|------|------------|
| P0 | 환경 세팅 | ✅ 완료 | 패키지 설치, `.gitignore` |
| P1 | 데이터 수집 | ✅ 완료 | `ohlcv.parquet`, `macro.parquet` |
| P2 | 팩터 계산 | ✅ 완료 | `factors.parquet`, `selected_features.json` |
| P3 | 백엔드 뼈대 | ✅ 완료 | FastAPI 16개 엔드포인트 |
| P4 | ML 학습 | 🔄 진행 중 | `models/trained/latest/` (학습 중) |
| P5 | 백테스트 | ⏳ 대기 | |
| P6 | 백엔드 완성 | ⏳ 대기 | |
| P7 | 프론트엔드 | ⏳ 대기 | |
| P8 | 통합 테스트 | ⏳ 대기 | |

---

## 스크립트 역할과 연결 관계

### 전체 파이프라인 흐름도

```
scripts/
├── fetch_constituents.py  ─────────────────────────────────► ①
├── fetch_ohlcv.py  ────────────────────────────────────────► ②
├── fetch_macro.py  ────────────────────────────────────────► ③
├── build_factors.py  (①②③ 결과를 받아서) ─────────────────► ④
└── train_model.py  (④ 결과를 받아서) ──────────────────────► ⑤

                                           ⑤ 완성된 모델
                                               │
                                    backend/main.py (FastAPI)
                                    └── /api/portfolio  (누가 오를지)
                                    └── /api/backtest   (과거 성과)
                                    └── /api/fundamentals (재무 필터)
                                    └── /api/sentiment  (뉴스 감성)
```

---

### 각 스크립트 상세 설명

#### ① `fetch_constituents.py` — "어떤 주식을 볼 것인가?"

```
역할  : S&P 500 구성 종목 목록 수집
입력  : Wikipedia 웹 스크래핑
출력  : data/constituents/sp500_tickers.csv (519종목)
특이점: 이미 상폐된 종목(Celgene, Activision 등 18개)도 포함
        → 생존편향 방지 (지금 살아남은 주식만 보면 결과가 좋게 왜곡됨)
```

#### ② `fetch_ohlcv.py` — "10년치 주가 데이터 수집"

```
역할  : 519종목 × 2014~2024년 일봉 OHLCV 다운로드
입력  : yfinance API (무료)
출력  : data/processed/ohlcv.parquet (2,767일 × 2,607열)
특이점: 50종목씩 묶어서 1초 간격으로 받음 (서버 차단 방지)
        중간에 끊겨도 체크포인트에서 이어서 재개 가능
```

> OHLCV = Open(시가) / High(고가) / Low(저가) / Close(종가) / Volume(거래량)

#### ③ `fetch_macro.py` — "시장 전체 환경 데이터 수집"

```
역할  : 시장 레짐 판단에 필요한 거시경제 지표 수집
입력  : yfinance (FRED API 키 없을 때 자동 폴백)
출력  : data/processed/macro.parquet (2,768행 × 4열)

수집 지표:
  VIXCLS  → VIX (공포지수): 높을수록 시장이 불안함
  DTWEXBGS→ DXY (달러 강세 지수)
  DGS10   → TNX (미국 10년 국채 금리)
  T10Y2Y  → 장단기금리차 (10년 - 2년): 음수면 경기침체 신호
```

#### ④ `build_factors.py` — "주가 패턴을 숫자로 만들기"

```
역할  : 475종목 × 10년 주가를 ML이 읽을 수 있는 숫자 패턴(팩터)으로 변환
입력  : ohlcv.parquet
출력  : data/processed/factors.parquet (1,306,183행)
        data/processed/selected_features.json (선택된 팩터 10개)
```

**최종 선택된 팩터 10개**

| 팩터 이름 | 뜻 | 계산 방법 |
|-----------|-----|---------|
| `disparity_20` | 20일 이격도 | 현재가 ÷ 20일 평균가 - 1 (평균에서 얼마나 멀어졌나) |
| `mom_gap` | 추세 강도 | 50일 평균 - 200일 평균 (단기가 장기보다 높으면 상승 추세) |
| `ret_1m` | 1개월 수익률 | 21거래일 전 대비 수익률 |
| `rsi` | 상대강도지수 | 0~100, 70 이상이면 과매수, 30 이하면 과매도 |
| `ma_cross` | 골든/데스크로스 | 50일선 > 200일선이면 1, 아니면 0 |
| `vol_zscore` | 거래량 이상치 | 오늘 거래량이 평소 대비 얼마나 튀었나 |
| `mfi` | 자금 흐름 지수 | 거래량 포함한 RSI (돈이 들어오는지 나가는지) |
| `dol_vol` | 달러 거래대금 | 가격 × 거래량의 20일 평균 (기업 크기 반영) |
| `downside_vol` | 하락 변동성 | 하락할 때만의 변동성 (손실 위험 측정) |
| `natr` | 정규화 ATR | 가격 대비 일일 진폭 (변동성 크기) |

**왜 14개에서 10개로 줄었나?**

- IC 검증: 각 팩터와 다음날 수익률의 상관관계 측정 → 너무 낮으면 제거
- VIF 검증: 팩터끼리 너무 비슷하면 중복이므로 제거 (vol_20이 VIF=64로 제거됨)

> **IC(Information Coefficient)**: 팩터 예측값과 실제 수익률의 순위 상관계수.
> 0이면 완전히 쓸모없고, 0.05면 뛰어난 팩터. 개별 팩터 0.01~0.02는 일봉에서 정상 범위.
> ML이 여러 팩터를 조합하면 더 강한 신호가 됩니다.

#### ⑤ `train_model.py` — "미래를 예측하는 모델 훈련" (현재 실행 중)

```
역할  : 팩터 데이터로 XGBoost / LightGBM / Ridge 3개 모델 훈련
입력  : factors.parquet + selected_features.json
출력  : models/trained/v1_YYYYMMDD_HHMM/  (모델 파일들)
        models/trained/latest/             (심볼릭 링크)
        models/model_registry.json         (버전 기록)
```

**핵심 설계 — Walk-Forward 검증**

```
일반적인 방법 (잘못됨):         Walk-Forward (올바름):
┌──────────────────────┐        ┌────────────────────────┐
│ 전체 데이터를 섞어서  │        │ 시간 순서 유지          │
│ train/test 분할       │   ──►  │ 학습: 2017~2020 (3년)  │
│ → 미래 데이터로       │        │ 검증: 2020~2020 (6개월)│
│   학습하는 버그 발생  │        │ 학습: 2018~2021 (3년)  │
└──────────────────────┘        │ 검증: 2021~2021 (6개월)│
                                │ ... (9스텝 반복)        │
                                └────────────────────────┘
```

> 주식 예측에서 미래 데이터를 학습에 사용하면 (look-ahead bias)
> 백테스트 결과는 좋아보이지만 실제로는 완전히 쓸모없는 모델이 됩니다.

**9개 Walk-Forward 윈도우 (현재 학습 중)**

```
[1] 2017~2020 학습 → 2020 하반기 검증 (코로나 충격 구간)
[2] 2017~2020 학습 → 2021 상반기 검증 (코로나 반등 구간)
[3] 2018~2021 학습 → 2021 하반기 검증
[4] 2018~2021 학습 → 2022 상반기 검증 (금리 인상 시작)
[5] 2019~2022 학습 → 2022 하반기 검증 (고금리 충격)
[6] 2019~2022 학습 → 2023 상반기 검증
[7] 2020~2023 학습 → 2023 하반기 검증 (AI 붐 시작)
[8] 2020~2023 학습 → 2024 상반기 검증
[9] 2021~2024 학습 → 2024 하반기 검증 (최근)
```

**앙상블**: 3개 모델 중 IC가 높은 2개를 50:50으로 조합

---

### 인프라 파일 (직접 수정 거의 없음)

#### `config.py` — "전체 설정의 중앙 제어판"

```python
DATA_PROVIDER   = "yfinance"   # ← 이것만 바꾸면 데이터 소스 전체 교체
STORAGE_BACKEND = "parquet"    # ← 이것만 바꾸면 DB 전체 교체
```

#### `services/data_provider.py` — "데이터 소스 교체 레이어"

```
현재: yfinance (무료, 프로토타입)
추후: Alpaca → Polygon → Sharadar 로 교체 예정
교체 시 config.py 한 줄만 수정하면 됨
```

#### `services/storage.py` — "저장소 교체 레이어"

```
현재: Parquet 파일 (로컬, 빠름)
추후: PostgreSQL → TimescaleDB 로 교체 예정
교체 시 config.py 한 줄만 수정하면 됨
```

---

## 백엔드 API 구조 (현재 실행 중: localhost:8000)

```
GET /health                      → 서버 살아있는지 확인
GET /docs                        → Swagger 자동 문서 (브라우저에서 테스트 가능)

GET /api/fundamentals/screen     → PER/PBR/ROE 기준으로 500종목 → 150종목으로 필터
GET /api/fundamentals/ticker/AAPL→ 특정 종목 재무 지표 조회

GET /api/backtest/summary        → 전략 성과 요약 (수익률, 샤프지수, 최대낙폭)
GET /api/backtest/sharpe-contour → 파라미터별 샤프지수 히트맵 데이터
GET /api/backtest/equity-curve   → 누적 수익률 시계열

GET /api/portfolio/current       → ML 모델이 추천하는 현재 포트폴리오
GET /api/portfolio/regime        → 현재 시장 레짐 (bull/bear/neutral)

GET /api/sentiment/feed          → 주요 종목 뉴스 + 감성점수
GET /api/sentiment/summary       → 전체 시장 감성 요약
GET /api/sentiment/reddit        → Reddit 투자 커뮤니티 감성
```

> 현재(P3)는 뼈대만 있고 모두 빈 값을 반환합니다.
> P6에서 실제 모델·데이터와 연결합니다.

---

## 데이터 흐름 상세 (숫자와 함께)

```
[원본]
  yfinance ──► 519종목 × 2,767일 = 약 143만 행의 주가 데이터
  FRED/yf  ──► VIX, DXY, TNX, T10Y2Y × 2,768일

[가공 후]
  ohlcv.parquet    : 2,767일 × 2,607열 (Close/High/Low/Open/Volume × 519종목)
  macro.parquet    : 2,768행 × 4열 (누락값 0개)
  factors.parquet  : 1,306,183행 × 14열 (475종목 × 약 2,750일 × 10팩터 + 타겟)

[모델 입력]
  X (특징) : 10개 팩터 컬럼
  y (정답) : target_next = 내일의 수익률
  (주의)   : target_smooth는 절대 y로 사용 금지 — EDA 시각화 전용
```

---

## 현재 실행 중인 프로세스

| 프로세스 | 포트/경로 | 상태 |
|---------|---------|------|
| FastAPI (uvicorn) | `:8000` | ✅ 실행 중 |
| ML 학습 (train_model.py) | `logs/train_model.log` | 🔄 진행 중 |

**학습 로그 실시간 확인:**
```bash
tail -f quant_project/logs/train_model.log
```

**API 문서 확인:**
```
https://[codespace-url]/docs
또는 VSCode 포트 탭 → 8000 → 브라우저 열기 → /docs
```

---

## 앞으로 남은 작업

```
P5 백테스트  : 훈련된 모델로 2014~2024 가상 투자 시뮬레이션
               → 얼마나 벌었는지, MDD(최대손실)는 얼마인지 계산

P6 백엔드 완성: API에 실제 데이터 연결
               → 펀더멘털 스크리닝, 감성분석(뉴스 RSS + VADER) 실제 작동

P7 프론트엔드 : Streamlit 대시보드
               → 슬라이더로 필터 조정, 차트로 시각화

P8 통합 테스트: look-ahead bias 없는지 날짜 검증
               → 과적합 여부, 업종 편중 확인
```

---

*이 문서는 작업 진행에 따라 자동 업데이트되지 않습니다. 주요 변경 시 수동으로 갱신하세요.*
