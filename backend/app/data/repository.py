from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime, timedelta
import logging

from .loader import ChargingDataLoader
from ..models.entities import ChargingStation, ChargingSession


class ChargingDataRepository:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._station_cache: Optional[Dict[str, ChargingStation]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_expire_minutes = 30

    def get_historical_sessions(self, station_id: Optional[str] = None, days: int = 90) -> pd.DataFrame:
        try:
            # Use "ALL" for aggregated data if station_id is None
            loader_id = station_id if station_id is not None else "ALL"
            loader = ChargingDataLoader(loader_id)

            df = loader.load_historical_sessions(days=days)

            if df is None or df.empty:
                self.logger.warning(f"No historical data found for station {loader_id}")
                return pd.DataFrame()

            # Validate and clean the data
            try:
                clean_df = self.validator.clean_data(df)
                self.logger.info(f"Data validation completed for station {loader_id}")
            except Exception as validation_error:
                self.logger.warning(f"Data validation failed for station {loader_id}: {validation_error}")
                # Return original data if validation fails
                clean_df = df

            self.logger.info(f"Loaded {len(clean_df)} sessions for station {loader_id}")
            return clean_df

        except Exception as e:
            self.logger.error(f"Failed to load historical sessions for {station_id}: {e}")
            return pd.DataFrame()

    def get_station_info(self, station_id: str) -> Optional[ChargingStation]:
        
        try:
            stations = self._get_stations_cache()
            return stations.get(station_id)
        except Exception as e:
            self.logger.error(f"Failed to get station info for {station_id}: {e}")
            return None

    def get_available_stations(self) -> List[ChargingStation]:
        
        try:
            stations = self._get_stations_cache()
            return list(stations.values())
        except Exception as e:
            self.logger.error(f"Failed to get available stations: {e}")
            return []

    def station_exists(self, station_id: str) -> bool:
        
        try:
            stations = self._get_stations_cache()
            return station_id in stations
        except Exception as e:
            self.logger.error(f"Failed to check station existence for {station_id}: {e}")
            return False

    def get_data_summary(self, station_id: str) -> Dict[str, Any]:
        
        try:
            loader = ChargingDataLoader(station_id)
            summary = loader.get_data_summary()

            if not summary or "error" in summary:
                return {"error": f"No data available for station {station_id}"}

            return summary

        except Exception as e:
            self.logger.error(f"Failed to get data summary for {station_id}: {e}")
            return {"error": str(e)}

    def analyze_charging_patterns(self, station_id: str) -> Dict[str, Any]:
        
        try:
            loader = ChargingDataLoader(station_id)
            patterns = loader.analyze_charging_patterns()

            if not patterns or "error" in patterns:
                return {"error": f"No patterns data available for station {station_id}"}

            return patterns

        except Exception as e:
            self.logger.error(f"Failed to analyze patterns for {station_id}: {e}")
            return {"error": str(e)}

    def get_realtime_status(self, station_id: str) -> Dict[str, Any]:
        
        try:
            loader = ChargingDataLoader(station_id)
            status = loader.load_realtime_status()
            return status or {}
        except Exception as e:
            self.logger.error(f"Failed to get realtime status for {station_id}: {e}")
            return {"error": str(e)}

    def get_external_factors(self) -> Dict[str, Any]:
        
        try:
            # Use a dummy loader to get external factors
            loader = ChargingDataLoader("ALL")
            factors = loader.load_external_factors()
            return factors or {}
        except Exception as e:
            self.logger.error(f"Failed to get external factors: {e}")
            return {"error": str(e)}

    def get_data_quality_report(self, station_id: str) -> Dict[str, Any]:
        
        try:
            df = self.get_historical_sessions(station_id)

            if df.empty:
                return {"error": "No data available for quality analysis"}

            try:
                return self.validator.get_data_quality_report(df)
            except Exception as report_error:
                self.logger.warning(f"Failed to generate data quality report: {report_error}")
                return {"error": f"Quality report generation failed: {str(report_error)}"}

        except Exception as e:
            self.logger.error(f"Failed to get data quality report for {station_id}: {e}")
            return {"error": str(e)}

    def _get_stations_cache(self) -> Dict[str, ChargingStation]:
        
        current_time = datetime.now()

        # Temporarily disable cache for debugging location issue
        # if (self._station_cache is not None and
        #     self._cache_timestamp is not None and
        #     (current_time - self._cache_timestamp).total_seconds() < self._cache_expire_minutes * 60):
        #     return self._station_cache

        # Refresh cache
        self.logger.info("Refreshing station cache...")
        print("DEBUG: Starting to load stations from data...")
        self._station_cache = self._load_stations_from_data()
        print(f"DEBUG: Loaded {len(self._station_cache)} stations")
        self._cache_timestamp = current_time

        return self._station_cache

    def _load_stations_from_data(self) -> Dict[str, ChargingStation]:
        
        stations = {}

        try:
            # Load full dataset first to get complete station metadata (no date filtering)
            loader = ChargingDataLoader("ALL")
            # Load raw CSV data without any date filtering
            full_df = loader.load_csv_file()
            if not full_df.empty:
                # Apply data type conversion and cleaning but not date filtering
                full_df = loader._normalize_column_names(full_df)
                full_df = loader._convert_data_types(full_df)
                full_df = loader._clean_data(full_df)

            if full_df.empty or "충전소ID" not in full_df.columns:
                self.logger.warning("No station data available")
                return stations

            # Create a mapping of station metadata from full dataset
            station_metadata = {}
            for station_id, station_group in full_df.groupby("충전소ID"):
                # Get the first row which should contain all station metadata
                first_row = station_group.iloc[0]
                station_metadata[str(station_id)] = first_row

            # Now load filtered data for session counts and activity
            df = loader.load_historical_sessions(days=90)

            # Group by station and create ChargingStation objects using full metadata
            for station_id in station_metadata.keys():
                try:
                    # Use full metadata for station creation
                    metadata_row = station_metadata[station_id]
                    metadata_df = full_df[full_df["충전소ID"] == station_id].head(1)  # Just need one row with metadata

                    # Create station with full metadata
                    station = ChargingStation.from_csv_data(str(station_id), metadata_df)

                    # Update with current session counts from filtered data
                    if station_id in df["충전소ID"].values:
                        current_data = df[df["충전소ID"] == station_id]
                        station.data_sessions = len(current_data)
                        if not current_data.empty and "충전시작일시" in current_data.columns:
                            last_session = current_data["충전시작일시"].max()
                            station.last_activity = (
                                last_session.strftime("%Y-%m-%d") if pd.notna(last_session) else None
                            )
                    else:
                        station.data_sessions = 0
                        station.last_activity = None

                    stations[str(station_id)] = station
                except Exception as e:
                    self.logger.error(f"Failed to create station object for {station_id}: {e}")

            # Add aggregated "ALL" station
            if stations:
                # 실제 충전소들의 충전기 구분과 커넥터 타입 집계
                charger_types = []
                connector_types = []
                
                for station in stations.values():
                    if station.charger_type and station.charger_type not in charger_types:
                        charger_types.append(station.charger_type)
                    if station.connector_type and station.connector_type not in connector_types:
                        connector_types.append(station.connector_type)
                
                # 대표 충전기 타입 결정
                if len(charger_types) == 1:
                    primary_charger_type = charger_types[0]
                elif len(charger_types) > 1:
                    # 급속/완속 등이 섞여있는 경우
                    primary_charger_type = " + ".join(charger_types)
                else:
                    primary_charger_type = "충전기 정보 없음"
                
                # 대표 커넥터 타입 결정
                if len(connector_types) == 1:
                    primary_connector_type = connector_types[0]
                elif len(connector_types) > 1:
                    primary_connector_type = " + ".join(connector_types[:3])  # 최대 3개까지만 표시
                else:
                    primary_connector_type = "커넥터 정보 없음"
                
                stations["ALL"] = ChargingStation(
                    station_id="ALL",
                    name="전체 충전소 통합 분석",
                    location=f"전국 ({len(stations)}개 충전소)",
                    charger_type=primary_charger_type,
                    connector_type=primary_connector_type,
                    region="전국",
                    city="전체",
                    status="정상 운영",
                )

            self.logger.info(f"Loaded {len(stations)} stations from data")

        except Exception as e:
            self.logger.error(f"Failed to load stations from data: {e}")

        return stations

    def invalidate_cache(self) -> None:
        
        self._station_cache = None
        self._cache_timestamp = None
        self.logger.info("Station cache invalidated")

    def get_station_sessions(self, station_id: str, limit: Optional[int] = None) -> List[ChargingSession]:
        
        try:
            df = self.get_historical_sessions(station_id)

            if df.empty:
                return []

            # Apply limit if specified
            if limit:
                df = df.head(limit)

            sessions = []
            for _, row in df.iterrows():
                try:
                    session = ChargingSession.from_csv_row(row)
                    sessions.append(session)
                except Exception as e:
                    self.logger.warning(f"Failed to create session object: {e}")

            return sessions

        except Exception as e:
            self.logger.error(f"Failed to get station sessions for {station_id}: {e}")
            return []
