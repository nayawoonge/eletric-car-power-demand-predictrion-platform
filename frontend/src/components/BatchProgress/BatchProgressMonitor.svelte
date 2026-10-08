<script>
    import { onMount, onDestroy } from 'svelte';
    import { createEventDispatcher } from 'svelte';
    
    const dispatch = createEventDispatcher();
    
    export let fileHash = null;
    export let autoRefresh = true;
    export let refreshInterval = 2000; // 2초
    
    let progress = {
        success: false,
        total: 0,
        completed: 0,
        failed: 0,
        status: 'unknown',
        percentage: 0,
        started_at: null,
        completed_at: null
    };
    
    let isLoading = false;
    let error = null;
    let refreshTimer = null;
    
    onMount(() => {
        if (fileHash) {
            loadProgress();
            if (autoRefresh) {
                startAutoRefresh();
            }
        }
    });
    
    onDestroy(() => {
        stopAutoRefresh();
    });
    
    function startAutoRefresh() {
        if (refreshTimer) return;
        
        refreshTimer = setInterval(() => {
            if (fileHash && !isCompleted()) {
                loadProgress();
            } else if (isCompleted()) {
                stopAutoRefresh();
            }
        }, refreshInterval);
    }
    
    function stopAutoRefresh() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
    }
    
    function isCompleted() {
        return progress.status && ['completed', 'partial_success', 'failed', 'error'].includes(progress.status);
    }
    
    async function loadProgress() {
        if (!fileHash || isLoading) return;
        
        try {
            isLoading = true;
            error = null;
            
            const response = await fetch(`/api/batch/progress/${encodeURIComponent(fileHash)}`);
            
            if (!response.ok) {
                if (response.status === 404) {
                    error = '배치 처리 정보를 찾을 수 없습니다.';
                    return;
                }
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                progress = data;
                
                // 완료 이벤트 발송
                if (isCompleted() && autoRefresh) {
                    dispatch('completed', {
                        progress: data,
                        success: data.status === 'completed'
                    });
                    stopAutoRefresh();
                }
                
                // 진행 상황 이벤트 발송
                dispatch('progress', data);
            } else {
                error = data.error || '진행 상황을 불러올 수 없습니다.';
            }
            
        } catch (e) {
            console.error('Progress loading failed:', e);
            error = `진행 상황 로드 실패: ${e.message}`;
        } finally {
            isLoading = false;
        }
    }
    
    function getStatusText(status) {
        const statusMap = {
            'processing': '처리 중',
            'completed': '완료',
            'partial_success': '부분 완료', 
            'failed': '실패',
            'error': '오류 발생',
            'unknown': '상태 불명'
        };
        return statusMap[status] || status;
    }
    
    function getStatusClass(status) {
        const classMap = {
            'processing': 'status-processing',
            'completed': 'status-success',
            'partial_success': 'status-warning',
            'failed': 'status-error',
            'error': 'status-error',
            'unknown': 'status-unknown'
        };
        return classMap[status] || 'status-unknown';
    }
    
    function formatTime(isoString) {
        if (!isoString) return '-';
        try {
            return new Date(isoString).toLocaleString();
        } catch {
            return isoString;
        }
    }
    
    function getEstimatedTimeRemaining() {
        if (!progress.started_at || isCompleted() || progress.total === 0) return null;
        
        const startTime = new Date(progress.started_at);
        const now = new Date();
        const elapsedMs = now - startTime;
        const processedCount = progress.completed + progress.failed;
        
        if (processedCount === 0) return null;
        
        const avgTimePerItem = elapsedMs / processedCount;
        const remainingItems = progress.total - processedCount;
        const estimatedRemainingMs = avgTimePerItem * remainingItems;
        
        const minutes = Math.ceil(estimatedRemainingMs / (1000 * 60));
        return minutes > 0 ? `약 ${minutes}분 남음` : '거의 완료';
    }
    
    // 외부에서 호출할 수 있는 함수들 expose
    export function refresh() {
        return loadProgress();
    }
    
    export function startMonitoring() {
        if (!refreshTimer) {
            startAutoRefresh();
        }
    }
    
    export function stopMonitoring() {
        stopAutoRefresh();
    }
