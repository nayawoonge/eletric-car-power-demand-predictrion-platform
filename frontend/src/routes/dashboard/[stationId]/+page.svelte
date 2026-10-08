<script>
    import { onMount, onDestroy } from "svelte";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import {
        stationActions,
        stationData,
        currentStation,
        isLoading,
        error,
        insufficientData,
        stationById,
    } from "../../../stores/stationStore.ts";
    import { uiActions, isRefreshing } from "../../../stores/uiStore.ts";
    import { theme } from "../../../stores/themeStore.ts";

    import PeakPowerPredictor from "../../../components/Dashboard/PeakPowerPredictor.svelte";
    import PowerDemandPredictor from "../../../components/Dashboard/PowerDemandPredictor.svelte";
    import EnsemblePrediction from "../../../components/Dashboard/EnsemblePrediction.svelte";
    import LoadingSpinner from "../../../components/LoadingSpinner.svelte";

    let stationId;
    let station = null;
    let showResults = false;
    let resultsContent = "";

    $: stationId = $page.params.stationId;
    $: station = $stationById.get(stationId);

    onMount(async () => {
        // Initialize theme
        theme.init();
        
        // Chart.js 모듈 미리 로드 (병렬 처리)
        if (typeof window !== 'undefined') {
            import('../../../lib/chart-utils.js').then(({ preloadChartModules }) => {
                preloadChartModules();
            }).catch(error => {
                console.log('Chart utils preload failed:', error);
            });
        }
        
        if (!stationId) {
            goto("/");
            return;
        }

        // Load station data if not already loaded (최적화: 병렬 처리)
        let stationLoadPromise = null;
        if (!station) {
            stationLoadPromise = stationActions.loadStations();
        }

        // 차트 데이터 로딩을 미리 시작 (충전소 정보와 병렬 처리)
        const dataLoadPromise = loadData();

        // 충전소 정보가 필요한 경우 대기
        if (stationLoadPromise) {
            await stationLoadPromise;
            station = $stationById.get(stationId);
        }

        if (!station) {
            uiActions.showNotification(
                `충전소 '${stationId}'를 찾을 수 없습니다.`,
                "error"
            );
            goto("/");
            return;
        }

        stationActions.setCurrentStation(station);
        
        // 데이터 로딩 완료 대기
        await dataLoadPromise;

        // Keyboard shortcuts (브라우저에서만 실행)
        if (typeof document !== 'undefined') {
            document.addEventListener("keydown", handleKeydown);
        }
    });

    onDestroy(() => {
        if (typeof document !== 'undefined') {
            document.removeEventListener("keydown", handleKeydown);
        }
    });

    async function loadData() {
        try {
            await stationActions.loadStationData(stationId);
        } catch (error) {
            uiActions.showNotification(
                '데이터 로딩에 실패했습니다. 새로고침을 시도해주세요.',
                'error'
            );
        }
    }

    async function refreshDashboard() {
        uiActions.setRefreshing(true);
        try {
            await loadData();
            uiActions.showNotification(
                "대시보드가 새로고침되었습니다",
                "success"
            );
        } catch (err) {
            uiActions.showNotification("새로고침에 실패했습니다", "error");
        } finally {
            uiActions.setRefreshing(false);
        }
    }

    async function testRealtime() {
        try {
            const prediction = $stationData.prediction;
            if (prediction) {
                resultsContent = JSON.stringify(prediction, null, 2);
                showResults = true;
                uiActions.showNotification(
                    "실시간 예측이 완료되었습니다",
                    "success"
                );
            }
        } catch (err) {
            uiActions.showNotification("실시간 예측에 실패했습니다", "error");
        }
    }

    async function testMonthly() {
        try {
            const monthlyContract = $stationData.monthlyContract;
            if (monthlyContract) {
                resultsContent = JSON.stringify(monthlyContract, null, 2);
                showResults = true;
                uiActions.showNotification(
                    "월별 계약 권고가 완료되었습니다",
                    "success"
                );
            }
        } catch (err) {
            uiActions.showNotification(
                "월별 계약 권고에 실패했습니다",
                "error"
            );
        }
    }

    async function testAnalysis() {
        try {
            const analysis = $stationData.analysis;
            if (analysis) {
                resultsContent = JSON.stringify(analysis, null, 2);
                showResults = true;
                uiActions.showNotification(
                    "상세 분석이 완료되었습니다",
                    "success"
                );
            }
        } catch (err) {
            uiActions.showNotification("상세 분석에 실패했습니다", "error");
        }
    }

    function exportData() {
        try {
            const exportData = {
                timestamp: new Date().toISOString(),
                station_id: stationId,
                station_info: station,
                data: $stationData,
            };

            const blob = new Blob([JSON.stringify(exportData, null, 2)], {
                type: "application/json",
            });

            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${stationId}_dashboard_${new Date().toISOString().split("T")[0]}.json`;
            a.click();
            URL.revokeObjectURL(url);

            uiActions.showNotification("데이터 내보내기 완료", "success");
        } catch (err) {
            uiActions.showNotification(
                "데이터 내보내기에 실패했습니다",
                "error"
            );
        }
    }

    function handleKeydown(event) {
        if (event.ctrlKey || event.metaKey) {
            switch (event.key.toLowerCase()) {
                case "r":
                    event.preventDefault();
                    refreshDashboard();
                    break;
                case "e":
                    event.preventDefault();
                    exportData();
                    break;
                case "1":
                    event.preventDefault();
                    testRealtime();
                    break;
                case "2":
                    event.preventDefault();
                    testAnalysis();
                    break;
                case "3":
                    event.preventDefault();
                    testMonthly();
                    break;
                case "arrowleft":
                    event.preventDefault();
                    window.history.back();
                    break;
            }
        }

        if (event.key === "Escape") {
            showResults = false;
        }
    }


    $: analysis = $stationData.analysis;
    $: monthlyContract = $stationData.monthlyContract;
</script>

<svelte:head>
    <title>{station?.name || stationId} - 전력 예측 대시보드</title>
</svelte:head>

<div class="container">
    <div class="header">
        <div class="header-content">
            <div class="navigation-section">
                <nav class="breadcrumb">
                    <a href="/" class="breadcrumb-item">
                        <svg
                            class="breadcrumb-icon"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path
                                d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
                            />
                            <polyline points="9,22 9,12 15,12 15,22" />
                        </svg>
                        <span>충전소 목록</span>
                    </a>
                    <svg
                        class="breadcrumb-separator"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                    >
                        <polyline points="9,18 15,12 9,6" />
                    </svg>
                    <span class="breadcrumb-current">
                        <svg
                            class="breadcrumb-icon"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                        </svg>
                        <span>대시보드</span>
                    </span>
                </nav>

                <button
                    class="btn-back-enhanced"
                    on:click={() => window.history.back()}
                >
                    <svg
                        class="back-arrow"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                    >
                        <path d="M19 12H5m7-7-7 7 7 7" />
                    </svg>
                    <div class="btn-back-content">
                        <span class="btn-back-text">뒤로 가기</span>
                        <span class="btn-back-hint">Ctrl + ←</span>
                    </div>
                </button>
            </div>

            <div class="header-title">
                <h1>전력 예측 대시보드</h1>
                <p class="header-subtitle">
                    블루네트웍스 전력 수요 예측 시스템
                </p>
            </div>

            <div class="header-actions">
                <div class="quick-actions">
                    <!-- 테마 토글 버튼 -->
                    <button 
                        class="header-action-btn theme-toggle" 
                        on:click={() => theme.toggleTheme()}
                        title={$theme === 'light' ? '다크 모드로 변경' : '라이트 모드로 변경'}
                    >
                        {#if $theme === 'light'}
                            <!-- Moon icon for dark mode -->
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                            </svg>
                        {:else}
                            <!-- Sun icon for light mode -->
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="5"/>
                                <line x1="12" y1="1" x2="12" y2="3"/>
                                <line x1="12" y1="21" x2="12" y2="23"/>
                                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                                <line x1="1" y1="12" x2="3" y2="12"/>
                                <line x1="21" y1="12" x2="23" y2="12"/>
                                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                            </svg>
                        {/if}
                    </button>

                    <button 
                        class="header-action-btn" 
                        title="대시보드 새로고침"
                        on:click={refreshDashboard}
                    >
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path d="M23 4v6h-6" />
                            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                        </svg>
                    </button>
                    <button class="header-action-btn" title="데이터 내보내기">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path
                                d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
                            />
                            <polyline points="7,10 12,15 17,10" />
                            <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                    </button>
                    <button class="header-action-btn" title="알림 설정">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path
                                d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"
                            />
                            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    </div>

    {#if station}
        <div class="station-info">
            <h2>🏢 {station.name}</h2>
            <div class="station-details">
                <div class="detail-item">
                    <span class="detail-label">⚡ 충전기 타입</span>
                    <span class="detail-value">{station.charger_type}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">🔌 커넥터</span>
                    <span class="detail-value">{station.connector_type}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">
                        📊 용량 효율성
                        <div class="info-tooltip">
                            <div class="info-icon">?</div>
                            <div class="tooltip-content">
                                <div class="tooltip-formula">
                                    <strong>계산 방식:</strong> 평균전력 / 정격용량 × 100%
                                </div>
                                <div class="capacity-examples">
                                    완속(AC): 7kW 기준 • 급속(DC): 100kW 기준
                                </div>
                            </div>
                        </div>
                    </span>
                    <span class="detail-value capacity-efficiency"
                        >{station.capacity_efficiency || "-"}</span
                    >
                </div>
            </div>
            <p class="station-location">📍 {station.location}</p>
        </div>
    {/if}

    {#if $isLoading}
        <div class="loading-container">
            <LoadingSpinner size="large" />
            <p>데이터를 로드하는 중...</p>
        </div>
    {:else if $insufficientData}
        <div class="insufficient-panel">
            <div class="insufficient-icon">📊</div>
            <h2 class="insufficient-title">
                {$insufficientData.error_code === 'NO_DATA' ? '이 충전소의 데이터를 찾을 수 없습니다' : '분석을 위한 데이터가 부족합니다'}
            </h2>
            <p class="insufficient-message">{$insufficientData.error}</p>
            {#if $insufficientData.details}
                <div class="insufficient-meta">
                    <div class="meta-row">
                        <span class="meta-label">현재</span>
                        <span>
                            세션 <strong>{$insufficientData.details.session_count ?? 0}</strong>건
                            {#if $insufficientData.details.unique_days !== null && $insufficientData.details.unique_days !== undefined}
                                · 관측 <strong>{$insufficientData.details.unique_days}</strong>일
                            {/if}
                            {#if $insufficientData.details.data_coverage_start && $insufficientData.details.data_coverage_end}
                                ({$insufficientData.details.data_coverage_start} ~ {$insufficientData.details.data_coverage_end})
                            {/if}
                        </span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">필요</span>
                        <span>
                            최소 세션 <strong>{$insufficientData.details.min_required_sessions ?? 14}</strong>건 ·
                            <strong>{$insufficientData.details.min_required_days ?? 7}</strong>일 이상
                        </span>
                    </div>
                </div>
            {/if}
            {#if $insufficientData.guidance && $insufficientData.guidance.length > 0}
                <ul class="insufficient-guidance">
                    {#each $insufficientData.guidance as g}
                        <li>{g}</li>
                    {/each}
                </ul>
            {/if}
            <button class="back-btn" on:click={() => goto('/')}>
                ← 충전소 목록으로 돌아가기
            </button>
        </div>
    {:else if $error}
        <div class="alert alert-error">
            <strong>오류</strong>
            {$error}
        </div>
    {:else}
        <!-- Phase 3: AI 앙상블 예측 (최상단) -->
        <EnsemblePrediction {stationId} currentContractKw={100} />

        <!-- Main Prediction Sections -->
        <!-- <div class="prediction-sections"> -->
            <!-- 순간최고 전력 예측 박스 -->
            <!-- <div class="prediction-box peak-power-box">
                <div class="prediction-box-header">
                    <div class="box-title">
                        <h2>순간 최고 전력 예측</h2>
                        <p>계약전력 권고 및 피크 전력 분석</p>
                    </div>
                    <button
                        class="box-refresh-btn primary"
                        on:click={refreshDashboard}
                        disabled={$isRefreshing}
                        title="순간최고전력 예측 갱신"
                    >
                        {#if $isRefreshing}
                            <LoadingSpinner size="small" />
                        {:else}
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M23 4v6h-6" />
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                            </svg>
                        {/if}
                        <span>갱신</span>
                    </button>
                </div>
                <div class="prediction-box-content">
                    <PeakPowerPredictor
                        {stationId}
                        {monthlyContract}
                    />
                </div>
            </div> -->

            <!-- 에너지 수요 예측 박스 -->
            <!-- <div class="prediction-box energy-demand-box">
                <div class="prediction-box-header">
                    <div class="box-title">
                        <h2>전력량 수요 예측</h2>
                        <p>전력량 기반 수요 패턴 분석 및 예측</p>
                    </div>
                    <button
                        class="box-refresh-btn secondary"
                        on:click={refreshDashboard}
                        disabled={$isRefreshing}
                        title="에너지 수요 예측 갱신"
                    >
                        {#if $isRefreshing}
                            <LoadingSpinner size="small" />
                        {:else}
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M23 4v6h-6" />
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                            </svg>
                        {/if}
                        <span>갱신</span>
                    </button>
                </div>
                <div class="prediction-box-content">
                    <PowerDemandPredictor
                        {stationId}
                        {analysis}
                    />
                </div>
            </div>
        </div> -->

        <!-- <div class="control-dashboard">
            <div class="dashboard-header">
                <div class="header-info">
                    <div class="header-icon">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path d="M12 20h9" />
                            <path
                                d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"
                            />
                        </svg>
                    </div>
                    <div class="header-text">
                        <h3>API 테스트 대시보드</h3>
                        <p>API 테스트 도구</p>
                    </div>
                </div>
            </div>

            <div class="action-grid">
                <div class="action-card primary" class:loading={$isRefreshing}>
                    <div class="action-icon">
                        {#if $isRefreshing}
                            <LoadingSpinner size="small" />
                        {:else}
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                            >
                                <path d="M23 4v6h-6" />
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                            </svg>
                        {/if}
                    </div>
                    <div class="action-content">
                        <h4>대시보드 새로고침</h4>
                        <p>전체 데이터 및 차트 업데이트</p>
                        <button
                            class="action-btn"
                            on:click={refreshDashboard}
                            disabled={$isRefreshing}
                        >
                            새로고침
                        </button>
                    </div>
                </div>

                <div class="action-card">
                    <div class="action-icon">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path d="M12 2L2 7l10 5 10-5-10-5z" />
                            <path d="M2 17l10 5 10-5" />
                            <path d="M2 12l10 5 10-5" />
                        </svg>
                    </div>
                    <div class="action-content">
                        <h4>예측 데이터 확인하기</h4>
                        <p>전력 수요 예측 및 분석</p>
                        <button class="action-btn" on:click={testRealtime}>
                            데이터 확인
                        </button>
                    </div>
                </div>

                <div class="action-card">
                    <div class="action-icon">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <rect
                                x="3"
                                y="4"
                                width="18"
                                height="18"
                                rx="2"
                                ry="2"
                            />
                            <line x1="16" y1="2" x2="16" y2="6" />
                            <line x1="8" y1="2" x2="8" y2="6" />
                            <line x1="3" y1="10" x2="21" y2="10" />
                        </svg>
                    </div>
                    <div class="action-content">
                        <h4>월별 계약 권고</h4>
                        <p>최적 계약 전력 및 비용 분석</p>
                        <button class="action-btn" on:click={testMonthly}>
                            분석 시작
                        </button>
                    </div>
                </div>

                <div class="action-card">
                    <div class="action-icon">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <line x1="18" y1="20" x2="18" y2="10" />
                            <line x1="12" y1="20" x2="12" y2="4" />
                            <line x1="6" y1="20" x2="6" y2="14" />
                        </svg>
                    </div>
                    <div class="action-content">
                        <h4>상세 분석</h4>
                        <p>종합적인 성능 및 이용 패턴 분석</p>
                        <button class="action-btn" on:click={testAnalysis}>
                            분석 보기
                        </button>
                    </div>
                </div>

                <div class="action-card">
                    <div class="action-icon">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                        >
                            <path
                                d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
                            />
                            <polyline points="7,10 12,15 17,10" />
                            <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                    </div>
                    <div class="action-content">
                        <h4>데이터 내보내기</h4>
                        <p>JSON 형식으로 전체 데이터 다운로드</p>
                        <button class="action-btn" on:click={exportData}>
                            내보내기
                        </button>
                    </div>
                </div>
            </div>

            {#if showResults}
                <div class="results-modal">
                    <div class="modal-header">
                        <div class="modal-title">
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                            >
                                <polyline
                                    points="22,12 18,12 15,21 9,3 6,12 2,12"
                                />
                            </svg>
                            분석 결과
                        </div>
                        <button
                            class="close-btn"
                            on:click={() => (showResults = false)}
                        >
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                            >
                                <line x1="18" y1="6" x2="6" y2="18" />
                                <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                        </button>
                    </div>
                    <div class="modal-content">
                        <pre class="results-code">{resultsContent}</pre>
                    </div>
                    <div class="modal-actions">
                        <button
                            class="action-btn secondary"
                            on:click={async () => {
                                try {
                                    await navigator.clipboard.writeText(resultsContent);
                                    uiActions.showNotification("복사되었습니다", "success");
                                } catch (err) {
                                    uiActions.showNotification("복사에 실패했습니다", "error");
                                }
                            }}
                        >
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                            >
                                <rect
                                    x="9"
                                    y="9"
                                    width="13"
                                    height="13"
                                    rx="2"
                                    ry="2"
                                />
                                <path
                                    d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                                />
                            </svg>
                            복사
                        </button>
                        <button
                            class="action-btn"
                            on:click={() => (showResults = false)}
                        >
                            닫기
                        </button>
                    </div>
                </div>
            {/if}
        </div> -->
    {/if}
</div>

<style>
    .loading-container {
        text-align: center;
        padding: 60px 20px;
    }

    .loading-container p {
        margin-top: 20px;
        color: var(--text-secondary);
        font-size: 1.1em;
    }

    .insufficient-panel {
        max-width: 720px;
        margin: 40px auto;
        padding: 40px 32px;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 14px;
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.06), rgba(139, 92, 246, 0.05));
        border: 1px solid rgba(59, 130, 246, 0.25);
        border-radius: 16px;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }

    .insufficient-icon {
        font-size: 3rem;
        opacity: 0.9;
    }

    .insufficient-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: var(--text-primary);
        margin: 0;
        text-align: center;
    }

    .insufficient-message {
        font-size: 0.98rem;
        color: var(--text-secondary);
        text-align: center;
        line-height: 1.65;
        margin: 0;
    }

    .insufficient-meta {
        width: 100%;
        padding: 12px 14px;
        background: rgba(255, 255, 255, 0.55);
        border: 1px solid rgba(59, 130, 246, 0.15);
        border-radius: 10px;
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    :global([data-theme="dark"]) .insufficient-meta {
        background: rgba(30, 41, 59, 0.5);
    }

    .meta-row {
        display: flex;
        gap: 10px;
        font-size: 0.9rem;
        color: var(--text-secondary);
    }

    .meta-label {
        flex: 0 0 48px;
        font-weight: 700;
        color: var(--primary-color, #4f46e5);
    }

    .meta-row strong {
        color: var(--text-primary);
    }

    .insufficient-guidance {
        margin: 0;
        padding-left: 20px;
        font-size: 0.88rem;
        color: var(--text-secondary);
        line-height: 1.7;
        align-self: stretch;
    }

    .insufficient-guidance li {
        margin-bottom: 4px;
    }

    .back-btn {
        margin-top: 8px;
        padding: 9px 20px;
        background: var(--primary-color, #4f46e5);
        color: #fff;
        border: none;
        border-radius: 999px;
        font-size: 0.9rem;
        font-weight: 600;
        cursor: pointer;
        transition: opacity 0.15s;
    }

    .back-btn:hover {
        opacity: 0.88;
    }

    .station-details {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin: 16px 0;
    }

    .detail-item {
        display: flex;
        flex-direction: column;
        padding: 12px;
        background: var(--neutral-light);
        border-radius: 8px;
        border-left: 4px solid var(--primary-color);
        transition: background-color 0.3s ease;
    }

    .detail-label {
        font-size: 0.9em;
        color: var(--text-secondary);
        margin-bottom: 4px;
        font-weight: 500;
    }

    .detail-value {
        font-size: 1.1em;
        color: var(--primary-color);
        font-weight: 600;
    }

    /* Base styles for mobile-first approach */
    .container {
        padding: 16px;
        max-width: 100%;
        margin: 0 auto;
    }

    .header {
        margin-bottom: 32px;
        padding: 24px;
        background: var(--gradient-primary);
        color: white;
        border-radius: 20px;
        box-shadow: 0 8px 32px var(--shadow-hover);
    }

    .header-content {
        display: flex;
        flex-direction: column;
        gap: 24px;
    }

    .navigation-section {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 16px;
    }

    .breadcrumb {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.9em;
    }

    .breadcrumb-item {
        display: flex;
        align-items: center;
        gap: 6px;
        color: rgba(255, 255, 255, 0.8);
        text-decoration: none;
        padding: 6px 12px;
        border-radius: 8px;
        transition: all 0.3s ease;
    }

    .breadcrumb-item:hover {
        color: white;
        background: rgba(255, 255, 255, 0.15);
        transform: translateY(-1px);
    }

    .breadcrumb-current {
        display: flex;
        align-items: center;
        gap: 6px;
        color: white;
        font-weight: 600;
        padding: 6px 12px;
        background: rgba(255, 255, 255, 0.15);
        border-radius: 8px;
    }

    .breadcrumb-icon {
        width: 16px;
        height: 16px;
        stroke-width: 2;
    }

    .breadcrumb-separator {
        width: 16px;
        height: 16px;
        stroke-width: 2;
        color: rgba(255, 255, 255, 0.5);
    }

    .btn-back-enhanced {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 16px;
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.25);
        color: white;
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.3s ease;
        font-size: 0.9em;
        backdrop-filter: blur(10px);
    }

    .btn-back-enhanced:hover {
        background: rgba(255, 255, 255, 0.25);
        border-color: rgba(255, 255, 255, 0.4);
        transform: translateY(-2px);
        box-shadow: 0 4px 20px var(--shadow-hover);
    }

    .back-arrow {
        width: 18px;
        height: 18px;
        stroke-width: 2;
        transition: transform 0.3s ease;
    }

    .btn-back-enhanced:hover .back-arrow {
        transform: translateX(-3px);
    }

    .btn-back-content {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
    }

    .btn-back-text {
        font-weight: 600;
        line-height: 1;
    }

    .btn-back-hint {
        font-size: 0.75em;
        opacity: 0.7;
        font-weight: 400;
    }
    
    /* 툴팁 스타일 */
    .info-tooltip {
        position: relative;
        display: inline-block;
        margin-left: 4px;
    }
    
    .info-icon {
        width: 16px;
        height: 16px;
        color: var(--primary-color, #4f46e5);
        cursor: help;
        transition: all 0.2s ease;
        opacity: 0.6;
        flex-shrink: 0;
        border-radius: 50%;
        background: rgba(79, 70, 229, 0.1);
        border: 1px solid rgba(79, 70, 229, 0.2);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        line-height: 1;
    }
    
    .info-icon:hover {
        color: white;
        opacity: 1;
        transform: scale(1.1);
        background: var(--primary-color, #4f46e5);
        border-color: var(--primary-color, #4f46e5);
    }
    
    .tooltip-content {
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 12px;
        box-shadow: 0 4px 20px var(--shadow);
        opacity: 0;
        visibility: hidden;
        transition: all 0.3s ease;
        z-index: 1000;
        min-width: 200px;
        max-width: 280px;
        white-space: nowrap;
    }
    
    .info-tooltip:hover .tooltip-content {
        opacity: 1;
        visibility: visible;
        transform: translateX(-50%) translateY(-8px);
    }
    
    .tooltip-formula {
        margin-bottom: 6px;
        line-height: 1.3;
    }
    
    .capacity-examples {
        font-style: italic;
        color: var(--text-muted);
        font-size: 11px;
        line-height: 1.2;
    }

    .header-title {
        text-align: center;
        flex: 1;
    }

    .header-title h1 {
        margin: 0 0 8px 0;
        font-size: 2em;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
    }

    .header-subtitle {
        margin: 0;
        font-size: 1em;
        opacity: 0.9;
        font-weight: 400;
    }

    .header-actions {
        display: flex;
        align-items: center;
    }

    .quick-actions {
        display: flex;
        gap: 8px;
    }

    .header-action-btn {
        width: 40px;
        height: 40px;
        border: none;
        background: rgba(255, 255, 255, 0.15);
        color: white;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }

    .header-action-btn:hover {
        background: rgba(255, 255, 255, 0.25);
        transform: translateY(-2px);
        box-shadow: 0 4px 15px var(--shadow);
    }

    .header-action-btn svg {
        width: 20px;
        height: 20px;
        stroke-width: 2;
    }

    /* 테마 토글 버튼 특별 스타일 */
    .header-action-btn.theme-toggle:hover {
        background: rgba(255, 255, 255, 0.3);
        box-shadow: 0 4px 20px rgba(255, 255, 255, 0.1);
    }

    .theme-toggle svg {
        transition: all 0.3s ease;
    }

    .theme-toggle:hover svg {
        transform: rotate(180deg);
    }


    .station-info {
        background: var(--bg-secondary);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 24px;
        box-shadow: 0 2px 8px var(--shadow);
        border: 1px solid var(--border-color);
        transition:
            background-color 0.3s ease,
            border-color 0.3s ease;
    }

    .station-info h2 {
        margin: 0 0 16px 0;
        font-size: 1.4em;
        color: var(--primary-color);
    }

    .station-details {
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
        margin: 16px 0;
    }

    .station-location {
        margin: 16px 0 0 0;
        color: var(--text-secondary);
        font-size: 1em;
    }


</style>
