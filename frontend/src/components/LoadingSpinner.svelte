<script>
	export let size = 'normal'; // 'small', 'normal', 'large'
	export let color = null; // null이면 CSS 변수 사용
</script>

<div class="spinner {size}" class:custom-color={color} style={color ? `border-top-color: ${color}` : ''}>
</div>

<style>
	.spinner {
		border: 2px solid var(--spinner-bg, rgba(0, 0, 0, 0.1));
		border-radius: 50%;
		border-top: 2px solid var(--spinner-color, #667eea);
		animation: spin 1s linear infinite;
		display: inline-block;
		transition: border-color 0.3s ease;
	}
	
	/* 커스텀 색상이 지정된 경우 CSS 변수 무시 */
	.spinner.custom-color {
		border: 2px solid rgba(0, 0, 0, 0.1);
	}
	
	.spinner.small {
		width: 16px;
		height: 16px;
		border-width: 2px;
	}
	
	.spinner.normal {
		width: 24px;
		height: 24px;
		border-width: 2px;
	}
	
	.spinner.large {
		width: 48px;
		height: 48px;
		border-width: 3px;
	}
	
	/* 다크모드 스타일 */
	:global([data-theme="dark"]) .spinner {
		--spinner-bg: rgba(255, 255, 255, 0.1);
		--spinner-color: #a78bfa;
	}
	
	/* 라이트모드 스타일 */
	:global([data-theme="light"]) .spinner {
		--spinner-bg: rgba(0, 0, 0, 0.1);
		--spinner-color: #6366f1;
	}
	
	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}
</style>