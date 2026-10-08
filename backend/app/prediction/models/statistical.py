import numpy as np
from typing import List, Dict, Any, Optional
from scipy import stats
from ..dynamic_patterns import PatternFactors
from .base import BasePredictor, ModelPrediction

class StatisticalModels(BasePredictor):
    """Statistical inference based prediction models"""
    
    def predict_all(self, power_data: np.ndarray, base_stats: Dict[str, float], 
                   pattern_factors: Optional[PatternFactors] = None) -> List[ModelPrediction]:
        """Run all statistical models"""
        models = []
        
        if not self._validate_input(power_data):
            return models
        
        # Dynamic Pattern Prediction (highest priority if available)
        if pattern_factors and pattern_factors.confidence > 0.4:
            pattern_result = self._safe_execute(
                self._dynamic_pattern_prediction, power_data, pattern_factors, base_stats
            )
            if pattern_result:
                models.append(pattern_result)
        
        # Bayesian Estimation
        bayesian_result = self._safe_execute(
            self._bayesian_estimation, power_data, base_stats
        )
        if bayesian_result:
            models.append(bayesian_result)
        
        # Pattern-Enhanced Bayesian (if patterns available)
        if pattern_factors and pattern_factors.confidence > 0.5:
            pattern_bayesian_result = self._safe_execute(
                self._pattern_enhanced_bayesian, power_data, base_stats, pattern_factors
            )
            if pattern_bayesian_result:
                models.append(pattern_bayesian_result)
        
        # Bootstrap Method
        bootstrap_result = self._safe_execute(
            self._bootstrap_method, power_data, base_stats
        )
        if bootstrap_result:
            models.append(bootstrap_result)
        
        # Fast Percentile
        fast_percentile = self._create_prediction(
            "Fast_Percentile_95",
            base_stats["q95"],
            base_stats["q90"], base_stats["q99"],
            0.75,
            {
                "method": "Direct Percentile",
                "percentile": 95,
                "description": "사전 계산된 95% 분위수 사용"
            }
        )
        models.append(fast_percentile)
        
        return models
    
    def _dynamic_pattern_prediction(self, power_data: np.ndarray, pattern_factors: PatternFactors,
                                   base_stats: Dict[str, float]) -> ModelPrediction:
        """Generate prediction based on dynamic pattern analysis"""
        from ..dynamic_patterns import DynamicPatternAnalyzer
        
        # Base prediction using 95th percentile
        base_prediction = base_stats["q95"]
        
        # Apply pattern adjustments
        analyzer = DynamicPatternAnalyzer()
        adjusted_prediction = analyzer.apply_pattern_adjustment(base_prediction, pattern_factors)
        
        # Calculate confidence interval based on pattern quality
        pattern_confidence = pattern_factors.confidence
        spread = base_prediction * (0.1 + (1 - pattern_confidence) * 0.2)
        
        ci_lower = adjusted_prediction - spread
        ci_upper = adjusted_prediction + spread
        
        # Enhanced confidence score
        model_confidence = min(0.95, pattern_confidence * 1.2)
        
        return self._create_prediction(
            "Dynamic_Pattern_Adaptive",
            adjusted_prediction,
            ci_lower, ci_upper,
            model_confidence,
            {
                "method": "Dynamic Pattern Analysis",
                "base_prediction": base_prediction,
                "adjusted_prediction": adjusted_prediction,
                "pattern_confidence": pattern_confidence,
                "seasonal_applied": len(pattern_factors.seasonal_factors) > 0,
                "weekly_applied": len(pattern_factors.weekly_factors) > 0,
                "trend_applied": abs(pattern_factors.trend_factor - 1.0) > 0.05,
                "data_quality": pattern_factors.data_quality,
                "description": "실제 데이터 패턴을 학습하여 적응형 예측 수행"
            }
        )
    
    def _bayesian_estimation(self, power_data: np.ndarray, base_stats: Dict[str, float]) -> ModelPrediction:
        """Simple Bayesian estimation"""
        n = len(power_data)
        sample_mean = base_stats["mean"]
        sample_std = base_stats["std"]
        
        # Weak informative prior
        prior_mean = sample_mean
        prior_std = sample_std * 2
        
        # Posterior calculation
        posterior_precision = 1 / (prior_std**2) + n / (sample_std**2)
        posterior_var = 1 / posterior_precision
        posterior_mean = (
            prior_mean / (prior_std**2) + n * sample_mean / (sample_std**2)
        ) * posterior_var
        posterior_std = np.sqrt(posterior_var)
        
        # 95% quantile prediction
        prediction = stats.norm.ppf(0.95, posterior_mean, posterior_std)
        
        # Confidence interval
        ci_lower = stats.norm.ppf(0.05, posterior_mean, posterior_std)
        ci_upper = stats.norm.ppf(0.95, posterior_mean, posterior_std)
        
        return self._create_prediction(
            "Bayesian_Normal",
            prediction,
            ci_lower, ci_upper,
            0.75,
            {
                "method": "Bayesian Estimation",
                "prior_mean": prior_mean,
                "prior_std": prior_std,
                "posterior_mean": posterior_mean,
                "posterior_std": posterior_std,
                "sample_size": n,
                "description": "베이지안 정규 분포 모델을 사용한 95% 분위수 추정"
            }
        )
    
    def _pattern_enhanced_bayesian(self, power_data: np.ndarray, base_stats: Dict[str, float],
                                  pattern_factors: PatternFactors) -> ModelPrediction:
        """Bayesian estimation enhanced with pattern information"""
        n = len(power_data)
        sample_mean = base_stats["mean"]
        sample_std = base_stats["std"]
        
        # Use pattern factors to inform prior
        if pattern_factors.trend_factor > 1.05:  # Increasing trend
            prior_mean = sample_mean * pattern_factors.trend_factor
        elif pattern_factors.trend_factor < 0.95:  # Decreasing trend
            prior_mean = sample_mean * pattern_factors.trend_factor
        else:
            prior_mean = sample_mean
        
        # Pattern confidence affects prior strength
        prior_strength = pattern_factors.confidence * 2.0
        prior_std = sample_std / np.sqrt(prior_strength)
        
        # Bayesian update
        posterior_precision = 1 / (prior_std**2) + n / (sample_std**2)
        posterior_var = 1 / posterior_precision
        posterior_mean = (
            prior_mean / (prior_std**2) + n * sample_mean / (sample_std**2)
        ) * posterior_var
        posterior_std = np.sqrt(posterior_var)
        
        # 95% quantile prediction
        prediction = stats.norm.ppf(0.95, posterior_mean, posterior_std)
        
        # Apply final pattern adjustment
        from ..dynamic_patterns import DynamicPatternAnalyzer
        analyzer = DynamicPatternAnalyzer()
        adjusted_prediction = analyzer.apply_pattern_adjustment(prediction, pattern_factors)
        
        # Confidence interval
        ci_lower = stats.norm.ppf(0.05, posterior_mean, posterior_std)
        ci_upper = stats.norm.ppf(0.99, posterior_mean, posterior_std)
        
        return self._create_prediction(
            "Pattern_Enhanced_Bayesian",
            adjusted_prediction,
            ci_lower, ci_upper,
            min(0.90, 0.7 + pattern_factors.confidence * 0.2),
            {
                "method": "Pattern-Enhanced Bayesian",
                "prior_mean": prior_mean,
                "posterior_mean": posterior_mean,
                "pattern_confidence": pattern_factors.confidence,
                "trend_factor": pattern_factors.trend_factor,
                "description": "패턴 정보를 활용한 베이지안 추정"
            }
        )
    
    def _bootstrap_method(self, power_data: np.ndarray, base_stats: Dict[str, float],
                         n_bootstrap: int = 200) -> ModelPrediction:
        """Bootstrap confidence interval method"""
        np.random.seed(42)  # Reproducibility
        bootstrap_predictions = np.random.choice(
            power_data, size=(n_bootstrap, len(power_data)), replace=True
        )
        # Vectorized 95th percentile calculation
        bootstrap_percentiles = np.percentile(bootstrap_predictions, 95, axis=1)
        
        # Bootstrap prediction mean
        prediction = np.mean(bootstrap_percentiles)
        
        # Confidence interval (bootstrap percentile method)
        ci_lower = np.percentile(bootstrap_percentiles, 5)
        ci_upper = np.percentile(bootstrap_percentiles, 95)
        
        return self._create_prediction(
            "Bootstrap_95th_Percentile",
            prediction,
            ci_lower, ci_upper,
            0.80,
            {
                "method": "Bootstrap",
                "n_bootstrap": n_bootstrap,
                "target_percentile": 95,
                "bootstrap_std": np.std(bootstrap_percentiles),
                "description": f"{n_bootstrap}회 부트스트랩을 통한 95% 분위수 추정"
            }
        )