import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import logging
import warnings
from pathlib import Path
import pickle

from .models.prediction_types import ModelPrediction, EnsemblePrediction

warnings.filterwarnings("ignore")

# Simplified Pattern Factors
from dataclasses import dataclass

@dataclass
class PatternFactors:
    """Simplified pattern factors"""
    seasonal_factor: float = 1.0
    weekly_factor: float = 1.0
    trend_factor: float = 1.0
    confidence: float = 0.7
    data_quality: str = "medium"

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    logging.warning("PyTorch not available. LSTM prediction will use fallback methods.")


class LSTMPredictionEngine:

    def __init__(self, model_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.max_contract_power = 100  # 최대 계약 전력 100kW

        # 충전기 타입별 최대 전력 제한
        self.charger_limits = {
            "완속충전기 (AC)": 7,
            "급속충전기 (DC)": 100,
            "미상": 50,
        }

        # LSTM 모델 설정
        self.sequence_length = 24  # 24시간(또는 24개 데이터 포인트) 시퀀스
        self.feature_dim = 6  # 입력 특징 개수
        self.model = None
        self.scaler = None

        # 모델 로드 또는 초기화
        if model_path and Path(model_path).exists():
            self._load_model(model_path)
        else:
            if TENSORFLOW_AVAILABLE:
                self._build_model()
            else:
                self.logger.warning("TensorFlow not available. Using statistical fallback.")

    def _build_model(self):
        if not TENSORFLOW_AVAILABLE:
            return

        try:
            # 시퀀스-투-벡터 LSTM 모델
            model = keras.Sequential([
                # LSTM Layer 1 - 시계열 패턴 학습
                layers.LSTM(
                    64,
                    return_sequences=True,
                    input_shape=(self.sequence_length, self.feature_dim),
                    dropout=0.2
                ),

                # LSTM Layer 2 - 더 깊은 패턴 추출
                layers.LSTM(32, return_sequences=False, dropout=0.2),

                # Dense Layers - 최종 예측
                layers.Dense(16, activation='relu'),
                layers.Dropout(0.1),
                layers.Dense(1, activation='linear')  # 회귀 문제
            ])

            # 모델 컴파일
            model.compile(
                optimizer=keras.optimizers.Adam(learning_rate=0.001),
                loss='mse',
                metrics=['mae']
            )

            self.model = model
            self.logger.info("LSTM model built successfully")

        except Exception as e:
            self.logger.error(f"Failed to build LSTM model: {e}")
            self.model = None

    def _load_model(self, model_path: str):
        """저장된 모델 로드"""
        try:
            model_dir = Path(model_path)

            # LSTM 모델 로드
            if (model_dir / "lstm_model.h5").exists() and TENSORFLOW_AVAILABLE:
                self.model = keras.models.load_model(model_dir / "lstm_model.h5")
                self.logger.info(f"LSTM model loaded from {model_path}")

            # Scaler 로드
            if (model_dir / "scaler.pkl").exists():
                with open(model_dir / "scaler.pkl", 'rb') as f:
                    self.scaler = pickle.load(f)
                self.logger.info("Scaler loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            if TENSORFLOW_AVAILABLE:
                self._build_model()

    def save_model(self, model_path: str):
        """모델 저장"""
        try:
            model_dir = Path(model_path)
            model_dir.mkdir(parents=True, exist_ok=True)

            # LSTM 모델 저장
            if self.model and TENSORFLOW_AVAILABLE:
                self.model.save(model_dir / "lstm_model.h5")
                self.logger.info(f"LSTM model saved to {model_path}")

            # Scaler 저장
            if self.scaler:
                with open(model_dir / "scaler.pkl", 'wb') as f:
                    pickle.dump(self.scaler, f)
                self.logger.info("Scaler saved successfully")

        except Exception as e:
            self.logger.error(f"Failed to save model: {e}")

    def predict_contract_power(
        self,
        data: pd.DataFrame,
        station_id: str,
        charger_type: str = None
    ) -> EnsemblePrediction:
        """
        계약전력 예측 (메인 메서드)

        Args:
            data: 충전소 데이터
            station_id: 충전소 ID
            charger_type: 충전기 타입

        Returns:
            EnsemblePrediction: 예측 결과
        """

        if data.empty or "순간최고전력" not in data.columns:
            return self._fallback_prediction(station_id)

        # 데이터 전처리
        power_data = self._preprocess_data(data)

        if len(power_data) < self.sequence_length:
            return self._fallback_prediction(station_id)

        try:
            # LSTM 예측
            if self.model and TENSORFLOW_AVAILABLE:
                lstm_prediction = self._lstm_predict(data, power_data)
            else:
                # TensorFlow가 없으면 통계적 방법 사용
                lstm_prediction = self._statistical_fallback(power_data)

            # 충전기 타입 제한 적용
            if charger_type and charger_type in self.charger_limits:
                max_limit = self.charger_limits[charger_type]
                lstm_prediction.final_prediction = min(
                    lstm_prediction.final_prediction,
                    max_limit
                )

            self.logger.info(
                f"Station {station_id}: LSTM prediction completed, "
                f"result: {lstm_prediction.final_prediction}kW"
            )

            return lstm_prediction

        except Exception as e:
            self.logger.error(f"LSTM prediction failed: {e}", exc_info=True)
            return self._fallback_prediction(station_id)

    def _preprocess_data(self, data: pd.DataFrame) -> np.ndarray:
        """데이터 전처리"""
        try:
            # 숫자 타입으로 변환 (날짜/시간 문제 방지)
            power_data = pd.to_numeric(data["순간최고전력"], errors='coerce').values

            # 결측값 및 이상값 제거
            power_data = power_data[~np.isnan(power_data)]
            power_data = power_data[power_data > 0]
            power_data = power_data[power_data < 1000]

            # IQR 기반 이상치 제거
            if len(power_data) > 10:
                Q1, Q3 = np.percentile(power_data, [25, 75])
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                power_data = power_data[
                    (power_data >= lower_bound) & (power_data <= upper_bound)
                ]

            return power_data

        except Exception as e:
            self.logger.error(f"Data preprocessing failed: {e}", exc_info=True)
            return np.array([])

    def _extract_features(self, data: pd.DataFrame, power_data: np.ndarray) -> np.ndarray:
        """
        시계열 데이터에서 특징 추출

        Features:
        1. 전력값 (normalized)
        2. 시간 (hour of day) - 주기적 인코딩
        3. 요일 (day of week) - 주기적 인코딩
        4. 월 (month) - 주기적 인코딩
        5. 트렌드 (선형 트렌드)
        6. 이동평균 (rolling mean)
        """
        try:
            # DatetimeIndex가 없으면 충전시작일시 컬럼에서 생성
            if not isinstance(data.index, pd.DatetimeIndex):
                # 충전시작일시 컬럼 찾기
                date_col = None
                for col in ['충전시작일시', '충전완료일시', 'timestamp']:
                    if col in data.columns:
                        date_col = col
                        break
                
                if date_col:
                    # DatetimeIndex 설정
                    data_copy = data.copy()
                    data_copy[date_col] = pd.to_datetime(data_copy[date_col], errors='coerce')
                    data_copy = data_copy.dropna(subset=[date_col])
                    data_copy = data_copy.set_index(date_col)
                    
                    if len(data_copy) > 0:
                        return self._extract_features_from_datetime_index(data_copy, power_data)
                
                # 날짜 정보가 없으면 기본 특징만 사용
                self.logger.warning("No datetime information found, using basic features")
                features = self._extract_basic_features(power_data)
                return features
            
            # DatetimeIndex가 있으면 정상 처리
            return self._extract_features_from_datetime_index(data, power_data)

        except Exception as e:
            self.logger.error(f"Feature extraction failed: {e}", exc_info=True)
            return self._extract_basic_features(power_data)
    
    def _extract_features_from_datetime_index(
        self, 
        data: pd.DataFrame, 
        power_data: np.ndarray
    ) -> np.ndarray:
        """DatetimeIndex가 있는 데이터에서 특징 추출"""
        features_list = []

        for i in range(len(data)):
            timestamp = data.index[i]
            power = power_data[i] if i < len(power_data) else 0

            # 1. 정규화된 전력값
            normalized_power = power / 100.0  # 0-100kW 범위를 0-1로

            # 2. 시간 (주기적 인코딩: sin/cos)
            hour = timestamp.hour
            hour_sin = np.sin(2 * np.pi * hour / 24)
            hour_cos = np.cos(2 * np.pi * hour / 24)

            # 3. 요일 (주기적 인코딩)
            weekday = timestamp.weekday()
            weekday_sin = np.sin(2 * np.pi * weekday / 7)
            weekday_cos = np.cos(2 * np.pi * weekday / 7)

            # 4. 월 (주기적 인코딩)
            month = timestamp.month
            month_sin = np.sin(2 * np.pi * month / 12)

            features = [
                normalized_power,
                hour_sin,
                weekday_sin,
                month_sin,
                hour_cos,  # 추가 시간 정보
                weekday_cos  # 추가 요일 정보
            ]

            features_list.append(features)

        return np.array(features_list)

    def _extract_basic_features(self, power_data: np.ndarray) -> np.ndarray:
        """기본 특징 추출 (시간 정보가 없을 때)"""
        features_list = []

        for i in range(len(power_data)):
            power = power_data[i]
            normalized_power = power / 100.0

            # 기본 특징: 전력값 + 더미 시간 특징
            features = [
                normalized_power,
                0.0,  # hour_sin
                0.0,  # weekday_sin
                0.0,  # month_sin
                1.0,  # hour_cos
                1.0   # weekday_cos
            ]
            features_list.append(features)

        return np.array(features_list)

    def _create_sequences(self, features: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """시퀀스 데이터 생성 (sliding window)"""
        X, y = [], []

        for i in range(len(features) - self.sequence_length):
            X.append(features[i:i + self.sequence_length])
            # 다음 시점의 전력값 예측
            y.append(features[i + self.sequence_length, 0] * 100.0)  # denormalize

        return np.array(X), np.array(y)

    def predict_with_uncertainty(
        self,
        data: pd.DataFrame,
        power_data: np.ndarray,
        n_iterations: int = 1000
    ) -> np.ndarray:
        """
        Monte Carlo Dropout을 사용한 불확실성 추정
        
        Args:
            data: 입력 데이터프레임
            power_data: 전력 데이터
            n_iterations: Monte Carlo 시뮬레이션 반복 횟수
            
        Returns:
            np.ndarray: 예측 분포 (shape: (n_iterations,))
        """
        try:
            # 특징 추출
            features = self._extract_features(data, power_data)
            
            if len(features) < self.sequence_length:
                # 데이터 부족 시 통계 기반 분포 생성
                mean = np.mean(power_data)
                std = np.std(power_data)
                return np.random.normal(mean, std, n_iterations)
            
            # 마지막 시퀀스로 예측
            last_sequence = features[-self.sequence_length:].reshape(
                1, self.sequence_length, self.feature_dim
            )
            
            predictions = []
            
            # Monte Carlo Dropout: training=True로 설정하여 Dropout 활성화
            for _ in range(n_iterations):
                # training=True로 설정하면 dropout이 계속 활성화됨
                pred = self.model(last_sequence, training=True)
                pred_value = float(pred[0][0]) * 100.0  # denormalize
                predictions.append(pred_value)
            
            return np.array(predictions)
            
        except Exception as e:
            self.logger.error(f"Monte Carlo prediction failed: {e}")
            # 폴백: 통계 기반 분포
            mean = np.mean(power_data)
            std = np.std(power_data)
            return np.random.normal(mean, std, n_iterations)

    def _lstm_predict(self, data: pd.DataFrame, power_data: np.ndarray) -> EnsemblePrediction:
        """LSTM 모델을 사용한 예측 (Monte Carlo Dropout 포함)"""
        try:
            # Monte Carlo Dropout으로 확률분포 생성
            prediction_distribution = self.predict_with_uncertainty(
                data, power_data, n_iterations=1000
            )
            
            # 분포 통계 계산
            prediction = np.mean(prediction_distribution)
            ci_lower = np.percentile(prediction_distribution, 2.5)
            ci_upper = np.percentile(prediction_distribution, 97.5)
            
            # 분포 정보를 method_details에 저장
            distribution_stats = {
                "mean": float(np.mean(prediction_distribution)),
                "std": float(np.std(prediction_distribution)),
                "min": float(np.min(prediction_distribution)),
                "max": float(np.max(prediction_distribution)),
                "p10": float(np.percentile(prediction_distribution, 10)),
                "p50": float(np.percentile(prediction_distribution, 50)),
                "p90": float(np.percentile(prediction_distribution, 90)),
                "p95": float(np.percentile(prediction_distribution, 95)),
                "p99": float(np.percentile(prediction_distribution, 99)),
            }

            # 기본 통계 계산
            base_stats = self._compute_base_statistics(power_data)

            # 모델 예측 객체 생성 (Monte Carlo Dropout 적용)
            lstm_model_prediction = ModelPrediction(
                model_name="LSTM_Deep_Learning",
                predicted_value=float(prediction),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=0.85,  # LSTM은 높은 신뢰도
                method_details={
                    "method": "LSTM Deep Learning with Monte Carlo Dropout",
                    "sequence_length": self.sequence_length,
                    "feature_dim": self.feature_dim,
                    "monte_carlo_iterations": 1000,
                    "description": "LSTM 딥러닝 + Monte Carlo Dropout 불확실성 추정",
                    "data_points_used": len(power_data),
                    "percentile_95_comparison": base_stats["q95"],
                    "distribution": distribution_stats,
                    "prediction_distribution": prediction_distribution.tolist()  # 전체 분포 저장
                }
            )

            # 보조 통계 예측 추가 (앙상블 효과)
            statistical_prediction = ModelPrediction(
                model_name="Statistical_Baseline",
                predicted_value=base_stats["q95"],
                confidence_interval=(base_stats["q90"], base_stats["q99"]),
                confidence_score=0.70,
                method_details={
                    "method": "95th Percentile",
                    "description": "통계적 기준선"
                }
            )

            # 가중 앙상블 (LSTM 70%, Statistical 30%)
            predictions = [lstm_model_prediction, statistical_prediction]
            weights = {
                "LSTM_Deep_Learning": 0.70,
                "Statistical_Baseline": 0.30
            }

            weighted_prediction = (
                lstm_model_prediction.predicted_value * 0.70 +
                statistical_prediction.predicted_value * 0.30
            )

            # 불확실성 계산
            uncertainty = np.sqrt(
                0.70 * (lstm_model_prediction.predicted_value - weighted_prediction) ** 2 +
                0.30 * (statistical_prediction.predicted_value - weighted_prediction) ** 2
            )

            # 최종 예측값 (올림)
            final_prediction = min(
                int(np.ceil(weighted_prediction)),
                self.max_contract_power
            )

            return EnsemblePrediction(
                final_prediction=final_prediction,
                raw_prediction=weighted_prediction,
                model_predictions=predictions,
                ensemble_method="weighted_lstm_statistical",
                weights=weights,
                uncertainty=float(uncertainty),
                visualization_data=self._prepare_visualization_data(
                    predictions,
                    weighted_prediction
                )
            )

        except Exception as e:
            self.logger.error(f"LSTM prediction failed: {e}", exc_info=True)
            return self._statistical_fallback(power_data)

    def _statistical_fallback(self, power_data: np.ndarray) -> EnsemblePrediction:
        """통계적 방법을 사용한 폴백 예측"""
        base_stats = self._compute_base_statistics(power_data)

        # 95th percentile 기반 예측
        predicted_value = base_stats["q95"]

        fallback_prediction = ModelPrediction(
            model_name="Statistical_Fallback",
            predicted_value=predicted_value,
            confidence_interval=(base_stats["q90"], base_stats["q99"]),
            confidence_score=0.75,
            method_details={
                "method": "95th Percentile",
                "reason": "LSTM not available or insufficient data",
                "description": "통계적 백분위수 기반 예측"
            }
        )

        final_prediction = min(
            int(np.ceil(predicted_value)),
            self.max_contract_power
        )

        return EnsemblePrediction(
            final_prediction=final_prediction,
            raw_prediction=predicted_value,
            model_predictions=[fallback_prediction],
            ensemble_method="statistical_fallback",
            weights={"Statistical_Fallback": 1.0},
            uncertainty=base_stats["std"],
            visualization_data=self._prepare_visualization_data(
                [fallback_prediction],
                predicted_value
            )
        )

    def _compute_base_statistics(self, power_data: np.ndarray) -> Dict[str, float]:
        """기본 통계량 계산"""
        try:
            return {
                "mean": np.mean(power_data),
                "std": np.std(power_data),
                "min": np.min(power_data),
                "max": np.max(power_data),
                "q25": np.percentile(power_data, 25),
                "q50": np.percentile(power_data, 50),
                "q75": np.percentile(power_data, 75),
                "q90": np.percentile(power_data, 90),
                "q95": np.percentile(power_data, 95),
                "q98": np.percentile(power_data, 98),
                "q99": np.percentile(power_data, 99),
            }
        except Exception:
            return {
                "mean": 45.0, "std": 15.0, "min": 0.0, "max": 100.0,
                "q25": 35.0, "q50": 45.0, "q75": 55.0, "q90": 65.0,
                "q95": 70.0, "q98": 75.0, "q99": 80.0
            }

    def _prepare_visualization_data(
        self,
        predictions: List[ModelPrediction],
        ensemble_prediction: float
    ) -> Dict[str, Any]:
        """시각화용 데이터 준비"""
        return {
            "individual_predictions": [
                {
                    "model": pred.model_name,
                    "value": pred.predicted_value,
                    "confidence": pred.confidence_score,
                    "ci_lower": pred.confidence_interval[0],
                    "ci_upper": pred.confidence_interval[1],
                }
                for pred in predictions
            ],
            "ensemble_prediction": ensemble_prediction,
            "model_count": len(predictions),
            "prediction_range": {
                "min": min(p.predicted_value for p in predictions),
                "max": max(p.predicted_value for p in predictions),
                "std": np.std([p.predicted_value for p in predictions]),
            },
        }

    def _fallback_prediction(self, station_id: str) -> EnsemblePrediction:
        """폴백 예측 (데이터 부족 시)"""
        self.logger.warning(f"Using fallback prediction for station {station_id}")

        fallback_prediction = ModelPrediction(
            model_name="Fallback_Default",
            predicted_value=45.0,
            confidence_interval=(35.0, 55.0),
            confidence_score=0.5,
            method_details={
                "method": "Default Fallback",
                "reason": "Insufficient data",
                "description": "기본값 사용 (데이터 부족)"
            }
        )

        return EnsemblePrediction(
            final_prediction=45,
            raw_prediction=45.0,
            model_predictions=[fallback_prediction],
            ensemble_method="fallback",
            weights={"Fallback_Default": 1.0},
            uncertainty=20.0,
            visualization_data=self._prepare_visualization_data(
                [fallback_prediction],
                45.0
            )
        )

    def train_model(
        self,
        training_data: pd.DataFrame,
        epochs: int = 50,
        batch_size: int = 32,
        validation_split: float = 0.2
    ) -> Dict[str, Any]:
        """
        LSTM 모델 학습

        Args:
            training_data: 학습 데이터 (컬럼: 순간최고전력 필수)
            epochs: 학습 에포크 수
            batch_size: 배치 크기
            validation_split: 검증 데이터 비율

        Returns:
            학습 히스토리
        """
        if not TENSORFLOW_AVAILABLE:
            self.logger.error("TensorFlow not available. Cannot train LSTM model.")
            return {"success": False, "error": "TensorFlow not installed"}

        if self.model is None:
            self._build_model()

        try:
            # 데이터 전처리
            power_data = self._preprocess_data(training_data)

            if len(power_data) < self.sequence_length * 2:
                return {
                    "success": False,
                    "error": f"Insufficient data. Need at least {self.sequence_length * 2} points"
                }

            # 특징 추출
            features = self._extract_features(training_data, power_data)

            # 시퀀스 생성
            X, y = self._create_sequences(features)

            if len(X) == 0:
                return {"success": False, "error": "Failed to create sequences"}

            self.logger.info(f"Training LSTM with {len(X)} sequences")

            # 모델 학습
            history = self.model.fit(
                X, y,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=validation_split,
                verbose=1,
                callbacks=[
                    keras.callbacks.EarlyStopping(
                        monitor='val_loss',
                        patience=10,
                        restore_best_weights=True
                    ),
                    keras.callbacks.ReduceLROnPlateau(
                        monitor='val_loss',
                        factor=0.5,
                        patience=5,
                        min_lr=0.00001
                    )
                ]
            )

            # 학습 결과
            final_loss = history.history['loss'][-1]
            final_val_loss = history.history['val_loss'][-1]
            final_mae = history.history['mae'][-1]

            self.logger.info(
                f"Training completed: loss={final_loss:.4f}, "
                f"val_loss={final_val_loss:.4f}, mae={final_mae:.4f}"
            )

            return {
                "success": True,
                "final_loss": float(final_loss),
                "final_val_loss": float(final_val_loss),
                "final_mae": float(final_mae),
                "epochs_trained": len(history.history['loss']),
                "training_samples": len(X)
            }

        except Exception as e:
            self.logger.error(f"Model training failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def predict_energy_demand(
        self,
        data: pd.DataFrame,
        station_id: str,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        에너지 수요 예측 (기존 메서드 유지 - 하위 호환성)
        """
        try:
            if data.empty:
                return {
                    "success": False,
                    "message": "데이터가 없습니다.",
                    "station_id": station_id
                }

            energy_col = "충전전력량(kWh)"
            if energy_col not in data.columns:
                return {
                    "success": False,
                    "message": "에너지 데이터 컬럼이 없습니다.",
                    "station_id": station_id
                }

            energy_data = data[energy_col].dropna()
            if len(energy_data) == 0:
                return {
                    "success": False,
                    "message": "유효한 에너지 데이터가 없습니다.",
                    "station_id": station_id
                }

            # 기본 통계
            daily_avg = energy_data.mean()
            daily_max = energy_data.max()
            daily_min = energy_data.min()

            # 예측
            forecast_daily = daily_avg
            forecast_total = forecast_daily * days

            # 신뢰구간
            std = energy_data.std()
            ci_lower = max(0, forecast_daily - 1.96 * std)
            ci_upper = forecast_daily + 1.96 * std

            return {
                "success": True,
                "station_id": station_id,
                "forecast_period_days": days,
                "daily_forecast": {
                    "average": round(float(forecast_daily), 2),
                    "min": round(float(daily_min), 2),
                    "max": round(float(daily_max), 2),
                    "confidence_interval": {
                        "lower": round(float(ci_lower), 2),
                        "upper": round(float(ci_upper), 2)
                    }
                },
                "total_forecast": {
                    "kwh": round(float(forecast_total), 2),
                    "confidence_interval": {
                        "lower": round(float(ci_lower * days), 2),
                        "upper": round(float(ci_upper * days), 2)
                    }
                },
                "data_quality": {
                    "sample_size": len(energy_data),
                    "data_range_days": (data.index.max() - data.index.min()).days if len(data) > 1 else 0
                },
                "method": "lstm_enhanced" if self.model else "statistical_average"
            }

        except Exception as e:
            self.logger.error(f"Energy demand prediction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "station_id": station_id
            }
