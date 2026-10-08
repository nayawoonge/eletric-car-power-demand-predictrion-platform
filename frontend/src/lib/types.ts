// Common type definitions shared across the frontend when talking to the API.

export interface ApiError {
	success: false;
	error: string;
	message?: string;
	statusCode?: number;
	[key: string]: unknown;
}

export type ApiResult<T> = (T & { success: true }) | ApiError;

export type NotificationType = "success" | "info" | "warning" | "error";

export interface NotificationState {
	id: string;
	message: string;
	type: NotificationType;
	duration?: number;
	timestamp: number;
}

export interface PaginationState {
	page: number;
	limit: number;
	totalPages: number;
	hasNext: boolean;
	hasPrev: boolean;
	total: number;
}

export interface ChargingStation {
	id: string;
	name?: string;
	location?: string;
	region?: string;
	city?: string;
	charger_type?: string;
	connector_type?: string;
	data_sessions?: number;
	avg_power?: number;
	max_power?: number;
	min_power?: number;
	power_std?: number;
	capacity_efficiency?: string;
	last_activity?: string | null;
	first_activity?: string | null;
	active_days?: number;
	[key: string]: unknown;
}

export interface StationsResponse {
	success: boolean;
	stations: ChargingStation[];
	total: number;
	last_updated?: string;
	message?: string;
	error?: string;
	requiresUpload?: boolean;
	pagination?: {
		page: number;
		limit: number;
		total: number;
		hasNext: boolean;
		hasPrev: boolean;
	};
}

export interface PowerStats {
	mean?: number;
	max?: number;
	min?: number;
	std?: number;
	percentile_95?: number;
	percentile_90?: number;
	percentile_50?: number;
	percentile_5?: number;
	count?: number;
	[key: string]: unknown;
}

export interface SessionStats {
	avg_duration?: number;
	avg_energy?: number;
	total_energy?: number;
	[key: string]: unknown;
}

export interface StationPatterns {
	power_statistics?: PowerStats;
	hourly_patterns?: Record<string, Record<string, number>>;
	daily_patterns?: Record<string, Record<string, number>>;
	monthly_patterns?: Record<string, Record<string, number>>;
	date_range?: { start?: string; end?: string };
	[key: string]: unknown;
}

export interface StationSummary {
	total_sessions?: number;
	power_stats?: PowerStats;
	session_stats?: SessionStats;
	[key: string]: unknown;
}

export interface StationAnalysis {
	station_id: string;
	timestamp: string;
	station_info: ChargingStation & {
		status?: string;
		utilization?: string;
	};
	summary: StationSummary;
	patterns: StationPatterns;
	performance_analysis?: {
		utilization_rate?: number;
		peak_utilization?: number;
		average_session_power?: number;
		maximum_recorded_power?: number;
		efficiency_grade?: string;
		rated_power?: number;
		[key: string]: unknown;
	};
	charts_data?: {
		hourly_pattern?: number[];
		monthly_predictions?: {
			data: number[];
			labels: string[];
		};
		soc_power_relationship?: Array<{ x: number; y: number }>;
		[key: string]: unknown;
	};
	realtime_status?: unknown;
	external_factors?: unknown;
}

export interface PredictionChartPoint {
	month: string;
	label: string;
	actual?: number | null;
	predicted?: number | null;
}

export interface PatternAnalysisSummary {
	analysis_method: string;
	pattern_confidence?: number;
	data_quality?: string;
	seasonal_strength?: number;
	weekly_strength?: number;
	trend_factor?: number;
	[key: string]: unknown;
}

export interface SarimaPredictionResult {
	predicted_value?: number;
	confidence?: number;
	success: boolean;
	error_message?: string;
	forecast_data?: Array<{ date: string; value: number }>;
}

export interface AdvancedModelSummary {
	final_prediction: number;
	raw_prediction: number;
	ensemble_method: string;
	model_count: number;
	uncertainty: number;
	model_weights?: Record<string, number> | number[];
	visualization_data?: unknown;
	models: Array<{
		name: string;
		prediction: number;
		confidence: number;
		method?: string;
	}>;
}

