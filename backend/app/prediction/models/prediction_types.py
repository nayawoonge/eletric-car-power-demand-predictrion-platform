from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PatternFactors:
    """Simplified pattern factors"""
    seasonal_factor: float = 1.0
    weekly_factor: float = 1.0
    trend_factor: float = 1.0
    confidence: float = 0.7
    data_quality: str = "medium"
    calculation_metadata: Dict[str, Any] = None


@dataclass
class ModelPrediction:
    model_name: str
    predicted_value: float
    confidence_interval: Tuple[float, float]
    confidence_score: float
    method_details: Dict[str, Any]
    r_squared: Optional[float] = None
    rmse: Optional[float] = None


@dataclass
class EnsemblePrediction:
    final_prediction: int  # 제한 적용된 최종 예측값
    raw_prediction: float  # 제한 없는 원본 예측값
    model_predictions: List[ModelPrediction]
    ensemble_method: str
    weights: Dict[str, float]
    uncertainty: float
    visualization_data: Dict[str, Any]
    pattern_factors: Optional[PatternFactors] = None  # Dynamic pattern information
    method_comparison: Optional[Dict[str, Any]] = None  # Comparison between methods