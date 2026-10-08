import { writable, derived } from "svelte/store";
import type { Readable } from "svelte/store";
import { api, apiService } from "../services/api";
import { searchActions } from "./searchStore";
import type {
    ChargingStation,
    PaginationState,
    StationAnalysis,
    PredictionResponse,
    MonthlyContractResponse,
} from "../lib/types";

// Station data store
export const stations = writable<ChargingStation[]>([]);
export const currentStation = writable<ChargingStation | null>(null);

interface StationData {
    analysis: StationAnalysis | null;
    prediction: PredictionResponse | null;
    monthlyContract: MonthlyContractResponse | null;
}

export const stationData = writable<StationData>({
    analysis: null,
    prediction: null,
    monthlyContract: null,
});

// Loading states
export const isLoading = writable<boolean>(false);
export const isLoadingMore = writable<boolean>(false);
export const error = writable<string | null>(null);

export interface InsufficientDataNotice {
    error: string;
    error_code: string;
    guidance?: string[];
    details?: {
        session_count?: number;
        unique_days?: number | null;
        min_required_sessions?: number;
        min_required_days?: number;
        data_coverage_start?: string | null;
        data_coverage_end?: string | null;
    };
}
export const insufficientData = writable<InsufficientDataNotice | null>(null);

// Upload states
export const requiresUpload = writable<boolean>(false);
export const hasData = writable<boolean>(false);
export const systemStatus = writable<any>(null);

// Pagination state
export const pagination = writable<PaginationState>({
    page: 1,
    limit: 20,
    totalPages: 1,
    hasNext: false,
    hasPrev: false,
    total: 0,
});

// Derived stores

export const stationById: Readable<Map<string, ChargingStation>> = derived(
    [stations],
    ([$stations]) => {
        const map = new Map<string, ChargingStation>();
        $stations.forEach((station) => map.set(station.id, station));
        return map;
    }
);

interface StationActions {
    loadStations: (
        reset?: boolean,
        search?: string,
        sortBy?: string,
        sortOrder?: string
    ) => Promise<void>;
    loadMore: () => Promise<void>;
    loadStationData: (stationId: string) => Promise<void>;
    setCurrentStation: (station: ChargingStation) => void;
    clearError: () => void;
    checkSystemStatus: () => Promise<void>;
    uploadCsv: (file: File) => Promise<void>;
}

// Actions
export const stationActions: StationActions = {
    async loadStations(
        reset: boolean = true,
        search?: string,
        sortBy: string = "id",
        sortOrder: string = "asc"
    ): Promise<void> {
        isLoading.set(true);
        error.set(null);

        try {
            // 클라이언트 사이드 검색을 위해 서버에서는 검색 파라미터 제외하고 전체 데이터만 요청
            const response = await apiService.getStations({
                limit: 9999,
                // search, sortBy, sortOrder 제거 - 클라이언트에서 처리
            });

            const allStationsData = response.stations || [];
            stations.set(allStationsData);

            // 검색 스토어 초기화 (인덱스 구축)
            searchActions.initializeSearch(allStationsData);

            pagination.set({
                page: 1,
                limit: 9999,
                totalPages: 1,
                hasNext: false,
                hasPrev: false,
                total: allStationsData.length,
            });
        } catch (err: unknown) {
            const errorMessage =
                err instanceof Error ? err.message : "Unknown error occurred";

            // 500 에러는 보통 데이터가 없거나 서버 문제를 의미함
            if (
                err instanceof Error &&
                (err.message.includes("500") ||
                    err.message.includes("Internal Server Error"))
            ) {
                requiresUpload.set(true);
                hasData.set(false);
                error.set(
                    "서버에 데이터가 없습니다. CSV 파일을 업로드해주세요."
                );
            } else {
                error.set(errorMessage);

                // Check if the error indicates upload is required
                if (
                    err instanceof Error &&
                    (err.message.includes("upload") ||
                        err.message.includes("업로드"))
                ) {
                    requiresUpload.set(true);
                    hasData.set(false);
                }
            }
        } finally {
            isLoading.set(false);
            isLoadingMore.set(false);
        }
    },

    async loadMore(): Promise<void> {
        const currentPagination = await new Promise<PaginationState>(
            (resolve) => {
                const unsubscribe = pagination.subscribe((p) => {
                    resolve(p);
                    unsubscribe();
                });
            }
        );

        if (!currentPagination.hasNext) return;

        pagination.update((p) => ({ ...p, page: p.page + 1 }));
        await this.loadStations(false);
    },

    async loadStationData(stationId: string): Promise<void> {
        if (!stationId) return;

        isLoading.set(true);
        error.set(null);
        insufficientData.set(null);

        try {
            const [analysis, prediction, monthlyContract] = await Promise.all([
                apiService.getStationAnalysis(stationId).catch((e) => ({
                    success: false,
                    error_code: "INTERNAL_ERROR",
                    error: e instanceof Error ? e.message : "station-analysis 요청 실패",
                })),
                apiService.getPrediction(stationId).catch((e) => ({
                    success: false,
                    error_code: "INTERNAL_ERROR",
                    error: e instanceof Error ? e.message : "prediction 요청 실패",
                })),
                apiService.getMonthlyContract(
                    stationId,
                    new Date().getFullYear(),
                    new Date().getMonth() + 1
                ).catch((e) => ({
                    success: false,
                    error_code: "INTERNAL_ERROR",
                    error: e instanceof Error ? e.message : "monthly-contract 요청 실패",
                })),
            ]);

            // 데이터 부족·누락 응답을 감지하여 전용 스토어에 안내 저장
            const anyInsufficient = [analysis, prediction, monthlyContract].find(
                (r: any) => r && r.success === false &&
                    (r.error_code === "INSUFFICIENT_DATA" || r.error_code === "NO_DATA")
            ) as any;

            if (anyInsufficient) {
                insufficientData.set({
                    error: anyInsufficient.error || "분석에 필요한 데이터가 부족합니다.",
                    error_code: anyInsufficient.error_code || "INSUFFICIENT_DATA",
                    guidance: anyInsufficient.guidance || [],
                    details: anyInsufficient.details || undefined,
                });
            }

            stationData.set({
                analysis,
                prediction,
                monthlyContract,
            });
        } catch (err: unknown) {
            const errorMessage =
                err instanceof Error ? err.message : "Unknown error occurred";
            error.set(errorMessage);
        } finally {
            isLoading.set(false);
        }
    },

    setCurrentStation(station: ChargingStation): void {
        currentStation.set(station);
    },

    clearError(): void {
        error.set(null);
    },

    async checkSystemStatus(): Promise<void> {
        try {
            const status = await apiService.getSystemStatus();
            systemStatus.set(status);
            hasData.set(status.hasData);
            requiresUpload.set(!status.hasData);
        } catch (err: unknown) {
            requiresUpload.set(true);
            hasData.set(false);
        }
    },

    async uploadCsv(file: File): Promise<void> {
        isLoading.set(true);
        error.set(null);

        try {
            const result = await apiService.uploadCsv(file);

            if (result.success) {
                requiresUpload.set(false);
                hasData.set(true);
                // Refresh station data
                await this.loadStations();
            } else {
                error.set(result.message || "업로드에 실패했습니다.");
            }
        } catch (err: unknown) {
            const errorMessage =
                err instanceof Error ? err.message : "Upload failed";
            error.set(errorMessage);
        } finally {
            isLoading.set(false);
        }
    },
};
