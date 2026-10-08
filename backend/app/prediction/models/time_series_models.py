import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
from .prediction_types import ModelPrediction


@dataclass
class PatternFactors:
    """Simplified pattern factors"""
    seasonal_factor: float = 1.0
    weekly_factor: float = 1.0
    trend_factor: float = 1.0
    confidence: float = 0.7
    data_quality: str = "medium"


class TimeSeriesModels:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def run_models(self, data: pd.DataFrame, pattern_factors: Optional[PatternFactors] = None) -> List[ModelPrediction]:
        """시계열 모델들을 실행합니다."""
        models = []

        try:
            if "충전시작일시" in data.columns:
                # 월별 최대값 추출
                data_copy = data.copy()
                data_copy["충전시작일시"] = pd.to_datetime(
                    data_copy["충전시작일시"], errors="coerce"
                )
                data_copy = data_copy.dropna(subset=["충전시작일시", "순간최고전력"])

                # 월별 집계
                monthly_max = data_copy.groupby(
                    data_copy["충전시작일시"].dt.to_period("M")
                )["순간최고전력"].max()

                if len(monthly_max) >= 3:
                    # 1. Exponential Smoothing (Enhanced with patterns)
                    exp_smooth_result = self._exponential_smoothing(monthly_max.values, pattern_factors)
                    if exp_smooth_result:
                        models.append(exp_smooth_result)

                    # 2. Linear Trend Analysis (Enhanced with patterns)
                    trend_result = self._linear_trend_analysis(monthly_max.values, pattern_factors)
                    if trend_result:
                        models.append(trend_result)
                        
                    # 3. Pattern-Based Seasonal Adjustment
                    if pattern_factors and pattern_factors.confidence > 0.6:
                        seasonal_result = self._seasonal_pattern_prediction(monthly_max.values, pattern_factors)
                        if seasonal_result:
                            models.append(seasonal_result)

        except Exception as e:
            self.logger.warning(f"Time series models failed: {e}")

        return models

    def _exponential_smoothing(self, monthly_data: np.ndarray, 
                              pattern_factors: Optional[PatternFactors] = None) -> Optional[ModelPrediction]:
        """지수평활법을 사용한 시계열 예측."""
        try:
            if len(monthly_data) < 3:
                return None

            # Simple Exponential Smoothing (α = 0.3)
            alpha = 0.3
            
            # Pattern-based adjustment
            if pattern_factors and pattern_factors.confidence > 0.5:
                # 트렌드가 강하면 더 높은 α 사용
                if hasattr(pattern_factors, 'trend_factor') and pattern_factors.trend_factor > 0.1:
                    alpha = min(0.5, alpha + pattern_factors.trend_factor * 0.5)

            smoothed_values = [monthly_data[0]]
            
            for i in range(1, len(monthly_data)):
                smoothed_value = alpha * monthly_data[i] + (1 - alpha) * smoothed_values[i-1]
                smoothed_values.append(smoothed_value)
            
            # 다음 달 예측
            prediction = smoothed_values[-1]
            
            # Pattern-based adjustment
            if pattern_factors:
                if hasattr(pattern_factors, 'trend_factor'):
                    prediction *= (1 + pattern_factors.trend_factor)
                
                if hasattr(pattern_factors, 'seasonal_factor'):
                    prediction *= pattern_factors.seasonal_factor
            
            # 신뢰구간 계산 (잔차 기반)
            residuals = []
            for i in range(1, len(monthly_data)):
                residuals.append(monthly_data[i] - smoothed_values[i-1])
            
            if residuals:
                residual_std = np.std(residuals)
                ci_lower = prediction - 1.96 * residual_std
                ci_upper = prediction + 1.96 * residual_std
            else:
                ci_lower = prediction * 0.8
                ci_upper = prediction * 1.2

            # 신뢰도 계산
            confidence = min(0.85, 0.6 + len(monthly_data) * 0.05)
            if pattern_factors and pattern_factors.confidence > 0.7:
                confidence += 0.1

            return ModelPrediction(
                model_name="Exponential_Smoothing",
                predicted_value=float(prediction),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=confidence,
                method_details={
                    "method": "Simple Exponential Smoothing",
                    "alpha": alpha,
                    "months_used": len(monthly_data),
                    "pattern_enhanced": pattern_factors is not None,
                    "description": f"지수평활법을 사용한 {len(monthly_data)}개월 데이터 기반 예측",
                },
            )

        except Exception as e:
            self.logger.debug(f"Exponential smoothing failed: {e}")
            return None

    def _linear_trend_analysis(self, monthly_data: np.ndarray, 
                              pattern_factors: Optional[PatternFactors] = None) -> Optional[ModelPrediction]:
        """선형 추세 분석을 사용한 예측."""
        try:
            if len(monthly_data) < 3:
                return None

            # 시간 인덱스
            x = np.arange(len(monthly_data))
            y = monthly_data

            # 선형 회귀
            slope, intercept = np.polyfit(x, y, 1)
            
            # 다음 달 예측 (인덱스 = len(monthly_data))
            prediction = intercept + slope * len(monthly_data)
            
            # Pattern-based adjustment
            if pattern_factors:
                if hasattr(pattern_factors, 'trend_factor'):
                    # 패턴 트렌드와 선형 트렌드 결합
                    adjusted_slope = slope * (1 + pattern_factors.trend_factor)
                    prediction = intercept + adjusted_slope * len(monthly_data)
                
                if hasattr(pattern_factors, 'seasonal_factor'):
                    prediction *= pattern_factors.seasonal_factor

            # R-squared 계산
            fitted_values = intercept + slope * x
            ss_res = np.sum((y - fitted_values) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            # 잔차 표준오차
            residuals = y - fitted_values
            rmse = np.sqrt(np.mean(residuals**2))

            # 신뢰구간 (예측 구간)
            # t-값 근사 (자유도 = n-2)
            df = len(monthly_data) - 2
            t_val = 2.0 if df < 10 else 1.96  # 간단한 근사

            # 예측점에서의 표준오차
            x_pred = len(monthly_data)
            x_mean = np.mean(x)
            se_pred = rmse * np.sqrt(1 + 1/len(x) + (x_pred - x_mean)**2 / np.sum((x - x_mean)**2))
            
            ci_lower = prediction - t_val * se_pred
            ci_upper = prediction + t_val * se_pred

            # 신뢰도 계산 (R-squared와 데이터 길이 기반)
            confidence = min(0.90, 0.5 + r_squared * 0.3 + len(monthly_data) * 0.02)
            if pattern_factors and pattern_factors.confidence > 0.7:
                confidence += 0.05

            return ModelPrediction(
                model_name="Linear_Trend_Analysis",
                predicted_value=float(prediction),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=confidence,
                r_squared=r_squared,
                rmse=rmse,
                method_details={
                    "method": "Linear Trend Analysis",
                    "slope": slope,
                    "intercept": intercept,
                    "months_used": len(monthly_data),
                    "pattern_enhanced": pattern_factors is not None,
                    "description": f"선형 추세 분석을 통한 {len(monthly_data)}개월 데이터 기반 예측",
                },
            )

        except Exception as e:
            self.logger.debug(f"Linear trend analysis failed: {e}")
            return None

    def _seasonal_pattern_prediction(self, monthly_data: np.ndarray, 
                                    pattern_factors: PatternFactors) -> Optional[ModelPrediction]:
        """계절성 패턴을 활용한 예측."""
        try:
            if len(monthly_data) < 6 or not pattern_factors:
                return None

            # 기본 트렌드 제거
            x = np.arange(len(monthly_data))
            slope, intercept = np.polyfit(x, monthly_data, 1)
            detrended = monthly_data - (intercept + slope * x)

            # 계절성 분해 (단순한 방법)
            # 각 월의 평균 계절성 효과 계산
            seasonal_effects = {}
            
            # 월별 효과 계산 (최소 2번 이상 나타나는 월만)
            months_in_data = len(monthly_data)
            for i, value in enumerate(detrended):
                month = (i % 12) + 1  # 1-12월
                if month not in seasonal_effects:
                    seasonal_effects[month] = []
                seasonal_effects[month].append(value)

            # 각 월의 평균 계절 효과
            avg_seasonal_effects = {}
            for month, values in seasonal_effects.items():
                if len(values) >= 1:  # 최소 1번은 나타나야 함
                    avg_seasonal_effects[month] = np.mean(values)

            # 다음 달 예측
            next_month_index = len(monthly_data)
            next_calendar_month = (next_month_index % 12) + 1

            # 트렌드 예측
            trend_prediction = intercept + slope * next_month_index
            
            # 계절성 조정
            seasonal_adjustment = avg_seasonal_effects.get(next_calendar_month, 0)
            prediction = trend_prediction + seasonal_adjustment

            # Pattern factors 적용
            if hasattr(pattern_factors, 'seasonal_strength'):
                # 계절성 강도에 따라 조정
                seasonal_multiplier = 1 + (pattern_factors.seasonal_strength - 0.5) * 0.2
                prediction *= seasonal_multiplier

            # 신뢰구간 계산
            residuals = detrended - np.array([avg_seasonal_effects.get((i % 12) + 1, 0) 
                                            for i in range(len(detrended))])
            residual_std = np.std(residuals)
            
            ci_lower = prediction - 1.96 * residual_std
            ci_upper = prediction + 1.96 * residual_std

            # 신뢰도 (패턴 신뢰도와 계절성 강도 기반)
            confidence = pattern_factors.confidence * 0.8
            if hasattr(pattern_factors, 'seasonal_strength'):
                confidence += pattern_factors.seasonal_strength * 0.15

            return ModelPrediction(
                model_name="Seasonal_Pattern_Prediction",
                predicted_value=float(prediction),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=min(0.90, confidence),
                method_details={
                    "method": "Seasonal Pattern Decomposition",
                    "trend_slope": slope,
                    "trend_intercept": intercept,
                    "next_month": next_calendar_month,
                    "seasonal_adjustment": seasonal_adjustment,
                    "months_used": len(monthly_data),
                    "seasonal_effects": avg_seasonal_effects,
                    "description": f"계절성 패턴을 활용한 {len(monthly_data)}개월 데이터 기반 예측",
                },
            )

        except Exception as e:
            self.logger.debug(f"Seasonal pattern prediction failed: {e}")
            return None