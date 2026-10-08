<script>
	import { createEventDispatcher } from 'svelte';
	import LoadingSpinner from '../LoadingSpinner.svelte';
	
	const dispatch = createEventDispatcher();
	
	export let searchQuery = '';
	export let sortBy = 'id';
	export let sortOrder = 'asc';
	export let isLoading = false;
	
	function clearSearch() {
		searchQuery = '';
		dispatch('searchChange', '');
	}
	
	function handleSearchInput(event) {
		dispatch('searchChange', event.target.value);
	}
	
	function handleSortByChange(event) {
		dispatch('sortChange', { sortBy: event.target.value, sortOrder });
	}
	
	function handleSortOrderChange(newOrder) {
		dispatch('sortChange', { sortBy, sortOrder: newOrder });
	}
</script>

<div class="search-section">
	<div class="search-container">
		<div class="search-box">
			<div class="search-icon">🔍</div>
			<input
				type="text"
				class="search-input"
				placeholder="충전소 ID, 이름, 위치로 검색"
				bind:value={searchQuery}
				on:input={handleSearchInput}
			/>
			{#if isLoading}
				<div class="search-loading">
					<LoadingSpinner size="small" />
				</div>
			{/if}
			{#if searchQuery}
				<button class="clear-button" on:click={clearSearch} title="검색어 지우기">
					✕
				</button>
			{/if}
		</div>
		
		<div class="filter-controls modern">
			<div class="control-group">
				<label class="control-label" for="sort-by-select">정렬 기준</label>
				<div class="select-wrapper">
					<svg class="select-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
						<path d="M8 9l4-4 4 4" />
						<path d="M16 15l-4 4-4-4" />
					</svg>
					<select
						id="sort-by-select"
						class="select"
						bind:value={sortBy}
						on:change={handleSortByChange}
						aria-label="정렬 기준 선택"
					>
						<option value="id">ID</option>
						<option value="name">이름</option>
						<option value="location">위치</option>
						<option value="region">권역</option>
						<option value="city">시군구</option>
						<option value="sessions">세션수</option>
						<option value="avg_power">평균 전력</option>
						<option value="max_power">최대 전력</option>
						<option value="capacity_efficiency">용량 효율성</option>
						<option value="charger_type">충전기 타입</option>
						<option value="last_activity">마지막 활동</option>
					</select>
				</div>
			</div>

			<div class="control-group">
				<div class="sort-control segmented">
					<span class="control-label">정렬</span>
					<div class="sort-toggle-switch" role="group" aria-label="정렬 방향">
						<button
							type="button"
							class="toggle-option"
							class:active={sortOrder === 'asc'}
							aria-pressed={sortOrder === 'asc'}
							on:click={() => handleSortOrderChange('asc')}
							title="오름차순 정렬"
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
								<polygon points="12 6, 6 18, 18 18"></polygon>
							</svg>
							<span>오름차순 (A-Z)</span>
						</button>
						<button
							type="button"
							class="toggle-option"
							class:active={sortOrder === 'desc'}
							aria-pressed={sortOrder === 'desc'}
							on:click={() => handleSortOrderChange('desc')}
							title="내림차순 정렬"
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
								<polygon points="6 6, 18 6, 12 18"></polygon>
							</svg>
							<span>내림차순 (Z-A)</span>
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	.search-section {
		margin-bottom: 32px;
	}
	
	.search-container {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}
	
	.search-box {
		position: relative;
		display: flex;
		align-items: center;
		background: var(--bg-secondary);
		border: 2px solid var(--border-color);
		border-radius: 16px;
		padding: 16px 20px;
		box-shadow: 0 4px 20px var(--shadow);
		transition: all 0.3s ease;
	}
	
	.search-box:focus-within {
		border-color: var(--primary-color);
		box-shadow: 0 4px 25px var(--shadow-hover), 0 0 0 4px rgba(var(--primary-rgb), 0.1);
	}
	
	.search-icon {
		margin-right: 12px;
		font-size: 1.2em;
		color: var(--text-muted);
	}
	
	.search-input {
		flex: 1;
		border: none;
		background: transparent;
		font-size: 1.1em;
		color: var(--text-primary);
		outline: none;
		font-weight: 500;
	}
	
	.search-input::placeholder {
		color: var(--text-muted);
	}
	
	.search-loading {
		margin-right: 12px;
	}
	
	.clear-button {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-size: 1.2em;
		padding: 4px;
		border-radius: 50%;
		transition: all 0.2s ease;
	}
	
	.clear-button:hover {
		color: var(--primary-color);
		background: var(--neutral-light);
	}
	
	.filter-controls.modern {
		display: flex;
		align-items: flex-end;
		gap: 16px;
		padding: 12px 16px;
		background: linear-gradient(180deg, var(--bg-secondary) 0%, var(--neutral-light) 100%);
		border: 1px solid var(--border-color);
		border-radius: 16px;
		box-shadow: 0 6px 20px var(--shadow);
		backdrop-filter: saturate(140%) blur(6px);
	}

	.control-group {
		display: flex;
		flex-direction: column;
		gap: 8px;
		min-width: 220px;
	}

	.control-label {
		font-size: 0.9em;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: 4px;
	}

	.select-wrapper {
		position: relative;
		display: flex;
		align-items: center;
	}

	.select-wrapper .select {
		appearance: none;
		-webkit-appearance: none;
		width: 100%;
		padding: 12px 40px 12px 40px;
		border-radius: 10px;
		border: 1px solid var(--border-color);
		background: var(--bg-secondary);
		color: var(--text-primary);
		font-weight: 600;
		cursor: pointer;
		transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.08s ease;
		box-shadow: 0 2px 8px var(--shadow);
	}

	.select-wrapper .select:focus {
		outline: none;
		border-color: var(--primary-color);
		box-shadow: 0 0 0 4px rgba(var(--primary-rgb), 0.12);
	}

	.select-wrapper .select:hover {
		border-color: var(--primary-color);
	}

	.select-wrapper .select-icon {
		position: absolute;
		left: 12px;
		width: 18px;
		height: 18px;
		stroke-width: 2;
		color: var(--primary-color);
		pointer-events: none;
		opacity: 0.9;
	}

	.sort-control {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.sort-control.segmented .sort-toggle-switch {
		display: inline-flex;
		background: var(--neutral-light);
		border-radius: 12px;
		padding: 4px;
		border: 1px solid var(--border-color);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 4px 14px var(--shadow);
		gap: 4px;
	}

	.sort-toggle-switch .toggle-option {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 14px;
		border: none;
		background: transparent;
		border-radius: 10px;
		cursor: pointer;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text-secondary);
		min-width: 92px;
		justify-content: center;
		transition: background 0.2s ease, color 0.2s ease, transform 0.08s ease;
	}

	.sort-toggle-switch .toggle-option:hover {
		background: rgba(var(--primary-rgb), 0.10);
		color: var(--primary-color);
	}

	.sort-toggle-switch .toggle-option.active {
		background: var(--primary-color);
		color: #fff;
		box-shadow: 0 4px 10px rgba(var(--primary-rgb), 0.35);
		transform: translateY(-1px);
	}

	.sort-toggle-switch .toggle-option svg {
		transition: transform 0.2s ease;
	}

	.sort-toggle-switch .toggle-option.active svg {
		transform: translateY(-1px);
	}

	.sort-toggle-switch .toggle-option span {
		font-weight: 600;
		font-size: 0.8em;
		letter-spacing: 0.5px;
	}

	@media (max-width: 767px) {
		.filter-controls.modern {
			flex-direction: column;
			align-items: stretch;
			gap: 12px;
			padding: 12px;
		}
		
		.control-group {
			min-width: 0;
		}
	}
</style>