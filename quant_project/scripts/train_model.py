"""
P4-C: Walk-Forward + Optuna ML 학습

분할 전략:
  sklearn.model_selection.TimeSeriesSplit을 고유 날짜 배열에 적용 후
  해당 날짜 범위로 (date, ticker) 패널 데이터를 슬라이싱.
  → look-ahead bias 구조적 방지 + sklearn 검증된 분할 로직 재사용

PRD 설정:
  Walk-Forward : 학습 3년 / 검증 6개월 / 스텝 3개월
  후보 모델    : XGBoost, LightGBM, Ridge (베이스라인)
  튜닝         : Optuna n_trials=50, max_depth≤5, min_child_weight≥50
  앙상블       : 상위 2개 모델 동일가중
  저장         : models/trained/v{날짜}_{시각}/ + latest 심볼릭 링크
  버전 추적    : model_registry.json
"""

import os, sys, json, logging, warnings, pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── 경로 ────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models" / "trained"
REG_PATH   = BASE_DIR / "models" / "model_registry.json"
CKPT_DIR   = BASE_DIR / "data" / "checkpoints" / "wf_results"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
CKPT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Walk-Forward 파라미터 ────────────────────────────────────
# 거래일 기준: 1년 ≈ 252일
TRADING_DAYS_YEAR  = 252
WF_TRAIN_DAYS      = TRADING_DAYS_YEAR * 3    # 학습 3년
WF_VAL_DAYS        = TRADING_DAYS_YEAR // 2   # 검증 6개월
WF_GAP_DAYS        = 0                         # 학습 끝 ~ 검증 시작 간격 (0: 연속)
N_OPTUNA_TRIALS    = 50


# ─── 1. 데이터 로드 ───────────────────────────────────────────

def load_features() -> tuple[pd.DataFrame, list[str]]:
    with open(BASE_DIR / "data" / "processed" / "selected_features.json") as f:
        sf = json.load(f)
    features = sf["selected_features"]

    storage = get_storage()
    df = storage.load("factors")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index(["date", "ticker"]).sort_index()

    logger.info(f"팩터 로드: {df.shape}, 피처 {len(features)}개")
    return df, features


# ─── 2. TimeSeriesSplit 기반 날짜 윈도우 생성 ────────────────

def make_wf_splits(df: pd.DataFrame) -> list[dict]:
    """
    고유 날짜 배열에 TimeSeriesSplit 적용:
      - max_train_size : 3년치 거래일 고정 롤링 윈도우
      - test_size      : 6개월 검증 고정
      - gap            : 학습/검증 사이 간격 (0 = 연속)
    n_splits는 (전체일수 - train_days) / (val_days + step_days) 에서 자동 산출.
    """
    dates = df.index.get_level_values("date").unique().sort_values()
    total_days = len(dates)

    step_days  = TRADING_DAYS_YEAR // 4   # 3개월 스텝 ≈ 63일
    min_required = WF_TRAIN_DAYS + WF_VAL_DAYS
    if total_days <= min_required:
        raise ValueError(f"데이터 기간 부족: {total_days}일 < 최소 {min_required}일")

    n_splits = max(1, (total_days - WF_TRAIN_DAYS) // (WF_VAL_DAYS + step_days) - 1)

    tscv = TimeSeriesSplit(
        n_splits=n_splits,
        max_train_size=WF_TRAIN_DAYS,
        test_size=WF_VAL_DAYS,
        gap=WF_GAP_DAYS,
    )

    windows = []
    for tr_idx, va_idx in tscv.split(dates):
        tr_dates = dates[tr_idx]
        va_dates = dates[va_idx]
        windows.append({
            "train_dates": tr_dates,
            "val_dates":   va_dates,
            "train_start": tr_dates[0],
            "train_end":   tr_dates[-1],
            "val_start":   va_dates[0],
            "val_end":     va_dates[-1],
        })

    logger.info(f"Walk-Forward 윈도우: {len(windows)}개 (TimeSeriesSplit n_splits={n_splits})")
    for w in windows:
        logger.info(f"  train [{w['train_start'].date()}~{w['train_end'].date()}]"
                    f"  val [{w['val_start'].date()}~{w['val_end'].date()}]")
    return windows


# ─── 3. 패널 슬라이싱 헬퍼 ───────────────────────────────────

def slice_panel(df: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """날짜 집합으로 (date, ticker) 패널 데이터 슬라이싱"""
    mask = df.index.get_level_values("date").isin(dates)
    return df[mask]


# ─── 4. 모델 튜닝 ────────────────────────────────────────────

def tune_xgboost(X_tr, y_tr, X_va, y_va) -> tuple:
    import optuna
    import xgboost as xgb
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "n_estimators":     trial.suggest_int("n_estimators", 100, 500),
            "max_depth":        trial.suggest_int("max_depth", 2, 5),           # PRD: ≤5
            "min_child_weight": trial.suggest_int("min_child_weight", 50, 200), # PRD: ≥50
            "learning_rate":    trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "subsample":        trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha":        trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
            "reg_lambda":       trial.suggest_float("reg_lambda", 1e-4, 1.0, log=True),
            "random_state": 42, "n_jobs": -1, "verbosity": 0,
        }
        m = xgb.XGBRegressor(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        ic, _ = spearmanr(m.predict(X_va), y_va)
        return -ic

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=N_OPTUNA_TRIALS, show_progress_bar=False)

    best = study.best_params
    best.update({"random_state": 42, "n_jobs": -1, "verbosity": 0})
    model = xgb.XGBRegressor(**best)
    model.fit(X_tr, y_tr)
    return model, -study.best_value


def tune_lightgbm(X_tr, y_tr, X_va, y_va) -> tuple:
    import optuna
    import lightgbm as lgb
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "n_estimators":      trial.suggest_int("n_estimators", 100, 500),
            "max_depth":         trial.suggest_int("max_depth", 2, 5),
            "min_child_samples": trial.suggest_int("min_child_samples", 50, 200),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 1.0, log=True),
            "random_state": 42, "n_jobs": -1, "verbose": -1,
        }
        m = lgb.LGBMRegressor(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_va, y_va)])
        ic, _ = spearmanr(m.predict(X_va), y_va)
        return -ic

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=N_OPTUNA_TRIALS, show_progress_bar=False)

    best = study.best_params
    best.update({"random_state": 42, "n_jobs": -1, "verbose": -1})
    model = lgb.LGBMRegressor(**best)
    model.fit(X_tr, y_tr)
    return model, -study.best_value


