import { writable, derived } from 'svelte/store';
import type { ChargingStation } from '../lib/types';

// 검색 관련 상태
export const searchQuery = writable<string>('');
export const sortBy = writable<string>('id');
export const sortOrder = writable<'asc' | 'desc'>('asc');

// 전체 충전소 데이터 (클라이언트 사이드 검색용)
export const allStations = writable<ChargingStation[]>([]);

// 검색 성능을 위한 인덱스
export const stationIndex = writable<Map<string, ChargingStation>>(new Map());

interface SearchIndex {
    byId: Map<string, ChargingStation>;
    byName: Map<string, ChargingStation[]>;
    byLocation: Map<string, ChargingStation[]>;
    byRegion: Map<string, ChargingStation[]>;
    keywords: Map<string, Set<string>>; // 키워드 -> 충전소 ID 세트
}

export const searchIndex = writable<SearchIndex>({
    byId: new Map(),
    byName: new Map(),
    byLocation: new Map(),
    byRegion: new Map(),
    keywords: new Map()
});

// 클라이언트 사이드 필터링 로직
export const filteredStations = derived(
    [allStations, searchQuery, sortBy, sortOrder, searchIndex],
    ([$allStations, $searchQuery, $sortBy, $sortOrder, $searchIndex]) => {
        if ($allStations.length === 0) return [];

        let filtered = [...$allStations];

        // 검색 필터링
        if ($searchQuery && $searchQuery.trim()) {
            const query = $searchQuery.toLowerCase().trim();
            
            filtered = $allStations.filter(station => {
                return (
                    station.id?.toLowerCase().includes(query) ||
                    station.name?.toLowerCase().includes(query) ||
                    station.location?.toLowerCase().includes(query) ||
                    station.region?.toLowerCase().includes(query) ||
                    station.city?.toLowerCase().includes(query)
                );
            });
        }

        // 정렬
        filtered.sort((a, b) => {
            let aValue: any = '';
            let bValue: any = '';

            switch ($sortBy) {
                case 'id':
                    aValue = a.id || '';
                    bValue = b.id || '';
                    break;
                case 'name':
                    aValue = a.name || '';
                    bValue = b.name || '';
                    break;
                case 'location':
                    aValue = a.location || '';
                    bValue = b.location || '';
                    break;
                case 'region':
                    aValue = a.region || '';
                    bValue = b.region || '';
                    break;
                case 'city':
                    aValue = a.city || '';
                    bValue = b.city || '';
                    break;
                case 'sessions':
                    aValue = a.data_sessions || 0;
                    bValue = b.data_sessions || 0;
                    break;
                case 'avg_power':
                    aValue = parseFloat(a.avg_power || '0');
                    bValue = parseFloat(b.avg_power || '0');
                    break;
                case 'max_power':
                    aValue = parseFloat(a.max_power || '0');
                    bValue = parseFloat(b.max_power || '0');
                    break;
                case 'capacity_efficiency':
                    aValue = parseFloat(a.capacity_efficiency?.replace('%', '') || '0');
                    bValue = parseFloat(b.capacity_efficiency?.replace('%', '') || '0');
                    break;
                case 'last_activity':
                    aValue = new Date(a.last_activity || '1970-01-01');
                    bValue = new Date(b.last_activity || '1970-01-01');
                    break;
                default:
                    aValue = a.id || '';
                    bValue = b.id || '';
            }

            let comparison = 0;
            if (typeof aValue === 'string' && typeof bValue === 'string') {
                comparison = aValue.localeCompare(bValue);
            } else if (typeof aValue === 'number' && typeof bValue === 'number') {
                comparison = aValue - bValue;
            } else if (aValue instanceof Date && bValue instanceof Date) {
                comparison = aValue.getTime() - bValue.getTime();
            }

            return $sortOrder === 'desc' ? -comparison : comparison;
        });

        return filtered;
    }
);

// 검색 인덱스 구축 함수
export function buildSearchIndex(stations: ChargingStation[]): SearchIndex {
    const index: SearchIndex = {
        byId: new Map(),
        byName: new Map(),
        byLocation: new Map(),
        byRegion: new Map(),
        keywords: new Map()
    };

    stations.forEach(station => {
        // ID 인덱스
        if (station.id) {
            index.byId.set(station.id.toLowerCase(), station);
        }

        // Name 인덱스
        if (station.name) {
            const nameKey = station.name.toLowerCase();
            if (!index.byName.has(nameKey)) {
                index.byName.set(nameKey, []);
            }
            index.byName.get(nameKey)?.push(station);
        }

        // Location 인덱스
        if (station.location) {
            const locationKey = station.location.toLowerCase();
            if (!index.byLocation.has(locationKey)) {
                index.byLocation.set(locationKey, []);
            }
            index.byLocation.get(locationKey)?.push(station);
        }

        // Region 인덱스
        if (station.region) {
            const regionKey = station.region.toLowerCase();
            if (!index.byRegion.has(regionKey)) {
                index.byRegion.set(regionKey, []);
            }
            index.byRegion.get(regionKey)?.push(station);
        }

        // 키워드 인덱스 (전체 텍스트 검색용)
        const keywords = [
            station.id,
            station.name,
            station.location,
            station.region,
            station.city
        ].filter(Boolean).join(' ').toLowerCase().split(/\s+/);

        keywords.forEach(keyword => {
            if (!index.keywords.has(keyword)) {
                index.keywords.set(keyword, new Set());
            }
            if (station.id) {
                index.keywords.get(keyword)?.add(station.id);
            }
        });
    });

    return index;
}

// 고성능 검색 함수
export function searchStations(
    stations: ChargingStation[], 
    query: string, 
    index: SearchIndex
): ChargingStation[] {
    if (!query.trim()) return stations;

    const queryLower = query.toLowerCase().trim();
    const matchedIds = new Set<string>();

    // 1. 정확한 ID 매치
    if (index.byId.has(queryLower)) {
        const station = index.byId.get(queryLower);
        if (station?.id) matchedIds.add(station.id);
    }

    // 2. 키워드 기반 검색
    const queryWords = queryLower.split(/\s+/);
    queryWords.forEach(word => {
        // 부분 매치
        for (const [keyword, stationIds] of index.keywords) {
            if (keyword.includes(word)) {
                stationIds.forEach(id => matchedIds.add(id));
            }
        }
    });

    // 3. 결과 반환
    return stations.filter(station => 
        station.id && matchedIds.has(station.id)
    );
}

// 검색 액션들
export const searchActions = {
    // 전체 데이터 로드 및 인덱스 구축
    initializeSearch(stations: ChargingStation[]) {
        allStations.set(stations);
        const index = buildSearchIndex(stations);
        searchIndex.set(index);
    },

    // 검색어 업데이트
    updateSearch(query: string) {
        searchQuery.set(query);
    },

    // 정렬 업데이트
    updateSort(field: string, order: 'asc' | 'desc') {
        sortBy.set(field);
        sortOrder.set(order);
    },

    // 검색 초기화
    clearSearch() {
        searchQuery.set('');
    }
};