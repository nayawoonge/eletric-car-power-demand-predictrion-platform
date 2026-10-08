<script>
	import { uiActions } from '../stores/uiStore.ts';
	
	export let notification;
	
	const icons = {
		info: 'ℹ️',
		success: '✅',
		warning: '⚠️',
		error: '❌'
	};
	
	function close() {
		uiActions.removeNotification(notification.id);
	}
	
	function handleKeydown(event) {
		if (event.key === 'Escape') {
			close();
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="alert alert-{notification.type}" role="alert">
	<span class="icon">{icons[notification.type] || icons.info}</span>
	<span class="message">{notification.message}</span>
	<button class="close-btn" on:click={close} aria-label="Close notification">
		×
	</button>
</div>

<style>
	.alert {
		display: flex;
		align-items: center;
		padding: 12px 16px;
		border-radius: 8px;
		margin-bottom: 8px;
		position: relative;
		animation: slideInRight 0.3s ease-out;
		box-shadow: 0 2px 8px var(--shadow);
		max-width: 400px;
		word-wrap: break-word;
		transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;
	}
	
	.alert-info {
		background-color: var(--alert-info-bg, #e3f2fd);
		border-left: 4px solid var(--alert-info-border, #2196f3);
		color: var(--alert-info-text, #1565c0);
	}
	
	.alert-success {
		background-color: var(--alert-success-bg, #e8f5e8);
		border-left: 4px solid var(--alert-success-border, #4caf50);
		color: var(--alert-success-text, #2e7d32);
	}
	
	.alert-warning {
		background-color: var(--alert-warning-bg, #fff3e0);
		border-left: 4px solid var(--alert-warning-border, #ff9800);
		color: var(--alert-warning-text, #ef6c00);
	}
	
	.alert-error {
		background-color: var(--alert-error-bg, #ffebee);
		border-left: 4px solid var(--alert-error-border, #f44336);
		color: var(--alert-error-text, #c62828);
	}
	
	.icon {
		margin-right: 8px;
		flex-shrink: 0;
	}
	
	.message {
		flex: 1;
		font-size: 14px;
		line-height: 1.4;
	}
	
	.close-btn {
		background: none;
		border: none;
		font-size: 18px;
		cursor: pointer;
		padding: 0;
		margin-left: 12px;
		opacity: 0.7;
		transition: opacity 0.2s ease;
		flex-shrink: 0;
		width: 20px;
		height: 20px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: inherit;
	}
	
	.close-btn:hover {
		opacity: 1;
	}
	
	@keyframes slideInRight {
		from {
			opacity: 0;
			transform: translateX(100%);
		}
		to {
			opacity: 1;
			transform: translateX(0);
		}
	}
</style>