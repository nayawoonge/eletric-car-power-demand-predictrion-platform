<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import type { Chart as ChartInstance, Point } from 'chart.js';
    import type {
        EnsemblePredictionResponse,
        ContractShortfallSimulation,
        ContractShortfallDailyPoint,
        ContractCandidateDetail
    } from '../../lib/types';

    export let optimizationData: any = null;
    export let predictionDistribution: number[] = [];
    export let ensemblePrediction: EnsemblePredictionResponse['ensemble_prediction'] | null = null;
    export let stationId: string;
    // 백엔드 이중 추천(균형 최적안 / 초과 최소안) — 카드와 동일한 2안을 여기서도 사용하기 위함
    export let recommendationOptions: any = null;
    
    let chartContainer: HTMLDivElement;
    let chartCanvas: HTMLCanvasElement | null = null;
    let chartInstance: ChartInstance | null = null;
    let isDarkMode = false;
    let histogram: { x: number; y: number }[] = [];
    let lstmProjection: { x: number; y: number }[] = [];
    let q5 = 0;
    let q90 = 0;
    let q95 = 0;
    let historicalMax = 0;
    let projectedPeakKw = 0;
    let optimalCandidate: ContractCandidateDetail | null = null;
    let manualCandidate: ContractCandidateDetail | null = null;
    let allCandidates: ContractCandidateDetail[] = [];
    let ChartCtor: typeof import('chart.js/auto')['default'] | null = null;
    let chartReady = false;
    let timeSeriesCanvas: HTMLCanvasElement | null = null;
    let timeSeriesChartInstance: ChartInstance | null = null;
    let sessionSeries: SessionPoint[] = [];
    let sessionPredictionSeries: SessionPoint[] = [];
    let combinedSessionSeries: SessionPoint[] = [];
    let hasSessionTimeline = false;
    let sessionDomain: { min: number | null; max: number | null } = { min: null, max: null };
    let scenarioRows: ScenarioRow[] = [];
    let decisionBasisRows: DecisionBasisRow[] = [];
    let bestDecisionBasis: DecisionBasisRow | null = null;
    let runnerUpDecisionBasis: DecisionBasisRow | null = null;
    let selectedDecisionBasis: DecisionBasisRow | null = null;
    let monthlyLossMinRow: ScenarioRow | null = null;
    let balancedOptimalRow: ScenarioRow | null = null;
    let detailCategory: 'compare' | 'loss' | 'balanced' = 'compare';
    let showFormulaDetails = false;
    let showQuestionSection = false;
    let shortfallScenarios: ShortfallScenario[] = [];
    let shortfallDailyProjection: ShortfallDailyPoint[] = [];
    let activeShortfallScenario: ShortfallScenario | null = null;
    let overfitSignal: OverfitSignal = { isRisk: false, mae: null, relativeError: null, coverageDays: 0 };
    let selectedContractKw: number | null = null;
    let targetContractKw: number | null = null;
    let scenarioPredictedPeakAvg: number | null = null;
    let scenarioPredictedPeakP90: number | null = null;
    let scenarioOverageProbability: number | null = null;
    let scenarioP50: number | null = null;
    let futureProjectionPreview: ShortfallDailyPoint[] = [];
    type MonthlyProjectionRow = {
        key: string;
        date: string;
        peak_kw: number;
        p10_peak_kw: number;
        p90_peak_kw: number;
        max_overshoot_kw: number;
        avg_risk_factor: number;
    };
    let futureMonthlyProjection: MonthlyProjectionRow[] = [];
    let isManualUndershoot = false;
    let isManualOvershoot = false;
    const FUTURE_FORECAST_MONTHS = 3;

    type MonthlyBucket = { key: string; date: string; peak_kw: number };

    function monthKeyFromDate(date: Date): string {
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    }

    function monthLabelFromKey(key: string): string {
        const [year, month] = key.split('-');
        return `${year}년 ${Number(month)}월`;
    }

    function firstDayOfMonthKey(key: string): string {
        return `${key}-01`;
    }

    function aggregateMonthlyPeaks(points: { date: string; power_kw?: number; simulated_peak_kw?: number }[]): MonthlyBucket[] {
        const map = new Map<string, number>();
        for (const point of points) {
            const raw = point.power_kw ?? point.simulated_peak_kw;
            if (!Number.isFinite(raw)) continue;
            const parsed = new Date(point.date);
            if (Number.isNaN(parsed.getTime())) continue;
            const key = monthKeyFromDate(parsed);
            const current = map.get(key) ?? 0;
            if ((raw as number) > current) {
                map.set(key, raw as number);
            }
        }
        return Array.from(map.entries())
            .map(([key, peak_kw]) => ({ key, date: firstDayOfMonthKey(key), peak_kw }))
            .sort((a, b) => a.date.localeCompare(b.date));
    }

    // 모델 검증 데이터 (9월까지 학습 → 10월 예측)
    let validationData: any = null;
    let validationLoading = false;
    let validationError: string | null = null;
    const BASIC_RATE_PER_KW = 8320;
    const SHORTAGE_PENALTY_RATIO = 1.5;
    const MONTHS_PER_YEAR = 12;
    const BASIC_RATE_LABEL = BASIC_RATE_PER_KW.toLocaleString('ko-KR');

    type SessionPoint = { date: string; power_kw: number };
    type OverfitSignal = {
        isRisk: boolean;
        mae: number | null;
        relativeError: number | null;
        coverageDays: number;
    };
    type ScenarioRow = {
        scenario: 'over' | 'optimal' | 'under';
        scenarioLabel: string;
        contractKw: number;
        baseMonthly: number;
        overCostMonthly: number;
        shortageMonthly: number;
        ratchetingMonthly: number;
        totalLossMonthly: number;
        monthlySavings: number;
        overageProbability: number;           // 표시용 (실측 우선, 없으면 모델)
        modelOverageProbability: number;      // 모델 분포 기반 (예측)
        sessionOverageProbability: number | null; // 과거 실측 세션 기반
        score: number;
        normalizedCost: number;
        riskScore: number;
        scoreReason: string;
    };
    type DecisionBasisRow = {
        contractKw: number;
        expectedAnnualCost: number;
        normalizedCost: number;
        riskScore: number;
        totalScore: number;
        overageProbability: number;          // 모델 분포 기반 (예측)
        sessionOverageProbability: number | null; // 과거 실측 세션 기반
        wasteProbability: number;
        costStd: number;
    };
    type ShortfallDailyPoint = ContractShortfallDailyPoint;
    type ShortfallScenario = ContractShortfallSimulation;
    type ProsCons = { pros: string[]; cons: string[] };

    function toNumber(value: any): number | null {
        const num = Number(value);
        return Number.isFinite(num) ? num : null;
    }

    function normalizeCandidate(candidate: any): ContractCandidateDetail | null {
        const contractKw = toNumber(candidate?.contract_kw);
        if (contractKw === null) {
            return null;
        }

        const normalizeOptional = (val: any) => {
            const num = toNumber(val);
            return num === null ? undefined : num;
        };

        return {
            ...candidate,
            contract_kw: contractKw,
            expected_annual_cost: toNumber(candidate?.expected_annual_cost) ?? 0,
            overage_probability: toNumber(candidate?.overage_probability) ?? 0,
            waste_probability: toNumber(candidate?.waste_probability) ?? 0,
            cost_std: normalizeOptional(candidate?.cost_std),
            risk_score: normalizeOptional(candidate?.risk_score),
            session_overage_probability: normalizeOptional(candidate?.session_overage_probability),
            session_average_overshoot_kw: normalizeOptional(candidate?.session_average_overshoot_kw),
            session_max_overshoot_kw: normalizeOptional(candidate?.session_max_overshoot_kw),
            session_waste_probability: normalizeOptional(candidate?.session_waste_probability),
            session_average_waste_kw: normalizeOptional(candidate?.session_average_waste_kw),
            session_sample_size: normalizeOptional(candidate?.session_sample_size),
            session_expected_waste_cost: normalizeOptional(candidate?.session_expected_waste_cost)
        };
    }

    function normalizeSessionSeries(series?: any[] | null): SessionPoint[] {
        if (!Array.isArray(series) || series.length === 0) {
            return [];
        }

        return series
            .map((entry) => {
                const rawDate = entry?.timestamp ?? entry?.date ?? entry?.time;
                const rawPeak = entry?.peak_kw ?? entry?.peakKw ?? entry?.predicted_peak_kw ?? entry?.predictedPeakKw ?? entry?.value;
                const parsedDate = rawDate ? new Date(rawDate) : null;
                const peakValue = rawPeak !== undefined && rawPeak !== null ? Number(rawPeak) : NaN;

                if (!parsedDate || Number.isNaN(parsedDate.getTime()) || Number.isNaN(peakValue)) {
                    return null;
                }

                return {
                    date: parsedDate.toISOString(),
                    power_kw: Number(peakValue.toFixed(2))
                } satisfies SessionPoint;
            })
            .filter((point): point is SessionPoint => point !== null)
            .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    }

    function normalizeDailyPeakSeries(series?: any[] | null): SessionPoint[] {
        if (!Array.isArray(series) || series.length === 0) {
            return [];
        }

        return series
            .map((entry) => {
                const rawDate = entry?.date ?? entry?.timestamp ?? entry?.time;
                const rawPeak = entry?.peak_kw ?? entry?.peakKw ?? entry?.predicted_peak_kw ?? entry?.predictedPeakKw ?? entry?.value;
                if (!rawDate || rawPeak === undefined || rawPeak === null) {
                    return null;
                }
                const parsedDate = new Date(rawDate);
                const peakValue = Number(rawPeak);
                if (Number.isNaN(parsedDate.getTime()) || Number.isNaN(peakValue)) {
                    return null;
                }
                return {
                    date: parsedDate.toISOString(),
                    power_kw: Number(peakValue.toFixed(2))
                } satisfies SessionPoint;
            })
            .filter((point): point is SessionPoint => point !== null)
            .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    }

    function computeSessionDomain(points: SessionPoint[]) {
        if (!points.length) {
            return { min: null, max: null };
        }
        const times = points.map((point) => new Date(point.date).getTime());
        return {
            min: Math.min(...times),
            max: Math.max(...times)
        };
    }

    function smoothChronologicalSeries(entries: { date: string; value: number }[], windowSize = 8) {
        if (!Array.isArray(entries) || entries.length === 0) {
            return [];
        }
        const sorted = [...entries].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
        const buffer: number[] = [];
        let sum = 0;
        return sorted.map(entry => {
            const value = Number(entry.value) || 0;
            buffer.push(value);
            sum += value;
            if (buffer.length > windowSize) {
                sum -= buffer.shift() ?? 0;
            }
            const avg = buffer.length > 0 ? sum / buffer.length : value;
            return {
                x: new Date(entry.date).getTime(),
                y: Number(avg.toFixed(2))
            } satisfies Point;
        });
    }

    function aggregateDailyPeaks(points: SessionPoint[]) {
        const map = new Map<string, number>();
        points.forEach(point => {
            const key = toDateKey(point.date);
            const current = map.get(key) ?? Number.NEGATIVE_INFINITY;
            if (point.power_kw > current) {
                map.set(key, point.power_kw);
            }
        });
        return map;
    }

    function toDateKey(dateInput: string) {
        const ts = new Date(dateInput);
        if (Number.isNaN(ts.getTime())) {
            return '';
        }
        return ts.toISOString().slice(0, 10);
    }

    function computeOverfitSignal(sessionPoints: SessionPoint[], projectionPoints: ShortfallDailyPoint[]): OverfitSignal {
        const base: OverfitSignal = { isRisk: false, mae: null, relativeError: null, coverageDays: 0 };
        if (!sessionPoints.length || !projectionPoints.length) {
            return base;
        }
        const dailyPeaks = aggregateDailyPeaks(sessionPoints);
        let sampleCount = 0;
        let errorSum = 0;
        let actualSum = 0;
        projectionPoints.forEach(point => {
            const key = toDateKey(point.date);
            if (!key) {
                return;
            }
            const actual = dailyPeaks.get(key);
            if (actual === undefined) {
                return;
            }
            sampleCount += 1;
            errorSum += Math.abs(actual - point.simulated_peak_kw);
            actualSum += actual;
        });
        if (sampleCount < 5) {
            return { ...base, coverageDays: sampleCount };
        }
        const mae = errorSum / sampleCount;
        const avgActual = actualSum / sampleCount;
        const relativeError = avgActual > 0 ? mae / avgActual : null;
        const isRisk = relativeError !== null && relativeError > 0.35;
        return {
            isRisk,
            mae: Number(mae.toFixed(2)),
            relativeError: relativeError !== null ? Number(relativeError.toFixed(3)) : null,
            coverageDays: sampleCount
        };
    }

    function normalizeShortfallProjection(series?: any[] | null): ShortfallDailyPoint[] {
        if (!Array.isArray(series) || series.length === 0) {
            return [];
        }

        return series
            .map((entry) => {
                const rawDate = entry?.date ?? entry?.timestamp ?? entry?.day;
                const simulatedValue = entry?.simulated_peak_kw ?? entry?.simulatedPeakKw;
                const overshootValue = entry?.overshoot_kw ?? entry?.overshootKw;
                const historicalValue = entry?.historical_peak_kw ?? entry?.historicalPeakKw ?? entry?.peak_kw;
                const parsedDate = rawDate ? new Date(rawDate) : null;

                if (!parsedDate || Number.isNaN(parsedDate.getTime()) || simulatedValue === undefined) {
                    return null;
                }

                const safeSimulated = Number(simulatedValue);
                if (Number.isNaN(safeSimulated)) {
                    return null;
                }

                const overshootRaw = overshootValue !== undefined ? Number(overshootValue) : Math.max(0, safeSimulated - (entry?.contract_kw ?? 0));
                const safeOvershoot = Number.isNaN(overshootRaw) ? 0 : overshootRaw;
                let historical: number | undefined;
                if (historicalValue !== undefined && historicalValue !== null) {
                    const numericHistorical = Number(historicalValue);
                    if (!Number.isNaN(numericHistorical)) {
                        historical = Number(numericHistorical.toFixed(2));
                    }
                }

                const pickFinite = (...values: unknown[]): number | undefined => {
                    for (const v of values) {
                        if (v === undefined || v === null) continue;
                        const n = Number(v);
                        if (Number.isFinite(n)) return Number(n.toFixed(2));
                    }
                    return undefined;
                };

                return {
                    date: parsedDate.toISOString(),
                    simulated_peak_kw: Number(safeSimulated.toFixed(2)),
                    overshoot_kw: Number(Math.max(0, safeOvershoot).toFixed(2)),
                    historical_peak_kw: historical,
                    risk_factor: entry?.risk_factor ?? entry?.riskFactor,
                    p10_kw: pickFinite(entry?.p10_kw, entry?.p10Kw),
                    p50_kw: pickFinite(entry?.p50_kw, entry?.p50Kw),
                    p90_kw: pickFinite(entry?.p90_kw, entry?.p90Kw),
                    p95_kw: pickFinite(entry?.p95_kw, entry?.p95Kw),
                    std_kw: pickFinite(entry?.std_kw, entry?.stdKw)
                } as ShortfallDailyPoint;
            })
            .filter((point): point is ShortfallDailyPoint => point !== null)
            .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    }

    function normalPdf(x: number, mean: number, stdDev: number) {
        const safeStd = Math.max(stdDev, 1e-3);
        const coeff = 1 / (safeStd * Math.sqrt(2 * Math.PI));
        const exponent = -0.5 * ((x - mean) / safeStd) ** 2;
        return coeff * Math.exp(exponent);
    }

    function generateHistogram(values: number[], targetBins = 26) {
        if (!Array.isArray(values) || values.length === 0) {
            return [];
        }
        const normalized = values
            .map((value) => Number(value))
            .filter((value) => Number.isFinite(value));
        if (normalized.length === 0) {
            return [];
        }
        const min = Math.min(...normalized);
        const max = Math.max(...normalized);
        const bins = Math.max(8, Math.min(targetBins, normalized.length));
        const range = max - min || 1;
        const width = range / bins;
        const counts = new Array(bins).fill(0);
        normalized.forEach((value) => {
            const index = Math.min(bins - 1, Math.floor((value - min) / width));
            counts[index] += 1;
        });
        return counts.map((count, index) => {
            const x = min + width * index + width / 2;
            return { x: Number(x.toFixed(2)), y: Number(count.toFixed(2)) };
        });
    }

    function detectDarkMode() {
        if (typeof document === 'undefined') {
            return false;
        }
        const html = document.documentElement;
        if (html.classList.contains('dark') || html.getAttribute('data-theme') === 'dark') {
            return true;
        }
        if (typeof window !== 'undefined' && window.matchMedia) {
            return window.matchMedia('(prefers-color-scheme: dark)').matches;
        }
        return false;
    }

    function formatManwon(value?: number | null) {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return '-';
        }
        const manwon = value / 10000;
        const digits = Math.abs(manwon) >= 100 ? 0 : 1;
        return manwon.toLocaleString('ko-KR', {
            maximumFractionDigits: digits,
            minimumFractionDigits: digits
        });
    }

    function formatWon(value?: number | null) {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return '-';
        }
        return `${Math.round(value).toLocaleString('ko-KR')}원`;
    }

    function formatScore(value?: number | null, digits = 3) {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return '-';
        }
        return Number(value).toFixed(digits);
    }

    function formatProbability(value?: number | null, digits = 1) {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return '-';
        }
        return `${Number(value).toFixed(digits)}%`;
    }

    // 모델 분포 기반(예측)과 과거 실측(세션) 두 확률을 함께 표시.
    // 두 값이 크게 어긋나면(20pp 이상) 모델의 과소/과대 예측 신호로 경고 텍스트를 함께 반환.
    function formatDualProbability(
        modelProb?: number | null,
        sessionProb?: number | null,
        digits = 1
    ): { text: string; divergence: 'none' | 'mild' | 'severe' } {
        const hasModel = modelProb !== null && modelProb !== undefined && !Number.isNaN(modelProb);
        const hasSession = sessionProb !== null && sessionProb !== undefined && !Number.isNaN(sessionProb);
        if (hasModel && hasSession) {
            const diff = Math.abs(Number(modelProb) - Number(sessionProb));
            const divergence: 'none' | 'mild' | 'severe' = diff >= 20 ? 'severe' : diff >= 10 ? 'mild' : 'none';
            return {
                text: `예측 ${Number(modelProb).toFixed(digits)}% (모델) · 실측 ${Number(sessionProb).toFixed(digits)}% (과거)`,
                divergence
            };
        }
        if (hasModel) {
            return { text: `예측 ${Number(modelProb).toFixed(digits)}% (모델)`, divergence: 'none' };
        }
        if (hasSession) {
            return { text: `실측 ${Number(sessionProb).toFixed(digits)}% (과거)`, divergence: 'none' };
        }
        return { text: '-', divergence: 'none' };
    }

    function getDecisionRowByContract(contractKw: number | null): DecisionBasisRow | null {
        if (contractKw === null || contractKw === undefined) {
            return null;
        }
        return decisionBasisRows.find((row) => row.contractKw === contractKw) ?? null;
    }

    function buildProsCons(row: ScenarioRow | null, mode: 'loss' | 'balanced'): ProsCons {
        if (!row) {
            return { pros: [], cons: [] };
        }

        const decision = getDecisionRowByContract(row.contractKw);
        const overProb = decision?.overageProbability ?? row.overageProbability ?? 0;
        const wasteProb = decision?.wasteProbability ?? 0;
        const annualCost = decision?.expectedAnnualCost ?? (row.totalLossMonthly * 12) ?? 0;

        // mode 'loss' = 균형 최적안, mode 'balanced' = 초과 최소(안전)안 (변수명은 유지)
        if (mode === 'loss') {
            return {
                pros: [
                    `비용과 초과 위험을 함께 고려한 종합 최적안(권장 계약전력)입니다.`,
                    `연간 기대비용이 ${formatWon(annualCost)} 수준으로 비용 효율이 좋습니다.`,
                    `필요 이상으로 계약을 키우지 않아 기본요금 낭비가 적습니다.`
                ],
                cons: [
                    `예측 피크를 연 ${formatProbability(overProb)} 확률로 초과할 수 있어, 초과 시 기본요금 150% 부가금이 발생할 수 있습니다.`,
                    `계약 여유 발생일 비율 ${formatProbability(wasteProb)}이 높으면 비수기 활용도가 낮을 수 있습니다.`
                ]
            };
        }

        return {
            pros: [
                `초과 확률이 약 ${formatProbability(overProb)}로 매우 낮아 피크월에도 초과 부가금 위험이 거의 없습니다.`,
                `예측 최고전력(P95)을 덮어 청구서 변동성이 작고 안정적입니다.`,
                `초과 패널티 리스크를 최소화하고 싶을 때 적합합니다.`
            ],
            cons: [
                `기본요금을 더 부담하므로 균형 최적안보다 연간 비용이 높습니다 (약 ${formatWon(annualCost)}).`,
                `평소 피크보다 계약이 커서 비수기 여유 계약전력이 클 수 있습니다.`
            ]
        };
    }

    function formatScenarioDelta(contractKw: number, optimalKw: number | null) {
        if (optimalKw === null || optimalKw === undefined) {
            return '';
        }
        const delta = contractKw - optimalKw;
        if (delta === 0) {
            return '최적안 기준';
        }
        const sign = delta > 0 ? '+' : '';
        return `최적안 대비 ${sign}${delta}kW`;
    }

    function calcWasteCost(candidate: ContractCandidateDetail, referenceKw: number) {
        const wasteProb = (candidate.session_waste_probability ?? candidate.waste_probability ?? 0) / 100;
        const wasteKw = candidate.session_average_waste_kw ?? Math.max(0, candidate.contract_kw - referenceKw);
        const expectedWasteCost = candidate.session_expected_waste_cost;
        if (typeof expectedWasteCost === 'number') {
            return expectedWasteCost / MONTHS_PER_YEAR;
        }
        if (wasteProb <= 0 || wasteKw <= 0) return 0;
        return wasteKw * BASIC_RATE_PER_KW * wasteProb;
    }

    function calcShortageCost(candidate: ContractCandidateDetail, referenceKw: number, shortfallScenario?: ShortfallScenario | null) {
        // 예측 기반과 과거 데이터 중 더 큰 값 사용 (보수적 접근)
        let predictionCost = 0;
        let historicalCost = 0;

        // 1. 예측 기반 비용 계산
        if (shortfallScenario) {
            const predProb = (shortfallScenario.overshoot_probability ?? 0) / 100;
            const predOvershoot = shortfallScenario.expected_overshoot_kw ?? 0;
            if (predProb > 0 && predOvershoot > 0) {
                predictionCost = predOvershoot * BASIC_RATE_PER_KW * SHORTAGE_PENALTY_RATIO * predProb;
            }
        }

        // 2. 과거 세션 데이터 기반 비용 계산
        const histProb = (candidate.session_overage_probability ?? candidate.overage_probability ?? 0) / 100;
        const histOvershoot = candidate.session_average_overshoot_kw
            ?? candidate.session_max_overshoot_kw
            ?? 0;
        if (histProb > 0 && histOvershoot > 0) {
            historicalCost = histOvershoot * BASIC_RATE_PER_KW * SHORTAGE_PENALTY_RATIO * histProb;
        }

        // 더 큰 값 반환 (보수적 리스크 관리)
        return Math.max(predictionCost, historicalCost);
    }

    // 한전 검침 상향(ratcheting) 기대 추가 기본요금
    // 1회 초과 시 이후 12개월간 계약이 초과 피크 기준으로 상향되어 기본요금이 상승
    // Steady-state 상향 비율 ≈ min(1, 월초과확률 × 12),
    // 추가 월 기본요금 ≈ 비율 × 평균 초과 kW × 기본요금 단가
    const RATCHETING_LOCK_MONTHS = 12;
    function calcRatchetingCost(candidate: ContractCandidateDetail, shortfallScenario?: ShortfallScenario | null) {
        const prob = ((candidate.session_overage_probability ?? candidate.overage_probability ?? 0) as number) / 100;
        const delta = (shortfallScenario?.expected_overshoot_kw
            ?? candidate.session_average_overshoot_kw
            ?? 0) as number;
        if (prob <= 0 || delta <= 0) return 0;
        const ratchetedFraction = Math.min(1, prob * RATCHETING_LOCK_MONTHS);
        return ratchetedFraction * delta * BASIC_RATE_PER_KW;
    }

    function buildDecisionBasisRows(candidates: ContractCandidateDetail[]): DecisionBasisRow[] {
        if (!Array.isArray(candidates) || candidates.length === 0) {
            return [];
        }

        const normalized = candidates
            .map((candidate) => {
                const annualCost = Number(candidate.expected_annual_cost ?? 0);
                const riskScore = Number(candidate.risk_score ?? 0);
                const costStd = Number(candidate.cost_std ?? 0);
                if (!Number.isFinite(candidate.contract_kw) || !Number.isFinite(annualCost)) {
                    return null;
                }
                const sessionOverageRaw = candidate.session_overage_probability;
                const sessionOverageProbability =
                    sessionOverageRaw !== undefined && sessionOverageRaw !== null && Number.isFinite(Number(sessionOverageRaw))
                        ? Number(sessionOverageRaw)
                        : null;
                return {
                    contractKw: candidate.contract_kw,
                    expectedAnnualCost: annualCost,
                    riskScore: Number.isFinite(riskScore) ? riskScore : 0,
                    overageProbability: Number(candidate.overage_probability ?? 0),
                    sessionOverageProbability,
                    wasteProbability: Number(candidate.waste_probability ?? 0),
                    costStd: Number.isFinite(costStd) ? costStd : 0
                };
            })
            .filter(
                (
                    item
                ): item is {
                    contractKw: number;
                    expectedAnnualCost: number;
                    riskScore: number;
                    overageProbability: number;
                    sessionOverageProbability: number | null;
                    wasteProbability: number;
                    costStd: number;
                } => item !== null
            );

        if (normalized.length === 0) {
            return [];
        }

        const positiveCosts = normalized
            .map((item) => item.expectedAnnualCost)
            .filter((cost) => cost > 0);
        const minAnnualCost = positiveCosts.length > 0 ? Math.min(...positiveCosts) : 0;

        return normalized
            .map((item) => {
                const normalizedCost = minAnnualCost > 0 ? item.expectedAnnualCost / minAnnualCost : 1;
                const totalScore = normalizedCost + item.riskScore;
                return {
                    ...item,
                    normalizedCost,
                    totalScore
                };
            })
            .sort((a, b) => {
                if (a.totalScore !== b.totalScore) return a.totalScore - b.totalScore;
                if (a.expectedAnnualCost !== b.expectedAnnualCost) return a.expectedAnnualCost - b.expectedAnnualCost;
                return a.contractKw - b.contractKw;
            });
    }


    function buildScenarioRows(candidates: ContractCandidateDetail[], optimalKw: number | null, shortfallScenarios: ShortfallScenario[], currentContractKw: number | null): ScenarioRow[] {
        if (!Array.isArray(candidates) || candidates.length === 0) {
            return [];
        }

        const positiveCosts = candidates
            .map((candidate) => Number(candidate.expected_annual_cost ?? 0))
            .filter((cost) => Number.isFinite(cost) && cost > 0);
        const minAnnualCost = positiveCosts.length ? Math.min(...positiveCosts) : 0;

        const referenceKw = optimalKw ?? candidates[0].contract_kw;
        const rawRows = candidates.map((candidate) => {
            const scenario: ScenarioRow['scenario'] = candidate.contract_kw === referenceKw
                ? 'optimal'
                : candidate.contract_kw > referenceKw
                    ? 'over'
                    : 'under';
            const scenarioLabel = scenario === 'optimal' ? '최적안' : scenario === 'over' ? '과다' : '과소';
            const baseMonthly = candidate.contract_kw * BASIC_RATE_PER_KW;
            const overCostMonthly = calcWasteCost(candidate, referenceKw);

            // 해당 계약전력에 대한 shortfall 시나리오 찾기
            const shortfallScenario = shortfallScenarios.find(s => s.contract_kw === candidate.contract_kw);
            const shortageMonthly = calcShortageCost(candidate, referenceKw, shortfallScenario);
            const ratchetingMonthly = calcRatchetingCost(candidate, shortfallScenario);
            const totalLossMonthly = overCostMonthly + shortageMonthly + ratchetingMonthly;

            const expectedAnnualCost = Number(candidate.expected_annual_cost ?? 0);
            const normalizedCost = minAnnualCost > 0 ? expectedAnnualCost / minAnnualCost : 1;
            const riskScore = Number(candidate.risk_score ?? 0);
            const safeRiskScore = Number.isFinite(riskScore) ? riskScore : 0;
            const score = normalizedCost + safeRiskScore;
            const scoreReason = `비용지수 ${formatScore(normalizedCost)} + 리스크 ${formatScore(safeRiskScore)} (연간비용 ${formatWon(expectedAnnualCost)} / 최소연간비용 ${formatWon(minAnnualCost)})`;

            // 디버깅: 패널티 비용 계산 로그
            const histProb = candidate.session_overage_probability ?? candidate.overage_probability ?? 0;
            const histOvershoot = candidate.session_average_overshoot_kw ?? 0;
            const predProb = shortfallScenario?.overshoot_probability ?? 0;
            const predOvershoot = shortfallScenario?.expected_overshoot_kw ?? 0;
            console.log(`[${candidate.contract_kw}kW] 과거데이터: ${histProb}% / ${histOvershoot}kW, 예측데이터: ${predProb}% / ${predOvershoot}kW → 패널티비용: ${shortageMonthly.toFixed(0)}원`);

            const modelOverageRaw = Number(candidate.overage_probability ?? 0);
            const modelOverageProbability = Number.isFinite(modelOverageRaw) ? modelOverageRaw : 0;
            const sessionOverageRaw = candidate.session_overage_probability;
            const sessionOverageProbability =
                sessionOverageRaw !== undefined && sessionOverageRaw !== null && Number.isFinite(Number(sessionOverageRaw))
                    ? Number(sessionOverageRaw)
                    : null;
            const overageProbability = sessionOverageProbability ?? modelOverageProbability;

            return {
                scenario,
                scenarioLabel,
                contractKw: candidate.contract_kw,
                baseMonthly,
                overCostMonthly,
                shortageMonthly,
                ratchetingMonthly,
                totalLossMonthly,
                overageProbability,
                modelOverageProbability,
                sessionOverageProbability,
                score,
                normalizedCost,
                riskScore: safeRiskScore,
                scoreReason
            };
        });

        // 월 절감액 기준: 현재 계약 전력의 월 총비용 대비
        // 현재 계약이 후보에 없으면 가장 가까운 후보의 월 총비용을 사용
        const baselineMonthlyCost = (() => {
            if (rawRows.length === 0) return 0;
            if (currentContractKw === null || !Number.isFinite(currentContractKw)) {
                // fallback: 최악 시나리오 대비
                return Math.max(...rawRows.map((row) => row.baseMonthly + row.totalLossMonthly));
            }
            const match = rawRows.find((row) => row.contractKw === currentContractKw);
            if (match) {
                return match.baseMonthly + match.totalLossMonthly;
            }
            // 가장 가까운 계약 전력 후보 선택
            const closest = rawRows.reduce((prev, cur) =>
                Math.abs(cur.contractKw - currentContractKw) < Math.abs(prev.contractKw - currentContractKw) ? cur : prev
            );
            return closest.baseMonthly + closest.totalLossMonthly;
        })();

        const rows: ScenarioRow[] = rawRows.map((row) => ({
            ...row,
            monthlySavings: baselineMonthlyCost - (row.baseMonthly + row.totalLossMonthly)
        }));

        const orderWeight: Record<ScenarioRow['scenario'], number> = { optimal: 0, under: 1, over: 2 };
        return rows.sort((a, b) => orderWeight[a.scenario] - orderWeight[b.scenario] || a.contractKw - b.contractKw);
    }

    async function fetchValidationData() {
        if (!stationId) return;

        validationLoading = true;
        validationError = null;

        try {
            console.log('[ContractOptimizationChart] Fetching validation data for:', stationId);
            const response = await fetch(`/api/stations/${stationId}/model-validation`);
            const data = await response.json();

            if (data.success) {
                console.log('[ContractOptimizationChart] Validation data received:', data);
                validationData = data;
            } else {
                console.warn('[ContractOptimizationChart] Validation failed:', data.error);
                validationError = data.error || '검증 데이터를 불러올 수 없습니다.';
            }
        } catch (error) {
            console.error('[ContractOptimizationChart] Validation data fetch error:', error);
            validationError = '네트워크 오류가 발생했습니다.';
        } finally {
            validationLoading = false;
        }
    }

    async function ensureChartModules() {
        if (typeof window === 'undefined') {
            return;
        }
        if (ChartCtor) {
            chartReady = true;
            return;
        }
        try {
            const [{ default: ChartJS }, annotationPlugin, zoomPlugin] = await Promise.all([
                import('chart.js/auto'),
                import('chartjs-plugin-annotation'),
                import('chartjs-plugin-zoom')
            ]);
            await import('chartjs-adapter-date-fns');
            ChartJS.register(annotationPlugin.default || annotationPlugin);
            ChartJS.register(zoomPlugin.default || zoomPlugin);
            ChartCtor = ChartJS;
            chartReady = true;
        } catch (error) {
            chartReady = false;
            console.error('ContractOptimizationChart: Chart.js 모듈 로드 실패', error);
        }
    }

    function findShortfallScenario(
        scenarios: ShortfallScenario[],
        contractKw: number | null
    ): ShortfallScenario | null {
        if (!scenarios.length) {
            return null;
        }

        if (contractKw === null || contractKw === undefined) {
            return scenarios[0];
        }

        const exactMatch = scenarios.find((scenario) => scenario.contract_kw === contractKw);
        if (exactMatch) {
            return exactMatch;
        }

        return scenarios.reduce((closest, scenario) => {
            if (!closest) {
                return scenario;
            }
            const currentDelta = Math.abs(scenario.contract_kw - contractKw);
            const bestDelta = Math.abs(closest.contract_kw - contractKw);
            return currentDelta < bestDelta ? scenario : closest;
        }, scenarios[0]);
    }

    function getModelLabel(source?: string): string {
        if (!source) {
            return '딥러닝 모델';
        }
        if (source === 'lstm_mc_dropout') {
            return 'LSTM Monte Carlo';
        }
        return source.replace(/_/g, ' ').toUpperCase();
    }

    function buildLstmUndershootProjection(contractKw: number) {
        if (!ensemblePrediction?.lstm || predictionDistribution.length === 0) {
            return [];
        }

        const { prediction_kw, uncertainty_kw, weight } = ensemblePrediction.lstm;
        const mean = prediction_kw;
        const stdDev = Math.max(uncertainty_kw, 0.5);
        const histogramPeak = histogram.reduce((max, bin) => Math.max(max, bin.y ?? 0), 0);
        const scaleBase = histogramPeak || Math.max(1, predictionDistribution.length / 12);
        const steps = 80;
        const start = Math.max(0, Math.min(contractKw - stdDev * 2, mean - stdDev * 4));
        const end = Math.max(contractKw + stdDev * 3, mean + stdDev * 3);
        const emphasis = 1 + (weight || 0.5);

        const points: { x: number; y: number }[] = [];
        for (let i = 0; i <= steps; i++) {
            const x = start + ((end - start) * i) / steps;
            const baseDensity = normalPdf(x, mean, stdDev);
            let adjusted = baseDensity * scaleBase * emphasis;

            if (x < contractKw) {
                const deficitRatio = (contractKw - x) / Math.max(contractKw, 1);
                adjusted *= Math.max(0.2, 1 - deficitRatio * 0.9);
            } else {
                const overshootRatio = (x - contractKw) / Math.max(stdDev * 1.5, 1);
                adjusted *= 1 + Math.min(1.5, overshootRatio);
            }

            points.push({
                x: Number(x.toFixed(2)),
                y: Number(adjusted.toFixed(2))
            });
        }

        return points;
    }

    function safeMax(arr: number[]): number {
        if (!arr || arr.length === 0) return 0;
        return Math.max(...arr);
    }
    
    // 분위수 계산
    function percentile(arr: number[], p: number): number {
        if (!arr || arr.length === 0) return 0;
        const sorted = [...arr].sort((a, b) => a - b);
        const index = (p / 100) * (sorted.length - 1);
        const lower = Math.floor(index);
        const upper = Math.ceil(index);
        const weight = index - lower;
        return sorted[lower] * (1 - weight) + sorted[upper] * weight;
    }
    
    // Chart.js로 차트 생성
    function createChart() {
        if (!chartCanvas || predictionDistribution.length === 0 || !ChartCtor) return;
        
        const histogramData = histogram.length ? histogram : generateHistogram(predictionDistribution);
        const q5Val = percentile(predictionDistribution, 5);
        const q95Val = percentile(predictionDistribution, 95);
        const optimalKw = optimalCandidate?.contract_kw ?? 0;
        const manualKw = selectedContractKw ?? optimalKw;
        const projectedMax = projectedPeakKw || q95Val;
        const showUnderProjection = manualKw !== null && isManualUndershoot && projectedMax > manualKw;
        
        // 기존 차트 제거
        if (chartInstance) {
            chartInstance.destroy();
        }
        
        // 다크모드 색상
        const textColor = isDarkMode ? '#e2e8f0' : '#1f2937';
        const gridColor = isDarkMode ? 'rgba(148, 163, 184, 0.2)' : 'rgba(0, 0, 0, 0.1)';
        
        // annotation 구성
        const annotations: Record<string, any> = {
            q5Line: {
                type: 'line',
                xMin: Math.round(q5Val),
                xMax: Math.round(q5Val),
                borderColor: '#9c27b0',
                borderWidth: 2,
                borderDash: [5, 5],
                label: {
                    content: `Q₅: ${Math.round(q5Val)}kW`,
                    display: true,
                    position: 'start',
                    backgroundColor: '#9c27b0',
                    color: 'white',
                    font: { size: 11, weight: 'bold' }
                }
            },
            q95Line: {
                type: 'line',
                xMin: Math.round(q95Val),
                xMax: Math.round(q95Val),
                borderColor: '#9c27b0',
                borderWidth: 2,
                borderDash: [5, 5],
                label: {
                    content: `Q₉₅: ${Math.round(q95Val)}kW`,
                    display: true,
                    position: 'end',
                    backgroundColor: '#9c27b0',
                    color: 'white',
                    font: { size: 11, weight: 'bold' }
                }
            },
            optimalLine: {
                type: 'line',
                xMin: optimalKw,
                xMax: optimalKw,
                borderColor: '#10b981',
                borderWidth: 3,
                borderDash: [10, 5],
                label: {
                    content: `최적: ${optimalKw}kW`,
                    display: true,
                    position: 'center',
                    backgroundColor: '#10b981',
                    color: 'white',
                    font: { size: 12, weight: 'bold' }
                }
            }
        };

        if (manualKw !== null && manualKw !== undefined) {
            annotations.manualLine = {
                type: 'line',
                xMin: manualKw,
                xMax: manualKw,
                borderColor: '#f97316',
                borderWidth: 3,
                borderDash: [6, 4],
                label: {
                    content: `선택: ${manualKw}kW`,
                    display: true,
                    position: 'center',
                    backgroundColor: '#f97316',
                    color: '#fff',
                    font: { size: 12, weight: 'bold' }
                }
            };
        }

        if (showUnderProjection && manualKw < projectedMax) {
            annotations.underProjection = {
                type: 'box',
                xMin: manualKw,
                xMax: Math.round(projectedMax),
                backgroundColor: 'rgba(14, 165, 233, 0.12)',
                borderColor: 'rgba(14, 165, 233, 0.6)',
                borderWidth: 1,
                label: {
                    display: true,
                    position: 'start',
                    backgroundColor: 'rgba(14, 165, 233, 0.9)',
                    color: '#fff',
                    content: `과소 리스크 예상 ${Math.round(projectedMax)}kW`,
                    font: { size: 11, weight: '600' }
                }
            };
        }

        // 과다 시나리오 시각화
        const showOverProjection = manualKw !== null && isManualOvershoot && manualKw > q95Val;
        if (showOverProjection) {
            annotations.overProjection = {
                type: 'box',
                xMin: Math.round(q95Val),
                xMax: manualKw,
                backgroundColor: 'rgba(34, 197, 94, 0.08)',
                borderColor: 'rgba(34, 197, 94, 0.5)',
                borderWidth: 1,
                label: {
                    display: true,
                    position: 'end',
                    backgroundColor: 'rgba(34, 197, 94, 0.85)',
                    color: '#fff',
                    content: `여유 영역 (과다 계약)`,
                    font: { size: 11, weight: '600' }
                }
            };
        }

        const datasets: any[] = [
            {
                label: '예측 분포',
                data: histogramData.map(h => ({ x: h.x, y: h.y })),
                borderColor: '#3b82f6',
                backgroundColor: (context) => {
                    const ctx = context.chart.ctx;
                    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
                    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
                    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
                    return gradient;
                },
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 6,
            }
        ];

        if (lstmProjection.length > 0) {
            datasets.push({
                label: 'LSTM 과소 계약 시 분포',
                data: lstmProjection,
                borderColor: '#dc2626',
                backgroundColor: 'rgba(220, 38, 38, 0.18)',
                borderWidth: 2,
                borderDash: [8, 4],
                fill: true,
                tension: 0.35,
                pointRadius: 0,
                pointHoverRadius: 0,
            });
        }

        // Chart.js 차트 생성
        chartInstance = new ChartCtor(chartCanvas, {
            type: 'line',
            data: {
                datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: isDarkMode ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)',
                        titleColor: textColor,
                        bodyColor: textColor,
                        borderColor: isDarkMode ? '#475569' : '#e5e7eb',
                        borderWidth: 1,
                        callbacks: {
                            label: function(context) {
                                return `빈도: ${context.parsed.y}`;
                            }
                        }
                    },
                    annotation: {
                        annotations
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        title: {
                            display: true,
                            text: '전력 (kW)',
                            color: textColor,
                            font: { size: 13, weight: 'bold' }
                        },
                        ticks: {
                            color: textColor,
                            maxTicksLimit: 10
                        },
                        grid: {
                            color: gridColor
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: '빈도',
                            color: textColor,
                            font: { size: 13, weight: 'bold' }
                        },
                        ticks: {
                            color: textColor
                        },
                        grid: {
                            color: gridColor
                        }
                    }
                }
            }
        });
    }

    function createTimeSeriesChart() {
        if (!timeSeriesCanvas || !ChartCtor) {
            return;
        }

        if (timeSeriesChartInstance) {
            timeSeriesChartInstance.destroy();
            timeSeriesChartInstance = null;
        }

        // 단일 통합 뷰: 일별 실측 + 월별 피크 + 향후 3개월 일별 예측(신뢰구간)
        createMonthlyTimeSeriesChart();
        return;
    }

    function buildHistoricalMonthlyPeaks(): MonthlyBucket[] {
        const normalizedDailyPeaks = normalizeDailyPeakSeries(
            optimizationData?.daily_peak_series
        );
        const sourcePoints: { date: string; power_kw: number }[] = [];

        if (normalizedDailyPeaks.length > 0) {
            for (const p of normalizedDailyPeaks) {
                sourcePoints.push({ date: p.date, power_kw: p.power_kw });
            }
        } else {
            for (const p of sessionSeries) {
                sourcePoints.push({ date: p.date, power_kw: p.power_kw });
            }
        }
        return aggregateMonthlyPeaks(sourcePoints);
    }

    function buildForecastMonthlyPeaks(historical: MonthlyBucket[]): MonthlyBucket[] {
        const projectionPoints = shortfallDailyProjection
            .filter((point) => Number.isFinite(point.simulated_peak_kw) && !!point.date)
            .map((point) => ({ date: point.date, simulated_peak_kw: point.simulated_peak_kw }));

        const buckets = aggregateMonthlyPeaks(projectionPoints);

        // 예측 버킷이 부족하면 과거 월별 평균/최댓값 기반으로 확장
        const anchorSource = historical.length > 0 ? historical : buckets;
        const meanRecent = (() => {
            if (anchorSource.length === 0) return 0;
            const recent = anchorSource.slice(-Math.min(6, anchorSource.length));
            const sum = recent.reduce((acc, b) => acc + b.peak_kw, 0);
            return recent.length > 0 ? sum / recent.length : 0;
        })();

        const startDate = (() => {
            if (buckets.length > 0) {
                const last = new Date(buckets[buckets.length - 1].date);
                return new Date(last.getFullYear(), last.getMonth() + 1, 1);
            }
            if (historical.length > 0) {
                const last = new Date(historical[historical.length - 1].date);
                return new Date(last.getFullYear(), last.getMonth() + 1, 1);
            }
            const now = new Date();
            return new Date(now.getFullYear(), now.getMonth() + 1, 1);
        })();

        const extended = [...buckets];
        while (extended.length < FUTURE_FORECAST_MONTHS && meanRecent > 0) {
            const next = new Date(startDate.getFullYear(), startDate.getMonth() + (extended.length - buckets.length), 1);
            extended.push({
                key: monthKeyFromDate(next),
                date: firstDayOfMonthKey(monthKeyFromDate(next)),
                peak_kw: Number(meanRecent.toFixed(2))
            });
        }

        return extended.slice(0, FUTURE_FORECAST_MONTHS);
    }

    function createMonthlyTimeSeriesChart() {
        if (!timeSeriesCanvas || !ChartCtor) {
            return;
        }

        const textColor = isDarkMode ? '#e2e8f0' : '#1f2937';
        const gridColor = isDarkMode ? 'rgba(148, 163, 184, 0.2)' : 'rgba(0, 0, 0, 0.08)';

        const historical = buildHistoricalMonthlyPeaks();
        const forecast = buildForecastMonthlyPeaks(historical);

        if (historical.length === 0 && forecast.length === 0) {
            return;
        }

        const manualKw = selectedContractKw ?? optimalCandidate?.contract_kw ?? null;
        const currentContractKw = optimizationData?.current_contract_kw ?? null;

        const historicalPoints = historical.map((b) => ({ x: new Date(b.date).getTime(), y: b.peak_kw }));
        const forecastPoints = forecast.map((b) => ({ x: new Date(b.date).getTime(), y: b.peak_kw }));

        // 일별 원본 실측 피크 (과거) — 백그라운드 참조용
        const rawDailyHistorical = (() => {
            const normalizedDailyPeaks = normalizeDailyPeakSeries(optimizationData?.daily_peak_series);
            if (normalizedDailyPeaks.length > 0) {
                return normalizedDailyPeaks.map((p) => ({ x: new Date(p.date).getTime(), y: p.power_kw }));
            }
            const dailyMap = new Map<string, number>();
            for (const point of sessionSeries) {
                const d = new Date(point.date);
                const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
                const prev = dailyMap.get(key) ?? 0;
                if (point.power_kw > prev) dailyMap.set(key, point.power_kw);
            }
            return Array.from(dailyMap.entries())
                .map(([key, value]) => ({ x: new Date(key).getTime(), y: value }))
                .sort((a, b) => a.x - b.x);
        })();

        // 일별 예측 피크 (향후) — P90(대표값) + p10/p90 신뢰구간
        const rawDailyForecast = shortfallDailyProjection
            .filter((p) => p?.date && Number.isFinite(p.simulated_peak_kw))
            .map((p) => {
                const x = new Date(p.date).getTime();
                const p50 = Number.isFinite(p.p50_kw) ? (p.p50_kw as number) : p.simulated_peak_kw;
                const p95 = Number.isFinite(p.p95_kw) ? (p.p95_kw as number) : p50;
                const p10 = Number.isFinite(p.p10_kw) ? (p.p10_kw as number) : p50;
                const p90 = Number.isFinite(p.p90_kw) ? (p.p90_kw as number) : p95;
                return { x, y: p90, p10, p50, p95, std: Number(p.std_kw ?? 0) };
            })
            .sort((a, b) => a.x - b.x);

        const dailyForecastUpper = rawDailyForecast.map((p) => ({ x: p.x, y: p.y }));
        const dailyForecastLower = rawDailyForecast.map((p) => ({ x: p.x, y: Math.max(0, p.p10) }));
        const hasBackendBand = rawDailyForecast.some((p) => p.p10 < p.y);

        const historicalPeakValue = historicalPoints.length > 0
            ? Math.max(...historicalPoints.map((p) => p.y))
            : 0;
        const forecastPeakValue = forecastPoints.length > 0
            ? Math.max(...forecastPoints.map((p) => p.y))
            : 0;

        const annotations: Record<string, any> = {};
        if (manualKw !== null) {
            annotations.contractLine = {
                type: 'line',
                yMin: manualKw,
                yMax: manualKw,
                borderColor: '#f97316',
                borderWidth: 2,
                borderDash: [6, 4],
                label: {
                    content: `계약선: ${manualKw}kW`,
                    display: true,
                    position: 'end',
                    backgroundColor: '#f97316',
                    color: '#fff',
                    font: { size: 11, weight: 'bold' }
                }
            };
        }
        if (currentContractKw !== null && currentContractKw !== manualKw) {
            annotations.currentContractLine = {
                type: 'line',
                yMin: currentContractKw,
                yMax: currentContractKw,
                borderColor: '#22c55e',
                borderWidth: 1.5,
                borderDash: [4, 4],
                label: {
                    content: `현재 계약선: ${currentContractKw}kW`,
                    display: true,
                    position: 'start',
                    backgroundColor: '#22c55e',
                    color: '#0f172a',
                    font: { size: 10, weight: 'bold' }
                }
            };
        }

        // 예측 기간 배경 음영
        if (forecastPoints.length > 0) {
            const forecastStartX = forecastPoints[0].x;
            const forecastEndX = forecastPoints[forecastPoints.length - 1].x;
            annotations.forecastBand = {
                type: 'box',
                xMin: forecastStartX,
                xMax: forecastEndX,
                backgroundColor: 'rgba(59, 130, 246, 0.06)',
                borderColor: 'rgba(59, 130, 246, 0.15)',
                borderWidth: 1,
                label: {
                    content: '향후 예측 구간',
                    display: true,
                    position: { x: 'center', y: 'start' },
                    backgroundColor: 'rgba(59, 130, 246, 0.85)',
                    color: '#fff',
                    font: { size: 10, weight: 'bold' }
                }
            };
        }

        // 앙상블 최종 예측(카드 값) 수평 기준선 — 차트 예측과 카드 값의 정합을 시각화
        const cardFinalPrediction = ensemblePrediction?.final_prediction_kw ?? null;
        if (cardFinalPrediction !== null && Number.isFinite(cardFinalPrediction)) {
            annotations.cardFinalPredictionLine = {
                type: 'line',
                yMin: cardFinalPrediction,
                yMax: cardFinalPrediction,
                borderColor: '#7c3aed',
                borderWidth: 1.5,
                borderDash: [2, 3],
                label: {
                    content: `앙상블 최종 예측 ${cardFinalPrediction.toFixed(1)}kW (P95)`,
                    display: true,
                    position: 'start',
                    backgroundColor: '#7c3aed',
                    color: '#fff',
                    font: { size: 10, weight: 'bold' }
                }
            };
        }

        const rawHistoricalMax = rawDailyHistorical.length > 0 ? Math.max(...rawDailyHistorical.map((p) => p.y)) : 0;
        const rawForecastMax = dailyForecastUpper.length > 0 ? Math.max(...dailyForecastUpper.map((p) => p.y)) : 0;
        const referenceMax = Math.max(
            historicalPeakValue,
            forecastPeakValue,
            rawHistoricalMax,
            rawForecastMax,
            manualKw ?? 0,
            currentContractKw ?? 0
        );
        const ySuggestedMax = referenceMax > 0 ? referenceMax * 1.12 : undefined;

        const datasets: any[] = [];

        // 1. 일별 원본 실측 피크 (메인 시계열)
        if (rawDailyHistorical.length > 0) {
            datasets.push({
                label: '일별 실측 피크 (과거)',
                data: rawDailyHistorical,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.08)',
                borderWidth: 1.6,
                pointRadius: 2,
                pointHoverRadius: 5,
                tension: 0.15,
                fill: false,
                order: 3,
                parsing: false
            });
        }

        // 2. 향후 일별 예측 신뢰구간 (p10 ~ p90)
        if (rawDailyForecast.length > 0 && hasBackendBand) {
            datasets.push({
                label: '예측 신뢰구간 상단 (p90)',
                data: dailyForecastUpper,
                borderColor: 'rgba(251, 113, 133, 0)',
                backgroundColor: 'rgba(251, 113, 133, 0.14)',
                borderWidth: 0,
                pointRadius: 0,
                pointHoverRadius: 0,
                tension: 0.25,
                fill: '+1',
                order: 6,
                parsing: false
            });
            datasets.push({
                label: '예측 신뢰구간 하단 (p10)',
                data: dailyForecastLower,
                borderColor: 'rgba(251, 113, 133, 0)',
                backgroundColor: 'rgba(251, 113, 133, 0.0)',
                borderWidth: 0,
                pointRadius: 0,
                pointHoverRadius: 0,
                tension: 0.25,
                fill: false,
                order: 6,
                parsing: false
            });
        }

        // 3. 향후 일별 예측 P90 (상위 10% 수준 — 보조 상한선)
        if (rawDailyForecast.length > 0) {
            datasets.push({
                label: '일별 예측 P90 (향후)',
                data: rawDailyForecast.map((p) => ({ x: p.x, y: p.y })),
                borderColor: 'rgba(251, 113, 133, 0.75)',
                backgroundColor: 'rgba(251, 113, 133, 0.12)',
                borderWidth: 1.2,
                borderDash: [4, 3],
                pointRadius: 1.5,
                pointHoverRadius: 4,
                tension: 0.15,
                fill: false,
                order: 4,
                parsing: false
            });
        }

        // 3-1. 향후 일별 예측 P50 (중앙값 — 메인 예측 시계열, 강조)
        if (rawDailyForecast.length > 0) {
            datasets.push({
                label: '일별 예측 P50 (중앙값)',
                data: rawDailyForecast.map((p) => ({ x: p.x, y: p.p50 })),
                borderColor: '#0ea5e9',
                backgroundColor: '#0ea5e9',
                borderWidth: 2.6,
                pointRadius: 3.5,
                pointHoverRadius: 6,
                pointBackgroundColor: '#0ea5e9',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 1.5,
                tension: 0.2,
                fill: false,
                order: 2,
                parsing: false
            });
        }

        // 4. 월별 실측 피크 — 마커만 (일별 선을 가리지 않도록)
        datasets.push({
            label: '월별 실측 피크',
            data: historicalPoints,
            borderColor: '#047857',
            backgroundColor: historicalPoints.map((p) =>
                p.y === historicalPeakValue ? '#ef4444' : '#047857'
            ),
            borderWidth: 2,
            pointRadius: historicalPoints.map((p) => (p.y === historicalPeakValue ? 9 : 6)),
            pointHoverRadius: 10,
            pointStyle: 'triangle',
            showLine: false,
            order: 1,
            parsing: false
        });

        // 5. 월별 예측 피크 — 마커 + 연결선으로 강조
        datasets.push({
            label: '월별 예측 피크',
            data: forecastPoints,
            borderColor: '#1d4ed8',
            backgroundColor: forecastPoints.map((p) =>
                p.y === forecastPeakValue ? '#ef4444' : '#1d4ed8'
            ),
            borderWidth: 3,
            borderDash: [8, 4],
            pointRadius: forecastPoints.map((p) => (p.y === forecastPeakValue ? 9 : 6)),
            pointHoverRadius: 10,
            pointBorderColor: '#1d4ed8',
            pointBorderWidth: 2,
            pointStyle: 'rectRot',
            tension: 0.3,
            fill: false,
            showLine: true,
            order: 1,
            parsing: false
        });

        timeSeriesChartInstance = new ChartCtor(timeSeriesCanvas, {
            type: 'line',
            data: { datasets },
            options: {
                parsing: false,
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'nearest', intersect: false },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            tooltipFormat: 'yyyy-MM-dd',
                            minUnit: 'day',
                            displayFormats: {
                                day: 'MM-dd',
                                week: 'MM-dd',
                                month: 'yyyy-MM'
                            }
                        },
                        adapters: { date: {} },
                        ticks: { color: textColor, maxRotation: 0, autoSkip: true, autoSkipPadding: 18 },
                        grid: { color: gridColor },
                        title: {
                            display: true,
                            text: '날짜',
                            color: textColor,
                            font: { size: 13, weight: 'bold' }
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: '월별 최고 전력 (kW)',
                            color: textColor,
                            font: { size: 13, weight: 'bold' }
                        },
                        suggestedMax: ySuggestedMax,
                        ticks: { color: textColor },
                        grid: { color: gridColor }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        labels: { color: textColor, font: { size: 12 } }
                    },
                    tooltip: {
                        callbacks: {
                            title: (items) => {
                                const x = items[0]?.parsed?.x;
                                if (!x) return '';
                                const label = items[0]?.dataset?.label ?? '';
                                const isMonthly = label.startsWith('월별');
                                const d = new Date(x);
                                return isMonthly
                                    ? monthLabelFromKey(monthKeyFromDate(d))
                                    : d.toLocaleDateString('ko-KR');
                            },
                            label: (context) => {
                                const value = context.parsed?.y;
                                if (value === null || value === undefined || Number.isNaN(value)) return '';
                                const formatted = Number(value).toFixed(1);
                                const label = context.dataset?.label ?? '';
                                if (label.startsWith('예측 신뢰구간')) {
                                    return `${label}: ${formatted} kW`;
                                }
                                const isPeak =
                                    (label === '월별 실측 피크' && value === historicalPeakValue) ||
                                    (label === '월별 예측 피크' && value === forecastPeakValue);
                                const peakMark = isPeak ? ' 🔺 최고' : '';
                                return `${label}: ${formatted} kW${peakMark}`;
                            }
                        },
                        backgroundColor: isDarkMode ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)',
                        titleColor: textColor,
                        bodyColor: textColor,
                        borderColor: isDarkMode ? '#475569' : '#e5e7eb',
                        borderWidth: 1
                    },
                    annotation: { annotations },
                    zoom: {
                        limits: (() => {
                            const allX: number[] = [
                                ...rawDailyHistorical.map((p) => p.x),
                                ...rawDailyForecast.map((p) => p.x),
                                ...historicalPoints.map((p) => p.x),
                                ...forecastPoints.map((p) => p.x)
                            ];
                            if (allX.length === 0) return undefined;
                            const minX = Math.min(...allX);
                            const maxX = Math.max(...allX);
                            return {
                                x: {
                                    min: minX,
                                    max: maxX,
                                    minRange: 7 * 24 * 60 * 60 * 1000 // 최소 줌 범위: 1주
                                }
                            };
                        })(),
                        zoom: {
                            wheel: { enabled: true, speed: 0.12 },
                            pinch: { enabled: true },
                            drag: { enabled: false },
                            mode: 'x'
                        },
                        pan: {
                            enabled: true,
                            mode: 'x'
                        }
                    }
                }
            }
        });
    }

    function createValidationChart(manualKw: number | null, currentContractKw: number | null) {
        if (!timeSeriesCanvas || !ChartCtor || !validationData) {
            console.log('[ContractOptimizationChart] Skipping createValidationChart - missing:', {
                canvas: !!timeSeriesCanvas,
                chart: !!ChartCtor,
                data: !!validationData
            });
            return;
        }

        console.log('[ContractOptimizationChart] Creating validation chart with data:', validationData.data_split);
        if (manualKw !== null) {
            console.log(`[검증차트] ${manualKw}kW 계약 선택, 예상초과=${activeShortfallScenario?.expected_overshoot_kw || 0}kW`);
        }

        const textColor = isDarkMode ? '#e2e8f0' : '#1f2937';
        const gridColor = isDarkMode ? 'rgba(148, 163, 184, 0.2)' : 'rgba(0, 0, 0, 0.08)';

        // 학습 기간 실제 데이터 (train_visualization_data 사용)
        const trainData = (validationData.train_visualization_data || []).map((item: any) => ({
            x: new Date(item.date).getTime(),
            y: item.actual_peak_kw
        }));

        // 테스트 기간 실제 데이터
        const testActualData = validationData.visualization_data.map((item: any) => ({
            x: new Date(item.date).getTime(),
            y: item.actual_peak_kw
        }));

        // 테스트 기간 예측 데이터는 원본 피크를 그대로 사용
        const testPredictedOriginal = validationData.visualization_data.map((item: any) => ({
            x: new Date(item.date).getTime(),
            y: item.predicted_peak_kw,
            yOriginal: item.predicted_peak_kw
        }));

        const testPredictedData = testPredictedOriginal.map((item: any) => ({
            x: item.x,
            y: item.yOriginal
        }));

        // 학습/테스트 구간 날짜
        // const trainEndDate = validationData.data_split?.train_end_date || '2024-09-30';
        // const testStartDate = validationData.data_split?.test_start_date || '2024-10-01';
        const trainEndDate = validationData.data_split?.train_end_date;
        const testStartDate = validationData.data_split?.test_start_date;

        // 초과 영역 데이터 (실제 데이터가 계약선을 넘는 부분만)
        const overshootAreaData = manualKw !== null
            ? testActualData.map(p => ({
                x: p.x,
                y: p.y > manualKw ? p.y : null
            }))
            : [];

        const datasets: any[] = [
            {
                label: `실제 피크 (${trainEndDate}까지 학습 데이터)`,
                data: trainData,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 4,
                tension: 0.2,
                fill: false,
                order: 3
            },
            {
                label: `실제 피크 (${testStartDate}부터 테스트)`,
                data: testActualData,
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                borderWidth: 2.5,
                pointRadius: 3,
                pointHoverRadius: 5,
                tension: 0.2,
                fill: false,
                order: 1,
                borderDash: []
            },
            {
                label: `예측 피크 (${testStartDate}부터)`,
                data: testPredictedData,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 4,
                tension: 0.3,
                fill: false,
                order: 2,
                borderDash: [5, 5]
            }
        ];

        // 초과 영역 음영 추가
        if (manualKw !== null && overshootAreaData.some(p => p.y !== null)) {
            datasets.push({
                label: '계약전력 초과 영역',
                data: overshootAreaData,
                borderColor: 'rgba(248, 113, 113, 0)',
                backgroundColor: 'rgba(248, 113, 113, 0.25)',
                pointRadius: 0,
                pointHoverRadius: 0,
                tension: 0.3,
                borderWidth: 0,
                fill: { target: { value: manualKw } },
                order: 0,
                spanGaps: true
            });
        }

        const splitLineDate = new Date(testStartDate).getTime();
        const annotations: Record<string, any> = {
            trainTestSplit: {
                type: 'line',
                xMin: splitLineDate,
                xMax: splitLineDate,
                borderColor: '#f59e0b',
                borderWidth: 2,
                borderDash: [10, 5],
                label: {
                    content: `${trainEndDate}까지 학습 → ${testStartDate}부터 예측`,
                    display: true,
                    position: 'start',
                    backgroundColor: '#f59e0b',
                    color: 'white',
                    font: { size: 11, weight: 'bold' }
                }
            }
        };

        if (manualKw !== null && manualKw !== undefined) {
            annotations.contractLine = {
                type: 'line',
                yMin: manualKw,
                yMax: manualKw,
                borderColor: '#f97316',
                borderWidth: 2,
                borderDash: [6, 4],
                label: {
                    content: `선택 계약선: ${manualKw}kW`,
                    display: true,
                    position: 'start',
                    backgroundColor: '#f97316',
                    color: '#fff',
                    font: { size: 10, weight: 'bold' }
                }
            };
        }

        if (currentContractKw !== null && currentContractKw !== undefined) {
            annotations.currentContractLine = {
                type: 'line',
                yMin: currentContractKw,
                yMax: currentContractKw,
                borderColor: '#22c55e',
                borderWidth: 1.5,
                borderDash: [4, 4],
                label: {
                    content: `현재 계약선: ${currentContractKw}kW`,
                    display: true,
                    position: 'end',
                    backgroundColor: '#22c55e',
                    color: '#0f172a',
                    font: { size: 10, weight: 'bold' }
                }
            };
        }

        const yValues = [
            ...trainData.map((p: any) => p.y),
            ...testActualData.map((p: any) => p.y),
            ...testPredictedData.map((p: any) => p.y),
            manualKw ?? null,
            currentContractKw ?? null
        ].filter((v) => Number.isFinite(v)) as number[];
        const ySuggestedMax = yValues.length ? Math.max(...yValues) * 1.08 : undefined;

        timeSeriesChartInstance = new ChartCtor(timeSeriesCanvas, {
            type: 'line',
            data: { datasets },
            options: {
                parsing: false,
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'nearest',
                    intersect: false
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            tooltipFormat: 'yyyy-MM-dd',
                            unit: 'day',
                            displayFormats: {
                                day: 'MM-dd',
                                month: 'yyyy-MM'
                            }
                        },
                        ticks: {
                            color: textColor
                        },
                        grid: {
                            color: gridColor
                        },
                        title: {
                            display: true,
                            text: '날짜',
                            color: textColor,
                            font: { size: 13, weight: 'bold' }
                        }
                    },
                    y: {
                        suggestedMax: ySuggestedMax,
                        title: {
                            display: true,
                            text: '전력 (kW)',
                            color: textColor,
                            font: { size: 13, weight: 'bold' }
                        },
                        ticks: {
                            color: textColor
                        },
                        grid: {
                            color: gridColor
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: textColor,
                            usePointStyle: true,
                            padding: 15,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            title: items => items[0]?.parsed?.x ? new Date(items[0].parsed.x).toLocaleDateString('ko-KR') : '',
                            label: context => {
                                const value = context.parsed?.y;
                                if (value === null || value === undefined) return '';
                                const label = context.dataset?.label ?? '';
                                return `${label}: ${value.toFixed(1)} kW`;
                            }
                        },
                        backgroundColor: isDarkMode ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)',
                        titleColor: textColor,
                        bodyColor: textColor,
                        borderColor: isDarkMode ? '#475569' : '#e5e7eb',
                        borderWidth: 1
                    },
                    annotation: {
                        annotations
                    },
                    zoom: {
                        zoom: {
                            wheel: {
                                enabled: true
                            },
                            pinch: {
                                enabled: true
                            },
                            mode: 'x'
                        },
                        pan: {
                            enabled: true,
                            mode: 'x'
                        }
                    }
                }
            }
        });
    }

    // 다크모드 변경 감지
    function setupDarkModeListener() {
        if (typeof window === 'undefined') return;
        
        // MutationObserver로 dark 클래스 변경 감지
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'class') {
                    const newDarkMode = detectDarkMode();
                    if (newDarkMode !== isDarkMode) {
                        isDarkMode = newDarkMode;
                        createChart();
                        createTimeSeriesChart();
                    }
                }
            });
        });
        
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['class']
        });
        
        // 시스템 설정 변경 감지
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        const handleChange = (e: MediaQueryListEvent | MediaQueryList) => {
            const matches = 'matches' in e ? e.matches : mediaQuery.matches;
            isDarkMode = matches;
            createChart();
            createTimeSeriesChart();
        };
        if (typeof mediaQuery.addEventListener === 'function') {
            mediaQuery.addEventListener('change', handleChange as EventListener);
        } else if (typeof mediaQuery.addListener === 'function') {
            mediaQuery.addListener(handleChange as any);
        }
        
        return () => {
            observer.disconnect();
            if (typeof mediaQuery.removeEventListener === 'function') {
                mediaQuery.removeEventListener('change', handleChange as EventListener);
            } else if (typeof mediaQuery.removeListener === 'function') {
                mediaQuery.removeListener(handleChange as any);
            }
        };
    }
    
    onMount(() => {
        isDarkMode = detectDarkMode();
        // validation 데이터 먼저 가져오기
        fetchValidationData();
        ensureChartModules().then(() => {
            createChart();
            createTimeSeriesChart();
        });
        const cleanup = setupDarkModeListener();

        return cleanup;
    });
    
    onDestroy(() => {
        if (chartInstance) {
            chartInstance.destroy();
        }
        if (timeSeriesChartInstance) {
            timeSeriesChartInstance.destroy();
        }
    });
    
    // 데이터 변경 시 차트 업데이트
    $: if (predictionDistribution.length > 0 && chartCanvas && chartReady) {
        manualCandidate;
        isManualUndershoot;
        isManualOvershoot;
        projectedPeakKw;
        lstmProjection;
        createChart();
    }

    $: sessionSeries = normalizeSessionSeries(optimizationData?.session_power_series);
    $: sessionPredictionSeries = normalizeSessionSeries(optimizationData?.session_prediction_series);
    $: combinedSessionSeries = [...sessionSeries, ...sessionPredictionSeries];
    $: sessionDomain = computeSessionDomain(combinedSessionSeries);
    $: hasSessionTimeline = combinedSessionSeries.length > 0;

    $: if (chartReady && timeSeriesCanvas) {
        sessionSeries;
        sessionPredictionSeries;
        combinedSessionSeries;
        hasSessionTimeline;
        sessionDomain;
        shortfallDailyProjection;
        activeShortfallScenario;
        isDarkMode;
        manualCandidate;
        optimalCandidate;
        validationData;
        createTimeSeriesChart();
    }
    
    $: histogram = generateHistogram(predictionDistribution);
    $: q5 = percentile(predictionDistribution, 5);
    $: q95 = percentile(predictionDistribution, 95);
    $: q90 = percentile(predictionDistribution, 90);
    $: historicalMax = safeMax(predictionDistribution);
    $: projectedPeakKw = Math.max(percentile(predictionDistribution, 99), historicalMax || 0);
    $: optimalCandidate = optimizationData?.optimal_candidate ? normalizeCandidate(optimizationData.optimal_candidate) : null;
    $: allCandidates = Array.isArray(optimizationData?.all_candidates)
        ? optimizationData.all_candidates
            .map(normalizeCandidate)
            .filter((candidate): candidate is ContractCandidateDetail => candidate !== null)
        : [];
    $: decisionBasisRows = buildDecisionBasisRows(allCandidates);
    $: bestDecisionBasis = (() => {
        if (!decisionBasisRows.length) {
            return null;
        }
        const optimalKw = optimalCandidate?.contract_kw;
        if (optimalKw !== null && optimalKw !== undefined) {
            const matched = decisionBasisRows.find((row) => row.contractKw === optimalKw);
            if (matched) {
                return matched;
            }
        }
        return decisionBasisRows[0];
    })();
    $: runnerUpDecisionBasis = (() => {
        if (!decisionBasisRows.length || !bestDecisionBasis) {
            return null;
        }
        return decisionBasisRows.find((row) => row.contractKw !== bestDecisionBasis.contractKw) ?? null;
    })();
    $: selectedDecisionBasis = selectedContractKw !== null
        ? decisionBasisRows.find((row) => row.contractKw === selectedContractKw) ?? null
        : null;
    $: scenarioRows = buildScenarioRows(
        allCandidates,
        optimalCandidate?.contract_kw ?? null,
        shortfallScenarios,
        optimizationData?.current_contract_kw ?? null
    );
    // 후보표(scenarioRows)에서 해당 계약을 찾고, 없으면(예: 초과최소안 100kW가 후보 범위 밖)
    // 백엔드 recommendation_options 값으로 행을 합성해 카드와 정확히 같은 값을 보장한다.
    function rowForContract(kw: number | null | undefined, optInfo: any): ScenarioRow | null {
        if (kw === null || kw === undefined) return null;
        const found = scenarioRows.find((r) => r.contractKw === kw);
        if (found) return found;
        if (!optInfo) return null;
        const over = Number(optInfo.overage_probability) || 0;
        return {
            scenario: 'over', scenarioLabel: optInfo.label || '', contractKw: kw,
            baseMonthly: 0, overCostMonthly: 0, shortageMonthly: 0, ratchetingMonthly: 0,
            totalLossMonthly: (Number(optInfo.annual_cost) || 0) / 12,
            monthlySavings: 0,
            overageProbability: over, modelOverageProbability: over, sessionOverageProbability: null,
            score: 0, normalizedCost: 0, riskScore: 0, scoreReason: ''
        };
    }
    // [주의] 변수명은 유지하되 의미를 통일: monthlyLossMinRow = '균형 최적안', balancedOptimalRow = '초과 최소안'
    // (EnsemblePrediction 카드의 이중 추천과 동일한 2안·동일 값으로 표시)
    $: monthlyLossMinRow = (() => {
        if (recommendationOptions?.cost_optimal) {
            const r = rowForContract(recommendationOptions.cost_optimal.contract_kw, recommendationOptions.cost_optimal);
            if (r) return r;
        }
        if (!scenarioRows.length) return null;
        if (bestDecisionBasis) return scenarioRows.find((row) => row.contractKw === bestDecisionBasis.contractKw) ?? scenarioRows[0];
        return scenarioRows.reduce((best, row) => (row.score < best.score ? row : best), scenarioRows[0]);
    })();
    $: balancedOptimalRow = (() => {
        if (recommendationOptions?.overage_minimized) {
            const r = rowForContract(recommendationOptions.overage_minimized.contract_kw, recommendationOptions.overage_minimized);
            if (r) return r;
        }
        if (!scenarioRows.length) return null;
        return scenarioRows.reduce((best, row) => (row.overageProbability < best.overageProbability ? row : best), scenarioRows[0]);
    })();
    $: if (detailCategory === 'loss' && !monthlyLossMinRow) {
        detailCategory = 'compare';
    }
    $: if (detailCategory === 'balanced' && !balancedOptimalRow) {
        detailCategory = 'compare';
    }
    $: if (allCandidates.length > 0) {
        const defaultKw = optimalCandidate?.contract_kw ?? allCandidates[0].contract_kw;
        const hasSelection = selectedContractKw !== null && allCandidates.some(candidate => candidate.contract_kw === selectedContractKw);
        if (!hasSelection) {
            selectedContractKw = defaultKw;
        }
    } else {
        selectedContractKw = null;
    }
    $: manualCandidate = selectedContractKw !== null
        ? allCandidates.find(candidate => candidate.contract_kw === selectedContractKw) || null
        : null;
    $: isManualUndershoot = (() => {
        const kw = selectedContractKw;
        const overProb = manualCandidate
            ? (manualCandidate.session_overage_probability ?? manualCandidate.overage_probability ?? 0)
            : 0;
        if (overProb > 30) return true;
        if (kw === null) return false;
        return kw < q90;
    })();
    $: isManualOvershoot = (() => {
        const kw = selectedContractKw;
        const wasteProb = manualCandidate
            ? (manualCandidate.session_waste_probability ?? manualCandidate.waste_probability ?? 0)
            : 0;
        if (wasteProb > 30) return true;
        if (kw === null) return false;
        return kw > q95;
    })();
    $: shortfallScenarios = Array.isArray(optimizationData?.contract_shortfall_simulations)
        ? optimizationData.contract_shortfall_simulations
        : [];
    $: targetContractKw = selectedContractKw ?? optimalCandidate?.contract_kw ?? null;
    $: activeShortfallScenario = findShortfallScenario(
        shortfallScenarios,
        targetContractKw
    );
    $: {
        console.log('[ContractOptimizationChart] targetContractKw:', targetContractKw);
        console.log('[ContractOptimizationChart] activeShortfallScenario:', activeShortfallScenario);
        console.log('[ContractOptimizationChart] shortfallScenarios:', shortfallScenarios);
    }
    // "예측 피크 평균/P90"은 계약 후보값과 독립적이어야 하므로
    // 백엔드의 model_peak_avg_kw / model_peak_p90_kw (= 모델 분포 통계)를 우선 사용.
    // 이전 공식 (targetContractKw + expected_overshoot_kw)은 계약 미만 영역에서
    // overshoot=0이라 결국 계약값 자체를 표시하는 문제가 있었음.
    $: scenarioPredictedPeakAvg = (() => {
        if (activeShortfallScenario?.model_peak_avg_kw !== undefined && activeShortfallScenario.model_peak_avg_kw !== null) {
            return Number(activeShortfallScenario.model_peak_avg_kw.toFixed(2));
        }
        if (predictionDistribution.length) {
            const mean = predictionDistribution.reduce((sum, v) => sum + v, 0) / predictionDistribution.length;
            return Number(mean.toFixed(2));
        }
        return null;
    })();
    $: scenarioPredictedPeakP90 = (() => {
        if (activeShortfallScenario?.model_peak_p90_kw !== undefined && activeShortfallScenario.model_peak_p90_kw !== null) {
            return Number(activeShortfallScenario.model_peak_p90_kw.toFixed(2));
        }
        if (predictionDistribution.length) {
            return Number(percentile(predictionDistribution, 90).toFixed(2));
        }
        return null;
    })();
    $: scenarioP50 = predictionDistribution.length
        ? Number(percentile(predictionDistribution, 50).toFixed(2))
        : null;
    $: scenarioOverageProbability = targetContractKw !== null && predictionDistribution.length
        ? Number(
            (
                (predictionDistribution.filter(value => Number.isFinite(value) && value > targetContractKw).length /
                    predictionDistribution.length) *
                100
            ).toFixed(2)
        )
        : null;
    $: shortfallDailyProjection = normalizeShortfallProjection(activeShortfallScenario?.daily_projection);
    $: futureProjectionPreview = shortfallDailyProjection.slice(0, 7);
    $: futureMonthlyProjection = (() => {
        if (!Array.isArray(shortfallDailyProjection) || shortfallDailyProjection.length === 0) {
            return [];
        }
        const buckets = new Map<string, { peak: number; p10Peak: number; p90Peak: number; maxOvershoot: number; riskSum: number; riskCount: number; firstDate: string }>();
        for (const point of shortfallDailyProjection) {
            if (!point?.date || !Number.isFinite(point.simulated_peak_kw)) continue;
            const parsed = new Date(point.date);
            if (Number.isNaN(parsed.getTime())) continue;
            const key = monthKeyFromDate(parsed);
            const entry = buckets.get(key) ?? { peak: 0, p10Peak: Number.POSITIVE_INFINITY, p90Peak: 0, maxOvershoot: 0, riskSum: 0, riskCount: 0, firstDate: firstDayOfMonthKey(key) };
            if (point.simulated_peak_kw > entry.peak) entry.peak = point.simulated_peak_kw;
            const p10Val = Number(point.p10_kw ?? point.simulated_peak_kw);
            const p90Val = Number(point.p90_kw ?? point.simulated_peak_kw);
            if (Number.isFinite(p10Val) && p10Val < entry.p10Peak) entry.p10Peak = p10Val;
            if (Number.isFinite(p90Val) && p90Val > entry.p90Peak) entry.p90Peak = p90Val;
            if (Number.isFinite(point.overshoot_kw) && point.overshoot_kw > entry.maxOvershoot) {
                entry.maxOvershoot = point.overshoot_kw;
            }
            const risk = Number(point.risk_factor ?? 0);
            if (Number.isFinite(risk)) {
                entry.riskSum += risk;
                entry.riskCount += 1;
            }
            buckets.set(key, entry);
        }
        return Array.from(buckets.entries())
            .map(([key, entry]) => ({
                key,
                date: entry.firstDate,
                peak_kw: entry.peak,
                p10_peak_kw: Number.isFinite(entry.p10Peak) ? entry.p10Peak : entry.peak,
                p90_peak_kw: entry.p90Peak || entry.peak,
                max_overshoot_kw: entry.maxOvershoot,
                avg_risk_factor: entry.riskCount > 0 ? entry.riskSum / entry.riskCount : 0
            }))
            .sort((a, b) => a.date.localeCompare(b.date))
            .slice(0, FUTURE_FORECAST_MONTHS);
    })();
    $: overfitSignal = computeOverfitSignal(sessionSeries, shortfallDailyProjection);

    $: if (manualCandidate && isManualUndershoot) {
        lstmProjection = buildLstmUndershootProjection(manualCandidate.contract_kw);
    } else {
        lstmProjection = [];
    }

    function handleCandidateSelect(contractKw: number | string) {
        const nextKw = toNumber(contractKw);
        if (nextKw === null || selectedContractKw === nextKw) {
            return;
        }
        selectedContractKw = nextKw;
    }
