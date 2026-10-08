<script>
	import { createEventDispatcher } from 'svelte';
	
	const dispatch = createEventDispatcher();
	
	export let station;
	
	function selectStation() {
		dispatch('select', station);
	}
	
	function handleKeydown(event) {
		if (event.key === 'Enter') {
			selectStation();
		}
	}
</script>

<div class="station-card">
	<div class="station-identity">
		<h3 class="station-name" title={station.name}>{station.name}</h3>
		<div class="station-id">{station.id}</div>
		<div class="station-location" title={station.location}>
			<svg class="location-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
				<circle cx="12" cy="10" r="3"/>
			</svg>
			<div class="location-info">
				{#if station.region || station.city}
					<span class="location-region">{station.region} {station.city}</span>
				{/if}
				<span class="location-address">{station.location}</span>
			</div>
		</div>
	</div>
	
	<div class="station-specs">
		<div class="spec-item">
			<svg class="spec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
			</svg>
			<span>{station.charger_type}</span>
		</div>
		<div class="spec-item">
			<svg class="spec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<circle cx="12" cy="12" r="3"/>
				<path d="M12 1v6m0 6v6m11-7h-6m-6 0H1"/>
			</svg>
			<span>{station.connector_type}</span>
		</div>
	</div>
	
	<div class="station-metrics">
		<div class="metric-grid">
			<div class="metric-item primary">
				<div class="metric-value">{station.data_sessions || 0}</div>
				<div class="metric-label">충전 세션</div>
			</div>
			<div class="metric-item secondary">
				<div class="metric-value capacity-efficiency" title="평균 사용량 / 정격 용량 × 100%">
					{station.capacity_efficiency || 'N/A'}
				</div>
				<div class="metric-label">용량 효율성</div>
			</div>
		</div>
	</div>
	
	{#if station.last_activity}
		<div class="station-activity">
			<svg class="activity-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<circle cx="12" cy="12" r="10"/>
				<polyline points="12,6 12,12 16,14"/>
			</svg>
			<span class="activity-text">마지막 활동: {station.last_activity}</span>
		</div>
	{/if}
	
	<div class="card-footer" on:click={selectStation} role="button" tabindex="0" on:keydown={handleKeydown}>
		<div class="view-details">
			<span>상세 정보 보기</span>
			<svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
				<path d="M9 18l6-6-6-6"/>
			</svg>
		</div>
	</div>
</div>

<style>
	.station-card {
		background: var(--bg-secondary);
		border-radius: 20px;
		padding: 0;
		box-shadow: 0 4px 20px var(--shadow);
		transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
		border: 1px solid var(--border-color);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		position: relative;
	}
	
	.station-card::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 4px;
		background: var(--gradient-primary);
		transform: scaleX(0);
		transition: transform 0.3s ease;
	}
	
	.station-card:hover {
		transform: translateY(-8px);
		box-shadow: 0 20px 40px var(--shadow-hover);
		border-color: var(--primary-color);
	}
	
	.station-card:hover::before {
		transform: scaleX(1);
	}
	
	.station-identity {
		padding: 24px 24px 0 24px;
		margin-bottom: 20px;
	}
	
	.station-name {
		margin: 0 0 6px 0;
		font-size: 1.4em;
		font-weight: 700;
		color: var(--primary-color);
		line-height: 1.3;
		height: 2.6em;
		overflow: hidden;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
	}
	
	.station-id {
		margin: 0 0 12px 0;
		font-size: 0.85em;
		font-weight: 600;
		color: var(--text-muted);
		background: var(--neutral-light);
		padding: 4px 8px;
		border-radius: 6px;
		display: inline-block;
		letter-spacing: 0.5px;
		font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
	}
	
	.station-location {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		color: var(--text-secondary);
		font-size: 0.9em;
		line-height: 1.3;
	}
	
	.location-icon {
		width: 16px;
		height: 16px;
		stroke-width: 2;
		color: #ef4444;
		flex-shrink: 0;
		margin-top: 2px;
	}
	
	.location-info {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	
	.location-region {
		font-weight: 600;
		color: var(--primary-color);
		font-size: 0.85em;
		opacity: 0.8;
	}
	
	.location-address {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.85em;
		color: var(--text-muted);
	}
	
	.station-specs {
		padding: 0 24px;
		margin-bottom: 20px;
	}
	
	.spec-item {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 0;
		font-size: 0.9em;
		color: var(--text-secondary);
	}
	
	.spec-icon {
		width: 18px;
		height: 18px;
		stroke-width: 2;
		color: var(--primary-color);
	}
	
	.station-metrics {
		padding: 0 24px;
		margin-bottom: 20px;
	}
	
	.metric-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
	}
	
	.metric-item {
		background: var(--neutral-light);
		border-radius: 12px;
		padding: 16px;
		text-align: center;
		transition: all 0.3s ease;
		border: 2px solid transparent;
	}
	
	.metric-item.primary {
		background: var(--gradient-primary);
		color: white;
	}
	
	.metric-item.secondary {
		background: linear-gradient(135deg, var(--neutral-light) 0%, var(--bg-tertiary) 100%);
		color: var(--text-primary);
	}
	
	.metric-item:hover {
		transform: translateY(-2px);
		border-color: var(--border-color);
	}
	
	.metric-value {
		font-size: 1.5em;
		font-weight: 700;
		line-height: 1;
		margin-bottom: 4px;
	}
	
	.metric-item.primary .metric-value {
		color: white;
	}
	
	.metric-item.secondary .metric-value {
		color: var(--primary-color);
	}
	
	.metric-label {
		font-size: 0.8em;
		font-weight: 500;
		opacity: 0.8;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}
	
	.metric-item.primary .metric-label {
		color: rgba(255, 255, 255, 0.9);
	}
	
	.metric-item.secondary .metric-label {
		color: var(--text-secondary);
	}
	
	.station-activity {
		padding: 0 24px;
		margin-bottom: 20px;
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--text-muted);
		font-size: 0.85em;
	}
	
	.activity-icon {
		width: 14px;
		height: 14px;
		stroke-width: 2;
	}
	
	.card-footer {
		padding: 20px 24px 24px 24px;
		margin-top: auto;
		border-top: 1px solid var(--border-color);
		background: var(--neutral-light);
		transition: all 0.3s ease;
		cursor: pointer;
		outline: none;
	}
	
	.card-footer:hover {
		background: var(--primary-color);
		border-top-color: var(--primary-color);
		transform: translateY(-2px);
	}
	
	.card-footer:active {
		transform: translateY(0);
	}
	
	.view-details {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		font-size: 1.1em;
		font-weight: 600;
		color: var(--primary-color);
		transition: all 0.3s ease;
	}
	
	.card-footer:hover .view-details {
		color: white;
		transform: translateX(4px);
	}
	
	.arrow-icon {
		width: 16px;
		height: 16px;
		stroke-width: 2;
		transition: transform 0.3s ease;
	}
	
	.card-footer:hover .arrow-icon {
		transform: translateX(4px);
	}
</style>