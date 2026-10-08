from typing import Dict, List, Optional, Tuple
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from pathlib import Path
import threading

MARKER_CANDIDATES = [".active_csv", ".active_csv.csv"]


# ============================================================================
# Process-local in-memory cache for parsed historical sessions.
# Key: (target_csv_path, csv_mtime_ns, station_id, days)
# 같은 충전소를 짧은 시간 안에 여러 API에서 동시에 조회할 때 CSV 재파싱을 방지.
# CSV 파일이 갱신되면 mtime_ns 가 달라져 자동으로 캐시 미스 → 재파싱.
# ============================================================================
_LOADER_CACHE_MAX = 128
_loader_cache: Dict[Tuple, pd.DataFrame] = {}
_loader_cache_order: List[Tuple] = []
_loader_cache_lock = threading.Lock()


# ============================================================================
# Raw full-file parse cache.
# Key: (csv_path, csv_mtime_ns, max_rows)
# 충전소별 캐시(_loader_cache)와 달리 "파일 1개를 통째로 파싱한 결과"를 캐싱한다.
# 일괄 예측처럼 같은 47MB CSV를 충전소 수(수백 개)만큼 반복 호출할 때,
# 충전소별 캐시는 station_id 가 달라 매번 미스 → 전체 재파싱(약 2초)이 발생했다.
# 이 캐시는 station_id 와 무관하게 파일 단위로 잡혀 파싱을 단 1회로 줄인다.
# 파일이 갱신되면 mtime_ns 가 바뀌어 자동 미스 → 재파싱.
# ============================================================================
_RAW_FILE_CACHE_MAX = 2
_raw_file_cache: Dict[Tuple, pd.DataFrame] = {}
_raw_file_cache_order: List[Tuple] = []
_raw_file_cache_lock = threading.Lock()


def _raw_file_cache_get(key: Tuple) -> Optional[pd.DataFrame]:
    with _raw_file_cache_lock:
        df = _raw_file_cache.get(key)
        if df is not None:
            try:
                _raw_file_cache_order.remove(key)
            except ValueError:
                pass
            _raw_file_cache_order.append(key)
            return df.copy()  # 호출자가 변형해도 캐시 보호
        return None


def _raw_file_cache_put(key: Tuple, df: pd.DataFrame) -> None:
    with _raw_file_cache_lock:
        _raw_file_cache[key] = df.copy()
        if key not in _raw_file_cache_order:
            _raw_file_cache_order.append(key)
        while len(_raw_file_cache_order) > _RAW_FILE_CACHE_MAX:
            old_key = _raw_file_cache_order.pop(0)
            _raw_file_cache.pop(old_key, None)


def _loader_cache_get(key: Tuple) -> Optional[pd.DataFrame]:
    with _loader_cache_lock:
        df = _loader_cache.get(key)
        if df is not None:
            # LRU: 최근 사용을 끝으로 이동
            try:
                _loader_cache_order.remove(key)
            except ValueError:
                pass
            _loader_cache_order.append(key)
            return df.copy()  # 호출자가 변형해도 캐시 보호
        return None


def _loader_cache_put(key: Tuple, df: pd.DataFrame) -> None:
    with _loader_cache_lock:
        if key in _loader_cache:
            _loader_cache[key] = df.copy()
            return
        _loader_cache[key] = df.copy()
        _loader_cache_order.append(key)
        while len(_loader_cache_order) > _LOADER_CACHE_MAX:
            old_key = _loader_cache_order.pop(0)
            _loader_cache.pop(old_key, None)


def clear_loader_cache() -> None:
    """CSV 재업로드 직후 명시적으로 호출하면 in-memory 캐시를 모두 비운다."""
    with _loader_cache_lock:
        _loader_cache.clear()
        _loader_cache_order.clear()
    with _raw_file_cache_lock:
        _raw_file_cache.clear()
        _raw_file_cache_order.clear()


