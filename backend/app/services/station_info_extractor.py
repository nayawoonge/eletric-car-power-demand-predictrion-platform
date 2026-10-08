import pandas as pd
from typing import Dict, Any, Optional
import logging


class StationInfoExtractor:
    """충전소 정보 추출을 담당하는 클래스"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def find_station_column(self, df: pd.DataFrame) -> Optional[str]:
        """충전소 ID 컬럼 찾기"""
        station_column_candidates = ["충전소ID", "stationId", "station_id", "충전소"]
        for col in station_column_candidates:
            if col in df.columns:
                return col
        return None

    def get_station_name(self, station_data: pd.DataFrame, station_id: str) -> str:
        """충전소 이름 추출"""
        try:
            name_columns = ["충전소명", "stationName", "station_name", "name", "이름"]
            
            for col in name_columns:
                if col in station_data.columns:
                    names = station_data[col].dropna().unique()
                    if len(names) > 0:
                        return str(names[0])
            
            # 컬럼이 없으면 ID로 대체
            return f"Station {station_id}"
            
        except Exception as e:
            self.logger.debug(f"충전소 이름 추출 실패: {e}")
            return f"Station {station_id}"

    def get_station_location(self, station_data: pd.DataFrame) -> str:
        """충전소 위치 정보 추출"""
        try:
            location_columns = ["주소", "location", "address", "위치", "설치위치"]
            
            for col in location_columns:
                if col in station_data.columns:
                    locations = station_data[col].dropna().unique()
                    if len(locations) > 0:
                        return str(locations[0])
            
            return "위치정보 없음"
            
        except Exception:
            return "위치정보 없음"

    def get_station_region(self, station_data: pd.DataFrame) -> str:
        """충전소 지역 정보 추출"""
        try:
            region_columns = ["지역", "region", "시도", "광역시도"]
            
            for col in region_columns:
                if col in station_data.columns:
                    regions = station_data[col].dropna().unique()
                    if len(regions) > 0:
                        return str(regions[0])
            
            # 주소에서 지역 정보 추출 시도
            address = self.get_station_location(station_data)
            if address and address != "위치정보 없음":
                # 첫 번째 공백 전까지를 지역으로 간주
                parts = address.split()
                if len(parts) > 0:
                    return parts[0]
            
            return "지역정보 없음"
            
        except Exception:
            return "지역정보 없음"

    def get_station_city(self, station_data: pd.DataFrame) -> str:
        """충전소 도시 정보 추출"""
        try:
            city_columns = ["시군구", "city", "도시", "구"]
            
            for col in city_columns:
                if col in station_data.columns:
                    cities = station_data[col].dropna().unique()
                    if len(cities) > 0:
                        return str(cities[0])
            
            # 주소에서 도시 정보 추출 시도
            address = self.get_station_location(station_data)
            if address and address != "위치정보 없음":
                parts = address.split()
                if len(parts) > 1:
                    return parts[1]
            
            return "도시정보 없음"
            
        except Exception:
            return "도시정보 없음"

    def get_charger_type(self, station_data: pd.DataFrame) -> str:
        """충전기 타입 추출"""
        try:
            type_columns = ["충전기타입", "charger_type", "타입", "type"]
            
            for col in type_columns:
                if col in station_data.columns:
                    types = station_data[col].dropna().unique()
                    if len(types) > 0:
                        charger_type = str(types[0])
                        # 타입 정규화
                        if any(keyword in charger_type.upper() for keyword in ["DC", "급속", "FAST"]):
                            return "급속충전기 (DC)"
                        elif any(keyword in charger_type.upper() for keyword in ["AC", "완속", "SLOW"]):
                            return "완속충전기 (AC)"
                        else:
                            return charger_type
            
            # 데이터 기반으로 타입 추정
            if "순간최고전력" in station_data.columns:
                power_data = station_data["순간최고전력"].dropna()
                if len(power_data) > 0:
                    max_power = power_data.max()
                    avg_power = power_data.mean()
                    
                    # 최대 전력이 20kW 이상이거나 평균이 15kW 이상이면 급속
                    if max_power >= 20 or avg_power >= 15:
                        return "급속충전기 (DC)"
                    else:
                        return "완속충전기 (AC)"
            
            return "미상"
            
        except Exception:
            return "미상"

    def get_connector_type(self, station_data: pd.DataFrame) -> str:
        """커넥터 타입 추출"""
        try:
            connector_columns = ["커넥터타입", "connector_type", "커넥터", "connector"]
            
            for col in connector_columns:
                if col in station_data.columns:
                    connectors = station_data[col].dropna().unique()
                    if len(connectors) > 0:
                        return str(connectors[0])
            
            # 충전기 타입 기반으로 추정
            charger_type = self.get_charger_type(station_data)
            if "급속" in charger_type or "DC" in charger_type:
                return "DC콤보"
            elif "완속" in charger_type or "AC" in charger_type:
                return "AC3상"
            else:
                return "미상"
                
        except Exception:
            return "미상"

    def extract_station_info(self, station_data: pd.DataFrame, station_id: str) -> Dict[str, Any]:
        """충전소 정보를 모두 추출하여 딕셔너리로 반환"""
        try:
            return {
                "station_id": station_id,
                "station_name": self.get_station_name(station_data, station_id),
                "location": self.get_station_location(station_data),
                "region": self.get_station_region(station_data),
                "city": self.get_station_city(station_data),
                "charger_type": self.get_charger_type(station_data),
                "connector_type": self.get_connector_type(station_data),
            }
        except Exception as e:
            self.logger.error(f"충전소 정보 추출 실패 {station_id}: {e}")
            return {
                "station_id": station_id,
                "station_name": f"Station {station_id}",
                "location": "정보없음",
                "region": "정보없음", 
                "city": "정보없음",
                "charger_type": "미상",
                "connector_type": "미상",
            }