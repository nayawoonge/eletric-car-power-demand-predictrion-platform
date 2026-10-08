<script lang="ts">
	/**
	 * 모델 검증 UI 컴포넌트
	 *
	 * 9월까지 학습하고 10월 예측 성능을 시각화합니다.
	 * - 예측 피크 vs 실제 피크 비교
	 * - MAE, 상대 오차, 일관성 지표
	 */

	import { onMount } from 'svelte';
	import MetricCard from './MetricCard.svelte';

	export let stationId = '';

	// 검증 데이터
	let validationData: any = null;
	let loading = false;
	let error = '';

	// 차트 설정
	let chartCanvas: HTMLCanvasElement;
	let chartInstance: any = null;

	onMount(async () => {
		if (stationId) {
			await fetchValidationData();
		}
	});

	/**
	 * 모델 검증 데이터 가져오기
	 */
	async function fetchValidationData() {
		loading = true;
		error = '';

		try {
			const response = await fetch(`/api/stations/${stationId}/model-validation`);

			if (!response.ok) {
				throw new Error('검증 데이터를 가져오는데 실패했습니다');
			}

			const data = await response.json();

			if (!data.success) {
				throw new Error(data.error || '알 수 없는 오류');
			}

			validationData = data;
			console.log('✅ 모델 검증 데이터 로드 완료:', validationData);

			// 차트 렌더링
			await renderChart();
		} catch (err) {
			error = err instanceof Error ? err.message : '오류가 발생했습니다';
			console.error('❌ 검증 데이터 로드 실패:', err);
		} finally {
			loading = false;
		}
	}

	/**
	 * 예측 vs 실제 차트 렌더링
	 */
	async function renderChart() {
		if (!validationData || !chartCanvas) return;

		// Chart.js 동적 로드
		const Chart = (await import('chart.js/auto')).default;

		// 기존 차트 제거
		if (chartInstance) {
			chartInstance.destroy();
		}

		const ctx = chartCanvas.getContext('2d');
		if (!ctx) return;

		const vizData = validationData.visualization_data || [];
		const dates = vizData.map((d: any) => d.date);
		const actualPeaks = vizData.map((d: any) => d.actual_peak_kw);
		const predictedPeaks = vizData.map((d: any) => d.predicted_peak_kw);

		chartInstance = new Chart(ctx, {
			type: 'line',
			data: {
				labels: dates,
				datasets: [
					{
						label: '실제 피크 (kW)',
						data: actualPeaks,
						borderColor: '#ef4444',
						backgroundColor: 'rgba(239, 68, 68, 0.1)',
						borderWidth: 2,
						pointRadius: 4,
						pointHoverRadius: 6,
						tension: 0.1
					},
					{
						label: '예측 피크 (kW)',
						data: predictedPeaks,
						borderColor: '#3b82f6',
						backgroundColor: 'rgba(59, 130, 246, 0.1)',
						borderWidth: 2,
						pointRadius: 4,
						pointHoverRadius: 6,
						tension: 0.1,
						borderDash: [5, 5]
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					title: {
						display: true,
						text: '10월 예측 vs 실제 피크 비교',
						font: {
							size: 16,
							weight: 'bold'
						}
					},
					legend: {
						display: true,
						position: 'top'
					},
					tooltip: {
						mode: 'index',
						intersect: false,
						callbacks: {
							label: function(context: any) {
								let label = context.dataset.label || '';
								if (label) {
									label += ': ';
								}
								if (context.parsed.y !== null) {
									label += context.parsed.y.toFixed(2) + ' kW';
								}
								return label;
							}
						}
					}
				},
				scales: {
					x: {
						display: true,
						title: {
							display: true,
							text: '날짜'
						},
						ticks: {
							maxRotation: 45,
							minRotation: 45
						}
					},
					y: {
						display: true,
						title: {
							display: true,
							text: '전력 (kW)'
						},
						beginAtZero: false
					}
				},
				interaction: {
					mode: 'nearest',
					axis: 'x',
					intersect: false
				}
			}
		});
	}

	/**
	 * 일관성 레벨에 따른 색상 반환
	 */
	function getConsistencyColor(consistency: string): string {
		switch (consistency) {
			case '양호':
				return '#10b981'; // green
			case '보통':
				return '#f59e0b'; // amber
			default:
				return '#ef4444'; // red
		}
	}

	/**
	 * 일관성 레벨에 따른 아이콘 반환
	 */
	function getConsistencyIcon(consistency: string): string {
		switch (consistency) {
			case '양호':
				return '✅';
			case '보통':
				return '⚠️';
			default:
				return '❌';
		}
	}
</script>

<div class="validation-container">
	<!-- 헤더 -->
	<header class="validation-header">
		<h2>📊 모델 성능 검증</h2>
		<p class="subtitle">9월까지 학습 → 10월 예측 성능 평가</p>
		<button class="refresh-button" on:click={fetchValidationData} disabled={loading}>
			{loading ? '⏳ 분석 중...' : '🔄 새로고침'}
		</button>
	</header>

	<!-- 로딩 상태 -->
	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>모델 검증을 수행하고 있습니다...</p>
		</div>
	{/if}

	<!-- 에러 상태 -->
	{#if error}
		<div class="error-banner">
			<span class="error-icon">⚠️</span>
			<span class="error-text">{error}</span>
			<button class="error-close" on:click={() => (error = '')}>✕</button>
		</div>
	{/if}

	<!-- 검증 결과 -->
	{#if validationData && !loading}
		<div class="validation-content">
			<!-- 검증 지표 요약 -->
			<section class="metrics-section">
				<h3>🎯 검증 지표</h3>
				<div class="metrics-grid">
					<MetricCard
						title="MAE"
						value={validationData.validation_metrics.mae}
						unit="kW"
						type="confidence"
						tooltip="평균 절대 오차. 예측과 실제의 평균 차이입니다."
					/>
					<MetricCard
						title="비교 일수"
						value={validationData.validation_metrics.comparison_days}
						unit="일"
						type="sessions"
						tooltip="예측과 실제를 비교한 날짜 수입니다."
					/>
					<MetricCard
						title="상대 오차"
						value={validationData.validation_metrics.relative_error_percent}
						unit="%"
						type={validationData.validation_metrics.relative_error_percent < 5 ? 'sessions' : 'confidence'}
						tooltip="실제 평균 대비 오차 비율입니다."
					/>
				</div>

				<!-- 일관성 평가 -->
				<div class="consistency-card" style="border-color: {getConsistencyColor(validationData.validation_metrics.consistency)}">
					<div class="consistency-header">
						<span class="consistency-icon">{getConsistencyIcon(validationData.validation_metrics.consistency)}</span>
						<h4>현재 {validationData.validation_metrics.consistency}</h4>
					</div>
					<div class="consistency-details">
						<div class="detail-item">
							<span class="label">MAE</span>
							<span class="value">{validationData.validation_metrics.mae}kW</span>
						</div>
						<div class="detail-item">
							<span class="label">비교</span>
							<span class="value">{validationData.validation_metrics.comparison_days}일</span>
						</div>
						<div class="detail-item">
							<span class="label">상대 오차</span>
							<span class="value">{validationData.validation_metrics.relative_error_percent}%</span>
						</div>
					</div>
					<p class="consistency-description">
						예측 곡선이 실측 추세와 {validationData.validation_metrics.consistency === '양호' ? '충분히 일치하여 안정적으로 일반화되고 있습니다' : validationData.validation_metrics.consistency === '보통' ? '대체로 일치하고 있습니다' : '개선이 필요합니다'}.
					</p>
				</div>
			</section>

			<!-- 차트 섹션 -->
			<section class="chart-section">
				<h3>📈 예측 vs 실제 비교</h3>
				<div class="chart-container">
					<canvas bind:this={chartCanvas}></canvas>
				</div>
			</section>

			<!-- 학습/테스트 정보 -->
			<section class="info-section">
				<details>
					<summary>ℹ️ 데이터 분할 정보</summary>
					<div class="info-content">
						<div class="info-row">
							<span class="info-label">학습 종료일:</span>
							<span class="info-value">{validationData.data_split.train_end_date}</span>
						</div>
						<div class="info-row">
							<span class="info-label">테스트 시작일:</span>
							<span class="info-value">{validationData.data_split.test_start_date}</span>
						</div>
						<div class="info-row">
							<span class="info-label">테스트 종료일:</span>
							<span class="info-value">{validationData.data_split.test_end_date}</span>
						</div>
						<div class="info-row">
							<span class="info-label">학습 세션 수:</span>
							<span class="info-value">{validationData.data_split.train_sessions.toLocaleString()}개</span>
						</div>
						<div class="info-row">
							<span class="info-label">테스트 세션 수:</span>
							<span class="info-value">{validationData.data_split.test_sessions.toLocaleString()}개</span>
						</div>
					</div>
				</details>

				<details>
					<summary>🤖 모델 예측 정보</summary>
					<div class="info-content">
						<div class="info-row">
							<span class="info-label">예측 피크:</span>
							<span class="info-value">{validationData.prediction_info.predicted_peak_kw}kW</span>
						</div>
						<div class="info-row">
							<span class="info-label">불확실성:</span>
							<span class="info-value">±{validationData.prediction_info.uncertainty_kw}kW</span>
						</div>
						<div class="info-row">
							<span class="info-label">신뢰도:</span>
							<span class="info-value">{(validationData.prediction_info.confidence_level * 100).toFixed(1)}%</span>
						</div>
						<div class="info-row">
							<span class="info-label">LSTM 가중치:</span>
							<span class="info-value">{(validationData.prediction_info.model_weights.lstm * 100).toFixed(1)}%</span>
						</div>
						<div class="info-row">
							<span class="info-label">XGBoost 가중치:</span>
							<span class="info-value">{(validationData.prediction_info.model_weights.xgboost * 100).toFixed(1)}%</span>
						</div>
					</div>
				</details>
			</section>
		</div>
	{/if}
</div>

<style>
	.validation-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 24px;
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
	}

	.validation-header {
		text-align: center;
		margin-bottom: 32px;
		padding-bottom: 20px;
		border-bottom: 2px solid #e5e7eb;
		position: relative;
	}

	.validation-header h2 {
		margin: 0 0 8px 0;
		font-size: 1.75rem;
		color: #111827;
	}

	.subtitle {
		margin: 0 0 16px 0;
		color: #6b7280;
		font-size: 1rem;
	}

	.refresh-button {
		padding: 10px 20px;
		background: #4f46e5;
		color: white;
		border: none;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.refresh-button:hover:not(:disabled) {
		background: #4338ca;
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
	}

	.refresh-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* 로딩 */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 60px 20px;
		color: #6b7280;
	}

	.spinner {
		width: 48px;
		height: 48px;
		border: 4px solid #e5e7eb;
		border-top-color: #4f46e5;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: 16px;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* 에러 */
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

	/* 검증 콘텐츠 */
	.validation-content {
		display: flex;
		flex-direction: column;
		gap: 32px;
	}

	/* 지표 섹션 */
	.metrics-section h3 {
		margin: 0 0 20px 0;
		font-size: 1.25rem;
		color: #111827;
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 16px;
		margin-bottom: 24px;
	}

	/* 일관성 카드 */
	.consistency-card {
		background: white;
		border: 3px solid;
		border-radius: 12px;
		padding: 24px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
	}

	.consistency-header {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 20px;
	}

	.consistency-icon {
		font-size: 2rem;
	}

	.consistency-header h4 {
		margin: 0;
		font-size: 1.5rem;
		color: #111827;
	}

	.consistency-details {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 16px;
		margin-bottom: 16px;
		padding: 16px;
		background: #f9fafb;
		border-radius: 8px;
	}

	.detail-item {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.detail-item .label {
		font-size: 0.85rem;
		color: #6b7280;
		font-weight: 500;
	}

	.detail-item .value {
		font-size: 1.25rem;
		font-weight: 700;
		color: #111827;
	}

	.consistency-description {
		margin: 0;
		color: #374151;
		line-height: 1.6;
	}

	/* 차트 섹션 */
	.chart-section h3 {
		margin: 0 0 20px 0;
		font-size: 1.25rem;
		color: #111827;
	}

	.chart-container {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 24px;
		height: 400px;
	}

	/* 정보 섹션 */
	.info-section {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.info-section details {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		padding: 16px;
		cursor: pointer;
	}

	.info-section summary {
		font-weight: 600;
		color: #111827;
		user-select: none;
		list-style: none;
	}

	.info-section summary::-webkit-details-marker {
		display: none;
	}

	.info-section summary::before {
		content: '▶';
		display: inline-block;
		margin-right: 8px;
		transition: transform 0.2s ease;
	}

	.info-section details[open] summary::before {
		transform: rotate(90deg);
	}

	.info-content {
		margin-top: 16px;
		padding-top: 16px;
		border-top: 1px solid #e5e7eb;
	}

	.info-row {
		display: flex;
		justify-content: space-between;
		padding: 8px 0;
		border-bottom: 1px solid #f3f4f6;
	}

	.info-row:last-child {
		border-bottom: none;
	}

	.info-label {
		color: #6b7280;
		font-weight: 500;
	}

	.info-value {
		color: #111827;
		font-weight: 600;
	}

	/* 다크모드 */
	:global([data-theme='dark']) .validation-container {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .validation-header h2 {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .consistency-card {
		background: #1f2937;
	}

	:global([data-theme='dark']) .consistency-header h4 {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .consistency-details {
		background: #111827;
	}

	:global([data-theme='dark']) .detail-item .value {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .chart-container {
		background: #1f2937;
		border-color: #374151;
	}

	:global([data-theme='dark']) .info-section details {
		background: #1f2937;
		border-color: #374151;
	}

	:global([data-theme='dark']) .info-section summary {
		color: #f9fafb;
	}

	:global([data-theme='dark']) .info-value {
		color: #f9fafb;
	}

	/* 반응형 */
	@media (max-width: 768px) {
		.consistency-details {
			grid-template-columns: 1fr;
		}

		.chart-container {
			height: 300px;
		}
	}
</style>