</script>

<div class="batch-progress-monitor">
    {#if error}
        <div class="error-card">
            <div class="error-icon">⚠️</div>
            <div class="error-content">
                <h4>오류 발생</h4>
                <p>{error}</p>
                <button class="retry-btn" on:click={loadProgress} disabled={isLoading}>
                    {isLoading ? '로딩 중...' : '다시 시도'}
                </button>
            </div>
        </div>
    {:else if progress.success}
        <div class="progress-card">
            <div class="progress-header">
                <h3>배치 예측 진행 상황</h3>
                <div class="status-badge {getStatusClass(progress.status)}">
                    {getStatusText(progress.status)}
                </div>
            </div>
            
            <div class="progress-body">
                <!-- Progress Bar -->
                <div class="progress-section">
                    <div class="progress-bar-container">
                        <div class="progress-bar">
                            <div 
                                class="progress-fill {getStatusClass(progress.status)}"
                                style="width: {progress.percentage}%"
                            ></div>
                        </div>
                        <div class="progress-text">
                            {Math.round(progress.percentage)}% ({progress.completed + progress.failed} / {progress.total})
                        </div>
                    </div>
                </div>
                
                <!-- Statistics -->
                <div class="stats-section">
                    <div class="stat-item">
                        <div class="stat-label">전체</div>
                        <div class="stat-value">{progress.total}</div>
                    </div>
                    <div class="stat-item success">
                        <div class="stat-label">완료</div>
                        <div class="stat-value">{progress.completed}</div>
                    </div>
                    {#if progress.failed > 0}
                        <div class="stat-item error">
                            <div class="stat-label">실패</div>
                            <div class="stat-value">{progress.failed}</div>
                        </div>
                    {/if}
                </div>
                
                <!-- Time Information -->
                <div class="time-section">
                    {#if progress.started_at}
                        <div class="time-item">
                            <span class="time-label">시작:</span>
                            <span class="time-value">{formatTime(progress.started_at)}</span>
                        </div>
                    {/if}
                    
                    {#if progress.completed_at}
                        <div class="time-item">
                            <span class="time-label">완료:</span>
                            <span class="time-value">{formatTime(progress.completed_at)}</span>
                        </div>
                    {:else}
                        {#if getEstimatedTimeRemaining()}
                            <div class="time-item">
                                <span class="time-label">예상:</span>
                                <span class="time-value">{getEstimatedTimeRemaining()}</span>
                            </div>
                        {/if}
                    {/if}
                </div>
                
                <!-- Loading Indicator -->
                {#if isLoading}
                    <div class="loading-indicator">
                        <div class="spinner"></div>
                        <span>상태 업데이트 중...</span>
                    </div>
                {/if}
            </div>
        </div>
    {:else}
        <div class="placeholder-card">
            <div class="placeholder-content">
                <div class="placeholder-icon">📊</div>
                <p>배치 처리 정보가 없습니다.</p>
                {#if fileHash}
                    <button class="load-btn" on:click={loadProgress} disabled={isLoading}>
                        {isLoading ? '로딩 중...' : '상태 확인'}
                    </button>
                {/if}
            </div>
        </div>
    {/if}
</div>

<style>
    .batch-progress-monitor {
        width: 100%;
        max-width: 600px;
        margin: 0 auto;
    }
    
    .progress-card, .error-card, .placeholder-card {
        background: var(--bg-secondary, #fff);
        border: 1px solid var(--border-color, #e5e7eb);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px var(--shadow, rgba(0, 0, 0, 0.1));
    }
    
    .progress-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--border-color, #e5e7eb);
    }
    
    .progress-header h3 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary, #1f2937);
    }
    
    .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
        color: white;
    }
    
    .status-processing {
        background: #3b82f6;
    }
    
    .status-success {
        background: #10b981;
    }
    
    .status-warning {
        background: #f59e0b;
    }
    
    .status-error {
        background: #ef4444;
    }
    
    .status-unknown {
        background: #6b7280;
    }
    
    .progress-section {
        margin-bottom: 20px;
    }
    
    .progress-bar-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    
    .progress-bar {
        height: 12px;
        background: #f3f4f6;
        border-radius: 6px;
        overflow: hidden;
        position: relative;
    }
    
    .progress-fill {
        height: 100%;
        transition: width 0.3s ease;
        border-radius: 6px;
    }
    
    .progress-fill.status-processing {
        background: linear-gradient(90deg, #3b82f6, #60a5fa);
    }
    
    .progress-fill.status-success {
        background: linear-gradient(90deg, #10b981, #34d399);
    }
    
    .progress-fill.status-warning {
        background: linear-gradient(90deg, #f59e0b, #fbbf24);
    }
    
    .progress-fill.status-error {
        background: linear-gradient(90deg, #ef4444, #f87171);
    }
    
    .progress-text {
        text-align: center;
        font-size: 0.9rem;
        font-weight: 500;
        color: var(--text-secondary, #6b7280);
    }
    
    .stats-section {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
        gap: 16px;
        margin-bottom: 20px;
    }
    
    .stat-item {
        text-align: center;
        padding: 12px;
        border-radius: 8px;
        background: #f9fafb;
        border: 1px solid #f3f4f6;
    }
    
    .stat-item.success {
        background: rgba(16, 185, 129, 0.1);
        border-color: rgba(16, 185, 129, 0.2);
    }
    
    .stat-item.error {
        background: rgba(239, 68, 68, 0.1);
        border-color: rgba(239, 68, 68, 0.2);
    }
    
    .stat-label {
        font-size: 0.8rem;
        color: var(--text-secondary, #6b7280);
        margin-bottom: 4px;
    }
    
    .stat-value {
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--text-primary, #1f2937);
    }
    
    .stat-item.success .stat-value {
        color: #059669;
    }
    
    .stat-item.error .stat-value {
        color: #dc2626;
    }
    
    .time-section {
        display: flex;
        flex-direction: column;
        gap: 8px;
        font-size: 0.9rem;
    }
    
    .time-item {
        display: flex;
        justify-content: space-between;
    }
    
    .time-label {
        color: var(--text-secondary, #6b7280);
    }
    
    .time-value {
        color: var(--text-primary, #1f2937);
        font-weight: 500;
    }
    
    .loading-indicator {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 16px;
        padding: 12px;
        background: #f9fafb;
        border-radius: 8px;
        font-size: 0.9rem;
        color: var(--text-secondary, #6b7280);
    }
    
    .spinner {
        width: 16px;
        height: 16px;
        border: 2px solid #e5e7eb;
        border-top: 2px solid #3b82f6;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .error-card {
        display: flex;
        gap: 16px;
        align-items: flex-start;
    }
    
    .error-icon {
        font-size: 2rem;
        flex-shrink: 0;
    }
    
    .error-content {
        flex: 1;
    }
    
    .error-content h4 {
        margin: 0 0 8px 0;
        color: #dc2626;
        font-size: 1rem;
    }
    
    .error-content p {
        margin: 0 0 16px 0;
        color: var(--text-secondary, #6b7280);
        line-height: 1.5;
    }
    
    .retry-btn, .load-btn {
        padding: 8px 16px;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 0.9rem;
        cursor: pointer;
        transition: background 0.2s;
    }
    
    .retry-btn:hover, .load-btn:hover {
        background: #2563eb;
    }
    
    .retry-btn:disabled, .load-btn:disabled {
        background: #9ca3af;
        cursor: not-allowed;
    }
    
    .placeholder-card {
        text-align: center;
        padding: 40px 20px;
    }
    
    .placeholder-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 16px;
    }
    
    .placeholder-icon {
        font-size: 3rem;
        opacity: 0.5;
    }
    
    .placeholder-content p {
        margin: 0;
        color: var(--text-secondary, #6b7280);
    }
    
    @media (max-width: 640px) {
        .progress-header {
            flex-direction: column;
            gap: 12px;
            align-items: flex-start;
        }
        
        .stats-section {
            grid-template-columns: repeat(2, 1fr);
        }
        
        .time-item {
            flex-direction: column;
            gap: 4px;
        }
    }
</style>