from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from ..data.loader import ChargingDataLoader


class StationService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._cached_data = {}
        self._cache_timestamp = {}
        self._cache_ttl = 1800  # 30분 캐시 (성능 개선)
        self._long_cache_ttl = 3600  # 1시간 캐시 (정적 데이터용)

    def _is_cache_valid(self, key: str, use_long_cache: bool = False) -> bool:
        if key not in self._cache_timestamp:
            return False
        ttl = self._long_cache_ttl if use_long_cache else self._cache_ttl
        return (
            datetime.now() - self._cache_timestamp[key]
        ).total_seconds() < ttl

    def _set_cache(self, key: str, data: Any) -> None:
        self._cached_data[key] = data
        self._cache_timestamp[key] = datetime.now()

    def _get_cache(self, key: str, use_long_cache: bool = False) -> Optional[Any]:
        if self._is_cache_valid(key, use_long_cache):
            return self._cached_data.get(key)
        return None

    def clear_cache(self) -> None:
        self._cached_data.clear()
        self._cache_timestamp.clear()

    def _clean_for_json(self, obj: Any) -> Any:
        if obj is None:
            return None
        elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        elif isinstance(obj, (np.float64, np.float32, np.float16)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, dict):
            return {k: self._clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._clean_for_json(item) for item in obj]
        elif pd.isna(obj):
            return None
        else:
            return obj

    def list_stations(
        self, search: str = None, sort_by: str = "id", sort_order: str = "asc"
    ) -> Dict[str, Any]:
        cache_key = f"stations_{search}_{sort_by}_{sort_order}"
        # 정적 데이터는 긴 캐시 사용
        cached_result = self._get_cache(cache_key, use_long_cache=True)
        if cached_result:
            return cached_result

        try:
            loader = ChargingDataLoader("ALL")
            file_info = loader.list_available_files()

            if file_info["total_files"] == 0:
                return {
                    "success": False,
                    "message": "CSV 파일이 없습니다.",
                    "stations": [],
                    "total": 0,
                }

            # 최적화: 최근 데이터 우선 로드 (성능 개선)
            df = loader.load_historical_sessions(days=365)  # 1년 데이터로 제한
            if df.empty:
                return {
                    "success": False,
                    "message": "데이터가 없습니다.",
                    "stations": [],
                    "total": 0,
                }

            # 충전소별 집계 데이터 생성
            stations = self._process_station_list(df, search, sort_by, sort_order)

            result = {
                "success": True,
                "stations": self._clean_for_json(stations),
                "total": len(stations),
                "last_updated": datetime.now().isoformat(),
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            self.logger.error(f"Error listing stations: {e}", exc_info=True)
            return {"success": False, "error": str(e), "stations": [], "total": 0}

    def _process_station_list(
        self,
        df: pd.DataFrame,
        search: str = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> List[Dict[str, Any]]:
        # 충전소 ID 컬럼 찾기
        station_col = self._find_station_column(df)
        if not station_col:
            return []

        # 충전소별 집계 - 모든 충전소 처리 (필요시 페이지네이션으로 제한)
        stations = []
        unique_stations = df[station_col].dropna().unique()

        # 데이터량이 많은 경우 세션 수 기준으로 정렬하여 처리 (상한선 제거)
        if len(unique_stations) > 50:
            station_counts = df[station_col].value_counts()
            unique_stations = station_counts.index.tolist()  # 모든 충전소 포함

        for station_id in unique_stations:
            station_data = df[df[station_col] == station_id].copy()
            if station_data.empty:
                continue

            # 기본 정보
            station_info = {
                "id": str(station_id),
                "name": self._get_station_name(station_data, station_id),
                "location": self._get_station_location(station_data),
                "region": self._get_station_region(station_data),
                "city": self._get_station_city(station_data),
                "charger_type": self._get_charger_type(station_data),
                "connector_type": self._get_connector_type(station_data),
            }

            # 집계된 메트릭 - 백엔드에서 모든 계산 완료
            metrics = self._calculate_station_metrics(station_data, station_info)
            station_info.update(metrics)

            # 검색 필터 적용
            if search and not self._matches_search(station_info, search):
                continue

            stations.append(station_info)

        # 정렬
        stations = self._sort_stations(stations, sort_by, sort_order)

        return stations

    def _find_station_column(self, df: pd.DataFrame) -> Optional[str]:
        station_id_cols = ["충전소ID", "station_id", "충전소명", "STATION_ID"]
        for col in station_id_cols:
            if col in df.columns:
                return col
        return None

    def _get_station_name(self, station_data: pd.DataFrame, station_id: str) -> str:
        name_cols = ["충전소명", "station_name", "name"]
        for col in name_cols:
            if col in station_data.columns:
                name = (
                    station_data[col].iloc[0]
                    if not station_data[col].isna().all()
                    else None
                )
                if name:
                    return str(name)
        return f"충전소 {station_id}"

    def _get_station_location(self, station_data: pd.DataFrame) -> str:
        location_cols = ["충전소주소", "주소", "location", "위치", "address"]
        for col in location_cols:
            if col in station_data.columns:
                location = (
                    station_data[col].iloc[0]
                    if not station_data[col].isna().all()
                    else None
                )
                if location:
                    return str(location)
        return "위치 미상"

    def _get_station_region(self, station_data: pd.DataFrame) -> str:
        region_cols = ["권역", "region", "시도"]
        for col in region_cols:
            if col in station_data.columns:
                region = (
                    station_data[col].iloc[0]
                    if not station_data[col].isna().all()
                    else None
                )
                if region:
                    return str(region)
        return "미상"

    def _get_station_city(self, station_data: pd.DataFrame) -> str:
        city_cols = ["시군구", "city", "구", "시"]
        for col in city_cols:
            if col in station_data.columns:
                city = (
                    station_data[col].iloc[0]
                    if not station_data[col].isna().all()
                    else None
                )
                if city:
                    return str(city)
        return "미상"

    def _get_charger_type(self, station_data: pd.DataFrame) -> str:
        # 다중 조건을 통한 더 정확한 충전기 타입 판별
        power_cols = ["순간최고전력", "max_power", "전력"]
        
        for col in power_cols:
            if col in station_data.columns:
                power_data = station_data[col].dropna()
                if len(power_data) > 0:
                    max_power = power_data.max()
                    mean_power = power_data.mean()
                    percentile_95 = power_data.quantile(0.95)
                    
                    # 다중 조건으로 급속충전기 판별
                    conditions = [
                        max_power >= 30,  # 최대 전력 30kW 이상
                        mean_power >= 15,  # 평균 전력 15kW 이상  
                        percentile_95 >= 25,  # 95% 백분위 25kW 이상
                    ]
                    
                    # 조건 중 2개 이상 만족하면 급속충전기
                    if sum(conditions) >= 2:
                        return "급속충전기 (DC)"
                    elif max_power >= 20:  # 단일 조건: 최대 전력 20kW 이상
                        return "급속충전기 (DC)"
                    else:
                        return "완속충전기 (AC)"
        
        return "미상"

    def _is_fast_charger(self, station_data: pd.DataFrame) -> bool:
        charger_type = self._get_charger_type(station_data)
        return "급속" in charger_type or "DC" in charger_type

    def _get_charger_max_contract(self, station_data: pd.DataFrame) -> int:
        if self._is_fast_charger(station_data):
            return 100  # 급속충전기: 100kW
        else:
            return 7  # 완속충전기: 7kW

    def _calculate_optimal_contract_power(
        self, station_data: pd.DataFrame, percentile_95: float
    ) -> dict:
        is_fast_charger = self._is_fast_charger(station_data)
        
        # 예측값이 높으면 급속충전기로 재판별 (보정 로직)
        if not is_fast_charger and percentile_95 >= 20:
            self.logger.info(f"Reclassifying as fast charger due to high predicted power: {percentile_95:.1f}kW")
            is_fast_charger = True
        
        # 충전기 타입에 따른 최대 계약전력 설정
        max_limit = 100 if is_fast_charger else 7

        # 실제 데이터 기반 계산 - 더 정확한 예측을 위해 개선
        if is_fast_charger:
            # 급속충전기: 데이터 품질에 따른 적응형 안전마진
            data_count = (
                len(station_data)
                if station_data is not None and not station_data.empty
                else 0
            )

            if data_count > 1000:
                # 충분한 데이터: 낮은 안전마진
                safety_margin = 0.12 if percentile_95 > 80 else 0.08
            elif data_count > 500:
                # 보통 데이터: 중간 안전마진
                safety_margin = 0.15 if percentile_95 > 60 else 0.12
            else:
                # 부족한 데이터: 높은 안전마진
                safety_margin = 0.20 if percentile_95 > 60 else 0.15

            # 실제 전력 패턴에 기반한 예측값 계산
            raw_prediction = percentile_95 * (1 + safety_margin)

            # 5kW 단위로 반올림하되, 실제 데이터 패턴 고려
            raw_prediction = round(raw_prediction / 5) * 5
            raw_prediction = max(50, raw_prediction)  # 최소 50kW

            # 계약전력은 제한 적용
            contract_recommendation = min(max_limit, raw_prediction)
        else:
            # 완속충전기: 데이터 품질에 따른 적응형 안전마진
            data_count = (
                len(station_data)
                if station_data is not None and not station_data.empty
                else 0
            )

            if data_count > 500:
                safety_margin = 0.08 if percentile_95 > 5 else 0.05
            else:
                safety_margin = 0.12 if percentile_95 > 5 else 0.08

            raw_prediction = percentile_95 * (1 + safety_margin)
            raw_prediction = round(raw_prediction)  # 1kW 단위
            raw_prediction = max(3, raw_prediction)  # 최소 3kW

            # 계약전력은 제한 적용
            contract_recommendation = min(max_limit, raw_prediction)

        # 로깅으로 계산 과정 추적
        self.logger.info(
            f"Contract calculation: percentile_95={percentile_95:.1f}kW, "
            f"raw_prediction={raw_prediction:.1f}kW, "
            f"contract_recommendation={contract_recommendation:.1f}kW, "
            f"max_limit={max_limit}kW, is_fast={is_fast_charger}, data_count={data_count if 'data_count' in locals() else 0}"
        )

        return self._clean_for_json(
            {
                "raw_prediction": raw_prediction,
                "contract_recommendation": contract_recommendation,
                "is_capped": raw_prediction > contract_recommendation,
                "max_limit": max_limit,
                "charger_type": "fast" if is_fast_charger else "slow",
            }
        )

    def _get_connector_type(self, station_data: pd.DataFrame) -> str:
        connector_cols = ["커넥터타입", "connector_type"]
        for col in connector_cols:
            if col in station_data.columns:
                connector = (
                    station_data[col].iloc[0]
                    if not station_data[col].isna().all()
                    else None
                )
                if connector:
                    return str(connector)
        return "DC콤보"

    def _get_station_name_by_id(self, station_id: str) -> str:
        try:
            loader = ChargingDataLoader(station_id)
            df = loader.load_csv_file()
            if df.empty:
                return station_id

            station_col = self._find_station_column(df)
            if not station_col:
                return station_id

            station_data = df[df[station_col] == station_id].copy()
            if station_data.empty:
                return station_id

            return self._get_station_name(station_data, station_id)
        except Exception:
            return station_id

    def _calculate_station_metrics(self, station_data: pd.DataFrame, station_info: Dict[str, Any] = None) -> Dict[str, Any]:
        metrics = {
            "data_sessions": len(station_data),
            "capacity_efficiency": "N/A",
            "last_activity": None,
        }

        # 전력 통계
        power_cols = ["순간최고전력", "max_power", "전력"]
        power_col = None
        for col in power_cols:
            if col in station_data.columns:
                power_col = col
                break

        if power_col:
            power_data = station_data[power_col].dropna()
            if not power_data.empty:
                metrics.update(
                    {
                        "avg_power": round(power_data.mean(), 1),
                        "max_power": round(power_data.max(), 1),
                        "min_power": round(power_data.min(), 1),
                        "power_std": round(power_data.std(), 1),
                        "capacity_efficiency": self._calculate_capacity_efficiency(power_data, station_info.get('charger_type') if station_info else '미상'),
                    }
                )

        # 시간 정보
        date_cols = ["충전시작일시", "start_time", "시작시간"]
        date_col = None
        for col in date_cols:
            if col in station_data.columns:
                date_col = col
                break

        if date_col:
            dates = pd.to_datetime(station_data[date_col], errors="coerce").dropna()
            if not dates.empty:
                metrics["last_activity"] = dates.max().strftime("%Y-%m-%d %H:%M")
                metrics["first_activity"] = dates.min().strftime("%Y-%m-%d %H:%M")
                metrics["active_days"] = (dates.max() - dates.min()).days + 1

        return metrics
    
    def _calculate_capacity_efficiency(self, power_data: pd.Series, charger_type: str) -> str:
        """
        충전기 용량 대비 효율성 계산
        완속충전기(AC): 7kW 기준
        급속충전기(DC): 100kW 기준
        """
        if power_data.empty:
            return "N/A"
        
        avg_power = power_data.mean()
        
        # 충전기 타입별 정격 용량 설정
        rated_capacity = {
            "완속충전기 (AC)": 7.0,
            "급속충전기 (DC)": 100.0,
            "미상": 50.0  # 기본값
        }
        
        capacity = rated_capacity.get(charger_type, 50.0)
        efficiency = min(100.0, (avg_power / capacity) * 100)
        
        return f"{round(efficiency, 1)}%"

    def _matches_search(self, station_info: Dict[str, Any], search: str) -> bool:
        search_lower = search.lower()
        searchable_fields = [
            str(station_info.get("id", "")),
            str(station_info.get("name", "")),
            str(station_info.get("location", "")),
        ]

        return any(search_lower in field.lower() for field in searchable_fields)

    def _sort_stations(
        self, stations: List[Dict[str, Any]], sort_by: str, sort_order: str
    ) -> List[Dict[str, Any]]:
        reverse = sort_order.lower() == "desc"

        sort_key_map = {
            "id": lambda x: x.get("id", ""),
            "name": lambda x: x.get("name", ""),
            "location": lambda x: x.get("location", ""),
            "region": lambda x: x.get("region", ""),
            "city": lambda x: x.get("city", ""),
            "sessions": lambda x: x.get("data_sessions", 0),
            "last_activity": lambda x: x.get("last_activity", ""),
            "avg_power": lambda x: x.get("avg_power", 0),
            "max_power": lambda x: x.get("max_power", 0),
            "capacity_efficiency": lambda x: float(x.get("capacity_efficiency", "0").rstrip("%"))
            if x.get("capacity_efficiency") != "N/A"
            else 0,
            "charger_type": lambda x: x.get("charger_type", ""),
        }

        sort_func = sort_key_map.get(sort_by, sort_key_map["id"])

        try:
            return sorted(stations, key=sort_func, reverse=reverse)
        except Exception as e:
            self.logger.warning(f"Sort failed: {e}, using default")
            return stations

    def get_station_timeseries(
        self, station_id: str, days: int = 3650
    ) -> Dict[str, Any]:
        cache_key = f"timeseries_{station_id}_{days}"
        cached_result = self._get_cache(cache_key)
        if cached_result:
            return cached_result

        try:
            loader = ChargingDataLoader(station_id)
            df = loader.load_historical_sessions(days=days)

            if df.empty:
                return {
                    "success": False,
                    "message": "데이터가 없습니다.",
                    "data": [],
                    "station_id": station_id,
                }

            # 완전 가공된 시계열 데이터 생성
            timeseries_data, monthly_peaks, data_info = self._process_timeseries_data(
                df
            )

            result = {
                "success": True,
                "station_id": station_id,
                "data": timeseries_data,
                "monthly_peaks": monthly_peaks,
                "data_info": data_info,
                "timestamp": datetime.now().isoformat(),
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            self.logger.error(
                f"Error getting timeseries for {station_id}: {e}", exc_info=True
            )
            return {"success": False, "error": str(e), "station_id": station_id}

    def _process_timeseries_data(self, df: pd.DataFrame):
        # 날짜와 전력 컬럼 찾기
        date_columns = [
            col
            for col in df.columns
            if any(keyword in col for keyword in ["일시", "date", "time", "시작"])
        ]
        power_columns = [
            col for col in df.columns if "전력" in col or "power" in col.lower()
        ]

        if not date_columns or not power_columns:
            return [], [], {}

        date_col = date_columns[0]
        power_col = power_columns[0]

        # 데이터 정리
        df_clean = df[[date_col, power_col]].copy()
        df_clean = df_clean.dropna()
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")
        df_clean[power_col] = pd.to_numeric(df_clean[power_col], errors="coerce")
        df_clean = df_clean.dropna()

        if df_clean.empty:
            return [], [], {}

        # 시계열 데이터 생성
        timeseries_data = []
        for _, row in df_clean.iterrows():
            timeseries_data.append(
                {
                    "timestamp": row[date_col].isoformat(),
                    "power": round(float(row[power_col]), 2),
                }
            )

        # 월별 최대값 계산 - 백엔드에서 완료
        df_clean["year_month"] = df_clean[date_col].dt.to_period("M")
        monthly_max = df_clean.groupby("year_month")[power_col].max().reset_index()

        monthly_peaks = []
        for _, row in monthly_max.iterrows():
            period = row["year_month"]
            monthly_peaks.append(
                {
                    "month": f"{period.year}-{period.month:02d}",
                    "peak_power": round(float(row[power_col]), 2),
                    "label": f"{period.year}.{period.month:02d}",
                }
            )

        # 데이터 정보
        data_info = {
            "total_records": len(timeseries_data),
            "date_range": {
                "start": df_clean[date_col].min().isoformat(),
                "end": df_clean[date_col].max().isoformat(),
            },
            "power_stats": {
                "min": round(float(df_clean[power_col].min()), 2),
                "max": round(float(df_clean[power_col].max()), 2),
                "mean": round(float(df_clean[power_col].mean()), 2),
                "std": round(float(df_clean[power_col].std()), 2),
            },
        }

        return timeseries_data, monthly_peaks, data_info

    def get_station_prediction(self, station_id: str) -> Dict[str, Any]:
        cache_key = f"prediction_{station_id}"
        cached_result = self._get_cache(cache_key)
        if cached_result:
            return cached_result

        try:
            loader = ChargingDataLoader(station_id)
            patterns = loader.analyze_charging_patterns()

            if not patterns or "power_statistics" not in patterns:
                return {
                    "success": False,
                    "message": "예측을 위한 충분한 데이터가 없습니다.",
                    "station_id": station_id,
                }

            # 예측 계산 - 백엔드에서 모든 비즈니스 로직 수행
            prediction_result = self._calculate_predictions(patterns, station_id)
            prediction_result["station_id"] = station_id
            prediction_result["station_name"] = self._get_station_name_by_id(station_id)

            self._set_cache(cache_key, prediction_result)
            return self._clean_for_json(prediction_result)

        except Exception as e:
            self.logger.error(
                f"Error getting prediction for {station_id}: {e}", exc_info=True
            )
            return {"success": False, "error": str(e), "station_id": station_id}

    def _calculate_predictions(
        self, patterns: Dict[str, Any], station_id: str
    ) -> Dict[str, Any]:
        from ..prediction.engine_factory import get_prediction_engine

        # 고급 예측 엔진 가져오기 (캐시된 인스턴스 - 빠른 로딩)
        prediction_engine = get_prediction_engine()

        # 원본 데이터 가져오기 (station_id 매개변수 유지)
        try:
            loader = ChargingDataLoader(station_id)
            raw_data = loader.load_historical_sessions(days=365, merge_all=True)

            # 충전기 타입 확인
            charger_type = self._get_charger_type(raw_data)

            # 고급 모델로 예측 수행
            ensemble_result = prediction_engine.predict_contract_power(
                raw_data, station_id, charger_type
            )

            # 기존 통계 정보도 유지
            power_stats = patterns["power_statistics"]

            # 실제 raw_data에서 95백분위수 직접 계산 (더 정확함)
            if not raw_data.empty:
                power_columns = [
                    col for col in raw_data.columns if "전력" in col and "최고" in col
                ]
                if power_columns:
                    power_data = raw_data[power_columns[0]].dropna()
                    if not power_data.empty:
                        current_peak = power_data.quantile(0.95)
                    else:
                        current_peak = power_stats.get("percentile_95", 45.0)
                else:
                    current_peak = power_stats.get("percentile_95", 45.0)
            else:
                current_peak = power_stats.get("percentile_95", 45.0)

            confidence = min(0.95, max(0.4, power_stats.get("count", 0) / 1000))

            # 실제 데이터로부터 월별 차트 데이터 생성
            chart_data = self._generate_monthly_chart_data(patterns)

            # 데이터 범위 정보
            data_start_date = patterns.get("date_range", {}).get(
                "start", datetime.now() - timedelta(days=365)
            )
            data_end_date = patterns.get("date_range", {}).get("end", datetime.now())

            # 마지막달 최고 전력 (실제 데이터 기준)
            last_month_peak = current_peak
            if chart_data:
                # 실제 데이터가 있는 마지막 달 찾기
                for item in reversed(chart_data):
                    if item.get("actual") is not None:
                        last_month_peak = item["actual"]
                        break

            # 충전기 타입별 제한을 적용한 고급 모델 예측 결과
            try:
                # 충전기 타입 판별을 위해 더 많은 데이터 사용 (기존 raw_data 재활용)
                if not raw_data.empty:
                    max_contract_advanced = self._get_charger_max_contract(raw_data)
                    is_fast_charger_advanced = self._is_fast_charger(raw_data)
                else:
                    # 데이터가 없으면 별도 로드
                    loader_temp = ChargingDataLoader(station_id)
                    station_df_temp = loader_temp.load_historical_sessions(days=90)
                    max_contract_advanced = self._get_charger_max_contract(
                        station_df_temp
                    )
                    is_fast_charger_advanced = self._is_fast_charger(station_df_temp)
                self.logger.info(
                    f"Station {station_id}: max_contract={max_contract_advanced}kW, fast_charger={is_fast_charger_advanced}"
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to determine charger type for {station_id}: {e}"
                )
                max_contract_advanced = 100
                is_fast_charger_advanced = True

            # 실제 데이터 기반 최적 계약전력 계산
            raw_prediction = ensemble_result.raw_prediction  # 제한 없는 원본 예측값
            self.logger.info(
                f"Station {station_id}: current_peak={current_peak:.1f}kW (used for contract calculation)"
            )
            optimal_result = self._calculate_optimal_contract_power(
                raw_data, current_peak
            )

            # 고급 모델 예측과 실제 데이터 기반 계산 중 적절한 값 선택
            if (
                abs(raw_prediction - optimal_result["raw_prediction"])
                / optimal_result["raw_prediction"]
                < 0.2
            ):  # 20% 이내 차이면 고급 모델 사용
                # 고급 모델 사용하지만 계약전력 제한은 적용
                algorithm_prediction = raw_prediction
                recommended_contract_kw = min(max_contract_advanced, raw_prediction)
            else:
                # 실제 데이터 기반 사용
                algorithm_prediction = optimal_result["raw_prediction"]
                recommended_contract_kw = optimal_result["contract_recommendation"]

            # 예측값이 제한을 넘는지 확인
            prediction_exceeds_limit = algorithm_prediction > recommended_contract_kw

            # Extract pattern information from ensemble result
            pattern_info = {}
            if ensemble_result.pattern_factors:
                pattern_info = {
                    "pattern_confidence": ensemble_result.pattern_factors.confidence,
                    "data_quality": ensemble_result.pattern_factors.data_quality,
                    "seasonal_strength": ensemble_result.pattern_factors.calculation_metadata.get("pattern_strength", {}).get("seasonal_strength", 0.0),
                    "weekly_strength": ensemble_result.pattern_factors.calculation_metadata.get("pattern_strength", {}).get("weekly_strength", 0.0),
                    "trend_factor": ensemble_result.pattern_factors.trend_factor,
                    "analysis_method": "dynamic_pattern_analysis"
                }
            else:
                pattern_info = {
                    "analysis_method": "fallback_static_patterns",
                    "pattern_confidence": 0.3
                }

            self.logger.info(
                f"Advanced prediction for {station_id}: algorithm={algorithm_prediction}kW, contract={recommended_contract_kw}kW, capped={prediction_exceeds_limit}, pattern_confidence={pattern_info.get('pattern_confidence', 0):.2f}"
            )

            # 신뢰도 계산 (불확실성 기반)
            model_confidence = max(0.4, 1.0 - (ensemble_result.uncertainty / 100.0))
            final_confidence = min(0.95, (confidence + model_confidence) / 2)

        except Exception as e:
            self.logger.warning(
                f"Advanced prediction failed for {station_id}: {e}, using fallback"
            )
            # 폴백: 기존 방식
            power_stats = patterns["power_statistics"]
            current_peak = power_stats.get("percentile_95", 45.0)
            confidence = min(0.95, max(0.4, power_stats.get("count", 0) / 1000))

            chart_data = self._generate_monthly_chart_data(patterns)
            data_start_date = patterns.get("date_range", {}).get(
                "start", datetime.now() - timedelta(days=365)
            )
            data_end_date = patterns.get("date_range", {}).get("end", datetime.now())

            last_month_peak = current_peak
            if chart_data:
                for item in reversed(chart_data):
                    if item.get("actual") is not None:
                        last_month_peak = item["actual"]
                        break

            # 충전기 타입별 제한 적용
            try:
                loader = ChargingDataLoader(station_id)
                station_df = loader.load_historical_sessions(days=30)
                max_contract = self._get_charger_max_contract(station_df)
                is_fast_charger_fallback = self._is_fast_charger(station_df)
                self.logger.info(
                    f"Fallback for {station_id}: max_contract={max_contract}kW, fast_charger={is_fast_charger_fallback}"
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to determine charger type for {station_id}: {e}"
                )
                max_contract = 100  # 기본값
                is_fast_charger_fallback = True

            chart_data = self._generate_monthly_chart_data(patterns)

            # 실제 데이터 기반 최적 계약전력 계산
            optimal_result = self._calculate_optimal_contract_power(
                station_df, current_peak
            )
            algorithm_prediction = optimal_result["raw_prediction"]
            recommended_contract_kw = optimal_result["contract_recommendation"]
            prediction_exceeds_limit = optimal_result["is_capped"]

            self.logger.info(
                f"Fallback prediction for {station_id}: percentile_95={current_peak}kW, algorithm={algorithm_prediction}kW -> contract={recommended_contract_kw}kW, capped={prediction_exceeds_limit}"
            )
            final_confidence = confidence
            ensemble_result = None

        # 결과 준비
        result = {
            "success": True,
            "station_id": "",  # Will be set by caller
            "station_name": "",  # Will be set by caller
            "predicted_peak": current_peak,  # Frontend expects this field
            "confidence": final_confidence
            if "final_confidence" in locals()
            else confidence,
            "predicted_hour": self._get_peak_hour(patterns),
            "method": "advanced_ensemble_models"
            if ensemble_result
            else "percentile_95_seasonal",
            "timestamp": datetime.now().isoformat(),
            # Additional data for charts
            "current_peak": current_peak,
            "chart_data": chart_data,
            "last_month_peak": last_month_peak,
            "recommended_contract_kw": recommended_contract_kw,
            # 알고리즘 예측값 (제한 없는 원본 예측)
            "algorithm_prediction_kw": algorithm_prediction
            if "algorithm_prediction" in locals()
            else recommended_contract_kw,
            "prediction_exceeds_limit": prediction_exceeds_limit
            if "prediction_exceeds_limit" in locals()
            else False,
            "data_start_date": (
                data_start_date.isoformat()
                if hasattr(data_start_date, "isoformat")
                else str(data_start_date)
            ),
            "data_end_date": data_end_date.isoformat()
            if hasattr(data_end_date, "isoformat")
            else str(data_end_date),
            "record_count": power_stats.get("count", 0),
            # Dynamic pattern information
            "pattern_analysis": pattern_info if "pattern_info" in locals() else {"analysis_method": "fallback", "pattern_confidence": 0.3},
        }

        # 고급 모델 결과가 있으면 추가 정보 포함
        if ensemble_result:
            # SARIMA 데이터 확인 및 생성
            sarima_data = None
            method_comparison_data = None
            
            if hasattr(ensemble_result, 'sarima_result') and ensemble_result.sarima_result:
                sarima_result = ensemble_result.sarima_result
                sarima_data = {
                    "predicted_value": sarima_result.predicted_value if sarima_result.success else None,
                    "confidence": sarima_result.confidence_score if sarima_result.success else 0.0,
                    "success": sarima_result.success,
                    "error_message": sarima_result.error_message if not sarima_result.success else None,
                    "forecast_data": sarima_result.forecast_data if sarima_result.success else []
                }
                self.logger.info(f"Station {station_id}: SARIMA data prepared - success: {sarima_result.success}, forecast_data_count: {len(sarima_result.forecast_data) if sarima_result.success else 0}")
            else:
                self.logger.warning(f"Station {station_id}: No SARIMA result available")
            
            if hasattr(ensemble_result, 'method_comparison') and ensemble_result.method_comparison:
                method_comparison_data = ensemble_result.method_comparison
                self.logger.info(f"Station {station_id}: Method comparison data available")

            result.update(
                {
                    "advanced_model_prediction": {
                        "final_prediction": ensemble_result.final_prediction,  # 권고 계약 전력 (제한 적용됨)
                        "raw_prediction": ensemble_result.raw_prediction,  # 알고리즘 원본 예측값 (제한 없음)
                        "ensemble_method": ensemble_result.ensemble_method,
                        "model_count": len(ensemble_result.model_predictions),
                        "uncertainty": ensemble_result.uncertainty,
                        "model_weights": ensemble_result.weights,
                        "visualization_data": ensemble_result.visualization_data,
                        "models": [
                            {
                                "name": pred.model_name,
                                "prediction": round(pred.predicted_value, 1),
                                "confidence": round(pred.confidence_score, 2),
                                "method": pred.method_details.get(
                                    "description", pred.model_name
                                ),
                            }
                            for pred in ensemble_result.model_predictions
                        ],
                    },
                    # Method comparison for visualization
                    "method_comparison": method_comparison_data,
                    # SARIMA prediction results
                    "sarima_prediction": sarima_data,
                    "charger_type": charger_type,  # 충전기 타입 정보 추가
                    "charger_max_power": max_contract_advanced
                    if "max_contract_advanced" in locals()
                    else 100,
                }
            )

        return self._clean_for_json(result)

    def _generate_monthly_chart_data(
        self, patterns: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        power_stats = patterns["power_statistics"]
        monthly_patterns = patterns.get("monthly_patterns", {})
        date_range = patterns.get("date_range", {})
        
        chart_data = []
        base_power = power_stats.get("percentile_95", 50.0)
        
        # 실제 데이터의 시작/끝 날짜 확인
        start_date = date_range.get("start")
        end_date = date_range.get("end")
        
        if isinstance(start_date, str):
            try:
                start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except:
                start_date = datetime.now() - timedelta(days=365)
        elif not start_date:
            start_date = datetime.now() - timedelta(days=365)
            
        if isinstance(end_date, str):
            try:
                end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except:
                end_date = datetime.now()
        elif not end_date:
            end_date = datetime.now()
        
        # 실제 데이터의 첫 번째/마지막 월 확인
        first_actual_month = start_date.replace(day=1)
        last_actual_month = end_date.replace(day=1)
        
        self.logger.info(f"Real data range: {start_date} to {end_date}")
        self.logger.info(f"Chart months: {first_actual_month} to {last_actual_month}")
        
        # 실제 데이터 시작월부터 미래 6개월까지 차트 데이터 생성
        current_date = first_actual_month
        future_months = 6
        
        # 미래 데이터 포함하여 전체 범위 계산
        end_chart_date = last_actual_month
        for _ in range(future_months):
            if end_chart_date.month == 12:
                end_chart_date = end_chart_date.replace(year=end_chart_date.year + 1, month=1)
            else:
                end_chart_date = end_chart_date.replace(month=end_chart_date.month + 1)
        
        while current_date <= end_chart_date:
            target_date = current_date
            target_year = target_date.year
            target_month = target_date.month
            month_key = f"{target_year}-{target_month:02d}"
            month_label = f"{str(target_year)[-2:]}.{target_month:02d}"
            
            # 실제 데이터 범위 기준으로 실제/예측 구분 (현재 날짜가 아닌 데이터 끝 날짜 기준)
            is_actual_data_available = target_date <= last_actual_month
            
            if is_actual_data_available and month_key in monthly_patterns:
                # 실제 데이터가 있는 월
                actual_power = monthly_patterns[month_key].get("avg_power", 0)
                predicted_power = None
                self.logger.info(f"Month {month_label}: Using actual data = {actual_power}")
            elif is_actual_data_available:
                # 데이터 범위 내이지만 해당 월 데이터가 없는 경우 (예: 부분적 데이터)
                actual_power = None
                predicted_power = None
                self.logger.info(f"Month {month_label}: No data available in actual range")
            else:
                # 실제 데이터 범위를 벗어난 미래 월 - 예측 데이터
                actual_power = None
                # 실제 데이터 이후의 월 수 계산
                months_after_data = (target_date.year - last_actual_month.year) * 12 + (target_date.month - last_actual_month.month)
                # 점진적 성장과 계절성 반영
                growth_factor = 1.0 + months_after_data * 0.005  # 월 0.5% 성장
                seasonal_factor = 1.0 + (target_month % 12) * 0.01  # 계절성
                predicted_power = base_power * growth_factor * seasonal_factor
                self.logger.info(f"Month {month_label}: Using predicted data = {predicted_power} (months after: {months_after_data})")
            
            chart_data.append({
                "month": month_key,
                "label": month_label,
                "actual": actual_power,
                "predicted": predicted_power,
            })
            
            # 다음 달로 이동
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        self.logger.info(f"Generated {len(chart_data)} months of chart data from {first_actual_month} to {end_chart_date}")
        
        return chart_data

    def _generate_fallback_chart_data(
        self, power_stats: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        base_power = min(power_stats.get("percentile_95", 45.0), 60.0)  # 현실적인 기준
        now = datetime.now()
        chart_data = []

        # 최근 6개월 데이터
        for i in range(6):
            target_month = now.month - 5 + i
            target_year = now.year

            while target_month < 1:
                target_month += 12
                target_year -= 1
            while target_month > 12:
                target_month -= 12
                target_year += 1

            month_date = datetime(target_year, target_month, 1)
            month_label = f"{str(month_date.year)[-2:]}.{month_date.month:02d}"

            # 현실적인 변동
            actual_power = base_power * (0.9 + (i % 3) * 0.1)

            chart_data.append(
                {
                    "month": f"{month_date.year}-{month_date.month:02d}",
                    "label": month_label,
                    "actual": actual_power,
                    "predicted": None,
                }
            )

        return chart_data

    def _get_peak_hour(self, patterns: Dict[str, Any]) -> str:
        hourly_patterns = patterns.get("hourly_patterns", {})
        if not hourly_patterns:
            return "14:00"  # 기본값

        # 가장 높은 평균 전력을 가진 시간대 찾기
        max_hour = "14"
        max_power = 0
        for hour, data in hourly_patterns.items():
            if data.get("avg_power", 0) > max_power:
                max_power = data.get("avg_power", 0)
                max_hour = hour

        return f"{max_hour}:00"

    def get_monthly_contract_recommendation(
        self,
        station_id: str,
        year: int = None,
        month: int = None,
        mode: str = "p95",
        round_kw: int = 1,
    ) -> Dict[str, Any]:
        # Default to current year/month if not provided
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        cache_key = f"contract_{station_id}_{year}_{month}_{mode}"
        cached_result = self._get_cache(cache_key)
        if cached_result:
            return cached_result

        try:
            loader = ChargingDataLoader(station_id)
            patterns = loader.analyze_charging_patterns()

            power_stats = patterns.get("power_statistics", {})

            if not power_stats:
                recommended_kw = 50.0
                safety_margin = 10
            else:
                # 95% 백분위수 + 안전 마진
                percentile_95 = power_stats.get("percentile_95", 45.0)
                peak_variation = power_stats.get("std", 5.0)

                # 안전 마진을 동적으로 계산 (변동성이 클수록 마진 증가)
                if peak_variation > 20:
                    safety_margin = 20
                elif peak_variation > 10:
                    safety_margin = 15
                else:
                    safety_margin = 10

                recommended_kw = percentile_95 * (1 + safety_margin / 100)

            # 충전기 타입별 제한 적용
            try:
                loader = ChargingDataLoader(station_id)
                station_df = loader.load_historical_sessions(days=30)
                is_fast_charger = self._is_fast_charger(station_df)
                
                # 예측값이 높으면 급속충전기로 재판별 (보정 로직)
                if not is_fast_charger and percentile_95 >= 20:
                    self.logger.info(f"Monthly recommendation: Reclassifying {station_id} as fast charger due to high predicted power: {percentile_95:.1f}kW")
                    is_fast_charger = True
                
                max_contract = 100 if is_fast_charger else 7
            except Exception:
                max_contract = 100
                is_fast_charger = True

            # 충전기 타입별 최소값 설정
            if is_fast_charger:
                min_kw = 50  # 급속충전기 최소 50kW
                round_unit = 5  # 5kW 단위
            else:
                min_kw = 3  # 완속충전기 최소 3kW
                round_unit = 1  # 1kW 단위

            # 실제 데이터 기반 최적 계약전력 계산 사용
            optimal_result = self._calculate_optimal_contract_power(
                station_df, percentile_95
            )

            # Apply round_kw parameter to contract recommendation
            final_kw = (
                round(optimal_result["contract_recommendation"] / round_kw) * round_kw
            )
            algorithm_prediction = optimal_result["raw_prediction"]
            prediction_exceeds_limit = optimal_result["is_capped"]
            final_kw = max(min_kw, min(max_contract, final_kw))

            # 로깅 추가
            self.logger.info(
                f"Monthly contract for {station_id}: charger_type={'fast' if is_fast_charger else 'slow'}, "
                f"percentile_95={percentile_95:.1f}kW, algorithm={algorithm_prediction:.1f}kW, "
                f"contract={final_kw:.1f}kW, max_limit={max_contract}kW, capped={prediction_exceeds_limit}"
            )

            result = {
                "success": True,
                "station_id": station_id,
                "station_name": self._get_station_name_by_id(station_id),
                "year": year,
                "month": month,
                "horizon_days": 30,  # Default 30-day horizon
                "mode": mode,
                "predicted_peak_kw": int(percentile_95 if power_stats else 45.0),
                "recommended_contract_kw": int(final_kw),
                "charger_type": "fast" if is_fast_charger else "slow",
                "actual_peak_power": float(percentile_95),
                "calculation_method": "percentile_95_dynamic_margin",
                "safety_margin_percent": safety_margin,
                "data_quality": "high"
                if power_stats.get("count", 0) > 100
                else "medium",
                "timestamp": datetime.now().isoformat(),
                # 알고리즘 예측값 추가
                "algorithm_prediction_kw": int(algorithm_prediction),
                "prediction_exceeds_limit": prediction_exceeds_limit,
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            self.logger.error(
                f"Error getting contract recommendation for {station_id}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": str(e), "station_id": station_id}

    def get_energy_demand_forecast(
        self, station_id: str, days: int = 90
    ) -> Dict[str, Any]:
        cache_key = f"energy_demand_{station_id}_{days}"
        cached_result = self._get_cache(cache_key)
        if cached_result:
            return cached_result

        try:
            from ..prediction.engine_factory import get_prediction_engine

            loader = ChargingDataLoader(station_id)
            df = loader.load_historical_sessions(days=days)

            if df.empty:
                return {
                    "success": False,
                    "message": "에너지 데이터가 없습니다.",
                    "station_id": station_id,
                }

            # PredictionEngine을 사용하여 에너지 예측 수행 (캐시된 인스턴스)
            prediction_engine = get_prediction_engine()
            result = prediction_engine.predict_energy_demand(df, station_id, days)
            
            # station_name 추가
            result["station_name"] = self._get_station_name_by_id(station_id)

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            self.logger.error(
                f"Error getting energy demand forecast for {station_id}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": str(e), "station_id": station_id}




    def clear_cache(self, station_id: str = None) -> Dict[str, Any]:
        if station_id:
            # 특정 충전소 캐시 클리어
            keys_to_remove = [
                key for key in self._cached_data.keys() if station_id in key
            ]
            for key in keys_to_remove:
                self._cached_data.pop(key, None)
                self._cache_timestamp.pop(key, None)
            return {
                "message": f"Cache cleared for station {station_id}",
                "cleared_keys": len(keys_to_remove),
            }
        else:
            # 전체 캐시 클리어
            cleared_keys = len(self._cached_data)
            self._cached_data.clear()
            self._cache_timestamp.clear()
            return {"message": "All cache cleared", "cleared_keys": cleared_keys}
