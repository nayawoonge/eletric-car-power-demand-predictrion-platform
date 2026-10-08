"""
계약전력 최적화 엔진

10kW 단위 후보 생성 및 비용 최소화 알고리즘
"""

import numpy as np
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .cost_calculator import KEPCOCostCalculator


@dataclass
class ContractCandidate:
    """계약전력 후보"""
    contract_kw: int  # 10kW 단위
    expected_annual_cost: float  # 연간 기대비용
    overage_probability: float  # 초과 확률 (%)
    waste_probability: float  # 낭비 확률 (%)
    cost_std: float  # 비용 표준편차
    cost_percentiles: Dict[str, float]  # 비용 분위수
    risk_score: float  # 리스크 점수
    session_overage_probability: Optional[float] = None
    session_average_overshoot_kw: Optional[float] = None
    session_max_overshoot_kw: Optional[float] = None
    session_waste_probability: Optional[float] = None
    session_average_waste_kw: Optional[float] = None
    session_sample_size: Optional[int] = None
    session_expected_waste_cost: Optional[float] = None


@dataclass
@dataclass
class OptimizationResult:
    """최적화 결과"""
    optimal_contract_kw: int  # 최적 계약전력
    current_contract_kw: Optional[int]  # 현재 계약전력
    
    # 비용 분석
    expected_annual_cost: float  # 예상 연간 비용
    expected_savings: Optional[float]  # 예상 절감액 (현재 대비)
    savings_percent: Optional[float]  # 절감 비율
    
    # 리스크 분석
    overage_probability: float  # 초과 확률
    waste_probability: float  # 낭비 확률
    confidence_level: float  # 신뢰도 (0-1)
    
    # 후보 분석
    all_candidates: List[ContractCandidate]  # 모든 후보
    optimal_candidate: ContractCandidate  # 최적 후보
    
    # 추천 사유
    recommendation_reason: str
    decision_factors: Dict[str, Any]
    
    @property
    def expected_annual_savings(self) -> Optional[float]:
        """expected_savings의 별칭 (하위 호환성)"""
        return self.expected_savings
    
    @property
    def recommendation_summary(self) -> str:
        """recommendation_reason의 별칭 (하위 호환성)"""
        return self.recommendation_reason


