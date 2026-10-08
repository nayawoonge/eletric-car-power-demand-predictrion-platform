export function initKeyboardShortcuts() {
	function handleKeyboard(event) {
		// Ctrl + Left Arrow - Go back
		if (event.ctrlKey && event.key === 'ArrowLeft') {
			event.preventDefault();
			window.history.back();
		}
		
		// Ctrl + R - Refresh dashboard
		if (event.ctrlKey && event.key === 'r') {
			event.preventDefault();
			window.location.reload();
		}
		
		// Escape - Go back to station list
		if (event.key === 'Escape') {
			event.preventDefault();
			window.location.href = '/';
		}
		
		// Ctrl + E - Export data (if export button exists)
		if (event.ctrlKey && event.key === 'e') {
			event.preventDefault();
			const exportBtn = document.querySelector('[title="데이터 내보내기"]');
			if (exportBtn) exportBtn.click();
		}
	}
	
	document.addEventListener('keydown', handleKeyboard);
	
	// Return cleanup function
	return () => {
		document.removeEventListener('keydown', handleKeyboard);
	};
}