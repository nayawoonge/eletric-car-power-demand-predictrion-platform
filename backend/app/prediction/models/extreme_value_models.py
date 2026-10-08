import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
import logging
from scipy.stats import genextreme, gumbel_r, weibull_min
from .prediction_types import ModelPrediction


class ExtremeValueModels:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def run_models(self, power_data: np.ndarray, base_stats: Dict[str, float]) -> List[ModelPrediction]:
        """극값 분포 모델들을 실행합니다."""
        models = []

        # 데이터 기반 상한: 실제 관측 최대값의 115% (관측 범위를 크게 벗어나지 않도록)
        observed_max = base_stats["max"]
        data_based_cap = observed_max * 1.15

        try:
            # 1. Generalized Extreme Value (GEV) Distribution
            gev_params = genextreme.fit(
                power_data, loc=base_stats["mean"], scale=base_stats["std"]
            )
            gev_prediction = genextreme.ppf(0.95, *gev_params)  # 95% 분위수
            
            # 비정상적인 예측값 검증 및 데이터 기반 상한 적용
            if not np.isfinite(gev_prediction) or gev_prediction < 0:
                self.logger.warning(f"GEV 예측값이 비정상적입니다: {gev_prediction}, 기본값으로 대체")
                gev_prediction = base_stats["q95"]
            elif gev_prediction > data_based_cap:
                self.logger.info(
                    f"GEV 예측값 {gev_prediction:.1f}kW가 데이터 기반 상한 "
                    f"{data_based_cap:.1f}kW(관측최대 {observed_max:.1f}kW * 1.15)를 초과하여 클리핑"
                )
                gev_prediction = data_based_cap
            
            gev_ci = (base_stats["q90"], min(base_stats["q99"], data_based_cap))

            models.append(
                ModelPrediction(
                    model_name="GEV_Distribution",
                    predicted_value=gev_prediction,
                    confidence_interval=gev_ci,
                    confidence_score=0.85,
                    method_details={
                        "distribution": "Generalized Extreme Value",
                        "parameters": gev_params,
                        "percentile": 95,
                        "data_based_cap": data_based_cap,
                        "description": "일반화 극값 분포를 사용한 극값 추정",
                    },
                )
            )

            # 2. Gumbel Distribution
            gumbel_params = gumbel_r.fit(
                power_data, loc=base_stats["mean"], scale=base_stats["std"]
            )
            gumbel_prediction = gumbel_r.ppf(0.95, *gumbel_params)
            
            # 비정상적인 예측값 검증 및 데이터 기반 상한 적용
            if not np.isfinite(gumbel_prediction) or gumbel_prediction < 0:
                self.logger.warning(f"Gumbel 예측값이 비정상적입니다: {gumbel_prediction}, 기본값으로 대체")
                gumbel_prediction = base_stats["q95"]
            elif gumbel_prediction > data_based_cap:
                self.logger.info(
                    f"Gumbel 예측값 {gumbel_prediction:.1f}kW가 데이터 기반 상한 "
                    f"{data_based_cap:.1f}kW를 초과하여 클리핑"
                )
                gumbel_prediction = data_based_cap
            
            gumbel_ci = (
                base_stats.get("q85", base_stats["q90"] * 0.95),
                base_stats.get("q98", base_stats["q95"] * 1.02),
            )

            models.append(
                ModelPrediction(
                    model_name="Gumbel_Distribution",
                    predicted_value=gumbel_prediction,
                    confidence_interval=gumbel_ci,
                    confidence_score=0.80,
                    method_details={
                        "distribution": "Gumbel",
                        "parameters": gumbel_params,
                        "percentile": 95,
                        "description": "검벨 분포를 사용한 극값 추정",
                    },
                )
            )

            # 3. Block Maxima Method
            block_maxima = self._block_maxima_method(power_data, data_based_cap=data_based_cap)
            if block_maxima:
                models.append(block_maxima)

            # 4. Peak Over Threshold (POT) Method
            pot_result = self._peak_over_threshold_method(power_data, data_based_cap=data_based_cap)
            if pot_result:
                models.append(pot_result)

        except Exception as e:
            self.logger.warning(f"Extreme value models failed: {e}")

        return models

    def _block_maxima_method(self, power_data: np.ndarray, block_size: int = 30, data_based_cap: float = None) -> Optional[ModelPrediction]:
        """블록 최대값 방법을 사용한 극값 예측."""
        try:
            if len(power_data) < block_size * 3:  # 최소 3개 블록 필요
                return None

            # 데이터를 블록으로 나누고 각 블록의 최대값 추출
            n_blocks = len(power_data) // block_size
            blocks = np.array_split(power_data[:n_blocks * block_size], n_blocks)
            block_maxima = np.array([np.max(block) for block in blocks])

            if len(block_maxima) < 3:
                return None

            # GEV 분포 피팅
            params = genextreme.fit(block_maxima)
            
            # 예측값 계산 (95% 분위수)
            predicted_max = genextreme.ppf(0.95, *params)
            
            # 신뢰구간 추정
            ci_lower = genextreme.ppf(0.85, *params)
            ci_upper = genextreme.ppf(0.995, *params)
            
            # 검증
            if not np.isfinite(predicted_max) or predicted_max < 0:
                return None

            # 데이터 기반 상한 적용
            if data_based_cap is not None and predicted_max > data_based_cap:
                self.logger.info(
                    f"Block Maxima 예측값 {predicted_max:.1f}kW가 데이터 기반 상한 "
                    f"{data_based_cap:.1f}kW를 초과하여 클리핑"
                )
                predicted_max = data_based_cap
                ci_upper = min(ci_upper, data_based_cap)

            # 신뢰도 계산 (블록 개수가 많을수록 신뢰도 높음)
            confidence = min(0.9, 0.5 + len(block_maxima) * 0.05)

            return ModelPrediction(
                model_name="Block_Maxima_GEV",
                predicted_value=float(predicted_max),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=confidence,
                method_details={
                    "method": "Block Maxima with GEV fitting",
                    "block_size": block_size,
                    "n_blocks": len(block_maxima),
                    "gev_parameters": params,
                    "description": f"{block_size}일 블록 최대값을 이용한 GEV 피팅",
                },
            )

        except Exception as e:
            self.logger.debug(f"Block maxima method failed: {e}")
            return None

    def _peak_over_threshold_method(self, power_data: np.ndarray, threshold_percentile: float = 90, data_based_cap: float = None) -> Optional[ModelPrediction]:
        """Peak Over Threshold (POT) 방법을 사용한 극값 예측."""
        try:
            # 임계값 설정 (90% 분위수)
            threshold = np.percentile(power_data, threshold_percentile)
            
            # 임계값을 초과하는 값들 추출
            exceedances = power_data[power_data > threshold] - threshold
            
            if len(exceedances) < 10:  # 최소 10개의 초과값 필요
                return None

            # Generalized Pareto Distribution 피팅 (scipy.stats에서 제공)
            # 파라미터 추정을 위해 직접 구현
            mean_excess = np.mean(exceedances)
            std_excess = np.std(exceedances)
            
            if std_excess == 0:
                return None

            # 간단한 지수분포 근사 (GPD의 특수한 경우)
            # lambda = 1 / mean_excess
            lambda_param = 1.0 / mean_excess if mean_excess > 0 else 1.0
            
            # Return level 계산
            n_exceedances = len(exceedances)
            n_total = len(power_data)
            exceedance_rate = n_exceedances / n_total
            
            # 95% 분위수에 해당하는 return level
            return_period = 1.0 / (1 - 0.95)  # 20년 return period for 95% quantile
            expected_exceedances = exceedance_rate * return_period
            
            if expected_exceedances <= 0:
                return None
                
            # 지수분포 가정하에서의 return level
            return_level = threshold + (-np.log(1 - (1 / expected_exceedances)) / lambda_param)
            
            # 신뢰구간 추정 (부트스트랩 근사)
            ci_lower = threshold + mean_excess * 0.5
            ci_upper = threshold + mean_excess * 2.5
            
            # 검증
            if not np.isfinite(return_level) or return_level < threshold:
                return None

            # 신뢰도 계산
            confidence = min(0.85, 0.4 + (n_exceedances / 100.0))

            return ModelPrediction(
                model_name="Peak_Over_Threshold",
                predicted_value=float(return_level),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=confidence,
                method_details={
                    "method": "Peak Over Threshold with Exponential approximation",
                    "threshold": float(threshold),
                    "threshold_percentile": threshold_percentile,
                    "n_exceedances": n_exceedances,
                    "exceedance_rate": exceedance_rate,
                    "lambda": lambda_param,
                    "description": f"{threshold_percentile}% 분위수를 임계값으로 하는 POT 방법",
                },
            )

        except Exception as e:
            self.logger.debug(f"Peak over threshold method failed: {e}")
            return None