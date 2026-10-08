<script>
	import { onMount, onDestroy } from 'svelte';
	import { getChartModules } from '../../lib/chart-utils.js';
	
	let Chart;
	let chartInstance = null;
	
	export let data = [];
	
	let canvas;
	let chart;
	
	export function resetZoom() {
		if (typeof window !== 'undefined' && chart) {
			chart.resetZoom();
		}
	}
	
	onMount(async () => {
		// 브라우저 환경에서만 실행
		if (typeof window === 'undefined') return;
		
		try {
			const modules = await getChartModules();
			if (modules) {
				Chart = modules.Chart;
				// 차트 초기화
				initChart();
			}
		} catch (error) {
			console.error('Chart.js 로드 실패:', error);
		}
	});
	
	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});
	
	$: if (typeof window !== 'undefined' && chart && data) {
		updateChart();
	}
	
	function initChart() {
		// 브라우저 환경 체크
		if (typeof window === 'undefined' || !Chart || !canvas) return;
		
		const ctx = canvas.getContext('2d');
		
		chart = new Chart(ctx, {
			type: 'bar',
			data: {
				labels: [
					'1월', '2월', '3월', '4월', '5월', '6월',
					'7월', '8월', '9월', '10월', '11월', '12월'
				],
				datasets: [{
					label: '예상 최고전력 (kW)',
					data: data || new Array(12).fill(0),
					backgroundColor: 'rgba(78, 205, 196, 0.8)',
					borderColor: '#4ecdc4',
					borderWidth: 2,
					borderRadius: 8,
					borderSkipped: false,
				}]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						display: false
					},
					tooltip: {
						backgroundColor: 'rgba(0,0,0,0.8)',
						titleColor: '#fff',
						bodyColor: '#fff',
						borderColor: '#4ecdc4',
						borderWidth: 1,
						callbacks: {
							label: function(context) {
								return `${context.label}: ${context.parsed.y.toFixed(1)}kW`;
							}
						}
					},
					zoom: {
						limits: {
							x: {min: 'original', max: 'original'},
							y: {min: 'original', max: 'original'}
						},
						pan: {
							enabled: true,
							mode: 'xy'
						},
						zoom: {
							wheel: {
								enabled: true,
								speed: 0.1
							},
							pinch: {
								enabled: true
							},
							mode: 'xy'
						}
					}
				},
				scales: {
					y: {
						beginAtZero: true,
						max: 100,
						title: {
							display: true,
							text: '전력 (kW)',
							color: '#666',
							font: { size: 12, weight: 'bold' }
						},
						grid: {
							color: 'rgba(0,0,0,0.1)',
							drawBorder: false,
						},
						ticks: {
							color: '#666',
							callback: function(value) {
								return value + 'kW';
							}
						}
					},
					x: {
						grid: { display: false },
						ticks: { color: '#666' }
					}
				},
				animation: {
					duration: 1000,
					easing: 'easeOutQuart'
				}
			}
		});
	}
	
	function updateChart() {
		if (!chart) return;
		
		const chartData = Array.isArray(data) && data.length === 12 ? 
			data.map(val => Number(val) || 0) : 
			new Array(12).fill(0);
			
		chart.data.datasets[0].data = chartData;
		chart.update('active');
	}
</script>

<div class="chart-wrapper">
	<div class="chart-header">
		<h4>월별 전력 사용량</h4>
		<button class="zoom-reset-btn" on:click={resetZoom} title="줌 초기화">
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
				<polyline points="9,22 9,12 15,12 15,22"/>
			</svg>
			리셋
		</button>
	</div>
	<div class="chart-container">
		<canvas bind:this={canvas}></canvas>
	</div>
</div>

<style>
	.chart-wrapper {
		background: var(--bg-secondary);
		border: 1px solid var(--border-color);
		border-radius: 12px;
		padding: 16px;
	}

	.chart-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 16px;
		padding-bottom: 8px;
		border-bottom: 1px solid var(--border-color);
	}

	.chart-header h4 {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.zoom-reset-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 6px 10px;
		background: var(--primary-color);
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.zoom-reset-btn:hover {
		background: var(--primary-dark);
		transform: translateY(-1px);
	}

	.zoom-reset-btn svg {
		width: 14px;
		height: 14px;
	}

	.chart-container {
		position: relative;
		height: 300px;
	}
</style>