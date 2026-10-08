<script>
	import { onMount, onDestroy } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	
	Chart.register(...registerables);
	
	export let data = [];
	
	let canvas;
	let chart;
	
	onMount(() => {
		initChart();
	});
	
	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});
	
	$: if (chart && data) {
		updateChart();
	}
	
	function initChart() {
		const ctx = canvas.getContext('2d');
		
		chart = new Chart(ctx, {
			type: 'line',
			data: {
				labels: Array.from({ length: 24 }, (_, i) => `${i}시`),
				datasets: [{
					label: '평균 전력 (kW)',
					data: data || new Array(24).fill(0),
					borderColor: '#ff6b6b',
					backgroundColor: 'rgba(255, 107, 107, 0.1)',
					borderWidth: 3,
					tension: 0.4,
					fill: true,
					pointBackgroundColor: '#ff6b6b',
					pointBorderColor: '#ffffff',
					pointBorderWidth: 2,
					pointRadius: 5,
					pointHoverRadius: 8,
				}]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: {
					intersect: false,
					mode: 'index',
				},
				plugins: {
					legend: {
						display: false
					},
					tooltip: {
						backgroundColor: 'rgba(0,0,0,0.8)',
						titleColor: '#fff',
						bodyColor: '#fff',
						borderColor: '#ff6b6b',
						borderWidth: 1,
						callbacks: {
							label: function(context) {
								return `${context.parsed.x}시: ${context.parsed.y.toFixed(1)}kW`;
							}
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
						grid: {
							color: 'rgba(0,0,0,0.05)',
							drawBorder: false,
						},
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
		
		const chartData = Array.isArray(data) && data.length === 24 ? 
			data.map(val => Number(val) || 0) : 
			new Array(24).fill(0);
			
		chart.data.datasets[0].data = chartData;
		chart.update('active');
	}
</script>

<div class="chart-container">
	<canvas bind:this={canvas}></canvas>
</div>

<style>
	.chart-container {
		position: relative;
		height: 300px;
		margin-top: 20px;
	}
</style>