<script lang="ts">
    import {
        stationActions,
        isLoading,
        requiresUpload,
        hasData
    } from "../stores/stationStore";
    import { uiActions } from "../stores/uiStore";
    import { createEventDispatcher, onMount } from "svelte";
    import LoadingSpinner from "./LoadingSpinner.svelte";
    import { apiService } from '../services/api';

    const dispatch = createEventDispatcher();

    let fileInput;
    let dragOver = false;
    let selectedFile: File | null = null;
    let isUploading = false;
    let uploadProgress = 0;
    let error: string | null = null;

    // 현재 업로드된(활성) CSV 의 데이터 기간
    let csvInfo: { has_data: boolean; start_date?: string; end_date?: string; row_count?: number } | null = null;

    async function loadCsvInfo() {
        try {
            const res = await fetch(`/api/admin/active-csv-info`);
            const data = await res.json();
            csvInfo = data?.success && data?.has_data ? data : null;
        } catch (e) {
            csvInfo = null;
        }
    }

    onMount(loadCsvInfo);

    // 고급 업로드 함수 (진행률 표시 포함)
    async function handleFileUpload(file: File) {
        // 파일 유효성 검사
        if (!file.name.toLowerCase().endsWith('.csv')) {
            uiActions.showNotification('CSV 파일만 업로드 가능합니다.', 'error');
            return;
        }

        if (file.size > 100 * 1024 * 1024) {
            uiActions.showNotification('파일 크기는 100MB를 초과할 수 없습니다.', 'error');
            return;
        }

        isUploading = true;
        uploadProgress = 0;

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('file_type', 'charging_sessions');

            // 업로드 진행률 시뮬레이션
            const progressInterval = setInterval(() => {
                if (uploadProgress < 90) {
                    uploadProgress = Math.min(90, uploadProgress + Math.random() * 20);
                }
            }, 200);

            // dev는 Vite 프록시가 /api를 백엔드로 전달, prod는 같은 오리진 사용
            const response = await fetch(`/api/admin/upload-csv`, {
                method: 'POST',
                body: formData
            });

            clearInterval(progressInterval);
            uploadProgress = 100;

            const result = await response.json();

            if (response.ok) {
                uiActions.showNotification(`CSV 파일 업로드 성공! (${result.rows_processed}개 행 불러옴)`, 'success');
                // 스토어 갱신
                await stationActions.loadStations();
                requiresUpload.set(false);
                hasData.set(true);
                // 활성 CSV 데이터 기간 표시 갱신
                await loadCsvInfo();
                // 업로드된 파일 정보와 함께 이벤트 디스패치
                dispatch("uploaded", { result });
            } else {
                throw new Error(result?.error || '업로드 실패');
            }

        } catch (error: any) {
            console.error('CSV 업로드 오류:', error);
            uiActions.showNotification(`업로드 실패 : ${error.message ?? error}`, 'error');
        } finally {
            isUploading = false;
            uploadProgress = 0;
            if (fileInput) fileInput.value = '';
        }
    }

    // 파일 선택 핸들러
    async function handleFileSelect(event) {
        const target = event.target as HTMLInputElement;
        if (target.files && target.files[0]) {
            selectedFile = target.files[0];
            await handleFileUpload(selectedFile); // 진행률 업로드 사용
        }
    }

    // 드래그 앤 드롭 업로드
    async function handleDrop(event: DragEvent) {
        event.preventDefault();
        dragOver = false;

        if (event.dataTransfer && event.dataTransfer.files) {
            const file = event.dataTransfer.files[0];
            if (file && file.name.toLowerCase().endsWith(".csv")) {
                selectedFile = file;
                await handleFileUpload(file); // 진행률 업로드 사용
            } else {
                uiActions.showNotification("CSV 파일만 업로드 가능합니다.", 'error');
            }
        }
    }

    function handleDragOver(event: DragEvent) {
        event.preventDefault();
        dragOver = true;
    }

    function handleDragLeave() {
        dragOver = false;
    }

    function triggerFileSelect() {
        if (!isUploading) fileInput.click();
    }

    async function onChange(e: Event) {
        const input = e.target as HTMLInputElement;
        const file = input.files?.[0];
        if (!file) return;
        error = null;
        isUploading = true;
        try {
            const res = await apiService.uploadCsv(file);
            dispatch('uploaded', res);
        } catch (err: unknown) {
            error = err instanceof Error ? err.message : '업로드 실패';
        } finally {
            isUploading = false;
            // 선택 초기화
            input.value = '';
        }
    }
</script>

