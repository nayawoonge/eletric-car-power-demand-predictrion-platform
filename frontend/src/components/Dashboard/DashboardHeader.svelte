<script>
	import { createEventDispatcher } from 'svelte';
	import ThemeToggle from '../ThemeToggle.svelte';
	
	const dispatch = createEventDispatcher();
	
	export let error = null;
	
	function clearError() {
		dispatch('clearError');
	}
</script>

<div class="header">
	<div class="header-content">
		<div class="header-text">
			<h1>블루네트웍스 충전소 전력 예측 시스템</h1>
		</div>
		<div class="header-actions">
			<ThemeToggle />
		</div>
	</div>
</div>

{#if error}
	<div class="alert alert-error">
		<strong>오류</strong> {error}
		<button class="btn" on:click={clearError}>
			닫기
		</button>
	</div>
{/if}

<style>
	.header {
		margin-bottom: 40px;
		padding: 40px 20px;
		background: var(--gradient-primary);
		color: white;
		border-radius: 16px;
		box-shadow: 0 8px 32px var(--shadow);
	}
	
	.header-content {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 20px;
	}
	
	.header-text {
		text-align: left;
	}
	
	.header h1 {
		margin: 0 0 10px 0;
		font-size: 2.5em;
		font-weight: 700;
	}
	
	.header-actions {
		display: flex;
		gap: 12px;
	}
	
	.alert {
		padding: 16px;
		margin-bottom: 20px;
		border-radius: 8px;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	
	.alert-error {
		background: #fee2e2;
		color: #dc2626;
		border: 1px solid #fecaca;
	}
	
	.btn {
		padding: 8px 16px;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		background: #dc2626;
		color: white;
		font-weight: 500;
	}
	
	@media (max-width: 767px) {
		.header-actions {
			flex-direction: column;
			gap: 8px;
			align-items: flex-end;
		}
	}
</style>