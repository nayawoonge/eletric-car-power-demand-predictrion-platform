import numpy as np
from typing import List, Dict, Any, Optional
from scipy.stats import genextreme, gumbel_r, genpareto
from .base import BasePredictor, ModelPrediction

class ExtremeValueModels(BasePredictor):
    """Extreme Value Theory based prediction models"""
    
    def predict_all(self, power_data: np.ndarray, base_stats: Dict[str, float]) -> List[ModelPrediction]:
        """Run all extreme value models"""
        models = []
        
        if not self._validate_input(power_data):
            return models
        
        # GEV Distribution
        gev_result = self._safe_execute(self._gev_prediction, power_data, base_stats)
        if gev_result:
            models.append(gev_result)
        
        # Gumbel Distribution  
        gumbel_result = self._safe_execute(self._gumbel_prediction, power_data, base_stats)
        if gumbel_result:
            models.append(gumbel_result)
        
        # Block Maxima Method
        block_result = self._safe_execute(self._block_maxima_method, power_data)
        if block_result:
            models.append(block_result)
        
        # Peak Over Threshold
        pot_result = self._safe_execute(self._peak_over_threshold_method, power_data)
        if pot_result:
            models.append(pot_result)
            
        return models
    
    def _gev_prediction(self, power_data: np.ndarray, base_stats: Dict[str, float]) -> ModelPrediction:
        """Generalized Extreme Value Distribution prediction"""
        params = genextreme.fit(power_data, loc=base_stats["mean"], scale=base_stats["std"])
        prediction = genextreme.ppf(0.95, *params)
        
        # Validation
        if not np.isfinite(prediction) or prediction < 0 or prediction > 10000:
            self.logger.warning(f"GEV prediction abnormal: {prediction}, using fallback")
            prediction = min(base_stats["q95"], 100)
        
        ci = (base_stats["q90"], base_stats["q99"])
        
        return self._create_prediction(
            "GEV_Distribution",
            prediction,
            ci[0], ci[1],
            0.85,
            {
                "distribution": "Generalized Extreme Value",
                "parameters": params,
                "percentile": 95,
                "description": "일반화 극값 분포를 사용한 극값 추정"
            }
        )
    
    def _gumbel_prediction(self, power_data: np.ndarray, base_stats: Dict[str, float]) -> ModelPrediction:
        """Gumbel Distribution prediction"""
        params = gumbel_r.fit(power_data, loc=base_stats["mean"], scale=base_stats["std"])
        prediction = gumbel_r.ppf(0.95, *params)
        
        # Validation
        if not np.isfinite(prediction) or prediction < 0 or prediction > 10000:
            self.logger.warning(f"Gumbel prediction abnormal: {prediction}, using fallback")
            prediction = min(base_stats["q95"], 100)
        
        ci = (
            base_stats.get("q85", base_stats["q90"] * 0.95),
            base_stats.get("q98", base_stats["q95"] * 1.02)
        )
        
        return self._create_prediction(
            "Gumbel_Distribution",
            prediction,
            ci[0], ci[1],
            0.80,
            {
                "distribution": "Gumbel",
                "parameters": params,
                "percentile": 95,
                "description": "검벨 분포를 사용한 극값 추정"
            }
        )
    
    def _block_maxima_method(self, power_data: np.ndarray, block_size: int = 30) -> Optional[ModelPrediction]:
        """Block Maxima Method"""
        if len(power_data) < block_size * 2:
            return None
        
        # Extract block maxima
        blocks = [power_data[i:i + block_size] for i in range(0, len(power_data), block_size)]
        block_maxima = [np.max(block) for block in blocks if len(block) == block_size]
        
        if len(block_maxima) < 3:
            return None
        
        # Fit GEV distribution
        params = genextreme.fit(block_maxima)
        prediction = genextreme.ppf(0.95, *params)
        
        # Validation
        if not np.isfinite(prediction) or prediction < 0 or prediction > 10000:
            self.logger.warning(f"Block Maxima prediction abnormal: {prediction}, using fallback")
            prediction = min(np.percentile(block_maxima, 95), 100)
        
        ci = genextreme.interval(0.9, *params)
        if not (np.isfinite(ci[0]) and np.isfinite(ci[1])):
            ci = (prediction * 0.9, prediction * 1.1)
        
        return self._create_prediction(
            "Block_Maxima_GEV",
            prediction,
            ci[0], ci[1],
            0.85,
            {
                "method": "Block Maxima with GEV",
                "block_size": block_size,
                "num_blocks": len(block_maxima),
                "gev_parameters": params,
                "description": f"블록 크기 {block_size}의 최대값을 GEV 분포에 피팅"
            }
        )
    
    def _peak_over_threshold_method(self, power_data: np.ndarray) -> Optional[ModelPrediction]:
        """Peak Over Threshold Method"""
        threshold = np.percentile(power_data, 90)
        excesses = power_data[power_data > threshold] - threshold
        
        if len(excesses) < 10:
            return None
        
        # Fit Generalized Pareto Distribution
        params = genpareto.fit(excesses)
        prediction = threshold + genpareto.ppf(0.95, *params)
        
        # Validation
        if not np.isfinite(prediction) or prediction < 0 or prediction > 10000:
            self.logger.warning(f"POT prediction abnormal: {prediction}, using fallback")
            prediction = min(np.percentile(power_data, 95), 100)
        
        # Confidence interval
        lower = threshold + genpareto.ppf(0.05, *params)
        upper = threshold + genpareto.ppf(0.99, *params)
        
        if not (np.isfinite(lower) and np.isfinite(upper)):
            lower = prediction * 0.9
            upper = prediction * 1.1
        
        return self._create_prediction(
            "Peak_Over_Threshold",
            prediction,
            lower, upper,
            0.80,
            {
                "method": "Peak Over Threshold",
                "threshold": threshold,
                "num_excesses": len(excesses),
                "pareto_parameters": params,
                "description": f"임계값 {threshold:.1f}kW 초과 데이터의 일반화 파레토 분포 피팅"
            }
        )