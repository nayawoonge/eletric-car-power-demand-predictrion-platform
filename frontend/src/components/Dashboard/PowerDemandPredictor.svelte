<script>
    import { onMount, onDestroy } from "svelte";
    import MetricCard from "./MetricCard.svelte";
    import LoadingSpinner from "../LoadingSpinner.svelte";

    export let stationId;
    export let analysis = null;

    let isLoading = false;
    let lastUpdated = null;
    let energyForecast = null;
    let selectedTimeframe = "90days";
    let chartContainer;

    let predictionRequested = false;
    let hasForecast = false;
    let chartModulesReady = false;
    let needsChartRender = false;
    let errorMessage = "";
    let currentStationId = null;

    const defaultDataRange = {
        startDate: null,
        endDate: null,
        recordCount: 0,
    };
    let dataRange = { ...defaultDataRange };

    const timeframes = [
        { value: "30days", label: "30일" },
        { value: "90days", label: "90일" },
        { value: "180days", label: "6개월" },
        { value: "365days", label: "1년" },
    ];

    let Chart;
    let chart; // 차트 인스턴스

    function resetForecastState() {
        energyForecast = null;
        dataRange = { ...defaultDataRange };
        hasForecast = false;
        predictionRequested = false;
        errorMessage = "";
        lastUpdated = null;
        needsChartRender = false;
        if (chart) {
            chart.destroy();
            chart = null;
        }
    }

    onMount(async () => {
        if (typeof window === "undefined") return;

        try {
            const [{ default: ChartJS }, dateAdapter, zoomPlugin] =
                await Promise.all([
                    import("chart.js/auto"),
                    import("chartjs-adapter-date-fns"),
                    import("chartjs-plugin-zoom"),
                ]);
            Chart = ChartJS;
            Chart.register(zoomPlugin.default);
            chartModulesReady = true;

            if (energyForecast?.daily_consumption?.length) {
                needsChartRender = true;
            }
        } catch (error) {
            console.error("PowerDemandPredictor: Chart.js 로드 실패", error);
        }
    });

    onDestroy(() => {
        try {
            if (chart) {
                chart.destroy();
                chart = null;
            }
        } catch (error) {}
    });

    $: if (stationId && stationId !== currentStationId) {
        currentStationId = stationId;
        resetForecastState();
    }

    $: if (
        chartModulesReady &&
        needsChartRender &&
        chartContainer &&
        energyForecast?.daily_consumption?.length
    ) {
        needsChartRender = false;
        createChart();
    }

    async function handlePredictClick() {
        if (isLoading || !stationId) return;
        predictionRequested = true;
        errorMessage = "";
        try {
            await loadEnergyForecast();
        } catch (error) {
            errorMessage = error?.message || "전력량 예측 실행에 실패했습니다.";
        }
    }

    async function handleTimeframeChange() {
        if (!predictionRequested || isLoading || !stationId) return;
        errorMessage = "";
        try {
            await loadEnergyForecast();
        } catch (error) {
            errorMessage = error?.message || "전력량 예측 실행에 실패했습니다.";
        }
    }

    async function loadEnergyForecast() {
        if (!stationId) {
            console.log('PowerDemandPredictor: stationId가 없습니다');
            return;
        }

        isLoading = true;

        try {
            const days = parseInt(selectedTimeframe.replace("days", ""));
            const url = `/api/stations/${encodeURIComponent(stationId)}/energy-demand-forecast?days=${days}`;
            console.log('📡 API 호출 URL:', url);

            const response = await fetch(url, {
                cache: "no-cache",
                signal: AbortSignal.timeout(15000),
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error(`API 호출 실패: ${response.status} ${response.statusText}`, errorText);
                throw new Error(
                    `API 호출 실패: ${response.status} ${response.statusText}`
                );
            }

            const result = await response.json();
            console.log('API 응답:', result);
            console.log('에너지 통계:', result?.energy_statistics);

            console.log('API 응답 전체:', result);
            console.log('result.success:', result.success);
            console.log('result.timeseries_data:', result.timeseries_data?.length);

            if (result.success && result.timeseries_data) {
                energyForecast = {
                    daily_consumption: result.timeseries_data,
                    energy_statistics: result.energy_statistics,
                    monthly_summary: result.monthly_summary,
                    insights: result.insights,
                    growth_rate: result.growth_rate
                };
                console.log('🎯 energyForecast 생성됨:', energyForecast);
                console.log('🎯 daily_consumption 길이:', energyForecast.daily_consumption.length);

                console.log('✅ energyForecast 설정 완료');
                console.log('📊 데이터 개수:', energyForecast.daily_consumption.length, '개');
                console.log('📈 에너지 통계:', energyForecast.energy_statistics);

                // 실제 데이터 범위 설정
                dataRange = {
                    startDate: new Date(result.data_range.start_date),
                    endDate: new Date(result.data_range.end_date),
                    recordCount: result.timeseries_data.length,
                };
                
                lastUpdated = new Date();
                hasForecast = true;
                needsChartRender = true;
            } else {
                throw new Error(result.error || "에너지 예측 실패");
            }
        } catch (error) {
            console.error('Energy forecast 데이터 로드 실패:', error);
            energyForecast = null;
            dataRange = { ...defaultDataRange };
            hasForecast = false;
            throw error;
        } finally {
            isLoading = false;
        }
    }

    function resetZoom() {
        if (typeof window !== 'undefined' && chart) {
            chart.resetZoom();
        }
    }

    // Reactive 데이터 변경 감지 -> 차트 업데이트
    $: if (
        typeof window !== 'undefined' &&
        energyForecast &&
        energyForecast.daily_consumption &&
        energyForecast.daily_consumption.length > 0 &&
        Chart &&
        chartContainer
    ) {
        console.log('🔄 차트 업데이트 조건 만족 - 차트 생성 시작');
        // DOM이 업데이트될 때까지 기다린 후 차트 생성/업데이트
        tick().then(() => {
            setTimeout(() => {
                console.log('📊 createChart() 호출');
                createChart();
            }, 100);
        });
    } else if (typeof window !== 'undefined') {
        console.log('❌ 차트 업데이트 조건 미충족:', {
            energyForecast: !!energyForecast,
            daily_consumption: !!energyForecast?.daily_consumption,
            daily_consumption_length: energyForecast?.daily_consumption?.length || 0,
            Chart: !!Chart,
            chartContainer: !!chartContainer
        });
    }

    function fmtDate(d) {
        if (!d) return "-";
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const da = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${da}`;
    }

    function createChart() {
        // 브라우저 환경 체크
        if (typeof window === 'undefined') return;
        
        if (!chartContainer || !Chart || !energyForecast?.daily_consumption) {
            console.log('차트 생성 실패: 요구사항 미충족', {
                chartContainer: !!chartContainer,
                Chart: !!Chart,
                daily_consumption: !!energyForecast?.daily_consumption
            });
            return;
        }

        // 기존 차트 파괴
        if (chart) {
            chart.destroy();
            chart = null;
        }

        try {
            const ctx = chartContainer.getContext("2d");
            
            if (!ctx) {
                console.error('캠버스 컨텍스트를 가져올 수 없습니다');
                return;
            }

            // 데이터 준비 및 검증
            const dailyData = energyForecast.daily_consumption;
            if (!dailyData || dailyData.length === 0) {
                console.log('차트 데이터가 비어있습니다');
                return;
            }

            const actualData = dailyData.filter(item => item.type === 'actual').map(item => ({
                x: item.date,
                y: parseFloat(item.energy) || 0,
            }));
            
            const predictedData = dailyData.filter(item => item.type === 'predicted').map(item => ({
                x: item.date,
                y: parseFloat(item.energy) || 0,
            }));
            
            console.log('실제 데이터:', actualData.slice(0, 3));
            console.log('예측 데이터:', predictedData.slice(0, 3));

            chart = new Chart(ctx, {
                type: "line",
                data: {
                    datasets: [
                        {
                            label: "실제 데이터 (kWh)",
                            data: actualData,
                            borderColor: "#2563eb",
                            backgroundColor: "rgba(37, 99, 235, 0.1)",
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            fill: false,
                            tension: 0.1,
                        },
                        {
                            label: "예측 데이터 (kWh)",
                            data: predictedData,
                            borderColor: "#f59e0b",
                            backgroundColor: "rgba(245, 158, 11, 0.1)",
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            fill: false,
                            tension: 0.1,
                            borderDash: [5, 5], // 점선으로 예측 데이터 표시
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: "index",
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                        },
                        tooltip: {
                            backgroundColor: "rgba(0,0,0,0.8)",
                            titleColor: "#fff",
                            bodyColor: "#fff",
                            borderColor: "#2563eb",
                            borderWidth: 1,
                            callbacks: {
                                label: function (context) {
                                    return `${context.parsed.y.toFixed(2)}kWh`;
                                },
                            },
                        },
                        zoom: {
                            pan: {
                                enabled: true,
                                mode: "x",
                            },
                            zoom: {
                                wheel: {
                                    enabled: true,
                                },
                                pinch: {
                                    enabled: true,
                                },
                                mode: "x",
                            },
                        },
                    },
                    scales: {
                        x: {
                            type: "time",
                            time: {
                                unit: "day",
                                displayFormats: {
                                    day: "MM/dd",
                                },
                            },
                            title: {
                                display: true,
                                text: "날짜",
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? '#e5e7eb' : '#374151',
                                font: { size: 14, weight: "bold" },
                            },
                            grid: { 
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0,0,0,0.1)' 
                            },
                            ticks: {
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? '#d1d5db' : '#4b5563',
                            },
                        },
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: "전력량 (kWh)",
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? '#e5e7eb' : '#374151',
                                font: { size: 14, weight: "bold" },
                            },
                            grid: { 
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0,0,0,0.1)' 
                            },
                            ticks: {
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? '#d1d5db' : '#4b5563',
                                callback: function (value) {
                                    return value + "kWh";
                                },
                            },
                        },
                    },
                },
            });
        } catch (error) {
            console.error("차트 생성 실패:", error);
        }
    }
    $: averageDailyEnergy = energyForecast?.energy_statistics?.avg_daily || 0;
    $: totalEnergy = energyForecast?.energy_statistics?.total_energy || 0;
    $: growthRate = energyForecast?.growth_rate || 0;
    $: averageDemand = analysis?.current_statistics?.avg_power || 0;
    $: peakDemand = analysis?.predictions?.peak_power || 0;
    
    // 전력량 예측 기간 설정 (사용자가 선택 가능)
    let energyForecastPeriod = "daily"; // daily, weekly, monthly
    const forecastPeriods = [
        { value: "daily", label: "일간", multiplier: 1 },
        { value: "weekly", label: "주간", multiplier: 7 },
        { value: "monthly", label: "월간", multiplier: 30 }
    ];

    // 예상 전력량 수요를 기간별로 계산 (kWh) - API 데이터 기반
    $: predictedEnergyDemand = (() => {
        if (!energyForecast?.energy_statistics) {
            console.log('❌ energy_statistics 없음');
            return 0;
        }

        const stats = energyForecast.energy_statistics;
        const avgDaily = stats.avg_daily || 0;
        const currentPeriod = forecastPeriods.find(p => p.value === energyForecastPeriod);
        
        console.log('📊 전력량 계산:', {
            avgDaily,
            currentPeriod,
            energyForecastPeriod
        });
        
        if (!currentPeriod || avgDaily === 0) {
            return 0;
        }

        // 기간별 예상 전력량 계산
        let baseEnergyDemand = avgDaily * currentPeriod.multiplier;
        
        // 성장률 반영 (향후 예측 조정)
        if (growthRate > 0) {
            baseEnergyDemand *= (1 + growthRate / 100 * 0.5); // 50% 가중치로 성장률 반영
        }
        
        // 계절성 요인 (현재 월 기준)
        const currentMonth = new Date().getMonth() + 1;
        let seasonalFactor = 1.0;
        
        if (currentMonth >= 6 && currentMonth <= 8) {
            // 여름철 (6-8월): 에어컨 사용으로 전력 수요 증가
            seasonalFactor = 1.15;
        } else if (currentMonth === 12 || currentMonth <= 2) {
            // 겨울철 (12-2월): 난방으로 전력 수요 증가
            seasonalFactor = 1.1;
        }
        
        const finalEnergyDemand = baseEnergyDemand * seasonalFactor;
        
        const result = Math.round(finalEnergyDemand * 10) / 10;
        console.log('💡 최종 예측 전력량:', result, 'kWh');
        return result;
    })();

    const MAX_INSIGHTS_PREVIEW = 5;
    let showAllInsights = false;

    $: insightsCount = energyForecast?.insights?.length || 0;
    $: visibleInsights = energyForecast?.insights
        ? showAllInsights
            ? energyForecast.insights
            : energyForecast.insights.slice(0, MAX_INSIGHTS_PREVIEW)
        : [];
</script>

<div class="demand-predictor">
    {#if !hasForecast}
        <div class="prediction-placeholder">
            <div class="placeholder-card">
                <div class="placeholder-icon">⚡</div>
                <h3>전력량 수요 예측을 시작하세요</h3>
                <p>예측하기 버튼을 눌러 충전소 {stationId}의 전력 사용 패턴을 분석합니다.</p>
                <button
                    class="predict-cta"
                    on:click={handlePredictClick}
                    disabled={!stationId || isLoading}
                >
                    {#if isLoading}
                        <LoadingSpinner size="small" />
                        <span>예측 중...</span>
                    {:else}
                        <span>{predictionRequested ? "다시 예측하기" : "예측하기"}</span>
                    {/if}
                </button>
                {#if errorMessage}
                    <div class="error-message">{errorMessage}</div>
                {:else if !predictionRequested}
                    <p class="placeholder-hint">버튼을 누르면 최근 1년 전력량 추이와 인사이트가 제공됩니다.</p>
                {/if}
            </div>
        </div>
    {:else}
        <div class="predict-toolbar">
            <div class="predict-meta">
                <span>충전소 {stationId}</span>
                {#if lastUpdated}
                    <span>마지막 예측: {lastUpdated.toLocaleTimeString()}</span>
                {/if}
            </div>
            <div class="toolbar-actions">
                <select
                    bind:value={selectedTimeframe}
                    class="timeframe-select-chart"
                    on:change={handleTimeframeChange}
                >
                    {#each timeframes as timeframe}
                        <option value={timeframe.value}>{timeframe.label}</option>
                    {/each}
                </select>
                <button
                    class="predict-cta compact"
                    on:click={handlePredictClick}
                    disabled={!stationId || isLoading}
                >
                    {#if isLoading}
                        <LoadingSpinner size="small" />
                        <span>예측 중...</span>
                    {:else}
                        <span>다시 예측하기</span>
                    {/if}
                </button>
            </div>
        </div>

        {#if errorMessage}
            <div class="error-message">{errorMessage}</div>
        {/if}

        <div class="forecast-period-selector">
            <div class="selector-header">
                <h3>전력량 수요 예측 기간</h3>
                <select bind:value={energyForecastPeriod} class="period-select">
                    {#each forecastPeriods as period}
                        <option value={period.value}>{period.label} 예측</option>
                    {/each}
                </select>
            </div>
        </div>

        <div class="metrics-row">
            <MetricCard
                title="일평균 소비 전력량"
                value={averageDailyEnergy}
                unit="kWh"
                type="energy"
                tooltip="선택된 기간 동안의 일일 평균 소비 전력량"
            />
            <MetricCard
                title="총 소비 전력량"
                value={totalEnergy}
                unit="kWh"
                type="total"
                tooltip="선택된 기간 동안의 총 소비 전력량"
            />
            <MetricCard
                title="증가율"
                value={growthRate}
                unit="%"
                type="growth"
                tooltip="전 기간 대비 소비 전력량 증가율"
            />
            <MetricCard
                title="예상 {forecastPeriods.find(p => p.value === energyForecastPeriod)?.label || '일간'} 전력량 수요"
                value={predictedEnergyDemand}
                unit="kWh"
                type={predictedEnergyDemand >= 200 ? "contract-high" : predictedEnergyDemand >= 100 ? "contract-medium" : "contract-low"}
                highlighted={true}
                tooltip="에너지 사용 패턴과 성장률을 기반으로 한 {forecastPeriods.find(p => p.value === energyForecastPeriod)?.label || '일간'} 전력량 예측"
            />
        </div>

        <div class="chart-container-wrapper">
            {#if isLoading}
                <div class="chart-loading">
                    <LoadingSpinner />
                    <p>에너지 데이터 로딩 중...</p>
                </div>
            {:else if energyForecast}
                <div class="chart-header">
                    <h3>일일 전력량 소비 추이</h3>
                    <div class="chart-meta">
                        {#if dataRange.startDate && dataRange.endDate}
                            <div class="data-info">
                                <div class="data-period">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M8 2v4"></path>
                                        <path d="M16 2v4"></path>
                                        <rect x="3" y="4" width="18" height="18" rx="2"></rect>
                                        <path d="M3 10h18"></path>
                                    </svg>
                                    <span>{dataRange.startDate.toLocaleDateString()} ~ {dataRange.endDate.toLocaleDateString()}</span>
                                </div>
                                <div class="data-stats">
                                    <span class="stat-badge">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <path d="M12 20V10"></path>
                                            <path d="M18 20V4"></path>
                                            <path d="M6 20v-6"></path>
                                        </svg>
                                        {dataRange.recordCount.toLocaleString()}개
                                    </span>
                                    <span class="duration-badge">
                                        {Math.ceil((dataRange.endDate - dataRange.startDate) / (1000 * 60 * 60 * 24))}일
                                    </span>
                                </div>
                            </div>
                        {:else}
                            <div class="no-data-info">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                                    <line x1="12" y1="9" x2="12" y2="13"></line>
                                    <line x1="12" y1="17" x2="12.01" y2="17"></line>
                                </svg>
                                <span>충전소 {stationId} 데이터 미발견</span>
                            </div>
                        {/if}
                        <div class="chart-controls">
                            <button class="zoom-reset-btn" on:click={resetZoom}>
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                    <path d="M3 3v18h18" />
                                    <path d="M18.5 9.5L12 16l-4-4-3.5 3.5" />
                                </svg>
                                원래대로
                            </button>
                        </div>
                    </div>
                </div>
                <div class="chart-container">
                    <canvas bind:this={chartContainer}></canvas>
                </div>
            {:else}
                <div class="no-chart-data">
                    <div class="no-data-icon">📉</div>
                    <h4>차트 데이터 없음</h4>
                    <p>에너지 소비 데이터를 불러올 수 없습니다.</p>
                    <div class="data-check-info">
                        <p>다음 사항을 확인해주세요</p>
                        <ul>
                            <li>충전소 ID가 올바른지 확인</li>
                            <li>데이터 파일이 올바르게 업로드되었는지 확인</li>
                            <li>서버 연결 상태 확인</li>
                        </ul>
                    </div>
                </div>
            {/if}
        </div>

        {#if energyForecast && energyForecast.insights && energyForecast.insights.length > 0}
            <div class="insights-section">
                <div class="insights-header">
                    <span class="insights-icon">💡</span>
                    <h3 class="insights-title">인사이트</h3>
                </div>
                <div class="insights-list">
                    {#each visibleInsights as insight, index}
                        <div
                            class="insight-item"
                            style="--delay: {index * 0.1}s"
                        >
                            <span class="insight-bullet">•</span>
                            <span class="insight-text">{insight}</span>
                        </div>
                    {/each}
                    {#if insightsCount > MAX_INSIGHTS_PREVIEW}
                        <button
                            class="show-more-btn"
                            on:click={() => (showAllInsights = !showAllInsights)}
                        >
                            {#if showAllInsights}간단히 보기{/if}
                            {#if !showAllInsights}더 보기 (+{insightsCount -
                                    MAX_INSIGHTS_PREVIEW}){/if}
                        </button>
                    {/if}
                </div>
            </div>
        {/if}

        {#if energyForecast && energyForecast.monthly_summary && energyForecast.monthly_summary.length > 0}
            <div class="monthly-summary">
                <h3>월별 에너지 소비</h3>
                <div class="monthly-grid">
                    {#each energyForecast.monthly_summary.slice(-6) as month}
                        <div class="month-card">
                            <div class="month-label">{month.month_label}</div>
                            <div class="month-total">
                                {month.total_energy.toFixed(1)}kWh
                            </div>
                            <div class="month-avg">
                                일평균: {month.avg_daily.toFixed(1)}kWh
                            </div>
                            <div class="month-days">{month.active_days}일 활동</div>
                        </div>
                    {/each}
                </div>
            </div>
        {/if}
    {/if}
</div>

<style>
    /* Mobile-first base styles */
    .demand-predictor {
        background: transparent;
        border-radius: 0;
        padding: 24px;
        border: none;
        box-shadow: none;
        transition: all 0.3s ease;
    }

    /* 전력량 예측 기간 선택기 */
    .forecast-period-selector {
        margin-bottom: 24px;
        padding: 16px 20px;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        box-shadow: 0 2px 8px var(--shadow);
    }

    .prediction-placeholder {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 320px;
        padding: 32px;
        background: var(--bg-secondary);
        border: 1px dashed var(--border-color);
        border-radius: 16px;
        box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.03);
    }

    .placeholder-card {
        text-align: center;
        max-width: 420px;
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    .placeholder-icon {
        font-size: 2.6rem;
        color: var(--primary-color);
    }

    .placeholder-card h3 {
        margin: 0;
        font-size: 1.2rem;
        color: var(--text-primary);
    }

    .placeholder-card p {
        margin: 0;
        color: var(--text-secondary);
        line-height: 1.5;
    }

    .placeholder-hint {
        font-size: 0.9rem;
        color: var(--text-secondary);
    }

    .predict-cta {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 12px 24px;
        border-radius: 999px;
        font-size: 1rem;
        font-weight: 600;
        border: none;
        cursor: pointer;
        background: var(--primary-color);
        color: #fff;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        box-shadow: 0 6px 20px rgba(79, 70, 229, 0.25);
    }

    .predict-cta.compact {
        padding: 10px 18px;
        font-size: 0.95rem;
        border-radius: 12px;
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.18);
    }

    .predict-cta:disabled {
        background: var(--border-color);
        cursor: not-allowed;
        box-shadow: none;
    }

    .predict-cta:not(:disabled):hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 22px rgba(79, 70, 229, 0.35);
    }

    .predict-toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        padding: 16px 20px;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 14px;
        box-shadow: 0 4px 12px var(--shadow);
        flex-wrap: wrap;
        margin-bottom: 20px;
    }

    .predict-meta {
        display: flex;
        gap: 12px;
        font-size: 0.95rem;
        color: var(--text-secondary);
        flex-wrap: wrap;
    }

    .toolbar-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }

    .error-message {
        margin-top: 4px;
        padding: 8px 12px;
        background: rgba(239, 68, 68, 0.08);
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 8px;
        color: #dc2626;
        font-size: 0.9rem;
        line-height: 1.4;
    }

    .selector-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
    }

    .selector-header h3 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .period-select {
        padding: 8px 16px;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        min-width: 120px;
    }

    .period-select:hover {
        border-color: var(--primary-color);
        box-shadow: 0 2px 8px var(--shadow);
    }

    .period-select:focus {
        outline: none;
        border-color: var(--primary-color);
        box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.1);
    }




    .metrics-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
        margin-bottom: 24px;
    }

    .chart-container {
        height: 350px;
        width: 100%;
        position: relative;
    }

    .insights-section {
        margin: 32px 0;
        padding: 0;
    }

    .insights-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 24px;
        padding-bottom: 12px;
        border-bottom: 2px solid var(--border-color);
    }

    .insights-icon {
        font-size: 1.5em;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
    }

    .insights-title {
        margin: 0;
        color: var(--text-primary);
        font-size: 1.5em;
        font-weight: 600;
        letter-spacing: -0.025em;
    }

    .insights-list {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    .insight-item {
        display: flex;
        align-items: flex-start;
        gap: 16px;
        padding: 4px 0;
        opacity: 0;
        animation: fadeInUp 0.6s ease forwards;
        animation-delay: var(--delay);
    }

    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .insight-bullet {
        color: var(--primary-color);
        font-weight: bold;
        font-size: 1.2em;
        line-height: 1.5;
        flex-shrink: 0;
        margin-top: -2px;
    }

    .insight-text {
        color: var(--text-primary);
        font-size: 1em;
        line-height: 1.6;
        font-weight: 400;
    }

    .show-more-btn {
        align-self: flex-start;
        padding: 8px 16px;
        background: transparent;
        border: 1px solid var(--primary-color);
        color: var(--primary-color);
        border-radius: 6px;
        font-size: 0.9em;
        font-weight: 500;
        cursor: pointer;
        transition:
            background-color 0.2s ease,
            color 0.2s ease,
            transform 0.2s ease;
        margin-top: 8px;
    }

    .show-more-btn:hover {
        background: var(--primary-color);
        color: white;
        transform: translateY(-1px);
    }

    .monthly-summary {
        margin: 32px 0;
        padding: 24px;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        box-shadow: 0 2px 8px var(--shadow);
    }

    .monthly-summary h3 {
        margin: 0 0 20px 0;
        color: var(--text-primary);
        font-size: 1.2em;
        font-weight: 700;
    }

    .monthly-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 16px;
    }

    .month-card {
        background: var(--neutral-light);
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        border: 1px solid var(--border-color);
        transition:
            transform 0.2s ease,
            box-shadow 0.2s ease;
    }

    .month-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 20px var(--shadow);
    }

    .month-label {
        font-size: 0.9em;
        color: var(--text-muted);
        font-weight: 600;
        margin-bottom: 8px;
    }

    .month-total {
        font-size: 1.4em;
        font-weight: 700;
        color: var(--primary-color);
        margin-bottom: 4px;
    }

    .month-avg {
        font-size: 0.8em;
        color: var(--text-secondary);
        margin-bottom: 2px;
    }

    .month-days {
        font-size: 0.75em;
        color: var(--text-muted);
    }

    .no-chart-data {
        display: grid;
        place-items: center;
        padding: 60px 24px;
        text-align: center;
        min-height: 300px;
    }

    .no-chart-data .no-data-icon {
        font-size: 2.5em;
        margin-bottom: 12px;
        opacity: 0.6;
    }

    .no-chart-data h4 {
        margin: 0 0 8px 0;
        color: var(--text-primary);
        font-size: 1.1em;
        font-weight: 600;
    }

    .no-chart-data p {
        margin: 0;
        color: var(--text-secondary);
        font-size: 0.9em;
        line-height: 1.4;
    }

    .data-check-info {
        background: var(--bg-secondary);
        border-radius: 8px;
        padding: 16px;
        text-align: left;
        margin-top: 20px;
    }

    .data-check-info p {
        margin: 0 0 8px 0;
        font-weight: 600;
        color: var(--text-primary);
    }

    .data-check-info ul {
        margin: 0;
        padding-left: 20px;
        color: var(--text-secondary);
    }

    .data-check-info li {
        margin-bottom: 4px;
        font-size: 0.9em;
    }

    .chart-loading {
        text-align: center;
        padding: 60px 20px;
        color: var(--text-secondary);
    }

    .chart-loading p {
        margin-top: 16px;
        font-size: 1.1em;
    }

    .chart-container-wrapper {
        margin-bottom: 24px;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 8px var(--shadow);
    }

    .chart-header {
        display: flex;
        flex-direction: column;
        gap: 12px;
        margin-bottom: 16px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--border-color);
    }

    .chart-header h3 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .chart-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }

    .data-info {
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
    }

    .data-period {
        display: flex;
        align-items: center;
        gap: 6px;
        color: var(--text-primary);
        font-size: 0.9rem;
    }

    .data-stats {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .stat-badge, .duration-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 500;
    }

    .stat-badge {
        background: rgba(16, 185, 129, 0.1);
        color: #059669;
        border: 1px solid rgba(16, 185, 129, 0.2);
    }

    .duration-badge {
        background: rgba(99, 102, 241, 0.1);
        color: #4f46e5;
        border: 1px solid rgba(99, 102, 241, 0.2);
    }

    .no-data-info {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #f59e0b;
        font-size: 0.9rem;
        font-weight: 500;
    }

    .chart-controls {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .timeframe-select-chart {
        padding: 6px 12px;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.85rem;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .timeframe-select-chart:hover {
        border-color: var(--primary-color);
        box-shadow: 0 2px 4px var(--shadow);
    }

    .timeframe-select-chart:focus {
        outline: none;
        border-color: var(--primary-color);
        box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.1);
    }


    .zoom-reset-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 12px;
        background: var(--primary-color);
        color: white;
        border: none;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .zoom-reset-btn:hover {
        background: var(--primary-dark);
        transform: translateY(-1px);
        box-shadow: 0 2px 8px var(--shadow);
    }

    .zoom-reset-btn svg {
        width: 16px;
        height: 16px;
    }

    /* 태블릿 반응형 */
    @media (min-width: 768px) {
        .chart-container {
            height: 450px;
        }

        .monthly-grid {
            grid-template-columns: repeat(3, 1fr);
        }
    }

    /* 데스크톱 반응형 */
    @media (min-width: 1024px) {
        .chart-container {
            height: 500px;
        }

        .monthly-grid {
            grid-template-columns: repeat(6, 1fr);
        }
    }

    /* Large Desktop Layout */
    @media (min-width: 1440px) {
        .demand-predictor {
            padding: 48px;
        }
    }

    @media (max-width: 768px) {
        .selector-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 12px;
        }

        .period-select {
            width: 100%;
            min-width: unset;
        }

        .chart-meta {
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
        }

        .data-info {
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
        }

        .data-stats {
            gap: 6px;
        }

        .stat-badge, .duration-badge {
            padding: 3px 6px;
            font-size: 0.75rem;
        }

        .predict-toolbar {
            flex-direction: column;
            align-items: flex-start;
        }
    }
</style>