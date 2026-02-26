# CLAUDE.md — 환경설정, 문제해결과정기록

## 프로젝트 구조

```
/workspaces/webapp-dev-trial/
├── CLAUDE.md
├── README.md
└── quant_project/
    ├── .venv/              # Python 가상환경 (Python 3.12.1)
    └── test.ipynb          # 환경 검증 노트북
```

## 환경 설정

- **패키지 관리**: `uv` (`~/.local/bin/uv`)
- **가상환경 경로**: `quant_project/.venv`
- **Python 버전**: 3.12.1

### PATH 설정 (필수)

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 패키지 설치

```bash
cd quant_project
uv pip install <패키지명>
```

## Jupyter 커널

`.venv`를 Jupyter 커널로 등록:

```bash
.venv/bin/python -m ipykernel install --user --name quant-venv --display-name "Python (quant .venv)"
```

등록된 커널 확인:

```bash
jupyter kernelspec list
```

VSCode에서 노트북 실행 시 커널을 **`Python (quant .venv)`** 로 선택해야 패키지를 정상 인식.

## 노트북 자동 실행

```bash
cd quant_project
.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=python3 <노트북명>.ipynb
```

## 주요 설치 패키지

| 분류 | 패키지 |
|------|--------|
| 데이터 처리 | pandas, numpy |
| 금융 데이터 | yfinance |
| 머신러닝 | scikit-learn, statsmodels |
| 시각화 | matplotlib, seaborn, plotly |
| 한글 폰트 | koreanize-matplotlib |
| 웹 프레임워크 | streamlit, fastapi, uvicorn |
| Jupyter | ipykernel, nbconvert, nbclient, nbformat |
| 기타 | setuptools (Python 3.12 distutils 대체) |

## 알려진 이슈 및 해결책

### `ModuleNotFoundError: No module named 'pandas'`
- **원인**: 노트북 커널이 `.venv`가 아닌 시스템 Python 사용
- **해결**: VSCode에서 커널을 `Python (quant .venv)` 로 변경

### `ModuleNotFoundError: No module named 'distutils'`
- **원인**: Python 3.12에서 `distutils` 표준 라이브러리 제거
- **해결**: `uv pip install setuptools`

### `ValueError: Mime type rendering requires nbformat>=4.2.0`
- **원인**: `nbformat` 미설치
- **해결**: `uv pip install nbformat`

### plotly가 노트북에서 렌더링 안 됨
- **원인**: `nbformat` 미설치
- **해결**: `uv pip install nbformat nbclient`

### Pylance "가져오기를 확인할 수 없습니다" 경고 (numpy, pandas, ta 등)
- **원인**: `python.defaultInterpreterPath`만 설정해도 Pylance가 venv site-packages를 못 찾는 경우 발생
- **실행에는 무관** — `.venv/bin/python script.py`로 실행 시 정상 동작
- **해결**: `.vscode/settings.json`에 `python.analysis.extraPaths` 추가
  ```json
  {
    "python.defaultInterpreterPath": "/workspaces/webapp-dev-trial/quant_project/.venv/bin/python",
    "python.analysis.extraPaths": [
      "/workspaces/webapp-dev-trial/quant_project/.venv/lib/python3.12/site-packages",
      "/workspaces/webapp-dev-trial/quant_project"
    ]
  }
  ```
- 설정 후 **VSCode 재시작** 또는 `Ctrl+Shift+P` → "Python: Restart Language Server"


# QuantVision — CLAUDE.md

> Claude Code가 매 세션 자동으로 읽는 프로젝트 컨텍스트 파일  
> 상세 스펙은 [@QUANT_PLATFORM_PRD.md](./QUANT_PLATFORM_PRD.md) 참조

---

## 환경

- Python 가상환경: `.venv` (`source .venv/bin/activate`)
- 패키지 관리: `uv`
- 환경변수: `.env` + `python-dotenv` (`os.getenv()` 사용)
- Storage: Parquet (`data/processed/`) → 추후 PostgreSQL 전환 예정

---

## 절대 원칙 (위반 금지)

1. **API 키 코드 직접 작성 금지** → 반드시 `os.getenv()` 사용
2. **DataProvider / StorageBackend는 추상 레이어 통해서만 접근**
3. **k-fold 금지** → Walk-Forward만 사용 (아래 분할 전략 참조)
4. **target_smooth는 EDA 전용** → 학습 타겟으로 절대 사용 금지
5. **데이터 소스 교체 시 `config.py`만 수정** → 상위 레이어 수정 금지

---

## Walk-Forward 분할 전략

`(date, ticker)` 패널 데이터에 `TimeSeriesSplit`을 직접 적용하면
행 기준으로 쪼개져 날짜가 섞이는 look-ahead bias가 발생한다.
**올바른 방법: 고유 날짜 배열에만 `TimeSeriesSplit` 적용 → 날짜 범위로 패널 슬라이싱.**

```python
from sklearn.model_selection import TimeSeriesSplit

# 1. 고유 날짜 배열에만 적용
dates = df.index.get_level_values("date").unique().sort_values()
tscv  = TimeSeriesSplit(
    n_splits=n_splits,
    max_train_size=252 * 3,   # 학습 3년 고정 롤링 윈도우
    test_size=126,             # 검증 6개월
    gap=0,                     # 학습/검증 간격 없음 (연속)
)

# 2. 날짜 집합으로 패널 슬라이싱 (look-ahead bias 구조적 차단)
for tr_idx, va_idx in tscv.split(dates):
    tr_dates = dates[tr_idx]
    va_dates = dates[va_idx]
    tr = df[df.index.get_level_values("date").isin(tr_dates)]
    va = df[df.index.get_level_values("date").isin(va_dates)]

# 3. 스케일링: train 통계만으로 fit (val에 fit 금지)
scaler = RobustScaler()
X_tr   = scaler.fit_transform(X_tr)
X_va   = scaler.transform(X_va)    # fit 절대 금지
```

구현 파일: `scripts/train_model.py` → `make_wf_splits()` + `slice_panel()`

---

## 설계 구조

```
services/data_provider.py   ← DataProvider 추상 레이어
services/storage.py         ← StorageBackend 추상 레이어
config.py                   ← DATA_PROVIDER / STORAGE_BACKEND 설정
.env                        ← API 키 (git 커밋 금지)
```

---

## Phase 진행 규칙

- 작업 전: `phase_status.json` 확인 → 완료된 Phase 건너뜀
- 작업 후: `phase_status.json` 즉시 업데이트
- 장시간 작업: `data/checkpoints/`에 중간 결과 저장, `logs/`에 실시간 기록
- **Agent F는 전 Phase 병렬 실행** → 결과를 `review_log.md`에 기록

---

## 중단 · 재개

```
# 재개
phase_status.json 확인하고 마지막 완료 Phase 이후부터 이어서 진행해줘.

# 중단 전
현재 상태를 phase_status.json에 업데이트하고 resume_note.md 정리해줘.
```

---

## 상세 PRD

@QUANT_PLATFORM_PRD.md