export interface PredictionResponse {
	success: boolean;
	station_id: string;
	station_name: string;
	predicted_peak: number;
	confidence: number;
	predicted_hour: string;
	method: string;
	timestamp: string;
	current_peak: number;
	chart_data: PredictionChartPoint[];
	last_month_peak: number;
	recommended_contract_kw: number;
	algorithm_prediction_kw: number;
	prediction_exceeds_limit: boolean;
	data_start_date?: string;
	data_end_date?: string;
	record_count?: number;
	pattern_analysis?: PatternAnalysisSummary;
	advanced_model_prediction?: AdvancedModelSummary;
	method_comparison?: Record<string, unknown> | null;
	sarima_prediction?: SarimaPredictionResult | null;
	charger_type?: string;
	charger_max_power?: number;
	error?: string;
	message?: string;
}

export interface MonthlyContractResponse {
	success: boolean;
	station_id: string;
	station_name?: string;
	year: number;
	month: number;
	horizon_days: number;
	mode: string;
	predicted_peak_kw: number;
	recommended_contract_kw: number;
	charger_type: string;
	actual_peak_power: number;
	calculation_method: string;
	safety_margin_percent: number;
	data_quality?: string;
	timestamp: string;
	algorithm_prediction_kw: number;
	prediction_exceeds_limit: boolean;
	error?: string;
	message?: string;
}

export interface ContractCandidateDetail {
	contract_kw: number;
	expected_annual_cost: number;
	overage_probability: number;
	waste_probability: number;
	cost_std?: number;
	risk_score?: number;
	session_overage_probability?: number;
	session_average_overshoot_kw?: number;
	session_max_overshoot_kw?: number;
	session_waste_probability?: number;
	session_average_waste_kw?: number;
	session_sample_size?: number;
	session_expected_waste_cost?: number;
}

export interface OptimizationDistributionStats {
	mean: number;
	std: number;
	q5: number;
	q50: number;
	q95: number;
	min: number;
	max: number;
}

export interface OptimizationDailyPeakPoint {
	date: string;
	peak_kw: number;
}

export interface OptimizationDetails {
	optimal_contract_kw: number;
	current_contract_kw?: number | null;
	optimal_candidate: ContractCandidateDetail;
	all_candidates: ContractCandidateDetail[];
	prediction_distribution: number[];
	distribution_stats: OptimizationDistributionStats;
	expected_savings?: number | null;
	savings_percent?: number | null;
	daily_peak_series?: OptimizationDailyPeakPoint[];
	session_power_series?: OptimizationSessionPoint[];
	contract_shortfall_simulations?: ContractShortfallSimulation[];
	session_prediction_series?: OptimizationSessionPoint[];
	session_prediction_assessment?: SessionPredictionAssessment | null;
}

export interface OptimizationSessionPoint {
	timestamp: string;
	peak_kw?: number;
	predicted_peak_kw?: number;
	value?: number;
}

export interface ContractShortfallDailyPoint {
	date: string;
	historical_peak_kw?: number;
	simulated_peak_kw: number;
	p10_kw?: number;
	p50_kw?: number;
	p90_kw?: number;
	p95_kw?: number;
	std_kw?: number;
	overshoot_kw: number;
	overshoot_p90_kw?: number;
	risk_factor?: number;
}

export interface ContractShortfallSimulation {
	contract_kw: number;
	overshoot_probability: number;
	expected_overshoot_kw: number;
	p90_overshoot_kw: number;
	// 계약 후보와 독립적인 모델 분포 통계 — "예측 피크 평균/P90" 표시에 사용
	model_peak_avg_kw?: number;
	model_peak_p50_kw?: number;
	model_peak_p90_kw?: number;
	model_peak_p95_kw?: number;
	model_peak_max_p90_kw?: number;
	model_source?: string;
	updated_at?: string;
	daily_projection: ContractShortfallDailyPoint[];
	session_prediction_summary?: SessionPredictionSummary | null;
	session_prediction_samples?: SessionPredictionSample[];
}

export interface SessionPredictionSummary {
	session_sample_size?: number;
	session_overage_probability?: number;
	session_average_overshoot_kw?: number;
	session_max_overshoot_kw?: number;
	session_waste_probability?: number;
	session_average_waste_kw?: number;
	session_expected_waste_cost?: number;
}

export interface SessionPredictionSample {
	timestamp: string;
	predicted_peak_kw: number;
	overshoot_kw: number;
}

export interface SessionPredictionCandidateMetrics extends SessionPredictionSummary {
	contract_kw: number;
}

