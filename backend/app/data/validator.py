# 데이터 검증 모듈
import pandas as pd
from typing import Dict, List, Any


class DataValidator:
    

    def validate_power_data(self, df: pd.DataFrame) -> Dict[str, bool]:
        
        validation_results = {
            "has_required_columns": self._check_required_columns(df),
            "power_ranges_valid": self._check_power_ranges(df),
            "timestamps_valid": self._check_timestamps(df),
        }
        return validation_results

    def _check_required_columns(self, df: pd.DataFrame) -> bool:
        
        required_cols = ["충전시작일시", "충전종료일시", "순간최고전력"]
        return all(col in df.columns for col in required_cols)

    def _check_power_ranges(self, df: pd.DataFrame) -> bool:
        
        if "순간최고전력" not in df.columns:
            return False

        power_data = df["순간최고전력"].dropna()

        if power_data.empty:
            return False

        # 물리적 한계 설정 (EV 충전기 기준)
        min_power = 0.1  # 0.1kW - 최소 충전 전력
        max_power = 350.0  # 350kW - 최고 급속충전기 한계

        # 범위 내 데이터 비율 계산
        valid_power_count = ((power_data >= min_power) & (power_data <= max_power)).sum()
        total_power_count = len(power_data)

        valid_ratio = valid_power_count / total_power_count if total_power_count > 0 else 0

        # 90% 이상의 데이터가 유효한 범위에 있으면 통과
        return valid_ratio >= 0.9

    def _check_timestamps(self, df: pd.DataFrame) -> bool:
        
        required_date_cols = ["충전시작일시", "충전종료일시"]

        # 필수 날짜 컬럼 존재 확인
        for col in required_date_cols:
            if col not in df.columns:
                return False

        # 날짜 형식 확인 및 변환
        try:
            start_times = pd.to_datetime(df["충전시작일시"], errors="coerce")
            end_times = pd.to_datetime(df["충전종료일시"], errors="coerce")
        except Exception:
            return False

        # null이 아닌 데이터에 대해서만 검증
        valid_mask = start_times.notna() & end_times.notna()

        if valid_mask.sum() == 0:  # 유효한 날짜 데이터가 없음
            return False

        # 시작시간 <= 종료시간 확인
        valid_time_order = (start_times <= end_times)[valid_mask]
        valid_ratio = valid_time_order.sum() / len(valid_time_order) if len(valid_time_order) > 0 else 0

        # 95% 이상의 데이터가 시간 순서를 만족하면 통과
        return valid_ratio >= 0.95


class ChargingDataValidator:
    

    def __init__(self):
        self.data_validator = DataValidator()

    def validate_charging_sessions(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        try:
            if df is None or df.empty:
                return {"success": False, "error": "데이터가 비어있습니다.", "validation_results": {}}

            validation_results = {}

            # 1. 기본 데이터 정보
            validation_results["basic_info"] = {
                "total_rows": len(df),
                "total_columns": len(df.columns),
                "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
            }

            # 2. 컬럼 검증
            validation_results["columns"] = self._validate_columns(df)

            # 3. 데이터 타입 검증
            validation_results["data_types"] = self._validate_data_types(df)

            # 4. 결측값 검증
            validation_results["missing_values"] = self._validate_missing_values(df)

            # 5. 충전소 ID 검증
            validation_results["station_ids"] = self._validate_station_ids(df)

            # 6. 전력 데이터 검증 (기존 DataValidator 활용)
            if self._has_power_columns(df):
                validation_results["power_data"] = self.data_validator.validate_power_data(df)

            # 7. 전체 검증 상태
            validation_results["overall_status"] = self._get_overall_status(validation_results)

            return {"success": True, "message": "데이터 검증 완료", "validation_results": validation_results}

        except Exception as e:
            return {"success": False, "error": f"검증 중 오류 발생: {str(e)}", "validation_results": {}}

    def _validate_columns(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        # 예상되는 충전 관련 컬럼들
        expected_columns = [
            "충전소ID",
            "충전소명",
            "station_id",
            "충전시작일시",
            "충전종료일시",
            "사용일시",
            "충전량",
            "충전시간",
            "순간최고전력",
        ]

        found_columns = [col for col in expected_columns if col in df.columns]
        missing_columns = [col for col in expected_columns if col not in df.columns]

        return {
            "total_columns": len(df.columns),
            "expected_columns": expected_columns,
            "found_columns": found_columns,
            "missing_columns": missing_columns,
            "sample_columns": list(df.columns)[:10],
        }

    def _validate_data_types(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        data_types = {}
        for col in df.columns:
            dtype = str(df[col].dtype)
            sample_values = df[col].dropna().head(3).tolist()
            data_types[col] = {"dtype": dtype, "sample_values": sample_values}

        return data_types

    def _validate_missing_values(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        missing_info = {}
        total_rows = len(df)

        for col in df.columns:
            missing_count = df[col].isnull().sum()
            missing_percentage = (missing_count / total_rows) * 100

            missing_info[col] = {
                "missing_count": int(missing_count),
                "missing_percentage": round(missing_percentage, 2),
            }

        return missing_info

    def _validate_station_ids(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        station_id_cols = ["충전소ID", "station_id", "충전소명"]
        station_col = None

        for col in station_id_cols:
            if col in df.columns:
                station_col = col
                break

        if not station_col:
            return {"station_column_found": False, "message": "충전소 ID 컬럼을 찾을 수 없습니다."}

        unique_stations = df[station_col].dropna().unique()

        return {
            "station_column_found": True,
            "station_column_name": station_col,
            "unique_stations_count": len(unique_stations),
            "sample_station_ids": list(unique_stations)[:10],
        }

    def _has_power_columns(self, df: pd.DataFrame) -> bool:
        
        power_columns = ["순간최고전력", "충전량", "전력"]
        return any(col in df.columns for col in power_columns)

    def _get_overall_status(self, validation_results: Dict) -> Dict[str, Any]:
        
        issues = []

        # 컬럼 이슈 확인
        if validation_results.get("columns", {}).get("found_columns", []):
            issues.append("일부 예상 컬럼이 누락되었습니다.")

        # 충전소 ID 이슈 확인
        if not validation_results.get("station_ids", {}).get("station_column_found", False):
            issues.append("충전소 ID 컬럼이 없습니다.")

        # 결측값 이슈 확인
        missing_values = validation_results.get("missing_values", {})
        high_missing_cols = [col for col, info in missing_values.items() if info.get("missing_percentage", 0) > 50]
        if high_missing_cols:
            issues.append(f"결측값이 많은 컬럼: {high_missing_cols}")

        return {"status": "warning" if issues else "success", "issues": issues, "is_valid": len(issues) == 0}


# 하위 호환성을 위한 별칭
ChargingSessionValidator = ChargingDataValidator
