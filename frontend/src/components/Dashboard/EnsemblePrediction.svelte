<script lang="ts">
    import { onMount } from 'svelte';
    import { apiService } from '../../services/api';
    import type { EnsemblePredictionResponse } from '../../lib/types';
    import LoadingSpinner from '../LoadingSpinner.svelte';
    import ContractOptimizationChart from './ContractOptimizationChart.svelte';

    export let stationId: string;
    export let currentContractKw: number | undefined = undefined;

    let loading = false;
    let error = '';
    let errorCode = '';
    let errorGuidance: string[] = [];
    let errorDetails: {
        session_count?: number;
        unique_days?: number | null;
        min_required_sessions?: number;
        min_required_days?: number;
        data_coverage_start?: string | null;
        data_coverage_end?: string | null;
    } | null = null;
    let prediction: EnsemblePredictionResponse | null = null;
    let showDetails = false;
    let summaryHighlights: string[] = [];
    let riskSummary = '';
    const CONTRACT_MIN_KW = 30;
    const CONTRACT_MAX_KW = 150;
    const CONTRACT_STEP_KW = 10;
    const DEFAULT_CONTRACT_KW = 100;
    let lastUpdated: Date | null = null;
    // savingsBadges removed per user request

    let contractInputKw = clampContractKw(currentContractKw ?? DEFAULT_CONTRACT_KW);
    let previousPropContractKw = currentContractKw;

    function clampContractKw(value: number | null | undefined): number {
        if (!Number.isFinite(value ?? NaN)) {
            return CONTRACT_MIN_KW;
        }
        const clamped = Math.min(CONTRACT_MAX_KW, Math.max(CONTRACT_MIN_KW, Number(value)));
        const stepped = Math.round(clamped / CONTRACT_STEP_KW) * CONTRACT_STEP_KW;
        return Math.min(CONTRACT_MAX_KW, Math.max(CONTRACT_MIN_KW, stepped));
    }

    function handleContractNumberBlur() {
        contractInputKw = clampContractKw(contractInputKw);
    }

    $: if (currentContractKw !== previousPropContractKw) {
        previousPropContractKw = currentContractKw;
        if (currentContractKw !== undefined && currentContractKw !== null) {
            contractInputKw = clampContractKw(currentContractKw);
        }
    }

    // 페이지 마운트 시 DB 캐시에서 자동 로드 (모델은 다시 돌리지 않음).
    // 사용자가 "예측 실행" 버튼을 누르면 forceRefresh=true 로 재계산한다.
    onMount(() => {
        if (stationId) {
            loadEnsemblePrediction(false);
        }
    });

    // forceRefresh=false (기본/페이지 로드): DB 캐시에서 가져와 표시.
    // forceRefresh=true ("예측 실행" 버튼): 모델을 다시 돌려 DB를 갱신한 결과 표시.
    async function loadEnsemblePrediction(forceRefresh: boolean = false) {
        loading = true;
        error = '';
        errorCode = '';
        errorGuidance = [];
        errorDetails = null;
        const requestContractKw = clampContractKw(contractInputKw ?? DEFAULT_CONTRACT_KW);
        try {
            const result = await apiService.getEnsemblePrediction(
                stationId,
                requestContractKw,
                forceRefresh
            );

            if (result.success) {
                prediction = result;
                const resolvedContract = result.contract_recommendation?.current_contract_kw ?? requestContractKw;
                contractInputKw = clampContractKw(resolvedContract);
            } else {
                error = result.error || '예측 실패';
                errorCode = (result as any).error_code || '';
                errorGuidance = (result as any).guidance || [];
                errorDetails = (result as any).details || null;
            }
        } catch (e) {
            error = e instanceof Error ? e.message : '알 수 없는 오류';
            errorCode = 'INTERNAL_ERROR';
            console.error('Ensemble prediction error:', e);
        } finally {
            loading = false;
        }
    }

    function formatCurrency(value: number): string {
        return new Intl.NumberFormat('ko-KR', {
            style: 'currency',
            currency: 'KRW',
            maximumFractionDigits: 0
        }).format(value);
    }

    function formatKw(value: number, digits = 1): string {
        if (!isFinite(value)) {
            return '-';
        }
        return value.toFixed(digits);
    }

    function formatPercent(value: number, digits = 0): string {
        if (!isFinite(value)) {
            return '-';
        }
        const percentValue = Math.abs(value) <= 1 ? value * 100 : value;
        return `${percentValue.toFixed(digits)}%`;
    }

    function getUrgencyText(level: string): string {
        switch (level) {
            case 'high':
                return '지금 즉시 계약 전력 변경을 검토하는 것이 좋아요.';
            case 'medium':
                return '빠른 시일 내에 계약 전력을 점검해 보는 것을 추천해요.';
            case 'low':
                return '현재 계약이 크게 문제되지는 않지만 주기적인 확인을 권장해요.';
            default:
                return '계약 전력 검토가 필요해 보입니다.';
        }
    }

    function getMaturityLearningCopy(level: string, sessionCount: number): string {
        const formattedCount = sessionCount.toLocaleString();
        switch (level) {
            case 'mature':
                return `${formattedCount}개의 충전 세션을 바탕으로 안정적인 패턴까지 학습했어요.`;
            case 'developing':
                return `${formattedCount}개의 충전 세션으로 주요 패턴을 학습 중이에요.`;
            case 'new':
                return `${formattedCount}개의 충전 세션 데이터라 아직 변동성이 커요. 더 많은 데이터가 들어오면 정확도가 올라가요.`;
            default:
                return `${formattedCount}개의 충전 세션 데이터를 활용해 학습했어요.`;
        }
    }

    function buildSummaryHighlights(pred: EnsemblePredictionResponse): string[] {
        const items: string[] = [];
        items.push(
            getMaturityLearningCopy(
                pred.ensemble_prediction.maturity.level,
                pred.ensemble_prediction.maturity.session_count
            )
        );

        items.push(
            `예상 최고전력은 약 ${formatKw(pred.contract_recommendation.predicted_peak_p50)}kW(P50), ` +
            `보수적 상한은 약 ${formatKw(pred.contract_recommendation.predicted_peak_p95)}kW(P95)예요.`
        );

        const recommendedKw = pred.contract_recommendation.recommended_contract_kw;
        const currentKw = pred.contract_recommendation.current_contract_kw ?? null;
        const currentIsAdequate = currentKw !== null && Number(currentKw) === Number(recommendedKw);

        const opts = pred.contract_recommendation.recommendation_options;
        if (opts) {
            if (opts.same) {
                items.push(
                    `비용·안전 모두 ${formatKw(opts.cost_optimal.contract_kw, 0)}kW 계약을 추천해요 ` +
                    `(초과확률 ${opts.cost_optimal.overage_probability}%).`
                );
            } else {
                items.push(
                    `⚖️ 균형 최적안 ${formatKw(opts.cost_optimal.contract_kw, 0)}kW(초과 ${opts.cost_optimal.overage_probability}%) · ` +
                    `🛡️ 초과 최소안 ${formatKw(opts.overage_minimized.contract_kw, 0)}kW(초과 ${opts.overage_minimized.overage_probability}%) 중 ` +
                    `비용과 초과 위험을 보고 선택하세요.`
                );
            }
        } else {
            if (currentIsAdequate) {
                items.push(`현재 ${formatKw(currentKw, 0)}kW 계약이 적정 수준으로 유지되고 있어요.`);
            } else {
                items.push(`안전하게 사용하려면 ${formatKw(recommendedKw, 0)}kW 계약을 추천해요.`);
            }
        }

        const annualSavings = pred.contract_recommendation.annual_savings_won;
        if (annualSavings && annualSavings !== 0) {
            if (annualSavings > 0) {
                items.push(
                    `권장 계약을 따르면 연간 약 ${formatCurrency(annualSavings)} 절감이 예상돼요.`
                );
                if (pred.contract_recommendation.monthly_savings && pred.contract_recommendation.monthly_savings > 0) {
                    const monthly = formatCurrency(pred.contract_recommendation.monthly_savings);
                    const percent = pred.contract_recommendation.savings_percentage
                        ? formatPercent(pred.contract_recommendation.savings_percentage, 1)
                        : null;
                    items.push(
                        percent
                            ? `월 평균 ${monthly} 절감 (${percent}).`
                            : `월 평균 ${monthly} 절감.`
                    );
                }
            } else {
                const absAnnual = formatCurrency(Math.abs(annualSavings));
                items.push(
                    `권장 계약 적용 시 연간 약 ${absAnnual}의 추가 비용이 예상되지만, ` +
                    `계약전력 초과 리스크를 낮춰 청구서 변동성을 줄일 수 있어요.`
                );
                if (pred.contract_recommendation.monthly_savings && pred.contract_recommendation.monthly_savings < 0) {
                    const monthly = formatCurrency(Math.abs(pred.contract_recommendation.monthly_savings));
                    items.push(`월 평균 약 ${monthly}의 추가 비용이 발생할 수 있어요.`);
                }
            }
        }

        if (
            pred.contract_recommendation.urgency_level &&
            !currentIsAdequate
        ) {
            items.push(getUrgencyText(pred.contract_recommendation.urgency_level));
        }

        return items;
    }

    // buildSavingsBadges removed per user request

    function getRiskLabel(level: string): string {
        switch (level) {
            case 'high':
                return '높음';
            case 'medium':
                return '보통';
            case 'low':
                return '낮음';
            default:
                return level;
        }
    }

    function buildRiskSummary(risk: NonNullable<EnsemblePredictionResponse['contract_recommendation']['risk_assessment']>): string {
        const overage = formatPercent(risk.overage_probability, 1);
        const waste = formatPercent(risk.waste_probability, 1);
        const level = getRiskLabel(risk.risk_level);
        return `${level} 수준으로 예측되며 계약 전력이 부족할 확률은 ${overage}, 여유가 남을 확률은 ${waste}입니다.`;
    }

    function buildModelExplainer(
        key: 'lstm' | 'xgboost',
        summary: EnsemblePredictionResponse['ensemble_prediction']
    ): string {
        const model = summary[key];
        const baseCopy =
            key === 'lstm'
                ? '최근 충전 패턴을 학습한 시계열 모델이'
                : '많은 변수를 고려하는 의사결정 모델이';
        return `${baseCopy} ${formatKw(model.prediction_kw)}kW로 예측했고 불확실성 범위는 ±${formatKw(model.uncertainty_kw)}kW에요.`;
    }

    $: summaryHighlights = prediction ? buildSummaryHighlights(prediction) : [];

    $:
        riskSummary = prediction?.contract_recommendation.risk_assessment
            ? buildRiskSummary(prediction.contract_recommendation.risk_assessment)
            : '';

    $: lastUpdated = prediction ? new Date(prediction.timestamp) : null;