class ChargingDataLoader:
    def __init__(self, station_id: str, data_dir: str = None):
        self.station_id = station_id

        if data_dir:
            self.data_dir = Path(data_dir).resolve()
        else:
            repo_dir = (Path(__file__).resolve().parents[3] / "data" / "raw").resolve()  # <repo_root>/data/raw
            legacy_dir = (Path(__file__).resolve().parent / "raw").resolve()  # <backend/app/data>/raw
            repo_dir.mkdir(parents=True, exist_ok=True)

            # 레거시 폴더에만 CSV가 있고 repo_dir 비어있으면 레거시 사용
            try:
                has_repo_csv = any(repo_dir.glob("*.csv"))
                has_legacy_csv = legacy_dir.exists() and any(legacy_dir.glob("*.csv"))
                self.data_dir = legacy_dir if (has_legacy_csv and not has_repo_csv) else repo_dir
            except Exception:
                self.data_dir = repo_dir

        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _is_marker(self, p: Path) -> bool:
        return p.name in MARKER_CANDIDATES

    def get_active_csv_file(self) -> Optional[Path]:
        
        for marker_name in MARKER_CANDIDATES:
            marker = self.data_dir / marker_name
            if marker.exists():
                try:
                    # 다양한 인코딩으로 마커 파일 읽기 시도
                    for encoding in ["utf-8", "cp949", "euc-kr", "utf-8-sig"]:
                        try:
                            first_line = marker.read_text(encoding=encoding).splitlines()[0].strip()
                            if first_line:
                                p = (self.data_dir / Path(first_line).name).resolve()
                                if p.exists():
                                    return p
                            break  # 성공하면 다른 인코딩 시도하지 않음
                        except (UnicodeDecodeError, UnicodeError):
                            continue
                except Exception:
                    continue
        return None

    def get_latest_csv_file(self) -> Optional[Path]:
        
        files = self.find_csv_files()
        if not files:
            return None
        files_sorted = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)
        return files_sorted[0]

    def find_csv_files(self) -> List[Path]:
        
        csv_files = []
        patterns = [
            "충전이력*.csv",
            "charging_sessions*.csv",
            "sessions*.csv",
            "*sessions*.csv",
            "*.csv",
        ]
        for pattern in patterns:
            files = list(self.data_dir.glob(pattern))
            # 마커 제외
            files = [f for f in files if not self._is_marker(f)]
            csv_files.extend(files)
            if files:
                break

        csv_files = list(set(csv_files))
        try:
            csv_files = sorted(csv_files, key=lambda f: f.stat().st_mtime, reverse=True)
        except Exception:
            pass

        if not csv_files:
            print(f"CSV 파일을 찾을 수 없습니다. 검색 경로: {self.data_dir}")

        return csv_files

    def load_csv_file(self, csv_file: Path = None, encoding: str = "utf-8", max_rows: int = None) -> pd.DataFrame:
        
        if csv_file is None:
            # 활성 파일 > 최신 파일 순서로 선택 (항상 data/raw 내부)
            csv_file = self.get_active_csv_file() or self.get_latest_csv_file()
            if not csv_file:
                print("로드할 CSV 파일이 없습니다.")
                return pd.DataFrame()

        # data/raw 내부 강제
        csv_file = (self.data_dir / Path(csv_file).name).resolve()
        if not csv_file.exists():
            print(f"파일을 찾을 수 없습니다: {csv_file}")
            return pd.DataFrame()

        # 전체 파일 파싱 캐시 조회 (파일+mtime+max_rows 단위, station 무관)
        # 같은 CSV 를 충전소 수만큼 반복 파싱하던 비용을 1회로 줄인다.
        raw_key: Optional[Tuple] = None
        try:
            mtime_ns = csv_file.stat().st_mtime_ns
            raw_key = (str(csv_file), mtime_ns, max_rows)
            cached_raw = _raw_file_cache_get(raw_key)
            if cached_raw is not None:
                return cached_raw
        except Exception:
            raw_key = None

        # 다양한 인코딩 시도
        encodings = [encoding, "utf-8", "euc-kr", "cp949", "utf-8-sig"]

        for enc in encodings:
            try:

                # 먼저 샘플로 테스트
                sample_df = pd.read_csv(csv_file, nrows=5, encoding=enc)

                df = pd.read_csv(csv_file, dtype=str, low_memory=True, encoding=enc, nrows=max_rows)

                if raw_key is not None:
                    _raw_file_cache_put(raw_key, df)

                return df

            except UnicodeDecodeError:
                continue
            except Exception as e:
                continue

        print("모든 인코딩 시도 실패")
        return pd.DataFrame()

    def load_historical_sessions(self, days: Optional[int] = 90, csv_file: str = None, merge_all: bool = False) -> pd.DataFrame:

        # 대상 CSV 파일 결정 (캐시 키 생성용)
        target_file: Optional[Path] = None
        if csv_file:
            target_file = (self.data_dir / Path(csv_file).name).resolve()
        elif not merge_all:
            target_file = self.get_active_csv_file() or self.get_latest_csv_file()

        # in-memory 캐시 조회 (merge_all 모드는 캐시 우회 — 다중 파일 결합은 빈번하지 않음)
        # 캐시 키에서 days 를 제외한다: load_historical_sessions 내부에서 날짜 필터링이
        # 비활성화되어 있어 days 값과 무관하게 결과가 동일하기 때문. days 를 포함시키면
        # 같은 station 에 대해 days=90, days=365 호출이 각각 별도 캐시로 잡혀 같은 station 을
        # 4~5번 재파싱하는 비효율이 발생한다.
        cache_key: Optional[Tuple] = None
        if target_file is not None and target_file.exists() and not merge_all:
            try:
                mtime_ns = target_file.stat().st_mtime_ns
                cache_key = (str(target_file), mtime_ns, self.station_id)
                cached_df = _loader_cache_get(cache_key)
                if cached_df is not None:
                    return cached_df
            except Exception:
                cache_key = None

        # CSV 파일 지정
        if csv_file:
            df = self.load_csv_file(target_file)
        else:
            csv_files = self.find_csv_files()
            if not csv_files:
                print("CSV 파일을 찾을 수 없습니다.")
                return pd.DataFrame()
            if merge_all:
                dfs = []
                for f in csv_files:
                    df_i = self.load_csv_file((self.data_dir / f.name).resolve())
                    if not df_i.empty:
                        dfs.append(df_i)
                if not dfs:
                    print("읽을 수 있는 CSV가 없습니다.")
                    return pd.DataFrame()
                df = pd.concat(dfs, ignore_index=True)
            else:
                if target_file is None:
                    print("읽을 수 있는 CSV가 없습니다.")
                    return pd.DataFrame()
                df = self.load_csv_file(target_file)

        try:
            # CSV 파일 로드
            if df.empty:
                print("CSV 파일이 비어있습니다.")
                return pd.DataFrame()

            # 데이터 처리 파이프라인
            # 충전소 필터링을 타입 변환/정제보다 먼저 수행한다.
            # 변환·정제는 행 간 의존성이 없어(행별 변환 + 행 선택) 순서를 바꿔도 결과가 동일하며,
            # 전체 12만여 행이 아니라 해당 충전소의 수천 행에만 datetime/numeric 변환을 적용해
            # 일괄 예측 시 충전소당 비용을 크게 줄인다. (convert→clean 순서는 유지: clean이 숫자형 전력 컬럼에 의존)
            df = self._normalize_column_names(df)

            # 특정 충전소 필터링 (변환 전 문자열 비교 — 비용 저렴)
            if self.station_id != "ALL":
                df = self._filter_by_station(df)

            df = self._convert_data_types(df)
            df = self._clean_data(df)

            # 날짜 필터링 비활성화: 전체 데이터 유지
            print(f"데이터 로드 완료: {len(df):,}개 세션")

            # 캐시에 저장 (가능한 경우)
            if cache_key is not None:
                try:
                    _loader_cache_put(cache_key, df)
                except Exception:
                    pass

            return df

        except Exception as e:
            print(f"CSV 로딩 중 오류 발생: {e}")
            return pd.DataFrame()

    def _filter_by_station(self, df: pd.DataFrame) -> pd.DataFrame:
        
        station_columns = ["충전소ID", "충전소명", "station_id", "station_name"]
        station_col = None

        for col in station_columns:
            if col in df.columns:
                station_col = col
                break

        if station_col:
            original_count = len(df)
            # 디버깅: 실제 데이터에서 고유값 확인 (필터링 전)
            unique_stations = df[station_col].unique()
            print(f"전체 충전소 수: {len(unique_stations)}")
            
            # 실제 필터링 수행
            df_filtered = df[df[station_col] == self.station_id]
            filtered_count = len(df_filtered)
            print(f"충전소 '{self.station_id}' 필터링: {original_count:,} → {filtered_count:,}개 세션")

            if filtered_count == 0:
                print(f"경고: 충전소 '{self.station_id}'에 대한 데이터가 없습니다.")
                # 유사한 충전소 ID가 있는지 확인
                similar_stations = [sid for sid in unique_stations if self.station_id.lower() in sid.lower() or sid.lower() in self.station_id.lower()]
                if similar_stations:
                    print(f"유사한 충전소 ID 발견: {similar_stations}")
                
                # 공백이나 특수문자 문제 확인
                station_id_variants = df[station_col].str.strip().unique()
                if self.station_id.strip() in station_id_variants:
                    print(f"공백 문제 감지: 원본='{self.station_id}', 공백제거 후 재시도")
                    df_filtered = df[df[station_col].str.strip() == self.station_id.strip()]
                    print(f"공백 제거 후 결과: {len(df_filtered)}개 세션")
            
            return df_filtered
        else:
            print("경고: 충전소 ID 컬럼을 찾을 수 없습니다.")
            print(f"사용 가능한 컬럼: {list(df.columns)}")
            return df


    def list_available_files(self) -> Dict:
        
        csv_files = self.find_csv_files()

        active = self.get_active_csv_file() or (csv_files[0] if csv_files else None)
        file_info = []
        for file in csv_files:
            try:
                # 파일 기본 정보
                stat = file.stat()
                info = {
                    "filename": file.name,
                    "path": str(file.absolute()),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }

                # CSV 구조 정보 (처음 5행만 읽어서)
                try:
                    sample_df = pd.read_csv(file, nrows=5)
                    info["columns"] = len(sample_df.columns)
                    info["sample_columns"] = list(sample_df.columns)[:10]  # 처음 10개 컬럼만
                except Exception:
                    info["columns"] = "unknown"
                    info["sample_columns"] = []

                file_info.append(info)

            except Exception as e:
                file_info.append({"filename": file.name, "error": str(e)})

        return {
            "data_directory": str(self.data_dir.absolute()),
            "total_files": len(csv_files),
            "files": file_info,
            "active_file": ({"filename": active.name, "path": str(active.absolute())} if active else None),
        }

    # 기존 메서드들은 그대로 유지 (_normalize_column_names, _convert_data_types, etc.)
    def _normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        

        # 컬럼명 공백 제거 및 정리
        df.columns = df.columns.str.strip()


        return df

    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        

        # 날짜 컬럼 찾기 및 변환
        date_patterns = ["일시", "date", "time", "시간"]
        date_columns = [col for col in df.columns if any(pattern in col for pattern in date_patterns)]

        for col in date_columns:
            try:
                # 먼저 샘플 데이터를 확인하여 형식을 추론
                sample_data = df[col].dropna().head(10)
                if len(sample_data) > 0:
                    # 일반적인 한국 날짜 형식들을 시도
                    date_formats = [
                        "%Y-%m-%d %H:%M:%S",  # ISO format
                        "%Y-%m-%d %H:%M:%S.%f",  # ISO with microseconds
                        "%Y/%m/%d %H:%M:%S",  # Slash separated
                        "%d/%m/%Y %H:%M:%S",  # Day first
                        "mixed",  # Let pandas infer but with proper handling
                    ]

                    parsed_successfully = False
                    for fmt in date_formats:
                        try:
                            if fmt == "mixed":
                                # Use pandas default inference for mixed formats
                                df[col] = pd.to_datetime(df[col], errors="coerce")
                            else:
                                df[col] = pd.to_datetime(df[col], format=fmt, errors="coerce")

                            # Check if parsing was successful
                            if df[col].notna().sum() > 0:
                                parsed_successfully = True
                                break
                        except Exception:
                            continue

                    if not parsed_successfully:
                        # Fallback to pandas default
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                else:
                    df[col] = pd.to_datetime(df[col], errors="coerce")

                valid_dates = df[col].notna().sum()
            except Exception as e:
                print(f"  {col} 날짜 변환 실패: {e}")

        # 숫자 컬럼 찾기 및 변환 (전력 관련 컬럼 우선 처리)
        numeric_patterns = ["전력", "전압", "전류", "kWh", "SOC", "시간", "금액", "량"]
        numeric_columns = [col for col in df.columns if any(pattern in col for pattern in numeric_patterns)]

        for col in numeric_columns:
            try:
                # 문자열에서 숫자가 아닌 문자 제거 (쉼표, 공백 등)
                df[col] = df[col].astype(str).str.replace(",", "", regex=False)
                df[col] = df[col].str.replace(" ", "", regex=False)  # 공백 제거
                df[col] = pd.to_numeric(df[col], errors="coerce")
                valid_numbers = df[col].notna().sum()
                        
            except Exception as e:
                print(f"  {col} 숫자 변환 실패: {e}")

        return df

    def _filter_by_days(self, df: pd.DataFrame, days: int) -> pd.DataFrame:
        
        date_columns = [col for col in df.columns if "시작일시" in col or "start" in col.lower()]

        if not date_columns:
            print("날짜 필터링 불가: 적절한 날짜 컬럼을 찾을 수 없음")
            return df

        date_col = date_columns[0]

        if df[date_col].isna().all():
            print(f"날짜 필터링 불가: {date_col} 컬럼의 모든 값이 null")
            return df

        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            original_count = len(df)
            df = df[df[date_col] >= cutoff_date]
            return df
        except Exception as e:
            print(f"날짜 필터링 중 오류: {e}")
            return df

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        
        original_size = len(df)

        # 전력 컬럼 찾기
        power_columns = [col for col in df.columns if "전력" in col]
        if power_columns:
            power_col = power_columns[0]
            before = len(df)
            df = df[(df[power_col] > 0) & (df[power_col] < 1000)]
            removed = before - len(df)

        retention_rate = (len(df) / original_size * 100) if original_size > 0 else 0
        return df

    # 기존 다른 메서드들도 그대로 유지...
    def load_realtime_status(self) -> Dict:
        return {
            "station_id": self.station_id,
            "active_chargers": 2,
            "total_chargers": 4,
            "current_power_usage": 85.3,
            "charger_status": {
                "CHG_01": {"status": "charging", "power": 42.1},
                "CHG_02": {"status": "charging", "power": 43.2},
                "CHG_03": {"status": "idle", "power": 0.0},
                "CHG_04": {"status": "maintenance", "power": 0.0},
            },
            "timestamp": datetime.now().isoformat(),
        }

    def load_external_factors(self) -> Dict:
        
        current_date = datetime.now()

        holidays = [
            "2025-01-01",
            "2025-03-01",
            "2025-05-05",
            "2025-06-06",
            "2025-08-15",
            "2025-10-03",
            "2025-12-25",
        ]
        is_holiday = current_date.strftime("%Y-%m-%d") in holidays

        return {
            "date": current_date.date().isoformat(),
            "is_holiday": is_holiday,
            "is_weekend": current_date.weekday() >= 5,
            "season": self._get_season(current_date.month),
            "weather": {
                "temperature": np.random.uniform(-5, 35),
                "condition": np.random.choice(["맑음", "흐림", "비", "눈"]),
            },
        }

    def _get_season(self, month: int) -> str:
        
        if month in [3, 4, 5]:
            return "봄"
        elif month in [6, 7, 8]:
            return "여름"
        elif month in [9, 10, 11]:
            return "가을"
        else:
            return "겨울"

    def get_data_summary(self) -> Dict:
        
        try:
            df = self.load_historical_sessions()

            if df.empty:
                return {"error": "데이터가 없습니다"}

            summary = {
                "total_sessions": len(df),
                "columns": list(df.columns),
                "date_range": {},
                "power_stats": {},
                "unique_stations": None,
                "unique_chargers": None,
                "data_source": "CSV file" if len(df) > 100 else "Sample data",
            }

            # 날짜 범위 (날짜 컬럼 자동 탐지)
            date_columns = [col for col in df.columns if pd.api.types.is_datetime64_any_dtype(df[col])]
            if date_columns:
                date_col = date_columns[0]
                summary["date_range"] = {
                    "start": df[date_col].min().isoformat() if pd.notna(df[date_col].min()) else None,
                    "end": df[date_col].max().isoformat() if pd.notna(df[date_col].max()) else None,
                }

            # 전력 통계 (전력 컬럼 자동 탐지)
            power_columns = [col for col in df.columns if "전력" in col]
            if power_columns:
                power_col = power_columns[0]
                power_data = df[power_col].dropna()
                if not power_data.empty:
                    summary["power_stats"] = {
                        "mean": round(power_data.mean(), 2),
                        "max": round(power_data.max(), 2),
                        "min": round(power_data.min(), 2),
                        "std": round(power_data.std(), 2),
                        "count": len(power_data),
                    }

            # 고유값 개수 (ID 컬럼 자동 탐지)
            id_columns = [col for col in df.columns if "ID" in col or "id" in col]
            for col in id_columns:
                if "충전소" in col:
                    summary["unique_stations"] = df[col].nunique()
                elif "충전기" in col:
                    summary["unique_chargers"] = df[col].nunique()

            return summary

        except Exception as e:
            return {"error": f"데이터 요약 생성 실패: {str(e)}"}

    def analyze_charging_patterns(self) -> Dict:
        
        try:
            # 차트와 패턴 분석을 위해 전체 데이터를 로드 (1년치)
            df = self.load_historical_sessions(365)
            if df.empty:
                return {"error": "분석할 데이터가 없습니다"}
            analysis = {
                "data_info": {
                    "total_sessions": len(df),
                    "columns": list(df.columns),
                    "station_id": self.station_id,
                }
            }

            # 전력 통계 (전력 컬럼 자동 탐지)
            power_columns = [col for col in df.columns if "전력" in col]
            if power_columns:
                power_col = power_columns[0]
                power_data = df[power_col].dropna()
                if not power_data.empty:
                    power_stats = power_data.describe()
                    analysis["power_statistics"] = {
                        "column_name": power_col,
                        "count": int(power_stats["count"]),
                        "mean": round(power_stats["mean"], 2),
                        "std": round(power_stats["std"], 2),
                        "min": round(power_stats["min"], 2),
                        "max": round(power_stats["max"], 2),
                        "percentile_50": round(power_stats["50%"], 2),
                        "percentile_75": round(power_stats["75%"], 2),
                        "percentile_90": round(power_data.quantile(0.90), 2),
                        "percentile_95": round(power_data.quantile(0.95), 2),
                        "percentile_99": round(power_data.quantile(0.99), 2),
                    }

            # 시간대별 패턴 (날짜 컬럼 자동 탐지)
            date_columns = [col for col in df.columns if pd.api.types.is_datetime64_any_dtype(df[col])]
            if date_columns and power_columns:
                date_col = date_columns[0]
                power_col = power_columns[0]

                try:
                    df["hour"] = df[date_col].dt.hour
                    hourly_stats = df.groupby("hour")[power_col].agg(["mean", "max", "count"]).round(2)

                    if not hourly_stats.empty:
                        analysis["hourly_patterns"] = {
                            int(hour): {
                                "avg_power": float(row["mean"]) if pd.notna(row["mean"]) else 0,
                                "max_power": float(row["max"]) if pd.notna(row["max"]) else 0,
                                "session_count": int(row["count"]),
                            }
                            for hour, row in hourly_stats.iterrows()
                        }

                        # 피크 시간대
                        peak_hour_idx = hourly_stats["mean"].idxmax()
                        peak_hour_data = hourly_stats.loc[peak_hour_idx]
                        analysis["peak_hour"] = {
                            "hour": int(peak_hour_idx),
                            "avg_power": float(peak_hour_data["mean"]),
                            "max_power": float(peak_hour_data["max"]),
                        }
                except Exception as e:
                    print(f"시간대별 패턴 분석 오류: {e}")

            # 월별 패턴 생성 (차트 데이터용)
            if date_columns and power_columns:
                try:
                    date_col = date_columns[0]
                    power_col = power_columns[0]
                    
                    # 년-월 조합으로 그룹핑 (정확한 시계열 데이터)
                    df["year_month"] = df[date_col].dt.strftime("%Y-%m")
                    monthly_stats = df.groupby("year_month")[power_col].agg(["mean", "max", "count"]).round(2)
                    
                    if not monthly_stats.empty:
                        analysis["monthly_patterns"] = {
                            year_month: {
                                "avg_power": float(row["mean"]) if pd.notna(row["mean"]) else 0,
                                "max_power": float(row["max"]) if pd.notna(row["max"]) else 0,
                                "session_count": int(row["count"]),
                            }
                            for year_month, row in monthly_stats.iterrows()
                        }
                        
                    # 날짜 범위 정보 추가
                    analysis["date_range"] = {
                        "start": df[date_col].min(),
                        "end": df[date_col].max()
                    }
                    
                except Exception as e:
                    print(f"월별 패턴 분석 오류: {e}")

            return analysis
        except Exception as e:
            return {"error": f"패턴 분석 실패: {str(e)}"}


