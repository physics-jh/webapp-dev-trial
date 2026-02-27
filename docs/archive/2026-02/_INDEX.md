# Archive Index — 2026-02

## quant_project (2026-02-27)

**QuantVision — S&P 500 ML 팩터 전략 + 웹 대시보드 v4.0**

| 항목 | 값 |
|------|-----|
| PDCA Match Rate | 96% |
| 백테스트 CAGR | 20.0% |
| Sharpe Ratio | 0.795 |
| MDD | -32.7% |
| WF IC | 0.0224 |
| 개발 기간 | 2026-02-25 ~ 2026-02-27 |
| 아카이브 경로 | `docs/archive/2026-02/quant_project/` |

### 파일 목록
- `quant_project.prd.md` — PRD v4.0
- `quant_project.analysis.md` — 갭 분석 (93%)
- `quant_project.report.md` — PDCA 완료 리포트
- `changelog.md` — 버전 이력

### 주요 특징
- AnalysisPlugin 추상 레이어 (FreePlugin → MCPPlugin 전환 가능)
- FastAPI 17개 엔드포인트 + Streamlit 5페이지
- APScheduler 18:00~18:30 KST 일일 갱신 파이프라인
- Walk-Forward 검증 (Look-ahead Bias 없음 — 5/5 ✅)

---

## ui-strategy-improvement (2026-02-27)

**QuantVision UI·전략 통합 고도화 v4.1**

| 항목 | 값 |
|------|-----|
| PDCA Match Rate | 93% |
| 신규 파일 | 2개 (ai_advisor.py, advisor.py) |
| 수정 파일 | 8개 |
| 추가 코드량 | +620줄 |
| 개발 기간 | 2026-02-27 |
| 아카이브 경로 | `docs/archive/2026-02/ui-strategy-improvement/` |

### 파일 목록
- `ui-strategy-improvement.plan.md` — Plan 문서
- `ui-strategy-improvement.analysis.md` — 갭 분석 (93%)
- `ui-strategy-improvement.report.md` — PDCA 완료 리포트

### 주요 구현 내용
- app.py GitHub 다크테마 + 6단계 워크플로우 스테퍼 + 홈 대시보드
- 백테스트 3D Sharpe Surface (ml_weight × rule_weight × Sharpe)
- SPY 벤치마크 누적수익 차트 정상 표시
- 감성 통합: `adjusted_signal = signal × (1 + sentiment_weight × sentiment)`
- AI 어드바이저: Claude Haiku 실시간 + 폴백 템플릿 (API 키 불필요)
- 4개 페이지 AI 해설 패널 (pages/1, 2, 3, 4)
