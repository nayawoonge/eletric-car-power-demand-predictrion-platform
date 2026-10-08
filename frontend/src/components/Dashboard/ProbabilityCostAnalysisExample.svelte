<script lang="ts">
	/**
	 * 확률 및 비용 산정 모듈 사용 예시
	 *
	 * 이 파일은 ProbabilityCostAnalysis 컴포넌트를 통합하는 방법을 보여줍니다.
	 */

	import { onMount } from 'svelte';
	import ProbabilityCostAnalysis from './ProbabilityCostAnalysis.svelte';
	import type { ContractRecommendation } from '../../lib/types';

	// API에서 가져온 추천 데이터
	let recommendation: ContractRecommendation | null = null;
	let currentContractKw: number | null = null;
	let loading = false;
	let error = '';

	// 충전소 선택
	let selectedStationId = 'station_001';

	onMount(() => {
		// 페이지 로드 시 데이터 가져오기
		fetchRecommendation();
	});

	/**
	 * API에서 계약 추천 데이터 가져오기
	 */
	async function fetchRecommendation() {
		loading = true;
		error = '';

		try {
			// 앙상블 예측 API 호출
			const response = await fetch(
				`/api/stations/${selectedStationId}/ensemble-prediction?current_contract_kw=${currentContractKw ?? 100}`
			);

			if (!response.ok) {
				throw new Error('데이터를 가져오는데 실패했습니다');
			}

			const data = await response.json();

			if (!data.success) {
				throw new Error(data.error || '알 수 없는 오류');
			}

			// 추천 데이터 설정
			recommendation = data.contract_recommendation;

			console.log('✅ 추천 데이터 로드 완료:', recommendation);
		} catch (err) {
			error = err instanceof Error ? err.message : '오류가 발생했습니다';
			console.error('❌ 데이터 로드 실패:', err);
		} finally {
			loading = false;
		}
	}

	/**
	 * 충전소 변경 시 데이터 다시 가져오기
	 */
	function handleStationChange(event: Event) {
		const select = event.target as HTMLSelectElement;
		selectedStationId = select.value;
		fetchRecommendation();
	}

	/**
	 * 현재 계약 변경 시 데이터 다시 가져오기
	 */
	function handleContractChange(event: Event) {
		const input = event.target as HTMLInputElement;
		const value = parseInt(input.value);
		currentContractKw = isNaN(value) ? null : value;

		// 디바운스 적용 (입력 후 500ms 대기)
		clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			fetchRecommendation();
		}, 500);
	}

	let debounceTimer: number;

	// Mock 데이터 (개발/테스트용)
	function loadMockData() {
		recommendation = {
			station_id: 'station_001',
			analysis_date: new Date().toISOString(),
			recommended_contract_kw: 80,
			current_contract_kw: 100,
			expected_annual_cost: 7987200,
			expected_annual_savings: 1996800,
			savings_percent: 20.0,
			predicted_peak_p50: 72.5,
			predicted_peak_p95: 78.3,
			overage_probability: 5.2,
			waste_probability: 35.8,
			confidence_level: 0.85,
			recommendation_summary: '계약전력을 80kW로 조정하면 연간 약 200만원 절감 가능',
			detailed_reasoning: [
				'📊 1,000개 예측 시나리오 분석 완료 (신뢰도: 85%)',
				'⚡ 예측 피크: 평균 72.5kW, 표준편차 ±5.2kW',
				'✅ 최적 계약 80kW 선정: 연간 비용 7,987,200원',
				'🟢 초과 위험 매우 낮음 (5.2%)',
				'💰 예상 절감: 연간 1,996,800원 (월 166,400원)',
				'🎯 10kW 단위 미세 조정으로 비용 최적화 달성'
			],
			action_required: true,
			urgency_level: 'medium',
			cost_comparison_data: {},
			candidate_analysis_data: [
				{
					contract_kw: 60,
					expected_annual_cost: 8324000,
					overage_probability: 25.3,
					waste_probability: 8.2,
					risk_score: 2.8
				},
				{
					contract_kw: 70,
					expected_annual_cost: 7954200,
					overage_probability: 12.1,
					waste_probability: 18.5,
					risk_score: 1.5
				},
				{
					contract_kw: 80,
					expected_annual_cost: 7987200,
					overage_probability: 5.2,
					waste_probability: 35.8,
					risk_score: 1.2
				},
				{
					contract_kw: 90,
					expected_annual_cost: 8245600,
					overage_probability: 2.1,
					waste_probability: 52.3,
					risk_score: 1.8
				},
				{
					contract_kw: 100,
					expected_annual_cost: 8984000,
					overage_probability: 0.8,
					waste_probability: 68.5,
					risk_score: 2.5
				}
			],
			recommendation: '계약전력을 80kW로 조정 권장'
		};
		loading = false;
	}