</script>

<div class="optimization-chart" bind:this={chartContainer}>
    <div class="chart-sections">
        <div class="section time-series">
            <div class="section-header">
                <div class="header-left">
                    <h4>순간전력 추이 — 일별 실측 · 월별 피크 · 향후 {FUTURE_FORECAST_MONTHS}개월 일별 예측 (신뢰구간 포함)</h4>
                </div>
                {#if hasSessionTimeline}
                    <div class="chart-actions">
                        <span class="zoom-hint">마우스 휠: 확대/축소 · 드래그: 좌우 이동 · 확대 시 일·주 단위 표시</span>
                    </div>
                {/if}
            </div>
            <p class="chart-stat-explain">
                <strong>하늘색 실선 = 일별 예측 P50 (중앙값)</strong>:
                해당 날짜에 발생할 것으로 가장 <strong>기대되는 피크 수준</strong>입니다. 실측 피크 평균과 비교하기에 가장 적합합니다.
                <strong>분홍 점선 = 일별 예측 P90 (보조)</strong>:
                상위 10% 수준 — 계약전력 결정 시 패널티 리스크를 피하기 위한 상한 기준으로 참고하세요.
                음영(p10 ~ p90)은 80% 확률 구간 — 예측 불확실성 폭을 보여줍니다.
                보라색 점선(카드의 P95)은 계약 결정 상한 기준선이며, 분포 기반의 별도 통계량이라 값이 약간 다른 것이 정상입니다.
            </p>

            {#if validationLoading}
                <div class="chart-wrapper time-domain-chart">
                    <div class="loading-state">
                        <div class="loading-spinner"></div>
                        <p>검증 데이터를 불러오는 중...</p>
                    </div>
                </div>
            {:else if hasSessionTimeline || validationData}
                <div class="chart-wrapper time-domain-chart">
                    <canvas bind:this={timeSeriesCanvas}></canvas>
                </div>

                {#if validationData && validationData.visualization_data}
                    <!-- 모델 검증 방식 설명 -->
                    <div class="validation-info-banner">
                        <div class="info-header">
                            <span class="info-icon">📊</span>
                            <h5>모델 검증: {validationData.data_split.train_end_date}까지 학습 → {validationData.data_split.test_start_date}부터 예측</h5>
                        </div>
                        <p class="info-description">
                            <strong class="highlight-green">녹색 실선</strong>: {validationData.data_split.train_end_date}까지의 <strong>실제 충전 피크</strong> (학습 데이터) <br/>
                            <strong class="highlight-red">빨간색 실선</strong>: {validationData.data_split.test_start_date}~{validationData.data_split.test_end_date}의 <strong>실제 충전 피크</strong> (테스트 데이터 - 실제 발생한 값) <br/>
                            <strong class="highlight-blue">파란색 점선</strong>: {validationData.data_split.train_end_date}까지 학습한 모델이 <strong>테스트 기간을 예측한 결과</strong>
                        </p>
                        <div class="validation-metrics">
                            <div class="metric-card">
                                <span class="metric-label">MAE (평균 절대 오차)</span>
                                <span class="metric-value">{validationData.validation_metrics.mae} kW</span>
                            </div>
                            <div class="metric-card">
                                <span class="metric-label">상대 오차</span>
                                <span class="metric-value">{validationData.validation_metrics.relative_error_percent.toFixed(1)}%</span>
                            </div>
                            <div class="metric-card">
                                <span class="metric-label">상관계수</span>
                                <span class="metric-value">{validationData.validation_metrics.correlation.toFixed(3)}</span>
                            </div>
                            <div class="metric-card">
                                <span class="metric-label">일관성</span>
                                <span class="metric-value consistency-{validationData.validation_metrics.consistency}">
                                    {validationData.validation_metrics.consistency}
                                </span>
                            </div>
                        </div>
                        <p class="info-note">
                            💡 <strong>용어 설명:</strong>
                            <strong>"실제 피크"</strong>는 충전소에서 실제로 측정된 일별 최대 전력이고,
                            <strong>"예측 피크"</strong>는 학습 구간(기본 80%)으로 학습한 AI 모델이 테스트 구간(기본 20%)에서 발생할 것으로 예상한 일별 최대 전력입니다.
                            빨간색과 파란색이 가까울수록 모델의 예측 정확도가 높습니다.
                        </p>
                    </div>
                {:else}
                    <p class="chart-footnote">
                        모든 충전 세션(실측 + 모델 예측)의 순간최대 전력을 시계열로
                        표현했습니다. 기본 뷰는 최근 3개월이며 확대/축소로 전체
                        기간을 탐색할 수 있습니다. 선택한 계약전력 시나리오가 있으면
                        예측 궤적이 계약선을 넘을 때 보라색 초과 영역으로 강조되어,
                        제한이 없을 경우 얼마나 초과할 수 있는지 직관적으로 확인할
                        수 있습니다.
                        {#if shortfallDailyProjection.length > 0}
                            {#if isManualOvershoot}
                                딥러닝 기반 예측 곡선(분홍색)과 여유 영역(녹색 음영)으로
                                과다 계약으로 인한 낭비 가능성을 시각화했습니다.
                            {:else}
                                딥러닝 기반 예측 곡선(분홍색)과 과소 위험 영역(붉은
                                음영)으로 계약선 초과 가능성을 강조했습니다.
                            {/if}
                        {/if}
                    </p>
                {/if}
                {#if overfitSignal.coverageDays >= 3}
                    <div
                        class="overfit-banner"
                        class:risk={overfitSignal.isRisk}
                    >
                        <div class="overfit-header">
                            <span class="status-chip"
                                >{overfitSignal.isRisk
                                    ? "과적합 의심"
                                    : "일관성 양호"}</span
                            >
                            <span class="overfit-meta">
                                MAE {overfitSignal.mae !== null
                                    ? `${overfitSignal.mae.toFixed(1)}kW`
                                    : "측정 불가"} · 비교 {overfitSignal.coverageDays}일
                                {#if overfitSignal.relativeError !== null}
                                    · 상대 오차 {(
                                        overfitSignal.relativeError * 100
                                    ).toFixed(1)}%
                                {/if}
                            </span>
                        </div>
                        <p>
                            {#if overfitSignal.isRisk}
                                최근 실측 패턴과 예측 추세가 다르게 움직여
                                과적합 가능성이 있습니다. 최신 데이터를
                                반영하거나 하이퍼파라미터를 조정해 주세요.
                            {:else}
                                예측 곡선이 실측 추세와 충분히 일치하여
                                안정적으로 일반화되고 있습니다.
                            {/if}
                        </p>
                    </div>
                {/if}
                {#if activeShortfallScenario && selectedContractKw !== null && shortfallDailyProjection.length > 0}
                    <div class="simulation-summary" class:overshoot={isManualOvershoot}>
                        <div class="summary-header">
                            <span
                                >{selectedContractKw}kW 기준 딥러닝 {isManualOvershoot ? '과다' : '과소'}
                                시뮬레이션</span
                            >
                            <span class="model-chip"
                                >{getModelLabel(
                                    activeShortfallScenario.model_source
                                )}</span
                            >
                        </div>
                        <div class="summary-grid">
                            {#if scenarioOverageProbability !== null}
                                <div class="summary-metric">
                                    <span>예측 분포 초과확률</span>
                                    <strong>{scenarioOverageProbability.toFixed(1)}%</strong>
                                </div>
                            {/if}
                            {#if scenarioP50 !== null}
                                <div class="summary-metric">
                                    <span>예측 피크 P50</span>
                                    <strong>{scenarioP50}kW</strong>
                                </div>
                            {/if}
                            {#if scenarioPredictedPeakAvg !== null}
                                <div class="summary-metric">
                                    <span>예측 피크 평균 (모델 분포)</span>
                                    <strong>{scenarioPredictedPeakAvg}kW</strong>
                                </div>
                            {/if}
                            {#if scenarioPredictedPeakP90 !== null}
                                <div class="summary-metric">
                                    <span>예측 피크 P90 (모델 분포)</span>
                                    <strong>{scenarioPredictedPeakP90}kW</strong>
                                </div>
                            {/if}
                            {#if isManualOvershoot}
                                {@const avgMargin = selectedContractKw - (activeShortfallScenario.expected_overshoot_kw || q95)}
                                {@const usageRate = selectedContractKw > 0 ? ((selectedContractKw - Math.max(0, avgMargin)) / selectedContractKw) * 100 : 0}
                                <div class="summary-metric">
                                    <span>계약 여유 발생일 비율</span>
                                    <strong
                                        >{(100 - activeShortfallScenario.overshoot_probability).toFixed(
                                            1
                                        )}%</strong
                                    >
                                </div>
                                <div class="summary-metric">
                                    <span>평균 여유 전력</span>
                                    <strong>{avgMargin.toFixed(1)}kW</strong>
                                </div>
                                <div class="summary-metric">
                                    <span>평균 사용률 (피크/계약)</span>
                                    <strong>{usageRate.toFixed(1)}%</strong>
                                </div>
                                <div class="summary-metric">
                                    <span>예상 월 낭비 비용</span>
                                    <strong
                                        >{formatManwon((manualCandidate?.session_expected_waste_cost ?? 0) / MONTHS_PER_YEAR)} 만원</strong
                                    >
                                </div>
                            {:else}
                                <div class="summary-metric">
                                    <span>과소 확률</span>
                                    <strong
                                        >{activeShortfallScenario.overshoot_probability.toFixed(
                                            1
                                        )}%</strong
                                    >
                                </div>
                                <div class="summary-metric">
                                    <span>예상 초과 폭 (평균)</span>
                                    <strong
                                        >{activeShortfallScenario.expected_overshoot_kw.toFixed(
                                            1
                                        )}kW</strong
                                    >
                                </div>
                                <div class="summary-metric">
                                    <span>P90 초과 폭</span>
                                    <strong
                                        >{activeShortfallScenario.p90_overshoot_kw.toFixed(
                                            1
                                        )}kW</strong
                                    >
                                </div>
                            {/if}
                        </div>
                        {#if futureMonthlyProjection.length > 0}
                            {@const monthlyPeakMax = Math.max(...futureMonthlyProjection.map((r) => r.peak_kw))}
                            <div class="future-projection-block">
                                <h6>향후 {futureMonthlyProjection.length}개월 일별 예측 요약 (신뢰구간 p10 ~ p90)</h6>
                                <p class="future-projection-note">
                                    각 월은 일별 예측의 월간 집계입니다. p10/p90은 LSTM MC Dropout 불확실성이 지평선 √t 확산된 값이며, 🔺 는 예측 기간 내 최고 피크 월입니다.
                                </p>
                                <div class="future-projection-table-wrap">
                                    <table class="future-projection-table">
                                        <thead>
                                            <tr>
                                                <th>월</th>
                                                <th>예측 피크 p50 (kW)</th>
                                                <th>신뢰구간 p10 ~ p90 (kW)</th>
                                                <th>최대 초과폭(kW)</th>
                                                <th>평균 리스크계수</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each futureMonthlyProjection as row}
                                                <tr class:peak-row={row.peak_kw === monthlyPeakMax}>
                                                    <td>{monthLabelFromKey(row.key)}</td>
                                                    <td>
                                                        {row.peak_kw.toFixed(1)}
                                                        {#if row.peak_kw === monthlyPeakMax}
                                                            <span class="peak-marker" title="예측 기간 내 최고 피크">🔺</span>
                                                        {/if}
                                                    </td>
                                                    <td>{row.p10_peak_kw.toFixed(1)} ~ {row.p90_peak_kw.toFixed(1)}</td>
                                                    <td>{row.max_overshoot_kw.toFixed(1)}</td>
                                                    <td>{row.avg_risk_factor.toFixed(2)}</td>
                                                </tr>
                                            {/each}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}
            {:else}
                <div class="empty-state">
                    세션 기반 피크 데이터가 부족하여 시계열 그래프를 표시할 수
                    없습니다.
                </div>
            {/if}
        </div>
    </div>

    <!-- Section 3: 비용 산정 테이블 -->
    <div class="section cost-table">
        <h4>확률 및 비용 산정 모듈</h4>
        <div class="table-info">
            <div class="info-badge">
                <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 10v5" />
                    <path d="M12 7h.01" />
                </svg>
                <span
                    >각 행을 클릭하면 선택한 계약전력 기준으로 그래프 상 선형
                    안내선이 갱신됩니다.</span
                >
            </div>
            <p class="table-explain"
                >시나리오 라벨은 최적안 대비 위치를 의미하며, 각 비용은 월별
                전력 분포 기반 기대값입니다.</p
            >
        </div>

        <!-- 1. 시나리오 테이블 -->
        <div class="scenario-table-container">
            <table class="scenario-table">
                <thead>
                    <tr>
                        <th>시나리오</th>
                        <th>계약전력</th>
                        <th
                            >월 기본요금<br /><small
                                >(kW당 {BASIC_RATE_LABEL}원)</small
                            ></th
                        >
                        <th>월 과다계약 비용</th>
                        <th>월 과소 계약 패널티 비용</th>
                        <th
                            >월 검침 상향 비용<br /><small
                                >(초과 시 12개월 기본요금 상향)</small
                            ></th
                        >
                        <th
                            >월 예상 비용<br /><small
                                >(과다 + 패널티 + 검침 상향)</small
                            ></th
                        >
                        <th
                            >월 절감액<br /><small
                                >(현재 계약 대비)</small
                            ></th
                        >
                        <th
                            >Score<br /><small
                                >(비용지수 + 리스크점수)</small
                            ></th
                        >
                    </tr>
                </thead>
                <tbody>
                    {#if scenarioRows.length === 0}
                        <tr>
                            <td colspan="9" class="empty-row"
                                >최적화 후보 데이터를 불러올 수 없습니다.</td
                            >
                        </tr>
                    {:else}
                        {#each scenarioRows as row}
                            <tr
                                class:optimal={row.scenario === "optimal"}
                                class:over={row.scenario === "over"}
                                class:under={row.scenario === "under"}
                                class:selected={row.contractKw ===
                                    selectedContractKw}
                                on:click={() =>
                                    handleCandidateSelect(row.contractKw)}
                            >
                                <td class="scenario-cell">
                                    <span class="scenario-tag"
                                        >{row.scenarioLabel}</span
                                    >
                                    {#if optimalCandidate}
                                        <small class="scenario-delta"
                                            >{formatScenarioDelta(
                                                row.contractKw,
                                                optimalCandidate.contract_kw
                                            )}</small
                                        >
                                    {/if}
                                </td>
                                <td>{row.contractKw}kW</td>
                                <td>약 {formatManwon(row.baseMonthly)} 만원</td>
                                <td
                                    >{row.overCostMonthly > 0
                                        ? `약 ${formatManwon(row.overCostMonthly)} 만원`
                                        : "-"}</td
                                >
                                <td
                                    >{row.shortageMonthly > 0
                                        ? `약 ${formatManwon(row.shortageMonthly)} 만원`
                                        : '-'}</td
                                >
                                <td class="ratcheting-cell"
                                    >{row.ratchetingMonthly > 0
                                        ? `약 ${formatManwon(row.ratchetingMonthly)} 만원`
                                        : '-'}</td
                                >
                                <td
                                    >{#if row.totalLossMonthly > 0}
                                        <div class="loss-main"
                                            >약 {formatManwon(
                                                row.totalLossMonthly
                                            )} 만원</div
                                        >
                                        <small class="loss-breakdown"
                                            >{formatManwon(
                                                row.overCostMonthly
                                            )} + {formatManwon(
                                                row.shortageMonthly
                                            )} + {formatManwon(
                                                row.ratchetingMonthly
                                            )}</small
                                        >
                                    {:else}
                                        -
                                    {/if}</td
                                >
                                <td class="savings-cell"
                                    class:savings-positive={row.monthlySavings > 0}
                                    class:savings-negative={row.monthlySavings < 0}
                                    class:savings-risky={row.monthlySavings > 0 && row.overageProbability >= 20}
                                    >{#if row.monthlySavings > 0}
                                        <div>약 {formatManwon(row.monthlySavings)} 만원 절감</div>
                                        {@const dual = formatDualProbability(row.modelOverageProbability, row.sessionOverageProbability)}
                                        {#if row.overageProbability >= 30}
                                            <small class="savings-risk-warn">⚠ 초과 확률 {dual.text} — 패널티·검침 상향 리스크 큼</small>
                                        {:else if row.overageProbability >= 20}
                                            <small class="savings-risk-note">초과 확률 {dual.text} — 리스크 주의</small>
                                        {:else if row.overageProbability >= 10}
                                            <small class="savings-risk-ok">초과 확률 {dual.text}</small>
                                        {:else}
                                            <small class="savings-risk-ok">초과 확률 {dual.text} (안정)</small>
                                        {/if}
                                    {:else if row.monthlySavings < 0}
                                        약 {formatManwon(Math.abs(row.monthlySavings))} 만원 추가
                                    {:else}
                                        동일
                                    {/if}</td
                                >
                                <td class="score-cell">
                                    <div class="score-main">{formatScore(row.score)}</div>
                                    <small class="score-breakdown">{formatScore(row.normalizedCost)} + {formatScore(row.riskScore)}</small>
                                    <small class="score-reason">{row.scoreReason}</small>
                                </td>
                            </tr>
                        {/each}
                    {/if}
                </tbody>
            </table>
        </div>

        <!-- 2. 실무 추천안 2가지 -->
        {#if monthlyLossMinRow && balancedOptimalRow}
            <div class="dual-recommendation-panel">
                <div class="dual-panel-header">
                    <h5>실무 추천안 2가지</h5>
                    <p>비용과 초과 위험을 함께 고려한 <strong>균형 최적안</strong>과, 초과를 거의 안 하는 <strong>초과 최소(안전)안</strong>을 동시에 제공합니다.</p>
                </div>
                <div class="dual-recommendation-grid">
                    <article class="rec-card balanced" on:click={() => handleCandidateSelect(monthlyLossMinRow.contractKw)}>
                        <div class="rec-tag">⚖️ 균형 최적안</div>
                        <strong>{monthlyLossMinRow.contractKw}kW</strong>
                        <p>초과 확률 약 {formatProbability(monthlyLossMinRow.overageProbability)}</p>
                        <small>비용·리스크 종합 최적 (권장 계약전력)</small>
                    </article>
                    <article class="rec-card loss" on:click={() => handleCandidateSelect(balancedOptimalRow.contractKw)}>
                        <div class="rec-tag">🛡️ 초과 최소안</div>
                        <strong>{balancedOptimalRow.contractKw}kW</strong>
                        <p>초과 확률 약 {formatProbability(balancedOptimalRow.overageProbability)}</p>
                        <small>예측 P95 커버 · 초과 위험 최소</small>
                    </article>
                </div>

                <div class="detail-filter-tabs">
                    <button class:active={detailCategory === 'compare'} on:click={() => detailCategory = 'compare'}>비교 보기</button>
                    <button class:active={detailCategory === 'loss'} on:click={() => detailCategory = 'loss'}>균형 최적안 상세</button>
                    <button class:active={detailCategory === 'balanced'} on:click={() => detailCategory = 'balanced'}>초과 최소안 상세</button>
                </div>

                {#if detailCategory === 'compare'}
                    {@const lossDecision = getDecisionRowByContract(monthlyLossMinRow.contractKw)}
                    {@const balancedDecision = getDecisionRowByContract(balancedOptimalRow.contractKw)}
                    {@const lossProsCons = buildProsCons(monthlyLossMinRow, 'loss')}
                    {@const balancedProsCons = buildProsCons(balancedOptimalRow, 'balanced')}
                    {@const lossOverDual = formatDualProbability(lossDecision?.overageProbability, lossDecision?.sessionOverageProbability)}
                    {@const balancedOverDual = formatDualProbability(balancedDecision?.overageProbability, balancedDecision?.sessionOverageProbability)}
                    <div class="compare-panel">
                        <div class="compare-column">
                            <h6>균형 최적안 ({monthlyLossMinRow.contractKw}kW)</h6>
                            <p class="compare-metric">월 예상 비용: 약 {formatManwon(monthlyLossMinRow.totalLossMonthly)} 만원</p>
                            <p class="compare-metric">초과 확률: {lossOverDual.text}</p>
                            <p class="compare-metric">계약 여유 발생일 비율: {formatProbability(lossDecision?.wasteProbability)}</p>
                            <p class="compare-metric">연간 기대비용: {formatWon(lossDecision?.expectedAnnualCost)}</p>
                            <div class="pros-cons-grid">
                                <div>
                                    <span class="pc-title">장점</span>
                                    <ul>
                                        {#each lossProsCons.pros as item}
                                            <li>{item}</li>
                                        {/each}
                                    </ul>
                                </div>
                                <div>
                                    <span class="pc-title">단점</span>
                                    <ul>
                                        {#each lossProsCons.cons as item}
                                            <li>{item}</li>
                                        {/each}
                                    </ul>
                                </div>
                            </div>
                        </div>
                        <div class="compare-column">
                            <h6>초과 최소안 ({balancedOptimalRow.contractKw}kW)</h6>
                            <p class="compare-metric">월 예상 비용: 약 {formatManwon(balancedOptimalRow.totalLossMonthly)} 만원</p>
                            <p class="compare-metric">초과 확률: {balancedOverDual.text}</p>
                            <p class="compare-metric">계약 여유 발생일 비율: {formatProbability(balancedDecision?.wasteProbability)}</p>
                            <p class="compare-metric">연간 기대비용: {formatWon(balancedDecision?.expectedAnnualCost)}</p>
                            <div class="pros-cons-grid">
                                <div>
                                    <span class="pc-title">장점</span>
                                    <ul>
                                        {#each balancedProsCons.pros as item}
                                            <li>{item}</li>
                                        {/each}
                                    </ul>
                                </div>
                                <div>
                                    <span class="pc-title">단점</span>
                                    <ul>
                                        {#each balancedProsCons.cons as item}
                                            <li>{item}</li>
                                        {/each}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                {:else if detailCategory === 'loss' && monthlyLossMinRow}
                    {@const lossDetail = getDecisionRowByContract(monthlyLossMinRow.contractKw)}
                    {@const lossOnlyProsCons = buildProsCons(monthlyLossMinRow, 'loss')}
                    <div class="single-detail-panel">
                        <h6>균형 최적안 상세: {monthlyLossMinRow.contractKw}kW</h6>
                        <p>월 예상 비용 약 {formatManwon(monthlyLossMinRow.totalLossMonthly)} 만원, 연간 기대비용 {formatWon(lossDetail?.expectedAnnualCost)}</p>
                        <div class="pros-cons-grid">
                            <div>
                                <span class="pc-title">장점</span>
                                <ul>
                                    {#each lossOnlyProsCons.pros as item}
                                        <li>{item}</li>
                                    {/each}
                                </ul>
                            </div>
                            <div>
                                <span class="pc-title">단점</span>
                                <ul>
                                    {#each lossOnlyProsCons.cons as item}
                                        <li>{item}</li>
                                    {/each}
                                </ul>
                            </div>
                        </div>
                    </div>
                {:else if detailCategory === 'balanced' && balancedOptimalRow}
                    {@const balancedDetail = getDecisionRowByContract(balancedOptimalRow.contractKw)}
                    {@const balancedOnlyProsCons = buildProsCons(balancedOptimalRow, 'balanced')}
                    <div class="single-detail-panel">
                        <h6>초과 최소안 상세: {balancedOptimalRow.contractKw}kW</h6>
                        <p>월 예상 비용 약 {formatManwon(balancedOptimalRow.totalLossMonthly)} 만원, 연간 기대비용 {formatWon(balancedDetail?.expectedAnnualCost)}</p>
                        <div class="pros-cons-grid">
                            <div>
                                <span class="pc-title">장점</span>
                                <ul>
                                    {#each balancedOnlyProsCons.pros as item}
                                        <li>{item}</li>
                                    {/each}
                                </ul>
                            </div>
                            <div>
                                <span class="pc-title">단점</span>
                                <ul>
                                    {#each balancedOnlyProsCons.cons as item}
                                        <li>{item}</li>
                                    {/each}
                                </ul>
                            </div>
                        </div>
                    </div>
                {/if}
            </div>
        {/if}

        <!-- 3. 왜 최적안인가 -->
        {#if bestDecisionBasis}
            {@const bestOverDual = formatDualProbability(bestDecisionBasis.overageProbability, bestDecisionBasis.sessionOverageProbability)}
            <div class="optimal-decision-panel">
                <div class="decision-heading">
                    <h5>왜 {bestDecisionBasis.contractKw}kW가 최적안인가?</h5>
                    <span class="decision-chip"
                        >총점 {formatScore(bestDecisionBasis.totalScore)} (최저)</span
                    >
                </div>
                <p class="decision-formula">
                    선정식: <code>총점 = (연간 기대비용 ÷ 후보 최소 연간비용) + 리스크 점수</code>
                </p>
                <div class="decision-metrics">
                    <div class="decision-metric">
                        <span>연간 기대비용</span>
                        <strong>{formatWon(bestDecisionBasis.expectedAnnualCost)}</strong>
                    </div>
                    <div class="decision-metric">
                        <span>비용 지수 (정규화)</span>
                        <strong>{formatScore(bestDecisionBasis.normalizedCost)}</strong>
                    </div>
                    <div class="decision-metric">
                        <span>리스크 점수</span>
                        <strong>{formatScore(bestDecisionBasis.riskScore)}</strong>
                    </div>
                    <div class="decision-metric">
                        <span>초과 확률</span>
                        <strong>{bestOverDual.text}</strong>
                    </div>
                    <div class="decision-metric">
                        <span>계약 여유 발생일 비율</span>
                        <strong>{bestDecisionBasis.wasteProbability.toFixed(1)}%</strong>
                    </div>
                </div>
                {#if runnerUpDecisionBasis}
                    {@const scoreGap = runnerUpDecisionBasis.totalScore - bestDecisionBasis.totalScore}
                    {@const costGap = runnerUpDecisionBasis.expectedAnnualCost - bestDecisionBasis.expectedAnnualCost}
                    {@const riskGap = runnerUpDecisionBasis.riskScore - bestDecisionBasis.riskScore}
                    <p class="decision-compare">
                        차선안 {runnerUpDecisionBasis.contractKw}kW 대비 총점이
                        {formatScore(scoreGap)}p 낮습니다
                        (비용 지수 차이 {formatScore(runnerUpDecisionBasis.normalizedCost - bestDecisionBasis.normalizedCost)} +
                        리스크 차이 {formatScore(riskGap)}).
                        연간 기대비용은 차선안이
                        {costGap >= 0
                            ? `${formatWon(costGap)} 더 높고`
                            : `${formatWon(Math.abs(costGap))} 더 낮지만`}
                        총점은 더 큽니다.
                    </p>
                {/if}
                {#if selectedDecisionBasis && selectedDecisionBasis.contractKw !== bestDecisionBasis.contractKw}
                    {@const selectedScoreGap = selectedDecisionBasis.totalScore - bestDecisionBasis.totalScore}
                    <p class="decision-selected-note">
                        현재 선택한 {selectedDecisionBasis.contractKw}kW의 총점은
                        {formatScore(selectedDecisionBasis.totalScore)}로,
                        최적안보다 {formatScore(selectedScoreGap)}p 높습니다.
                        그래서 월 예상 비용이 비슷해도 최적안으로 선정되지 않을 수 있습니다.
                    </p>
                {/if}
                <p class="decision-note">
                    리스크 점수는 초과 확률·여유 발생일 비율·비용 변동성을 합쳐 백엔드에서 산정합니다.
                </p>
            </div>
        {/if}

        <!-- 4. 수식 설명 (토글, 기본 숨김) -->
        <div class="collapsible-section">
            <button
                type="button"
                on:click={() => showFormulaDetails = !showFormulaDetails}
                class="collapsible-toggle"
                class:active={showFormulaDetails}
            >
                <div class="toggle-content">
                    <span class="toggle-icon">📐</span>
                    <span class="toggle-label">수식 설명</span>
                </div>
                <svg class="toggle-arrow" class:rotated={showFormulaDetails} viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M6 9l6 6 6-6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            {#if showFormulaDetails}
                <div class="collapsible-content">
                    <div class="metric-definitions">
                        <article class="metric-definition-card">
                            <h6>연간 기대비용</h6>
                            <p>각 계약전력 후보에서 1년 동안 예상되는 총비용의 기대값입니다.</p>
                            <p class="definition-formula">
                                기대 월비용 = E[계약전력 × {BASIC_RATE_LABEL} + max(0, 피크-계약전력) × {BASIC_RATE_LABEL} × {SHORTAGE_PENALTY_RATIO}]
                            </p>
                            <p class="definition-formula">연간 기대비용 = 12 × 기대 월비용</p>
                        </article>
                        <article class="metric-definition-card">
                            <h6>비용 지수</h6>
                            <p>후보 간 비용 비교를 위해 연간 기대비용을 최소 비용 후보 기준으로 정규화한 값입니다.</p>
                            <p class="definition-formula">비용 지수 = 연간 기대비용 / 후보 최소 연간 기대비용</p>
                            <p class="definition-note">1.000에 가까울수록 비용 측면에서 유리합니다.</p>
                        </article>
                        <article class="metric-definition-card">
                            <h6>리스크 점수</h6>
                            <p>초과 확률, 계약 여유 발생일 비율, 비용 변동성을 합산한 지표로 백엔드 최적화 로직에서 계산됩니다.</p>
                            <p class="definition-formula">리스크 점수 = 2×(초과확률/100)×(1-리스크허용도) + (여유발생일비율/100)×리스크허용도 + 0.5×(비용표준편차/1,000,000)</p>
                            <p class="definition-formula">총점(Score) = 비용 지수 + 리스크 점수</p>
                            <p class="definition-note">낮을수록 안정적이며 최적안 선정에 유리합니다.</p>
                        </article>
                        <article class="metric-definition-card">
                            <h6>초과 확률 / 계약 여유 발생일 비율</h6>
                            <p class="definition-formula">초과확률(%) = (피크 &gt; 계약전력 인 샘플 수 / 전체 샘플 수) × 100</p>
                            <p class="definition-formula">계약 여유 발생일 비율(%) = (피크 &lt; 계약전력 인 샘플 수 / 전체 샘플 수) × 100</p>
                            <p class="definition-note">
                                "여유 발생일 비율"은 <strong>여유가 1kW라도 남은 날의 빈도</strong>일 뿐 낭비량의 크기는 반영하지 않습니다.
                                예를 들어 비율이 100%여도 평균 여유가 5kW라면 실질 사용률은 95%로 빠듯한 계약입니다.
                                실제 낭비 정도는 <strong>평균 여유 전력 / 평균 사용률</strong>로 함께 확인하세요.
                            </p>
                        </article>
                    </div>
                </div>
            {/if}
        </div>

        <!-- 5. Question (토글, 기본 숨김) -->
        <div class="collapsible-section">
            <button
                type="button"
                on:click={() => showQuestionSection = !showQuestionSection}
                class="collapsible-toggle"
                class:active={showQuestionSection}
            >
                <div class="toggle-content">
                    <span class="toggle-icon">❓</span>
                    <span class="toggle-label">자주 묻는 질문</span>
                </div>
                <svg class="toggle-arrow" class:rotated={showQuestionSection} viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M6 9l6 6 6-6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            {#if showQuestionSection}
                <div class="collapsible-content">
                    <div class="scenario-table-disclaimer">
                        <strong>Q. 월 절감액이 가장 큰 행이 곧 최적안인가요?</strong>
                        <p>
                            아닙니다. 과소 계약 시나리오는 기본요금이 낮아 평균적으로 절감되는 것처럼 보이지만, 실제 청구에는 다음 비용들이 따라붙습니다. <strong>본 표는 이 중 정량화 가능한 비용을 이미 절감액에 반영하고 있습니다:</strong>
                        </p>
                        <ul>
                            <li><strong>150% 초과 패널티 [월 과소 계약 패널티 비용 컬럼]</strong>: 피크가 계약을 넘는 순간 초과 kW에 대해 기본요금의 1.5배 부과. 초과 확률 × 평균 초과 kW 기대값으로 반영.</li>
                            <li><strong>한전 검침 상향 (ratcheting) [월 검침 상향 비용 컬럼]</strong>: 1회 초과 시 이후 12개월간 계약전력이 초과 피크 기준으로 자동 상향되어 기본요금이 상승. <code>min(1, 월초과확률 × 12) × 평균 초과 kW × 기본요금 단가</code>로 근사 반영. 실제 청구서에 가장 크게 나타나는 "숨은 비용"입니다.</li>
                            <li><strong>청구서 변동성 (미정량)</strong>: 절감액은 평균값이며, 어떤 달은 크게 아낀 뒤 어떤 달은 큰 패널티로 튈 수 있어 예산 관리가 어렵습니다. 이 변동성 리스크는 <strong>Score의 리스크점수</strong>가 담당합니다.
                        </ul>
                        <p>
                            따라서 <strong>이 표의 월 절감액은 "초과 패널티 + 검침 상향"이 모두 차감된 실질 절감액</strong>입니다. 과소 시나리오가 처음에는 절감이 커 보이더라도 검침 상향 비용이 붙으면 실질 절감이 크게 줄어들거나 오히려 마이너스(추가 비용)가 됩니다. <strong>Score 최저</strong>가 "장기 안정 + 실질 비용 최저"를 동시에 만족하는 최적안입니다.
                        </p>
                    </div>
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    :global([data-theme="light"]) .optimization-chart {
        --container-bg: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
        --container-border: rgba(15, 23, 42, 0.08);
        --container-shadow: 0 18px 32px rgba(15, 23, 42, 0.08);
        --section-bg: #ffffff;
        --section-border: rgba(148, 163, 184, 0.25);
        --section-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
        --section-hover-shadow: 0 10px 28px rgba(15, 23, 42, 0.12);
        --text-primary: #0f172a;
        --text-secondary: #475569;
        --legend-color: #334155;
        --accent-primary: #4f46e5;
        --accent-secondary: #22c55e;
        --accent-tertiary: #f97316;
        --badge-bg: rgba(79, 70, 229, 0.1);
        --badge-text: #4338ca;
        --table-header-bg: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
        --table-header-text: #1e1b4b;
        --table-border: rgba(148, 163, 184, 0.35);
        --table-row-alt: #f8fafc;
        --table-total-bg: rgba(16, 185, 129, 0.12);
        --table-total-text: #065f46;
        --optimal-bg: rgba(16, 185, 129, 0.16);
        --optimal-bg-hover: rgba(16, 185, 129, 0.22);
        --optimal-text: #047857;
        --optimal-border: rgba(16, 185, 129, 0.32);
        --risk-high-bg: rgba(239, 68, 68, 0.18);
        --risk-high-text: #b91c1c;
        --risk-medium-bg: rgba(249, 115, 22, 0.2);
        --risk-medium-text: #c2410c;
        --star-color: #f59e0b;
        --output-bg: rgba(59, 130, 246, 0.12);
        --output-border: rgba(59, 130, 246, 0.24);
    }

    :global([data-theme="dark"]) .optimization-chart {
        --container-bg: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
        --container-border: rgba(148, 163, 184, 0.28);
        --container-shadow: 0 18px 36px rgba(2, 6, 23, 0.6);
        --section-bg: rgba(15, 23, 42, 0.96);
        --section-border: rgba(148, 163, 184, 0.32);
        --section-shadow: 0 8px 24px rgba(2, 6, 23, 0.6);
        --section-hover-shadow: 0 12px 32px rgba(2, 6, 23, 0.7);
        --text-primary: #e2e8f0;
        --text-secondary: #cbd5f5;
        --legend-color: #cbd5f5;
        --accent-primary: #818cf8;
        --accent-secondary: #34d399;
        --accent-tertiary: #fb923c;
        --badge-bg: rgba(129, 140, 248, 0.22);
        --badge-text: #c7d2fe;
        --table-header-bg: linear-gradient(
            135deg,
            rgba(148, 163, 184, 0.28) 0%,
            rgba(129, 140, 248, 0.24) 100%
        );
        --table-header-text: #f8fafc;
        --table-border: rgba(71, 85, 105, 0.65);
        --table-row-alt: rgba(30, 41, 59, 0.82);
        --table-total-bg: rgba(16, 185, 129, 0.32);
        --table-total-text: #d1fae5;
        --optimal-bg: rgba(16, 185, 129, 0.34);
        --optimal-bg-hover: rgba(16, 185, 129, 0.44);
        --optimal-text: #d1fae5;
        --optimal-border: rgba(16, 185, 129, 0.48);
        --risk-high-bg: rgba(239, 68, 68, 0.38);
        --risk-high-text: #fecaca;
        --risk-medium-bg: rgba(249, 115, 22, 0.38);
        --risk-medium-text: #fdba74;
        --star-color: #fbbf24;
        --output-bg: rgba(59, 130, 246, 0.24);
        --output-border: rgba(59, 130, 246, 0.32);
    }

    .optimization-chart {
        background: var(--container-bg);
        border: 1px solid var(--container-border);
        border-radius: 18px;
        padding: clamp(20px, 4vw, 28px);
        box-shadow: var(--container-shadow);
        color: var(--text-primary);
    }

    .chart-title {
        text-align: center;
        font-size: clamp(1.35rem, 2vw, 1.6rem);
        font-weight: 800;
        margin-bottom: clamp(20px, 3vw, 28px);
        color: var(--text-primary);
        letter-spacing: -0.3px;
    }

    .chart-sections {
        display: grid;
        grid-template-columns: 1fr;
        gap: clamp(16px, 3vw, 24px);
        margin-bottom: clamp(18px, 3vw, 26px);
    }

    .section {
        background: var(--section-bg);
        border: 1px solid var(--section-border);
        border-radius: 14px;
        padding: clamp(16px, 2.5vw, 20px);
        box-shadow: var(--section-shadow);
        transition:
            transform 0.2s ease,
            box-shadow 0.2s ease,
            border-color 0.2s ease;
    }

    .section:hover {
        transform: translateY(-3px);
        box-shadow: var(--section-hover-shadow);
        border-color: rgba(79, 70, 229, 0.18);
    }

    .section h4 {
        margin: 0 0 14px;
        font-size: 1.05rem;
        font-weight: 700;
        background: linear-gradient(
            135deg,
            var(--accent-primary),
            var(--accent-secondary)
        );
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
    }

    .header-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .view-mode-select {
        padding: 6px 12px;
        border: 1px solid var(--table-border);
        border-radius: 6px;
        background: var(--section-bg);
        color: var(--text-primary);
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .view-mode-select:hover {
        border-color: var(--accent-primary);
        background: var(--badge-bg);
    }

    .view-mode-select:focus {
        outline: none;
        border-color: var(--accent-primary);
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
    }

    .time-series {
        border-left: 4px solid var(--accent-tertiary);
    }

    .chart-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: flex-end;
    }

    .zoom-hint {
        font-size: 0.8rem;
        color: var(--text-secondary);
    }

    .chart-wrapper {
        position: relative;
        height: clamp(260px, 35vw, 320px);
    }

    .time-domain-chart {
        height: clamp(240px, 34vw, 320px);
    }

    .chart-footnote {
        margin-top: 8px;
        font-size: 0.82rem;
        color: var(--text-secondary);
    }

    .chart-stat-explain {
        margin: 6px 0 12px;
        padding: 10px 14px;
        border-radius: 10px;
        background: rgba(251, 113, 133, 0.08);
        border-left: 3px solid #fb7185;
        color: var(--text-secondary);
        font-size: 0.82rem;
        line-height: 1.6;
    }

    .chart-stat-explain strong {
        color: var(--text-primary);
    }

    .overfit-banner {
        margin-top: 10px;
        padding: 12px 14px;
        border-radius: 12px;
        border: 1px solid rgba(14, 165, 233, 0.25);
        background: rgba(14, 165, 233, 0.08);
        color: var(--text-primary);
        font-size: 0.88rem;
    }

    .overfit-banner.risk {
        border-color: rgba(248, 113, 113, 0.45);
        background: rgba(248, 113, 113, 0.12);
    }

    .overfit-header {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 6px;
        font-weight: 600;
    }

    .status-chip {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        background: rgba(59, 130, 246, 0.15);
        color: var(--accent-primary);
    }

    .overfit-banner.risk .status-chip {
        background: rgba(248, 113, 113, 0.2);
        color: #dc2626;
    }

    .overfit-meta {
        font-size: 0.78rem;
        color: var(--text-secondary);
    }

    .simulation-summary {
        margin-top: 12px;
        padding: 14px 16px;
        border-radius: 12px;
        border: 1px solid var(--section-border);
        background: rgba(251, 113, 133, 0.08);
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .simulation-summary.overshoot {
        background: rgba(34, 197, 94, 0.08);
        border-color: rgba(34, 197, 94, 0.3);
    }

    .summary-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        font-size: 0.9rem;
        color: var(--text-primary);
        flex-wrap: wrap;
    }

    .model-chip {
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(251, 113, 133, 0.2);
        color: var(--accent-tertiary);
        font-size: 0.75rem;
        font-weight: 600;
    }

    .simulation-summary.overshoot .model-chip {
        background: rgba(34, 197, 94, 0.25);
        color: #16a34a;
    }

    .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
    }

    .summary-metric {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.35);
        border: 1px solid rgba(251, 113, 133, 0.22);
    }

    :global([data-theme="dark"]) .summary-metric {
        background: rgba(15, 23, 42, 0.7);
    }

    .summary-metric span {
        font-size: 0.78rem;
        color: var(--text-secondary);
    }

    .summary-metric strong {
        font-size: 1.05rem;
        color: var(--text-primary);
    }

    .empty-state {
        padding: 20px;
        border: 1px dashed var(--section-border);
        border-radius: 12px;
        text-align: center;
        font-size: 0.9rem;
        color: var(--text-secondary);
        background: rgba(148, 163, 184, 0.08);
    }

    .table-info {
        margin-bottom: 14px;
    }

    .table-explain {
        margin: 8px 2px 0;
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.45;
    }

    .collapsible-section {
        margin-top: 16px;
        border: 1px solid var(--section-border);
        border-radius: 12px;
        background: var(--section-bg);
        overflow: hidden;
    }

    .collapsible-toggle {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 14px 18px;
        background: transparent;
        border: none;
        cursor: pointer;
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--text-primary);
        text-align: left;
        transition: background 0.2s ease;
    }

    .collapsible-toggle:hover {
        background: rgba(79, 70, 229, 0.06);
    }

    .collapsible-toggle.active {
        background: rgba(79, 70, 229, 0.08);
        border-bottom: 1px solid var(--section-border);
    }

    :global([data-theme="dark"]) .collapsible-toggle:hover {
        background: rgba(129, 140, 248, 0.1);
    }

    :global([data-theme="dark"]) .collapsible-toggle.active {
        background: rgba(129, 140, 248, 0.14);
    }

    .collapsible-toggle .toggle-content {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .collapsible-toggle .toggle-icon {
        font-size: 1.1rem;
    }

    .collapsible-toggle .toggle-label {
        font-weight: 600;
    }

    .collapsible-toggle .toggle-arrow {
        width: 18px;
        height: 18px;
        transition: transform 0.25s ease;
        color: var(--text-secondary);
    }

    .collapsible-toggle .toggle-arrow.rotated {
        transform: rotate(180deg);
    }

    .collapsible-content {
        padding: 16px 18px 18px;
        background: var(--section-bg);
    }

    .optimal-decision-panel {
        margin-top: 12px;
        padding: 14px 16px;
        border-radius: 12px;
        border: 1px solid rgba(79, 70, 229, 0.22);
        background: rgba(79, 70, 229, 0.08);
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    :global([data-theme="dark"]) .optimal-decision-panel {
        border-color: rgba(129, 140, 248, 0.35);
        background: rgba(30, 27, 75, 0.46);
    }

    .decision-heading {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }

    .decision-heading h5 {
        margin: 0;
        font-size: 0.95rem;
        color: var(--text-primary);
    }

    .decision-chip {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(16, 185, 129, 0.2);
        color: var(--table-total-text);
        font-size: 0.76rem;
        font-weight: 700;
    }

    .decision-formula {
        margin: 0;
        font-size: 0.82rem;
        color: var(--text-secondary);
        line-height: 1.45;
    }

    .decision-formula code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.76rem;
        color: var(--text-primary);
        background: rgba(15, 23, 42, 0.08);
        border-radius: 6px;
        padding: 2px 6px;
    }

    :global([data-theme="dark"]) .decision-formula code {
        background: rgba(148, 163, 184, 0.16);
    }

    .decision-metrics {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 10px;
    }

    .decision-metric {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.45);
        border: 1px solid rgba(79, 70, 229, 0.15);
    }

    :global([data-theme="dark"]) .decision-metric {
        background: rgba(15, 23, 42, 0.62);
        border-color: rgba(129, 140, 248, 0.24);
    }

    .decision-metric span {
        font-size: 0.75rem;
        color: var(--text-secondary);
    }

    .decision-metric strong {
        font-size: 0.93rem;
        color: var(--text-primary);
    }


    .decision-compare,
    .decision-note,
    .decision-selected-note {
        margin: 0;
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.45;
    }

    .decision-selected-note {
        padding: 8px 10px;
        border-radius: 8px;
        background: rgba(249, 115, 22, 0.12);
        border: 1px solid rgba(249, 115, 22, 0.26);
        color: #9a3412;
    }

    :global([data-theme="dark"]) .decision-selected-note {
        color: #fdba74;
        border-color: rgba(251, 146, 60, 0.4);
        background: rgba(124, 45, 18, 0.32);
    }

    .dual-recommendation-panel {
        margin-top: 14px;
        padding: 14px;
        border-radius: 12px;
        border: 1px solid rgba(59, 130, 246, 0.22);
        background: rgba(59, 130, 246, 0.06);
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .dual-panel-header h5 {
        margin: 0;
        font-size: 0.95rem;
    }

    .dual-panel-header p {
        margin: 4px 0 0;
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.45;
    }

    .dual-recommendation-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px;
    }

    .rec-card {
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.35);
        background: rgba(255, 255, 255, 0.7);
        padding: 12px;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    :global([data-theme="dark"]) .rec-card {
        background: rgba(15, 23, 42, 0.72);
        border-color: rgba(148, 163, 184, 0.35);
    }

    .rec-card.loss {
        border-color: rgba(249, 115, 22, 0.35);
    }

    .rec-card.balanced {
        border-color: rgba(16, 185, 129, 0.4);
    }

    .rec-card strong {
        font-size: 1.05rem;
    }

    .rec-card p,
    .rec-card small {
        margin: 0;
        color: var(--text-secondary);
        line-height: 1.4;
    }

    .rec-tag {
        display: inline-flex;
        width: fit-content;
        padding: 3px 8px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        background: rgba(148, 163, 184, 0.2);
        color: var(--text-primary);
    }

    .detail-filter-tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }

    .detail-filter-tabs button {
        border: 1px solid var(--table-border);
        background: transparent;
        color: var(--text-secondary);
        border-radius: 999px;
        padding: 6px 12px;
        font-size: 0.78rem;
        font-weight: 600;
        cursor: pointer;
    }

    .detail-filter-tabs button.active {
        background: rgba(79, 70, 229, 0.18);
        border-color: rgba(79, 70, 229, 0.4);
        color: var(--text-primary);
    }

    .compare-panel {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 10px;
    }

    .compare-column,
    .single-detail-panel {
        border: 1px solid var(--table-border);
        border-radius: 10px;
        padding: 12px;
        background: rgba(255, 255, 255, 0.6);
    }

    :global([data-theme="dark"]) .compare-column,
    :global([data-theme="dark"]) .single-detail-panel {
        background: rgba(15, 23, 42, 0.7);
    }

    .compare-column h6,
    .single-detail-panel h6 {
        margin: 0 0 8px;
        font-size: 0.88rem;
    }

    .compare-metric,
    .single-detail-panel p {
        margin: 0 0 6px;
        font-size: 0.78rem;
        color: var(--text-secondary);
    }

    .pros-cons-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-top: 8px;
    }

    .pc-title {
        display: inline-block;
        margin-bottom: 4px;
        font-size: 0.76rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .pros-cons-grid ul {
        margin: 0;
        padding-left: 16px;
    }

    .pros-cons-grid li {
        font-size: 0.74rem;
        line-height: 1.45;
        color: var(--text-secondary);
        margin-bottom: 4px;
    }

    @media (max-width: 768px) {
        .pros-cons-grid {
            grid-template-columns: 1fr;
        }
    }


    .info-badge {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        background: var(--badge-bg);
        border-radius: 10px;
        font-size: 0.85rem;
        color: var(--badge-text);
        border: 1px solid var(--section-border);
    }

    .info-badge svg {
        width: 18px;
        height: 18px;
        stroke-width: 2.2;
    }

    .metric-definitions {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px;
        margin-top: 10px;
    }

    .metric-definition-card {
        padding: 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.62);
        border: 1px solid rgba(79, 70, 229, 0.16);
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.06);
    }

    :global([data-theme="dark"]) .metric-definition-card {
        background: rgba(15, 23, 42, 0.72);
        border-color: rgba(129, 140, 248, 0.25);
        box-shadow: 0 6px 14px rgba(2, 6, 23, 0.45);
    }

    .metric-definition-card h6 {
        margin: 0 0 6px;
        font-size: 0.82rem;
        color: var(--text-primary);
    }

    .metric-definition-card p {
        margin: 0;
        font-size: 0.75rem;
        color: var(--text-secondary);
        line-height: 1.45;
    }

    .metric-definition-card p + p {
        margin-top: 6px;
    }

    .metric-definition-card .definition-formula {
        color: var(--text-primary);
        font-weight: 600;
    }

    .metric-definition-card .definition-note {
        font-size: 0.72rem;
    }

    .scenario-table-container {
        margin-top: 18px;
        border: 1px solid var(--section-border);
        border-radius: 16px;
        overflow-x: auto;
        background: var(--section-bg);
        box-shadow: var(--section-shadow);
    }

    .scenario-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
        min-width: 640px;
    }

    .scenario-table thead th {
        background: var(--table-header-bg);
        color: var(--table-header-text);
        text-transform: uppercase;
        font-size: 0.78rem;
        letter-spacing: 0.45px;
        padding: 14px 12px;
        text-align: center;
    }

    .scenario-table thead th small {
        display: block;
        font-size: 0.68rem;
        text-transform: none;
        opacity: 0.8;
        margin-top: 4px;
    }

    .scenario-table td {
        padding: 14px 12px;
        text-align: center;
        border-top: 1px solid var(--table-border);
    }

    .scenario-table tbody tr {
        background: var(--section-bg);
        transition:
            background 0.2s ease,
            color 0.2s ease,
            transform 0.2s ease,
            box-shadow 0.2s ease;
        cursor: pointer;
    }

    .scenario-table tbody tr + tr {
        border-top: 1px solid rgba(148, 163, 184, 0.2);
    }

    .scenario-table tbody tr:hover {
        transform: translateY(-1px);
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
    }

    .scenario-table tbody tr.optimal {
        background: var(--optimal-bg);
        color: var(--optimal-text);
        font-weight: 700;
    }

    .scenario-table tbody tr.over {
        background: rgba(14, 165, 233, 0.08);
    }

    .scenario-table tbody tr.under {
        background: rgba(249, 115, 22, 0.08);
    }

    :global([data-theme="dark"]) .scenario-table tbody tr.over {
        background: rgba(14, 165, 233, 0.2);
    }

    :global([data-theme="dark"]) .scenario-table tbody tr.under {
        background: rgba(249, 115, 22, 0.2);
    }

    .scenario-table tbody tr.selected {
        outline: 2px solid var(--accent-primary);
        outline-offset: -2px;
        box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.25);
    }

    .scenario-cell {
        text-align: left;
    }

    .scenario-delta {
        display: block;
        margin-top: 5px;
        font-size: 0.72rem;
        color: var(--text-secondary);
        font-weight: 500;
    }

    .scenario-tag {
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        background: rgba(79, 70, 229, 0.12);
        color: var(--accent-primary);
    }

    .scenario-table tbody tr.over .scenario-tag {
        background: rgba(14, 165, 233, 0.15);
        color: #0284c7;
    }

    .scenario-table tbody tr.under .scenario-tag {
        background: rgba(249, 115, 22, 0.18);
        color: #c2410c;
    }

    .scenario-table tbody tr.optimal .scenario-tag {
        background: var(--table-total-bg);
        color: var(--table-total-text);
    }

    .loss-main {
        font-weight: 600;
    }

    .loss-breakdown {
        display: block;
        margin-top: 4px;
        font-size: 0.7rem;
        color: var(--text-secondary);
        opacity: 0.92;
    }

    .score-cell {
        min-width: 260px;
    }

    .score-main {
        font-weight: 700;
    }

    .score-breakdown {
        display: block;
        margin-top: 4px;
        font-size: 0.74rem;
        color: var(--text-secondary);
        opacity: 0.95;
    }

    .score-reason {
        display: block;
        margin-top: 4px;
        font-size: 0.68rem;
        color: var(--text-secondary);
        line-height: 1.45;
        opacity: 0.9;
    }

    .scenario-table .empty-row {
        text-align: center;
        padding: 36px 12px;
        color: var(--text-secondary);
    }

    .ratcheting-cell {
        color: #b45309;
        font-weight: 500;
        white-space: nowrap;
    }

    :global([data-theme="dark"]) .ratcheting-cell {
        color: #fbbf24;
    }

    .savings-cell {
        font-weight: 600;
        color: var(--text-secondary);
        min-width: 180px;
    }

    .savings-cell.savings-positive {
        color: #047857;
    }

    .savings-cell.savings-negative {
        color: #b91c1c;
    }

    .savings-cell.savings-risky {
        color: #b45309;
    }

    :global([data-theme="dark"]) .savings-cell.savings-positive {
        color: #34d399;
    }

    :global([data-theme="dark"]) .savings-cell.savings-negative {
        color: #f87171;
    }

    :global([data-theme="dark"]) .savings-cell.savings-risky {
        color: #fbbf24;
    }

    .savings-risk-warn,
    .savings-risk-note,
    .savings-risk-ok {
        display: block;
        margin-top: 3px;
        font-size: 0.7rem;
        font-weight: 500;
    }

    .savings-risk-warn {
        color: #b91c1c;
    }

    .savings-risk-note {
        color: #b45309;
    }

    .savings-risk-ok {
        color: var(--text-secondary);
        opacity: 0.85;
    }

    :global([data-theme="dark"]) .savings-risk-warn { color: #f87171; }
    :global([data-theme="dark"]) .savings-risk-note { color: #fbbf24; }

    .scenario-table-disclaimer {
        margin-top: 14px;
        padding: 14px 16px;
        border-radius: 12px;
        background: rgba(234, 179, 8, 0.08);
        border-left: 4px solid #eab308;
        color: var(--text-secondary);
        font-size: 0.82rem;
        line-height: 1.6;
    }

    .scenario-table-disclaimer strong {
        color: var(--text-primary);
    }

    .scenario-table-disclaimer p {
        margin: 6px 0;
    }

    .scenario-table-disclaimer ul {
        margin: 6px 0 6px 18px;
        padding: 0;
    }

    .scenario-table-disclaimer li {
        margin-bottom: 4px;
    }

    .future-projection-block {
        margin-top: 16px;
        padding: 14px 16px;
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 12px;
        background: rgba(59, 130, 246, 0.04);
    }

    .future-projection-block h6 {
        margin: 0 0 6px;
        font-size: 0.95rem;
        color: var(--text-primary);
    }

    .future-projection-note {
        margin: 0 0 10px;
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.5;
    }

    .future-projection-table-wrap {
        overflow-x: auto;
    }

    .future-projection-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.88rem;
    }

    .future-projection-table th,
    .future-projection-table td {
        padding: 8px 10px;
        text-align: right;
        border-bottom: 1px solid rgba(148, 163, 184, 0.25);
    }

    .future-projection-table th:first-child,
    .future-projection-table td:first-child {
        text-align: left;
    }

    .future-projection-table tbody tr.peak-row {
        background: rgba(239, 68, 68, 0.08);
        font-weight: 600;
    }

    .peak-marker {
        margin-left: 4px;
        color: #ef4444;
    }

    @media (max-width: 640px) {
        .scenario-table {
            min-width: 100%;
            font-size: 0.9rem;
        }

        .scenario-table td,
        .scenario-table th {
            padding: 10px 8px;
        }
    }

    /* Scenario/conclusion UI styles removed as markup no longer renders those sections */

    /* Validation Info Banner */
    .validation-info-banner {
        margin-top: 16px;
        padding: 20px;
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.05), rgba(16, 185, 129, 0.05));
        border: 2px solid rgba(59, 130, 246, 0.2);
        border-radius: 14px;
    }

    .info-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
    }

    .info-icon {
        font-size: 1.5rem;
    }

    .info-header h5 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .info-description {
        margin: 12px 0;
        font-size: 0.95rem;
        line-height: 1.8;
        color: var(--text-primary);
    }

    .highlight-green {
        color: #10b981;
        font-weight: 600;
    }

    .highlight-red {
        color: #ef4444;
        font-weight: 600;
    }

    .highlight-blue {
        color: #3b82f6;
        font-weight: 600;
    }

    .validation-metrics {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
        margin: 16px 0;
    }

    .metric-card {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 12px;
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 10px;
    }

    :global([data-theme="dark"]) .metric-card {
        background: rgba(15, 23, 42, 0.6);
        border-color: rgba(148, 163, 184, 0.3);
    }

    .metric-label {
        font-size: 0.8rem;
        color: var(--text-secondary);
        font-weight: 500;
    }

    .metric-value {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    .metric-value.consistency-양호 {
        color: #10b981;
    }

    .metric-value.consistency-보통 {
        color: #f59e0b;
    }

    .metric-value.consistency-개선\ 필요 {
        color: #ef4444;
    }

    .info-note {
        margin: 12px 0 0 0;
        padding: 12px;
        background: rgba(59, 130, 246, 0.1);
        border-left: 3px solid #3b82f6;
        border-radius: 6px;
        font-size: 0.9rem;
        line-height: 1.6;
        color: var(--text-primary);
    }

    /* Loading State */
    .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 60px 20px;
        gap: 16px;
    }

    .loading-spinner {
        width: 48px;
        height: 48px;
        border: 4px solid rgba(79, 70, 229, 0.2);
        border-top-color: #4f46e5;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        to { transform: rotate(360deg); }
    }

    .loading-state p {
        font-size: 1rem;
        color: var(--text-secondary);
        margin: 0;
    }

    @media (max-width: 1200px) {
        .chart-sections {
            grid-template-columns: 1fr;
        }
    }

    @media (max-width: 768px) {
        .optimization-chart {
            padding: 18px;
        }

        .section {
            padding: 16px;
        }

        .chart-wrapper {
            height: 240px;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        .section,
        .scenario-table tbody tr {
            transition: none;
            animation: none;
        }
    }
</style>
