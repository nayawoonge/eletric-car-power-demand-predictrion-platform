from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List
import pandas as pd


@dataclass
class ChargingSession:
    session_id: str
    station_id: str
    charger_id: str
    start_time: datetime
    end_time: datetime
    peak_power: float  # kW
    total_energy: float  # kWh
    start_soc: Optional[float] = None  # %
    end_soc: Optional[float] = None  # %
    duration_minutes: Optional[float] = None

    @classmethod
    def from_csv_row(cls, row: pd.Series) -> "ChargingSession":
        try:
            # Required fields with error handling
            session_id = str(
                row.get("세션ID", row.name if hasattr(row, "name") else "UNKNOWN")
            )

            if "충전소ID" not in row or pd.isna(row["충전소ID"]):
                raise ValueError("Missing required field: 충전소ID")
            station_id = str(row["충전소ID"])

            charger_id = str(row.get("충전기ID", "UNKNOWN"))

            # Date fields with validation
            start_time = row.get("충전시작일시")
            if pd.isna(start_time):
                raise ValueError("Missing required field: 충전시작일시")

            end_time = row.get("충전종료일시")
            if pd.isna(end_time):
                end_time = start_time  # Use start time as fallback

            # Power field with validation
            peak_power_val = row.get("순간최고전력")
            if pd.isna(peak_power_val):
                raise ValueError("Missing required field: 순간최고전력")

            try:
                peak_power = float(peak_power_val)
                if peak_power <= 0 or peak_power > 1000:  # Sanity check
                    raise ValueError(f"Invalid power value: {peak_power}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid power value '{peak_power_val}': {e}")

            # Optional numeric fields with safe conversion
            def safe_float_convert(value, default=0.0):
                try:
                    return float(value) if pd.notna(value) else default
                except (ValueError, TypeError):
                    return default

            def safe_int_convert(value, default=None):
                try:
                    return int(value) if pd.notna(value) else default
                except (ValueError, TypeError):
                    return default

            total_energy = safe_float_convert(row.get("충전량(kWh)"))
            start_soc = safe_int_convert(row.get("시작SOC(%)"))
            end_soc = safe_int_convert(row.get("완료SOC(%)"))
            duration_minutes = safe_float_convert(row.get("충전시간"))

            # Validate SOC ranges if provided
            if start_soc is not None and (start_soc < 0 or start_soc > 100):
                start_soc = None
            if end_soc is not None and (end_soc < 0 or end_soc > 100):
                end_soc = None

            return cls(
                session_id=session_id,
                station_id=station_id,
                charger_id=charger_id,
                start_time=start_time,
                end_time=end_time,
                peak_power=peak_power,
                total_energy=total_energy,
                start_soc=start_soc,
                end_soc=end_soc,
                duration_minutes=duration_minutes,
            )

        except Exception as e:
            # Provide more context for debugging
            row_info = (
                f"Row data: {dict(row.head(5))}"
                if hasattr(row, "head")
                else f"Row: {row}"
            )
            raise ValueError(
                f"Failed to create ChargingSession from CSV row: {e}. {row_info}"
            )


@dataclass
class ChargingStation:
    station_id: str
    name: str
    location: str
    charger_type: str
    connector_type: str
    region: str
    city: str
    operator: Optional[str] = None
    rated_power: Optional[float] = None  # kW
    num_chargers: Optional[int] = None
    status: str = "운영중"

    @classmethod
    def from_csv_data(cls, station_id: str, df: pd.DataFrame) -> "ChargingStation":
        try:
            if df.empty:
                raise ValueError(f"Empty DataFrame provided for station {station_id}")

            first_row = df.iloc[0]

            # Safe string conversion with fallbacks
            def safe_str_get(key, default):
                value = first_row.get(key)
                result = str(value) if pd.notna(value) else default
                if key == "충전소주소":
                    print(
                        f"DEBUG safe_str_get - Key: {key}, Value: '{value}', Result: '{result}'"
                    )
                return result

            name = safe_str_get("충전소명", f"충전소 {station_id}")
            location = safe_str_get("충전소주소", "위치 정보 없음")
            charger_type = safe_str_get("충전기 구분", "급속")
            connector_type = safe_str_get("커넥터명", "DC콤보")
            operator = safe_str_get("운영사명", None)

            # Debug: Print actual values
            print(f"DEBUG - Station {station_id}:")
            print(f"  충전소주소 value: '{first_row.get('충전소주소')}'")
            print(f"  Location result: '{location}'")

            # Extract region and city safely
            address = first_row.get("충전소주소", "")
            region = cls._extract_region(address)
            city = cls._extract_city(address)

            # Count unique chargers safely
            num_chargers = None
            if "충전기ID" in df.columns:
                try:
                    num_chargers = df["충전기ID"].nunique()
                except Exception:
                    num_chargers = None

            return cls(
                station_id=station_id,
                name=name,
                location=location,
                charger_type=charger_type,
                connector_type=connector_type,
                region=region,
                city=city,
                operator=operator,
                num_chargers=num_chargers,
            )

        except Exception as e:
            raise ValueError(
                f"Failed to create ChargingStation from CSV data for station {station_id}: {e}"
            )

    @staticmethod
    def _extract_region(address: str) -> str:
        try:
            if not address or pd.isna(address):
                return "미상"
            address_str = str(address).strip()
            if not address_str:
                return "미상"
            parts = address_str.split()
            return parts[0] if parts else "미상"
        except Exception:
            return "미상"

    @staticmethod
    def _extract_city(address: str) -> str:
        try:
            if not address or pd.isna(address):
                return "미상"
            address_str = str(address).strip()
            if not address_str:
                return "미상"
            parts = address_str.split()
            return parts[1] if len(parts) >= 2 else "미상"
        except Exception:
            return "미상"


@dataclass
class PredictionResult:
    station_id: str
    predicted_peak: float  # kW
    prediction_time: datetime
    target_time: datetime
    confidence: float  # 0-1
    confidence_interval: Optional[Dict[str, float]] = None
    method: str = "statistical"
    factors: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station_id": self.station_id,
            "predicted_peak": round(self.predicted_peak, 1),
            "confidence": self.confidence,
            "predicted_hour": self.target_time.isoformat(),
            "timestamp": self.prediction_time.isoformat(),
            "method": self.method,
            "confidence_interval": self.confidence_interval,
            "prediction_factors": self.factors,
        }


@dataclass
class ContractRecommendation:
    station_id: str
    year: int
    month: int
    predicted_peak: float  # kW
    recommended_contract: int  # kW (rounded)
    confidence_interval: Dict[str, float]
    seasonal_factor: float
    safety_margin: float
    method: str = "statistical"
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station_id": self.station_id,
            "year": self.year,
            "month": self.month,
            "predicted_peak_kw": round(self.predicted_peak, 1),
            "recommended_contract_kw": self.recommended_contract,
            "confidence_interval": {
                k: round(v, 1) for k, v in self.confidence_interval.items()
            },
            "seasonal_factor": self.seasonal_factor,
            "safety_margin": self.safety_margin,
            "method": self.method,
            "reasoning": self.reasoning,
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class AnalysisResult:
    station_id: str
    station_info: ChargingStation
    summary: Dict[str, Any]
    patterns: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    charts_data: Dict[str, Any]
    timestamp: datetime = datetime.now()