</script>

<div class="example-container">
	<header class="example-header">
		<h1>📊 확률 및 비용 산정 모듈 예시</h1>
		<p class="subtitle">전기 계약전력 최적화 시뮬레이션</p>
	</header>

	<!-- 컨트롤 패널 -->
	<section class="control-panel">
		<div class="control-group">
			<label for="station-select">충전소 선택</label>
			<select id="station-select" value={selectedStationId} on:change={handleStationChange}>
				<option value="station_001">Station 001 - 서울 강남점</option>
				<option value="station_002">Station 002 - 부산 해운대점</option>
				<option value="station_003">Station 003 - 대전 유성점</option>
			</select>
		</div>

		<div class="control-group">
			<label for="current-contract">현재 계약전력 (선택사항)</label>
			<input
				id="current-contract"
				type="number"
				step="10"
				placeholder="예: 100"
				value={currentContractKw ?? ''}
				on:input={handleContractChange}
			/>
			<span class="unit">kW</span>
		</div>

		<div class="button-group">
			<button class="btn btn-primary" on:click={fetchRecommendation} disabled={loading}>
				{loading ? '분석 중...' : '🔄 데이터 새로고침'}
			</button>
			<button class="btn btn-secondary" on:click={loadMockData}>
				🧪 Mock 데이터 로드
			</button>
		</div>
	</section>

	<!-- 에러 표시 -->
	{#if error}
		<div class="error-banner">
			<span class="error-icon">⚠️</span>
			<span class="error-text">{error}</span>
			<button class="error-close" on:click={() => (error = '')}>✕</button>
		</div>
	{/if}

	<!-- 확률 및 비용 산정 모듈 -->
	<section class="analysis-section">
		<ProbabilityCostAnalysis {recommendation} {currentContractKw} {loading} />
	</section>

	<!-- 통합 가이드 -->
	<section class="integration-guide">
		<details>
			<summary>💡 통합 가이드</summary>
			<div class="guide-content">
				<h3>1. 컴포넌트 임포트</h3>
				<pre><code>import ProbabilityCostAnalysis from './ProbabilityCostAnalysis.svelte';
import type &#123; ContractRecommendation &#125; from '../../lib/types';</code></pre>

				<h3>2. 데이터 준비</h3>
				<pre><code>let recommendation: ContractRecommendation | null = null;
let currentContractKw: number | null = 100;
let loading = false;</code></pre>

				<h3>3. API 호출</h3>
				<pre><code>const response = await fetch(
  `/api/stations/$&#123;stationId&#125;/ensemble-prediction?current_contract_kw=$&#123;currentContractKw&#125;`
);
const data = await response.json();
recommendation = data.contract_recommendation;</code></pre>

				<h3>4. 컴포넌트 사용</h3>
				<pre><code>&lt;ProbabilityCostAnalysis
  &#123;recommendation&#125;
  &#123;currentContractKw&#125;
  &#123;loading&#125;
/&gt;</code></pre>
			</div>
		</details>
	</section>
</div>

<style>
	.example-container {
		max-width: 1400px;
		margin: 0 auto;
		padding: 20px;
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
	}

	.example-header {
		text-align: center;
		margin-bottom: 40px;
		padding-bottom: 20px;
		border-bottom: 2px solid #e5e7eb;
	}

	.example-header h1 {
		margin: 0 0 10px 0;
		font-size: 2rem;
		color: #111827;
	}

	.subtitle {
		margin: 0;
		color: #6b7280;
		font-size: 1.1rem;
	}

	/* Control Panel */
	.control-panel {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 24px;
		margin-bottom: 24px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
	}

	.control-group {
		margin-bottom: 20px;
		position: relative;
	}

	.control-group label {
		display: block;
		margin-bottom: 8px;
		font-weight: 600;
		color: #374151;
	}

	.control-group select,
	.control-group input {
		width: 100%;
		padding: 12px 16px;
		border: 2px solid #d1d5db;
		border-radius: 8px;
		font-size: 1rem;
		background: white;
		color: #111827;
		transition: all 0.2s ease;
	}

	.control-group select:focus,
	.control-group input:focus {
		outline: none;
		border-color: #4f46e5;
		box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
	}

	.control-group .unit {
		position: absolute;
		right: 16px;
		bottom: 12px;
		color: #6b7280;
		font-weight: 500;
		pointer-events: none;
	}

	.button-group {
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}

	.btn {
		padding: 12px 24px;
		border: none;
		border-radius: 8px;
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s ease;
		flex: 1;
		min-width: 200px;
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-primary {
		background: #4f46e5;
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: #4338ca;
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
	}

	.btn-secondary {
		background: #f3f4f6;
		color: #374151;
		border: 2px solid #d1d5db;
	}

	.btn-secondary:hover:not(:disabled) {
		background: #e5e7eb;
		border-color: #9ca3af;
	}

	/* Error Banner */
	.error-banner {
		display: flex;
		align-items: center;
		gap: 12px;
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 8px;
		padding: 16px 20px;
		margin-bottom: 24px;
		color: #dc2626;
	}

	.error-icon {
		font-size: 1.25rem;
		flex-shrink: 0;
	}

	.error-text {
		flex: 1;
		font-weight: 500;
	}

	.error-close {
		background: none;
		border: none;
		font-size: 1.25rem;
		cursor: pointer;
		color: #dc2626;
		padding: 0;
		width: 24px;
		height: 24px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 4px;
		transition: background 0.2s ease;
	}

	.error-close:hover {
		background: rgba(220, 38, 38, 0.1);
	}

	/* Analysis Section */
	.analysis-section {
		margin-bottom: 40px;
	}

	/* Integration Guide */
	.integration-guide {
		background: #f9fafb;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 20px;
	}

	.integration-guide details {
		cursor: pointer;
	}

	.integration-guide summary {
		font-weight: 700;
		font-size: 1.1rem;
		color: #111827;
		user-select: none;
		padding: 8px;
	}

	.integration-guide summary:hover {
		color: #4f46e5;
	}

	.guide-content {
		padding: 20px 8px;
	}

	.guide-content h3 {
		margin: 24px 0 12px 0;
		font-size: 1rem;
		color: #374151;
	}

	.guide-content h3:first-child {
		margin-top: 0;
	}

	.guide-content pre {
		background: #1f2937;
		border-radius: 8px;
		padding: 16px;
		overflow-x: auto;
		margin: 8px 0;
	}

	.guide-content code {
		color: #e5e7eb;
		font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
		font-size: 0.9rem;
		line-height: 1.6;
	}

	/* Dark Mode */
	:global([data-theme='dark']) .example-container {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .example-header h1 {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .control-panel {
		background: #1f2937;
		border-color: #374151;
	}

	:global([data-theme='dark']) .control-group label {
		color: #d1d5db;
	}

	:global([data-theme='dark']) .control-group select,
	:global([data-theme='dark']) .control-group input {
		background: #111827;
		border-color: #374151;
		color: #f9fafb;
	}

	:global([data-theme='dark']) .btn-secondary {
		background: #374151;
		color: #d1d5db;
		border-color: #4b5563;
	}

	:global([data-theme='dark']) .integration-guide {
		background: #1f2937;
		border-color: #374151;
	}

	:global([data-theme='dark']) .integration-guide summary {
		color: #f9fafb;
	}

	/* Responsive */
	@media (max-width: 768px) {
		.button-group {
			flex-direction: column;
		}

		.btn {
			min-width: 100%;
		}

		.example-header h1 {
			font-size: 1.5rem;
		}
	}
</style>
