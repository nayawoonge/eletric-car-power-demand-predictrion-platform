"""
LSTM 모델 학습 스크립트

사용법:
    python -m app.prediction.train_lstm --data_path <데이터 경로> --model_path <저장 경로>
"""

import argparse
import logging
import sys
from pathlib import Path
import pandas as pd
import numpy as np

from .lstm_prediction_engine import LSTMPredictionEngine

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_training_data(data_path: str) -> pd.DataFrame:
    """
    학습 데이터 로드

    데이터 형식:
    - CSV, Excel 파일 지원
    - 필수 컬럼: 순간최고전력
    - 선택 컬럼: 충전시작일시 (시계열 정보)
    """
    logger.info(f"Loading training data from {data_path}")

    path = Path(data_path)

    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    # 파일 형식에 따라 로드
    if path.suffix == '.csv':
        data = pd.read_csv(data_path)
    elif path.suffix in ['.xlsx', '.xls']:
        data = pd.read_excel(data_path)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    logger.info(f"Loaded {len(data)} rows, columns: {list(data.columns)}")

    # 필수 컬럼 확인
    if "순간최고전력" not in data.columns:
        raise ValueError("Missing required column: 순간최고전력")

    # 시계열 인덱스 설정 (있는 경우)
    time_cols = ["충전시작일시", "사용일시", "charging_start_time", "timestamp"]
    for col in time_cols:
        if col in data.columns:
            try:
                data[col] = pd.to_datetime(data[col], errors='coerce')
                data.set_index(col, inplace=True)
                data = data.sort_index()
                logger.info(f"Set time index using column: {col}")
                break
            except Exception as e:
                logger.warning(f"Failed to set time index using {col}: {e}")

    return data


def prepare_multi_station_data(data_path: str) -> pd.DataFrame:
    """
    여러 충전소 데이터를 하나로 합치기 (선택 사항)

    디렉토리 내 모든 CSV/Excel 파일을 로드하여 합침
    """
    path = Path(data_path)

    if path.is_file():
        return load_training_data(data_path)

    elif path.is_dir():
        logger.info(f"Loading all data files from directory: {data_path}")

        all_data = []

        # CSV 파일 로드
        for file_path in path.glob("*.csv"):
            try:
                df = pd.read_csv(file_path)
                all_data.append(df)
                logger.info(f"Loaded {file_path.name}: {len(df)} rows")
            except Exception as e:
                logger.warning(f"Failed to load {file_path.name}: {e}")

        # Excel 파일 로드
        for file_path in path.glob("*.xlsx"):
            try:
                df = pd.read_excel(file_path)
                all_data.append(df)
                logger.info(f"Loaded {file_path.name}: {len(df)} rows")
            except Exception as e:
                logger.warning(f"Failed to load {file_path.name}: {e}")

        if not all_data:
            raise ValueError(f"No valid data files found in {data_path}")

        # 모든 데이터 합치기
        combined_data = pd.concat(all_data, ignore_index=True)
        logger.info(f"Combined {len(all_data)} files, total rows: {len(combined_data)}")

        return combined_data

    else:
        raise ValueError(f"Invalid path: {data_path}")


def train_lstm_model(
    data_path: str,
    model_path: str = "models/lstm_model",
    epochs: int = 50,
    batch_size: int = 32,
    validation_split: float = 0.2
):
    """LSTM 모델 학습 메인 함수"""

    logger.info("=" * 60)
    logger.info("LSTM Model Training Started")
    logger.info("=" * 60)

    try:
        # 1. 데이터 로드
        logger.info("Step 1: Loading training data...")
        training_data = prepare_multi_station_data(data_path)

        logger.info(f"Training data summary:")
        logger.info(f"  - Total samples: {len(training_data)}")
        logger.info(f"  - Columns: {list(training_data.columns)}")

        if "순간최고전력" in training_data.columns:
            power_stats = training_data["순간최고전력"].describe()
            logger.info(f"  - Power statistics:\n{power_stats}")

        # 2. LSTM 엔진 초기화
        logger.info("\nStep 2: Initializing LSTM engine...")
        engine = LSTMPredictionEngine()

        # 3. 모델 학습
        logger.info(f"\nStep 3: Training LSTM model...")
        logger.info(f"  - Epochs: {epochs}")
        logger.info(f"  - Batch size: {batch_size}")
        logger.info(f"  - Validation split: {validation_split}")

        result = engine.train_model(
            training_data=training_data,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split
        )

        if not result.get("success", False):
            logger.error(f"Training failed: {result.get('error', 'Unknown error')}")
            return False

        # 4. 학습 결과 출력
        logger.info("\n" + "=" * 60)
        logger.info("Training Results:")
        logger.info("=" * 60)
        logger.info(f"  ✓ Success!")
        logger.info(f"  - Final Loss: {result['final_loss']:.4f}")
        logger.info(f"  - Final Val Loss: {result['final_val_loss']:.4f}")
        logger.info(f"  - Final MAE: {result['final_mae']:.4f} kW")
        logger.info(f"  - Epochs Trained: {result['epochs_trained']}")
        logger.info(f"  - Training Samples: {result['training_samples']}")

        # 5. 모델 저장
        logger.info(f"\nStep 4: Saving model to {model_path}...")
        engine.save_model(model_path)
        logger.info(f"  ✓ Model saved successfully")

        # 6. 간단한 테스트 예측
        logger.info("\nStep 5: Running test prediction...")
        test_prediction = engine.predict_contract_power(
            data=training_data.tail(100),  # 마지막 100개 데이터로 테스트
            station_id="test_station"
        )

        logger.info(f"  - Test Prediction: {test_prediction.final_prediction} kW")
        logger.info(f"  - Ensemble Method: {test_prediction.ensemble_method}")
        logger.info(f"  - Uncertainty: {test_prediction.uncertainty:.2f}")

        logger.info("\n" + "=" * 60)
        logger.info("Training Completed Successfully!")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"Training failed with error: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Train LSTM model for power demand prediction"
    )

    parser.add_argument(
        "--data_path",
        type=str,
        required=True,
        help="Path to training data (CSV/Excel file or directory)"
    )

    parser.add_argument(
        "--model_path",
        type=str,
        default="models/lstm_model",
        help="Path to save trained model (default: models/lstm_model)"
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Number of training epochs (default: 50)"
    )

    parser.add_argument(
        "--batch_size",
        type=int,
        default=32,
        help="Batch size for training (default: 32)"
    )

    parser.add_argument(
        "--validation_split",
        type=float,
        default=0.2,
        help="Validation data split ratio (default: 0.2)"
    )

    args = parser.parse_args()

    # 학습 실행
    success = train_lstm_model(
        data_path=args.data_path,
        model_path=args.model_path,
        epochs=args.epochs,
        batch_size=args.batch_size,
        validation_split=args.validation_split
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
