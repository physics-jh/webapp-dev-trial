"""
페이지 2: 백테스트 & 파라미터 최적화 v2
- ML×룰베이스 3D Sharpe Surface (go.Surface)
- 누적수익 vs SPY 벤치마크
- AI 해설 패널
"""

import json
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="백테스트", layout="wide")

# ── 글로벌 CSS (앱과 동일한 다크테마) ─────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0e1117; color: #e6edf3; }
[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
p, [data-testid="stMarkdownContainer"] p { color: #e6edf3 !important; }
.qv-hint { background:#1c2128; border-left:3px solid #1f6feb; border-radius:0 6px 6px 0;
           padding:10px 14px; font-size:0.85rem; color:#c9d1d9; margin:8px 0; }
.qv-section-header { font-size:1.05rem; font-weight:600; color:#e6edf3;
                     border-left:3px solid #238636; padding-left:10px; margin:20px 0 12px 0; }
[data-testid="stExpander"] summary { color: #e6edf3 !important; }
</style>
""", unsafe_allow_html=True)

st.title("2. 백테스트 & 파라미터 최적화")
st.markdown('<div class="qv-hint">📌 ML 신호와 룰베이스 신호의 혼합 비율(ml_weight × rule_weight)에 따른 Sharpe 곡면을 확인하세요. <b>경사가 완만하고 안정적으로 높은 영역</b>이 실전에서 신뢰도 높은 파라미터입니다.</div>', unsafe_allow_html=True)


def _get(endpoint: str, **params):
    r = requests.get(f"{API}{endpoint}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _ai_insight(context: dict) -> str:
    try:
        r = requests.post(f"{API}/api/advisor/insight",
                          json={"page": "backtest", "context": context}, timeout=15)
        r.raise_for_status()
        return r.json().get("insight", "")
    except Exception:
        return ""


# ── 성과 지표 카드 ─────────────────────────────────────────────
try:
    summary = _get("/api/backtest/summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("CAGR",    f"{summary['cagr']*100:.1f}%")
    col2.metric("Sharpe",  f"{summary['sharpe']:.3f}")
    col3.metric("Sortino", f"{summary.get('sortino', 0):.3f}" if summary.get("sortino") else "N/A")
    col4.metric("MDD",     f"{summary['max_drawdown']*100:.1f}%",
                delta=f"{'목표달성 ✅' if summary['max_drawdown'] >= -0.30 else '목표미달 ⚠️'}")
    col5.metric("승률",    f"{summary['win_rate']*100:.1f}%")
    st.caption(f"기간: {summary['start_date']} ~ {summary['end_date']}")
except Exception as e:
    st.warning(f"백테스트 요약 로드 실패: {e}")
    summary = {}

st.divider()

# ── 3D Sharpe Surface (ML × 룰베이스 × Sharpe) ─────────────────
st.markdown('<div class="qv-section-header">3D Sharpe Surface — ML 가중치 × 룰베이스 가중치</div>', unsafe_allow_html=True)
st.markdown('<div class="qv-hint">경사가 <b>완만하고 넓게 높은 플래토(plateau)</b>를 찾으세요. 날카로운 피크(sharp peak)는 과적합 신호입니다.</div>', unsafe_allow_html=True)

try:
    contour = _get("/api/backtest/sharpe-contour")
    if contour:
        df_c = pd.DataFrame(contour)

        if "rule_weight" in df_c.columns and df_c["rule_weight"].nunique() > 1:
            # ── 신규: ml_weight × rule_weight 3D Surface ──────────────
            pivot = df_c.pivot_table(index="rule_weight", columns="ml_weight", values="sharpe")
            fig3d = go.Figure(data=[go.Surface(
                z=pivot.values,
                x=pivot.columns.tolist(),   # ml_weight
                y=pivot.index.tolist(),      # rule_weight
                colorscale="RdYlGn",
                colorbar=dict(title="Sharpe", thickness=15),
                hovertemplate="ML가중치: %{x:.1f}<br>룰베이스가중치: %{y:.1f}<br>Sharpe: %{z:.3f}<extra></extra>",
            )])
            fig3d.update_layout(
                scene=dict(
                    xaxis_title="ML 가중치 (ml_weight)",
                    yaxis_title="룰베이스 가중치 (rule_weight)",
                    zaxis_title="Sharpe Ratio",
                    bgcolor="#0e1117",
                    xaxis=dict(backgroundcolor="#161b22", gridcolor="#30363d"),
                    yaxis=dict(backgroundcolor="#161b22", gridcolor="#30363d"),
                    zaxis=dict(backgroundcolor="#161b22", gridcolor="#30363d"),
                ),
                paper_bgcolor="#0e1117",
                font=dict(color="#e6edf3"),
                height=520,
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig3d, use_container_width=True)
            st.caption("• X축: ML 모델 신호 가중치 | Y축: 룰베이스(모멘텀+저변동성) 신호 가중치 | Z축: Sharpe Ratio")
            st.caption("• 두 가중치 합은 정규화되므로 절대값보다 비율이 중요합니다.")
        else:
            # ── 레거시 폴백: ml_weight × top_n 3D Surface ──────────────
            pivot = df_c.pivot_table(index="top_n", columns="ml_weight", values="sharpe")
            fig3d = go.Figure(data=[go.Surface(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                colorscale="RdYlGn",
                colorbar=dict(title="Sharpe", thickness=15),
                hovertemplate="ML가중치: %{x:.1f}<br>종목수: %{y}<br>Sharpe: %{z:.3f}<extra></extra>",
            )])
            fig3d.update_layout(
                scene=dict(
                    xaxis_title="ML 가중치",
                    yaxis_title="포지션 수 (top_n)",
                    zaxis_title="Sharpe Ratio",
                    bgcolor="#0e1117",
                ),
                paper_bgcolor="#0e1117",
                font=dict(color="#e6edf3"),
                height=500,
            )
            st.plotly_chart(fig3d, use_container_width=True)
            st.caption("⚠️ 룰베이스 스윕 데이터 없음 — 백테스트 재실행 후 2D(ML × 룰베이스) 3D Surface 활성화됩니다.")
    else:
        st.info("파라미터 스윕 데이터 없음 (run_backtest.py 실행 필요)")
except Exception as e:
    st.warning(f"3D Surface 로드 실패: {e}")

st.divider()

# ── 누적 수익률 — 전략 vs SPY ─────────────────────────────────
st.markdown('<div class="qv-section-header">누적 수익률 — 전략 vs SPY 벤치마크</div>', unsafe_allow_html=True)
try:
    equity = _get("/api/backtest/equity-curve")
    if equity.get("dates"):
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=equity["dates"], y=equity["strategy"],
            name="전략", line=dict(color="#4c9be8", width=2.5)
        ))
        if equity.get("benchmark") and any(v for v in equity["benchmark"] if v):
            fig_eq.add_trace(go.Scatter(
                x=equity["dates"], y=equity["benchmark"],
                name="SPY (Buy & Hold)",
                line=dict(color="#8b949e", width=1.5, dash="dot")
            ))
            # Alpha 영역 표시
            fig_eq.add_trace(go.Scatter(
                x=equity["dates"] + equity["dates"][::-1],
                y=equity["strategy"] + equity["benchmark"][::-1],
                fill="toself",
                fillcolor="rgba(76,155,232,0.08)",
                line=dict(color="rgba(255,255,255,0)"),
                showlegend=False,
                name="Alpha 영역",
            ))
        fig_eq.add_hline(y=1.0, line_dash="dash", line_color="#30363d",
                         annotation_text="기준선 (원금)", annotation_position="bottom right")
        fig_eq.update_layout(
            yaxis_title="누적 수익률 (시작=1.0)",
            xaxis_title="날짜",
            height=420,
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e6edf3"),
            legend=dict(orientation="h", y=-0.2),
            xaxis=dict(gridcolor="#21262d"),
            yaxis=dict(gridcolor="#21262d"),
        )
        st.plotly_chart(fig_eq, use_container_width=True)
    else:
        st.info("누적 수익률 데이터 없음 (run_backtest.py 실행 필요)")
except Exception as e:
    st.warning(f"누적 수익률 로드 실패: {e}")

st.divider()

# ── 파라미터 최적화 과정 ───────────────────────────────────────
st.markdown('<div class="qv-section-header">파라미터 최적화 과정</div>', unsafe_allow_html=True)

try:
    opt = _get("/api/backtest/optimal-params", metric="sharpe", top_k=5)
    meta     = opt["metadata"]
    profiles = opt["profiles"]
    top_k    = opt["top_k"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("평가 조합 수", f"{meta['total_combos']}개")
    m2.metric("탐색 ml_weight",
              f"{meta['param_grid']['ml_weight'][0]}~{meta['param_grid']['ml_weight'][-1]}")
    if "rule_weight" in meta.get("param_grid", {}):
        m3.metric("탐색 rule_weight",
                  f"{meta['param_grid']['rule_weight'][0]}~{meta['param_grid']['rule_weight'][-1]}")
    else:
        m3.metric("탐색 top_n",
                  f"{meta['param_grid']['top_n'][0]}~{meta['param_grid']['top_n'][-1]}")
    m4.metric("평가 기간", meta["evaluation_period"])

    # Sharpe vs MDD 산점도
    all_contour = _get("/api/backtest/sharpe-contour")
    if all_contour:
        df_sc = pd.DataFrame(all_contour)
        cur_sharpe = summary.get("sharpe", 0)
        cur_mdd    = summary.get("max_drawdown", 0)

        fig_sc = go.Figure()
        hover_text = [
            f"ml={r.get('ml_weight',0):.1f}, rb={r.get('rule_weight',r.get('top_n',0))}"
            for _, r in df_sc.iterrows()
        ]
        if "mdd" in df_sc.columns:
            fig_sc.add_trace(go.Scatter(
                x=df_sc["sharpe"], y=df_sc["mdd"],
                mode="markers+text",
                text=hover_text,
                textposition="top center",
                textfont=dict(size=8, color="#8b949e"),
                marker=dict(size=9, color="#4c9be8", opacity=0.8),
                name="파라미터 조합",
                hovertemplate="Sharpe: %{x:.3f}<br>MDD: %{y:.1%}<br>%{text}<extra></extra>",
            ))
            fig_sc.add_trace(go.Scatter(
                x=[cur_sharpe], y=[cur_mdd],
                mode="markers+text", text=["현재 ★"],
                textposition="bottom right",
                textfont=dict(size=11, color="#f85149"),
                marker=dict(size=16, color="#f85149", symbol="star"),
                name="현재 설정",
            ))
            profile_meta = {
                "high_sharpe": ("gold", "◆ HIGH SHARPE"),
                "balanced":    ("#3fb950", "◆ BALANCED"),
                "low_risk":    ("#bc8cff", "◆ LOW RISK"),
            }
            for pname, (pcolor, plabel) in profile_meta.items():
                pdata = profiles.get(pname, {})
                if pdata.get("mdd") is not None:
                    fig_sc.add_trace(go.Scatter(
                        x=[pdata["sharpe"]], y=[pdata["mdd"]],
                        mode="markers+text", text=[plabel],
                        textposition="top left",
                        textfont=dict(size=9),
                        marker=dict(size=12, color=pcolor, symbol="diamond"),
                        name=plabel,
                    ))

        fig_sc.update_layout(
            xaxis_title="Sharpe Ratio (높을수록 좋음 →)",
            yaxis_title="MDD (덜 부정적일수록 좋음 ↑)",
            yaxis_tickformat=".0%",
            height=380,
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e6edf3"),
            legend=dict(orientation="h", y=-0.25),
            xaxis=dict(gridcolor="#21262d"),
            yaxis=dict(gridcolor="#21262d"),
        )
        fig_sc.add_vline(x=0.80, line_dash="dash", line_color="#30363d",
                          annotation_text="Sharpe 0.80 목표", annotation_position="top right",
                          annotation_font_color="#8b949e")
        fig_sc.add_hline(y=-0.30, line_dash="dash", line_color="#30363d",
                          annotation_text="MDD -30% 목표", annotation_position="bottom right",
                          annotation_font_color="#8b949e")
        st.plotly_chart(fig_sc, use_container_width=True)

    # 프로필 3개 카드
    c1, c2, c3 = st.columns(3)
    hs = profiles["high_sharpe"]
    ba = profiles["balanced"]
    lr = profiles["low_risk"]
    for col, label, bg, data in [
        (c1, "🚀 HIGH SHARPE", "#1a4731", hs),
        (c2, "⚖️ BALANCED",    "#1c2128", ba),
        (c3, "🛡️ LOW RISK",   "#1c1a30", lr),
    ]:
        rb_label = f"rule_w={data.get('rule_weight', data.get('top_n','?'))}"
        col.markdown(f"""
        <div style="background:{bg};border:1px solid #30363d;border-radius:10px;padding:14px;">
            <div style="font-weight:700;color:#e6edf3;margin-bottom:8px;">{label}</div>
            <div style="font-size:0.78rem;color:#8b949e;">ml_weight={data['ml_weight']} | {rb_label}</div>
            <hr style="border-color:#30363d;margin:8px 0;">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="color:#8b949e;font-size:0.8rem;">Sharpe</span>
                <span style="color:#3fb950;font-weight:700;">{data['sharpe']:.3f}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="color:#8b949e;font-size:0.8rem;">CAGR</span>
                <span style="color:#e6edf3;">{data['cagr']*100:.1f}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <span style="color:#8b949e;font-size:0.8rem;">MDD</span>
                <span style="color:#f85149;">{data['mdd']*100:.1f}%</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("전체 최적화 결과 (상위 5개 조합 상세)"):
        df_top = pd.DataFrame(top_k)
        df_top["sharpe"] = df_top["sharpe"].map(lambda x: f"{x:.4f}")
        df_top["cagr"]   = df_top["cagr"].map(lambda x: f"{x*100:.1f}%")
        df_top["mdd"]    = df_top["mdd"].map(lambda x: f"{x*100:.1f}%")
        if "score" in df_top.columns:
            df_top["score"] = df_top["score"].map(lambda x: f"{x:.4f}")
        st.dataframe(df_top, use_container_width=True, hide_index=True)

except Exception as e:
    st.warning(f"파라미터 최적화 결과 로드 실패: {e}")

st.divider()

# ── MDD 개선 전후 비교 ────────────────────────────────────────
st.markdown('<div class="qv-section-header">MDD 개선 전후 비교</div>', unsafe_allow_html=True)

BASELINE_PATH = os.path.join(os.path.dirname(__file__), "../../models/results/baseline_summary.json")
CURRENT_PATH  = os.path.join(os.path.dirname(__file__), "../../data/processed/backtest_summary.json")

try:
    with open(BASELINE_PATH) as f:
        baseline = json.load(f)
    with open(CURRENT_PATH) as f:
        current = json.load(f)

    rows = [
        {"지표": "CAGR",   "기존": f"{baseline['cagr']*100:.1f}%",
         "개선 후": f"{current['cagr']*100:.1f}%",    "목표": "≥ 18.0%",
         "_ok": current["cagr"] >= 0.18},
        {"지표": "Sharpe", "기존": f"{baseline['sharpe']:.3f}",
         "개선 후": f"{current['sharpe']:.3f}",        "목표": "≥ 0.80",
         "_ok": current["sharpe"] >= 0.80},
        {"지표": "MDD",    "기존": f"{baseline['max_drawdown']*100:.1f}%",
         "개선 후": f"{current['max_drawdown']*100:.1f}%", "목표": "≤ -30.0%",
         "_ok": current["max_drawdown"] >= -0.30},
        {"지표": "승률",   "기존": f"{baseline['win_rate']*100:.1f}%",
         "개선 후": f"{current['win_rate']*100:.1f}%",  "목표": "—", "_ok": True},
    ]

    df_cmp = pd.DataFrame(rows)
    df_cmp["달성"] = df_cmp["_ok"].map({True: "✅", False: "❌"})
    st.dataframe(df_cmp.drop(columns=["_ok"]), use_container_width=True, hide_index=True)

    all_ok = all(r["_ok"] for r in rows)
    if all_ok:
        st.success("모든 목표 달성 ✅")
    else:
        msgs = [r["지표"] + " 목표 미달" for r in rows if not r["_ok"]]
        st.warning(" | ".join(msgs))

except FileNotFoundError:
    st.info("비교 파일 없음 (백테스트 재실행 필요)")
except Exception as e:
    st.warning(f"비교 로드 실패: {e}")

st.divider()

# ── AI 해설 패널 ──────────────────────────────────────────────
st.markdown('<div class="qv-section-header">🤖 AI 퀀트 어드바이저 해설</div>', unsafe_allow_html=True)
st.markdown('<div class="qv-hint">현재 성과 지표와 최적 파라미터를 분석하여 전략 권고를 제공합니다.</div>', unsafe_allow_html=True)

if st.button("AI 해설 생성", key="bt_ai_backtest"):
    with st.spinner("분석 중..."):
        ctx = {
            "sharpe": summary.get("sharpe", 0),
            "mdd": summary.get("max_drawdown", 0),
            "cagr": summary.get("cagr", 0),
            "win_rate": summary.get("win_rate", 0),
        }
        insight = _ai_insight(ctx)
        if insight:
            st.info(insight)
        else:
            st.caption("AI 해설을 생성할 수 없습니다. ANTHROPIC_API_KEY를 .env에 설정하세요.")
