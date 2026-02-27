# QuantVision — 핵심 지침

> 스킬: `/env-setup` | `/troubleshoot` | `/walk-forward` | `/resume` | `/prd`

---

## 환경

| 항목 | 값 |
|------|-----|
| 가상환경 | `quant_project/.venv` (Python 3.12.1) |
| 패키지 관리 | `uv` — `export PATH="$HOME/.local/bin:$PATH"` |
| 환경변수 | `.env` + `python-dotenv` — `os.getenv()` 필수 사용 |
| FastAPI 재시작 | `cd quant_project && nohup .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 > logs/uvicorn.log 2>&1 &` |

---

## 절대 원칙 (위반 금지)

1. **API 키 코드 직접 작성 금지** → 반드시 `os.getenv()` 사용
2. **DataProvider / StorageBackend는 추상 레이어 통해서만 접근**
3. **k-fold 금지** → Walk-Forward만 사용 (`/walk-forward`)
4. **`target_smooth`는 EDA 전용** → 학습 타겟으로 절대 사용 금지
5. **데이터 소스 교체 시 `config.py`만 수정** → 상위 레이어 수정 금지

---

## Walk-Forward 핵심 규칙

- `(date, ticker)` 패널에 `TimeSeriesSplit` 직접 적용 금지 → look-ahead bias
- 고유 날짜 배열에만 `TimeSeriesSplit` 적용 → 날짜 범위로 패널 슬라이싱
- 분할: 학습 3년 / 검증 6개월 | 스케일러: train `.fit_transform()`, val `.transform()` 전용

---

## 설계 구조

```
services/data_provider.py   ← DataProvider 추상 레이어
services/storage.py         ← StorageBackend 추상 레이어
services/analysis_plugin.py ← AnalysisPlugin (FreePlugin / MCPPlugin)
config.py                   ← DATA_PROVIDER / STORAGE_BACKEND / FUNDAMENTAL_SOURCE
.env                        ← API 키 (git 커밋 절대 금지)
```

---

## Phase 현황 (2026-02-27)

P0~P8 모두 완료. 추가 작업 시 `phase_status.json` 업데이트 후 진행.
