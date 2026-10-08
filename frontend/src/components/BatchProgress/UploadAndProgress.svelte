<script>
    import { createEventDispatcher } from 'svelte';
    import BatchProgressMonitor from './BatchProgressMonitor.svelte';
    
    const dispatch = createEventDispatcher();
    
    // Props
    export let accept = '.csv';
    export let maxSize = 100 * 1024 * 1024; // 100MB
    
    // State
    let fileInput;
    let isUploading = false;
    let uploadError = null;
    let currentFileHash = null;
    let showProgress = false;
    let progressMonitor;
    
    // File validation
    function validateFile(file) {
        const errors = [];
        
        if (!file) {
            errors.push('파일을 선택해주세요.');
        } else {
            if (file.size > maxSize) {
                errors.push(`파일 크기가 ${Math.round(maxSize / 1024 / 1024)}MB를 초과합니다.`);
            }
            
            const allowedExtensions = accept.split(',').map(ext => ext.trim().toLowerCase());
            const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!allowedExtensions.includes(fileExtension)) {
                errors.push(`허용된 파일 형식: ${accept}`);
            }
        }
        
        return errors;
    }
    
    // Upload and start batch prediction
    async function handleFileUpload(file) {
        const validationErrors = validateFile(file);
        if (validationErrors.length > 0) {
            uploadError = validationErrors.join(' ');
            return;
        }
        
        try {
            isUploading = true;
            uploadError = null;
            
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/api/batch/start', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Upload failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.success) {
                currentFileHash = result.file_hash;
                showProgress = true;
                
                // Success 이벤트 발송
                dispatch('uploadSuccess', {
                    fileHash: result.file_hash,
                    totalStations: result.total_stations,
                    estimatedTime: result.estimated_time_minutes
                });
                
                // Progress monitor 시작
                if (progressMonitor) {
                    progressMonitor.startMonitoring();
                }
                
            } else {
                uploadError = result.error || '업로드에 실패했습니다.';
            }
            
        } catch (e) {
            console.error('Upload failed:', e);
            uploadError = `업로드 실패: ${e.message}`;
        } finally {
            isUploading = false;
        }
    }
    
    // File input change handler
    function onFileChange(event) {
        const file = event.target.files[0];
        if (file) {
            handleFileUpload(file);
        }
    }
    
    // Drag and drop handlers
    function onDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
    }
    
    function onDrop(event) {
        event.preventDefault();
        
        const files = Array.from(event.dataTransfer.files);
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    }

    // Keyboard accessibility for clickable dropzone
    function onKeyDown(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            fileInput?.click();
        }
    }
    
    // Progress event handlers
    function onProgress(event) {
        dispatch('progress', event.detail);
    }
    
    function onCompleted(event) {
        dispatch('completed', event.detail);
    }
    
    // Reset function
    export function reset() {
        currentFileHash = null;
        showProgress = false;
        uploadError = null;
        isUploading = false;
        if (fileInput) {
            fileInput.value = '';
        }
        if (progressMonitor) {
            progressMonitor.stopMonitoring();
        }
    }
    
        // Get progress function
        export function getProgress() {
            return progressMonitor?.getProgress();
        }
    </script>
    
    <div class="upload-and-progress">
        <!-- Upload Section -->
        {#if !showProgress}
            <div class="upload-section">
                <div 
                    class="upload-dropzone" 
                    class:uploading={isUploading}
                    class:error={uploadError}
                    on:dragover={onDragOver}
                    on:drop={onDrop}
                    on:click={() => fileInput?.click()}
                    on:keydown={onKeyDown}
                    role="button"
                    tabindex="0"
                    aria-disabled={isUploading}
                    aria-label="파일 업로드 영역"
                >
                <input
                    bind:this={fileInput}
                    type="file"
                    {accept}
                    on:change={onFileChange}
                    disabled={isUploading}
                    style="display: none"
                />
                
                <div class="dropzone-content">
                    {#if isUploading}
                        <div class="upload-spinner"></div>
                        <h3>업로드 중...</h3>
                        <p>파일을 업로드하고 배치 예측을 시작하고 있습니다.</p>
                    {:else}
                        <div class="upload-icon">📁</div>
                        <h3>CSV 파일을 업로드하세요</h3>
                        <p>파일을 드래그 앤 드롭하거나 클릭하여 선택하세요</p>
                        <div class="upload-specs">
                            <span>지원 형식: CSV</span>
                            <span>최대 크기: {Math.round(maxSize / 1024 / 1024)}MB</span>
                        </div>
                    {/if}
                </div>
                
                {#if uploadError}
                    <div class="error-message">
                        ⚠️ {uploadError}
                    </div>
                {/if}
            </div>
        </div>
    {/if}
    
    <!-- Progress Section -->
    {#if showProgress && currentFileHash}
        <div class="progress-section">
            <div class="progress-header">
                <h2>배치 예측 진행 중</h2>
                <button 
                    class="reset-btn"
                    on:click={reset}
                    title="새 파일 업로드"
                >
                    새로 시작
                </button>
            </div>
            
            <BatchProgressMonitor 
                bind:this={progressMonitor}
                fileHash={currentFileHash}
                on:progress={onProgress}
                on:completed={onCompleted}
            />
        </div>
    {/if}
</div>

<style>
    .upload-and-progress {
        width: 100%;
        max-width: 800px;
        margin: 0 auto;
    }
    
    .upload-section {
        margin-bottom: 24px;
    }
    
    .upload-dropzone {
        border: 2px dashed #d1d5db;
        border-radius: 12px;
        padding: 40px 20px;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s ease;
        background: var(--bg-secondary, #fff);
        position: relative;
        min-height: 200px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    .upload-dropzone:hover {
        border-color: #3b82f6;
        background: #f8faff;
    }
    
    .upload-dropzone.uploading {
        border-color: #3b82f6;
        background: #f0f9ff;
        cursor: not-allowed;
    }
    
    .upload-dropzone.error {
        border-color: #ef4444;
        background: #fef2f2;
    }
    
    .dropzone-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 16px;
    }
    
    .upload-icon {
        font-size: 3rem;
        opacity: 0.7;
    }
    
    .upload-spinner {
        width: 48px;
        height: 48px;
        border: 4px solid #e5e7eb;
        border-top: 4px solid #3b82f6;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .dropzone-content h3 {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--text-primary, #1f2937);
    }
    
    .dropzone-content p {
        margin: 0;
        color: var(--text-secondary, #6b7280);
        font-size: 1rem;
    }
    
    .upload-specs {
        display: flex;
        gap: 16px;
        font-size: 0.85rem;
        color: var(--text-secondary, #9ca3af);
    }
    
    .error-message {
        position: absolute;
        bottom: 16px;
        left: 16px;
        right: 16px;
        background: #fee2e2;
        border: 1px solid #fecaca;
        color: #dc2626;
        padding: 12px;
        border-radius: 8px;
        font-size: 0.9rem;
        text-align: left;
    }
    
    .progress-section {
        animation: fadeIn 0.3s ease-in-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .progress-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
    }
    
    .progress-header h2 {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--text-primary, #1f2937);
    }
    
    .reset-btn {
        padding: 8px 16px;
        background: #6b7280;
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 0.9rem;
        cursor: pointer;
        transition: background 0.2s;
    }
    
    .reset-btn:hover {
        background: #4b5563;
    }
    
    @media (max-width: 640px) {
        .upload-dropzone {
            padding: 30px 15px;
            min-height: 160px;
        }
        
        .dropzone-content h3 {
            font-size: 1.25rem;
        }
        
        .upload-specs {
            flex-direction: column;
            gap: 4px;
        }
        
        .progress-header {
            flex-direction: column;
            gap: 12px;
            align-items: flex-start;
        }
    }
</style>