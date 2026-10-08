"""
XGBoost 모델 학습 스크립트 (슬라이딩 윈도우 재학습 지원)

특징:
- 시간 특징: 시간, 요일, 월, 주차, 주말
- 충전 패턴: 충전량, 충전시간, SOC 변화
- 회원 특징: 개인/법인 비율

사용 예:
    # 전체 데이터로 학습 (기본)
    python train_xgboost_model.py

    # 최근 12개월 데이터로만 학습 (슬라이딩 윈도우)
    python train_xgboost_model.py --window-months 12

    # CSV 명시 + 윈도우 18개월
    python train_xgboost_model.py --data-path ../data/raw/충전이력.csv --window-months 18

    # 모델 저장 경로 지정
    python train_xgboost_model.py --window-months 12 \\
        --model-save-path app/prediction/models/xgboost_w12
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import pandas as pd

from app.prediction.xgboost_prediction_engine import XGBoostPredictionEngine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 데이터 로딩 / 전처리 / 슬라이딩 윈도우
# ============================================================================

def resolve_data_path(explicit_path: Optional[str]) -> Path:
    """--data-path 가 명시되면 그 경로, 아니면 data/raw/ 에서 최신 CSV 자동 선택."""
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {p}")
        return p

    # 기본: <repo_root>/data/raw 내부에서 가장 최근에 수정된 CSV 사용
    backend_dir = Path(__file__).resolve().parent
    candidates = []
    for raw_dir in [backend_dir.parent / "data" / "raw", backend_dir / "data" / "raw"]:
        if raw_dir.exists():
            candidates.extend([f for f in raw_dir.glob("*.csv") if not f.name.startswith(".")])

    if not candidates:
        raise FileNotFoundError(
            "data/raw/ 디렉토리에서 CSV를 찾지 못했습니다. --data-path 로 명시해 주세요."
        )

    latest = max(candidates, key=lambda f: f.stat().st_mtime)
    logger.info(f"--data-path 미지정 → 자동 탐지된 CSV: {latest}")
    return latest


def load_and_preprocess_data(file_path: Path) -> pd.DataFrame:
    """데이터 로드 및 전처리 (인코딩 자동 fallback)."""
    logger.info(f"데이터 로드 중: {file_path}")

    df = None
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(file_path, encoding=enc)
            logger.info(f"✓ 인코딩 {enc} 로 로드 성공: {len(df):,}개 레코드")
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise RuntimeError(f"CSV 인코딩을 인식할 수 없습니다: {file_path}")

    # 날짜 변환
    df['충전시작일시'] = pd.to_datetime(df['충전시작일시'], errors='coerce')
    if '충전종료일시' in df.columns:
        df['충전종료일시'] = pd.to_datetime(df['충전종료일시'], errors='coerce')

    # 결측값 제거
    df = df.dropna(subset=['충전시작일시'])
    logger.info(f"✓ 충전시작일시 결측값 제거 후: {len(df):,}개 레코드")

    # 순간최고전력 변환 + 이상값 제거
    df['순간최고전력'] = pd.to_numeric(df['순간최고전력'], errors='coerce')
    df = df.dropna(subset=['순간최고전력'])
    df = df[df['순간최고전력'] > 0]
    df = df[df['순간최고전력'] <= 200]
    logger.info(f"✓ 이상값(순간최고전력 0 또는 >200kW) 제거 후: {len(df):,}개 레코드")

    if '충전량(kWh)' in df.columns:
        df['충전량(kWh)'] = pd.to_numeric(df['충전량(kWh)'], errors='coerce')

    date_min = df['충전시작일시'].min()
    date_max = df['충전시작일시'].max()
    logger.info(f"✓ 데이터 기간: {date_min} ~ {date_max}")

    return df


def apply_sliding_window(df: pd.DataFrame, window_months: Optional[int]) -> pd.DataFrame:
    """슬라이딩 윈도우 적용 — 데이터의 최신 날짜로부터 N 개월치만 남긴다.
    window_months 가 None 또는 0 이하면 필터 없이 그대로 반환.
    'now' 가 아니라 '데이터 내 최신 날짜' 기준으로 자르는 이유:
    재학습 시점에 데이터가 며칠 지연될 수 있고, 과거 백테스트에도 동일 동작을 보장하기 위함."""
    if not window_months or window_months <= 0:
        logger.info("슬라이딩 윈도우 미적용 (전체 데이터 사용).")
        return df

    latest_date = df['충전시작일시'].max()
    cutoff = latest_date - pd.DateOffset(months=window_months)
    before = len(df)
    df_win = df[df['충전시작일시'] >= cutoff].copy()
    after = len(df_win)

    logger.info(
        f"슬라이딩 윈도우 적용: 최근 {window_months}개월 "
        f"({cutoff.date()} ~ {latest_date.date()})"
    )
    logger.info(f"  - 필터 전: {before:,}개 → 필터 후: {after:,}개 ({after/before*100:.1f}% 잔존)")

    if df_win.empty:
        raise ValueError(
            f"슬라이딩 윈도우 적용 후 데이터가 비어있습니다. "
            f"window_months={window_months} 가 너무 좁거나 데이터가 부족합니다."
        )

    # 데이터가 너무 적으면 학습 품질 저하 경고
    if after < 1000:
        logger.warning(
            f"⚠ 필터 후 데이터가 매우 적습니다 ({after:,}개). "
            f"학습 품질이 낮을 수 있으니 window_months 를 늘리거나 데이터를 더 모으세요."
        )

    return df_win


# ============================================================================
# 학습 본체
# ============================================================================

def train_xgboost_model(
    data_path: Path,
    model_save_path: str = 'app/prediction/models/xgboost_trained',
    validation_split: float = 0.2,
    window_months: Optional[int] = None,
):
    """XGBoost 모델 학습 메인 함수."""
    logger.info("=" * 80)
    logger.info("XGBoost 모델 학습 시작")
    logger.info("=" * 80)

    # 1. 데이터 로드 + 슬라이딩 윈도우
    df = load_and_preprocess_data(data_path)
    df = apply_sliding_window(df, window_months)

    # 2. XGBoost 엔진 초기화
    logger.info("\n" + "=" * 80)
    logger.info("XGBoost 모델 초기화")
    logger.info("=" * 80)
    xgb_engine = XGBoostPredictionEngine()

    # 3. 모델 학습
    logger.info("\n" + "=" * 80)
    logger.info("모델 학습 시작")
    logger.info("=" * 80)
    history = xgb_engine.train_model(
        training_data=df,
        validation_split=validation_split
    )

    if not history.get('success'):
        logger.error(f"\n❌ 학습 실패: {history.get('error')}")
        return None, history

    # 4. 학습 결과 출력
    logger.info("\n" + "=" * 80)
    logger.info("✅ 학습 완료!")
    logger.info("=" * 80)
    logger.info(f"Train R² Score:      {history['train_r2_score']:.4f}")
    logger.info(f"Validation R² Score: {history['val_r2_score']:.4f}")
    logger.info(f"Train MAE:           {history['train_mae']:.2f}kW")
    logger.info(f"Validation MAE:      {history['val_mae']:.2f}kW")
    logger.info(f"특징 수:             {history['n_features']}")
    logger.info(f"학습 샘플 수:        {history['n_samples']}")
    if window_months:
        logger.info(f"슬라이딩 윈도우:     최근 {window_months}개월")

    logger.info("\n특징 중요도 (상위 10개):")
    feature_importance = history['feature_importance']
    sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (feature, importance) in enumerate(sorted_features, 1):
        logger.info(f"  {i}. {feature}: {importance:.4f}")

    # 5. 모델 저장
    logger.info(f"\n모델 저장 중: {model_save_path}")
    xgb_engine.save_model(model_save_path)
    logger.info("✓ 모델 저장 완료!")

    # 6. 테스트 예측 (최근 1000개 데이터)
    logger.info("\n" + "=" * 80)
    logger.info("테스트 예측")
    logger.info("=" * 80)
    recent_data = df.tail(1000)
    test_prediction = xgb_engine.predict_contract_power(
        data=recent_data,
        station_id="TEST_XGBOOST",
        charger_type="급속충전기 (DC)"
    )
    logger.info(f"예측 결과:    {test_prediction.final_prediction}kW")
    logger.info(f"실제 P95:     {recent_data['순간최고전력'].quantile(0.95):.1f}kW")
    logger.info(f"앙상블 방법:  {test_prediction.ensemble_method}")
    logger.info(f"불확실성:     ±{test_prediction.uncertainty:.1f}kW")

    return xgb_engine, history


# ============================================================================
# CLI
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="XGBoost 모델 학습 (슬라이딩 윈도우 재학습 지원)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
예시:
  # 전체 데이터 학습 (data/raw/ 의 최신 CSV 자동 선택)
  python train_xgboost_model.py

  # 최근 12개월 데이터로 재학습
  python train_xgboost_model.py --window-months 12

  # CSV 명시 + 18개월 윈도우
  python train_xgboost_model.py \\
      --data-path ../data/raw/충전이력.csv --window-months 18
""",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="학습용 CSV 경로. 생략 시 data/raw/ 에서 최신 CSV 자동 선택.",
    )
    parser.add_argument(
        "--window-months",
        type=int,
        default=None,
        help=(
            "슬라이딩 윈도우 크기(개월). 지정 시 데이터의 최신 날짜로부터 N개월치만 학습. "
            "권장: 12~18. 미지정 시 전체 데이터 사용."
        ),
    )
    parser.add_argument(
        "--model-save-path",
        type=str,
        default="app/prediction/models/xgboost_trained",
        help="학습된 모델 저장 디렉토리 (기본: app/prediction/models/xgboost_trained).",
    )
    parser.add_argument(
        "--validation-split",
        type=float,
        default=0.2,
        help="검증 데이터 비율 (기본 0.2 = 20%%).",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()

    try:
        data_path = resolve_data_path(args.data_path)
        xgb_engine, history = train_xgboost_model(
            data_path=data_path,
            model_save_path=args.model_save_path,
            validation_split=args.validation_split,
            window_months=args.window_months,
        )

        if xgb_engine:
            print("\n" + "=" * 80)
            print("🎉 XGBoost 모델 학습 및 저장 완료!")
            print("=" * 80)
            print(f"모델 경로: {args.model_save_path}")
            if args.window_months:
                print(f"슬라이딩 윈도우: 최근 {args.window_months}개월")
            print("\n다음 명령어로 모델을 사용할 수 있습니다:")
            print("```python")
            print("from app.prediction.xgboost_prediction_engine import XGBoostPredictionEngine")
            print(f"xgb_engine = XGBoostPredictionEngine(model_path='{args.model_save_path}')")
            print("prediction = xgb_engine.predict_contract_power(data, station_id)")
            print("```")

    except Exception as e:
        logger.error(f"학습 중 오류 발생: {e}", exc_info=True)
        print(f"\n❌ 학습 실패: {e}")
        sys.exit(1)
