"""
계약전력 최적화 엔진 테스트

10kW 단위 최적화 핵심 기능 검증
"""

import numpy as np
from app.contract import ContractOptimizer, KEPCOCostCalculator, RecommendationEngine

def test_cost_calculator():
    """한전 요금 계산기 테스트"""
    print("\n=== 한전 요금 계산기 테스트 ===")
    
    calculator = KEPCOCostCalculator()
    
    # 테스트 1: 과다계약 (120kW 계약, 실제 100kW)
    print("\n[테스트 1] 과다계약 시나리오")
    result = calculator.calculate_monthly_cost(120, 100)
    print(f"  계약: 120kW, 실제: 100kW")
    print(f"  기본요금: {result.basic_cost:,}원")
    print(f"  기회비용: {result.opportunity_cost:,}원 (낭비 {result.waste_kw}kW)")
    print(f"  총 비용: {result.total_cost:,}원")
    
    # 테스트 2: 과소계약 (80kW 계약, 실제 100kW)
    print("\n[테스트 2] 과소계약 시나리오")
    result = calculator.calculate_monthly_cost(80, 100)
    print(f"  계약: 80kW, 실제: 100kW")
    print(f"  기본요금: {result.basic_cost:,}원")
    print(f"  초과부가금: {result.overage_cost:,}원 (초과 {result.overage_kw}kW)")
    print(f"  총 비용: {result.total_cost:,}원")
    
    # 테스트 3: 적정계약 (110kW 계약, 실제 105kW)
    print("\n[테스트 3] 적정계약 시나리오")
    result = calculator.calculate_monthly_cost(110, 105)
    print(f"  계약: 110kW, 실제: 105kW")
    print(f"  기본요금: {result.basic_cost:,}원")
    print(f"  총 비용: {result.total_cost:,}원")
    
    # 테스트 4: 계약 비교
    print("\n[테스트 4] 계약 비교 (120kW -> 110kW)")
    comparison = calculator.compare_contracts(120, 110, 105)
    print(f"  현재 (120kW): 연간 {comparison['current']['annual_cost']:,}원")
    print(f"  신규 (110kW): 연간 {comparison['new']['annual_cost']:,}원")
    print(f"  절감액: 연간 {comparison['savings']['annual']:,}원 ({comparison['savings']['percent']:.1f}%)")
    print(f"  추천: {comparison['recommendation']}")

def test_optimizer():
    """계약전력 최적화 엔진 테스트"""
    print("\n\n=== 계약전력 최적화 엔진 테스트 ===")
    
    optimizer = ContractOptimizer()
    
    # Monte Carlo 시뮬레이션 (평균 110kW, 표준편차 15kW, 1000회)
    np.random.seed(42)
    prediction_distribution = np.random.normal(110, 15, 1000)
    
    print(f"\n예측 분포: 평균 {np.mean(prediction_distribution):.1f}kW, "
          f"표준편차 {np.std(prediction_distribution):.1f}kW")
    print(f"  P50: {np.percentile(prediction_distribution, 50):.1f}kW")
    print(f"  P95: {np.percentile(prediction_distribution, 95):.1f}kW")
    
    # 최적화 실행
    print("\n[최적화 실행]")
    result = optimizer.optimize_contract(
        prediction_distribution=prediction_distribution,
        current_contract_kw=120,
        risk_tolerance=0.5  # 중립적 리스크
    )
    
    print(f"\n✅ 최적 계약전력: {result.optimal_contract_kw}kW")
    print(f"  현재 계약: {result.current_contract_kw}kW")
    print(f"  예상 연간 비용: {result.expected_annual_cost:,}원")
    print(f"  예상 절감액: {result.expected_savings:,}원 ({result.savings_percent:.1f}%)")
    print(f"  초과 확률: {result.overage_probability:.1f}%")
    print(f"  낭비 확률: {result.waste_probability:.1f}%")
    print(f"  신뢰도: {result.confidence_level:.1%}")
    
    print(f"\n📊 후보 분석:")
    print(f"  총 후보 수: {len(result.all_candidates)}개")
    print(f"  후보 범위: {result.all_candidates[0].contract_kw}kW ~ {result.all_candidates[-1].contract_kw}kW")
    
    # 상위 3개 후보
    print(f"\n  [상위 3개 후보]")
    sorted_candidates = sorted(result.all_candidates, key=lambda x: x.expected_annual_cost)
    for i, candidate in enumerate(sorted_candidates[:3], 1):
        print(f"    {i}. {candidate.contract_kw}kW: "
              f"연간 {candidate.expected_annual_cost:,}원, "
              f"초과확률 {candidate.overage_probability:.1f}%")
    
    print(f"\n💡 추천 사유:")
    print(f"  {result.recommendation_reason}")

