<script lang="ts">
	/**
	 * 확률 및 비용 산정 모듈 UI
	 *
	 * Nielsen의 휴리스틱 원칙 적용:
	 * 1. 시스템 상태의 가시성 (Visibility of system status)
	 * 2. 실제 세계와의 일치 (Match between system and real world)
	 * 3. 사용자 제어와 자유 (User control and freedom)
	 * 4. 일관성과 표준 (Consistency and standards)
	 * 5. 오류 예방 (Error prevention)
	 * 6. 인식보다 기억 (Recognition rather than recall)
	 * 7. 유연성과 효율성 (Flexibility and efficiency of use)
	 * 8. 미니멀하고 미적인 디자인 (Aesthetic and minimalist design)
	 * 9. 오류 인식 및 복구 (Help users recognize, diagnose, and recover from errors)
	 * 10. 도움말과 문서화 (Help and documentation)
	 */

	import MetricCard from './MetricCard.svelte';
	import type { ContractRecommendation } from '../../lib/types';

	export let recommendation: ContractRecommendation | null = null;
	export let currentContractKw: number | null = null;
	export let loading = false;

	// 계약 시나리오 상태
	let selectedScenario: 'optimal' | 'current' | 'custom' = 'optimal';
	let customContractKw: number | null = null;
	let showAdvancedOptions = false;

	// 시뮬레이션 결과
	let simulationResults: CostSimulation[] = [];
	let riskMetrics: RiskMetrics | null = null;

	// 비교 모드
	let comparisonMode: 'monthly' | 'annual' = 'annual';
	let optimalTotalExpectedCost = 0;

	// 사용자 피드백
	let errorMessage = '';

	// 타입 정의
	interface CostSimulation {
		contractKw: number;
		scenario: string;
		basicCost: number;           // 기본요금
		overageProbability: number;  // 초과 확률
		expectedOverageCost: number; // 예상 초과요금
		wasteProbability: number;    // 낭비 확률
		expectedWasteCost: number;   // 예상 낭비비용
		totalExpectedCost: number;   // 총 예상비용
		riskLevel: 'low' | 'medium' | 'high';
		isOptimal: boolean;
	}

	interface RiskMetrics {
		overageRisk: number;     // 0-100
		wasteRisk: number;       // 0-100
		confidenceLevel: number; // 0-100
		recommendation: string;
	}

	// 상수
	const BASIC_RATE_PER_KW = 8320;
	const OVERAGE_PENALTY_MULTIPLIER = 1.5;
	const CONTRACT_STEP = 10; // 10kW 단위

	// 휴리스틱 1: 시스템 상태의 가시성
	$: statusMessage = getStatusMessage(loading, recommendation);
	$: progressPercent = loading ? 50 : recommendation ? 100 : 0;

	// 휴리스틱 2: 실제 세계와의 일치
	function getScenarioLabel(scenario: string): string {
		const labels: Record<string, string> = {
			under: '⚠️ 과소 계약',
			optimal: '✅ 최적 계약',
			over: '📊 과다 계약',
			current: '📌 현재 계약',
			custom: '⚙️ 사용자 지정'
		};
		return labels[scenario] || scenario;
	}

	// 데이터 업데이트 시 시뮬레이션 재실행
	$: if (recommendation) {
		updateSimulations();
		calculateRiskMetrics();
	}

	$: {
		const optimalScenario = simulationResults.find((simulation) => simulation.isOptimal);
		optimalTotalExpectedCost = optimalScenario?.totalExpectedCost ?? 0;
	}

	// 후보 데이터를 계약전력 순서로 정렬
	$: sortedCandidates = recommendation?.candidate_analysis_data
		? [...recommendation.candidate_analysis_data].sort((a: any, b: any) => {
				const aKw = Number(a.contract_kw ?? 0);
				const bKw = Number(b.contract_kw ?? 0);
				return aKw - bKw;
		  })
		: [];

	function getStatusMessage(loading: boolean, rec: any): string {
		if (loading) return '데이터를 분석하고 있습니다...';
		if (!rec) return '분석할 데이터가 없습니다';
		return '분석 완료';
	}

	function updateSimulations() {
		if (!recommendation) return;

		const scenarios: CostSimulation[] = [];
		const optimalKw = recommendation.recommended_contract_kw;

		// 1. 과소 계약 시나리오 (최적안보다 낮음)
		const underContractKw = optimalKw - CONTRACT_STEP;
		if (underContractKw >= CONTRACT_STEP) {
			const underCandidate = recommendation.candidate_analysis_data?.find(
				(c: any) => c.contract_kw === underContractKw
			);
			scenarios.push(createSimulation(
				underContractKw,
				'under',
				typeof underCandidate?.overage_probability === 'number' ? underCandidate.overage_probability : 0,
				typeof underCandidate?.waste_probability === 'number' ? underCandidate.waste_probability : 0,
				false
			));
		}

		// 2. 최적 계약 시나리오
		scenarios.push(createSimulation(
			optimalKw,
			'optimal',
			recommendation.overage_probability,
			recommendation.waste_probability,
			true
		));

		// 3. 과다 계약 시나리오 (최적안보다 높음)
		const overContractKw = optimalKw + CONTRACT_STEP;
		const overCandidate = recommendation.candidate_analysis_data?.find(
			(c: any) => c.contract_kw === overContractKw
		);
		scenarios.push(createSimulation(
			overContractKw,
			'over',
			typeof overCandidate?.overage_probability === 'number' ? overCandidate.overage_probability : 0,
			typeof overCandidate?.waste_probability === 'number' ? overCandidate.waste_probability : 0,
			false
		));

		// 4. 현재 계약 시나리오 (있는 경우, 별도 표시)
		if (currentContractKw && currentContractKw !== optimalKw) {
			const currentCandidate = recommendation.candidate_analysis_data?.find(
				(c: any) => c.contract_kw === currentContractKw
			);
			scenarios.push(createSimulation(
				currentContractKw,
				'current',
				typeof currentCandidate?.overage_probability === 'number' ? currentCandidate.overage_probability : 0,
				typeof currentCandidate?.waste_probability === 'number' ? currentCandidate.waste_probability : 0,
				false
			));
		}

		// 5. 사용자 지정 시나리오 (있는 경우, 별도 표시)
		if (customContractKw && customContractKw > 0 && customContractKw !== optimalKw) {
			const customCandidate = recommendation.candidate_analysis_data?.find(
				(c: any) => c.contract_kw === customContractKw
			);
			scenarios.push(createSimulation(
				customContractKw,
				'custom',
				typeof customCandidate?.overage_probability === 'number' ? customCandidate.overage_probability : 0,
				typeof customCandidate?.waste_probability === 'number' ? customCandidate.waste_probability : 0,
				false
			));
		}

		simulationResults = scenarios;
	}

	function createSimulation(
		contractKw: number,
		scenario: string,
		overageProb: number,
		wasteProb: number,
		isOptimal: boolean
	): CostSimulation {
		const basicCost = contractKw * BASIC_RATE_PER_KW;

		// 초과요금 예상치 (확률 기반)
		const expectedOverageCost = (basicCost * OVERAGE_PENALTY_MULTIPLIER * overageProb) / 100;

		// 낭비비용 예상치 (확률 기반)
		const expectedWasteCost = (basicCost * wasteProb) / 100;

		const totalExpectedCost = basicCost + expectedOverageCost + expectedWasteCost;

		// 리스크 레벨 계산
		let riskLevel: 'low' | 'medium' | 'high';
		if (overageProb > 20 || wasteProb > 70) {
			riskLevel = 'high';
		} else if (overageProb > 10 || wasteProb > 50) {
			riskLevel = 'medium';
		} else {
			riskLevel = 'low';
		}

		return {
			contractKw,
			scenario,
			basicCost,
			overageProbability: overageProb,
			expectedOverageCost,
			wasteProbability: wasteProb,
			expectedWasteCost,
			totalExpectedCost,
			riskLevel,
			isOptimal
		};
	}

	function calculateRiskMetrics() {
		if (!recommendation) return;

		const overageRisk = recommendation.overage_probability;
		const wasteRisk = recommendation.waste_probability;
		const confidenceLevel = recommendation.confidence_level * 100;

		let recommendationText = '';
		if (overageRisk < 5 && wasteRisk < 30) {
			recommendationText = '매우 안정적인 계약입니다';
		} else if (overageRisk < 15 && wasteRisk < 50) {
			recommendationText = '균형잡힌 계약입니다';
		} else if (overageRisk > 20) {
			recommendationText = '초과 위험이 높습니다. 계약전력을 상향 조정하세요';
		} else {
			recommendationText = '낭비가 큽니다. 계약전력을 하향 조정하세요';
		}

		riskMetrics = {
			overageRisk,
			wasteRisk,
			confidenceLevel,
			recommendation: recommendationText
		};
	}

	// 휴리스틱 3: 사용자 제어와 자유
	function resetCustomValue() {
		customContractKw = null;
		selectedScenario = 'optimal';
		errorMessage = '';
	}

	// 휴리스틱 5: 오류 예방
	function validateCustomInput(value: number): boolean {
		if (!value || value < CONTRACT_STEP) {
			errorMessage = `최소 ${CONTRACT_STEP}kW 이상 입력해주세요`;
			return false;
		}
		if (value > 1000) {
			errorMessage = '1000kW를 초과할 수 없습니다';
			return false;
		}
		if (value % CONTRACT_STEP !== 0) {
			errorMessage = `${CONTRACT_STEP}kW 단위로 입력해주세요`;
			return false;
		}
		errorMessage = '';
		return true;
	}

	function handleCustomInputChange(event: Event) {
		const input = event.target as HTMLInputElement;
		const value = parseInt(input.value);

		if (isNaN(value)) {
			customContractKw = null;
			return;
		}

		if (validateCustomInput(value)) {
			customContractKw = value;
			selectedScenario = 'custom';
			updateSimulations();
		}
	}

	// 휴리스틱 7: 유연성과 효율성
	function quickSelectContract(kw: number) {
		customContractKw = kw;
		selectedScenario = 'custom';
		updateSimulations();
	}

	// 포맷팅 함수들
	function formatCurrency(value: number, mode: 'monthly' | 'annual' = comparisonMode): string {
		const amount = mode === 'monthly' ? value / 12 : value;
		return amount.toLocaleString('ko-KR', { maximumFractionDigits: 0 });
	}

	function formatPercent(value: number): string {
		return value.toFixed(1);
	}

	function getRiskColor(level: 'low' | 'medium' | 'high'): string {
		return {
			low: 'var(--success-color, #10b981)',
			medium: 'var(--warning-color, #f59e0b)',
			high: 'var(--danger-color, #ef4444)'
		}[level];
	}

	function getRiskLabel(level: 'low' | 'medium' | 'high'): string {
		return {
			low: '낮음',
			medium: '보통',
			high: '높음'
		}[level];
	}

	function getContractDirection(simulation: CostSimulation): 'under' | 'over' | 'balanced' {
		if (!recommendation || simulation.isOptimal) return 'balanced';
		if (simulation.contractKw < recommendation.recommended_contract_kw) return 'under';
		if (simulation.contractKw > recommendation.recommended_contract_kw) return 'over';
		return 'balanced';
	}

	function getPrimaryRiskType(simulation: CostSimulation): 'overage' | 'waste' {
		const direction = getContractDirection(simulation);
		if (direction === 'under') return 'overage';
		if (direction === 'over') return 'waste';
		return simulation.expectedOverageCost >= simulation.expectedWasteCost ? 'overage' : 'waste';
	}

	function getSecondaryRiskType(simulation: CostSimulation): 'overage' | 'waste' {
		return getPrimaryRiskType(simulation) === 'overage' ? 'waste' : 'overage';
	}

	function getRiskTypeLabel(type: 'overage' | 'waste'): string {
		return type === 'overage' ? '과소 리스크 비용(초과 발생)' : '과다 리스크 비용(미사용 계약전력)';
	}

	function getRiskTypeProbability(type: 'overage' | 'waste', simulation: CostSimulation): number {
		return type === 'overage' ? simulation.overageProbability : simulation.wasteProbability;
	}

	function getRiskTypeCost(type: 'overage' | 'waste', simulation: CostSimulation): number {
		return type === 'overage' ? simulation.expectedOverageCost : simulation.expectedWasteCost;
	}

	function getDirectionFocusText(simulation: CostSimulation): string {
		const direction = getContractDirection(simulation);
		if (direction === 'under') return '주요 리스크: 과소';
		if (direction === 'over') return '주요 리스크: 과다';
		return '주요 리스크: 균형';
	}

	function formatRiskCost(value: number): string {
		if (value < 10000) return '미미';
		return `${formatCurrency(value)}원`;
	}

	function formatOptimalDelta(value: number): string {
		if (Math.abs(value) < 1) return '0원';
		const sign = value > 0 ? '+' : '-';
		return `${sign}${formatCurrency(Math.abs(value))}원`;
	}

	function getCandidateAnnualCost(candidate: Record<string, unknown>): number {
		const annualCost = Number(candidate.annual_cost ?? candidate.expected_annual_cost ?? 0);
		return Number.isFinite(annualCost) ? annualCost : 0;
	}

	function getCandidateRiskScore(candidate: Record<string, unknown>): number {
		const riskScore = Number(candidate.risk_score ?? 0);
		return Number.isFinite(riskScore) ? riskScore : 0;
	}

	function getCandidateSelectionScore(candidate: Record<string, unknown>, minAnnualCost: number): number {
		const annualCost = getCandidateAnnualCost(candidate);
		const normalizedCost = minAnnualCost > 0 ? annualCost / minAnnualCost : 1;
		return normalizedCost + getCandidateRiskScore(candidate);
	}

	function getBestSelectionScore(candidates: Array<Record<string, unknown>>): number {
		if (!candidates.length) return 0;
		const minAnnualCost = Math.min(...candidates.map(getCandidateAnnualCost));
		return Math.min(...candidates.map((candidate) => getCandidateSelectionScore(candidate, minAnnualCost)));
	}

	function getSelectionCriterionText(
		candidate: Record<string, unknown>,
		candidates: Array<Record<string, unknown>>,
		optimalKw: number
	): string {
		if (!candidates.length) return '근거 데이터 부족';

		const contractKw = Number(candidate.contract_kw ?? 0);
		const annualCost = getCandidateAnnualCost(candidate);
		const riskScore = getCandidateRiskScore(candidate);
		const minAnnualCost = Math.min(...candidates.map(getCandidateAnnualCost));
		const normalizedCost = minAnnualCost > 0 ? annualCost / minAnnualCost : 1;
		const selectionScore = normalizedCost + riskScore;
		const bestSelectionScore = getBestSelectionScore(candidates);
		const monthlyLoss = annualCost / 12;
		const selected = contractKw === optimalKw;
		const monthlyMin = Math.abs(annualCost - minAnnualCost) < 1e-6;

		if (selected) {
			return `선정: 종합점수 최저 (${selectionScore.toFixed(3)} = 비용정규화 ${normalizedCost.toFixed(3)} + 리스크 ${riskScore.toFixed(3)})`;
		}

		if (monthlyMin) {
			return `월 예상 비용 최소 (${formatCurrency(monthlyLoss, 'monthly')}원/월)지만 종합점수 ${selectionScore.toFixed(3)}가 최적안 ${bestSelectionScore.toFixed(3)}보다 높음`;
		}

		return `미선정: 종합점수 ${selectionScore.toFixed(3)} (최적안 ${bestSelectionScore.toFixed(3)})`;
	}

	$: monthlyMinCandidate = sortedCandidates.length
		? sortedCandidates.reduce((best: Record<string, unknown> | null, candidate: Record<string, unknown>) => {
				if (!best) return candidate;
				return getCandidateAnnualCost(candidate) < getCandidateAnnualCost(best) ? candidate : best;
		  }, null)
		: null;

	$: selectedCandidate = sortedCandidates.find(
		(candidate: Record<string, unknown>) =>
			Number(candidate.contract_kw ?? 0) === (recommendation?.recommended_contract_kw ?? 0)
	);
