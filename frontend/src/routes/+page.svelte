<script>
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { stations, isLoading, isLoadingMore, error, stationActions, pagination, requiresUpload, hasData } from '../stores/stationStore.ts';
	import { uiActions } from '../stores/uiStore.ts';
	import { searchQuery, sortBy, sortOrder, filteredStations, searchActions } from '../stores/searchStore.ts';
	import LoadingSpinner from '../components/LoadingSpinner.svelte';
	import FileUpload from '../components/FileUpload.svelte';
	import DashboardHeader from '../components/Dashboard/DashboardHeader.svelte';
	import DashboardOverview from '../components/Dashboard/DashboardOverview.svelte';
	import SearchAndFilter from '../components/Dashboard/SearchAndFilter.svelte';
	import StationCard from '../components/Dashboard/StationCard.svelte';

	let scrollContainer;
	let scrollCleanup;
	let searchTimeout;
	
	onMount(async () => {
		await stationActions.checkSystemStatus();
		await stationActions.loadStations();
		scrollCleanup = setupInfiniteScroll();
	});
	
	function setupInfiniteScroll() {
		const handleScroll = () => {
			// 메인 네비게이션 스크롤 사용
			const { scrollTop, scrollHeight, clientHeight } = document.documentElement;
			const nearBottom = scrollTop + clientHeight >= scrollHeight - 300; // 300px 여유
			
			if (nearBottom && !$isLoadingMore && $pagination.hasNext) {
				stationActions.loadMore();
			}
		};

		// 전체 페이지 스크롤에 이벤트 리스너 추가
		window.addEventListener('scroll', handleScroll, { passive: true });
		return () => window.removeEventListener('scroll', handleScroll);
	}
	
	onDestroy(() => {
		if (scrollCleanup) {
			scrollCleanup();
		}
	});
	
	function selectStation(event) {
		const station = event.detail;
		stationActions.setCurrentStation(station);
		goto(`/dashboard/${station.id}`);
	}
	
	function refreshStations() {
		stationActions.loadStations();
		uiActions.showNotification('로드 중...', 'info');
	}
	
	function handleSearchChange(event) {
		if (searchTimeout) clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			searchActions.updateSearch(event.detail);
		}, 50);
	}
	
	function handleSortChange(event) {
		const { sortBy: field, sortOrder: order } = event.detail;
		searchActions.updateSort(field, order);
	}
	
	function clearError() {
		stationActions.clearError();
	}
	
</script>

<svelte:head>
	<title>블루네트웍스 전력 예측 시스템</title>
</svelte:head>

<div class="container">
	<DashboardHeader 
		error={$error} 
		on:clearError={clearError} 
	/>

	{#if $requiresUpload}
		<div class="upload-required-container">
			<FileUpload on:uploaded={() => stationActions.loadStations()} />
		</div>
	{:else}
		<div class="additional-upload">
			<FileUpload on:uploaded={() => stationActions.loadStations()} />
		</div>
	
	<DashboardOverview 
		filteredStations={$filteredStations}
		pagination={$pagination}
		isLoading={$isLoading}
		on:refresh={refreshStations}
	/>

	<SearchAndFilter
		searchQuery={$searchQuery}
		sortBy={$sortBy}
		sortOrder={$sortOrder}
		isLoading={$isLoading}
		on:searchChange={handleSearchChange}
		on:sortChange={handleSortChange}
	/>

	{#if $isLoading}
		<div class="loading-container">
			<LoadingSpinner size="large" />
			<p>충전소 정보를 로드하는 중...</p>
		</div>
	{:else if $filteredStations.length === 0}
		<div class="empty-state">
			<h3>데이터가 존재하지 않습니다.</h3>
			<div class="empty-actions">
				<button class="btn" on:click={refreshStations}>
					다시 시도
				</button>
			</div>
		</div>
	{:else}
		<div class="station-grid" bind:this={scrollContainer}>
			{#each $filteredStations as station (station.id)}
				<StationCard {station} on:select={selectStation} />
			{/each}
			
			{#if $isLoadingMore}
				<div class="loading-more">
					<LoadingSpinner />
					<p>더 많은 충전소를 불러오는 중...</p>
				</div>
			{:else if !$pagination.hasNext && $filteredStations.length > 0}
				<div class="end-message-modern">
					<div class="end-icon">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
							<path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
						</svg>
					</div>
					<div class="end-content">
						{#if $searchQuery}
							<h3>검색 완료</h3>
							<p><strong>{$filteredStations.length}개소</strong>를 찾았습니다</p>
							<span class="end-subtitle">전체 {$pagination.total}개소 중</span>
						{:else}
							<h3>모든 데이터 로드 완료</h3>
							<p>총 <strong>{$pagination.total}개소</strong>의 충전소</p>
							<span class="end-subtitle">시스템에 등록된 모든 충전소입니다</span>
						{/if}
					</div>
				</div>
			{/if}
		</div>
		{/if}
	{/if}
</div>


<style>
	.container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 20px;
	}
	
	.upload-required-container {
		margin-bottom: 2rem;
	}

	.additional-upload {
		margin-bottom: 2rem;
		padding: 1rem;
		background: var(--bg-secondary);
		border-radius: 12px;
		border: 1px solid var(--border-color);
	}

	.end-message-modern {
		grid-column: 1 / -1;
		display: flex;
		align-items: center;
		gap: 16px;
		background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--neutral-light) 100%);
		border-radius: 20px;
		padding: 32px;
		margin: 32px 0;
		border: 1px solid var(--border-color);
		box-shadow: 0 8px 32px var(--shadow);
		transition: all 0.3s ease;
		position: relative;
		overflow: hidden;
	}
	
	.end-message-modern::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 4px;
		background: linear-gradient(90deg, #22c55e, #16a34a, #15803d);
		opacity: 0.8;
	}
	
	.end-message-modern:hover {
		transform: translateY(-2px);
		box-shadow: 0 12px 40px var(--shadow-hover);
		border-color: #22c55e;
	}
	
	.end-icon {
		width: 56px;
		height: 56px;
		background: linear-gradient(135deg, #22c55e, #16a34a);
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
		flex-shrink: 0;
		box-shadow: 0 4px 16px rgba(34, 197, 94, 0.3);
	}
	
	.end-icon svg {
		width: 28px;
		height: 28px;
		stroke-width: 2.5;
	}
	
	.end-content {
		flex: 1;
		min-width: 0;
	}
	
	.end-content h3 {
		margin: 0 0 8px 0;
		font-size: 1.4em;
		font-weight: 700;
		color: var(--primary-color);
		line-height: 1.2;
	}
	
	.end-content p {
		margin: 0 0 6px 0;
		font-size: 1.1em;
		color: var(--text-primary);
		font-weight: 500;
	}
	
	.end-content p strong {
		color: #22c55e;
		font-weight: 700;
	}
	
	.end-subtitle {
		font-size: 0.9em;
		color: var(--text-muted);
		font-weight: 500;
		opacity: 0.8;
	}

	@media (max-width: 767px) {
		.container {
			padding: 16px;
		}
		
		.end-message-modern {
			flex-direction: column;
			text-align: center;
			padding: 24px;
			gap: 20px;
		}
		
		.end-content h3 {
			font-size: 1.2em;
		}
		
		.end-content p {
			font-size: 1em;
		}
	}
</style>