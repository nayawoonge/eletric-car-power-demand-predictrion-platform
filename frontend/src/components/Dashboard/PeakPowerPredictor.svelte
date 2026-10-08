<script>
    import { onMount, onDestroy } from "svelte";
    import MetricCard from "./MetricCard.svelte";
    import LoadingSpinner from "../LoadingSpinner.svelte";

    // Chart.js는 클라이언트에서만 동적 로드
    let Chart;
    let chartCanvas;
    let chartInstance = null;

    export let stationId;
    export let monthlyContract = null;

    let isLoading = false;
    let lastUpdated = null;
    let predictionRequested = false;
    let hasPrediction = false;
    let chartModulesReady = false;
    let needsChartRender = false;
    let errorMessage = "";
    let currentStationId = null;

    const defaultMetrics = {
        lastMonthPeak: 0,
        nextMonthRecommended: 0,
        confidence: 0,
        algorithmPrediction: 0,
        predictionExceedsLimit: false,
    };

    const defaultDataInfo = {
        startDate: null,
        endDate: null,
        recordCount: 0,
    };

    // UI 상태 변수 - 백엔드에서 전처리된 데이터만 저장
    let chartData = [];
    let metrics = { ...defaultMetrics };
    let dataInfo = { ...defaultDataInfo };

    // 고급 모델 예측 결과
    // Method comparison 및 고급 모델 UI는 현재 비활성화 상태

    $: if (stationId && stationId !== currentStationId) {
        currentStationId = stationId;
        resetPredictionState();
    }

    $: if (chartModulesReady && needsChartRender && chartCanvas) {
        needsChartRender = false;
        createChart();
    }

    function resetPredictionState() {
        chartData = [];
        metrics = { ...defaultMetrics };
        dataInfo = { ...defaultDataInfo };
        needsChartRender = false;
        hasPrediction = false;
        predictionRequested = false;
        errorMessage = "";
        lastUpdated = null;
        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
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

            if (chartData.length) {
                needsChartRender = true;
            }
        } catch (error) {
            console.error("Chart.js 로드 실패:", error);
        }
    });

    onDestroy(() => {
        if (chartInstance) {
            chartInstance.destroy();
        }
    });

    async function handlePredictClick() {
        if (isLoading || !stationId) return;
        predictionRequested = true;
        errorMessage = "";
        try {
            await loadAll();
        } catch (err) {
            errorMessage = err?.message || "예측 실행에 실패했습니다.";
        }
    }

    async function loadAll() {
        if (!stationId) {
            return;
        }

        isLoading = true;
        try {
            // 단일 API 호출로 모든 전처리된 데이터를 받음
            const response = await fetch(
                `/api/stations/${encodeURIComponent(stationId)}/prediction`,
                {
                    cache: "no-cache",
                    signal: AbortSignal.timeout(15000),
                }
            );

            if (!response.ok) {
                throw new Error(`API 호출 실패: ${response.status}`);
            }

            const result = await response.json();

            if (result.success) {
                // 백엔드에서 전처리된 데이터 직접 사용
                chartData = result.chart_data || [];

                // 고급 예측 모델 결과 처리
                if (result.advanced_model_prediction) {
                    const advModel = result.advanced_model_prediction;
                    let rawPrediction = advModel.raw_prediction || 0; // 알고리즘 원본 예측값

                    // 비정상적으로 큰 값이면 단위 변환 (와트 → 킬로와트)
                    if (rawPrediction > 100000) {
                        console.warn(
                            "비정상적으로 큰 예측값 감지:",
                            rawPrediction,
                            "-> kW로 변환"
                        );
                        rawPrediction = rawPrediction / 1000;
                    }

                    // 여전히 비정상적으로 크면 제한
                    if (rawPrediction > 10000) {
                        console.warn(
                            "여전히 비정상적으로 큰 값:",
                            rawPrediction,
                            "-> 10000kW로 제한"
                        );
                        rawPrediction = 10000;
                    }
                    const finalPrediction = advModel.final_prediction || 0; // 제한 적용된 권고값

                    console.log("PeakPowerPredictor - API 원본 데이터:", {
                        rawPrediction,
                        finalPrediction,
                        advModel,
                    });

                    // 제한 초과 여부 계산
                    const predictionExceedsLimit =
                        rawPrediction > finalPrediction;

                    metrics = {
                        lastMonthPeak: parseFloat(
                            (
                                result.last_month_peak ||
                                result.current_peak ||
                                0
                            ).toFixed(1)
                        ),
                        nextMonthRecommended: parseFloat(
                            finalPrediction.toFixed(1)
                        ), // 소수점 1자리
                        confidence: Math.max(
                            0,
                            Math.min(1, result.confidence || 0)
                        ),
                        algorithmPrediction: parseFloat(
                            rawPrediction.toFixed(1)
                        ), // 소수점 1자리
                        predictionExceedsLimit: predictionExceedsLimit,
                    };

                    console.log("PeakPowerPredictor - 계산된 메트릭:", {
                        originalRawPrediction: rawPrediction,
                        roundedAlgorithmPrediction: Math.round(rawPrediction),
                        finalMetrics: metrics,
                    });

                    // 고급 모델 예측 결과 저장
                } else {
                    // 고급 모델이 없는 경우 기존 방식 사용
                    const contractRecommendation =
                        monthlyContract?.recommended_contract_kw ||
                        result.recommended_contract_kw ||
                        0;
                    const algorithmPrediction = Math.min(
                        result.algorithm_prediction_kw ||
                            contractRecommendation,
                        10000
                    ); // 최대 10000kW 제한

                    metrics = {
                        lastMonthPeak: Math.round(
                            result.last_month_peak || result.current_peak || 0
                        ),
                        nextMonthRecommended: Math.round(
                            contractRecommendation
                        ),
                        confidence: Math.max(
                            0,
                            Math.min(1, result.confidence || 0)
                        ),
                        algorithmPrediction: Math.round(
                            Math.min(algorithmPrediction, 10000)
                        ),
                        predictionExceedsLimit:
                            result.prediction_exceeds_limit || false,
                    };
                }
                dataInfo = {
                    startDate: result.data_start_date
                        ? new Date(result.data_start_date)
                        : null,
                    endDate: result.data_end_date
                        ? new Date(result.data_end_date)
                        : null,
                    recordCount: result.record_count || 0,
                };

                // 차트 렌더링 예약
                needsChartRender = true;
            } else {
                throw new Error(result.error || "데이터 로드 실패");
            }
            hasPrediction = true;
        } catch (e) {
            // 오류 시 기본값 설정
            chartData = [];
            metrics = { ...defaultMetrics };
            dataInfo = { ...defaultDataInfo };
            hasPrediction = false;
            throw e;
        } finally {
            isLoading = false;
            lastUpdated = new Date();
        }
    }

    function resetZoom() {
        if (chartInstance) {
            chartInstance.resetZoom();
        }
    }

    function createChart() {
        // 브라우저 환경 체크
        if (typeof window === "undefined" || !Chart) return;

        if (!chartCanvas) {
            return;
        }

        // Canvas 크기 확인
        const rect = chartCanvas.getBoundingClientRect();

        // 기존 차트 파괴
        if (chartInstance) {
            chartInstance.destroy();
        }

        // 데이터가 없으면 차트 생성하지 않음
        if (!chartData.length) {
            return;
        }

        const ctx = chartCanvas.getContext("2d");

        // 날짜 변환 헬퍼 함수
        const convertToYearMonth = (dateStr) => {
            if (!dateStr) return null;
            if (dateStr.includes(".")) {
                const [year, month] = dateStr.split(".");
                const fullYear = year.length === 2 ? `20${year}` : year;
                return `${fullYear}-${month.padStart(2, "0")}`;
            } else if (dateStr.includes("-") && dateStr.length >= 7) {
                return dateStr.substring(0, 7);
            }
            return dateStr;
        };

        const actualData = chartData
            .filter((d) => d && d.actual !== null && !isNaN(d.actual))
            .map((d) => {
                const xValue = convertToYearMonth(d.month || d.label);
                return {
                    x: xValue,
                    y: Number(d.actual),
                };
            })
            .filter((d) => d.x);

        const actualDataSorted = [...actualData].sort((a, b) =>
            a.x.localeCompare(b.x)
        );
        const lastActualMonth =
            actualDataSorted.length > 0
                ? actualDataSorted[actualDataSorted.length - 1].x
                : null;

        const predictedData = chartData
            .filter((d) => d && d.predicted !== null && !isNaN(d.predicted))
            .map((d) => {
                const xValue = convertToYearMonth(d.month || d.label);
                return {
                    x: xValue,
                    y: Number(d.predicted),
                };
            })
            .filter((d) => d.x && (!lastActualMonth || d.x > lastActualMonth));

        const allXValues = new Set();
        actualData.forEach((d) => allXValues.add(d.x));
        predictedData.forEach((d) => allXValues.add(d.x));

        const sortedXValues = Array.from(allXValues).sort();

        const datasets = [];

        if (actualData.length > 0) {
            datasets.push({
                label: "실제 데이터",
                data: actualData,
                borderColor: "#10b981",
                backgroundColor: "#10b981",
                borderWidth: 3,
                pointRadius: 5,
                pointHoverRadius: 7,
                fill: false,
                tension: 0.2,
                spanGaps: false,
            });
        }

        if (predictedData.length > 0) {
            datasets.push({
                label: "적응형 예측",
                data: predictedData,
                borderColor: "#3b82f6",
                backgroundColor: "rgba(59, 130, 246, 0.1)",
                borderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.2,
                borderDash: [5, 5],
                spanGaps: false,
            });
        }

        try {
            chartInstance = new Chart(ctx, {
                type: "line",
                data: {
                    datasets: datasets,
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
                            position: "top",
                            align: "end",
                            labels: {
                                usePointStyle: true,
                                padding: 20,
                                font: {
                                    size: 12,
                                },
                            },
                        },
                        tooltip: {
                            backgroundColor: "rgba(255, 255, 255, 0.95)",
                            titleColor: "#374151",
                            bodyColor: "#374151",
                            borderColor: "#d1d5db",
                            borderWidth: 1,
                            cornerRadius: 8,
                            padding: 12,
                            callbacks: {
                                title: function (context) {
                                    return `${context[0].label} 월`;
                                },
                                label: function (context) {
                                    return `${context.dataset.label}: ${context.parsed.y.toFixed(1)}kW`;
                                },
                            },
                        },
                        zoom: {
                            limits: {
                                x: { min: "original", max: "original" },
                                y: { min: "original", max: "original" },
                            },
                            pan: {
                                enabled: true,
                                mode: "xy",
                                onPanComplete({ chart }) {},
                            },
                            zoom: {
                                wheel: {
                                    enabled: true,
                                    speed: 0.1,
                                },
                                pinch: {
                                    enabled: true,
                                },
                                mode: "xy",
                                onZoomComplete({ chart }) {},
                            },
                        },
                    },
                    scales: {
                        x: {
                            type: "category",
                            labels: sortedXValues,
                            grid: {
                                color:
                                    document.documentElement.getAttribute(
                                        "data-theme"
                                    ) === "dark"
                                        ? "rgba(255, 255, 255, 0.05)"
                                        : "rgba(0, 0, 0, 0.1)",
                                drawBorder: false,
                            },
                            ticks: {
                                color:
                                    document.documentElement.getAttribute(
                                        "data-theme"
                                    ) === "dark"
                                        ? "#d1d5db"
                                        : "#4b5563",
                                font: {
                                    size: 11,
                                },
                                maxRotation: 45,
                                minRotation: 0,
                            },
                        },
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: "전력 (kW)",
                                color:
                                    document.documentElement.getAttribute(
                                        "data-theme"
                                    ) === "dark"
                                        ? "#e5e7eb"
                                        : "#374151",
                                font: {
                                    size: 14,
                                    weight: "bold",
                                },
                            },
                            grid: {
                                color:
                                    document.documentElement.getAttribute(
                                        "data-theme"
                                    ) === "dark"
                                        ? "rgba(255, 255, 255, 0.1)"
                                        : "rgba(0, 0, 0, 0.1)",
                                drawBorder: false,
                            },
                            ticks: {
                                color:
                                    document.documentElement.getAttribute(
                                        "data-theme"
                                    ) === "dark"
                                        ? "#d1d5db"
                                        : "#4b5563",
                                font: {
                                    size: 11,
                                },
                                callback: function (value) {
                                    return value + "kW";
                                },
                            },
                        },
                    },
                },
            });
        } catch (error) {}
    }

    // 유틸리티 함수 - UI 포맷팅만
    function fmtDate(d) {
        if (!d) return "-";
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const da = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${da}`;
    }
</script>

<div class="peak-predictor">
    {#if !hasPrediction}
        <div class="prediction-placeholder">
            <div class="placeholder-card">
                <div class="placeholder-icon">⚡</div>
                <h3>순간 최고 전력 예측을 시작하세요</h3>
                <p>예측하기 버튼을 눌러 충전소 {stationId}의 피크 전력과 권고 계약 전력을 계산합니다.</p>
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

        <div class="metrics-row">
            <MetricCard
                title="마지막달 최고 전력"
                value={metrics.lastMonthPeak}
                unit="kW"
                type="power"
                tooltip="지난 달 충전소에서 기록된 최대 순간 전력 사용량"
            />
            <MetricCard
                title="다음 달 권고계약 전력"
                value={metrics.nextMonthRecommended}
                unit="kW"
                type={metrics.nextMonthRecommended >= 80
                    ? "contract-high"
                    : metrics.nextMonthRecommended >= 50
                      ? "contract-medium"
                      : "contract-low"}
                highlighted={true}
                tooltip="알고리즘 예측값 + 안전마진으로 계산한 권고값

• 안전마진: 8-20% (데이터 품질에 따라 조정)
• 충전기별 권고 계약 전력 제한:
  - 완속충전기: 최대 7kW
  - 급속충전기: 최대 100kW"
            />
            <MetricCard
                title="예측 신뢰도"
                value={Math.round(metrics.confidence * 100)}
                unit="%"
                type="confidence"
                tooltip="예측 모델의 신뢰성 지표 (0-100%)

• 계산 요소: 데이터 품질, 모델 불확실성, 패턴 일관성
• 해석 기준:
  - 70% 이상: 높은 신뢰도
  - 50-70%: 보통 신뢰도  
  - 50% 미만: 낮은 신뢰도"
            />
            <MetricCard
                title="알고리즘 예측값"
                value={metrics.algorithmPrediction}
                unit="kW"
                type={metrics.algorithmPrediction > 100
                    ? "algorithm-exceeded"
                    : "algorithm"}
                subtitle={metrics.algorithmPrediction > 100
                    ? "100kW 제한 초과"
                    : "예측 범위 내"}
                tooltip="순수한 알고리즘 예측값

• 제한 없이 계산된 원시 예측 결과
• 100kW 초과 시 계약전력 제한 적용됨
• 실제 권고값은 충전기 타입별 제한 반영"
            />
        </div>

        <div class="chart-card">
            <div class="chart-header">
                <h3>월별 최대 순간최고전력 추이</h3>
                <div class="chart-meta">
                    {#if dataInfo.startDate && dataInfo.endDate}
                        <div class="data-info">
                            <div class="data-period">
                                <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="2"
                                >
                                    <path d="M8 2v4"></path>
                                    <path d="M16 2v4"></path>
                                    <rect x="3" y="4" width="18" height="18" rx="2"
                                    ></rect>
                                    <path d="M3 10h18"></path>
                                </svg>
                                <span
                                    >{fmtDate(dataInfo.startDate)} ~ {fmtDate(
                                        dataInfo.endDate
                                    )}</span
                                >
                            </div>
                            <div class="data-stats">
                                <span class="stat-badge">
                                    <svg
                                        width="12"
                                        height="12"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        stroke-width="2"
                                    >
                                        <path d="M12 20V10"></path>
                                        <path d="M18 20V4"></path>
                                        <path d="M6 20v-6"></path>
                                    </svg>
                                    {(dataInfo.recordCount || 0).toLocaleString()}개
                                </span>
                                <span class="duration-badge">
                                    {Math.ceil(
                                        (new Date(dataInfo.endDate) -
                                            new Date(dataInfo.startDate)) /
                                            (1000 * 60 * 60 * 24)
                                    )}일
                                </span>
                            </div>
                        </div>
                    {:else}
                        <div class="no-data-info">
                            <svg
                                width="16"
                                height="16"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                            >
                                <path
                                    d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
                                ></path>
                                <line x1="12" y1="9" x2="12" y2="13"></line>
                                <line x1="12" y1="17" x2="12.01" y2="17"></line>
                            </svg>
                            <span>충전소 {stationId} 데이터 불러올 수 없음</span>
                        </div>
                    {/if}
                    <div class="chart-controls">
                        <button
                            class="zoom-reset-btn"
                            on:click={resetZoom}
                            title="줌 초기화"
                        >
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                            >
                                <path d="M3 3v18h18" />
                                <path d="M18.5 9.5L12 16l-4-4-3.5 3.5" />
                            </svg>
                            원래대로
                        </button>
                    </div>
                </div>
            </div>
            <div class="chart-container">
                <canvas bind:this={chartCanvas}></canvas>
            </div>
            {#if isLoading}
                <div class="loading-placeholder">
                    <LoadingSpinner />
                    <p>차트 데이터 로딩 중...</p>
                </div>
            {:else if chartData.length === 0}
                <div class="no-chart-data">
                    <div class="no-data-icon">📊</div>
                    <h4>차트 데이터 없음</h4>
                    <p>해당 충전소({stationId})의 전력 사용 데이터를 불러올 수 없습니다.</p>
                </div>
            {/if}
        </div>
        {#if errorMessage}
            <div class="error-message">{errorMessage}</div>
        {/if}
    {/if}
</div>

<style>
    .peak-predictor {
        display: flex;
        flex-direction: column;
        gap: 24px;
        padding: 24px;
        background: transparent;
    }

    .metrics-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px;
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
    }

    .predict-toolbar .predict-meta {
        display: flex;
        gap: 12px;
        font-size: 0.95rem;
        color: var(--text-secondary);
        flex-wrap: wrap;
    }

    .chart-card {
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 2px 8px var(--shadow);
        min-height: 400px;
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

    .stat-badge,
    .duration-badge {
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
        gap: 8px;
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

    .chart-container {
        position: relative;
        height: 400px;
        width: 100%;
    }

    .loading-placeholder {
        display: grid;
        place-items: center;
        padding: 60px 24px;
        color: var(--text-secondary);
        font-size: 0.95rem;
        min-height: 300px;
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

    @media (min-width: 768px) {
        .chart-card {
            padding: 24px;
        }

        .chart-container {
            height: 450px;
        }
    }

    @media (max-width: 768px) {
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

        .stat-badge,
        .duration-badge {
            padding: 3px 6px;
            font-size: 0.75rem;
        }

        .predict-toolbar {
            flex-direction: column;
            align-items: flex-start;
        }
    }

    .error-message {
        margin-top: 8px;
        padding: 8px;
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.2);
        border-radius: 6px;
        font-size: 0.85rem;
        color: #dc2626;
        line-height: 1.4;
    }
</style>
