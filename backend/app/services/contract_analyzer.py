import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Literal
import logging
from dataclasses import dataclass
from enum import Enum

# 새로운 계약 최적화 엔진 import
from ..contract import ContractOptimizer, KEPCOCostCalculator, RecommendationEngine


class ContractStatus(Enum):
    """계약 상태 분류"""
    OVERCONTRACTED = "과다계약"  # 현재 계약이 과도하게 높음
    OPTIMAL = "적정계약"  # 적정 수준
    UNDERCONTRACTED = "과소계약"  # 현재 계약이 부족함
    UNKNOWN = "알 수 없음"  # 판별 불가


@dataclass
class ContractAnalysis:
    """계약 분석 결과"""
    status: ContractStatus
    current_contract_kw: float
    recommended_contract_kw: float
    actual_peak_kw: float  # 실제 95백분위 전력

    # 차이 분석
    difference_kw: float  # 현재 계약 - 권장 계약
    difference_percent: float  # 차이 비율

    # 의사결정 지원 정보
    estimated_monthly_waste: Optional[float] = None  # 과다계약 시 월 낭비 금액
    estimated_overage_risk: Optional[float] = None  # 과소계약 시 초과 위험도 (0-100)
    estimated_monthly_savings: Optional[float] = None  # 계약 변경 시 월 절감액

    # 추가 정보
    confidence_score: float = 0.0  # 판별 신뢰도
    charger_type: str = "미상"
    data_quality: str = "medium"
    recommendation_reason: str = ""