def train_ridge(X_tr, y_tr, X_va, y_va) -> tuple:
    best_ic, best_model = -np.inf, None
    for alpha in [0.01, 0.1, 1.0, 10.0, 100.0]:
        m = Ridge(alpha=alpha)
        m.fit(X_tr, y_tr)
        ic, _ = spearmanr(m.predict(X_va), y_va)
        if ic > best_ic:
            best_ic, best_model = ic, m
    return best_model, best_ic


# ─── 5. Walk-Forward 실행 ─────────────────────────────────────

def run_walk_forward(df: pd.DataFrame, features: list[str]) -> list[dict]:
    windows   = make_wf_splits(df)
    wf_results = []

    for i, w in enumerate(windows):
        ckpt_path = CKPT_DIR / f"wf_step_{i:02d}.json"
        if ckpt_path.exists():
            logger.info(f"[{i+1}/{len(windows)}] 스킵 (체크포인트)")
            with open(ckpt_path) as f:
                wf_results.append(json.load(f))
            continue

        logger.info(f"[{i+1}/{len(windows)}] "
                    f"train {w['train_start'].date()}~{w['train_end'].date()} | "
                    f"val {w['val_start'].date()}~{w['val_end'].date()}")

        # TimeSeriesSplit이 만든 날짜 인덱스로 패널 슬라이싱
        tr = slice_panel(df, w["train_dates"]).dropna(subset=features + ["target_next"])
        va = slice_panel(df, w["val_dates"]).dropna(subset=features + ["target_next"])

        if len(tr) < 1000 or len(va) < 100:
            logger.warning(f"  데이터 부족 (train={len(tr)}, val={len(va)}) → 스킵")
            continue

        X_tr, y_tr = tr[features].values, tr["target_next"].values
        X_va, y_va = va[features].values, va["target_next"].values

        # 스케일링: train 통계만 사용 (test leak 방지)
        scaler = RobustScaler()
        X_tr   = scaler.fit_transform(X_tr)
        X_va   = scaler.transform(X_va)

        logger.info("  XGBoost 튜닝...")
        xgb_model, xgb_ic   = tune_xgboost(X_tr, y_tr, X_va, y_va)

        logger.info("  LightGBM 튜닝...")
        lgb_model, lgb_ic   = tune_lightgbm(X_tr, y_tr, X_va, y_va)

        ridge_model, ridge_ic = train_ridge(X_tr, y_tr, X_va, y_va)

        model_scores = {"xgboost": xgb_ic, "lightgbm": lgb_ic, "ridge": ridge_ic}
        logger.info(f"  IC — XGB:{xgb_ic:.4f}  LGB:{lgb_ic:.4f}  Ridge:{ridge_ic:.4f}")

        # 앙상블: 상위 2개 동일가중
        ranked    = sorted(model_scores.items(), key=lambda x: x[1], reverse=True)
        top2      = [ranked[0][0], ranked[1][0]]
        model_map = {"xgboost": xgb_model, "lightgbm": lgb_model, "ridge": ridge_model}

        pred_va     = np.mean([model_map[m].predict(X_va) for m in top2], axis=0)
        ensemble_ic, _ = spearmanr(pred_va, y_va)
        logger.info(f"  앙상블({top2}) IC: {ensemble_ic:.4f}")

        step = {
            "step":        i,
            "train_start": str(w["train_start"].date()),
            "train_end":   str(w["train_end"].date()),
            "val_start":   str(w["val_start"].date()),
            "val_end":     str(w["val_end"].date()),
            "model_ics":   model_scores,
            "ensemble_ic": ensemble_ic,
            "top2_models": top2,
            "n_train":     int(len(tr)),
            "n_val":       int(len(va)),
        }

        with open(ckpt_path, "w") as f:
            json.dump(step, f, indent=2)
        wf_results.append(step)

    return wf_results


