"""
LSTM 모델 학습 스크립트 (슬라이딩 윈도우 재학습 지원)

사용 예:
    # 전체 데이터로 학습 (기본)
    python train_lstm_model.py

    # 최근 12개월 데이터로만 학습 (슬라이딩 윈도우)
    python train_lstm_model.py --window-months 12

    # 상위 N개 충전소, 에포크/배치 지정
    python train_lstm_model.py --window-months 12 \\
        --top-n-stations 20 --epochs 100 --batch-size 64
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import pandas as pd

from app.prediction.lstm_prediction_engine import LSTMPredictionEngine

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


def load_charging_data(file_path: Path) -> pd.DataFrame:
    """충전 이력 데이터 로드 (인코딩 자동 fallback)."""
    logger.info(f"데이터 로드 중: {file_path}")
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(file_path, encoding=enc)
            logger.info(f"✓ 인코딩 {enc} 로 로드 성공: {len(df):,}개 레코드")
            return df
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"CSV 인코딩을 인식할 수 없습니다: {file_path}")


def preprocess_for_training(df: pd.DataFrame) -> pd.DataFrame:
    """학습용 데이터 전처리."""
    logger.info("데이터 전처리 시작...")

    required_cols = ['충전시작일시', '충전종료일시', '순간최고전력', '충전소ID']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"필수 컬럼 누락: {missing_cols}")

    df['충전시작일시'] = pd.to_datetime(df['충전시작일시'], errors='coerce')
    df['충전종료일시'] = pd.to_datetime(df['충전종료일시'], errors='coerce')

    df = df.dropna(subset=['충전시작일시', '순간최고전력'])
    logger.info(f"✓ 결측값 제거 후: {len(df):,}개 레코드")

    df['순간최고전력'] = pd.to_numeric(df['순간최고전력'], errors='coerce')
    df = df.dropna(subset=['순간최고전력'])

    if '충전량(kWh)' in df.columns:
        df['충전량(kWh)'] = pd.to_numeric(df['충전량(kWh)'], errors='coerce')

    df = df[df['순간최고전력'] > 0]
    df = df[df['순간최고전력'] <= 200]
    logger.info(f"✓ 이상값 제거 후: {len(df):,}개 레코드")

    date_min = df['충전시작일시'].min()
    date_max = df['충전시작일시'].max()
    logger.info(f"✓ 데이터 기간: {date_min} ~ {date_max}")

    return df


def apply_sliding_window(df: pd.DataFrame, window_months: Optional[int]) -> pd.DataFrame:
    """슬라이딩 윈도우 적용 — 데이터 내 최신 날짜 기준으로 N개월치만 남긴다."""
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
    if after < 1000:
        logger.warning(
            f"⚠ 필터 후 데이터가 매우 적습니다 ({after:,}개). "
            f"학습 품질이 낮을 수 있으니 window_months 를 늘리거나 데이터를 더 모으세요."
        )

    return df_win


def aggregate_hourly_data(df: pd.DataFrame, top_n_stations: int = 10) -> pd.DataFrame:
    """시간 단위로 데이터 집계."""
    logger.info("시간 단위 집계 시작...")

    station_usage = df.groupby('충전소ID')['순간최고전력'].agg(['count', 'mean'])
    station_usage = station_usage.sort_values('count', ascending=False)
    top_stations = station_usage.head(top_n_stations).index.tolist()

    logger.info(f"✓ 상위 {top_n_stations}개 충전소 선택:")
    for i, station in enumerate(top_stations, 1):
        count = station_usage.loc[station, 'count']
        mean_power = station_usage.loc[station, 'mean']
        logger.info(f"  {i}. {station}: {count:,}회 충전, 평균 {mean_power:.1f}kW")

    df_filtered = df[df['충전소ID'].isin(top_stations)].copy()
    logger.info(f"✓ 필터링 후: {len(df_filtered):,}개 레코드")

    df_filtered['hour'] = df_filtered['충전시작일시'].dt.floor('h')  # 'H'는 최신 pandas에서 제거됨 → 'h'
    hourly_data = df_filtered.groupby('hour').agg({
        '순간최고전력': ['max', 'mean', 'count'],
        '충전량(kWh)': 'sum'
    }).reset_index()
    hourly_data.columns = ['timestamp', '순간최고전력', 'mean_power', 'session_count', '충전량(kWh)']
    hourly_data = hourly_data.set_index('timestamp').sort_index()

    logger.info(f"✓ 시간 단위 집계 완료: {len(hourly_data):,}개 시간대")
    logger.info(f"  - 평균 전력: {hourly_data['순간최고전력'].mean():.1f}kW")
    logger.info(f"  - 최대 전력: {hourly_data['순간최고전력'].max():.1f}kW")
    logger.info(f"  - 표준편차: {hourly_data['순간최고전력'].std():.1f}kW")

    return hourly_data


def split_train_val(data: pd.DataFrame, val_ratio: float = 0.2):
    """학습/검증 데이터 분할."""
    split_idx = int(len(data) * (1 - val_ratio))
    train_data = data.iloc[:split_idx]
    val_data = data.iloc[split_idx:]
    logger.info(f"✓ 데이터 분할:")
    logger.info(f"  - 학습: {len(train_data):,}개 ({len(train_data)/len(data)*100:.1f}%)")
    logger.info(f"  - 검증: {len(val_data):,}개 ({len(val_data)/len(data)*100:.1f}%)")
    return train_data, val_data


# ============================================================================
# 학습 본체
# ============================================================================

def train_lstm_model(
    data_path: Path,
    model_save_path: str = 'app/prediction/models/lstm_trained',
    top_n_stations: int = 10,
    epochs: int = 50,
    batch_size: int = 32,
    window_months: Optional[int] = None,
):
    """LSTM 모델 학습 메인 함수."""
    logger.info("=" * 80)
    logger.info("LSTM 모델 학습 시작")
    logger.info("=" * 80)

    # 1. 데이터 로드
    df = load_charging_data(data_path)

    # 2. 전처리
    df = preprocess_for_training(df)

    # 3. 슬라이딩 윈도우 (시간 집계 전에 적용)
    df = apply_sliding_window(df, window_months)

    # 4. 시간 단위 집계
    hourly_data = aggregate_hourly_data(df, top_n_stations=top_n_stations)

    # 5. 학습/검증 분할
    train_data, val_data = split_train_val(hourly_data, val_ratio=0.2)

    # 6. LSTM 엔진 초기화
    logger.info("\n" + "=" * 80)
    logger.info("LSTM 모델 학습 시작")
    logger.info("=" * 80)
    lstm_engine = LSTMPredictionEngine()

    # 7. 모델 학습
    history = lstm_engine.train_model(
        training_data=train_data,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=0.2
    )

    if not history.get('success'):
        logger.error(f"\n❌ 학습 실패: {history.get('error')}")
        return None, history

    # 8. 결과 출력
    logger.info("\n" + "=" * 80)
    logger.info("✅ 학습 완료!")
    logger.info("=" * 80)
    logger.info(f"최종 Loss:    {history['final_loss']:.4f}")
    logger.info(f"검증 Loss:    {history['final_val_loss']:.4f}")
    logger.info(f"MAE:          {history['final_mae']:.4f}")
    logger.info(f"학습 에포크:  {history['epochs_trained']}")
    logger.info(f"학습 샘플 수: {history['training_samples']}")
    if window_months:
        logger.info(f"슬라이딩 윈도우: 최근 {window_months}개월")

    # 9. 모델 저장
    logger.info(f"\n모델 저장 중: {model_save_path}")
    lstm_engine.save_model(model_save_path)
    logger.info("✓ 모델 저장 완료!")

    # 10. 검증 테스트
    logger.info("\n" + "=" * 80)
    logger.info("검증 데이터 테스트")
    logger.info("=" * 80)
    test_prediction = lstm_engine.predict_contract_power(
        data=val_data,
        station_id="TEST_VALIDATION",
        charger_type="급속충전기 (DC)"
    )
    logger.info(f"예측 결과:   {test_prediction.final_prediction}kW")
    logger.info(f"실제 P95:    {val_data['순간최고전력'].quantile(0.95):.1f}kW")
    logger.info(f"앙상블 방법: {test_prediction.ensemble_method}")
    logger.info(f"불확실성:    ±{test_prediction.uncertainty:.1f}kW")

    return lstm_engine, history


# ============================================================================
# CLI
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LSTM 모델 학습 (슬라이딩 윈도우 재학습 지원)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
예시:
  # 전체 데이터 학습
  python train_lstm_model.py

  # 최근 12개월 데이터로 재학습
  python train_lstm_model.py --window-months 12

  # 상위 충전소 / 에포크 / 배치 크기 조정
  python train_lstm_model.py --window-months 12 \\
      --top-n-stations 20 --epochs 100 --batch-size 64
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
            "슬라이딩 윈도우 크기(개월). 지정 시 데이터 내 최신 날짜로부터 N개월치만 학습. "
            "권장: 12~18. 미지정 시 전체 데이터 사용."
        ),
    )
    parser.add_argument(
        "--model-save-path",
        type=str,
        default="app/prediction/models/lstm_trained",
        help="학습된 모델 저장 디렉토리 (기본: app/prediction/models/lstm_trained).",
    )
    parser.add_argument(
        "--top-n-stations",
        type=int,
        default=10,
        help="시간 집계 시 사용할 상위 충전소 수 (기본 10).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="LSTM 학습 에포크 수 (기본 50).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="배치 크기 (기본 32).",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()

    try:
        data_path = resolve_data_path(args.data_path)
        lstm_engine, history = train_lstm_model(
            data_path=data_path,
            model_save_path=args.model_save_path,
            top_n_stations=args.top_n_stations,
            epochs=args.epochs,
            batch_size=args.batch_size,
            window_months=args.window_months,
        )

        if lstm_engine:
            print("\n" + "=" * 80)
            print("🎉 LSTM 모델 학습 및 저장 완료!")
            print("=" * 80)
            print(f"모델 경로: {args.model_save_path}")
            if args.window_months:
                print(f"슬라이딩 윈도우: 최근 {args.window_months}개월")
            print("\n다음 명령어로 모델을 사용할 수 있습니다:")
            print("```python")
            print("from app.prediction.lstm_prediction_engine import LSTMPredictionEngine")
            print(f"lstm_engine = LSTMPredictionEngine(model_path='{args.model_save_path}')")
            print("prediction = lstm_engine.predict_contract_power(data, station_id)")
            print("```")

    except Exception as e:
        logger.error(f"학습 중 오류 발생: {e}", exc_info=True)
        print(f"\n❌ 학습 실패: {e}")
        sys.exit(1)
