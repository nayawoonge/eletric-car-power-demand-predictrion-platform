<script>
	import { onMount, onDestroy } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	
	Chart.register(...registerables);
	
	export let avgPower = 0;
	
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
	
	$: if (chart && avgPower !== undefined) {
		updateChart();
	}
	
	function initChart() {
		const ctx = canvas.getContext('2d');
		
		chart = new Chart(ctx, {
			type: 'doughnut',
			data: {
				labels: [
					'낮은 전력 (0-30kW)',
					'중간 전력 (30-60kW)',
					'높은 전력 (60-100kW)'
				],
				datasets: [{
					data: [30, 50, 20],
					backgroundColor: [
						'rgba(150, 206, 180, 0.8)',
						'rgba(69, 183, 209, 0.8)',
						'rgba(255, 107, 107, 0.8)'
					],
					borderColor: ['#96ceb4', '#45b7d1', '#ff6b6b'],
					borderWidth: 3,
					hoverOffset: 15,
				}]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '60%',
				plugins: {
					legend: {
						display: true,
						position: 'bottom',
						labels: {
							padding: 20,
							usePointStyle: true,
							font: { size: 11 },
							color: '#666'
						}
					},
					tooltip: {
						backgroundColor: 'rgba(0,0,0,0.8)',
						titleColor: '#fff',
						bodyColor: '#fff',
						callbacks: {
							label: function(context) {
								const total = context.dataset.data.reduce((a, b) => a + b, 0);
								const percentage = ((context.parsed / total) * 100).toFixed(1);
								return `${context.label}: ${percentage}%`;
							}
						}
					}
				},
				animation: {
					duration: 1000,
					easing: 'easeOutQuart'
				}
			}
		});
	}
	
	function calculateDistribution(avgPower) {
		let lowPower, mediumPower, highPower;
		
		if (avgPower <= 30) {
			lowPower = 70;
			mediumPower = 25;
			highPower = 5;
		} else if (avgPower <= 60) {
			lowPower = 30;
			mediumPower = 50;
			highPower = 20;
		} else {
			lowPower = 15;
			mediumPower = 35;
			highPower = 50;
		}
		
		return [lowPower, mediumPower, highPower];
	}
	
	function updateChart() {
		if (!chart) return;
		
		const distribution = calculateDistribution(Number(avgPower) || 0);
		chart.data.datasets[0].data = distribution;
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