export interface SessionPredictionAssessment {
	total_points: number;
	time_span_days?: number | null;
	first_timestamp?: string | null;
	last_timestamp?: string | null;
	candidates: SessionPredictionCandidateMetrics[];
}

export interface ContractRecommendation {
	station_id: string;
	analysis_date: string;
	recommended_contract_kw: number;
	current_contract_kw?: number | null;
	expected_annual_cost: number;
	expected_annual_savings?: number | null;
	savings_percent?: number | null;
	predicted_peak_p50: number;
	predicted_peak_p95: number;
	overage_probability: number;
	waste_probability: number;
	confidence_level: number;
	recommendation_summary: string;
	detailed_reasoning: string[];
	action_required: boolean;
	urgency_level: string;
	cost_comparison_data: Record<string, unknown>;
	candidate_analysis_data: Array<Record<string, unknown>>;
	optimization_details?: OptimizationDetails | null;
	annual_savings_won?: number | null;
	monthly_savings?: number | null;
	savings_percentage?: number | null;
	recommendation: string;
	risk_assessment?: {
		risk_level: string;
		overage_probability: number;
		waste_probability: number;
		confidence_level: number;
	};
}

export interface EnsembleModelBreakdown {
	prediction_kw: number;
	uncertainty_kw: number;
	weight: number;
}

export interface EnsembleMaturity {
	level: string;
	session_count: number;
	reasoning: string;
}

export interface EnsemblePredictionSummary {
	final_prediction_kw: number;
	uncertainty_kw: number;
	confidence_level: number;
	lstm: EnsembleModelBreakdown;
	xgboost: EnsembleModelBreakdown;
	maturity: EnsembleMaturity;
}

export interface EnsembleMetadata {
	charger_type: string;
	data_sessions: number;
	model_version: string;
}

export interface InsufficientDataDetails {
	session_count?: number;
	unique_days?: number | null;
	min_required_sessions?: number;
	min_required_days?: number;
	data_coverage_start?: string | null;
	data_coverage_end?: string | null;
}

export interface EnsemblePredictionResponse {
	success: boolean;
	station_id: string;
	timestamp: string;
	ensemble_prediction: EnsemblePredictionSummary;
	contract_recommendation: ContractRecommendation;
	metadata: EnsembleMetadata;
	error?: string;
	error_code?: 'NO_DATA' | 'INSUFFICIENT_DATA' | 'INTERNAL_ERROR' | string;
	guidance?: string[];
	details?: InsufficientDataDetails;
	technical_detail?: string;
	message?: string;
}

export interface EnergyDemandTimeseriesPoint {
	date: string;
	energy: number;
	type: string;
}

export interface EnergyStatistics {
	avg_daily?: number;
	total_energy?: number;
	max_daily?: number;
	min_daily?: number;
	[key: string]: number | undefined;
}

export interface MonthlyEnergySummary {
	month: string;
	month_label: string;
	total_energy: number;
	avg_daily: number;
	active_days: number;
}

export interface EnergyDemandForecastResponse {
	success: boolean;
	station_id: string;
	station_name?: string;
	forecast_period_days?: number;
	daily_forecast?: {
		average: number;
		min: number;
		max: number;
		confidence_interval?: { lower: number; upper: number };
	};
	total_forecast?: {
		kwh: number;
		confidence_interval?: { lower: number; upper: number };
	};
	data_quality?: {
		sample_size: number;
		data_range_days: number;
	};
	method?: string;
	timeseries_data?: EnergyDemandTimeseriesPoint[];
	energy_statistics?: EnergyStatistics;
	monthly_summary?: MonthlyEnergySummary[];
	insights?: string[];
	growth_rate?: number;
	data_range?: {
		start_date: string;
		end_date: string;
	};
	message?: string;
	error?: string;
}

export interface SystemStatusResponse {
	success: boolean;
	hasData: boolean;
	csvFiles: string[];
	dataCount: number;
	activeFile: {
		filename: string;
		path: string;
	} | null;
	dataDir: string;
	timestamp: string;
}

export interface UploadCsvResponse {
	success: boolean;
	message?: string;
	filename?: string;
	file_size_mb?: number;
	rows_processed?: number;
	columns?: number;
	encoding_used?: string;
	validation?: Record<string, unknown>;
	sample_columns?: string[];
	data_dir?: string;
	active_file?: string;
	active_path?: string;
	timestamp?: string;
	error?: string;
}
