from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional

@dataclass
class ModelPrediction:
    """Base prediction result from individual models"""
    model_name: str
    predicted_value: float
    confidence_interval: Tuple[float, float]
    confidence_score: float
    method_details: Dict[str, Any]
    r_squared: Optional[float] = None
    rmse: Optional[float] = None

class BasePredictor:
    """Base class for all prediction models"""
    
    def __init__(self, logger=None):
        self.logger = logger or self._get_default_logger()
    
    def _get_default_logger(self):
        import logging
        return logging.getLogger(__name__)
    
    def _validate_input(self, data, min_points=10):
        """Validate input data"""
        if data is None:
            return False
        if hasattr(data, '__len__') and len(data) < min_points:
            return False
        return True
    
    def _safe_execute(self, func, *args, **kwargs):
        """Safely execute a function with error handling"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.logger.warning(f"Model execution failed: {e}")
            return None
    
    def _create_prediction(self, name, value, ci_lower, ci_upper, 
                          confidence, details):
        """Helper to create ModelPrediction objects"""
        return ModelPrediction(
            model_name=name,
            predicted_value=value,
            confidence_interval=(ci_lower, ci_upper),
            confidence_score=confidence,
            method_details=details
        )