"""
충전소 메트릭 계산 모듈
station_service.py에서 분리된 메트릭 계산 로직
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
import logging


class StationMetricsCalculator:
    """충전소 메트릭 계산"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def calculate_metrics(
        self,
        station_data: pd.DataFrame,
        station_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """충전소의 모든 메트릭 계산"""
        try:
            if station_data.empty:
                return self._get_empty_metrics()

            metrics = {
                "data_sessions": len(station_data),
                "capacity_efficiency": "N/A",
                "last_activity": None,
            }

            # 전력 통계
            power_metrics = self._calculate_power_metrics(station_data)
            metrics.update(power_metrics)

            # 용량 효율성 (충전기 타입 필요)
            if power_metrics and station_info and "charger_type" in station_info:
                efficiency = self._calculate_capacity_efficiency(
                    station_data, station_info["charger_type"]
                )
                metrics["capacity_efficiency"] = efficiency

            # 시간 정보
            time_metrics = self._calculate_time_metrics(station_data)
            metrics.update(time_metrics)

            return metrics

        except Exception as e:
            self.logger.error(f"메트릭 계산 중 오류: {e}", exc_info=True)
            return self._get_empty_metrics()

    def _calculate_power_metrics(self, station_data: pd.DataFrame) -> Dict[str, Any]:
        """전력 관련 메트릭 계산"""
        power_cols = ["순간최고전력", "max_power", "전력"]

        for col in power_cols:
            if col in station_data.columns:
                power_data = station_data[col].dropna()
                if not power_data.empty:
                    return {
                        "avg_power": round(power_data.mean(), 1),
                        "max_power": round(power_data.max(), 1),
                        "min_power": round(power_data.min(), 1),
                        "power_std": round(power_data.std(), 1),
                        "percentile_50": round(power_data.quantile(0.50), 1),
                        "percentile_75": round(power_data.quantile(0.75), 1),
                        "percentile_90": round(power_data.quantile(0.90), 1),
                        "percentile_95": round(power_data.quantile(0.95), 1),
                        "percentile_99": round(power_data.quantile(0.99), 1),
                    }

        return {}

    def _calculate_time_metrics(self, station_data: pd.DataFrame) -> Dict[str, Any]:
        """시간 관련 메트릭 계산"""
        date_cols = ["충전시작일시", "start_time", "시작시간"]

        for col in date_cols:
            if col in station_data.columns:
                dates = pd.to_datetime(station_data[col], errors="coerce").dropna()
                if not dates.empty:
                    return {
                        "last_activity": dates.max().strftime("%Y-%m-%d %H:%M"),
                        "first_activity": dates.min().strftime("%Y-%m-%d %H:%M"),
                        "active_days": (dates.max() - dates.min()).days + 1,
                    }

        return {}

    def _calculate_capacity_efficiency(
        self,
        station_data: pd.DataFrame,
        charger_type: str
    ) -> str:
        """
        충전기 용량 대비 효율성 계산
        완속충전기(AC): 7kW 기준
        급속충전기(DC): 100kW 기준
        """
        power_cols = ["순간최고전력", "max_power", "전력"]

        for col in power_cols:
            if col in station_data.columns:
                power_data = station_data[col].dropna()
                if not power_data.empty:
                    avg_power = power_data.mean()

                    # 충전기 타입별 정격 용량
                    rated_capacity = {
                        "완속충전기 (AC)": 7.0,
                        "급속충전기 (DC)": 100.0,
                        "미상": 50.0,
                    }

                    capacity = rated_capacity.get(charger_type, 50.0)
                    efficiency = min(100.0, (avg_power / capacity) * 100)

                    return f"{round(efficiency, 1)}%"

        return "N/A"

    def _get_empty_metrics(self) -> Dict[str, Any]:
        """빈 메트릭 반환"""
        return {
            "data_sessions": 0,
            "avg_power": 0.0,
            "max_power": 0.0,
            "min_power": 0.0,
            "power_std": 0.0,
            "capacity_efficiency": "N/A",
            "last_activity": None,
        }

    def calculate_advanced_metrics(
        self,
        station_data: pd.DataFrame,
        station_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        고급 메트릭 계산
        (station_analyzer.py에서 가져온 기능)
        """
        try:
            if station_data.empty:
                return {}

            power_col = "순간최고전력"
            if power_col not in station_data.columns:
                return {}

            power_data = station_data[power_col].dropna()
            if len(power_data) == 0:
                return {}

            metrics = {
                "record_count": len(station_data),
                "power_record_count": len(power_data),
            }

            # 에너지 통계
            energy_col = "충전전력량(kWh)"
            if energy_col in station_data.columns:
                energy_data = station_data[energy_col].dropna()
                if len(energy_data) > 0:
                    metrics.update({
                        "total_energy": float(energy_data.sum()),
                        "avg_energy": float(energy_data.mean()),
                        "max_energy": float(energy_data.max()),
                    })

            # 시간 기반 통계
            if "충전시작일시" in station_data.columns:
                time_metrics = self._calculate_advanced_time_metrics(station_data)
                metrics.update(time_metrics)

            # 효율성 계산
            if station_info:
                efficiency_metrics = self._calculate_efficiency_metrics(
                    station_data, station_info, metrics
                )
                metrics.update(efficiency_metrics)

            return metrics

        except Exception as e:
            self.logger.error(f"고급 메트릭 계산 중 오류: {e}", exc_info=True)
            return {}

    def _calculate_advanced_time_metrics(
        self,
        station_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """시간 기반 고급 메트릭"""
        try:
            time_col = "충전시작일시"
            time_data = pd.to_datetime(station_data[time_col], errors='coerce')
            valid_time_data = time_data.dropna()

            if len(valid_time_data) == 0:
                return {}

            # 시간대별 분석
            hours = valid_time_data.dt.hour
            hour_distribution = hours.value_counts().to_dict()
            peak_hour = hours.mode().iloc[0] if len(hours.mode()) > 0 else 12

            # 요일별 분석
            weekdays = valid_time_data.dt.dayofweek
            weekday_distribution = weekdays.value_counts().to_dict()
            peak_weekday = weekdays.mode().iloc[0] if len(weekdays.mode()) > 0 else 1

            # 월별 분석
            months = valid_time_data.dt.month
            monthly_distribution = months.value_counts().to_dict()

            return {
                "data_start_date": valid_time_data.min().isoformat() if pd.notna(valid_time_data.min()) else None,
                "data_end_date": valid_time_data.max().isoformat() if pd.notna(valid_time_data.max()) else None,
                "peak_hour": int(peak_hour),
                "peak_weekday": int(peak_weekday),
                "hour_distribution": hour_distribution,
                "weekday_distribution": weekday_distribution,
                "monthly_distribution": monthly_distribution,
                "data_span_days": (valid_time_data.max() - valid_time_data.min()).days if len(valid_time_data) > 1 else 0,
            }

        except Exception as e:
            self.logger.error(f"시간 메트릭 계산 중 오류: {e}", exc_info=True)
            return {}

    def _calculate_efficiency_metrics(
        self,
        station_data: pd.DataFrame,
        station_info: Dict[str, Any],
        base_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """효율성 메트릭 계산"""
        try:
            efficiency_metrics = {}

            # 용량 대비 효율성
            if "max_power" in base_metrics and "capacity" in station_info:
                capacity = station_info.get("capacity", 100)
                if capacity > 0:
                    utilization_rate = min(100, (base_metrics["max_power"] / capacity) * 100)
                    efficiency_metrics["capacity_utilization"] = float(utilization_rate)
                    if "avg_power" in base_metrics:
                        efficiency_metrics["capacity_efficiency"] = float(
                            base_metrics["avg_power"] / capacity * 100
                        )

            # 활성 시간 비율
            if "record_count" in base_metrics and base_metrics["record_count"] > 0:
                total_possible_hours = 24 * 365
                if "data_span_days" in base_metrics and base_metrics["data_span_days"] > 0:
                    total_possible_hours = base_metrics["data_span_days"] * 24

                active_ratio = min(100, (base_metrics["record_count"] / total_possible_hours) * 100)
                efficiency_metrics["active_time_ratio"] = float(active_ratio)

            # 전력 품질 지표
            if "power_std" in base_metrics and "avg_power" in base_metrics:
                avg_power = base_metrics["avg_power"]
                if avg_power > 0:
                    cv = (base_metrics["power_std"] / avg_power) * 100
                    efficiency_metrics["power_stability"] = max(0, 100 - cv)

            return efficiency_metrics

        except Exception as e:
            self.logger.error(f"효율성 메트릭 계산 중 오류: {e}", exc_info=True)
            return {}