<!-- 업로드 컨트롤 섹션 -->
<div class="upload-requirements">
    <div class="requirement-grid">
        <div class="requirement-card">
            <svg class="requirement-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                <polyline points="13,2 13,9 20,9"/>
            </svg>
            <div class="requirement-content">
                <div class="requirement-value">파일 업로드</div>
                <div class="requirement-label">csv파일</div>
            </div>
        </div>
        <div class="requirement-card">
            <svg class="requirement-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
                <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
            </svg>
            <div class="requirement-content">
                <div class="requirement-value">드래그 & 드롭</div>
                <div class="requirement-label">업로드 방식</div>
            </div>
        </div>
        <div class="requirement-card">
            <svg class="requirement-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14,2 14,8 20,8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10,9 9,9 8,9"/>
            </svg>
            <div class="requirement-content">
                <div class="requirement-value">CSV</div>
                <div class="requirement-label">지원 확장자</div>
            </div>
        </div>
    </div>
</div>

{#if isUploading}
    <div class="progress-bar">
        <div class="progress-fill" style="width: {uploadProgress}%"></div>
    </div>
{/if}

<div
    class="upload-area"
    class:drag-over={dragOver}
    class:loading={$isLoading || isUploading}
    on:drop={handleDrop}
    on:dragover={handleDragOver}
    on:dragleave={handleDragLeave}
    role="button"
    tabindex="0"
    on:click={triggerFileSelect}
    on:keydown={(e) => e.key === "Enter" && triggerFileSelect()}
>
    {#if $isLoading || isUploading}
        <div class="loading-spinner">
            <div class="spinner"></div>
            <p>파일을 업로드하고 처리 중입니다...</p>
        </div>
    {:else}
        <div class="upload-content">
            <svg
                width="64"
                height="64"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
            >
                <path
                    d="M12 15V3m0 0l-4 4m4-4l4 4M2 17l.621 2.485A2 2 0 0 0 4.561 21h14.878a2 2 0 0 0 1.94-1.515L22 17"
                ></path>
            </svg>
            <h3>파일을 드래그하거나 클릭하여 업로드</h3>
            <p>CSV 형식의 충전이력 데이터를 업로드해주세요</p>

            {#if selectedFile}
                <div class="selected-file">
                    <p><strong>선택된 파일 :</strong> {selectedFile.name}</p>
                </div>
            {/if}
        </div>
    {/if}
</div>

{#if csvInfo && csvInfo.has_data}
    <p class="csv-data-range">
        현재 데이터: {csvInfo.start_date} ~ {csvInfo.end_date}
        {#if csvInfo.row_count}<span class="csv-rows">({csvInfo.row_count.toLocaleString()}행)</span>{/if}
    </p>
{/if}

<div class="upload-note">
    <strong>⚠️ 업로드 시 유의사항</strong>
    <ul>
        <li>업로드 파일은 기존 데이터에 <strong>합쳐지지 않고 전체가 교체</strong>됩니다.
            새 월만 올리면 이전 데이터가 모두 사라지므로, <strong>처음부터 최신 월까지 전체 기간을 포함한 누적 CSV</strong>를 업로드해야 합니다.</li>
        <li>여러 월 파일을 그대로 이어붙이면 중복이 섞일 수 있어,
            <strong>병합 + 중복 제거 전처리</strong> 후 업로드를 권장합니다.
            (전처리 스크립트: <code>backend/preprocess_train_data.py</code>)</li>
    </ul>
</div>

<input
    bind:this={fileInput}
    type="file"
    accept=".csv"
    on:change={handleFileSelect}
    style="display: none;"
/>

<style>

    .csv-data-range {
        margin: 0.5rem 0 0;
        text-align: center;
        font-size: 0.8rem;
        color: var(--text-secondary, #6b7280);
    }

    .csv-data-range .csv-rows {
        opacity: 0.75;
        margin-left: 0.25rem;
    }

    .upload-note {
        margin: 0.75rem auto 0;
        max-width: 640px;
        padding: 0.75rem 1rem;
        font-size: 0.8rem;
        line-height: 1.5;
        color: var(--text-secondary, #6b7280);
        background: var(--alert-warning-bg, #fffbeb);
        border: 1px solid var(--alert-warning-border, #fde68a);
        border-radius: 10px;
    }

    .upload-note strong {
        color: var(--text-primary, #374151);
    }

    .upload-note ul {
        margin: 0.4rem 0 0;
        padding-left: 1.1rem;
    }

    .upload-note li {
        margin-top: 0.3rem;
    }

    .upload-note code {
        font-size: 0.75rem;
        background: rgba(0, 0, 0, 0.06);
        padding: 0.05rem 0.3rem;
        border-radius: 4px;
    }

    .upload-area {
        border: 2px dashed var(--border-color);
        border-radius: 16px;
        padding: 3rem 2rem;
        text-align: center;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
        background: transparent;
        position: relative;
    }

    .upload-area:hover {
        border-color: var(--primary-color);
        background: var(--neutral-light);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px var(--shadow-hover);
    }

    .upload-area.drag-over {
        border-color: var(--primary-color);
        background: var(--neutral-light);
        transform: scale(1.02) translateY(-2px);
        box-shadow: 0 12px 35px var(--shadow-hover);
    }

    .upload-area.loading {
        cursor: not-allowed;
        opacity: 0.7;
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0%,
        100% {
            opacity: 0.7;
        }
        50% {
            opacity: 1;
        }
    }

    .upload-content svg {
        color: var(--primary-color);
        margin-bottom: 1.5rem;
        animation: bounce 3s ease-in-out infinite;
    }

    @keyframes bounce {
        0%,
        100% {
            transform: translateY(0px);
        }
        50% {
            transform: translateY(-8px);
        }
    }

    .upload-content h3 {
        margin: 0 0 1rem 0;
        color: var(--text-primary);
        font-size: 1.5rem;
        font-weight: 600;
        letter-spacing: -0.025em;
        line-height: 1.3;
    }

    .upload-content p {
        margin: 0;
        color: var(--text-secondary);
        font-size: 1rem;
        font-weight: 400;
        max-width: 400px;
        margin: 0 auto;
        line-height: 1.5;
    }

    .selected-file {
        margin-top: 1.5rem;
        padding: 1rem 1.5rem;
        background: var(--alert-success-bg);
        border-radius: 12px;
        border: 1px solid var(--alert-success-border);
        position: relative;
        animation: slideIn 0.3s ease-out;
    }

    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .selected-file::before {
        content: "✓";
        position: absolute;
        top: -8px;
        right: -8px;
        width: 20px;
        height: 20px;
        background: var(--alert-success-border);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 12px;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);
    }

    .selected-file p {
        margin: 0;
        color: var(--alert-success-text);
        font-size: 0.95rem;
        font-weight: 500;
        text-align: left;
    }

    .loading-spinner {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1.5rem;
    }

    .spinner {
        width: 40px;
        height: 40px;
        border: 3px solid var(--border-color);
        border-top: 3px solid var(--primary-color);
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    .loading-spinner p {
        color: var(--text-primary);
        font-size: 1.1rem;
        font-weight: 500;
        animation: pulse 2s ease-in-out infinite;
    }

    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
    }

    .upload-requirements {
        margin-bottom: 24px;
    }
    
    .requirement-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 16px;
    }

    .requirement-card {
        background: var(--bg-secondary, white);
        border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
        border-radius: 12px;
        padding: 20px;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: all 0.3s ease;
        box-shadow: 0 2px 8px var(--shadow, rgba(0, 0, 0, 0.05));
    }
    
    .requirement-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px var(--shadow-hover, rgba(0, 0, 0, 0.15));
        border-color: var(--primary-color, #4f46e5);
    }

    .requirement-icon {
        width: 24px;
        height: 24px;
        stroke-width: 2;
        color: var(--primary-color, #4f46e5);
        flex-shrink: 0;
    }
    
    .requirement-content {
        flex: 1;
    }
    
    .requirement-value {
        font-size: 1.1em;
        font-weight: 700;
        color: var(--text-primary, #111827);
        margin-bottom: 2px;
        line-height: 1.2;
    }
    
    .requirement-label {
        font-size: 0.85em;
        color: var(--text-secondary, #6b7280);
        font-weight: 500;
    }

    /* 다크모드 호환성 */
    :global([data-theme="dark"]) .requirement-card {
        --bg-secondary: #1f2937;
        --border-color: #374151;
        --shadow: rgba(0, 0, 0, 0.3);
        --shadow-hover: rgba(0, 0, 0, 0.5);
        --text-primary: #f9fafb;
        --text-secondary: #d1d5db;
        --primary-color: #6366f1;
    }
    
    :global([data-theme="light"]) .requirement-card {
        --bg-secondary: #ffffff;
        --border-color: rgba(0, 0, 0, 0.1);
        --shadow: rgba(0, 0, 0, 0.05);
        --shadow-hover: rgba(0, 0, 0, 0.15);
        --text-primary: #111827;
        --text-secondary: #6b7280;
        --primary-color: #4f46e5;
    }

    /* 진행률 바 스타일 */
    .progress-bar {
        width: 100%;
        height: 6px;
        background: var(--bg-tertiary);
        border-radius: 3px;
        overflow: hidden;
        margin-bottom: 20px;
        border: 1px solid var(--border-color);
    }

    .progress-fill {
        height: 100%;
        background: var(--gradient-success);
        border-radius: 3px;
        transition: width 0.3s ease;
        position: relative;
    }

    .progress-fill::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(90deg, 
            transparent 0%, 
            rgba(255,255,255,0.3) 50%, 
            transparent 100%);
        animation: shimmer 2s infinite;
    }

    @keyframes shimmer {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
    }

    /* 반응형 디자인 */
    @media (max-width: 768px) {
        .requirement-grid {
            grid-template-columns: 1fr;
        }

        .upload-area {
            padding: 2rem 1rem;
        }
    }
</style>
