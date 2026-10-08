import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
from scipy import stats
from .prediction_types import ModelPrediction


@dataclass
class PatternFactors:
    """Simplified pattern factors"""
    seasonal_factor: float = 1.0
    weekly_factor: float = 1.0
    trend_factor: float = 1.0
    confidence: float = 0.7
    data_quality: str = "medium"


class StatisticalModels:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def run_models(self, power_data: np.ndarray, base_stats: Dict[str, float], 
                   pattern_factors: Optional[PatternFactors] = None) -> List[ModelPrediction]:
        """통계적 추론 모델들을 실행합니다."""
        models = []

        try:
            # 1. Bayesian Estimation (사전 계산된 통계량 사용)
            bayesian_result = self._bayesian_estimation_optimized(power_data, base_stats)
            if bayesian_result:
                models.append(bayesian_result)

            # 2. Bootstrap Confidence Interval (축소된 반복 횟수)
            bootstrap_result = self._bootstrap_method_optimized(power_data, base_stats, n_bootstrap=200)
            if bootstrap_result:
                models.append(bootstrap_result)

            # 3. 빠른 분위수 추정 (사전 계산된 값 사용)
            fast_percentile_result = ModelPrediction(
                model_name="Fast_Percentile_95",
                predicted_value=base_stats["q95"],
                confidence_interval=(base_stats["q90"], base_stats["q99"]),
                confidence_score=0.75,
                method_details={
                    "method": "Direct Percentile",
                    "percentile": 95,
                    "description": "사전 계산된 95% 분위수 사용",
                },
            )
            models.append(fast_percentile_result)

        except Exception as e:
            self.logger.warning(f"Statistical inference models failed: {e}")

        return models

    def _bayesian_estimation_optimized(self, power_data: np.ndarray, base_stats: Dict[str, float]) -> Optional[ModelPrediction]:
        try:
            # 단순 베이지안 추정 (사전 계산된 통계량 사용)
            n = len(power_data)
            sample_mean = base_stats["mean"]
            sample_std = base_stats["std"]

            # 사전 분포: 약한 정보적 사전분포
            prior_mean = sample_mean
            prior_std = sample_std * 2  # 불확실성 반영

            # 사후 분포 계산
            posterior_precision = 1 / (prior_std**2) + n / (sample_std**2)
            posterior_var = 1 / posterior_precision
            posterior_mean = (
                prior_mean / (prior_std**2) + n * sample_mean / (sample_std**2)
            ) * posterior_var
            posterior_std = np.sqrt(posterior_var)

            # 95% 분위수 예측
            prediction = stats.norm.ppf(0.95, posterior_mean, posterior_std)

            # 신뢰구간
            ci_lower = stats.norm.ppf(0.05, posterior_mean, posterior_std)
            ci_upper = stats.norm.ppf(0.95, posterior_mean, posterior_std)

            return ModelPrediction(
                model_name="Bayesian_Normal",
                predicted_value=prediction,
                confidence_interval=(ci_lower, ci_upper),
                confidence_score=0.75,
                method_details={
                    "method": "Bayesian Estimation",
                    "prior_mean": prior_mean,
                    "prior_std": prior_std,
                    "posterior_mean": posterior_mean,
                    "posterior_std": posterior_std,
                    "sample_size": n,
                    "description": "베이지안 정규 분포 모델을 사용한 95% 분위수 추정",
                },
            )

        except Exception as e:
            self.logger.warning(f"Bayesian estimation failed: {e}")
            return None

    def _bootstrap_method_optimized(self, power_data: np.ndarray, base_stats: Dict[str, float], 
                                   n_bootstrap: int = 200) -> Optional[ModelPrediction]:
        try:
            # 병렬로 부트스트랩 실행 (속도 개선)
            np.random.seed(42)  # 재현성을 위한 시드 설정
            bootstrap_predictions = np.random.choice(
                power_data, size=(n_bootstrap, len(power_data)), replace=True
            )
            # 백터화된 연산으로 95% 분위수 계산
            bootstrap_percentiles = np.percentile(bootstrap_predictions, 95, axis=1)

            # 부트스트랩 예측값들의 평균
            prediction = np.mean(bootstrap_percentiles)

            # 신뢰구간 (부트스트랩 분위수 방법)
            ci_lower = np.percentile(bootstrap_percentiles, 5)
            ci_upper = np.percentile(bootstrap_percentiles, 95)

            return ModelPrediction(
                model_name="Bootstrap_95th_Percentile",
                predicted_value=prediction,
                confidence_interval=(ci_lower, ci_upper),
                confidence_score=0.80,
                method_details={
                    "method": "Bootstrap",
                    "n_bootstrap": n_bootstrap,
                    "target_percentile": 95,
                    "bootstrap_std": np.std(bootstrap_percentiles),
                    "description": f"{n_bootstrap}회 부트스트랩을 통한 95% 분위수 추정",
                },
            )

        except Exception as e:
            self.logger.warning(f"Bootstrap method failed: {e}")
            return None

    def quantile_regression(self, power_data: np.ndarray) -> Optional[ModelPrediction]:
        try:
            from scipy.optimize import minimize

            # 시간 인덱스 생성 (단순 선형 추세 가정)
            x = np.arange(len(power_data))
            y = power_data

            def quantile_loss(theta, quantile=0.95):
                residuals = y - (theta[0] + theta[1] * x)
                return np.sum(
                    np.maximum(quantile * residuals, (quantile - 1) * residuals)
                )

            # 95% 분위수 회귀
            # 초기값: OLS 추정치
            ols_slope = np.polyfit(x, y, 1)[0]
            ols_intercept = np.polyfit(x, y, 1)[1]

            result = minimize(
                lambda theta: quantile_loss(theta, 0.95),
                x0=[ols_intercept, ols_slope],
                method="Nelder-Mead",
            )

            if result.success:
                intercept, slope = result.x
                # 미래 예측 (다음 시점)
                prediction = intercept + slope * len(power_data)

                # R-squared 근사 계산
                fitted_values = intercept + slope * x
                ss_res = np.sum((y - fitted_values) ** 2)
                ss_tot = np.sum((y - np.mean(y)) ** 2)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

                # 신뢰구간 추정 (잔차 기반)
                residuals = y - fitted_values
                residual_std = np.std(residuals)
                ci_lower = prediction - 1.96 * residual_std
                ci_upper = prediction + 1.96 * residual_std

                return ModelPrediction(
                    model_name="Quantile_Regression_95",
                    predicted_value=prediction,
                    confidence_interval=(ci_lower, ci_upper),
                    confidence_score=0.70,
                    r_squared=r_squared,
                    method_details={
                        "method": "Quantile Regression",
                        "quantile": 0.95,
                        "intercept": intercept,
                        "slope": slope,
                        "description": "95% 분위수 회귀를 통한 추세 기반 예측",
                    },
                )

        except Exception as e:
            self.logger.debug(f"Quantile regression failed: {e}")
            return None

    def robust_statistics_method(self, power_data: np.ndarray) -> Optional[ModelPrediction]:
        """Robust statistical method using median and MAD."""
        try:
            # Median Absolute Deviation (MAD) 계산
            median = np.median(power_data)
            mad = np.median(np.abs(power_data - median))
            
            # MAD를 표준편차로 변환 (정규분포 가정)
            mad_std = mad * 1.4826
            
            # Robust 95% 분위수 추정
            # 정규분포 가정하에서 median + 1.645 * robust_std
            prediction = median + stats.norm.ppf(0.95) * mad_std
            
            # 신뢰구간
            ci_lower = median + stats.norm.ppf(0.85) * mad_std
            ci_upper = median + stats.norm.ppf(0.995) * mad_std
            
            # 이상치 비율 계산
            outlier_threshold = median + 3 * mad_std
            outlier_ratio = np.sum(power_data > outlier_threshold) / len(power_data)
            
            # 신뢰도 계산 (이상치가 적을수록 신뢰도 높음)
            confidence = max(0.5, 0.9 - outlier_ratio * 2)
            
            return ModelPrediction(
                model_name="Robust_Statistics_MAD",
                predicted_value=prediction,
                confidence_interval=(ci_lower, ci_upper),
                confidence_score=confidence,
                method_details={
                    "method": "Robust Statistics with MAD",
                    "median": median,
                    "mad": mad,
                    "robust_std": mad_std,
                    "outlier_ratio": outlier_ratio,
                    "description": "중위수와 MAD를 이용한 강건한 95% 분위수 추정",
                },
            )
            
        except Exception as e:
            self.logger.debug(f"Robust statistics method failed: {e}")
            return None