# ─── 6. 최종 모델 학습 (전체 데이터) ─────────────────────────

def train_final_model(df: pd.DataFrame, features: list[str], wf_results: list[dict]):
    import xgboost as xgb
    import lightgbm as lgb

    # WF 전체에서 가장 자주 선정된 앙상블 조합
    combo_count: dict[tuple, int] = {}
    for r in wf_results:
        combo = tuple(sorted(r["top2_models"]))
        combo_count[combo] = combo_count.get(combo, 0) + 1
    best_combo = max(combo_count, key=combo_count.get)
    logger.info(f"최종 앙상블: {list(best_combo)} ({combo_count[best_combo]}/{len(wf_results)}회)")

    clean   = df.dropna(subset=features + ["target_next"])
    X       = clean[features].values
    y       = clean["target_next"].values
    scaler  = RobustScaler()
    X_sc    = scaler.fit_transform(X)

    trained: dict = {}
    if "xgboost" in best_combo:
        m = xgb.XGBRegressor(n_estimators=300, max_depth=4, min_child_weight=100,
                              learning_rate=0.05, random_state=42, n_jobs=-1, verbosity=0)
        m.fit(X_sc, y)
        trained["xgboost"] = m

    if "lightgbm" in best_combo:
        m = lgb.LGBMRegressor(n_estimators=300, max_depth=4, min_child_samples=100,
                               learning_rate=0.05, random_state=42, n_jobs=-1, verbose=-1)
        m.fit(X_sc, y)
        trained["lightgbm"] = m

    if "ridge" in best_combo:
        m = Ridge(alpha=1.0)
        m.fit(X_sc, y)
        trained["ridge"] = m

    return trained, scaler, list(best_combo)


# ─── 7. 모델 저장 ─────────────────────────────────────────────

def save_models(trained: dict, scaler, features: list[str],
                best_combo: list[str], wf_results: list[dict]):
    now_str     = datetime.now().strftime("v1_%Y%m%d_%H%M")
    version_dir = MODELS_DIR / now_str
    version_dir.mkdir(parents=True, exist_ok=True)

    for name, model in trained.items():
        with open(version_dir / f"{name}.pkl", "wb") as f:
            pickle.dump(model, f)

    with open(version_dir / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    avg_ic = float(np.mean([r["ensemble_ic"] for r in wf_results]))
    meta = {
        "version":          now_str,
        "features":         features,
        "ensemble":         best_combo,
        "split_strategy":   "TimeSeriesSplit(max_train_size=756, test_size=126, gap=0)",
        "wf_steps":         len(wf_results),
        "avg_ensemble_ic":  avg_ic,
        "trained_at":       datetime.now().isoformat(),
    }
    with open(version_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    # latest 심볼릭 링크
    latest = MODELS_DIR / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(version_dir.name)
    logger.info(f"심볼릭 링크: models/trained/latest → {now_str}")

    # model_registry.json 누적 등록
    registry = []
    if REG_PATH.exists():
        with open(REG_PATH) as f:
            registry = json.load(f)
    registry.append(meta)
    with open(REG_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    logger.info(f"저장: {version_dir}  |  WF 평균 IC: {avg_ic:.4f}")
    return version_dir


# ─── 8. 메인 ─────────────────────────────────────────────────

def main():
    df, features = load_features()

    wf_results = run_walk_forward(df, features)
    if not wf_results:
        logger.error("WF 결과 없음")
        return

    avg_ic = np.mean([r["ensemble_ic"] for r in wf_results])
    logger.info(f"\n=== Walk-Forward 완료: {len(wf_results)}스텝, 평균 IC {avg_ic:.4f} ===")

    trained, scaler, best_combo = train_final_model(df, features, wf_results)
    version_dir = save_models(trained, scaler, features, best_combo, wf_results)

    print(f"\n{'='*55}")
    print(f"✅ P4 ML 학습 완료")
    print(f"   앙상블     : {best_combo}")
    print(f"   WF 평균 IC : {avg_ic:.4f}")
    print(f"   저장 경로  : {version_dir}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