</script>

<div class="ensemble-predictor">
    <div class="ensemble-hero">
        <div class="hero-copy">
            <p class="eyebrow">AI 계약 전력 추천</p>
            <h2>순간 최고 전력 예측과 전력량 수요를 한눈에</h2>
            <p class="hero-sub">
                LSTM · XGBoost 앙상블이 학습한 패턴으로 계약전력, 리스크, 절감액을 실시간 계산합니다.
            </p>
            <div class="hero-meta">
                <span class="meta-chip">충전소 {stationId}</span>
                {#if prediction}
                    <span class="meta-chip muted">업데이트 {lastUpdated?.toLocaleString('ko-KR')}</span>
                    <span class="meta-chip muted">모델 {prediction.metadata.model_version}</span>
                {/if}
            </div>
        </div>
        <div class="hero-actions">
            <button
                on:click={() => loadEnsemblePrediction(true)}
                disabled={loading}
                class="refresh-btn"
                class:loading
            >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class:spinning={loading}>
                    <path d="M23 4v6h-6M1 20v-6h6"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                {loading ? '예측 중...' : '예측 실행'}
            </button>
        </div>
    </div>

    {#if loading}
        <div class="loading-state">
            <LoadingSpinner />
            <div class="loading-text">
                <p class="loading-title">LSTM + XGBoost 앙상블 분석 중...</p>
                <p class="loading-subtitle">잠시만 기다려주세요</p>
            </div>
        </div>
    {:else if error && (errorCode === 'INSUFFICIENT_DATA' || errorCode === 'NO_DATA')}
        <div class="insufficient-data-state">
            <div class="insufficient-icon">📊</div>
            <h3 class="insufficient-title">
                {errorCode === 'NO_DATA' ? '이 충전소의 데이터를 찾을 수 없습니다' : '예측을 위한 데이터가 부족합니다'}
            </h3>
            <p class="insufficient-message">{error}</p>
            {#if errorDetails}
                <div class="insufficient-meta">
                    <div class="meta-row">
                        <span class="meta-label">현재</span>
                        <span class="meta-value">
                            세션 <strong>{errorDetails.session_count ?? 0}</strong>건
                            {#if errorDetails.unique_days !== null && errorDetails.unique_days !== undefined}
                                · 관측 <strong>{errorDetails.unique_days}</strong>일
                            {/if}
                            {#if errorDetails.data_coverage_start && errorDetails.data_coverage_end}
                                ({errorDetails.data_coverage_start} ~ {errorDetails.data_coverage_end})
                            {/if}
                        </span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">필요</span>
                        <span class="meta-value">
                            최소 세션 <strong>{errorDetails.min_required_sessions ?? 14}</strong>건
                            · <strong>{errorDetails.min_required_days ?? 7}</strong>일 이상
                        </span>
                    </div>
                </div>
            {/if}
            {#if errorGuidance.length > 0}
                <ul class="insufficient-guidance">
                    {#each errorGuidance as g}
                        <li>{g}</li>
                    {/each}
                </ul>
            {/if}
        </div>
    {:else if error}
        <div class="error-state">
            <div class="error-icon">⚠️</div>
            <p class="error-message">{error}</p>
        </div>
    {:else if !prediction}
        <!-- 초기 상태: 예측 시작 전 -->
        <div class="welcome-state">
            <div class="welcome-icon">🚀</div>
            <h3 class="welcome-title">AI 계약 전력 예측을 시작하세요</h3>
            <p class="welcome-description">
                LSTM과 XGBoost 앙상블 모델이 충전소의 사용 패턴을 분석하여<br />
                최적의 계약 전력과 예상 절감액을 계산해드립니다.
            </p>
            <div class="welcome-features">
                <div class="feature-item">
                    <span class="feature-icon">🧠</span>
                    <span class="feature-text">시계열 패턴 분석</span>
                </div>
                <div class="feature-item">
                    <span class="feature-icon">🌲</span>
                    <span class="feature-text">다양한 변수 고려</span>
                </div>
                <div class="feature-item">
                    <span class="feature-icon">💰</span>
                    <span class="feature-text">비용 절감 분석</span>
                </div>
            </div>
            <p class="welcome-cta">
                위의 <strong>"예측 실행"</strong> 버튼을 눌러 분석을 시작하세요!
            </p>
        </div>
    {:else if prediction}
        <div class="metric-grid">
            <div class="metric-card final">
                <div class="metric-head">
                    <span class="metric-label">예상 최고전력</span>
                    <span class="badge">P50</span>
                </div>
                <div class="metric-value">
                    {formatKw(prediction.contract_recommendation.predicted_peak_p50)}<span class="unit">kW</span>
                </div>
                <div class="metric-sub">
                    보수적 상한 <strong>P95 {formatKw(prediction.contract_recommendation.predicted_peak_p95)}kW</strong>
                    · 불확실성 ±{formatKw(prediction.ensemble_prediction.uncertainty_kw)}kW · 신뢰도 {formatPercent(prediction.ensemble_prediction.confidence_level, 0)}
                </div>
                <p class="metric-explain">
                    <strong>P50 (예상)</strong>: 보통의 피크 날에 기대되는 최고전력입니다.
                    <strong>P95 (상한)</strong>: 피크가 이 값 이하로 떨어지는 날이 95% 인 보수적 상한으로,
                    드물게 튀는 날까지 고려한 <strong>계약 안전마진의 기준</strong>입니다.
                    한전 계약전력은 초과 시 기본요금의 150% 패널티가 붙으므로, 계약은 P50~P95 사이에서 비용·위험을 함께 보고 정합니다.
                </p>
            </div>
            <div class="metric-card contract">
                <div class="metric-head">
                    <span class="metric-label">권장 계약 전력</span>
                    <span class="badge accent">2가지 안</span>
                </div>
                {#if prediction.contract_recommendation.recommendation_options}
                    {@const opts = prediction.contract_recommendation.recommendation_options}
                    <div class="rec-options">
                        <div class="rec-option cost">
                            <div class="rec-opt-head">⚖️ 균형 최적안</div>
                            <div class="rec-opt-kw">
                                {formatKw(opts.cost_optimal.contract_kw, 0)}<span class="unit">kW</span>
                            </div>
                            <div class="rec-opt-meta">
                                연 {formatCurrency(opts.cost_optimal.annual_cost)} · 초과확률 {opts.cost_optimal.overage_probability}%
                            </div>
                        </div>
                        <div class="rec-option safe" class:same={opts.same}>
                            <div class="rec-opt-head">🛡️ 초과 최소안</div>
                            <div class="rec-opt-kw">
                                {formatKw(opts.overage_minimized.contract_kw, 0)}<span class="unit">kW</span>
                            </div>
                            <div class="rec-opt-meta">
                                연 {formatCurrency(opts.overage_minimized.annual_cost)} · 초과확률 {opts.overage_minimized.overage_probability}%
                            </div>
                        </div>
                    </div>
                    <p class="rec-note">{opts.note}</p>
                {:else}
                    <div class="metric-value">
                        {formatKw(prediction.contract_recommendation.recommended_contract_kw, 0)}<span class="unit">kW</span>
                    </div>
                    <div class="metric-sub">
                        {#if prediction.contract_recommendation.current_contract_kw}
                            현재 {prediction.contract_recommendation.current_contract_kw}kW ·
                        {/if}
                        {getUrgencyText(prediction.contract_recommendation.urgency_level)}
                    </div>
                {/if}
            </div>
            {#if prediction.contract_recommendation.annual_savings_won}
                {@const annualSavingsWon = prediction.contract_recommendation.annual_savings_won}
                {@const isCostIncrease = annualSavingsWon < 0}
                <div class="metric-card savings" class:cost-increase={isCostIncrease}>
                    <div class="metric-head">
                        <span class="metric-label">
                            {isCostIncrease ? '연간 예상 추가 비용' : '연간 예상 절감액'}
                        </span>
                        <span class="badge {isCostIncrease ? 'warning' : 'success'}">비용</span>
                    </div>
                    <div class="metric-value">
                        {formatCurrency(Math.abs(annualSavingsWon))}
                    </div>
                    <div class="metric-sub">
                        {#if isCostIncrease}
                            안전 마진 확보를 위한 추가 비용 추정치
                        {:else if prediction.contract_recommendation.savings_percentage}
                            절감률 {formatPercent(prediction.contract_recommendation.savings_percentage, 1)}
                        {:else}
                            권장 계약 기준 절감 추정치
                        {/if}
                    </div>
                </div>
            {/if}
        </div>
        <div class="insight-panel">
            <div>
                <h3 class="section-title">요약 인사이트</h3>
                <ul class="summary-list">
                    {#each summaryHighlights as item}
                        <li>
                            <span class="summary-bullet">•</span>
                            <span>{item}</span>
                        </li>
                    {/each}
                </ul>
            </div>
            <div class="meta-chips">
                <span class="meta-chip">LSTM {formatKw(prediction.ensemble_prediction.lstm.prediction_kw, 1)}kW</span>
                <span class="meta-chip">XGBoost {formatKw(prediction.ensemble_prediction.xgboost.prediction_kw, 1)}kW</span>
                <span class="meta-chip muted">샘플 {prediction.ensemble_prediction.maturity.session_count.toLocaleString()}건</span>
            </div>
        </div>
        <!-- 모델 상세 정보 (토글) -->
        <div class="details-section">
            <button
                on:click={() => showDetails = !showDetails}
                class="details-toggle"
                class:active={showDetails}
            >
                <div class="toggle-content">
                    <span class="toggle-icon">🔍</span>
                    <span class="toggle-label">모델 상세 정보</span>
                </div>
                <svg class="toggle-arrow" class:rotated={showDetails} viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M6 9l6 6 6-6"/>
                </svg>
            </button>

            {#if showDetails}
                <div class="details-content">
                    <div class="model-cards">
                        <!-- LSTM 모델 -->
                        <div class="model-card lstm-model">
                            <div class="model-header">
                                <span class="model-icon">🧠</span>
                                <h3 class="model-title">LSTM 모델</h3>
                            </div>
                            <div class="model-metrics">
                                <div class="model-metric">
                                    <span class="metric-label">예측값</span>
                                    <span class="metric-value">
                                        {prediction.ensemble_prediction.lstm.prediction_kw.toFixed(1)} kW
                                    </span>
                                </div>
                                <div class="model-metric">
                                    <span class="metric-label">불확실성</span>
                                    <span class="metric-value">
                                        ±{prediction.ensemble_prediction.lstm.uncertainty_kw.toFixed(1)} kW
                                    </span>
                                </div>
                                <div class="model-metric">
                                    <span class="metric-label">가중치</span>
                                    <span class="metric-value weight">
                                        {(prediction.ensemble_prediction.lstm.weight * 100).toFixed(0)}%
                                    </span>
                                </div>
                            </div>
                            <div class="weight-bar">
                                <div
                                    class="weight-fill"
                                    style={`width: ${(prediction.ensemble_prediction.lstm.weight * 100).toFixed(0)}%`}
                                ></div>
                            </div>
                            <p class="model-explainer">{buildModelExplainer('lstm', prediction.ensemble_prediction)}</p>
                            <div class="model-description">
                                <span class="model-note">주요 특징</span>
                                <ul class="model-points">
                                    <li>최근 충전 흐름을 학습한 시계열 기반 예측</li>
                                    <li>Monte Carlo Dropout으로 변동성을 추정해 안정성을 확보</li>
                                </ul>
                            </div>
                        </div>

                        <!-- XGBoost 모델 -->
                        <div class="model-card xgboost-model">
                            <div class="model-header">
                                <span class="model-icon">🌲</span>
                                <h3 class="model-title">XGBoost 모델</h3>
                            </div>
                            <div class="model-metrics">
                                <div class="model-metric">
                                    <span class="metric-label">예측값</span>
                                    <span class="metric-value">
                                        {prediction.ensemble_prediction.xgboost.prediction_kw.toFixed(1)} kW
                                    </span>
                                </div>
                                <div class="model-metric">
                                    <span class="metric-label">불확실성</span>
                                    <span class="metric-value">
                                        ±{prediction.ensemble_prediction.xgboost.uncertainty_kw.toFixed(1)} kW
                                    </span>
                                </div>
                                <div class="model-metric">
                                    <span class="metric-label">가중치</span>
                                    <span class="metric-value weight">
                                        {(prediction.ensemble_prediction.xgboost.weight * 100).toFixed(0)}%
                                    </span>
                                </div>
                            </div>
                            <div class="weight-bar">
                                <div
                                    class="weight-fill"
                                    style={`width: ${(prediction.ensemble_prediction.xgboost.weight * 100).toFixed(0)}%`}
                                ></div>
                            </div>
                            <p class="model-explainer">{buildModelExplainer('xgboost', prediction.ensemble_prediction)}</p>
                            <div class="model-description">
                                <span class="model-note">주요 특징</span>
                                <ul class="model-points">
                                    <li>충전소 이용 시간, 요일, 환경 정보를 함께 고려</li>
                                    <li>비선형 패턴을 학습해 갑작스런 피크에도 대비</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            {/if}
        </div>

        <!-- 10kW 단위 최적화 시각화 -->
        {#if prediction.contract_recommendation.optimization_details}
            <div class="optimization-section">
                <ContractOptimizationChart
                    {stationId}
                    optimizationData={prediction.contract_recommendation.optimization_details}
                    predictionDistribution={prediction.contract_recommendation.optimization_details.prediction_distribution || []}
                    ensemblePrediction={prediction.ensemble_prediction}
                    recommendationOptions={prediction.contract_recommendation.recommendation_options}
                />
            </div>
        {/if}

        <!-- 메타데이터 -->
        <div class="metadata">
            <div class="metadata-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
                <span>모델 버전: {prediction.metadata.model_version}</span>
            </div>
            <div class="metadata-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                    <path d="M9 3v18"/>
                    <path d="M15 3v18"/>
                </svg>
                <span>충전기 타입: {prediction.metadata.charger_type}</span>
            </div>
            <div class="metadata-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12,6 12,12 16,14"/>
                </svg>
                <span>예측 시각: {new Date(prediction.timestamp).toLocaleString('ko-KR')}</span>
            </div>
        </div>
    {/if}
</div>

<style>
    /* 현대적 UI 스타일 - PeakPowerPredictor 참고 */
    .ensemble-predictor {
        display: flex;
        flex-direction: column;
        gap: 24px;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 2px 8px var(--shadow);
        margin-bottom: clamp(24px, 4vw, 40px);
    }

    .ensemble-hero {
        display: grid;
        grid-template-columns: 1.2fr 0.8fr;
        gap: 20px;
        padding: 18px;
        border: 1px solid var(--border-color);
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(59,130,246,0.08));
    }

    .hero-copy h2 {
        margin: 6px 0 8px;
        font-size: 1.55rem;
        color: var(--text-primary);
    }

    .hero-sub {
        margin: 0;
        color: var(--text-secondary);
        line-height: 1.5;
    }

    .eyebrow {
        margin: 0;
        font-size: 0.9rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        color: var(--primary-color);
    }

    .hero-meta {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 10px;
    }

    .meta-chip {
        padding: 6px 10px;
        border-radius: 10px;
        background: rgba(99, 102, 241, 0.12);
        color: var(--text-primary);
        font-size: 0.85rem;
        border: 1px solid rgba(99, 102, 241, 0.25);
    }

    .meta-chip.muted {
        background: rgba(148, 163, 184, 0.12);
        border-color: rgba(148, 163, 184, 0.35);
        color: var(--text-secondary);
    }

    .hero-actions {
        display: flex;
        flex-direction: column;
        gap: 12px;
        align-items: flex-end;
        justify-content: center;
    }

    .refresh-btn {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 20px;
        background: var(--primary-color);
        color: white;
        border: none;
        border-radius: 10px;
        font-size: 0.95rem;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.2s ease;
        min-width: 160px;
        justify-content: center;
    }

    .refresh-btn:hover:not(:disabled) {
        background: var(--primary-dark);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }

    .refresh-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .refresh-btn svg {
        width: 18px;
        height: 18px;
        stroke-width: 2.5;
    }

    .refresh-btn svg.spinning {
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }

    /* 로딩 상태 */
    .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 80px 24px;
        gap: 20px;
    }

    .loading-text {
        text-align: center;
    }

    .loading-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .loading-subtitle {
        margin: 4px 0 0 0;
        font-size: 0.9rem;
        color: var(--text-secondary);
    }

    /* 에러 상태 */
    .error-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 60px 24px;
        gap: 16px;
        background: rgba(239, 68, 68, 0.05);
        border: 1px solid rgba(239, 68, 68, 0.2);
        border-radius: 12px;
    }

    .error-icon {
        font-size: 3rem;
    }

    .error-message {
        font-size: 1rem;
        font-weight: 500;
        color: #dc2626;
        text-align: center;
    }

    /* 데이터 부족 안내 */
    .insufficient-data-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 44px 28px;
        gap: 12px;
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.05), rgba(139, 92, 246, 0.04));
        border: 1px solid rgba(59, 130, 246, 0.25);
        border-radius: 14px;
        max-width: 720px;
        margin: 0 auto;
    }

    .insufficient-icon {
        font-size: 2.8rem;
        opacity: 0.9;
    }

    .insufficient-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-primary);
        margin: 4px 0 0;
        text-align: center;
    }

    .insufficient-message {
        font-size: 0.95rem;
        color: var(--text-secondary);
        text-align: center;
        line-height: 1.6;
        margin: 0;
    }

    .insufficient-meta {
        width: 100%;
        margin-top: 8px;
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
        font-size: 0.88rem;
    }

    .meta-label {
        flex: 0 0 48px;
        font-weight: 700;
        color: var(--primary-color, #4f46e5);
    }

    .meta-value {
        flex: 1;
        color: var(--text-secondary);
    }

    .meta-value strong {
        color: var(--text-primary);
    }

    .insufficient-guidance {
        margin: 8px 0 0;
        padding-left: 18px;
        font-size: 0.88rem;
        color: var(--text-secondary);
        line-height: 1.65;
    }

    .insufficient-guidance li {
        margin-bottom: 4px;
    }

    /* 초기 상태 (환영 메시지) */
    .welcome-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 60px 24px;
        gap: 20px;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.03), rgba(59, 130, 246, 0.03));
        border: 2px dashed rgba(99, 102, 241, 0.2);
        border-radius: 16px;
        text-align: center;
    }

    .welcome-icon {
        font-size: 4rem;
        animation: bounce 2s ease-in-out infinite;
    }

    @keyframes bounce {
        0%, 100% {
            transform: translateY(0);
        }
        50% {
            transform: translateY(-10px);
        }
    }

    .welcome-title {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .welcome-description {
        margin: 0;
        font-size: 1rem;
        color: var(--text-secondary);
        line-height: 1.6;
        max-width: 600px;
    }

    .welcome-features {
        display: flex;
        gap: 24px;
        margin-top: 12px;
        flex-wrap: wrap;
        justify-content: center;
    }

    .feature-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
        padding: 16px 20px;
        background: rgba(99, 102, 241, 0.05);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 12px;
        min-width: 140px;
        transition: all 0.2s ease;
    }

    .feature-item:hover {
        transform: translateY(-4px);
        background: rgba(99, 102, 241, 0.08);
        border-color: rgba(99, 102, 241, 0.25);
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
    }

    .feature-icon {
        font-size: 2rem;
    }

    .feature-text {
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .welcome-cta {
        margin: 12px 0 0 0;
        font-size: 1rem;
        color: var(--text-secondary);
    }

    .welcome-cta strong {
        color: var(--primary-color);
        font-weight: 700;
    }

    /* 메트릭 카드 및 인사이트 */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 14px;
    }

    .metric-card {
        padding: 16px;
        border-radius: 12px;
        border: 1px solid var(--border-color);
        background: var(--bg-secondary);
        box-shadow: 0 2px 8px var(--shadow);
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .metric-card.final { background: linear-gradient(135deg, rgba(59,130,246,0.1), rgba(99,102,241,0.08)); }
    .metric-card.contract { background: linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.05)); }
    .metric-card.savings { background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(16,185,129,0.08)); }

    .metric-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
    }

    .badge {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        background: rgba(99, 102, 241, 0.15);
        color: var(--primary-color);
    }

    .badge.accent { background: rgba(16,185,129,0.15); color: #059669; }
    .badge.success { background: rgba(34,197,94,0.18); color: #15803d; }

    .metric-label {
        font-weight: 700;
        color: var(--text-primary);
        font-size: 0.95rem;
    }

    .metric-value {
        font-size: 1.9rem;
        font-weight: 800;
        color: var(--text-primary);
        display: flex;
        align-items: baseline;
        gap: 4px;
    }

    .unit { font-size: 1rem; color: var(--text-secondary); }

    .metric-sub {
        color: var(--text-secondary);
        font-size: 0.95rem;
    }

    .metric-explain {
        margin: 10px 0 0;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(99, 102, 241, 0.08);
        border-left: 3px solid var(--primary-color, #6366f1);
        color: var(--text-secondary);
        font-size: 0.8rem;
        line-height: 1.55;
    }

    /* 이중 추천(비용 최적안 / 초과 최소안) */
    .rec-options {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-top: 4px;
    }
    .rec-option {
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid var(--border-color, #e5e7eb);
        background: var(--card-bg, #fff);
    }
    .rec-option.cost { border-left: 3px solid #2563eb; }
    .rec-option.safe { border-left: 3px solid #059669; }
    .rec-option.safe.same { opacity: 0.6; }
    .rec-opt-head {
        font-size: 0.78rem;
        font-weight: 600;
        color: var(--text-primary, #374151);
        margin-bottom: 4px;
    }
    .rec-opt-kw {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary, #111827);
        line-height: 1.1;
    }
    .rec-opt-kw .unit { font-size: 0.8rem; font-weight: 500; margin-left: 2px; }
    .rec-opt-meta {
        margin-top: 4px;
        font-size: 0.72rem;
        color: var(--text-secondary, #6b7280);
    }
    .rec-note {
        margin: 10px 0 0;
        padding: 8px 12px;
        border-radius: 10px;
        background: rgba(16, 185, 129, 0.08);
        border-left: 3px solid #059669;
        color: var(--text-secondary, #6b7280);
        font-size: 0.78rem;
        line-height: 1.5;
    }
    @media (max-width: 520px) {
        .rec-options { grid-template-columns: 1fr; }
    }

    .metric-explain strong {
        color: var(--text-primary);
    }

    .insight-panel {
        border: 1px solid var(--border-color);
        border-radius: 14px;
        padding: 16px;
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 12px;
        align-items: center;
        background: var(--bg-secondary);
        box-shadow: 0 2px 8px var(--shadow);
    }

    .section-title {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .summary-list {
        list-style: none;
        margin: 8px 0 0 0;
        padding: 0;
        display: grid;
        gap: 6px;
    }

    .summary-list li {
        display: flex;
        gap: 10px;
        font-size: 0.95rem;
        color: var(--text-primary);
        line-height: 1.5;
    }

    .summary-bullet {
        color: var(--primary-color);
        font-weight: 700;
    }

    .meta-chips {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
    }

    /* 상세 정보 섹션 */
    .details-section {
        background: rgba(100, 116, 139, 0.03);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        overflow: hidden;
    }

    .details-toggle {
        width: 100%;
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 20px;
        background: transparent;
        border: none;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .details-toggle:hover {
        background: rgba(100, 116, 139, 0.05);
    }

    .details-toggle.active {
        background: rgba(99, 102, 241, 0.05);
    }

    .toggle-content {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .toggle-icon {
        font-size: 1.2rem;
    }

    .toggle-label {
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .toggle-arrow {
        width: 20px;
        height: 20px;
        stroke-width: 2.5;
        color: var(--text-secondary);
        transition: transform 0.3s ease;
    }

    .toggle-arrow.rotated {
        transform: rotate(180deg);
    }

    .details-content {
        padding: 20px;
        border-top: 1px solid var(--border-color);
        animation: slideDown 0.3s ease;
    }

    @keyframes slideDown {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* 모델 카드 */
    .model-cards {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 16px;
        margin-bottom: 20px;
    }

    .model-card {
        background: var(--bg-secondary);
        border: 1px solid var(--model-border);
        border-radius: 12px;
        padding: 20px;
        transition: all 0.2s ease;
    }

    .model-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px var(--shadow);
    }

    .lstm-model {
        --model-border: rgba(99, 102, 241, 0.3);
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(129, 140, 248, 0.05));
    }

    .xgboost-model {
        --model-border: rgba(249, 115, 22, 0.3);
        background: linear-gradient(135deg, rgba(249, 115, 22, 0.05), rgba(251, 146, 60, 0.05));
    }

    .model-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
    }

    .model-icon {
        font-size: 1.5rem;
    }

    .model-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .model-metrics {
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-bottom: 12px;
    }

    .model-metric {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid var(--border-color);
    }

    .model-metric:last-child {
        border-bottom: none;
    }

    .model-metric .metric-label {
        font-size: 0.9rem;
        color: var(--text-secondary);
    }

    .model-metric .metric-value {
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .model-metric .metric-value.weight {
        color: #6366f1;
    }

    .weight-bar {
        height: 6px;
        border-radius: 999px;
        background: rgba(99, 102, 241, 0.15);
        overflow: hidden;
        margin-bottom: 12px;
    }

    .model-card.xgboost-model .weight-bar {
        background: rgba(249, 115, 22, 0.18);
    }

    .weight-fill {
        height: 100%;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.7), rgba(59, 130, 246, 0.9));
        transition: width 0.4s ease;
    }

    .model-card.xgboost-model .weight-fill {
        background: linear-gradient(135deg, rgba(251, 146, 60, 0.8), rgba(249, 115, 22, 0.9));
    }

    .model-explainer {
        margin: 0 0 12px 0;
        font-size: 0.9rem;
        color: var(--text-secondary);
        line-height: 1.5;
    }

    .model-description {
        padding: 12px;
        background: rgba(100, 116, 139, 0.05);
        border-radius: 10px;
        font-size: 0.85rem;
        color: var(--text-secondary);
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .model-note {
        font-weight: 700;
        color: var(--text-primary);
    }

    .model-points {
        margin: 0;
        padding-left: 18px;
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .model-points li {
        line-height: 1.4;
    }

    /* 최적화 섹션 */
    .optimization-section {
        margin-top: 8px;
    }

    /* 메타데이터 */
    .metadata {
        display: flex;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
        padding-top: 16px;
        border-top: 1px solid var(--border-color);
    }

    .metadata-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.8rem;
        color: var(--text-secondary);
    }

    .metadata-item svg {
        width: 14px;
        height: 14px;
        stroke-width: 2;
    }

    /* CSS 변수 정의 */
    :global([data-theme="light"]) .ensemble-predictor {
        --bg-secondary: #ffffff;
        --border-color: rgba(0, 0, 0, 0.1);
        --shadow: rgba(0, 0, 0, 0.05);
        --shadow-hover: rgba(0, 0, 0, 0.15);
        --text-primary: #111827;
        --text-secondary: #6b7280;
        --primary-color: #4f46e5;
        --primary-dark: #4338ca;
    }

    :global([data-theme="dark"]) .ensemble-predictor {
        --bg-secondary: #1f2937;
        --border-color: #374151;
        --shadow: rgba(0, 0, 0, 0.3);
        --shadow-hover: rgba(0, 0, 0, 0.5);
        --text-primary: #f9fafb;
        --text-secondary: #d1d5db;
        --primary-color: #6366f1;
        --primary-dark: #4f46e5;
    }

    /* 반응형 */
    @media (max-width: 768px) {
        .ensemble-predictor {
            padding: 16px;
        }

        .ensemble-hero {
            grid-template-columns: 1fr;
            gap: 12px;
        }

        .hero-actions {
            width: 100%;
            align-items: flex-start;
        }

        .hero-copy h2 {
            font-size: 1.3rem;
        }

        .metric-grid {
            grid-template-columns: 1fr;
        }

        .metadata {
            flex-direction: column;
            gap: 8px;
        }

        .model-cards {
            grid-template-columns: 1fr;
        }
    }
</style>
