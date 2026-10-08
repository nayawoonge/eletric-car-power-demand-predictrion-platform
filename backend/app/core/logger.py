# 로깅 설정
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_logger(name: str, log_file: str = None, level: str = "INFO") -> logging.Logger:
    # level이 문자열인 경우 변환
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 이미 핸들러가 있으면 제거
    if logger.handlers:
        logger.handlers.clear()

    # 포매터 설정
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (선택적)
    if log_file:
        # 로그 디렉토리 생성
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)  # 10MB
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class PerformanceLogger:
    

    def __init__(self, logger_name: str = "performance"):
        self.logger = setup_logger(logger_name, "logs/performance.log")

    def log_prediction_performance(self, actual: float, predicted: float, station_id: str, timestamp: datetime):
        
        error = abs(actual - predicted)
        error_rate = error / actual if actual > 0 else 0

        self.logger.info(
            f"Prediction - Station: {station_id}, "
            f"Actual: {actual:.2f}, Predicted: {predicted:.2f}, "
            f"Error: {error:.2f}, Error Rate: {error_rate:.3f}, "
            f"Timestamp: {timestamp}"
        )

    def log_model_training(self, model_name: str, training_time: float, accuracy_metrics: dict):
        
        self.logger.info(
            f"Training - Model: {model_name}, " f"Time: {training_time:.2f}s, " f"Metrics: {accuracy_metrics}"
        )
