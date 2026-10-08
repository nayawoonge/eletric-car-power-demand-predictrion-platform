<script>
	import { onMount } from 'svelte';
	import { notifications } from '../stores/uiStore.ts';
	import AlertMessage from '../components/AlertMessage.svelte';
	import '../app.css';
	import '../styles/shared.css';
</script>


<main>
	<slot />
</main>

<!-- Global notifications -->
{#if $notifications.length > 0}
	<div class="notifications">
		{#each $notifications as notification (notification.id)}
			<AlertMessage {notification} />
		{/each}
	</div>
{/if}

<style>
	/* CSS variables are defined in app.css - avoid duplication */

	:global([data-theme="dark"]) {
		/* Dark theme alert colors only */
		--alert-info-bg: #1a237e;
		--alert-info-border: #1976d2;
		--alert-info-text: #90caf9;
		--alert-success-bg: #1b5e20;
		--alert-success-border: #388e3c;
		--alert-success-text: #a5d6a7;
		--alert-warning-bg: #e65100;
		--alert-warning-border: #ff9800;
		--alert-warning-text: #ffcc02;
		--alert-error-bg: #b71c1c;
		--alert-error-border: #d32f2f;
		--alert-error-text: #ffcdd2;
	}

	/* body styles moved to app.css */

	main {
		min-height: 100vh;
	}

	.notifications {
		position: fixed;
		top: 20px;
		right: 20px;
		z-index: 1000;
		display: flex;
		flex-direction: column;
		gap: 10px;
		max-width: 400px;
	}

	:global(.container) {
		max-width: 1200px;
		margin: 0 auto;
		padding: 20px;
	}

	:global(.btn) {
		background: var(--gradient-primary);
		color: white;
		border: none;
		padding: 12px 24px;
		border-radius: 8px;
		cursor: pointer;
		font-size: 14px;
		font-weight: 600;
		transition: all 0.3s ease;
		text-decoration: none;
		display: inline-block;
		text-align: center;
	}

	:global(.btn:hover) {
		transform: translateY(-2px);
		box-shadow: 0 5px 15px rgba(46, 86, 166, 0.4);
	}

	:global(.btn:disabled) {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}

	:global(.metric-card) {
		background: var(--bg-secondary);
		border-radius: 12px;
		padding: 24px;
		box-shadow: 0 4px 6px var(--shadow);
		border: 1px solid var(--border-color);
		text-align: center;
	}

	:global(.metric-card):hover {
		transition: transform 0.2s ease;
	}

	:global(.metric-card:hover) {
		transform: translateY(-4px);
		box-shadow: 0 8px 25px var(--shadow-hover);
	}

	:global(.metric-value) {
		font-size: 2.5em;
		font-weight: bold;
		margin: 10px 0;
	}

	:global(.metric-value.power) { color: #ff6b6b; }
	:global(.metric-value.contract) { color: #4ecdc4; }
	:global(.metric-value.capacity-efficiency) { color: #45b7d1; }
	:global(.metric-value.sessions) { color: #96ceb4; }

	:global(.chart-card) {
		background: var(--bg-secondary);
		border-radius: 12px;
		padding: 24px;
		box-shadow: 0 4px 6px var(--shadow);
		border: 1px solid var(--border-color);
		margin-bottom: 20px;
	}

	:global(.chart-container) {
		position: relative;
		height: 300px;
		margin-top: 20px;
	}

	/* Global Search Components */
	:global(.search-section) {
		background: linear-gradient(135deg, var(--neutral-light) 0%, var(--bg-secondary) 100%);
		border-radius: 20px;
		padding: 32px;
		margin-bottom: 30px;
		box-shadow: 0 8px 32px var(--shadow);
		border: 1px solid var(--border-color);
	}
	
	:global(.search-container) {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}
	
	:global(.search-box) {
		position: relative;
		display: flex;
		align-items: center;
		background: var(--bg-secondary);
		border-radius: 16px;
		box-shadow: 0 4px 20px var(--shadow);
		border: 2px solid var(--border-color);
		transition: all 0.3s ease;
	}
	
	:global(.search-box:focus-within) {
		border-color: var(--primary-color);
		box-shadow: 0 8px 32px rgba(46, 86, 166, 0.15);
		transform: translateY(-2px);
	}
	
	:global(.search-icon) {
		padding: 16px 20px;
		color: var(--primary-color);
		font-size: 1.2em;
		pointer-events: none;
	}
	
	:global(.search-input) {
		flex: 1;
		padding: 16px 60px 16px 0;
		border: none;
		background: transparent;
		font-size: 1.1em;
		color: var(--text-primary);
	}
	
	:global(.search-input::placeholder) {
		color: var(--text-muted);
	}
	
	:global(.search-input:focus) {
		outline: none;
	}
	
	:global(.search-loading) {
		position: absolute;
		right: 50px;
		top: 50%;
		transform: translateY(-50%);
		pointer-events: none;
	}
	
	:global(.clear-button) {
		position: absolute;
		right: 12px;
		top: 50%;
		transform: translateY(-50%);
		background: #ff6b6b;
		color: white;
		border: none;
		border-radius: 50%;
		width: 32px;
		height: 32px;
		font-size: 0.9em;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.3s ease;
		font-weight: bold;
	}
	
	:global(.clear-button:hover) {
		background: #ff5252;
		transform: translateY(-50%) scale(1.1);
	}
	
	:global(.filter-controls) {
		display: flex;
		gap: 24px;
		flex-wrap: wrap;
	}
	
	:global(.control-group) {
		display: flex;
		flex-direction: column;
		gap: 8px;
		min-width: 140px;
	}
	
	:global(.control-label) {
		font-size: 0.9em;
		font-weight: 600;
		color: var(--primary-color);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}
	
	:global(.custom-select) {
		position: relative;
	}
	
	:global(.custom-select select) {
		width: 100%;
		padding: 12px 16px;
		border: 2px solid var(--border-color);
		border-radius: 12px;
		background: var(--bg-secondary);
		color: var(--text-primary);
		font-size: 0.95em;
		cursor: pointer;
		transition: all 0.3s ease;
		appearance: none;
		background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
		background-position: right 12px center;
		background-repeat: no-repeat;
		background-size: 16px;
		padding-right: 40px;
	}
	
	:global(.custom-select select:hover) {
		border-color: var(--primary-color);
	}
	
	:global(.custom-select select:focus) {
		outline: none;
		border-color: var(--primary-color);
		box-shadow: 0 0 0 3px rgba(46, 86, 166, 0.1);
	}
	
	:global(.sort-toggle) {
		display: flex;
		background: var(--neutral-light);
		border-radius: 12px;
		padding: 4px;
		gap: 2px;
	}
	
	:global(.sort-btn) {
		flex: 1;
		padding: 10px 12px;
		border: none;
		background: transparent;
		border-radius: 8px;
		font-size: 0.85em;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.3s ease;
		color: #64748b;
		white-space: nowrap;
	}
	
	:global(.sort-btn.active) {
		background: var(--primary-color);
		color: white;
		box-shadow: 0 2px 8px rgba(46, 86, 166, 0.3);
	}
	
	:global(.sort-btn:hover:not(.active)) {
		background: #e2e8f0;
		color: #475569;
	}
	
	/* Global Upload Components */
	:global(.upload-section) {
		background: var(--bg-secondary);
		border-radius: 16px;
		padding: 24px;
		margin-bottom: 30px;
		box-shadow: 0 4px 12px var(--shadow);
		border: 2px dashed var(--border-color);
		transition: all 0.3s ease;
	}
	
	:global(.upload-section.drag-over) {
		border-color: var(--primary-color);
		background: var(--neutral-light);
	}
	
	:global(.upload-controls) {
		display: flex;
		align-items: center;
		gap: 20px;
		margin-bottom: 20px;
		flex-wrap: wrap;
	}
	
	:global(.btn-upload) {
		background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
		color: white;
		border: none;
		padding: 12px 24px;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.3s ease;
		display: flex;
		align-items: center;
		gap: 8px;
	}
	
	:global(.btn-upload:hover:not(:disabled)) {
		transform: translateY(-2px);
		box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
	}
	
	:global(.btn-upload:disabled) {
		background: #ccc;
		cursor: not-allowed;
	}
	
	:global(.progress-bar) {
		width: 100%;
		height: 4px;
		background: #e0e0e0;
		border-radius: 2px;
		overflow: hidden;
		margin-bottom: 20px;
	}
	
	:global(.progress-fill) {
		height: 100%;
		background: linear-gradient(90deg, #28a745, #20c997);
		border-radius: 2px;
		transition: width 0.3s ease;
	}
	
	:global(.drop-zone) {
		border: 2px dashed var(--border-color);
		border-radius: 12px;
		padding: 40px 20px;
		text-align: center;
		cursor: pointer;
		transition: all 0.3s ease;
		background: var(--neutral-light);
	}
	
	:global(.drop-zone:hover),
	:global(.drop-zone.active) {
		border-color: var(--primary-color);
		background: var(--neutral-light);
	}
	
	:global(.drop-content) {
		pointer-events: none;
	}
	
	:global(.drop-icon) {
		font-size: 3em;
		display: block;
		margin-bottom: 16px;
		opacity: 0.6;
	}
	
	/* Global Loading States */
	:global(.loading-container) {
		text-align: center;
		padding: 60px 20px;
	}
	
	:global(.loading-container p) {
		margin-top: 20px;
		color: var(--text-secondary);
		font-size: 1.1em;
	}
	
	:global(.empty-state) {
		text-align: center;
		padding: 60px 20px;
		background: var(--bg-secondary);
		border-radius: 12px;
		box-shadow: 0 4px 6px var(--shadow);
		border: 1px solid var(--border-color);
	}
	
	:global(.empty-state h3) {
		color: var(--text-secondary);
		margin-bottom: 10px;
	}
	
	:global(.empty-actions) {
		display: flex;
		gap: 16px;
		justify-content: center;
		flex-wrap: wrap;
		margin-top: 20px;
	}
	
	:global(.loading-more) {
		text-align: center;
		padding: 30px 20px;
		color: var(--text-secondary);
	}
	
	:global(.loading-more p) {
		margin-top: 10px;
		font-size: 0.9em;
	}
	
	:global(.end-message) {
		text-align: center;
		padding: 20px;
		color: #28a745;
		background: #f8fff9;
		border-radius: 8px;
		margin: 20px 0;
		border: 1px solid #d4edda;
	}
	
	:global(.end-message p) {
		margin: 0;
		font-weight: 500;
	}
	
	/* Global Alert Styles */
	:global(.alert) {
		padding: 16px 20px;
		border-radius: 8px;
		margin-bottom: 20px;
		border: 1px solid transparent;
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	
	:global(.alert-error) {
		background: var(--alert-error-bg);
		border-color: var(--alert-error-border);
		color: var(--alert-error-text);
	}
	
	:global(.alert strong) {
		margin-right: 8px;
	}
	
	/* Scrollbar Styles */
	:global(.scroll-container) {
		max-height: 80vh;
		overflow-y: auto;
		padding: 10px 8px 10px 0;
	}
	
	:global(.scroll-container::-webkit-scrollbar) {
		width: 8px;
	}
	
	:global(.scroll-container::-webkit-scrollbar-track) {
		background: #f1f1f1;
		border-radius: 4px;
	}
	
	:global(.scroll-container::-webkit-scrollbar-thumb) {
		background: #888;
		border-radius: 4px;
	}
	
	:global(.scroll-container::-webkit-scrollbar-thumb:hover) {
		background: #555;
	}
	
	/* Mobile responsive styles for global components */
	@media (max-width: 767px) {
		:global(.upload-section) {
			padding: 16px;
			margin-bottom: 20px;
		}
		
		:global(.upload-controls) {
			flex-direction: column;
			text-align: center;
			gap: 12px;
		}
		
		:global(.btn-upload) {
			padding: 10px 20px;
			font-size: 0.9em;
		}
		
		:global(.drop-zone) {
			padding: 24px 12px;
		}
		
		:global(.search-section) {
			padding: 20px;
			margin-bottom: 20px;
		}
		
		:global(.search-container) {
			gap: 16px;
		}
		
		:global(.filter-controls) {
			flex-direction: column;
			gap: 12px;
		}
		
		:global(.control-group) {
			min-width: unset;
		}
		
		:global(.sort-toggle) {
			flex-direction: column;
		}
		
		:global(.sort-btn) {
			padding: 10px 12px;
			text-align: center;
			font-size: 0.8em;
		}
	}
	
	/* Tablet responsive styles */
	@media (min-width: 768px) and (max-width: 1023px) {
		:global(.upload-section) {
			padding: 24px;
		}
		
		:global(.search-section) {
			padding: 24px;
		}
	}
	
	/* Desktop responsive styles */
	@media (min-width: 1024px) {
		:global(.upload-section),
		:global(.search-section) {
			padding: 32px;
		}
	}
	
	/* Large desktop responsive styles */
	@media (min-width: 1300px) {
		:global(.upload-section),
		:global(.search-section) {
			padding: 40px;
		}
	}
</style>