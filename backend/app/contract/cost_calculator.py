"""
한국전력공사(KEPCO) 요금 규칙 엔진

기본요금, 초과 부가금 계산 및 연간 비용 산출
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class CostBreakdown:
    """비용 상세 분석"""
    contract_kw: float
    actual_peak_kw: float
    
    # 비용 구성요소
    basic_cost: float  # 기본요금
    overage_cost: float  # 초과 부가금
    opportunity_cost: float  # 과다계약 기회비용
    total_cost: float  # 총 비용
    
    # 추가 정보
    is_overcontracted: bool  # 과다계약 여부
    is_undercontracted: bool  # 과소계약 여부
    waste_kw: float  # 낭비 전력
    overage_kw: float  # 초과 전력


class KEPCOCostCalculator:
    """
    한국전력공사 전기요금 계산 엔진
    
    요금 구조:
    1. 기본요금: 계약전력 × kW당 기본요금
    2. 초과 부가금: (실제 피크 - 계약전력) × kW당 기본요금 × 1.5배
    3. 기회비용: (계약전력 - 실제 피크) × kW당 기본요금 (낭비)
    """
    
    # 2024년 기준 산업용 전력(을) 요금 - 고압A 선택II
    # 출처: 한국전력공사 전기요금표
    BASIC_RATE_PER_KW = 8320  # 원/kW/월 (기본요금)
    OVERAGE_PENALTY_RATE = 1.5  # 초과 사용 시 1.5배 부가금
    
    # 전력량 요금 (kWh당) - 참고용
    ENERGY_RATE_SUMMER_LIGHT = 56.1  # 원/kWh (경부하)
    ENERGY_RATE_SUMMER_MID = 109.0  # 원/kWh (중간부하)
    ENERGY_RATE_SUMMER_PEAK = 191.4  # 원/kWh (최대부하)
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def calculate_monthly_cost(
        self,
        contract_kw: float,
        actual_peak_kw: float,
        include_opportunity_cost: bool = True
    ) -> CostBreakdown:
        """
        월간 전기요금 계산
        
        Args:
            contract_kw: 계약전력 (kW)
            actual_peak_kw: 실제 최대 수요전력 (kW)
            include_opportunity_cost: 기회비용 포함 여부
            
        Returns:
            CostBreakdown: 비용 상세 분석
        """
        # 1. 기본요금 계산 (항상 발생)
        basic_cost = contract_kw * self.BASIC_RATE_PER_KW
        
        # 2. 초과 부가금 계산 (과소계약 시)
        overage_kw = max(0, actual_peak_kw - contract_kw)
        overage_cost = 0.0
        
        if overage_kw > 0:
            # 초과 전력에 대해 기본요금의 1.5배 부과
            overage_cost = overage_kw * self.BASIC_RATE_PER_KW * self.OVERAGE_PENALTY_RATE
            is_undercontracted = True
        else:
            is_undercontracted = False
        
        # 3. 기회비용 계산 (과다계약 시)
        waste_kw = max(0, contract_kw - actual_peak_kw)
        opportunity_cost = 0.0

        # 과다계약 여부는 의사결정 지표이므로 기회비용 포함 여부와 무관하게 판별
        is_overcontracted = waste_kw > 0

        if waste_kw > 0 and include_opportunity_cost:
            # 사용하지 않는 계약전력에 대한 기본요금 납부 = 기회비용
            opportunity_cost = waste_kw * self.BASIC_RATE_PER_KW
        
        # 4. 총 비용 = 기본요금 + 초과 부가금
        # (기회비용은 총 비용에 포함하지 않음 - 의사결정용 지표)
        total_cost = basic_cost + overage_cost
        
        self.logger.debug(
            f"비용 계산: 계약={contract_kw}kW, 실제={actual_peak_kw:.1f}kW, "
            f"기본={basic_cost:,.0f}원, 초과={overage_cost:,.0f}원, "
            f"기회비용={opportunity_cost:,.0f}원, 총={total_cost:,.0f}원"
        )
        
        return CostBreakdown(
            contract_kw=contract_kw,
            actual_peak_kw=actual_peak_kw,
            basic_cost=basic_cost,
            overage_cost=overage_cost,
            opportunity_cost=opportunity_cost,
            total_cost=total_cost,
            is_overcontracted=is_overcontracted,
            is_undercontracted=is_undercontracted,
            waste_kw=waste_kw,
            overage_kw=overage_kw
        )
    
    def calculate_annual_cost(
        self,
        contract_kw: float,
        actual_peak_kw: float
    ) -> float:
        """
        연간 전기요금 계산 (단순화: 월간 비용 × 12)
        
        Args:
            contract_kw: 계약전력 (kW)
            actual_peak_kw: 실제 최대 수요전력 (kW)
            
        Returns:
            float: 연간 총 비용 (원)
        """
        monthly = self.calculate_monthly_cost(contract_kw, actual_peak_kw)
        return monthly.total_cost * 12
    
    def compare_contracts(
        self,
        current_contract_kw: float,
        new_contract_kw: float,
        actual_peak_kw: float
    ) -> Dict[str, Any]:
        """
        현재 계약과 신규 계약 비교
        
        Args:
            current_contract_kw: 현재 계약전력
            new_contract_kw: 신규 계약전력
            actual_peak_kw: 실제 피크
            
        Returns:
            Dict: 비교 분석 결과
        """
        current = self.calculate_monthly_cost(current_contract_kw, actual_peak_kw)
        new = self.calculate_monthly_cost(new_contract_kw, actual_peak_kw)
        
        monthly_savings = current.total_cost - new.total_cost
        annual_savings = monthly_savings * 12
        savings_percent = (monthly_savings / current.total_cost * 100) if current.total_cost > 0 else 0
        
        return {
            "current": {
                "contract_kw": current_contract_kw,
                "monthly_cost": current.total_cost,
                "annual_cost": current.total_cost * 12,
                "overage_cost": current.overage_cost,
                "opportunity_cost": current.opportunity_cost
            },
            "new": {
                "contract_kw": new_contract_kw,
                "monthly_cost": new.total_cost,
                "annual_cost": new.total_cost * 12,
                "overage_cost": new.overage_cost,
                "opportunity_cost": new.opportunity_cost
            },
            "savings": {
                "monthly": monthly_savings,
                "annual": annual_savings,
                "percent": savings_percent,
                "is_beneficial": monthly_savings > 0
            },
            "recommendation": self._generate_comparison_recommendation(
                current, new, monthly_savings
            )
        }
    
    def _generate_comparison_recommendation(
        self,
        current: CostBreakdown,
        new: CostBreakdown,
        monthly_savings: float
    ) -> str:
        """비교 분석 추천 메시지 생성"""
        if monthly_savings > 10000:  # 월 1만원 이상 절감
            if new.is_overcontracted:
                return f"계약 변경 권장: 월 {monthly_savings:,.0f}원 절감 가능 (단, {new.waste_kw:.0f}kW 여유분 존재)"
            elif new.is_undercontracted:
                return f"계약 변경 시 월 {monthly_savings:,.0f}원 절감하나, 초과 위험 {new.overage_kw:.0f}kW 존재"
            else:
                return f"계약 변경 강력 권장: 월 {monthly_savings:,.0f}원 절감 가능 (최적 수준)"
        elif monthly_savings > 0:
            return f"소폭 절감 가능: 월 {monthly_savings:,.0f}원"
        elif monthly_savings < -10000:
            return f"계약 변경 비권장: 월 {abs(monthly_savings):,.0f}원 추가 비용 발생"
        else:
            return "현재 계약 유지 권장: 비용 차이 미미"
    
    def estimate_cost_distribution(
        self,
        contract_kw: float,
        peak_distribution: list[float]
    ) -> Dict[str, Any]:
        """
        확률분포 기반 비용 기댓값 계산
        
        Args:
            contract_kw: 계약전력
            peak_distribution: 피크 전력 확률분포 (예: Monte Carlo 샘플 1,000개)
            
        Returns:
            Dict: 비용 분포 통계
        """
        import numpy as np
        
        costs = []
        overage_count = 0
        waste_count = 0
        
        for peak in peak_distribution:
            breakdown = self.calculate_monthly_cost(contract_kw, peak, include_opportunity_cost=False)
            costs.append(breakdown.total_cost)
            
            if breakdown.is_undercontracted:
                overage_count += 1
            if breakdown.is_overcontracted:
                waste_count += 1
        
        costs_array = np.array(costs)
        
        return {
            "contract_kw": contract_kw,
            "expected_monthly_cost": float(np.mean(costs_array)),
            "expected_annual_cost": float(np.mean(costs_array) * 12),
            "cost_std": float(np.std(costs_array)),
            "cost_min": float(np.min(costs_array)),
            "cost_max": float(np.max(costs_array)),
            "cost_percentiles": {
                "p25": float(np.percentile(costs_array, 25)),
                "p50": float(np.percentile(costs_array, 50)),
                "p75": float(np.percentile(costs_array, 75)),
                "p95": float(np.percentile(costs_array, 95))
            },
            "overage_probability": overage_count / len(peak_distribution) * 100,
            "waste_probability": waste_count / len(peak_distribution) * 100,
            "simulations": len(peak_distribution)
        }