def test_recommendation_engine():
    """추천 엔진 테스트"""
    print("\n\n=== 추천 엔진 테스트 ===")
    
    engine = RecommendationEngine()
    
    # 예측 분포 생성
    np.random.seed(42)
    prediction_distribution = np.random.normal(110, 15, 1000)
    
    # 추천 생성
    recommendation = engine.generate_recommendation(
        station_id="TEST_STATION_001",
        prediction_distribution=prediction_distribution,
        current_contract_kw=120
    )
    
    print(f"\n충전소: {recommendation.station_id}")
    print(f"분석 일시: {recommendation.analysis_date}")
    
    print(f"\n📌 추천 계약전력: {recommendation.recommended_contract_kw}kW")
    print(f"  현재 계약: {recommendation.current_contract_kw}kW")
    print(f"  예상 연간 비용: {recommendation.expected_annual_cost:,}원")
    print(f"  예상 절감액: {recommendation.expected_annual_savings:,}원 ({recommendation.savings_percent:.1f}%)")
    
    print(f"\n⚡ 예측 피크:")
    print(f"  중앙값 (P50): {recommendation.predicted_peak_p50:.1f}kW")
    print(f"  95백분위 (P95): {recommendation.predicted_peak_p95:.1f}kW")
    
    print(f"\n⚠️ 리스크 분석:")
    print(f"  초과 확률: {recommendation.overage_probability:.1f}%")
    print(f"  낭비 확률: {recommendation.waste_probability:.1f}%")
    print(f"  신뢰도: {recommendation.confidence_level:.1%}")
    
    print(f"\n✅ 액션:")
    print(f"  조치 필요: {'예' if recommendation.action_required else '아니오'}")
    print(f"  긴급도: {recommendation.urgency_level}")
    
    print(f"\n📋 상세 사유:")
    for i, reason in enumerate(recommendation.detailed_reasoning, 1):
        print(f"  {i}. {reason}")

def test_real_scenario():
    """실제 시나리오 테스트"""
    print("\n\n=== 실제 시나리오 테스트 ===")
    print("시나리오: 급속충전소, 현재 160kW 계약, 실제 최대 110kW 사용")
    
    calculator = KEPCOCostCalculator()
    optimizer = ContractOptimizer()
    
    # 실제와 유사한 분포 (약간의 변동성 포함)
    np.random.seed(100)
    # 평균 110kW, 하지만 계절성과 변동성 고려
    base_distribution = np.random.normal(110, 12, 1000)
    
    # 현재 계약 비용
    current_cost = calculator.calculate_annual_cost(160, 110)
    print(f"\n현재 상황:")
    print(f"  계약: 160kW, 실제 피크: 110kW")
    print(f"  연간 비용: {current_cost:,}원")
    print(f"  낭비 전력: 50kW (기회비용: {50 * 8320 * 12:,}원/년)")
    
    # 최적화
    result = optimizer.optimize_contract(
        base_distribution,
        current_contract_kw=160,
        risk_tolerance=0.3  # 보수적 (초과 위험 최소화)
    )
    
    print(f"\n최적화 결과:")
    print(f"  추천 계약: {result.optimal_contract_kw}kW")
    print(f"  예상 절감액: 연간 {result.expected_savings:,}원")
    print(f"  초과 위험: {result.overage_probability:.1f}%")
    
    # 비교
    comparison = calculator.compare_contracts(160, result.optimal_contract_kw, 110)
    print(f"\n상세 비교:")
    print(f"  {comparison['recommendation']}")

if __name__ == "__main__":
    print("="*60)
    print("계약전력 최적화 엔진 종합 테스트")
    print("="*60)
    
    test_cost_calculator()
    test_optimizer()
    test_recommendation_engine()
    test_real_scenario()
    
    print("\n" + "="*60)
    print("✅ 모든 테스트 완료!")
    print("="*60)
