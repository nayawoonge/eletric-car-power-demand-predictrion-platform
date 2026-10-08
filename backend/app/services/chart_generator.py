"""
차트 데이터 생성 모듈
station_service.py에서 분리된 차트 관련 로직
"""
import pandas as pd
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging


class ChartDataGenerator:
    """차트 데이터 생성"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_monthly_chart_data(
        self,
        patterns: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        월별 차트 데이터 생성
        실제 데이터 + 예측 데이터 (미래 6개월)
        """
        try:
            power_stats = patterns["power_statistics"]
            monthly_patterns = patterns.get("monthly_patterns", {})
            date_range = patterns.get("date_range", {})

            chart_data = []
            base_power = power_stats.get("percentile_95", 50.0)

            # 날짜 범위 파싱
            start_date = self._parse_date(date_range.get("start"), default_days_ago=365)
            end_date = self._parse_date(date_range.get("end"), default_days_ago=0)

            first_actual_month = start_date.replace(day=1)
            last_actual_month = end_date.replace(day=1)

            self.logger.info(f"실제 데이터 범위: {start_date} ~ {end_date}")
            self.logger.info(f"차트 월 범위: {first_actual_month} ~ {last_actual_month}")

            # 미래 6개월 추가
            future_months = 6
            end_chart_date = self._add_months(last_actual_month, future_months)

            # 차트 데이터 생성
            current_date = first_actual_month
            while current_date <= end_chart_date:
                month_key = f"{current_date.year}-{current_date.month:02d}"
                month_label = f"{str(current_date.year)[-2:]}.{current_date.month:02d}"

                is_actual = current_date <= last_actual_month

                if is_actual and month_key in monthly_patterns:
                    # 실제 데이터 있음
                    actual_power = monthly_patterns[month_key].get("avg_power", 0)
                    predicted_power = None
                    self.logger.debug(f"월 {month_label}: 실제 데이터 = {actual_power}")
                elif is_actual:
                    # 데이터 범위 내이지만 해당 월 데이터 없음
                    actual_power = None
                    predicted_power = None
                else:
                    # 미래 예측
                    actual_power = None
                    months_after = self._months_between(last_actual_month, current_date)
                    growth_factor = 1.0 + months_after * 0.005  # 월 0.5% 성장
                    seasonal_factor = 1.0 + (current_date.month % 12) * 0.01
                    predicted_power = base_power * growth_factor * seasonal_factor
                    self.logger.debug(f"월 {month_label}: 예측 데이터 = {predicted_power}")

                chart_data.append({
                    "month": month_key,
                    "label": month_label,
                    "actual": actual_power,
                    "predicted": predicted_power,
                })

                current_date = self._add_months(current_date, 1)

            self.logger.info(f"{len(chart_data)}개월 차트 데이터 생성 완료")
            return chart_data

        except Exception as e:
            self.logger.error(f"월별 차트 데이터 생성 중 오류: {e}", exc_info=True)
            return self._generate_fallback_chart_data(patterns.get("power_statistics", {}))

    def generate_fallback_chart_data(
        self,
        power_stats: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """폴백 차트 데이터 생성"""
        return self._generate_fallback_chart_data(power_stats)

    def _generate_fallback_chart_data(
        self,
        power_stats: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """기본 차트 데이터 생성 (데이터 부족 시)"""
        base_power = min(power_stats.get("percentile_95", 45.0), 60.0)
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

            chart_data.append({
                "month": f"{month_date.year}-{month_date.month:02d}",
                "label": month_label,
                "actual": actual_power,
                "predicted": None,
            })

        return chart_data

    def generate_timeseries_data(
        self,
        df: pd.DataFrame
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        시계열 데이터 생성
        Returns: (timeseries_data, monthly_peaks, data_info)
        """
        try:
            # 날짜와 전력 컬럼 찾기
            date_columns = [
                col for col in df.columns
                if any(keyword in col for keyword in ["일시", "date", "time", "시작"])
            ]
            power_columns = [
                col for col in df.columns
                if "전력" in col or "power" in col.lower()
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

            # 시계열 데이터
            timeseries_data = [
                {
                    "timestamp": row[date_col].isoformat(),
                    "power": round(float(row[power_col]), 2),
                }
                for _, row in df_clean.iterrows()
            ]

            # 월별 최대값
            df_clean["year_month"] = df_clean[date_col].dt.to_period("M")
            monthly_max = df_clean.groupby("year_month")[power_col].max().reset_index()

            monthly_peaks = [
                {
                    "month": f"{row['year_month'].year}-{row['year_month'].month:02d}",
                    "peak_power": round(float(row[power_col]), 2),
                    "label": f"{row['year_month'].year}.{row['year_month'].month:02d}",
                }
                for _, row in monthly_max.iterrows()
            ]

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

        except Exception as e:
            self.logger.error(f"시계열 데이터 생성 중 오류: {e}", exc_info=True)
            return [], [], {}

    def _parse_date(self, date_value: Any, default_days_ago: int = 0) -> datetime:
        """날짜 파싱"""
        if isinstance(date_value, str):
            try:
                return datetime.fromisoformat(date_value.replace("Z", "+00:00"))
            except:
                pass

        if isinstance(date_value, datetime):
            return date_value

        # 기본값
        return datetime.now() - timedelta(days=default_days_ago)

    def _add_months(self, date: datetime, months: int) -> datetime:
        """날짜에 월 추가"""
        month = date.month + months
        year = date.year

        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1

        return date.replace(year=year, month=month)

    def _months_between(self, start: datetime, end: datetime) -> int:
        """두 날짜 사이의 월 수"""
        return (end.year - start.year) * 12 + (end.month - start.month)
