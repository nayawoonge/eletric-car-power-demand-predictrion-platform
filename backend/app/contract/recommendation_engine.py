"""
계약전력 추천 엔진

최적화 결과를 기반으로 사용자 친화적 추천 생성
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .optimizer import ContractOptimizer, OptimizationResult
from .cost_calculator import KEPCOCostCalculator


@dataclass
class ContractRecommendation:
    """계약전력 추천 결과"""
    # 기본 정보
    station_id: str
    analysis_date: str
    
    # 추천 계약전력
    recommended_contract_kw: int
    current_contract_kw: Optional[int]
    
    # 비용 분석
    expected_annual_cost: float
    expected_annual_savings: Optional[float]
    savings_percent: Optional[float]
    
    # 예측 정보
    predicted_peak_p50: float  # 중앙값
    predicted_peak_p95: float  # 95백분위
    
    # 리스크 분석
    overage_probability: float
    waste_probability: float
    confidence_level: float
    
    # 추천 사유
    recommendation_summary: str
    detailed_reasoning: List[str]
    
    # 액션 아이템
    action_required: bool
    urgency_level: str  # "high", "medium", "low"
    
    # 시각화 데이터
    cost_comparison_data: Dict[str, Any]
    candidate_analysis_data: List[Dict[str, Any]]
    
    # 최적화 상세 데이터 (시각화용)
    optimization_details: Optional[Dict[str, Any]] = None

    # 이중 추천: 비용 최적안 + 초과 최소(안전)안
    recommendation_options: Optional[Dict[str, Any]] = None


class RecommendationEngine:
    """
    계약전력 추천 엔진
    
    최적화 결과를 사용자 친화적인 추천으로 변환
    """
    
    def __init__(self):
        self.optimizer = ContractOptimizer()
        self.cost_calculator = KEPCOCostCalculator()
        self.logger = logging.getLogger(__name__)
    
    def generate_recommendation(
        self,
        station_id: str,
        prediction_distribution: Any,  # np.ndarray
        current_contract_kw: Optional[int] = None,
        historical_peak_series: Optional[List[Dict[str, Any]]] = None,
        session_power_series: Optional[List[Dict[str, Any]]] = None,
        session_prediction_series: Optional[List[Dict[str, Any]]] = None,
        **optimizer_kwargs
    ) -> ContractRecommendation:
        """
        계약전력 추천 생성
        
        Args:
            station_id: 충전소 ID
            prediction_distribution: 예측 피크 확률분포
            current_contract_kw: 현재 계약전력
            **optimizer_kwargs: 최적화 옵션
            
        Returns:
            ContractRecommendation: 추천 결과
        """
        self.logger.info(f"Station {station_id}: 계약전력 추천 생성 시작")
        
        # 1. 최적화 실행
        effective_session_series = session_prediction_series or session_power_series or []
        optimizer_options = dict(optimizer_kwargs)
        optimizer_options.setdefault("min_contract_kw", 30)
        optimizer_options.setdefault("max_contract_kw", 150)
        optimizer_options.setdefault("candidate_range_override", (30, 150))

        optimization = self.optimizer.optimize_contract(
            prediction_distribution=prediction_distribution,
            current_contract_kw=current_contract_kw,
            session_prediction_series=effective_session_series,
            **optimizer_options
        )
        
        # 2. 예측 통계 계산
        p50 = float(np.percentile(prediction_distribution, 50))
        p95 = float(np.percentile(prediction_distribution, 95))
        
        # 3. 상세 사유 생성
        detailed_reasoning = self._generate_detailed_reasoning(
            optimization,
            prediction_distribution
        )
        
        # 4. 액션 요구사항 판단
        action_required, urgency = self._assess_action_urgency(
            optimization,
            current_contract_kw
        )
        
        # 5. 시각화 데이터 준비
        cost_comparison = self._prepare_cost_comparison(
            optimization,
            current_contract_kw
        )
        
        candidate_analysis = self._prepare_candidate_analysis(
            optimization.all_candidates
        )
        
        # 6. 최적화 상세 데이터 (시각화용)
        optimization_details = self._prepare_optimization_details(
            optimization,
            prediction_distribution,
            historical_peak_series,
            session_power_series,
            effective_session_series
        )
        
        # 6.5 이중 추천(비용 최적안 + 초과 최소 안전안) 구성
        recommendation_options = self._build_recommendation_options(
            optimization, prediction_distribution, p50, p95
        )

        recommendation = ContractRecommendation(
            station_id=station_id,
            analysis_date=datetime.now().isoformat(),
            recommended_contract_kw=optimization.optimal_contract_kw,
            current_contract_kw=current_contract_kw,
            expected_annual_cost=optimization.expected_annual_cost,
            expected_annual_savings=optimization.expected_savings,
            savings_percent=optimization.savings_percent,
            predicted_peak_p50=p50,
            predicted_peak_p95=p95,
            overage_probability=optimization.overage_probability,
            waste_probability=optimization.waste_probability,
            confidence_level=optimization.confidence_level,
            recommendation_summary=optimization.recommendation_reason,
            detailed_reasoning=detailed_reasoning,
            action_required=action_required,
            urgency_level=urgency,
            cost_comparison_data=cost_comparison,
            candidate_analysis_data=candidate_analysis,
            optimization_details=optimization_details,
            recommendation_options=recommendation_options
        )
        
        self.logger.info(
            f"Station {station_id}: 추천 완료 - {optimization.optimal_contract_kw}kW "
            f"(절감: {optimization.expected_savings:,.0f}원)" if optimization.expected_savings else ""
        )
        
        return recommendation

    def _estimate_contract_ceiling(
        self,
        distribution: Any,
        current_contract_kw: Optional[int]
    ) -> int:
        """과다 계약 비교를 위한 동적 상한 계산"""

        try:
            dist_array = np.asarray(distribution, dtype=float)
        except Exception:
            dist_array = np.array([])

        if dist_array.size == 0:
            base_kw = float(current_contract_kw or 120)
        else:
            p95 = float(np.percentile(dist_array, 95))
            p99 = float(np.percentile(dist_array, 99))
            base_kw = max(p99, p95 + 10.0)

        if current_contract_kw:
            base_kw = max(base_kw, float(current_contract_kw))

        step = getattr(self.optimizer, "candidate_step", 10) or 10
        headroom = max(40.0, step * 3)
        target_kw = max(base_kw + headroom, getattr(self.optimizer, "minimum_over_contract_kw", 120))
        padded_kw = int(np.ceil(target_kw / step) * step)
        hard_cap = 400

        return min(hard_cap, max(step, padded_kw))
    
    def _generate_detailed_reasoning(
        self,
        optimization: OptimizationResult,
        distribution: Any
    ) -> List[str]:
        """상세 추천 사유 생성"""
        import numpy as np
        
        reasons = []
        
        # 1. 데이터 기반 분석
        sample_size = len(distribution)
        reasons.append(
            f"📊 {sample_size:,}개 예측 시나리오 분석 완료 "
            f"(신뢰도: {optimization.confidence_level:.0%})"
        )
        
        # 2. 예측 결과
        mean_peak = np.mean(distribution)
        std_peak = np.std(distribution)
        reasons.append(
            f"⚡ 예측 피크: 평균 {mean_peak:.0f}kW, "
            f"표준편차 ±{std_peak:.0f}kW"
        )
        
        # 3. 최적 계약 선정 이유
        optimal = optimization.optimal_candidate
        reasons.append(
            f"✅ 최적 계약 {optimal.contract_kw}kW 선정: "
            f"연간 비용 {optimal.expected_annual_cost:,.0f}원"
        )
        
        # 4. 리스크 평가
        if optimal.overage_probability < 5:
            risk_msg = f"🟢 초과 위험 매우 낮음 ({optimal.overage_probability:.1f}%)"
        elif optimal.overage_probability < 15:
            risk_msg = f"🟡 초과 위험 적정 ({optimal.overage_probability:.1f}%)"
        else:
            risk_msg = f"🔴 초과 위험 주의 ({optimal.overage_probability:.1f}%)"
        reasons.append(risk_msg)
        
        # 5. 절감 효과
        if optimization.expected_savings and optimization.expected_savings > 0:
            monthly_savings = optimization.expected_savings / 12
            reasons.append(
                f"💰 예상 절감: 연간 {optimization.expected_savings:,.0f}원 "
                f"(월 {monthly_savings:,.0f}원)"
            )
        
        # 6. 10kW 단위 최적화 강조
        reasons.append(
            "🎯 10kW 단위 미세 조정으로 비용 최적화 달성"
        )

        return reasons

    def _assess_action_urgency(
        self,
        optimization: OptimizationResult,
        current_contract_kw: Optional[int]
    ) -> Tuple[bool, str]:
        """
        액션 긴급도 평가

        Returns:
            (action_required, urgency_level): 액션 필요 여부와 긴급도
        """
        # 현재 계약이 없으면 즉시 조치 필요
        if current_contract_kw is None:
            return True, "high"

        # 절감액이 크면 긴급도 높음
        if optimization.expected_savings:
            monthly_savings = optimization.expected_savings / 12
            if monthly_savings > 100000:  # 월 10만원 이상
                return True, "high"
            elif monthly_savings > 50000:  # 월 5만원 이상
                return True, "medium"

        # 초과 위험이 높으면 긴급도 높음
        if optimization.overage_probability > 20:
            return True, "high"
        elif optimization.overage_probability > 10:
            return True, "medium"

        # 과다 계약 낭비가 심하면 조치 필요
        if optimization.waste_probability > 70:
            return True, "medium"
        elif optimization.waste_probability > 50:
            return True, "low"

        # 계약 전력 차이가 크면 조치 필요
        contract_diff = abs(optimization.optimal_contract_kw - current_contract_kw)
        if contract_diff >= 30:
            return True, "high"
        elif contract_diff >= 20:
            return True, "medium"
        elif contract_diff >= 10:
            return True, "low"

        # 그 외에는 조치 불필요
        return False, "low"

    def _prepare_cost_comparison(
        self,
        optimization: OptimizationResult,
        current_contract: Optional[int]
    ) -> Dict[str, Any]:
        """비용 비교 데이터 준비 (차트용)"""
        if current_contract is None:
            return {
                "has_comparison": False,
                "recommended": {
                    "contract_kw": optimization.optimal_contract_kw,
                    "annual_cost": optimization.expected_annual_cost
                }
            }

        return {
            "has_comparison": True,
            "current": {
                "contract_kw": current_contract,
                "annual_cost": optimization.expected_annual_cost + (optimization.expected_savings or 0),
                "label": "현행 계약"
            },
            "recommended": {
                "contract_kw": optimization.optimal_contract_kw,
                "annual_cost": optimization.expected_annual_cost,
                "label": "추천 계약"
            },
            "savings": {
                "amount": optimization.expected_savings or 0,
                "percent": optimization.savings_percent or 0
            }
        }
    
    def _prepare_candidate_analysis(
        self,
        candidates: List[Any]  # List[ContractCandidate]
    ) -> List[Dict[str, Any]]:
        """후보 분석 데이터 준비 (차트용)"""
        return [
            {
                "contract_kw": c.contract_kw,
                "annual_cost": c.expected_annual_cost,
                "overage_probability": c.overage_probability,
                "waste_probability": c.waste_probability,
                "risk_score": c.risk_score,
                "session_overage_probability": c.session_overage_probability,
                "session_average_overshoot_kw": c.session_average_overshoot_kw,
                "session_max_overshoot_kw": c.session_max_overshoot_kw,
                "session_waste_probability": c.session_waste_probability,
                "session_average_waste_kw": c.session_average_waste_kw,
                "session_sample_size": c.session_sample_size,
                "session_expected_waste_cost": c.session_expected_waste_cost
            }
            for c in sorted(candidates, key=lambda x: x.contract_kw)
        ]
    
    def _prepare_optimization_details(
        self,
        optimization: OptimizationResult,
        distribution: Any,
        historical_peaks: Optional[List[Dict[str, Any]]] = None,
        session_series: Optional[List[Dict[str, Any]]] = None,
        session_prediction_series: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """최적화 상세 데이터 준비 (시각화용)"""
        import numpy as np
        series_for_metrics = session_prediction_series or session_series or []
        shortfall_simulations = self._build_shortfall_simulations(
            optimization.all_candidates,
            distribution,
            historical_peaks,
            series_for_metrics
        )
        session_prediction_assessment = self._build_session_prediction_assessment(
            series_for_metrics,
            optimization.all_candidates
        )

        return {
            "optimal_contract_kw": optimization.optimal_contract_kw,
            "current_contract_kw": optimization.current_contract_kw,
            "optimal_candidate": {
                "contract_kw": optimization.optimal_candidate.contract_kw,
                "expected_annual_cost": optimization.optimal_candidate.expected_annual_cost,
                "overage_probability": optimization.optimal_candidate.overage_probability,
                "waste_probability": optimization.optimal_candidate.waste_probability,
                "risk_score": optimization.optimal_candidate.risk_score
            },
            "all_candidates": [
                {
                    "contract_kw": c.contract_kw,
                    "expected_annual_cost": c.expected_annual_cost,
                    "overage_probability": c.overage_probability,
                    "waste_probability": c.waste_probability,
                    "cost_std": c.cost_std,
                    "risk_score": c.risk_score,
                    "session_overage_probability": c.session_overage_probability,
                    "session_average_overshoot_kw": c.session_average_overshoot_kw,
                    "session_max_overshoot_kw": c.session_max_overshoot_kw,
                    "session_waste_probability": c.session_waste_probability,
                    "session_average_waste_kw": c.session_average_waste_kw,
                    "session_sample_size": c.session_sample_size,
                    "session_expected_waste_cost": c.session_expected_waste_cost
                }
                for c in sorted(optimization.all_candidates, key=lambda x: x.contract_kw)
            ],
            "prediction_distribution": distribution.tolist() if hasattr(distribution, 'tolist') else list(distribution),
            "distribution_stats": {
                "mean": float(np.mean(distribution)),
                "std": float(np.std(distribution)),
                "q5": float(np.percentile(distribution, 5)),
                "q50": float(np.percentile(distribution, 50)),
                "q95": float(np.percentile(distribution, 95)),
                "min": float(np.min(distribution)),
                "max": float(np.max(distribution))
            },
            "expected_savings": optimization.expected_savings,
            "savings_percent": optimization.savings_percent,
            "daily_peak_series": historical_peaks or [],
            "session_power_series": session_series or [],
            "session_prediction_series": session_prediction_series or session_series or [],
            "contract_shortfall_simulations": shortfall_simulations,
            "session_prediction_assessment": session_prediction_assessment
        }

    def _normalize_session_prediction_points(
        self,
        session_predictions: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        if not isinstance(session_predictions, list):
            return []

        # 타임스탬프를 항목마다 pd.to_datetime(스칼라)로 파싱하면 매번 포맷을 추측해
        # 수천 세션 처리 시 수 초가 소요된다. 먼저 모든 타임스탬프를 모아 단 1회 벡터화
        # 파싱한 뒤 결과를 순회한다.
        raw_timestamps: List[Any] = []
        raw_values: List[Any] = []
        for entry in session_predictions:
            timestamp = entry.get("timestamp") or entry.get("date") or entry.get("time")
            value = (
                entry.get("predicted_peak_kw")
                or entry.get("predictedPeakKw")
                or entry.get("peak_kw")
                or entry.get("peakKw")
                or entry.get("value")
            )
            if timestamp is None or value is None:
                continue
            raw_timestamps.append(timestamp)
            raw_values.append(value)

        if not raw_timestamps:
            return []

        parsed_ts = pd.to_datetime(pd.Series(raw_timestamps), errors="coerce")

        normalized: List[Dict[str, Any]] = []
        for ts, value in zip(parsed_ts, raw_values):
            if pd.isna(ts):
                continue
            try:
                normalized.append({
                    "timestamp": ts,
                    "value": float(value)
                })
            except (TypeError, ValueError):
                continue

        return sorted(normalized, key=lambda item: item["timestamp"])

    def _build_session_prediction_assessment(
        self,
        session_predictions: Optional[List[Dict[str, Any]]],
        candidates: List[Any]
    ) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_session_prediction_points(session_predictions)
        if not normalized:
            return None

        first_ts = normalized[0]["timestamp"]
        last_ts = normalized[-1]["timestamp"]
        span_days = (last_ts - first_ts).days if first_ts and last_ts else None

        return {
            "total_points": len(normalized),
            "time_span_days": span_days,
            "first_timestamp": first_ts.isoformat() if first_ts else None,
            "last_timestamp": last_ts.isoformat() if last_ts else None,
            "candidates": [
                {
                    "contract_kw": c.contract_kw,
                    "session_overage_probability": c.session_overage_probability,
                    "session_average_overshoot_kw": c.session_average_overshoot_kw,
                    "session_max_overshoot_kw": c.session_max_overshoot_kw,
                    "session_waste_probability": c.session_waste_probability,
                    "session_average_waste_kw": c.session_average_waste_kw,
                    "session_expected_waste_cost": c.session_expected_waste_cost,
                    "session_sample_size": c.session_sample_size
                }
                for c in sorted(candidates, key=lambda item: item.contract_kw)
            ]
        }

    def _assess_session_predictions(
        self,
        session_predictions: Optional[List[Dict[str, Any]]],
        contract_kw: float,
        sample_limit: int = 80
    ) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_session_prediction_points(session_predictions)
        if not normalized:
            return None

        values = [item["value"] for item in normalized]
        if not values:
            return None

        total = len(values)
        overshoot_points = [item for item in normalized if item["value"] > contract_kw]
        waste_points = [item for item in normalized if item["value"] < contract_kw]

        def _avg(dataset: List[float]) -> Optional[float]:
            return float(np.mean(dataset)) if dataset else None

        overshoot_magnitudes = [item["value"] - contract_kw for item in overshoot_points]
        waste_magnitudes = [contract_kw - item["value"] for item in waste_points]

        summary = {
            "session_sample_size": total,
            "session_overage_probability": (len(overshoot_points) / total * 100) if total else None,
            "session_average_overshoot_kw": _avg(overshoot_magnitudes),
            "session_max_overshoot_kw": float(np.max(overshoot_magnitudes)) if overshoot_magnitudes else None,
            "session_waste_probability": (len(waste_points) / total * 100) if total else None,
            "session_average_waste_kw": _avg(waste_magnitudes)
        }

        basic_rate = self.cost_calculator.BASIC_RATE_PER_KW
        annual_multiplier = basic_rate * 12
        if (
            summary["session_waste_probability"] is not None and
            summary["session_average_waste_kw"] is not None
        ):
            expected_waste_kw = summary["session_average_waste_kw"] * (summary["session_waste_probability"] / 100)
            summary["session_expected_waste_cost"] = expected_waste_kw * annual_multiplier
        else:
            summary["session_expected_waste_cost"] = None

        samples = [
            {
                "timestamp": item["timestamp"].isoformat(),
                "predicted_peak_kw": round(item["value"], 2),
                "overshoot_kw": round(item["value"] - contract_kw, 2)
            }
            for item in sorted(
                overshoot_points,
                key=lambda point: point["value"],
                reverse=True
            )[:sample_limit]
        ]

        return {
            "summary": summary,
            "samples": samples
        }

    def _build_shortfall_simulations(
        self,
        candidates: List[Any],
        distribution: Any,
        historical_peaks: Optional[List[Dict[str, Any]]] = None,
        session_predictions: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """LSTM 기반 과소 계약 시뮬레이션 데이터 생성"""
        import numpy as np

        try:
            dist_array = np.asarray(distribution, dtype=float)
        except Exception:
            return []

        if dist_array.size == 0 or not candidates:
            return []

        hist_points: List[Dict[str, Any]] = []
        if isinstance(historical_peaks, list):
            for entry in historical_peaks:
                date_value = entry.get("date") or entry.get("day") or entry.get("timestamp")
                peak_value = entry.get("peak_kw") or entry.get("peakKw") or entry.get("value")
                if not date_value:
                    continue
                try:
                    peak_float = float(peak_value)
                except (TypeError, ValueError):
                    continue
                hist_points.append({
                    "date": str(date_value),
                    "peak_kw": peak_float
                })

        # 최근 데이터 위주로 최대 120일치만 사용
        if hist_points:
            hist_points = sorted(hist_points, key=lambda item: item["date"])[-120:]

        # === 향후 3개월(90일) 일별 예측 베이스라인 (계약과 무관한 수요 예측) ===
        PROJECTION_DAYS = 90

        anchor_ts = datetime.now()
        if hist_points:
            latest_date = pd.to_datetime(hist_points[-1].get("date"), errors="coerce")
            if not pd.isna(latest_date):
                anchor_ts = latest_date.to_pydatetime()

        # === 과거 실측 기반 일별 예측 (학습→테스트 근사성을 우선) ===
        # p50은 "해당 날짜의 기대 피크"를 추적해야 실측 테스트와 MAE/상관계수가 개선됨.
        # 카드 값(P95)과의 정합은 프런트의 기준선(horizontal annotation)이 담당.
        hist_peaks_arr = (
            np.array([p["peak_kw"] for p in hist_points], dtype=float)
            if hist_points else np.array([], dtype=float)
        )

        if hist_peaks_arr.size >= 14:
            # 최근 60일의 평균 + 요일 계절성 (추세항은 장기 드리프트 오해 방지 위해 제외)
            recent_window = hist_peaks_arr[-min(60, hist_peaks_arr.size):]
            mu_recent = float(np.mean(recent_window))
            std_local = float(np.std(recent_window)) or 1.0

            # 요일별 승수 (unnormalized — 평균 ≈ 1.0, 자연스러운 ±10~20% swing)
            overall_mean = mu_recent
            weekday_sum: Dict[int, List[float]] = {wd: [] for wd in range(7)}
            # 날짜를 항목마다 파싱하지 않고 한 번에 벡터화 파싱
            hist_dates = pd.to_datetime(
                pd.Series([p["date"] for p in hist_points]), errors="coerce"
            )
            for dt, p in zip(hist_dates, hist_points):
                if pd.isna(dt):
                    continue
                weekday_sum[dt.weekday()].append(float(p["peak_kw"]))
            weekly_factor: Dict[int, float] = {}
            for wd in range(7):
                vals = weekday_sum.get(wd, [])
                weekly_factor[wd] = (
                    float(np.mean(vals)) / overall_mean if vals and overall_mean > 0 else 1.0
                )
        else:
            mu_recent = float(dist_array.mean()) if dist_array.size else 0.0
            std_local = float(dist_array.std()) if dist_array.size else 5.0
            weekly_factor = {wd: 1.0 for wd in range(7)}

        # 잔차 기반 σ (MC 분포가 피크 레벨이라 너무 크면 일별 변동성을 왜곡 → 실측 std 우선)
        base_std = max(std_local, 1.0)

        # 일별 μ / σ / 분위수 (3개월) — 추세 없이 요일 계절성 + 지평선 기반 σ 확산
        daily_forecast: List[Dict[str, float]] = []
        for idx in range(PROJECTION_DAYS):
            future_dt = anchor_ts + timedelta(days=idx + 1)
            wf = weekly_factor.get(future_dt.weekday(), 1.0)
            mu_d = mu_recent * wf
            # 지평선 √t 확산, 상한 캡
            horizon_factor = float(min(np.sqrt(1.0 + idx / 30.0), 1.8))
            sigma_d = base_std * horizon_factor
            p10 = max(0.0, mu_d - 1.2816 * sigma_d)
            p50 = mu_d
            p90 = mu_d + 1.2816 * sigma_d
            p95 = mu_d + 1.645 * sigma_d
            daily_forecast.append({
                "date": future_dt.date().isoformat(),
                "weekday": future_dt.weekday(),
                "mu": mu_d,
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "p95": p95,
                "std": sigma_d,
            })

        # 모델 분포 통계 — 계약 후보와 무관한, 모델이 예측한 미래 피크의 평균/P50/P90/P95.
        # 프런트에서 "예측 피크 평균/P90"을 표시할 때 계약값을 베이스로 깐 가산식이 아니라
        # 이 분포 값을 직접 사용하도록 노출한다.
        if daily_forecast:
            model_peak_avg_kw = float(np.mean([f["p50"] for f in daily_forecast]))
            model_peak_p50_kw = float(np.median([f["p50"] for f in daily_forecast]))
            model_peak_p90_kw = float(np.mean([f["p90"] for f in daily_forecast]))
            model_peak_p95_kw = float(np.mean([f["p95"] for f in daily_forecast]))
            model_peak_max_p90_kw = float(np.max([f["p90"] for f in daily_forecast]))
        else:
            model_peak_avg_kw = float(dist_array.mean()) if dist_array.size else 0.0
            model_peak_p50_kw = float(np.percentile(dist_array, 50)) if dist_array.size else 0.0
            model_peak_p90_kw = float(np.percentile(dist_array, 90)) if dist_array.size else 0.0
            model_peak_p95_kw = float(np.percentile(dist_array, 95)) if dist_array.size else 0.0
            model_peak_max_p90_kw = model_peak_p90_kw

        simulations: List[Dict[str, Any]] = []

        for candidate in sorted(candidates, key=lambda item: item.contract_kw):
            contract_kw = float(getattr(candidate, "contract_kw", 0))
            if contract_kw <= 0:
                continue

            overshoot_samples = dist_array - contract_kw
            positive_samples = overshoot_samples[overshoot_samples > 0]
            overshoot_probability = float(
                (positive_samples.size / dist_array.size) * 100
            ) if dist_array.size else 0.0

            expected_overshoot_kw = float(positive_samples.mean()) if positive_samples.size else 0.0
            p90_overshoot_kw = float(np.percentile(positive_samples, 90)) if positive_samples.size else 0.0

            daily_projection: List[Dict[str, Any]] = []

            # 과거 관측 피크 참조값 (요일 매핑) — 프런트 표시용
            historical_refs: List[float] = [float(p["peak_kw"]) for p in hist_points] if hist_points else []
            margin = max(contract_kw * 0.2, 5.0)

            for idx, f in enumerate(daily_forecast):
                mu_d = f["mu"]
                p10 = f["p10"]
                p50 = f["p50"]
                p90 = f["p90"]
                p95 = f["p95"]
                sigma_d = f["std"]
                # 계약 대비 일별 리스크 계수 (예측 p50 기준)
                risk_factor = max(0.0, min(1.0, (p50 - contract_kw) / margin))
                historical_peak = (
                    historical_refs[idx % len(historical_refs)] if historical_refs else mu_d
                )
                daily_projection.append({
                    "date": f["date"],
                    "historical_peak_kw": round(float(historical_peak), 2),
                    "simulated_peak_kw": round(p50, 2),
                    "p10_kw": round(p10, 2),
                    "p50_kw": round(p50, 2),
                    "p90_kw": round(p90, 2),
                    "p95_kw": round(p95, 2),
                    "std_kw": round(sigma_d, 2),
                    "overshoot_kw": round(max(0.0, p50 - contract_kw), 2),
                    "overshoot_p90_kw": round(max(0.0, p90 - contract_kw), 2),
                    "risk_factor": round(risk_factor, 3)
                })

            session_eval = self._assess_session_predictions(
                session_predictions,
                contract_kw
            )
            session_summary = session_eval.get("summary") if session_eval else None
            session_samples = session_eval.get("samples") if session_eval else []

            simulations.append({
                "contract_kw": int(contract_kw),
                "overshoot_probability": round(overshoot_probability, 2),
                "expected_overshoot_kw": round(expected_overshoot_kw, 2),
                "p90_overshoot_kw": round(p90_overshoot_kw, 2),
                # 계약 후보와 독립적인 모델 분포 통계 (프런트의 "예측 피크 평균/P90" 표시용)
                "model_peak_avg_kw": round(model_peak_avg_kw, 2),
                "model_peak_p50_kw": round(model_peak_p50_kw, 2),
                "model_peak_p90_kw": round(model_peak_p90_kw, 2),
                "model_peak_p95_kw": round(model_peak_p95_kw, 2),
                "model_peak_max_p90_kw": round(model_peak_max_p90_kw, 2),
                "model_source": "lstm_mc_dropout",
                "updated_at": datetime.now().isoformat(),
                "daily_projection": daily_projection,
                "session_prediction_summary": session_summary,
                "session_prediction_samples": session_samples
            })

        return simulations
    
    def _build_recommendation_options(
        self,
        optimization: OptimizationResult,
        prediction_distribution: Any,
        p50: float,
        p95: float,
        step: int = 10,
    ) -> Dict[str, Any]:
        """비용 최적안 + 초과 최소(안전)안 2가지를 함께 제시한다.

        - cost_optimal : 총 전기요금(기본료+초과벌금)이 최소인 계약. 초과를 일부 감수.
        - overage_minimized : 예측 P95 를 덮는 가장 작은 10kW 단계 계약. 초과를 거의 안 함(≈5% 이하).
                              기본료를 더 내지만 초과 위험을 최소화.
        둘이 같은 값이면(이미 비용안이 P95 를 덮으면) same=True.
        """
        try:
            dist = np.asarray(prediction_distribution, dtype=float)
            dist = dist[np.isfinite(dist)]
        except Exception:
            dist = np.array([])

        cost_calc = KEPCOCostCalculator()

        def overage_prob(kw: float) -> float:
            return float((dist > kw).mean() * 100) if dist.size else 0.0

        def annual_cost(kw: float) -> float:
            # 분포 전체에 대한 기대 연간 비용 (기본료 + 초과벌금)
            if dist.size:
                monthly = float(np.mean([
                    cost_calc.calculate_monthly_cost(kw, float(pk)).total_cost for pk in dist
                ]))
                return monthly * 12
            return float(kw) * cost_calc.BASIC_RATE_PER_KW * 12

        # 1) 균형 최적안 (옵티마이저 결과 = 비용+리스크 종합 최적, 권장 계약전력과 동일)
        co_kw = int(optimization.optimal_contract_kw)
        cost_optimal = {
            "contract_kw": co_kw,
            "annual_cost": float(optimization.expected_annual_cost),
            "overage_probability": round(float(optimization.overage_probability), 1),
            "label": "균형 최적안",
            "description": (
                f"비용과 초과 위험을 함께 고려한 종합 최적 계약입니다(권장 계약전력). "
                f"예측 피크가 이 값을 연 {float(optimization.overage_probability):.0f}% 초과할 수 있습니다."
            ),
        }

        # 2) 초과 최소(안전)안 — P95 를 덮는 가장 작은 10kW 단계 (비용안 이상으로 보장)
        safety_kw = int(np.ceil(max(p95, co_kw) / step) * step)
        safety_kw = max(safety_kw, co_kw)
        s_over = overage_prob(safety_kw)
        overage_minimized = {
            "contract_kw": safety_kw,
            "annual_cost": round(annual_cost(safety_kw), 0),
            "overage_probability": round(s_over, 1),
            "label": "초과 최소(안전)안",
            "description": (
                f"예측 최고전력(P95 {p95:.0f}kW)을 덮어 초과 확률이 약 {s_over:.0f}% 로 낮습니다. "
                f"기본요금을 더 부담하는 대신 초과 위험을 최소화합니다."
            ),
        }

        same = safety_kw == co_kw
        # 안전안의 추가 비용(비용안 대비)
        extra_cost = round(overage_minimized["annual_cost"] - cost_optimal["annual_cost"], 0)
        return {
            "cost_optimal": cost_optimal,
            "overage_minimized": overage_minimized,
            "same": same,
            "safety_extra_annual_cost": extra_cost if not same else 0,
            "note": (
                "균형 최적안과 초과 최소안이 동일합니다." if same else
                f"초과 최소안은 균형 최적안보다 연 {extra_cost:,.0f}원 더 들지만 초과 위험이 낮습니다."
            ),
        }

    def to_dict(self, recommendation: ContractRecommendation) -> Dict[str, Any]:
        """추천 결과를 딕셔너리로 변환 (API 응답용)"""
        result = asdict(recommendation)
        
        # annual_savings_won 키 추가 (하위 호환성)
        if recommendation.expected_annual_savings:
            result['annual_savings_won'] = recommendation.expected_annual_savings
            result['monthly_savings'] = recommendation.expected_annual_savings / 12
        
        # savings_percentage 키 추가
        if recommendation.current_contract_kw and recommendation.expected_annual_savings:
            current_annual_cost = recommendation.current_contract_kw * 8320 * 12
            result['savings_percentage'] = (
                recommendation.expected_annual_savings / current_annual_cost * 100
                if current_annual_cost > 0 else 0
            )
        
        # recommendation 키 추가 (추천 요약문)
        result['recommendation'] = recommendation.recommendation_summary
        
        # risk_assessment 키 추가
        result['risk_assessment'] = {
            'risk_level': recommendation.urgency_level,
            'overage_probability': recommendation.overage_probability,
            'waste_probability': recommendation.waste_probability,
            'confidence_level': recommendation.confidence_level
        }
        
        return result
