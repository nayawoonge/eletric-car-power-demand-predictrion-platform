import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Theme type
export type Theme = 'light' | 'dark' | 'auto';

// Default to 'auto' which respects system preference
const defaultTheme: Theme = 'auto';

// Create theme store
function createThemeStore() {
	const { subscribe, set, update } = writable<Theme>(defaultTheme);

	return {
		subscribe,
		setTheme: (theme: Theme) => {
			set(theme);
			if (browser) {
				localStorage.setItem('theme', theme);
				applyTheme(theme);
			}
		},
		toggleTheme: () => {
			update(current => {
				const newTheme = current === 'light' ? 'dark' : 'light';
				if (browser) {
					localStorage.setItem('theme', newTheme);
					applyTheme(newTheme);
				}
				return newTheme;
			});
		},
		init: () => {
			if (browser) {
				const stored = localStorage.getItem('theme') as Theme;
				const theme = stored || defaultTheme;
				set(theme);
				applyTheme(theme);
			}
		}
	};
}

function applyTheme(theme: Theme) {
	if (!browser) return;

	const root = document.documentElement;

	// Determine target theme
	const targetTheme = theme === 'auto'
		? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
		: theme;

	// Immediate update - let browser optimize
	root.setAttribute('data-theme', targetTheme);
}

export const theme = createThemeStore();

// Listen for system theme changes when in auto mode
if (browser) {
	const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
	let currentTheme: Theme = 'auto';

	// Subscribe once and store the unsubscribe function
	const unsubscribe = theme.subscribe(value => {
		currentTheme = value;
	});

	// Use addEventListener instead of deprecated addListener
	mediaQuery.addEventListener('change', (e) => {
		if (currentTheme === 'auto') {
			applyTheme('auto');
		}
	});
}