</script>

<!-- 휴리스틱 1: 시스템 상태의 가시성 -->
<div class="analysis-container">
	<header class="analysis-header">
		<h2>📊 확률 및 비용 산정 분석</h2>
		<p class="status-message" class:loading>{statusMessage}</p>
		{#if loading}
			<div class="progress-bar">
				<div class="progress-fill" style="width: {progressPercent}%"></div>
			</div>
		{/if}
	</header>

	{#if !loading && recommendation}
		<!-- 휴리스틱 6: 인식보다 기억 - 핵심 메트릭을 항상 표시 -->
		<section class="risk-overview">
			<h3>📈 리스크 요약</h3>
			<div class="metrics-grid">
				<MetricCard
					title="초과 확률"
					value={riskMetrics?.overageRisk ?? 0}
					unit="%"
					type={(riskMetrics?.overageRisk ?? 0) > 20 ? 'algorithm-exceeded' : (riskMetrics?.overageRisk ?? 0) > 10 ? 'confidence' : 'sessions'}
					tooltip="계약전력을 초과할 확률입니다. 낮을수록 좋습니다."
				/>
				<MetricCard
					title="낭비 확률"
					value={riskMetrics?.wasteRisk ?? 0}
					unit="%"
					type={(riskMetrics?.wasteRisk ?? 0) > 70 ? 'algorithm-exceeded' : (riskMetrics?.wasteRisk ?? 0) > 50 ? 'confidence' : 'sessions'}
					tooltip="계약전력을 낭비할 확률입니다. 적정 수준이 좋습니다."
				/>
				<MetricCard
					title="신뢰도"
					value={riskMetrics?.confidenceLevel ?? 0}
					unit="%"
					type="confidence"
					tooltip="예측 모델의 신뢰도입니다. 높을수록 정확한 예측입니다."
				/>
			</div>

			<!-- 휴리스틱 9: 오류 인식 및 복구 - 명확한 권고사항 -->
			{#if riskMetrics}
				<div class="recommendation-banner" class:high={riskMetrics.overageRisk > 20 || riskMetrics.wasteRisk > 70}>
					<span class="icon">💡</span>
					<span class="text">{riskMetrics.recommendation}</span>
				</div>
			{/if}
		</section>

		<!-- 휴리스틱 4: 일관성과 표준 - 표준적인 탭 UI -->
		<section class="scenario-selector">
			<h3>🎯 시나리오 선택</h3>
			<div class="tab-buttons">
				<button
					class="tab-button"
					class:active={selectedScenario === 'optimal'}
					on:click={() => selectedScenario = 'optimal'}
				>
					✅ 최적 계약
				</button>
				{#if currentContractKw}
					<button
						class="tab-button"
						class:active={selectedScenario === 'current'}
						on:click={() => selectedScenario = 'current'}
					>
						📌 현재 계약
					</button>
				{/if}
				<button
					class="tab-button"
					class:active={selectedScenario === 'custom'}
					on:click={() => selectedScenario = 'custom'}
				>
					⚙️ 사용자 지정
				</button>
			</div>
		</section>

		<!-- 휴리스틱 3 & 5: 사용자 제어 및 오류 예방 -->
		{#if selectedScenario === 'custom'}
			<section class="custom-input-section">
				<div class="input-group">
					<label for="custom-contract">
						계약전력 입력 ({CONTRACT_STEP}kW 단위)
					</label>
					<div class="input-wrapper">
						<input
							id="custom-contract"
							type="number"
							step={CONTRACT_STEP}
							min={CONTRACT_STEP}
							max="1000"
							placeholder="예: 80"
							value={customContractKw ?? ''}
							on:input={handleCustomInputChange}
							class:error={errorMessage}
						/>
						<span class="unit">kW</span>

						<!-- 휴리스틱 3: 취소 버튼 -->
						{#if customContractKw}
							<button class="reset-button" on:click={resetCustomValue} title="초기화">
								✕
							</button>
						{/if}
					</div>

					<!-- 휴리스틱 9: 오류 메시지 -->
					{#if errorMessage}
						<div class="error-message">
							<span class="error-icon">⚠️</span>
							{errorMessage}
						</div>
					{/if}
				</div>

				<!-- 휴리스틱 7: 빠른 선택 버튼 -->
				<div class="quick-select">
					<span class="quick-label">빠른 선택:</span>
					{#if recommendation}
						{@const optimal = recommendation.recommended_contract_kw}
						<button class="quick-button" on:click={() => quickSelectContract(optimal - 10)}>
							{optimal - 10}kW
						</button>
						<button class="quick-button primary" on:click={() => quickSelectContract(optimal)}>
							{optimal}kW (최적)
						</button>
						<button class="quick-button" on:click={() => quickSelectContract(optimal + 10)}>
							{optimal + 10}kW
						</button>
					{/if}
				</div>
			</section>
		{/if}

		<!-- 휴리스틱 2 & 4: 실제 세계와의 일치 & 일관성 -->
		<section class="comparison-toggle">
			<label class="toggle-label">
				<input
					type="radio"
					name="comparison"
					value="monthly"
					checked={comparisonMode === 'monthly'}
					on:change={() => comparisonMode = 'monthly'}
				/>
				월간 비용
			</label>
			<label class="toggle-label">
				<input
					type="radio"
					name="comparison"
					value="annual"
					checked={comparisonMode === 'annual'}
					on:change={() => comparisonMode = 'annual'}
				/>
				연간 비용
			</label>
		</section>

		<!-- 휴리스틱 8: 미니멀하고 미적인 디자인 - 핵심 정보만 표시 -->
		<section class="cost-breakdown">
			<h3>💰 비용 분석 (과소 ← 최적안 → 과다)</h3>

			{#each simulationResults as simulation}
				{@const primaryRiskType = getPrimaryRiskType(simulation)}
				{@const secondaryRiskType = getSecondaryRiskType(simulation)}
				{@const primaryRiskCost = getRiskTypeCost(primaryRiskType, simulation)}
				{@const secondaryRiskCost = getRiskTypeCost(secondaryRiskType, simulation)}
				{@const primaryRiskProbability = getRiskTypeProbability(primaryRiskType, simulation)}
				{@const secondaryRiskProbability = getRiskTypeProbability(secondaryRiskType, simulation)}
				{@const optimalDelta = simulation.totalExpectedCost - optimalTotalExpectedCost}
				<div
					class="cost-card"
					class:optimal={simulation.isOptimal}
					class:under={simulation.scenario === 'under'}
					class:over={simulation.scenario === 'over'}
					class:active={simulation.scenario === selectedScenario}
				>
					<div class="card-header">
						<div>
							<h4>{getScenarioLabel(simulation.scenario)}</h4>
							<div class="scenario-focus">{getDirectionFocusText(simulation)}</div>
						</div>
						<div class="contract-value">{simulation.contractKw}kW</div>
					</div>

					<div class="cost-items">
						<div class="cost-item">
							<span class="label">기본요금</span>
							<span class="value">{formatCurrency(simulation.basicCost)}원</span>
						</div>

						<div class="cost-item risk primary-risk">
							<span class="label">
								주요 리스크 비용: {getRiskTypeLabel(primaryRiskType)}
								<span class="probability">({formatPercent(primaryRiskProbability)}%)</span>
							</span>
							<span class="value" class:danger={primaryRiskType === 'overage'} class:warning={primaryRiskType === 'waste'}>
								{formatRiskCost(primaryRiskCost)}
							</span>
						</div>

						<div class="cost-item risk secondary-risk">
							<span class="label">
								보조 리스크 비용: {getRiskTypeLabel(secondaryRiskType)}
								<span class="probability">({formatPercent(secondaryRiskProbability)}%)</span>
							</span>
							<span class="value" class:danger={secondaryRiskType === 'overage'} class:warning={secondaryRiskType === 'waste'}>
								{formatRiskCost(secondaryRiskCost)}
							</span>
						</div>

						<div class="cost-divider"></div>

						<div class="cost-item total">
							<span class="label">총 예상비용</span>
							<span class="value">{formatCurrency(simulation.totalExpectedCost)}원</span>
						</div>

						<div class="cost-item optimal-diff" class:better={optimalDelta < 0} class:worse={optimalDelta > 0}>
							<span class="label">최적안 대비</span>
							<span class="value">{formatOptimalDelta(optimalDelta)}</span>
						</div>
					</div>

					<div class="risk-indicator">
						<span class="risk-label">위험도:</span>
						<span class="risk-badge" style="background-color: {getRiskColor(simulation.riskLevel)}">
							{getRiskLabel(simulation.riskLevel)}
						</span>
					</div>

					{#if simulation.isOptimal}
						<div class="optimal-badge">✨ 추천</div>
					{/if}
				</div>
			{/each}
		</section>

		<!-- 휴리스틱 7: 고급 옵션 토글 -->
		<section class="advanced-section">
			<button class="toggle-advanced" on:click={() => showAdvancedOptions = !showAdvancedOptions}>
				{showAdvancedOptions ? '▼' : '▶'} 고급 분석 옵션
			</button>

			{#if showAdvancedOptions}
				<div class="advanced-content">
					<h4>📊 상세 확률 분포 (과소 → 최적안 → 과다)</h4>
					{#if monthlyMinCandidate && selectedCandidate}
						{@const monthlyMinKw = Number(monthlyMinCandidate.contract_kw ?? 0)}
						{@const selectedKw = Number(selectedCandidate.contract_kw ?? 0)}
						{@const monthlyMinCost = getCandidateAnnualCost(monthlyMinCandidate)}
						{@const selectedAnnualCost = getCandidateAnnualCost(selectedCandidate)}
						{@const minAnnualCost = Math.min(...sortedCandidates.map(getCandidateAnnualCost))}
						{@const monthlyMinScore = getCandidateSelectionScore(monthlyMinCandidate, minAnnualCost)}
						{@const selectedScore = getCandidateSelectionScore(selectedCandidate, minAnnualCost)}
						<div class="selection-explanation" class:warning={monthlyMinKw !== selectedKw}>
							<p>
								최적안 선정 기준은 <strong>종합점수 최소</strong>입니다.
								(종합점수 = 비용정규화 + 리스크점수)
							</p>
							{#if monthlyMinKw !== selectedKw}
						<p>
							월 예상 비용 최소안은 <strong>{monthlyMinKw}kW</strong>
							({formatCurrency(monthlyMinCost, 'monthly')}원/월,
							종합점수 {monthlyMinScore.toFixed(3)})이고,
							현재 최적안은 <strong>{selectedKw}kW</strong>
							({formatCurrency(selectedAnnualCost, 'monthly')}원/월,
							종합점수 {selectedScore.toFixed(3)})이므로
							리스크를 포함한 종합 기준에서 최적안이 선택되었습니다.
						</p>
							{:else}
						<p>
							현재 최적안은 월 예상 비용 최소안과 동일하며,
							리스크를 포함한 종합점수도 가장 낮습니다.
						</p>
							{/if}
						</div>
					{/if}
					<div class="probability-details">
						{#if sortedCandidates.length > 0}
							<table class="analysis-table">
								<thead>
									<tr>
										<th>시나리오</th>
										<th>계약전력</th>
										<th>초과확률</th>
										<th>낭비확률</th>
										<th>리스크점수</th>
										<th>예상비용</th>
										<th>최적안 선정 기준</th>
									</tr>
								</thead>
								<tbody>
									{#each sortedCandidates as candidate}
										{@const contractKw = Number(candidate.contract_kw ?? 0)}
										{@const overageProb = Number(candidate.overage_probability ?? 0)}
										{@const wasteProb = Number(candidate.waste_probability ?? 0)}
										{@const riskScore = Number(candidate.risk_score ?? 0)}
										{@const annualCost = Number(candidate.annual_cost ?? 0)}
										{@const optimalKw = recommendation?.recommended_contract_kw ?? 0}
										{@const scenarioType = contractKw < optimalKw ? '⚠️ 과소' : contractKw > optimalKw ? '📊 과다' : '✅ 최적'}
										<tr class:highlight={contractKw === optimalKw}>
											<td>{scenarioType}</td>
											<td>{contractKw}kW</td>
											<td>{formatPercent(overageProb)}%</td>
											<td>{formatPercent(wasteProb)}%</td>
											<td>{riskScore.toFixed(2)}</td>
											<td>{formatCurrency(annualCost, 'annual')}원</td>
											<td class="selection-criterion">{getSelectionCriterionText(candidate, sortedCandidates, optimalKw)}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						{/if}
					</div>
				</div>
			{/if}
		</section>

		<!-- 휴리스틱 10: 도움말과 문서화 -->
		<section class="help-section">
			<details>
				<summary>❓ 용어 설명</summary>
				<dl class="terminology">
					<dt>초과 확률</dt>
					<dd>실제 사용 전력이 계약전력을 초과할 확률입니다. 초과 시 기본요금의 1.5배가 추가로 부과됩니다.</dd>

					<dt>낭비 확률</dt>
					<dd>계약전력보다 실제 사용량이 낮을 확률입니다. 과도하게 높으면 기본요금을 낭비하는 것입니다.</dd>

					<dt>리스크 점수</dt>
					<dd>초과 위험과 낭비를 종합한 지표입니다. 낮을수록 좋습니다.</dd>

					<dt>예상 초과요금</dt>
					<dd>초과 확률을 반영한 추가 비용 예상치입니다.</dd>

					<dt>예상 낭비비용</dt>
					<dd>낭비 확률을 반영한 불필요한 기본요금입니다.</dd>
				</dl>
			</details>
		</section>
	{:else if loading}
		<!-- 로딩 상태 -->
		<div class="loading-state">
			<div class="spinner"></div>
			<p>데이터를 분석하고 있습니다...</p>
		</div>
	{:else}
		<!-- 빈 상태 -->
		<div class="empty-state">
			<div class="empty-icon">📭</div>
			<p>분석할 데이터가 없습니다</p>
			<p class="empty-hint">충전소를 선택하고 예측을 실행해주세요</p>
		</div>
	{/if}
</div>

<style>
	.analysis-container {
		background: var(--bg-secondary, #ffffff);
		border-radius: 16px;
		padding: 32px;
		box-shadow: 0 4px 12px var(--shadow, rgba(0, 0, 0, 0.1));
		color: var(--text-primary, #111827);
		max-width: 1200px;
		margin: 0 auto;
	}

	.analysis-header {
		margin-bottom: 32px;
		border-bottom: 2px solid var(--border-color, #e5e7eb);
		padding-bottom: 16px;
	}

	.analysis-header h2 {
		margin: 0 0 8px 0;
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary, #111827);
	}

	.status-message {
		margin: 8px 0;
		font-size: 0.95rem;
		color: var(--text-secondary, #6b7280);
		font-weight: 500;
	}

	.status-message.loading {
		color: var(--primary-color, #4f46e5);
	}

	.progress-bar {
		height: 4px;
		background: var(--bg-tertiary, #f3f4f6);
		border-radius: 2px;
		overflow: hidden;
		margin-top: 12px;
	}

	.progress-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--primary-color, #4f46e5), #8b5cf6);
		transition: width 0.3s ease;
		animation: shimmer 1.5s infinite;
	}

	@keyframes shimmer {
		0% { opacity: 0.6; }
		50% { opacity: 1; }
		100% { opacity: 0.6; }
	}

	/* Risk Overview */
	.risk-overview {
		margin-bottom: 32px;
	}

	.risk-overview h3 {
		margin: 0 0 16px 0;
		font-size: 1.25rem;
		font-weight: 600;
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 16px;
		margin-bottom: 16px;
	}

	.recommendation-banner {
		background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
		border-left: 4px solid var(--primary-color, #4f46e5);
		padding: 16px 20px;
		border-radius: 8px;
		display: flex;
		align-items: center;
		gap: 12px;
		margin-top: 16px;
	}

	.recommendation-banner.high {
		background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
		border-left-color: var(--danger-color, #ef4444);
	}

	.recommendation-banner .icon {
		font-size: 1.5rem;
		flex-shrink: 0;
	}

	.recommendation-banner .text {
		font-weight: 600;
		color: var(--text-primary, #111827);
	}

	/* Scenario Selector */
	.scenario-selector {
		margin-bottom: 24px;
	}

	.scenario-selector h3 {
		margin: 0 0 16px 0;
		font-size: 1.25rem;
		font-weight: 600;
	}

	.tab-buttons {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}

	.tab-button {
		padding: 12px 24px;
		background: var(--bg-tertiary, #f3f4f6);
		border: 2px solid transparent;
		border-radius: 8px;
		font-size: 1rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
		color: var(--text-secondary, #6b7280);
	}

	.tab-button:hover {
		background: var(--bg-hover, #e5e7eb);
		transform: translateY(-2px);
	}

	.tab-button.active {
		background: var(--primary-color, #4f46e5);
		color: white;
		border-color: var(--primary-color, #4f46e5);
	}

	/* Custom Input */
	.custom-input-section {
		background: var(--bg-tertiary, #f9fafb);
		padding: 20px;
		border-radius: 12px;
		margin-bottom: 24px;
	}

	.input-group {
		margin-bottom: 16px;
	}

	.input-group label {
		display: block;
		margin-bottom: 8px;
		font-weight: 600;
		color: var(--text-primary, #111827);
	}

	.input-wrapper {
		position: relative;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.input-wrapper input {
		flex: 1;
		padding: 12px 50px 12px 16px;
		border: 2px solid var(--border-color, #d1d5db);
		border-radius: 8px;
		font-size: 1rem;
		background: white;
		color: var(--text-primary, #111827);
		transition: all 0.2s ease;
	}

	.input-wrapper input:focus {
		outline: none;
		border-color: var(--primary-color, #4f46e5);
		box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
	}

	.input-wrapper input.error {
		border-color: var(--danger-color, #ef4444);
	}

	.input-wrapper .unit {
		position: absolute;
		right: 50px;
		color: var(--text-secondary, #6b7280);
		font-weight: 500;
		pointer-events: none;
	}

	.reset-button {
		padding: 8px 12px;
		background: var(--bg-tertiary, #f3f4f6);
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 1.2rem;
		line-height: 1;
		color: var(--text-secondary, #6b7280);
		transition: all 0.2s ease;
	}

	.reset-button:hover {
		background: var(--danger-color, #ef4444);
		color: white;
	}

	.error-message {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 8px;
		padding: 8px 12px;
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 6px;
		color: #dc2626;
		font-size: 0.9rem;
		font-weight: 500;
	}

	.error-icon {
		flex-shrink: 0;
	}

	/* Quick Select */
	.quick-select {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}

	.quick-label {
		font-size: 0.9rem;
		color: var(--text-secondary, #6b7280);
		font-weight: 500;
	}

	.quick-button {
		padding: 8px 16px;
		background: white;
		border: 2px solid var(--border-color, #d1d5db);
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 500;
		transition: all 0.2s ease;
		color: var(--text-primary, #111827);
	}

	.quick-button:hover {
		border-color: var(--primary-color, #4f46e5);
		background: rgba(79, 70, 229, 0.05);
	}

	.quick-button.primary {
		background: var(--primary-color, #4f46e5);
		border-color: var(--primary-color, #4f46e5);
		color: white;
	}

	.quick-button.primary:hover {
		background: #4338ca;
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
	}

	/* Comparison Toggle */
	.comparison-toggle {
		display: flex;
		gap: 16px;
		margin-bottom: 24px;
		padding: 12px;
		background: var(--bg-tertiary, #f9fafb);
		border-radius: 8px;
	}

	.toggle-label {
		display: flex;
		align-items: center;
		gap: 8px;
		cursor: pointer;
		font-weight: 500;
		color: var(--text-secondary, #6b7280);
	}

	.toggle-label input[type="radio"] {
		width: 18px;
		height: 18px;
		cursor: pointer;
	}

	.toggle-label:has(input[type="radio"]:checked) {
		color: var(--primary-color, #4f46e5);
	}

	/* Cost Breakdown */
	.cost-breakdown {
		margin-bottom: 32px;
	}

	.cost-breakdown h3 {
		margin: 0 0 16px 0;
		font-size: 1.25rem;
		font-weight: 600;
	}

	.cost-card {
		background: white;
		border: 2px solid var(--border-color, #e5e7eb);
		border-radius: 12px;
		padding: 24px;
		margin-bottom: 16px;
		position: relative;
		transition: all 0.3s ease;
	}

	.cost-card.active {
		border-color: var(--primary-color, #4f46e5);
		box-shadow: 0 4px 20px rgba(79, 70, 229, 0.15);
	}

	.cost-card.optimal {
		border-color: var(--success-color, #10b981);
		background: linear-gradient(135deg, white 0%, rgba(16, 185, 129, 0.03) 100%);
	}

	.cost-card.under {
		border-color: var(--warning-color, #f59e0b);
		background: linear-gradient(135deg, white 0%, rgba(245, 158, 11, 0.03) 100%);
	}

	.cost-card.over {
		border-color: #9ca3af;
		background: linear-gradient(135deg, white 0%, rgba(156, 163, 175, 0.03) 100%);
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 20px;
		padding-bottom: 12px;
		border-bottom: 1px solid var(--border-color, #e5e7eb);
	}

	.card-header h4 {
		margin: 0;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text-primary, #111827);
	}

	.contract-value {
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--primary-color, #4f46e5);
	}

	.scenario-focus {
		margin-top: 6px;
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--text-secondary, #6b7280);
	}

	.cost-items {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.cost-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 8px 0;
	}

	.cost-item.risk {
		opacity: 0.9;
	}

	.cost-item.primary-risk {
		background: rgba(79, 70, 229, 0.04);
		padding: 10px 12px;
		border-radius: 8px;
	}

	.cost-item.secondary-risk {
		opacity: 0.78;
	}

	.cost-item.total {
		padding-top: 12px;
		font-size: 1.1rem;
		font-weight: 700;
	}

	.cost-item .label {
		color: var(--text-secondary, #6b7280);
		font-weight: 500;
	}

	.cost-item .probability {
		font-size: 0.85rem;
		color: var(--text-tertiary, #9ca3af);
		margin-left: 4px;
	}

	.cost-item .value {
		font-weight: 600;
		color: var(--text-primary, #111827);
	}

	.cost-item .value.danger {
		color: var(--danger-color, #ef4444);
	}

	.cost-item .value.warning {
		color: var(--warning-color, #f59e0b);
	}

	.cost-item.optimal-diff {
		margin-top: 6px;
		padding-top: 10px;
		border-top: 1px dashed var(--border-color, #e5e7eb);
	}

	.cost-item.optimal-diff .value {
		font-weight: 700;
	}

	.cost-item.optimal-diff.better .value {
		color: var(--success-color, #10b981);
	}

	.cost-item.optimal-diff.worse .value {
		color: var(--danger-color, #ef4444);
	}

	.cost-divider {
		height: 1px;
		background: var(--border-color, #e5e7eb);
		margin: 4px 0;
	}

	.risk-indicator {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 16px;
		padding-top: 16px;
		border-top: 1px solid var(--border-color, #e5e7eb);
	}

	.risk-label {
		font-size: 0.9rem;
		color: var(--text-secondary, #6b7280);
		font-weight: 500;
	}

	.risk-badge {
		padding: 4px 12px;
		border-radius: 12px;
		color: white;
		font-size: 0.85rem;
		font-weight: 600;
	}

	.optimal-badge {
		position: absolute;
		top: 16px;
		right: 16px;
		background: linear-gradient(135deg, #10b981, #059669);
		color: white;
		padding: 6px 12px;
		border-radius: 20px;
		font-size: 0.85rem;
		font-weight: 600;
		box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
	}

	/* Advanced Section */
	.advanced-section {
		margin-bottom: 24px;
	}

	.toggle-advanced {
		width: 100%;
		padding: 12px 16px;
		background: var(--bg-tertiary, #f9fafb);
		border: 1px solid var(--border-color, #e5e7eb);
		border-radius: 8px;
		cursor: pointer;
		font-size: 1rem;
		font-weight: 600;
		text-align: left;
		transition: all 0.2s ease;
		color: var(--text-primary, #111827);
	}

	.toggle-advanced:hover {
		background: var(--bg-hover, #f3f4f6);
	}

	.advanced-content {
		padding: 20px;
		background: white;
		border: 1px solid var(--border-color, #e5e7eb);
		border-top: none;
		border-radius: 0 0 8px 8px;
	}

	.advanced-content h4 {
		margin: 0 0 16px 0;
		font-size: 1.1rem;
		font-weight: 600;
	}

	.selection-explanation {
		margin-bottom: 16px;
		padding: 12px 14px;
		background: #f0f9ff;
		border: 1px solid #bae6fd;
		border-radius: 8px;
		color: #0f172a;
	}

	.selection-explanation.warning {
		background: #fffbeb;
		border-color: #fde68a;
	}

	.selection-explanation p {
		margin: 0;
		line-height: 1.5;
	}

	.selection-explanation p + p {
		margin-top: 8px;
	}

	.analysis-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}

	.analysis-table th {
		background: var(--bg-tertiary, #f9fafb);
		padding: 12px;
		text-align: left;
		font-weight: 600;
		color: var(--text-secondary, #6b7280);
		border-bottom: 2px solid var(--border-color, #e5e7eb);
	}

	.analysis-table td {
		padding: 12px;
		border-bottom: 1px solid var(--border-color, #e5e7eb);
		color: var(--text-primary, #111827);
	}

	.analysis-table td.selection-criterion {
		max-width: 420px;
		font-size: 0.85rem;
		line-height: 1.45;
		color: var(--text-secondary, #374151);
	}

	.analysis-table tr.highlight {
		background: rgba(79, 70, 229, 0.05);
		font-weight: 600;
	}

	.analysis-table tr:hover {
		background: var(--bg-hover, #f9fafb);
	}

	/* Help Section */
	.help-section {
		margin-top: 32px;
		padding-top: 24px;
		border-top: 2px solid var(--border-color, #e5e7eb);
	}

	.help-section details {
		background: var(--bg-tertiary, #f9fafb);
		padding: 16px;
		border-radius: 8px;
		cursor: pointer;
	}

	.help-section summary {
		font-weight: 600;
		font-size: 1rem;
		color: var(--text-primary, #111827);
		user-select: none;
	}

	.terminology {
		margin-top: 16px;
		display: grid;
		gap: 16px;
	}

	.terminology dt {
		font-weight: 600;
		color: var(--primary-color, #4f46e5);
		margin-bottom: 4px;
	}

	.terminology dd {
		margin: 0 0 0 16px;
		color: var(--text-secondary, #6b7280);
		line-height: 1.6;
	}

	/* Loading & Empty States */
	.loading-state,
	.empty-state {
		text-align: center;
		padding: 60px 20px;
	}

	.spinner {
		width: 50px;
		height: 50px;
		margin: 0 auto 20px;
		border: 4px solid var(--bg-tertiary, #e5e7eb);
		border-top-color: var(--primary-color, #4f46e5);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.empty-icon {
		font-size: 4rem;
		margin-bottom: 16px;
	}

	.empty-hint {
		color: var(--text-tertiary, #9ca3af);
		font-size: 0.9rem;
		margin-top: 8px;
	}

	/* Dark Mode */
	:global([data-theme="dark"]) .analysis-container {
		--bg-secondary: #1f2937;
		--bg-tertiary: #111827;
		--bg-hover: #374151;
		--border-color: #374151;
		--shadow: rgba(0, 0, 0, 0.3);
		--text-primary: #f9fafb;
		--text-secondary: #d1d5db;
		--text-tertiary: #9ca3af;
		--primary-color: #6366f1;
		--success-color: #10b981;
		--warning-color: #f59e0b;
		--danger-color: #ef4444;
	}

	:global([data-theme="dark"]) .cost-card {
		background: #1f2937;
	}

	:global([data-theme="dark"]) .cost-card.optimal {
		background: linear-gradient(135deg, #1f2937 0%, rgba(16, 185, 129, 0.08) 100%);
	}

	:global([data-theme="dark"]) .cost-card.under {
		background: linear-gradient(135deg, #1f2937 0%, rgba(245, 158, 11, 0.08) 100%);
	}

	:global([data-theme="dark"]) .cost-card.over {
		background: linear-gradient(135deg, #1f2937 0%, rgba(156, 163, 175, 0.08) 100%);
	}

	:global([data-theme="dark"]) .input-wrapper input {
		background: #111827;
		border-color: #374151;
		color: #f9fafb;
	}

	:global([data-theme="dark"]) .recommendation-banner {
		background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
	}

	:global([data-theme="dark"]) .recommendation-banner.high {
		background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%);
	}

	/* Responsive */
	@media (max-width: 768px) {
		.analysis-container {
			padding: 20px;
		}

		.metrics-grid {
			grid-template-columns: 1fr;
		}

		.tab-buttons {
			flex-direction: column;
		}

		.card-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 8px;
		}

		.analysis-table {
			font-size: 0.8rem;
		}

		.analysis-table th,
		.analysis-table td {
			padding: 8px;
		}
	}
</style>