class ContractAnalyzer:
    """
    계약 전력 분석 및 최적화
    
    레거시 분석기 - 새로운 ContractOptimizer와 통합
    """

    # 요금 상수 (레거시 - KEPCO 계산기 사용 권장)
    BASIC_RATE_PER_KW = 8320  # 기본요금 (원/kW/월) - 산업용 전력 기준
    OVERAGE_PENALTY_RATE = 1.5  # 초과 사용 시 패널티 배율

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 새로운 최적화 엔진 초기화
        self.optimizer = ContractOptimizer()
        self.cost_calculator = KEPCOCostCalculator()
        self.recommendation_engine = RecommendationEngine()

        # 충전기 타입별 최대 계약 전력
        self.charger_limits = {
            "완속충전기 (AC)": 7,
            "급속충전기 (DC)": 100,
            "미상": 50,
        }

        # 판별 기준 (조정 가능)
        self.overcontract_threshold = 1.20  # 20% 이상 초과
        self.undercontract_threshold = 0.95  # 5% 미만

    def analyze_contract(
        self,
        current_contract_kw: float,
        station_data: pd.DataFrame,
        charger_type: str = "미상",
        data_quality: str = "medium"
    ) -> ContractAnalysis:
        """
        현재 계약 전력을 분석하고 과다/과소 여부 판별

        Args:
            current_contract_kw: 현재 계약 전력 (kW)
            station_data: 충전소 데이터
            charger_type: 충전기 타입
            data_quality: 데이터 품질

        Returns:
            ContractAnalysis: 분석 결과
        """
        try:
            # 실제 전력 사용 패턴 분석
            actual_peak_kw = self._calculate_actual_peak(station_data)
            recommended_kw = self._calculate_optimal_contract(
                station_data, actual_peak_kw, charger_type
            )

            # 차이 계산
            difference_kw = current_contract_kw - recommended_kw
            difference_percent = (difference_kw / recommended_kw * 100) if recommended_kw > 0 else 0

            # 계약 상태 판별
            status = self._determine_contract_status(
                current_contract_kw, recommended_kw, actual_peak_kw
            )

            # 의사결정 지원 정보 계산
            monthly_waste = None
            overage_risk = None
            monthly_savings = None
            recommendation_reason = ""

            if status == ContractStatus.OVERCONTRACTED:
                # 과다계약: 낭비 금액 계산
                monthly_waste = self._calculate_monthly_waste(difference_kw)
                monthly_savings = monthly_waste
                recommendation_reason = (
                    f"현재 계약이 실제 필요량보다 {abs(difference_kw):.1f}kW ({abs(difference_percent):.1f}%) 높습니다. "
                    f"계약을 {recommended_kw:.0f}kW로 조정하면 월 약 {monthly_savings:,.0f}원 절감 가능합니다."
                )

            elif status == ContractStatus.UNDERCONTRACTED:
                # 과소계약: 초과 위험도 및 예상 손실 계산
                overage_risk = self._calculate_overage_risk(
                    current_contract_kw, actual_peak_kw, station_data
                )
                potential_overage_cost = self._estimate_overage_cost(
                    current_contract_kw, actual_peak_kw
                )
                additional_basic_cost = self._calculate_monthly_waste(-difference_kw)
                monthly_savings = -(additional_basic_cost + potential_overage_cost)

                recommendation_reason = (
                    f"현재 계약이 실제 필요량보다 {abs(difference_kw):.1f}kW ({abs(difference_percent):.1f}%) 낮습니다. "
                    f"초과 사용 위험도 {overage_risk:.1f}%로, 계약을 {recommended_kw:.0f}kW로 상향하면 "
                    f"초과요금 리스크를 회피할 수 있습니다."
                )

            else:  # OPTIMAL
                recommendation_reason = (
                    f"현재 계약 {current_contract_kw:.0f}kW는 실제 사용 패턴({actual_peak_kw:.1f}kW)에 "
                    f"적정한 수준입니다."
                )

            # 신뢰도 계산
            confidence_score = self._calculate_confidence(station_data, data_quality)

            return ContractAnalysis(
                status=status,
                current_contract_kw=current_contract_kw,
                recommended_contract_kw=recommended_kw,
                actual_peak_kw=actual_peak_kw,
                difference_kw=difference_kw,
                difference_percent=difference_percent,
                estimated_monthly_waste=monthly_waste,
                estimated_overage_risk=overage_risk,
                estimated_monthly_savings=monthly_savings,
                confidence_score=confidence_score,
                charger_type=charger_type,
                data_quality=data_quality,
                recommendation_reason=recommendation_reason,
            )

        except Exception as e:
            self.logger.error(f"계약 분석 중 오류 발생: {e}", exc_info=True)
            # 폴백: 알 수 없음 상태로 반환
            return ContractAnalysis(
                status=ContractStatus.UNKNOWN,
                current_contract_kw=current_contract_kw,
                recommended_contract_kw=current_contract_kw,
                actual_peak_kw=0.0,
                difference_kw=0.0,
                difference_percent=0.0,
                confidence_score=0.0,
                charger_type=charger_type,
                data_quality="low",
                recommendation_reason="데이터 부족으로 분석할 수 없습니다.",
            )

    def _calculate_actual_peak(self, station_data: pd.DataFrame) -> float:
        """실제 피크 전력 계산 (95백분위수)"""
        power_cols = ["순간최고전력", "max_power", "전력"]

        for col in power_cols:
            if col in station_data.columns:
                power_data = station_data[col].dropna()
                if len(power_data) > 0:
                    return float(power_data.quantile(0.95))

        return 0.0

    def _calculate_optimal_contract(
        self,
        station_data: pd.DataFrame,
        actual_peak_kw: float,
        charger_type: str
    ) -> float:
        """최적 계약 전력 계산"""
        if actual_peak_kw == 0:
            return 45.0  # 기본값

        # 충전기 타입 판별
        is_fast_charger = self._is_fast_charger(station_data, charger_type)

        # 데이터 품질에 따른 안전 마진
        data_count = len(station_data)

        if is_fast_charger:
            if data_count > 1000:
                safety_margin = 0.12 if actual_peak_kw > 80 else 0.08
            elif data_count > 500:
                safety_margin = 0.15 if actual_peak_kw > 60 else 0.12
            else:
                safety_margin = 0.20 if actual_peak_kw > 60 else 0.15

            raw_prediction = actual_peak_kw * (1 + safety_margin)
            raw_prediction = round(raw_prediction / 5) * 5  # 5kW 단위
            raw_prediction = max(50, raw_prediction)
            max_limit = self.charger_limits.get("급속충전기 (DC)", 100)
        else:
            if data_count > 500:
                safety_margin = 0.08 if actual_peak_kw > 5 else 0.05
            else:
                safety_margin = 0.12 if actual_peak_kw > 5 else 0.08

            raw_prediction = actual_peak_kw * (1 + safety_margin)
            raw_prediction = round(raw_prediction)  # 1kW 단위
            raw_prediction = max(3, raw_prediction)
            max_limit = self.charger_limits.get("완속충전기 (AC)", 7)

        return min(max_limit, raw_prediction)

    def _is_fast_charger(self, station_data: pd.DataFrame, charger_type: str) -> bool:
        """급속 충전기 여부 판단"""
        # 명시적 타입이 있으면 사용
        if "급속" in charger_type or "DC" in charger_type:
            return True
        if "완속" in charger_type or "AC" in charger_type:
            return False

        # 데이터 기반 판별
        power_cols = ["순간최고전력", "max_power", "전력"]
        for col in power_cols:
            if col in station_data.columns:
                power_data = station_data[col].dropna()
                if len(power_data) > 0:
                    max_power = power_data.max()
                    mean_power = power_data.mean()
                    p95 = power_data.quantile(0.95)

                    # 다중 조건 판별
                    conditions = [
                        max_power >= 30,
                        mean_power >= 15,
                        p95 >= 25,
                    ]

                    return sum(conditions) >= 2 or max_power >= 20

        return False  # 기본값: 완속

    def _determine_contract_status(
        self,
        current_contract_kw: float,
        recommended_kw: float,
        actual_peak_kw: float
    ) -> ContractStatus:
        """계약 상태 판별"""
        if recommended_kw == 0:
            return ContractStatus.UNKNOWN

        ratio = current_contract_kw / recommended_kw

        if ratio >= self.overcontract_threshold:
            return ContractStatus.OVERCONTRACTED
        elif ratio < self.undercontract_threshold:
            return ContractStatus.UNDERCONTRACTED
        else:
            return ContractStatus.OPTIMAL

    def _calculate_monthly_waste(self, excess_kw: float) -> float:
        """과다계약 시 월 낭비 금액 계산"""
        if excess_kw <= 0:
            return 0.0
        return excess_kw * self.BASIC_RATE_PER_KW

    def _calculate_overage_risk(
        self,
        current_contract_kw: float,
        actual_peak_kw: float,
        station_data: pd.DataFrame
    ) -> float:
        """
        과소계약 시 초과 위험도 계산 (0-100)
        실제 데이터에서 현재 계약을 초과한 비율 계산
        """
        if actual_peak_kw <= current_contract_kw:
            return 0.0

        power_cols = ["순간최고전력", "max_power", "전력"]
        for col in power_cols:
            if col in station_data.columns:
                power_data = station_data[col].dropna()
                if len(power_data) > 0:
                    # 현재 계약을 초과한 비율
                    exceed_count = (power_data > current_contract_kw).sum()
                    total_count = len(power_data)
                    risk_percent = (exceed_count / total_count * 100) if total_count > 0 else 0
                    return min(100.0, risk_percent)

        # 데이터가 없으면 단순 비율로 추정
        excess_ratio = (actual_peak_kw - current_contract_kw) / current_contract_kw
        return min(100.0, excess_ratio * 100)

    def _estimate_overage_cost(
        self,
        current_contract_kw: float,
        actual_peak_kw: float
    ) -> float:
        """초과 사용 시 예상 추가 비용 (월)"""
        if actual_peak_kw <= current_contract_kw:
            return 0.0

        excess_kw = actual_peak_kw - current_contract_kw
        # 초과 부분은 기본요금의 1.5배로 가정
        return excess_kw * self.BASIC_RATE_PER_KW * self.OVERAGE_PENALTY_RATE

    def _calculate_confidence(
        self,
        station_data: pd.DataFrame,
        data_quality: str
    ) -> float:
        """판별 신뢰도 계산"""
        data_count = len(station_data)

        # 데이터 양 기반 신뢰도
        if data_count > 1000:
            count_confidence = 0.95
        elif data_count > 500:
            count_confidence = 0.85
        elif data_count > 100:
            count_confidence = 0.70
        else:
            count_confidence = 0.50

        # 데이터 품질 기반 조정
        quality_factor = {
            "high": 1.0,
            "medium": 0.9,
            "low": 0.7
        }.get(data_quality, 0.8)

        return min(0.95, count_confidence * quality_factor)
    
    def optimize_contract_with_lstm_distribution(
        self,
        station_id: str,
        lstm_prediction: Any,  # EnsemblePrediction
        current_contract_kw: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        LSTM Monte Carlo Dropout 분포를 사용한 계약전력 최적화
        
        Args:
            station_id: 충전소 ID
            lstm_prediction: LSTM 예측 결과 (EnsemblePrediction)
            current_contract_kw: 현재 계약전력
            
        Returns:
            Dict: 최적화 결과
        """
        try:
            # LSTM 예측에서 확률분포 추출
            prediction_distribution = None
            
            # method_details에서 prediction_distribution 찾기
            for model_pred in lstm_prediction.model_predictions:
                if "distribution" in model_pred.method_details:
                    # 분포 데이터가 있으면 추출
                    dist_data = model_pred.method_details.get("prediction_distribution")
                    if dist_data:
                        prediction_distribution = np.array(dist_data)
                        break
            
            # 분포가 없으면 통계 기반으로 생성
            if prediction_distribution is None:
                self.logger.warning("LSTM 분포를 찾을 수 없어 통계 기반 분포 생성")
                mean = lstm_prediction.raw_prediction
                # uncertainty를 std로 사용
                std = lstm_prediction.uncertainty if lstm_prediction.uncertainty else mean * 0.15
                prediction_distribution = np.random.normal(mean, std, 1000)
            
            # 10kW 단위 최적화 실행
            return self.optimize_contract_with_distribution(
                station_id=station_id,
                prediction_distribution=prediction_distribution,
                current_contract_kw=current_contract_kw
            )
            
        except Exception as e:
            self.logger.error(f"LSTM 분포 기반 최적화 실패: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "station_id": station_id
            }

    def optimize_contract_with_distribution(
        self,
        station_id: str,
        prediction_distribution: Any,  # np.ndarray
        current_contract_kw: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        확률분포 기반 계약전력 최적화 (신규 메서드)
        
        Args:
            station_id: 충전소 ID
            prediction_distribution: 예측 피크 확률분포
            current_contract_kw: 현재 계약전력
            
        Returns:
            Dict: 최적화 결과 (10kW 단위)
        """
        try:
            # 새로운 추천 엔진 사용
            recommendation = self.recommendation_engine.generate_recommendation(
                station_id=station_id,
                prediction_distribution=prediction_distribution,
                current_contract_kw=current_contract_kw
            )
            
            # 레거시 포맷으로 변환 (하위 호환성)
            result = self.recommendation_engine.to_dict(recommendation)
            
            # 추가 필드
            result["method"] = "10kW_unit_optimization"
            result["optimization_engine"] = "ContractOptimizer_v2"
            
            self.logger.info(
                f"Station {station_id}: 10kW 단위 최적화 완료 - "
                f"{recommendation.recommended_contract_kw}kW 추천"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"최적화 실패: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "station_id": station_id
            }

    def to_dict(self, analysis: ContractAnalysis) -> Dict[str, Any]:
        """분석 결과를 딕셔너리로 변환"""
        return {
            "status": analysis.status.value,
            "status_code": analysis.status.name,
            "current_contract_kw": round(analysis.current_contract_kw, 1),
            "recommended_contract_kw": round(analysis.recommended_contract_kw, 1),
            "actual_peak_kw": round(analysis.actual_peak_kw, 1),
            "difference_kw": round(analysis.difference_kw, 1),
            "difference_percent": round(analysis.difference_percent, 1),
            "estimated_monthly_waste": round(analysis.estimated_monthly_waste, 0) if analysis.estimated_monthly_waste else None,
            "estimated_overage_risk": round(analysis.estimated_overage_risk, 1) if analysis.estimated_overage_risk else None,
            "estimated_monthly_savings": round(analysis.estimated_monthly_savings, 0) if analysis.estimated_monthly_savings else None,
            "confidence_score": round(analysis.confidence_score, 2),
            "charger_type": analysis.charger_type,
            "data_quality": analysis.data_quality,
            "recommendation_reason": analysis.recommendation_reason,
        }
