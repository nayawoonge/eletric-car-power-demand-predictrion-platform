import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import warnings

from .models.prediction_types import ModelPrediction, EnsemblePrediction
from .models.extreme_value_models import ExtremeValueModels
from .models.statistical_models import StatisticalModels
from .models.time_series_models import TimeSeriesModels

warnings.filterwarnings("ignore")


@dataclass
class PatternFactors:
    """Simplified pattern factors"""
    seasonal_factor: float = 1.0
    weekly_factor: float = 1.0
    trend_factor: float = 1.0
    confidence: float = 0.7
    data_quality: str = "medium"
    calculation_metadata: Dict[str, Any] = None


class PredictionEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.max_contract_power = 100  # 최대 계약 전력 100kW
        self.max_workers = 4  # 병렬 처리 스레드 수
        self._stats_cache = {}  # 기본 통계량 캐시
        
        # Model runners
        self.extreme_value_models = ExtremeValueModels()
        self.statistical_models = StatisticalModels()
        self.time_series_models = TimeSeriesModels()

        # 충전기 타입별 최대 전력 제한
        self.charger_limits = {
            "완속충전기 (AC)": 7,  # 완속은 최대 7kW
            "급속충전기 (DC)": 100,  # 급속은 최대 100kW
            "미상": 50,  # 미상인 경우 보수적으로 50kW
        }

    def predict_contract_power(
        self, data: pd.DataFrame, station_id: str, charger_type: str = None
    ) -> EnsemblePrediction:
        start_time = time.time()

        if data.empty or "순간최고전력" not in data.columns:
            return self._fallback_prediction(station_id)

        # 데이터 전처리 및 기본 통계량 계산
        power_data = self._preprocess_data(data)

        if len(power_data) < 10:
            return self._fallback_prediction(station_id)

        # 기본 통계량 사전 계산 (캐싱)
        cache_key = hash(power_data.tobytes())
        if cache_key not in self._stats_cache:
            self._stats_cache[cache_key] = self._compute_base_statistics(power_data)

        base_stats = self._stats_cache[cache_key]
        
        # Simplified pattern factors (no complex analysis)
        pattern_factors = PatternFactors(
            seasonal_factor=1.0,
            weekly_factor=1.0,
            trend_factor=1.0,
            confidence=0.7,
            data_quality="medium"
        )

        # 모든 모델 실행
        model_predictions = []

        try:
            # 병렬로 모든 모델 실행
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                # Extreme Value Models
                futures.append(
                    executor.submit(self.extreme_value_models.run_models, power_data, base_stats)
                )
                
                # Statistical Models  
                futures.append(
                    executor.submit(self.statistical_models.run_models, power_data, base_stats, pattern_factors)
                )
                
                # Time Series Models
                futures.append(
                    executor.submit(self.time_series_models.run_models, data, pattern_factors)
                )

                # 결과 수집
                for future in as_completed(futures):
                    try:
                        results = future.result(timeout=30)
                        model_predictions.extend(results)
                    except Exception as e:
                        self.logger.warning(f"Model execution failed: {e}")

        except Exception as e:
            self.logger.error(f"Parallel model execution failed: {e}")
            # 폴백: 단순 통계 기반 예측
            model_predictions.append(
                ModelPrediction(
                    model_name="Fallback_Percentile_95",
                    predicted_value=base_stats["q95"],
                    confidence_interval=(base_stats["q90"], base_stats["q99"]),
                    confidence_score=0.6,
                    method_details={"method": "Fallback", "percentile": 95},
                )
            )

        if not model_predictions:
            return self._fallback_prediction(station_id)

        # 앙상블 예측
        ensemble_result = self._ensemble_prediction(model_predictions, pattern_factors)
        
        # 충전기 타입 제한 적용
        if charger_type and charger_type in self.charger_limits:
            max_limit = self.charger_limits[charger_type]
            ensemble_result.final_prediction = min(ensemble_result.final_prediction, max_limit)

        # 실행 시간 로깅
        execution_time = time.time() - start_time
        self.logger.info(
            f"Station {station_id}: Prediction completed in {execution_time:.2f}s, "
            f"models: {len(model_predictions)}, result: {ensemble_result.final_prediction}kW"
        )

        return ensemble_result

    def _preprocess_data(self, data: pd.DataFrame) -> np.ndarray:
        """데이터 전처리 및 이상치 제거."""
        try:
            power_data = data["순간최고전력"].values
            
            # 결측값 및 비정상값 제거
            power_data = power_data[~np.isnan(power_data)]
            power_data = power_data[power_data > 0]  # 음수 제거
            power_data = power_data[power_data < 1000]  # 명백한 이상치 제거
            
            # IQR 기반 이상치 제거
            if len(power_data) > 10:
                Q1, Q3 = np.percentile(power_data, [25, 75])
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                power_data = power_data[(power_data >= lower_bound) & (power_data <= upper_bound)]
            
            return power_data
            
        except Exception as e:
            self.logger.error(f"Data preprocessing failed: {e}")
            return np.array([])

    def _compute_base_statistics(self, power_data: np.ndarray) -> Dict[str, float]:
        """기본 통계량 계산."""
        try:
            return {
                "mean": np.mean(power_data),
                "std": np.std(power_data),
                "min": np.min(power_data),
                "max": np.max(power_data),
                "q25": np.percentile(power_data, 25),
                "q50": np.percentile(power_data, 50),
                "q75": np.percentile(power_data, 75),
                "q85": np.percentile(power_data, 85),
                "q90": np.percentile(power_data, 90),
                "q95": np.percentile(power_data, 95),
                "q98": np.percentile(power_data, 98),
                "q99": np.percentile(power_data, 99),
            }
        except Exception:
            # 기본값 반환
            return {
                "mean": 45.0, "std": 15.0, "min": 0.0, "max": 100.0,
                "q25": 35.0, "q50": 45.0, "q75": 55.0, "q85": 60.0,
                "q90": 65.0, "q95": 70.0, "q98": 75.0, "q99": 80.0
            }

    def _ensemble_prediction(self, predictions: List[ModelPrediction], 
                           pattern_factors: Optional[PatternFactors] = None) -> EnsemblePrediction:
        """앙상블 예측 수행."""
        if not predictions:
            raise ValueError("No predictions available for ensemble")

        # 가중치 계산 (신뢰도 기반)
        weights = {}
        total_confidence = sum(p.confidence_score for p in predictions)
        
        for pred in predictions:
            normalized_weight = pred.confidence_score / total_confidence if total_confidence > 0 else 1.0 / len(predictions)
            weights[pred.model_name] = normalized_weight

        # 가중 평균 계산
        weighted_prediction = sum(
            pred.predicted_value * weights[pred.model_name] for pred in predictions
        )

        # 불확실성 계산
        prediction_variance = sum(
            weights[pred.model_name] * (pred.predicted_value - weighted_prediction) ** 2
            for pred in predictions
        )
        uncertainty = np.sqrt(prediction_variance) if prediction_variance > 0 else 10.0

        # 시각화 데이터 준비
        visualization_data = self._prepare_visualization_data(predictions, weighted_prediction)

        # 제한 적용
        raw_prediction = weighted_prediction
        final_prediction = min(int(np.ceil(raw_prediction)), self.max_contract_power)

        return EnsemblePrediction(
            final_prediction=final_prediction,
            raw_prediction=raw_prediction,
            model_predictions=predictions,
            ensemble_method="weighted_average_by_confidence",
            weights=weights,
            uncertainty=uncertainty,
            visualization_data=visualization_data,
            pattern_factors=pattern_factors,
        )

    def _prepare_visualization_data(self, predictions: List[ModelPrediction], 
                                  ensemble_prediction: float) -> Dict[str, Any]:
        """시각화용 데이터 준비."""
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

    def predict_energy_demand(
        self, data: pd.DataFrame, station_id: str, days: int = 90
    ) -> Dict[str, Any]:
        """
        에너지 수요 예측

        Args:
            data: 충전소 데이터
            station_id: 충전소 ID
            days: 예측 기간 (일)

        Returns:
            에너지 수요 예측 결과
        """
        try:
            if data.empty:
                return {
                    "success": False,
                    "message": "데이터가 없습니다.",
                    "station_id": station_id
                }

            # 에너지 컬럼 확인
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

            # 예측 (간단한 평균 기반)
            forecast_daily = daily_avg
            forecast_total = forecast_daily * days

            # 신뢰구간 (표준편차 기반)
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
                "method": "statistical_average"
            }

        except Exception as e:
            self.logger.error(f"Energy demand prediction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "station_id": station_id
            }

    def _fallback_prediction(self, station_id: str) -> EnsemblePrediction:
        """폴백 예측 (데이터가 부족한 경우)."""
        self.logger.warning(f"Using fallback prediction for station {station_id}")

        fallback_prediction = ModelPrediction(
            model_name="Fallback_Default",
            predicted_value=45.0,
            confidence_interval=(35.0, 55.0),
            confidence_score=0.3,
            method_details={
                "method": "Default Fallback",
                "reason": "Insufficient data",
                "description": "기본값 사용 (데이터 부족)",
            },
        )

        return EnsemblePrediction(
            final_prediction=45,
            raw_prediction=45.0,
            model_predictions=[fallback_prediction],
            ensemble_method="fallback",
            weights={"Fallback_Default": 1.0},
            uncertainty=20.0,
            visualization_data=self._prepare_visualization_data([fallback_prediction], 45.0),
        )