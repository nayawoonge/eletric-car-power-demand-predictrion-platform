"""Backtest script: train on data through 2025-09, evaluate accuracy on October 2025."""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

# Ensure backend modules can be imported when executing as a script
CURRENT_DIR = Path(__file__).resolve().parent
APP_DIR = CURRENT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.prediction.lstm_prediction_engine import LSTMPredictionEngine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOGGER = logging.getLogger("october-backtest")

TRAIN_START = pd.Timestamp(2024, 1, 1)
TEST_START = pd.Timestamp(2025, 10, 1)
TEST_END = pd.Timestamp(2025, 11, 1)
DEFAULT_DATA_PATH = CURRENT_DIR.parent / "data" / "raw" / "충전이력리스트_급속_202409-202510.csv"
REPORT_PATH = CURRENT_DIR / "reports" / "october_2025_backtest.json"


def load_datasets(data_paths: List[Path]) -> pd.DataFrame:
    frames = []
    for path in data_paths:
        if not path.exists():
            LOGGER.warning("Skipping missing dataset %s", path)
            continue
        LOGGER.info("Loading dataset %s", path)
        frames.append(pd.read_csv(path, encoding="utf-8"))
    if not frames:
        raise FileNotFoundError("No valid CSV files were provided for backtesting")
    df = pd.concat(frames, ignore_index=True)
    LOGGER.info("Loaded %s rows from %s file(s)", f"{len(df):,}", len(frames))
    return df


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    required_cols = ["충전시작일시", "충전종료일시", "순간최고전력", "충전소ID"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")

    df = df.copy()
    df["충전시작일시"] = pd.to_datetime(df["충전시작일시"], errors="coerce")
    df["충전종료일시"] = pd.to_datetime(df["충전종료일시"], errors="coerce")
    df = df.dropna(subset=["충전시작일시", "순간최고전력"])
    df["순간최고전력"] = pd.to_numeric(df["순간최고전력"], errors="coerce")
    df = df.dropna(subset=["순간최고전력"])
    df = df[df["순간최고전력"] > 0]
    df = df[df["순간최고전력"] <= 200]

    if "충전량(kWh)" in df.columns:
        df["충전량(kWh)"] = pd.to_numeric(df["충전량(kWh)"], errors="coerce")

    LOGGER.info(
        "Dataset after preprocessing: %s rows spanning %s to %s",
        f"{len(df):,}",
        df["충전시작일시"].min(),
        df["충전시작일시"].max(),
    )
    return df


def filter_by_date(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    mask = (df["충전시작일시"] >= start) & (df["충전시작일시"] < end)
    result = df.loc[mask].copy()
    LOGGER.info(
        "Filtered %s rows for range %s ~ %s",
        f"{len(result):,}",
        start.date(),
        (end - pd.Timedelta(days=1)).date(),
    )
    return result


def select_top_stations(df: pd.DataFrame, top_n: int) -> List[str]:
    station_usage = (
        df.groupby("충전소ID")["순간최고전력"]
        .count()
        .sort_values(ascending=False)
    )
    stations = station_usage.head(top_n).index.tolist()
    LOGGER.info("Using top %d stations for training: %s", top_n, stations)
    return stations


def aggregate_hourly(df: pd.DataFrame, stations: List[str]) -> pd.DataFrame:
    subset = df[df["충전소ID"].isin(stations)].copy()
    if subset.empty:
        raise ValueError("선택된 충전소에 해당하는 데이터가 없습니다.")
    subset["hour"] = subset["충전시작일시"].dt.floor("h")

    agg_map = {"순간최고전력": ["max", "mean", "count"]}
    if "충전량(kWh)" in subset.columns:
        agg_map["충전량(kWh)"] = "sum"

    grouped = subset.groupby("hour").agg(agg_map).reset_index()
    columns = [
        "timestamp",
        "순간최고전력",
        "mean_power",
        "session_count",
    ]
    if "충전량(kWh)" in agg_map:
        columns.append("충전량(kWh)")

    grouped.columns = columns

    if "충전량(kWh)" not in grouped.columns:
        grouped["충전량(kWh)"] = 0.0

    grouped = grouped.set_index("timestamp").sort_index()
    LOGGER.info(
        "Aggregated %s hourly samples (%s ~ %s)",
        f"{len(grouped):,}",
        grouped.index.min(),
        grouped.index.max(),
    )
    return grouped


def evaluate_prediction(
    predicted_kw: float,
    uncertainty_kw: float,
    actual_series: pd.Series,
) -> Tuple[dict, pd.DataFrame]:
    actual_p95 = float(actual_series.quantile(0.95)) if len(actual_series) else 0.0
    absolute_error = abs(predicted_kw - actual_p95)
    mape = (absolute_error / actual_p95 * 100) if actual_p95 else None
    rmse = float(np.sqrt(np.mean((actual_series - predicted_kw) ** 2))) if len(actual_series) else None
    coverage = (
        actual_p95 >= predicted_kw - uncertainty_kw
        and actual_p95 <= predicted_kw + uncertainty_kw
        if actual_p95 and uncertainty_kw is not None
        else False
    )

    daily_max = (
        actual_series.reset_index()
        .rename(columns={"index": "timestamp"})
        .set_index("timestamp")
        .resample("D")["순간최고전력"]
        .max()
        .dropna()
        .reset_index()
    )
    daily_max.columns = ["date", "daily_peak_kw"]

    metrics = {
        "predicted_contract_kw": round(predicted_kw, 2),
        "actual_p95_kw": round(actual_p95, 2),
        "absolute_error_kw": round(absolute_error, 2),
        "mape_percent": round(mape, 2) if mape is not None else None,
        "rmse_vs_series_kw": round(rmse, 2) if rmse is not None else None,
        "within_5_percent": bool(actual_p95 and absolute_error <= actual_p95 * 0.05),
        "within_10_percent": bool(actual_p95 and absolute_error <= actual_p95 * 0.10),
        "confidence_interval_hit": coverage,
    }
    return metrics, daily_max


def run_backtest(args: argparse.Namespace) -> None:
    data_paths = [Path(path) for path in args.data]
    df = preprocess(load_datasets(data_paths))

    train_df = filter_by_date(df, TRAIN_START, TEST_START)
    test_df = filter_by_date(df, TEST_START, TEST_END)
    if train_df.empty or test_df.empty:
        raise ValueError("학습 혹은 테스트 구간에 해당하는 데이터가 충분하지 않습니다.")

    stations = select_top_stations(train_df, args.top_n_stations)
    train_hourly = aggregate_hourly(train_df, stations)
    test_hourly = aggregate_hourly(test_df, stations)

    LOGGER.info("Training LSTM on %s hourly samples", f"{len(train_hourly):,}")
    lstm_engine = LSTMPredictionEngine()
    history = lstm_engine.train_model(
        training_data=train_hourly,
        epochs=args.epochs,
        batch_size=args.batch_size,
        validation_split=0.2,
        learning_rate=args.learning_rate,
    )
    if not history.get("success"):
        raise RuntimeError(f"학습 실패: {history.get('error')}")

    if args.model_output:
        output_path = Path(args.model_output)
        output_path.mkdir(parents=True, exist_ok=True)
        lstm_engine.save_model(str(output_path))
        LOGGER.info("Saved backtest model to %s", output_path)

    prediction = lstm_engine.predict_contract_power(
        data=test_hourly,
        station_id="BACKTEST_OCT_2025",
        charger_type="급속충전기 (DC)",
    )

    metrics, daily_max = evaluate_prediction(
        predicted_kw=prediction.final_prediction,
        uncertainty_kw=getattr(prediction, "uncertainty", np.nan),
        actual_series=test_hourly["순간최고전력"],
    )

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "train_range": {
            "start": TRAIN_START.isoformat(),
            "end": (TEST_START - pd.Timedelta(seconds=1)).isoformat(),
            "samples": len(train_hourly),
        },
        "test_range": {
            "start": TEST_START.isoformat(),
            "end": (TEST_END - pd.Timedelta(seconds=1)).isoformat(),
            "samples": len(test_hourly),
        },
        "top_stations": stations,
        "training_history": history,
        "prediction": {
            "final_prediction_kw": prediction.final_prediction,
            "uncertainty_kw": getattr(prediction, "uncertainty", None),
        },
        "metrics": metrics,
        "daily_october_maxima": daily_max.to_dict(orient="records"),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    LOGGER.info("Backtest report written to %s", REPORT_PATH)

    LOGGER.info("Summary metrics: %s", json.dumps(metrics, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="October 2025 backtest pipeline")
    parser.add_argument(
        "--data",
        nargs="+",
        default=[str(DEFAULT_DATA_PATH)],
        help="학습/검증에 사용할 CSV 경로 (여러 개 가능)",
    )
    parser.add_argument("--top-n-stations", type=int, default=10)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument(
        "--model-output",
        type=str,
        default="app/prediction/models/lstm_backtest_202510",
        help="학습된 모델 저장 경로",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_backtest(parse_args())