class ContractOptimizer:
    """
    계약전력 최적화 엔진
    
    핵심 알고리즘:
    1. 10kW 단위 후보 생성 (예측분포 분위수 범위 기반)
    2. 각 후보별 Monte Carlo 시뮬레이션 (1,000회)
    3. 비용 기댓값 계산 및 리스크 평가
    4. 비용 최소화 + 리스크 균형 최적화
    """
    
    def __init__(
        self,
        cost_calculator: Optional[KEPCOCostCalculator] = None,
        candidate_step: int = 10,  # 10kW 단위
        charger_type: Optional[str] = None,
        over_contract_headroom_kw: int = 40,
        minimum_over_contract_kw: int = 120,
        risk_weight: float = 0.8
    ):
        """
        Args:
            cost_calculator: 비용 계산기 (기본값: 새 인스턴스)
            candidate_step: 후보 간격 (kW) - 기본 10kW
            charger_type: 충전기 타입 (완속/급속)
            over_contract_headroom_kw: 예측분포 상단 이후로 추가 탐색할 여유 (kW)
            minimum_over_contract_kw: 과다 계약 비교를 위해 항상 포함할 최소 상단 kW
        """
        self.cost_calculator = cost_calculator or KEPCOCostCalculator()
        self.candidate_step = candidate_step
        self.charger_type = charger_type
        self.over_contract_headroom_kw = max(0, over_contract_headroom_kw)
        self.minimum_over_contract_kw = max(minimum_over_contract_kw, candidate_step)
        self.risk_weight = max(0.1, float(risk_weight))
        self.logger = logging.getLogger(__name__)
        
    def optimize_contract(
        self,
        prediction_distribution: Optional[np.ndarray] = None,
        station_data: Optional[Any] = None,
        predicted_peak_kw: Optional[float] = None,
        uncertainty_kw: Optional[float] = None,
        current_contract_kw: Optional[int] = None,
        min_contract_kw: int = 10,
        max_contract_kw: int = 200,
        risk_tolerance: float = 0.1,  # 0.0 (보수적) ~ 1.0 (공격적)
        session_prediction_series: Optional[List[Dict[str, Any]]] = None,
        candidate_range_override: Optional[Tuple[int, int]] = None
    ) -> OptimizationResult:
        """
        계약전력 최적화 실행
        
        Args:
            prediction_distribution: 예측 피크 확률분포 (np.ndarray, 예: 1,000개 샘플)
            station_data: 충전소 데이터 (선택사항, 미사용 파라미터 - 하위 호환성)
            predicted_peak_kw: 예측 피크 전력 (kW)
            uncertainty_kw: 불확실성 (kW)
            current_contract_kw: 현재 계약전력 (선택사항)
            min_contract_kw: 최소 계약전력
            max_contract_kw: 최대 계약전력
            risk_tolerance: 리스크 허용도 (0=보수적, 1=공격적)
            session_prediction_series: 세션 기반 예측 시계열 (OPTIONAL)
            candidate_range_override: (min, max) 튜플로 직접 후보 범위를 지정
            
        Returns:
            OptimizationResult: 최적화 결과
        """
        # prediction_distribution이 없으면 predicted_peak_kw와 uncertainty_kw로 생성
        if prediction_distribution is None:
            if predicted_peak_kw is None or uncertainty_kw is None:
                raise ValueError(
                    "Either prediction_distribution or (predicted_peak_kw, uncertainty_kw) must be provided"
                )
            # 정규분포로 근사 (1000개 샘플)
            prediction_distribution = np.random.normal(
                predicted_peak_kw,
                uncertainty_kw,
                1000
            )
        
        self.logger.info(
            f"계약전력 최적화 시작: 분포 크기={len(prediction_distribution)}, "
            f"현재 계약={current_contract_kw}kW, 리스크 허용도={risk_tolerance}"
        )
        
        # 1. 후보 범위 결정
        if candidate_range_override is not None:
            override_min, override_max = candidate_range_override
            if override_min >= override_max:
                raise ValueError("candidate_range_override 상단이 하단보다 커야 합니다.")
            range_min = max(min_contract_kw, override_min)
            range_max = min(max_contract_kw, override_max)
            range_min = int(np.floor(range_min / self.candidate_step)) * self.candidate_step
            range_max = int(np.ceil(range_max / self.candidate_step)) * self.candidate_step
            if range_min >= range_max:
                range_max = range_min + self.candidate_step * 2
                range_max = min(max_contract_kw, range_max)
            candidate_range = (range_min, range_max)
        else:
            candidate_range = self._determine_candidate_range(
                prediction_distribution,
                min_contract_kw,
                max_contract_kw
            )
        
        self.logger.info(
            f"후보 범위: {candidate_range[0]}kW ~ {candidate_range[1]}kW "
            f"(총 {len(range(candidate_range[0], candidate_range[1] + 1, self.candidate_step))}개)"
        )
        
        # 2. 각 후보별 비용 시뮬레이션
        candidates = self._evaluate_candidates(
            candidate_range,
            prediction_distribution,
            risk_tolerance,
            session_prediction_series
        )
        
        if not candidates:
            raise ValueError("유효한 계약전력 후보를 생성할 수 없습니다.")
        
        # 3. 최적 후보 선택 (비용 최소화 + 리스크 균형)
        optimal = self._select_optimal_candidate(candidates, risk_tolerance)
        
        # 4. 현재 계약과 비교
        expected_savings = None
        savings_percent = None
        
        if current_contract_kw is not None:
            current_cost = self._estimate_cost_for_contract(
                current_contract_kw,
                prediction_distribution
            )
            expected_savings = current_cost - optimal.expected_annual_cost
            savings_percent = (expected_savings / current_cost * 100) if current_cost > 0 else 0
            
            self.logger.info(
                f"현재 계약 대비: {expected_savings:,.0f}원 절감 ({savings_percent:.1f}%)"
            )
        
        # 5. 추천 사유 생성
        recommendation_reason = self._generate_recommendation(
            optimal,
            current_contract_kw,
            expected_savings,
            prediction_distribution
        )
        
        # 6. 의사결정 요인 분석
        decision_factors = self._analyze_decision_factors(
            optimal,
            candidates,
            prediction_distribution,
            risk_tolerance
        )
        
        return OptimizationResult(
            optimal_contract_kw=optimal.contract_kw,
            current_contract_kw=current_contract_kw,
            expected_annual_cost=optimal.expected_annual_cost,
            expected_savings=expected_savings,
            savings_percent=savings_percent,
            overage_probability=optimal.overage_probability,
            waste_probability=optimal.waste_probability,
            confidence_level=self._calculate_confidence(prediction_distribution),
            all_candidates=candidates,
            optimal_candidate=optimal,
            recommendation_reason=recommendation_reason,
            decision_factors=decision_factors
        )
    
    def _determine_candidate_range(
        self,
        distribution: np.ndarray,
        min_kw: int,
        max_kw: int
    ) -> Tuple[int, int]:
        """후보 범위 결정 (예측분포 중심 범위)"""
        # 5th ~ 95th percentile 기준으로 실제 데이터 범위만 사용
        p_low = np.percentile(distribution, 5)
        p_high = np.percentile(distribution, 95)
        
        range_min = max(
            min_kw,
            int(np.floor(p_low / self.candidate_step)) * self.candidate_step
        )
        range_max = min(
            max_kw,
            int(np.ceil(p_high / self.candidate_step)) * self.candidate_step
        )
        
        # 최소한 3개 후보는 확보 (range_min, +step, +2*step)
        if range_max - range_min < self.candidate_step * 2:
            median = np.median(distribution)
            buffer = self.candidate_step
            adjusted_min = int(np.floor((median - buffer) / self.candidate_step)) * self.candidate_step
            adjusted_max = int(np.ceil((median + buffer) / self.candidate_step)) * self.candidate_step
            range_min = max(min_kw, adjusted_min)
            range_max = min(max_kw, adjusted_max)
        
        # 과다계약 비교를 위해 여유 구간 확보 (최소 100kW 이상 포함)
        padded_max = max(
            range_max + self.over_contract_headroom_kw,
            self.minimum_over_contract_kw
        )
        padded_max_aligned = int(np.ceil(padded_max / self.candidate_step)) * self.candidate_step
        range_max = min(
            max_kw,
            max(range_min + self.candidate_step, padded_max_aligned)
        )
        
        # 최악의 경우라도 상·하한이 같지 않도록 보정
        if range_min >= range_max:
            range_min = max(min_kw, range_max - self.candidate_step * 2)
            range_max = min(max_kw, range_min + self.candidate_step * 2)
        
        return (range_min, range_max)
    
    def _evaluate_candidates(
        self,
        candidate_range: Tuple[int, int],
        distribution: np.ndarray,
        risk_tolerance: float,
        session_series: Optional[List[Dict[str, Any]]] = None
    ) -> List[ContractCandidate]:
        """모든 후보 평가"""
        candidates = []
        
        for contract_kw in range(candidate_range[0], candidate_range[1] + 1, self.candidate_step):
            # Monte Carlo 시뮬레이션
            cost_analysis = self.cost_calculator.estimate_cost_distribution(
                contract_kw,
                distribution.tolist()
            )
            
            # 리스크 점수 계산 (낮을수록 좋음)
            risk_score = self._calculate_risk_score(
                cost_analysis["overage_probability"],
                cost_analysis["waste_probability"],
                cost_analysis["cost_std"],
                risk_tolerance
            )

            session_metrics = self._compute_session_risk_metrics(
                contract_kw,
                session_series
            )
            
            candidate = ContractCandidate(
                contract_kw=contract_kw,
                expected_annual_cost=cost_analysis["expected_annual_cost"],
                overage_probability=cost_analysis["overage_probability"],
                waste_probability=cost_analysis["waste_probability"],
                cost_std=cost_analysis["cost_std"],
                cost_percentiles=cost_analysis["cost_percentiles"],
                risk_score=risk_score,
                session_overage_probability=session_metrics.get("session_overage_probability") if session_metrics else None,
                session_average_overshoot_kw=session_metrics.get("session_average_overshoot_kw") if session_metrics else None,
                session_max_overshoot_kw=session_metrics.get("session_max_overshoot_kw") if session_metrics else None,
                session_waste_probability=session_metrics.get("session_waste_probability") if session_metrics else None,
                session_average_waste_kw=session_metrics.get("session_average_waste_kw") if session_metrics else None,
                session_sample_size=session_metrics.get("session_sample_size") if session_metrics else None,
                session_expected_waste_cost=session_metrics.get("session_expected_waste_cost") if session_metrics else None
            )
            
            candidates.append(candidate)
            
            self.logger.debug(
                f"후보 {contract_kw}kW: 연간 {candidate.expected_annual_cost:,.0f}원, "
                f"초과확률 {candidate.overage_probability:.1f}%, "
                f"리스크점수 {risk_score:.3f}"
            )
        
        return candidates
    
    def _calculate_risk_score(
        self,
        overage_prob: float,
        waste_prob: float,
        cost_std: float,
        risk_tolerance: float
    ) -> float:
        """
        리스크 점수 계산
        
        리스크 = 초과 위험 + 낭비 위험 + 변동성
        - risk_tolerance=0: 보수적 (초과 위험 크게 페널티)
        - risk_tolerance=1: 공격적 (낭비 위험 크게 페널티)
        """
        # 정규화
        overage_risk = overage_prob / 100.0
        waste_risk = waste_prob / 100.0
        volatility = cost_std / 1000000.0  # 백만원 단위로 정규화
        
        # 가중치 계산
        overage_weight = 1.0 - risk_tolerance  # 보수적일수록 초과 위험 중시
        waste_weight = risk_tolerance  # 공격적일수록 낭비 위험 중시
        
        risk_score = (
            overage_risk * overage_weight * 2.0 +  # 초과는 2배 가중
            waste_risk * waste_weight +
            volatility * 0.5  # 변동성은 0.5배
        )
        
        return risk_score

    def _compute_session_risk_metrics(
        self,
        contract_kw: int,
        session_series: Optional[List[Dict[str, Any]]]
    ) -> Optional[Dict[str, float]]:
        """세션 예측 기반 리스크 메트릭 계산"""
        if not session_series:
            return None

        values: List[float] = []
        for entry in session_series:
            raw_value = None
            for key in (
                "predicted_peak_kw",
                "predictedPeakKw",
                "peak_kw",
                "peakKw",
                "value"
            ):
                if entry.get(key) is not None:
                    raw_value = entry.get(key)
                    break
            if raw_value is None:
                continue
            try:
                values.append(float(raw_value))
            except (TypeError, ValueError):
                continue

        if not values:
            return None

        total = len(values)
        overshoot = [val - contract_kw for val in values if val > contract_kw]
        waste = [contract_kw - val for val in values if val < contract_kw]

        def _avg(dataset: List[float]) -> Optional[float]:
            return float(np.mean(dataset)) if dataset else None

        metrics: Dict[str, Optional[float]] = {
            "session_sample_size": total,
            "session_overage_probability": (len(overshoot) / total * 100) if total else None,
            "session_average_overshoot_kw": _avg(overshoot),
            "session_max_overshoot_kw": float(np.max(overshoot)) if overshoot else None,
            "session_waste_probability": (len(waste) / total * 100) if total else None,
            "session_average_waste_kw": _avg(waste)
        }

        basic_rate = self.cost_calculator.BASIC_RATE_PER_KW
        annual_multiplier = basic_rate * 12
        if (
            metrics["session_waste_probability"] is not None and
            metrics["session_average_waste_kw"] is not None
        ):
            expected_waste_kw = metrics["session_average_waste_kw"] * (metrics["session_waste_probability"] / 100)
            metrics["session_expected_waste_cost"] = expected_waste_kw * annual_multiplier
        else:
            metrics["session_expected_waste_cost"] = None

        return metrics
    
    def _select_optimal_candidate(
        self,
        candidates: List[ContractCandidate],
        risk_tolerance: float
    ) -> ContractCandidate:
        """최적 후보 선택 (비용 + 리스크 균형)"""
        # 비용과 리스크의 가중 합산 최소화
        best_candidate = None
        best_score = float('inf')
        
        for candidate in candidates:
            # 정규화된 비용 (최소 비용 대비 비율)
            min_cost = min(c.expected_annual_cost for c in candidates)
            normalized_cost = candidate.expected_annual_cost / min_cost if min_cost > 0 else 1.0
            
            # 종합 점수 = 정규화 비용 + 리스크 점수
            total_score = normalized_cost + (candidate.risk_score * self.risk_weight)
            
            if total_score < best_score:
                best_score = total_score
                best_candidate = candidate
        
        return best_candidate
    
    def _estimate_cost_for_contract(
        self,
        contract_kw: int,
        distribution: np.ndarray
    ) -> float:
        """특정 계약전력의 연간 비용 추정"""
        cost_analysis = self.cost_calculator.estimate_cost_distribution(
            contract_kw,
            distribution.tolist()
        )
        return cost_analysis["expected_annual_cost"]
    
    def _calculate_confidence(self, distribution: np.ndarray) -> float:
        """예측 신뢰도 계산 (샘플 수 및 분산 기반)"""
        sample_size = len(distribution)
        cv = np.std(distribution) / np.mean(distribution) if np.mean(distribution) > 0 else 1.0
        
        # 샘플 크기 신뢰도
        size_confidence = min(1.0, sample_size / 1000.0)
        
        # 변동성 신뢰도 (낮을수록 신뢰도 높음)
        variability_confidence = max(0.3, 1.0 - cv)
        
        return (size_confidence + variability_confidence) / 2.0
    
    def _generate_recommendation(
        self,
        optimal: ContractCandidate,
        current_contract: Optional[int],
        savings: Optional[float],
        distribution: np.ndarray
    ) -> str:
        """추천 사유 생성"""
        reasons = []
        
        # 1. 최적화 결과
        reasons.append(
            f"10kW 단위 최적화 결과 {optimal.contract_kw}kW 선정"
        )
        
        # 2. 예측분포 기반
        p50 = np.percentile(distribution, 50)
        p95 = np.percentile(distribution, 95)
        reasons.append(
            f"예측 피크 중앙값 {p50:.0f}kW, 95백분위 {p95:.0f}kW 기준"
        )
        
        # 3. 절감액
        if savings is not None and savings > 0:
            reasons.append(
                f"현행 대비 연간 {savings:,.0f}원 절감 예상"
            )
        
        # 4. 리스크 분석
        if optimal.overage_probability < 10:
            reasons.append(
                f"초과 위험도 낮음 ({optimal.overage_probability:.1f}%)"
            )
        elif optimal.overage_probability < 20:
            reasons.append(
                f"초과 위험도 적정 ({optimal.overage_probability:.1f}%)"
            )
        else:
            reasons.append(
                f"⚠️ 초과 위험 존재 ({optimal.overage_probability:.1f}%)"
            )
        
        return " | ".join(reasons)
    
    def _analyze_decision_factors(
        self,
        optimal: ContractCandidate,
        all_candidates: List[ContractCandidate],
        distribution: np.ndarray,
        risk_tolerance: float
    ) -> Dict[str, Any]:
        """의사결정 요인 분석"""
        return {
            "optimization_method": "10kW 단위 Monte Carlo 시뮬레이션",
            "simulation_count": len(distribution),
            "candidate_count": len(all_candidates),
            "risk_tolerance": risk_tolerance,
            "distribution_stats": {
                "mean": float(np.mean(distribution)),
                "std": float(np.std(distribution)),
                "min": float(np.min(distribution)),
                "max": float(np.max(distribution)),
                "p50": float(np.percentile(distribution, 50)),
                "p95": float(np.percentile(distribution, 95))
            },
            "cost_range": {
                "min": min(c.expected_annual_cost for c in all_candidates),
                "max": max(c.expected_annual_cost for c in all_candidates),
                "optimal": optimal.expected_annual_cost
            },
            "risk_assessment": {
                "overage_risk": "낮음" if optimal.overage_probability < 10 else "보통" if optimal.overage_probability < 20 else "높음",
                "waste_risk": "낮음" if optimal.waste_probability < 30 else "보통" if optimal.waste_probability < 50 else "높음",
                "overall_risk": optimal.risk_score
            }
        }