def test_enhanced_loader():
    # 1. 사용 가능한 파일 목록
    loader = ChargingDataLoader("BNS0791")
    print("1. 사용 가능한 CSV 파일:")
    file_info = loader.list_available_files()
    print(f"   데이터 디렉토리: {file_info['data_directory']}")
    print(f"   총 {file_info['total_files']}개 파일 발견")

    for file in file_info["files"]:
        if "error" not in file:
            print(f"   - {file['filename']} ({file['size_mb']}MB, {file['columns']}개 컬럼)")

    # 2. 데이터 로드 및 요약
    print("\n2. 데이터 로드 및 요약:")
    summary = loader.get_data_summary()
    print(f"   총 세션: {summary.get('total_sessions', 0):,}개")
    print(f"   데이터 소스: {summary.get('data_source', 'unknown')}")

    if "power_stats" in summary and summary["power_stats"]:
        stats = summary["power_stats"]
        print(f"   전력 통계: 평균 {stats['mean']}kW, 최대 {stats['max']}kW")

    # 3. 패턴 분석
    print("\n3. 충전 패턴 분석:")
    patterns = loader.analyze_charging_patterns()
    if "power_statistics" in patterns:
        stats = patterns["power_statistics"]
        print(f"   전력 분석 ({stats['column_name']}): 평균 {stats['mean']}kW, 95% {stats['percentile_95']}kW")

    if "peak_hour" in patterns:
        peak = patterns["peak_hour"]
        print(f"   피크 시간: {peak['hour']}시 (평균 {peak['avg_power']}kW)")


if __name__ == "__main__":
    test_enhanced_loader()
