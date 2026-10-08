<script>
	import { createEventDispatcher } from 'svelte';
	import { tweened } from 'svelte/motion';
	import { cubicOut } from 'svelte/easing';
	import LoadingSpinner from '../LoadingSpinner.svelte';
	
	const dispatch = createEventDispatcher();
	
	export let filteredStations = [];
	export let pagination = { total: 0 };
	export let isLoading = false;
	
	const stationCount = tweened(0, { duration: 500, easing: cubicOut });
	
	$: totalSessions = (filteredStations || []).reduce((sum, s) => sum + (s?.data_sessions || 0), 0);
	$: stationCount.set((filteredStations || []).length);
	
	function refreshStations() {
		dispatch('refresh');
	}
</script>

<div class="dashboard-overview">
	<div class="overview-header">
		<h1 class="section-title">충전소 개요</h1>
		<button class="refresh-btn" on:click={refreshStations} disabled={isLoading}>
			{#if isLoading}
				<LoadingSpinner size="small" />
			{:else}
				<svg class="refresh-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
					<path d="M23 4v6h-6"/>
					<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
				</svg>
			{/if}
			<span>새로고침</span>
		</button>
	</div>
	
	<div class="stats-grid">
		<div class="stat-card featured">
			<div class="stat-header">
				<div class="stat-icon-wrapper primary">
					<svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
						<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
					</svg>
				</div>
				<div class="stat-badge">실시간</div>
			</div>
			<div class="stat-content">
				<div class="stat-value">{$stationCount}</div>
				<div class="stat-label">총 충전소</div>
			</div>
			<div class="stat-footer">
				<div class="stat-trend positive">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
						<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
						<polyline points="17 6 23 6 23 12"/>
					</svg>
					<span>활성</span>
				</div>
			</div>
		</div>

		<div class="stat-card">
			<div class="stat-header">
				<div class="stat-icon-wrapper secondary">
					<svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
						<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
						<line x1="9" y1="9" x2="9" y2="15"/>
						<line x1="15" y1="9" x2="15" y2="15"/>
					</svg>
				</div>
				<div class="stat-metric">세션</div>
			</div>
			<div class="stat-content">
				<div class="stat-value">{(totalSessions || 0).toLocaleString()}</div>
				<div class="stat-label">총 충전 세션</div>
			</div>
			<div class="stat-footer">
				<div class="stat-detail">
					<span>누적 데이터</span>
				</div>
			</div>
		</div>

		<div class="stat-card">
			<div class="stat-header">
				<div class="stat-icon-wrapper tertiary">
					<svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
						<circle cx="12" cy="12" r="3"/>
						<path d="M12 1v6m0 6v6m11-7h-6m-6 0H1"/>
					</svg>
				</div>
				<div class="stat-metric">전체</div>
			</div>
			<div class="stat-content">
				<div class="stat-value">{pagination?.total ?? filteredStations.length}</div>
				<div class="stat-label">등록된 개소</div>
			</div>
			<div class="stat-footer">
				<div class="stat-detail">
					<span>시스템 등록</span>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	.dashboard-overview {
		background: linear-gradient(135deg, var(--neutral-light) 0%, var(--bg-secondary) 100%);
		border-radius: 24px;
		padding: 32px;
		margin-bottom: 40px;
		border: 1px solid var(--border-color);
		box-shadow: 0 10px 40px var(--shadow);
		transition: background 0.3s ease, border-color 0.3s ease;
	}
	
	.overview-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 28px;
		flex-wrap: wrap;
		gap: 20px;
	}
	
	.section-title {
		margin: 0;
		font-size: 1.5em;
		font-weight: 700;
		color: var(--primary-color);
		display: flex;
		align-items: center;
		gap: 12px;
	}
	
	.refresh-btn {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 20px;
		background: var(--gradient-primary);
		color: white;
		border: none;
		border-radius: 14px;
		font-weight: 600;
		font-size: 0.95em;
		cursor: pointer;
		transition: all 0.3s ease;
		box-shadow: 0 4px 15px var(--shadow);
	}
	
	.refresh-btn:hover:not(:disabled) {
		transform: translateY(-2px);
		box-shadow: 0 8px 25px var(--shadow-hover);
	}
	
	.refresh-btn:disabled {
		background: var(--text-muted);
		cursor: not-allowed;
		transform: none;
		box-shadow: 0 2px 8px var(--shadow);
	}
	
	.refresh-icon {
		width: 18px;
		height: 18px;
		stroke-width: 2;
	}
	
	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 24px;
	}
	
	.stat-card {
		background: var(--bg-secondary);
		border-radius: 20px;
		padding: 28px;
		border: 1px solid var(--border-color);
		transition: all 0.3s ease;
		position: relative;
		overflow: hidden;
	}
	
	.stat-card::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 4px;
		background: var(--gradient-primary);
		opacity: 0;
		transition: opacity 0.3s ease;
	}
	
	.stat-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 15px 35px var(--shadow-hover);
		border-color: var(--primary-color);
	}
	
	.stat-card:hover::before {
		opacity: 1;
	}
	
	.stat-card.featured {
		background: var(--gradient-primary);
		color: white;
		border: none;
		box-shadow: 0 10px 30px rgba(46, 86, 166, 0.3);
	}
	
	.stat-card.featured::before {
		background: rgba(255, 255, 255, 0.2);
	}
	
	.stat-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 20px;
	}
	
	.stat-icon-wrapper {
		width: 48px;
		height: 48px;
		border-radius: 14px;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.3s ease;
	}
	
	.stat-icon-wrapper.primary {
		background: rgba(255, 255, 255, 0.2);
	}
	
	.stat-icon-wrapper.secondary {
		background: linear-gradient(135deg, var(--primary-light) 0%, var(--primary-color) 100%);
		color: white;
	}
	
	.stat-icon-wrapper.tertiary {
		background: linear-gradient(135deg, var(--primary-medium) 0%, var(--primary-soft) 100%);
		color: white;
	}
	
	.stat-icon {
		width: 24px;
		height: 24px;
		stroke-width: 2;
	}
	
	.stat-badge {
		background: rgba(255, 255, 255, 0.2);
		padding: 6px 12px;
		border-radius: 20px;
		font-size: 0.75em;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}
	
	.stat-metric {
		background: var(--neutral-light);
		padding: 6px 12px;
		border-radius: 20px;
		font-size: 0.75em;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--text-muted);
		transition: background-color 0.3s ease, color 0.3s ease;
	}
	
	.stat-content {
		margin-bottom: 20px;
	}
	
	.stat-value {
		font-size: 2.5em;
		font-weight: 800;
		line-height: 1;
		margin-bottom: 8px;
		letter-spacing: -0.025em;
	}
	
	.stat-card.featured .stat-value {
		color: white;
	}
	
	.stat-label {
		font-size: 0.95em;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: capitalize;
	}
	
	.stat-card.featured .stat-label {
		color: rgba(255, 255, 255, 0.9);
	}
	
	.stat-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	
	.stat-trend {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.85em;
		font-weight: 500;
	}
	
	.stat-trend svg {
		width: 16px;
		height: 16px;
		stroke-width: 2;
	}
	
	.stat-trend.positive {
		color: rgba(255, 255, 255, 0.9);
	}
	
	.stat-detail {
		font-size: 0.85em;
		color: var(--text-muted);
		font-weight: 500;
	}
</style>