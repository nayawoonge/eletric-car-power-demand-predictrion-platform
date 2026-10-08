let chartModules = null;
let loadingPromise = null;

export async function getChartModules() {
    // 이미 로드된 경우
    if (chartModules) {
        return chartModules;
    }
    
    // 현재 로딩 중인 경우 (중복 로딩 방지)
    if (loadingPromise) {
        return loadingPromise;
    }
    
    // 서버사이드 렌더링 환경 체크
    if (typeof window === 'undefined') {
        return null;
    }
    
    // 로딩 시작
    loadingPromise = loadChartModules();
    
    try {
        chartModules = await loadingPromise;
        return chartModules;
    } catch (error) {
        // 로딩 실패 시 재시도 가능하도록 Promise 초기화
        loadingPromise = null;
        throw error;
    }
}

async function loadChartModules() {
    try {
        const [{ default: ChartJS }, zoomPlugin, dateAdapter] = await Promise.all([
            import("chart.js/auto"),
            import("chartjs-plugin-zoom"),
            import("chartjs-adapter-date-fns") // 날짜 어댑터 추가
        ]);
        
        // 플러그인 등록
        ChartJS.register(zoomPlugin.default);
        
        return {
            Chart: ChartJS,
            zoomPlugin: zoomPlugin.default,
            dateAdapter: dateAdapter.default
        };
    } catch (error) {
        console.error('Chart.js 모듈 로드 실패:', error);
        throw new Error(`Chart.js 로드 실패: ${error.message}`);
    }
}

// 페이지 로드 시 미리 로드 (성능 최적화)
export function preloadChartModules() {
    if (typeof window !== 'undefined' && !chartModules && !loadingPromise) {
        getChartModules().catch(error => {
            console.warn('Chart.js 미리 로드 실패:', error);
        });
    }
}

// 메모리 정리 (필요한 경우)
export function clearChartModules() {
    chartModules = null;
    loadingPromise = null;
}