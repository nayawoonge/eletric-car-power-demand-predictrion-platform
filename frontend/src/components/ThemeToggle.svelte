<script>
	import { theme } from '../stores/themeStore.ts';
	import { onMount } from 'svelte';

	let currentTheme;
	
	onMount(() => {
		theme.init();
	});

	$: currentTheme = $theme;

	function handleThemeChange() {
		// Performance measurement
		const startTime = performance.now();
		performance.mark('theme-change-start');

		if (currentTheme === 'light') {
			theme.setTheme('dark');
		} else if (currentTheme === 'dark') {
			theme.setTheme('auto');
		} else {
			theme.setTheme('light');
		}

		// Measure after next paint
		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				const endTime = performance.now();
				performance.mark('theme-change-end');
				performance.measure('theme-change', 'theme-change-start', 'theme-change-end');

				const duration = endTime - startTime;
				console.log(`🎨 테마 전환 시간: ${duration.toFixed(2)}ms`);

				// Get paint timing
				const paintEntries = performance.getEntriesByType('paint');
				console.log('🖌️ Paint 이벤트:', paintEntries);

				// Get measure
				const measures = performance.getEntriesByName('theme-change');
				if (measures.length > 0) {
					console.log('📊 성능 측정:', measures[0]);
				}
			});
		});
	}

	function getThemeIcon(themeValue) {
		switch (themeValue) {
			case 'light':
				return '☀️';
			case 'dark':
				return '🌙';
			case 'auto':
			default:
				return '🌗';
		}
	}

	function getThemeLabel(themeValue) {
		switch (themeValue) {
			case 'light':
				return '라이트 모드';
			case 'dark':
				return '다크 모드';
			case 'auto':
			default:
				return '자동 모드';
		}
	}
</script>

<button 
	class="theme-toggle" 
	on:click={handleThemeChange}
	title={getThemeLabel(currentTheme)}
	aria-label={getThemeLabel(currentTheme)}
>
	<span class="theme-icon">{getThemeIcon(currentTheme)}</span>
	<span class="theme-label">{getThemeLabel(currentTheme)}</span>
</button>

<style>
	.theme-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 16px;
		background: rgba(255, 255, 255, 0.1);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 20px;
		color: white;
		cursor: pointer;
		font-size: 0.9em;
		font-weight: 500;
	}

	.theme-toggle:hover {
		background: rgba(255, 255, 255, 0.2);
		transform: translateY(-1px);
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		transition: background 0.15s ease-out,
		            transform 0.15s ease-out,
		            box-shadow 0.15s ease-out;
	}

	.theme-toggle:active {
		transform: translateY(0);
		transition: transform 0.05s ease-out;
	}

	.theme-icon {
		font-size: 1.1em;
	}

	.theme-label {
		white-space: nowrap;
	}

	/* Dark theme styles */
	:global([data-theme="dark"]) .theme-toggle {
		background: rgba(255, 255, 255, 0.1);
		border-color: rgba(255, 255, 255, 0.2);
		color: #f1f5f9;
	}

	:global([data-theme="dark"]) .theme-toggle:hover {
		background: rgba(255, 255, 255, 0.2);
	}

	@media (max-width: 768px) {
		.theme-label {
			display: none;
		}
		
		.theme-toggle {
			padding: 8px 12px;
		}
	}
</style>