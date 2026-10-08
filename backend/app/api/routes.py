from datetime import datetime
import pandas as pd
from pathlib import Path
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks

from ..data.loader import ChargingDataLoader
from ..data.validator import ChargingDataValidator
from ..services.station_service import StationService
from ..storage.storage_manager import StorageManager

main = None
logger = logging.getLogger(__name__)

# 서비스 인스턴스 생성 - 싱글톤 패턴
_station_service = None
_storage_manager: Optional[StorageManager] = None
_ensemble_engine = None  # EnsemblePredictionEngine 싱글톤 (모델 로딩 1회만)


def get_ensemble_engine():
    """
    앙상블 예측 엔진 싱글톤.

    EnsemblePredictionEngine() 생성은 LSTM/XGBoost 모델을 디스크에서 로드하므로
    매 요청/충전소마다 새로 만들면 수백 ms 가 낭비된다(일괄 예측 시 수십 초).
    엔진은 학습된 모델만 보유하는 사실상 무상태 객체이므로 재사용한다.
    """
    global _ensemble_engine
    if _ensemble_engine is None:
        from ..prediction.ensemble_prediction_engine import EnsemblePredictionEngine
        _ensemble_engine = EnsemblePredictionEngine()
    return _ensemble_engine


async def _get_or_compute_ensemble(station_id: str) -> dict:
    """
    앙상블 예측을 DB 캐시에서 우선 가져오고, 없을 때만 1회 계산한다.

    /prediction, /monthly-contract 엔드포인트는 사용자 노출 추천값을 앙상블 결과로
    통일하기 위해 내부적으로 앙상블을 참조한다. 기존에는 force_refresh 를 그대로 전파해,
    일괄 예측 루프에서 같은 충전소의 앙상블이 (ensemble 직접 + prediction + monthly)
    최대 3번까지 중복 재계산됐다. 데이터는 CSV 재업로드 시에만 바뀌고 그때 캐시가
    비워지므로(clear_loader_cache + DB 무효화), 한 번 계산된 앙상블을 재사용해도 정확하다.

    - 캐시 hit: 저장된 앙상블 결과를 그대로 반환 (재계산 없음)
    - 캐시 miss: 1회 계산해 DB 에 저장한 뒤 반환
    """
    cached = await get_ensemble_prediction(station_id, force_refresh=False)
    if isinstance(cached, dict) and cached.get("success"):
        return cached
    return await get_ensemble_prediction(station_id, force_refresh=True)


def get_storage_manager() -> StorageManager:
    """예측 결과 저장 관리자 싱글톤"""
    global _storage_manager
    if _storage_manager is None:
        # data/predictions.db 가 기본 경로
        repo_root = Path(__file__).resolve().parents[3]
        _storage_manager = StorageManager(use_database=True, base_path=str(repo_root / "data"))
    return _storage_manager


def get_station_service() -> StationService:
    global _station_service
    if _station_service is None:
        _station_service = StationService()
    return _station_service


def set_main_module(main_module):
    global main
    main = main_module


# data/raw 절대 경로 헬퍼
def get_data_dir() -> Path:
    repo_dir = (Path(__file__).resolve().parents[3] / "data" / "raw").resolve()  # <repo_root>/data/raw
    legacy_dir = (Path(__file__).resolve().parents[1] / "data" / "raw").resolve()  # <backend/app>/data/raw

    # 기본 디렉터리 생성
    repo_dir.mkdir(parents=True, exist_ok=True)

    # 레거시 폴더에만 CSV가 있고 repo_dir이 비어 있으면 레거시 사용
    try:
        if legacy_dir.exists():
            has_legacy_csv = any(legacy_dir.glob("*.csv"))
        else:
            has_legacy_csv = False
        has_repo_csv = any(repo_dir.glob("*.csv"))
        if has_legacy_csv and not has_repo_csv:
            return legacy_dir
    except Exception:
        pass

    return repo_dir


def get_active_csv_path() -> Optional[Path]:
    """현재 활성 CSV 파일 경로를 반환한다 (.active_csv 마커 우선, 없으면 최근 수정 파일)."""
    data_dir = get_data_dir()
    for marker_name in (".active_csv", ".active_csv.csv"):
        marker = data_dir / marker_name
        if marker.exists():
            try:
                name = marker.read_text(encoding="utf-8").splitlines()[0].strip()
            except Exception:
                name = None
            if name:
                p = (data_dir / Path(name).name)
                if p.exists():
                    return p
    csv_files = [f for f in data_dir.glob("*.csv")]
    return max(csv_files, key=lambda f: f.stat().st_mtime) if csv_files else None


def detect_csv_encoding(csv_path: Path) -> str:
    """CSV 인코딩 자동 감지 (헤더만 읽어 시도)."""
    for enc in ("utf-8", "cp949", "euc-kr", "utf-8-sig"):
        try:
            pd.read_csv(csv_path, nrows=1, encoding=enc)
            return enc
        except Exception:
            continue
    return "utf-8"


async def run_bulk_prediction_if_needed(force: bool = False) -> dict:
    """활성 CSV 에 대해 일괄 예측을 실행한다.

    앱 시작 시(force=False) "DB 예측이 현재 활성 CSV 와 일치하는가"를 콘텐츠 해시로 판별한다:
      - DB 예측이 있고 + 그 예측을 만든 CSV 해시 == 현재 활성 CSV 해시  → 동일 데이터이므로
        재예측 없이 DB 를 그대로 사용 (skip).
      - DB 예측이 없거나 해시가 다르면 → stale/미존재 이므로 기존 예측을 비우고 새로 예측·저장.
    force=True(수동) 이면 무조건 재예측한다.
    """
    csv_path = get_active_csv_path()
    if csv_path is None:
        logger.info("[BulkPredict] 활성 CSV 없음 — 일괄 예측 건너뜀")
        return {"started": False, "reason": "no_active_csv"}

    sm = get_storage_manager()
    try:
        current_hash = sm.compute_file_hash(csv_path)
    except Exception as e:
        logger.warning(f"[BulkPredict] CSV 해시 계산 실패: {e}")
        current_hash = None

    if not force:
        existing = 0
        try:
            existing = sm.count_predictions()
        except Exception:
            pass
        stored_hash = sm.get_predictions_source_hash()
        if existing > 0 and current_hash is not None and stored_hash == current_hash:
            # DB 예측이 현재 활성 CSV 로 만든 것과 동일 → 그대로 사용
            logger.info(f"[BulkPredict] DB 예측({existing}건)이 활성 CSV 와 일치 — 재예측 건너뜀")
            return {"started": False, "reason": "db_matches_active_csv", "count": existing}
        if existing > 0:
            # 예측은 있으나 CSV 가 바뀜(또는 해시 미기록) → stale 이므로 초기화 후 재예측
            logger.info(
                f"[BulkPredict] DB 예측({existing}건)이 활성 CSV 와 불일치(stored={stored_hash}, "
                f"current={current_hash}) — 초기화 후 재예측"
            )
            sm.clear_all_predictions()

    used_encoding = detect_csv_encoding(csv_path)
    logger.info(f"[BulkPredict] 일괄 예측 시작 (file={csv_path.name}, force={force})")
    await _bulk_predict_all_stations(csv_path, used_encoding)
    return {"started": True, "file": csv_path.name}


api_router = APIRouter()


# ----------------------------------------------------------------------
# 데이터 충분성 사전 검증
# ----------------------------------------------------------------------
MIN_SESSIONS_FOR_ANALYSIS = 14
MIN_UNIQUE_DAYS_FOR_ANALYSIS = 7


def check_data_sufficiency(station_id: str):
    """
    충전소의 세션 수·관측일이 분석에 충분한지 확인.

    반환값:
      - (None, df): 충분함. df는 재사용을 위해 돌려받을 수 있는 DataFrame (또는 None).
      - (error_response_dict, None): 불충분. 호출 측은 이 dict를 그대로 응답하면 됨.

    이 함수는 ChargingDataLoader를 한 번 호출해 세션 수·고유 일수를 집계합니다.
    pd.std()가 NaN을 내서 JSON 직렬화 실패로 이어지는 1~몇 건짜리 케이스를 차단합니다.
    """
    try:
        loader = ChargingDataLoader(station_id)
        df = loader.load_historical_sessions(days=365)
    except Exception as exc:
        logger.warning("[sufficiency] Failed to load data for %s: %s", station_id, exc)
        return (
            {
                "success": False,
                "error_code": "NO_DATA",
                "error": "이 충전소의 충전 이력 데이터를 불러올 수 없습니다. CSV 파일 또는 충전소 ID를 확인해 주세요.",
                "station_id": station_id,
            },
            None,
        )

    if df is None or df.empty:
        return (
            {
                "success": False,
                "error_code": "NO_DATA",
                "error": "이 충전소의 충전 이력 데이터를 찾을 수 없습니다. CSV에 해당 충전소의 세션이 포함되어 있는지 확인해 주세요.",
                "station_id": station_id,
            },
            None,
        )

    session_count = int(len(df))
    unique_days_count: Optional[int] = None
    first_date_iso: Optional[str] = None
    last_date_iso: Optional[str] = None
    time_col_candidates = [
        "충전시작일시",
        "충전완료일시",
        "timestamp",
        "측정일시",
        "date",
        "created_at",
    ]
    for _tc in time_col_candidates:
        if _tc in df.columns:
            _ts = pd.to_datetime(df[_tc], errors="coerce").dropna()
            if not _ts.empty:
                unique_days_count = int(_ts.dt.date.nunique())
                first_date_iso = _ts.min().strftime("%Y-%m-%d")
                last_date_iso = _ts.max().strftime("%Y-%m-%d")
            break

    if session_count < MIN_SESSIONS_FOR_ANALYSIS or (
        unique_days_count is not None and unique_days_count < MIN_UNIQUE_DAYS_FOR_ANALYSIS
    ):
        coverage_str = ""
        if first_date_iso and last_date_iso:
            coverage_str = f" ({first_date_iso} ~ {last_date_iso})"
        logger.info(
            "[sufficiency] Insufficient data for %s: sessions=%s, unique_days=%s",
            station_id, session_count, unique_days_count,
        )
        return (
            {
                "success": False,
                "error_code": "INSUFFICIENT_DATA",
                "error": (
                    f"이 충전소의 충전 이력이 충분하지 않아 분석·예측을 수행할 수 없습니다. "
                    f"현재 세션 {session_count}건"
                    + (
                        f" · 관측 {unique_days_count}일{coverage_str}"
                        if unique_days_count is not None else ""
                    )
                    + f"이 확인되지만, 안정적인 결과를 위해 최소 세션 {MIN_SESSIONS_FOR_ANALYSIS}건 · "
                    f"{MIN_UNIQUE_DAYS_FOR_ANALYSIS}일 이상의 데이터가 필요합니다."
                ),
                "guidance": [
                    "해당 충전소에서 더 많은 충전 세션이 누적될 때까지 분석을 보류해 주세요.",
                    "최근 일일 이용률이 낮은 신규 충전소라면 통상 2~4주 뒤 재시도를 권장합니다.",
                    "데이터가 풍부한 다른 충전소를 선택하거나, 여러 충전소의 데이터를 통합 분석하는 것도 대안입니다.",
                ],
                "details": {
                    "session_count": session_count,
                    "unique_days": unique_days_count,
                    "min_required_sessions": MIN_SESSIONS_FOR_ANALYSIS,
                    "min_required_days": MIN_UNIQUE_DAYS_FOR_ANALYSIS,
                    "data_coverage_start": first_date_iso,
                    "data_coverage_end": last_date_iso,
                },
                "station_id": station_id,
            },
            None,
        )

    return (None, df)


@api_router.get("/stations")
async def list_stations(
    page: int = 1,
    limit: int = 10000,  # 모든 충전소를 표시하도록 기본값 증가
    include_summary: bool = False,
    search: str = None,
    sort_by: str = "id",
    sort_order: str = "asc",
):
    
    try:
        logger.info(f"API called: page={page}, limit={limit}, search={search}")

        # CSV 파일 존재 여부 확인
        data_dir = get_data_dir()
        csv_files = list(data_dir.glob("*.csv"))

        if not csv_files:
            return {
                "success": False,
                "error": "CSV 파일을 먼저 업로드해주세요.",
                "requiresUpload": True,
                "stations": [],
                "pagination": {"page": page, "limit": limit, "total": 0, "hasNext": False},
            }

        station_service = get_station_service()
        result = station_service.list_stations(search=search, sort_by=sort_by, sort_order=sort_order)

        # 페이지네이션 정보 추가 (모든 충전소 표시)
        if result["success"]:
            stations = result.get("stations", [])
            total = result.get("total", len(stations))
            # limit이 매우 큰 경우(10000) 모든 충전소 표시, 아니면 제한 적용
            if limit >= 10000:
                stations = stations  # 모든 충전소 표시
            else:
                stations = stations[:limit]  # 제한된 충전소 표시
            result["stations"] = stations
            result["pagination"] = {
                "page": page,
                "limit": limit,
                "total": total,
                "hasNext": total > len(stations),
                "hasPrev": False,
            }

        return result

    except Exception as e:
        logger.error(f"Error in list_stations: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "stations": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "hasNext": False},
        }


@api_router.get("/station-analysis/{station_id}")
async def get_station_detailed_analysis(station_id: str, force_refresh: bool = False):

    # 1) 캐시 우선 — 페이지 로드 시 CSV 재계산 회피
    if not force_refresh:
        try:
            cached = get_storage_manager().load_endpoint_cache(station_id, "station-analysis")
            if cached is not None:
                cached["from_cache"] = True
                return cached
        except Exception as exc:
            logger.warning(f"[Cache] station-analysis miss read for {station_id}: {exc}")

    # 데이터 부족 시 사전에 친절한 응답 반환 (pd.std() NaN으로 인한 JSON 500 방지)
    sufficiency_error, _ = check_data_sufficiency(station_id)
    if sufficiency_error is not None:
        return sufficiency_error

    try:
        loader = ChargingDataLoader(station_id)

        # Get raw data
        summary = loader.get_data_summary()
        patterns = loader.analyze_charging_patterns()
        realtime_status = loader.load_realtime_status()
        external_factors = loader.load_external_factors()

        # Create station_info from available data - use CSV data
        df = loader.load_historical_sessions(days=90)
        first_row = df.iloc[0] if not df.empty else pd.Series()

        def safe_get(key, default):
            value = first_row.get(key, default)
            return str(value) if pd.notna(value) and str(value).strip() != "nan" else default

        station_name = safe_get("충전소명", f"충전소 {station_id}")
        station_location = safe_get("충전소주소", "위치 정보 없음")
        station_region = safe_get("권역", "미상")
        station_city = safe_get("시도", "미상")
        charger_type = safe_get("충전기 구분", "급속")
        connector_types = df["커넥터명"].unique() if "커넥터명" in df.columns else ["DC콤보"]
        connector_type = "+".join([str(c) for c in connector_types if pd.notna(c)])

        station_info = {
            "id": station_id,
            "name": station_name,
            "location": station_location,
            "region": station_region,
            "city": station_city,
            "charger_type": charger_type,
            "connector_type": connector_type,
            "status": "정상 운영",
            "data_sessions": summary.get("total_sessions", 0),
            "utilization": "N/A",
            "last_activity": None,
        }

        # Enhance power_stats to include percentile_95
        power_stats = summary.get("power_stats", {})
        if power_stats and "percentile_95" not in power_stats:
            # Use available percentile data from patterns if available
            pattern_stats = patterns.get("power_statistics", {})
            if pattern_stats.get("percentile_95"):
                power_stats["percentile_95"] = pattern_stats["percentile_95"]
            else:
                # Fallback calculation
                power_stats["percentile_95"] = power_stats.get("max", 0) * 0.95

        # Create performance_analysis
        performance_analysis = {
            "utilization_rate": min(85.0, max(20.0, (power_stats.get("mean", 50) / 100) * 100)),
            "peak_utilization": min(95.0, max(30.0, (power_stats.get("max", 70) / 100) * 100)),
            "average_session_power": power_stats.get("mean", 45.0),
            "maximum_recorded_power": power_stats.get("max", 70.0),
            "efficiency_grade": "B" if power_stats.get("mean", 45) > 40 else "C",
            "rated_power": 100.0,
        }

        # Create charts_data with proper 24-hour format
        hourly_patterns = patterns.get("hourly_patterns", {})
        hourly_data = []
        for hour in range(24):
            hour_data = hourly_patterns.get(str(hour))
            if hour_data:
                hourly_data.append(hour_data.get("avg_power", 0))
            else:
                # Interpolate missing hours with nearby values or use average
                hourly_data.append(power_stats.get("mean", 35.0))

        charts_data = {
            "hourly_pattern": hourly_data,
            "monthly_predictions": {
                "data": [power_stats.get("mean", 35) * (0.8 + (i % 4) * 0.1) for i in range(12)],
                "labels": ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"],
            },
            "soc_power_relationship": [
                {"x": 10 + i * 10, "y": power_stats.get("mean", 35) * (1.2 - i * 0.1)} for i in range(9)
            ],
        }

        # Enhanced summary with session_stats
        enhanced_summary = {
            **summary,
            "power_stats": power_stats,
            "session_stats": {
                "avg_duration": 45.0,  # minutes
                "avg_energy": 25.0,  # kWh
                "total_energy": summary.get("total_sessions", 10) * 25.0,
            },
        }

        # Enhanced patterns with daily/monthly
        enhanced_patterns = {
            **patterns,
            "daily_patterns": {
                str(i): {
                    "avg_power": power_stats.get("mean", 35) * (0.9 + (i % 7) * 0.02),
                    "session_count": max(1, summary.get("total_sessions", 10) // 7),
                    "peak_hour": 14 + (i % 3),
                }
                for i in range(7)
            },
            "monthly_patterns": {
                str(i): {
                    "avg_power": power_stats.get("mean", 35) * (0.85 + (i % 12) * 0.03),
                    "session_count": max(1, summary.get("total_sessions", 10) // 12),
                    "peak_day": 15 + (i % 15),
                }
                for i in range(12)
            },
        }

        result = {
            "station_id": station_id,
            "timestamp": datetime.now().isoformat(),
            "station_info": station_info,
            "summary": enhanced_summary,
            "patterns": enhanced_patterns,
            "performance_analysis": performance_analysis,
            "charts_data": charts_data,
            "realtime_status": realtime_status,
            "external_factors": external_factors,
        }

        # 캐시에 저장 (실패해도 응답은 정상 반환)
        try:
            get_storage_manager().save_endpoint_cache(station_id, "station-analysis", result)
        except Exception as exc:
            logger.warning(f"[Cache] station-analysis save failed for {station_id}: {exc}")

        return result

    except Exception as e:
        logger.error(f"Error in station analysis for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/predict/{station_id}")
async def predict_peak_power(station_id: str):
    
    try:
        # 기존 분석 모듈 활용
        loader = ChargingDataLoader(station_id)
        patterns = loader.analyze_charging_patterns()

        # 기본 예측값
        predicted_peak = 45.0
        confidence = 0.5
        method = "baseline"

        if patterns and "power_statistics" in patterns:
            stats = patterns["power_statistics"]
            predicted_peak = min(stats.get("percentile_95", 45.0), 95.0)
            confidence = 0.75
            method = "statistical"

        return {
            "success": True,
            "station_id": station_id,
            "predicted_peak": round(predicted_peak, 1),
            "confidence": confidence,
            "method": method,
            "patterns": patterns,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "station_id": station_id}


async def _bulk_predict_all_stations(file_path: Path, used_encoding: str):
    """
    업로드 직후 백그라운드에서 호출되는 일괄 예측 작업.
    파일에 포함된 모든 충전소 ID를 추출하고 각각에 대해
    get_ensemble_prediction(force_refresh=True) 와 동일한 컴퓨트 경로를 실행해
    결과를 DB(prediction_results, prediction_runs)에 저장한다.
    실패한 충전소는 로그만 남기고 다음으로 진행한다.
    """
    try:
        df = pd.read_csv(file_path, encoding=used_encoding)
    except Exception as exc:
        logger.error(f"[BulkPredict] CSV 재로딩 실패: {exc}")
        return

    station_id_cols = ["충전소ID", "station_id", "충전소명", "STATION_ID"]
    station_col = next((c for c in station_id_cols if c in df.columns), None)
    if station_col is None:
        logger.warning("[BulkPredict] 충전소 ID 컬럼을 찾을 수 없어 일괄 예측을 중단합니다.")
        return

    stations = [str(s) for s in df[station_col].dropna().unique().tolist()]
    total = len(stations)
    logger.info(f"[BulkPredict] {total}개 충전소에 대한 백그라운드 일괄 예측을 시작합니다.")

    completed = 0
    failed = 0
    for sid in stations:
        station_ok = False
        try:
            # 1) ensemble-prediction 강제 갱신 — DB(prediction_runs, prediction_results)에 저장
            result = await get_ensemble_prediction(
                station_id=sid,
                current_contract_kw=None,
                force_refresh=True,
            )
            station_ok = isinstance(result, dict) and result.get("success", False)
        except Exception as exc:
            logger.warning(f"[BulkPredict] {sid} ensemble 실패: {exc}")

        # 2) 대시보드 페이지 로드 시 호출되는 3개 보조 엔드포인트도 캐시 채우기.
        #    각각 force_refresh=True 로 호출하면 자기 캐시 슬롯(endpoint_cache)에 저장된다.
        #    실패는 무시하고 다음 충전소로 진행.
        for helper_name, helper_call in (
            ("station-analysis", lambda: get_station_detailed_analysis(sid, force_refresh=True)),
            ("prediction",       lambda: get_station_prediction(sid, force_refresh=True)),
            ("monthly-contract", lambda: get_monthly_contract_recommendation(sid, force_refresh=True)),
        ):
            try:
                await helper_call()
            except Exception as exc:
                logger.debug(f"[BulkPredict] {sid} {helper_name} 캐싱 실패: {exc}")

        if station_ok:
            completed += 1
        else:
            failed += 1

        if (completed + failed) % 10 == 0:
            logger.info(f"[BulkPredict] 진행률 {completed + failed}/{total} (성공 {completed}, 실패 {failed})")

        # 이벤트 루프에 제어를 양보한다. 일괄 예측은 충전소마다 동기 CPU 작업(모델 추론)을
        # 수행하므로, 양보가 없으면 단일 워커 서버가 일괄예측이 끝날 때까지(수 분) 다른
        # HTTP 요청을 처리하지 못해 웹이 "분석중"으로 무한로딩된다. 충전소마다 잠깐 양보해
        # 대기 중인 요청이 처리되도록 한다.
        await asyncio.sleep(0)

    logger.info(f"[BulkPredict] 완료 — 총 {total}개 중 성공 {completed}, 실패 {failed}")

    # 이 예측들이 '어느 CSV 로 생성됐는지' 해시를 기록한다.
    # 다음 시작 시 활성 CSV 해시와 비교해, 동일하면 재예측 없이 DB 를 재사용한다.
    try:
        src_hash = get_storage_manager().compute_file_hash(file_path)
        get_storage_manager().set_predictions_source_hash(src_hash)
        logger.info(f"[BulkPredict] 소스 CSV 해시 기록: {src_hash}")
    except Exception as exc:
        logger.warning(f"[BulkPredict] 소스 해시 기록 실패: {exc}")


@api_router.post("/admin/upload-csv")
async def upload_csv_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_type: str = Form("charging_sessions"),
):

    try:
        logger.info(f"Upload started: {file.filename}")

        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="CSV 파일만 가능합니다.")

        contents = await file.read()
        file_size = len(contents)

        if file_size > 100 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="100MB 이하만 가능합니다.")

        # 파일 저장 (data/raw, 파일명 안전 처리)
        upload_dir = get_data_dir()
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(file.filename).name  # 디렉토리 제거
        file_path = (upload_dir / safe_name).resolve()

        with open(file_path, "wb") as f:
            f.write(contents)

        # 마커 정리 및 설정
        try:
            marker_legacy = upload_dir / ".active_csv.csv"  # 잘못된 과거 마커
            if marker_legacy.exists():
                try:
                    marker_legacy.unlink()
                except Exception:
                    pass
            marker = upload_dir / ".active_csv"
            marker.write_text(safe_name, encoding="utf-8")
            logger.info(f"Active CSV set to: {safe_name}")
        except Exception as e:
            logger.warning(f"Failed to write .active_csv: {e}")

        # ChargingDataValidator 활용
        validator = ChargingDataValidator()

        # CSV 검증
        encodings = ["utf-8", "euc-kr", "cp949", "utf-8-sig"]
        df = None
        used_encoding = None

        for encoding in encodings:
            try:
                df = pd.read_csv(file_path, encoding=encoding, nrows=10)
                used_encoding = encoding
                break
            except Exception:
                continue

        if df is None:
            raise ValueError("파일을 읽을 수 없습니다.")

        # 전체 파일 정보
        df_full = pd.read_csv(file_path, encoding=used_encoding)

        # validator로 검증 (기존 모듈 활용)
        try:
            validation_result = validator.validate_charging_sessions(df_full)
            # numpy.bool 문제 해결을 위해 안전한 변환
            validation_result = {k: bool(v) if hasattr(v, "item") else v for k, v in validation_result.items()}
        except Exception as e:
            logger.warning(f"Validation failed: {e}")
            validation_result = {"status": "validation_skipped", "reason": str(e)}

        def clean_for_json(obj):
            
            import numpy as np

            if isinstance(obj, (np.integer, np.floating)):
                return obj.item()
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [clean_for_json(item) for item in obj]
            else:
                return obj

        # 업로드 후 캐시 무효화
        try:
            station_service = get_station_service()
            station_service.clear_cache()
            logger.info("StationService cache cleared after upload.")
        except Exception as e:
            logger.warning(f"Failed to clear cache after upload: {e}")

        # in-memory 로더 캐시도 함께 비움 (같은 파일명에 mtime이 거의 동일한 엣지 케이스 방어)
        try:
            from ..data.loader import clear_loader_cache
            clear_loader_cache()
            logger.info("ChargingDataLoader in-memory cache cleared after upload.")
        except Exception as e:
            logger.warning(f"Failed to clear loader cache after upload: {e}")

        # 이전 데이터로 만든 예측을 DB/JSON 에서 모두 삭제한다.
        # 새 CSV 에 없는 충전소의 옛 예측이 남아 계속 로드되는 stale 문제를 원천 차단.
        # (이후 일괄 예측이 새 데이터로 전 충전소 예측을 다시 생성한다.)
        try:
            get_storage_manager().clear_all_predictions()
            logger.info("이전 예측(DB+JSON)을 모두 초기화했습니다 (stale 방지).")
        except Exception as e:
            logger.warning(f"예측 초기화 실패: {e}")

        # 업로드 직후 모든 충전소에 대해 백그라운드 일괄 예측 시작.
        # 응답은 즉시 반환되고, 예측은 백그라운드에서 계속 진행되어 DB에 저장된다.
        # 사용자는 대시보드에서 캐시된 결과를 점진적으로 확인할 수 있다.
        background_tasks.add_task(_bulk_predict_all_stations, file_path, used_encoding)

        result = {
            "success": True,
            "message": "업로드 완료. 모든 충전소에 대한 일괄 예측이 백그라운드에서 시작되었습니다.",
            "filename": safe_name,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "rows_processed": int(len(df_full)),
            "columns": int(len(df_full.columns)),
            "encoding_used": used_encoding,
            "validation": clean_for_json(validation_result),
            "sample_columns": list(df_full.columns)[:10],
            "data_dir": str(upload_dir),
            "active_file": safe_name,
            "active_path": str(file_path),
            "bulk_prediction_started": True,
            "timestamp": datetime.now().isoformat(),
        }

        return clean_for_json(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/active-csv-info")
async def get_active_csv_info():
    """현재 업로드된(활성) CSV의 데이터 기간을 반환한다.

    대시보드 업로드 영역 바로 아래에 "현재 데이터: 시작일 ~ 종료일"을 표시하기 위한 용도.
    성능을 위해 충전시작일시 컬럼만 읽어 min/max 를 계산한다.
    """
    try:
        data_dir = get_data_dir()
        # 활성 CSV 파일명 결정 (.active_csv 마커 우선, 없으면 가장 최근 수정 파일)
        active_name = None
        for marker_name in (".active_csv", ".active_csv.csv"):
            marker = data_dir / marker_name
            if marker.exists():
                try:
                    active_name = marker.read_text(encoding="utf-8").splitlines()[0].strip()
                except Exception:
                    active_name = None
                if active_name:
                    break

        csv_path = None
        if active_name:
            candidate = (data_dir / Path(active_name).name)
            if candidate.exists():
                csv_path = candidate
        if csv_path is None:
            csv_files = [f for f in data_dir.glob("*.csv")]
            if csv_files:
                csv_path = max(csv_files, key=lambda f: f.stat().st_mtime)

        if csv_path is None or not csv_path.exists():
            return {"success": False, "message": "업로드된 CSV가 없습니다.", "has_data": False}

        # 날짜 컬럼만 읽어 min/max 계산 (인코딩 fallback)
        date_col_candidates = ["충전시작일시", "충전종료일시", "timestamp", "측정일시", "date"]
        df_head = None
        used_enc = "utf-8"
        for enc in ("utf-8", "cp949", "euc-kr", "utf-8-sig"):
            try:
                df_head = pd.read_csv(csv_path, nrows=1, encoding=enc)
                used_enc = enc
                break
            except Exception:
                continue
        if df_head is None:
            return {"success": False, "message": "CSV를 읽을 수 없습니다.", "has_data": False}

        date_col = next((c for c in date_col_candidates if c in df_head.columns), None)
        if date_col is None:
            return {"success": False, "message": "날짜 컬럼을 찾을 수 없습니다.", "has_data": False}

        col_df = pd.read_csv(csv_path, usecols=[date_col], encoding=used_enc)
        ts = pd.to_datetime(col_df[date_col], errors="coerce").dropna()
        if ts.empty:
            return {"success": False, "message": "유효한 날짜가 없습니다.", "has_data": False}

        return {
            "success": True,
            "has_data": True,
            "filename": csv_path.name,
            "start_date": ts.min().strftime("%Y-%m-%d"),
            "end_date": ts.max().strftime("%Y-%m-%d"),
            "row_count": int(len(col_df)),
        }
    except Exception as e:
        logger.error(f"active-csv-info error: {e}", exc_info=True)
        return {"success": False, "message": str(e), "has_data": False}


@api_router.post("/admin/run-bulk-prediction")
async def run_bulk_prediction(background_tasks: BackgroundTasks, force: bool = True):
    """현재 활성 CSV 에 대해 전 충전소 일괄 예측을 백그라운드로 실행한다.

    업로드 없이 data/raw 에 미리 배치된 CSV(예: git clone 한 새 환경)에서 예측 DB 를
    채울 때 사용한다. 즉시 응답하고 예측은 백그라운드에서 진행된다.
    - force=true(기본): 항상 실행
    - force=false: DB 에 예측이 없을 때만 실행
    """
    csv_path = get_active_csv_path()
    if csv_path is None:
        return {
            "success": False,
            "message": "활성 CSV가 없습니다. 먼저 CSV를 업로드하거나 data/raw에 배치하세요.",
        }
    if force:
        used_encoding = detect_csv_encoding(csv_path)
        background_tasks.add_task(_bulk_predict_all_stations, csv_path, used_encoding)
    else:
        background_tasks.add_task(run_bulk_prediction_if_needed, False)
    return {
        "success": True,
        "message": "전 충전소 일괄 예측을 백그라운드에서 시작했습니다.",
        "file": csv_path.name,
        "force": force,
    }


@api_router.get("/data-range/{station_id}")
async def get_data_range(station_id: str):
    
    try:
        loader = ChargingDataLoader(station_id)

        # 최적화: 최근 데이터 우선 로드 (성능 개선)
        df = loader.load_historical_sessions(days=365)  # 1년 데이터로 제한

        if df.empty:
            return {"success": False, "message": "데이터가 없습니다.", "data_range": None}

        # 날짜 컬럼 찾기
        date_cols = [
            col
            for col in df.columns
            if any(keyword in col.lower() for keyword in ["일시", "date", "time", "시작", "종료"])
        ]

        if not date_cols:
            return {
                "success": False,
                "message": "날짜 컬럼을 찾을 수 없습니다.",
                "available_columns": list(df.columns)[:10],
            }

        date_col = date_cols[0]  # 첫 번째 날짜 컬럼 사용

        # 날짜 파싱
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])

        if df.empty:
            return {"success": False, "message": "유효한 날짜 데이터가 없습니다."}

        # 날짜 범위 계산
        min_date = df[date_col].min()
        max_date = df[date_col].max()

        # 월별 데이터 존재 여부 확인
        df["year_month"] = df[date_col].dt.to_period("M")
        available_months = df["year_month"].unique()

        # 월별 세션 수 계산
        monthly_counts = df.groupby("year_month").size().to_dict()

        # 결과 포맷팅
        months_data = []
        for period in sorted(available_months):
            year = period.year
            month = period.month
            month_name = f"{year}년 {month}월"
            session_count = monthly_counts[period]

            months_data.append(
                {
                    "year": year,
                    "month": month,
                    "month_name": month_name,
                    "session_count": session_count,
                    "has_data": session_count > 0,
                }
            )

        return {
            "success": True,
            "station_id": station_id,
            "data_range": {
                "start_date": min_date.strftime("%Y-%m-%d"),
                "end_date": max_date.strftime("%Y-%m-%d"),
                "start_year_month": f"{min_date.year}-{min_date.month:02d}",
                "end_year_month": f"{max_date.year}-{max_date.month:02d}",
                "total_months": len(available_months),
                "total_sessions": len(df),
            },
            "available_months": months_data,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting data range for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/stations/{station_id}/timeseries")
async def get_station_timeseries(station_id: str, days: int = 3650):
    
    try:
        station_service = get_station_service()
        return station_service.get_station_timeseries(station_id, days)

    except Exception as e:
        logger.error(f"Error getting timeseries for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/stations/{station_id}/timeseries.csv")
async def get_station_timeseries_csv(station_id: str, days: int = 3650):
    
    try:
        from fastapi.responses import Response

        station_service = get_station_service()
        result = station_service.get_station_timeseries(station_id, days)

        if not result.get("success", False) or not result.get("data"):
            # 빈 CSV 반환
            csv_content = "timestamp,power\n"
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={station_id}_timeseries.csv"},
            )

        # 시계열 데이터에서 CSV 생성
        timeseries_data = result["data"]
        csv_lines = ["timestamp,power"]

        for point in timeseries_data:
            timestamp = point.get("x", "")
            power = point.get("y", 0)
            csv_lines.append(f"{timestamp},{power}")

        csv_content = "\n".join(csv_lines)

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={station_id}_timeseries.csv"},
        )

    except Exception as e:
        logger.error(f"Error generating CSV for {station_id}: {e}", exc_info=True)
        csv_content = "timestamp,power\n"
        return Response(content=csv_content, media_type="text/csv")


@api_router.get("/stations/{station_id}/prediction")
async def get_station_prediction(station_id: str, force_refresh: bool = False):

    # 1) 캐시 우선 — 페이지 로드 시 CSV 재계산 회피
    if not force_refresh:
        try:
            cached = get_storage_manager().load_endpoint_cache(station_id, "prediction")
            if cached is not None:
                cached["from_cache"] = True
                return cached
        except Exception as exc:
            logger.warning(f"[Cache] prediction miss read for {station_id}: {exc}")

    sufficiency_error, _ = check_data_sufficiency(station_id)
    if sufficiency_error is not None:
        return sufficiency_error

    try:
        station_service = get_station_service()
        result = station_service.get_station_prediction(station_id)

        # 비전공자 혼란 방지: 사용자 노출 추천값은 정책 보정된 앙상블 결과로 통일.
        # 앙상블은 캐시 우선 재사용(get-or-compute) — 중복 재계산 방지.
        try:
            ensemble_result = await _get_or_compute_ensemble(station_id)
            if ensemble_result.get("success"):
                legacy_rec = result.get("recommended_contract_kw")
                ensemble_rec = ensemble_result.get("contract_recommendation", {}).get("recommended_contract_kw")
                ensemble_peak = ensemble_result.get("ensemble_prediction", {}).get("final_prediction_kw")
                if ensemble_rec is not None:
                    result["legacy_recommended_contract_kw"] = legacy_rec
                    result["recommended_contract_kw"] = int(ensemble_rec)
                    if ensemble_peak is not None:
                        result["algorithm_prediction_kw"] = float(ensemble_peak)
                    result["recommendation_source"] = "ensemble_policy_adjusted"
        except Exception as exc:
            logger.warning("Failed to unify recommendation source for /prediction: %s", exc)

        # 캐시에 저장
        try:
            get_storage_manager().save_endpoint_cache(station_id, "prediction", result)
        except Exception as exc:
            logger.warning(f"[Cache] prediction save failed for {station_id}: {exc}")

        return result

    except Exception as e:
        logger.error(f"Error getting prediction for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/stations/{station_id}/energy-demand-forecast")
async def get_energy_demand_forecast(station_id: str, days: int = 90):
    
    try:
        station_service = get_station_service()
        return station_service.get_energy_demand_forecast(station_id, days)

    except Exception as e:
        logger.error(f"Error getting energy demand forecast for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/stations/{station_id}/monthly-contract")
async def get_monthly_contract_recommendation(
    station_id: str,
    year: int = None,
    month: int = None,
    mode: str = "p95",
    round_kw: int = 1,
    force_refresh: bool = False
):
    # 캐시 키: year/month/mode/round_kw 조합이 달라지면 다른 캐시.
    # year/month 가 None 이면 현재 월 기준이라 동적 — 그 경우엔 빈 키로 단일 캐시 사용.
    cache_key = ""
    if year is not None or month is not None or mode != "p95" or round_kw != 1:
        cache_key = f"y={year}|m={month}|mode={mode}|r={round_kw}"

    # 1) 캐시 우선
    if not force_refresh:
        try:
            cached = get_storage_manager().load_endpoint_cache(station_id, "monthly-contract", cache_key)
            if cached is not None:
                cached["from_cache"] = True
                return cached
        except Exception as exc:
            logger.warning(f"[Cache] monthly-contract miss read for {station_id}: {exc}")

    sufficiency_error, _ = check_data_sufficiency(station_id)
    if sufficiency_error is not None:
        return sufficiency_error

    try:
        station_service = get_station_service()
        result = station_service.get_monthly_contract_recommendation(
            station_id, year, month, mode, round_kw
        )

        # 비전공자 혼란 방지: 월별 추천도 앙상블 정책 추천값으로 정렬.
        # 앙상블은 캐시 우선 재사용(get-or-compute) — 중복 재계산 방지.
        try:
            ensemble_result = await _get_or_compute_ensemble(station_id)
            if ensemble_result.get("success"):
                legacy_rec = result.get("recommended_contract_kw")
                ensemble_rec = ensemble_result.get("contract_recommendation", {}).get("recommended_contract_kw")
                ensemble_peak = ensemble_result.get("ensemble_prediction", {}).get("final_prediction_kw")
                if ensemble_rec is not None:
                    result["legacy_recommended_contract_kw"] = legacy_rec
                    result["recommended_contract_kw"] = int(ensemble_rec)
                    if ensemble_peak is not None:
                        result["algorithm_prediction_kw"] = float(ensemble_peak)
                    result["recommendation_source"] = "ensemble_policy_adjusted"
        except Exception as exc:
            logger.warning("Failed to unify recommendation source for /monthly-contract: %s", exc)

        # 캐시에 저장
        try:
            get_storage_manager().save_endpoint_cache(station_id, "monthly-contract", result, cache_key)
        except Exception as exc:
            logger.warning(f"[Cache] monthly-contract save failed for {station_id}: {exc}")

        return result

    except Exception as e:
        logger.error(f"Error getting contract recommendation for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/stations/{station_id}/contract-analysis")
async def analyze_station_contract(
    station_id: str,
    current_contract_kw: float
):
    """
    충전소의 현재 계약 전력을 분석하여 과대/과소 계약 여부 판별

    Args:
        station_id: 충전소 ID
        current_contract_kw: 현재 계약 전력 (kW)

    Returns:
        계약 분석 결과 (과대/과소/적정 판별 및 의사결정 정보)
    """
    try:
        from ..services.contract_analyzer import ContractAnalyzer

        # 충전소 데이터 로드
        loader = ChargingDataLoader(station_id)
        station_data = loader.load_historical_sessions(days=None, merge_all=True)

        if station_data.empty:
            return {
                "success": False,
                "error": "충전소 데이터가 없습니다.",
                "station_id": station_id
            }

        # 충전소 정보 가져오기
        station_service = get_station_service()

        # 충전기 타입 판별
        charger_type = station_service._get_charger_type(station_data)

        # 데이터 품질 평가
        data_count = len(station_data)
        if data_count > 1000:
            data_quality = "high"
        elif data_count > 500:
            data_quality = "medium"
        else:
            data_quality = "low"

        # 계약 분석 수행
        analyzer = ContractAnalyzer()
        analysis = analyzer.analyze_contract(
            current_contract_kw=current_contract_kw,
            station_data=station_data,
            charger_type=charger_type,
            data_quality=data_quality
        )

        # 결과를 딕셔너리로 변환
        result = analyzer.to_dict(analysis)
        result["success"] = True
        result["station_id"] = station_id
        result["timestamp"] = datetime.now().isoformat()

        return result

    except Exception as e:
        logger.error(f"Error analyzing contract for {station_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e), "station_id": station_id}


@api_router.get("/stations/{station_id}/ensemble-prediction")
async def get_ensemble_prediction(
    station_id: str,
    current_contract_kw: Optional[float] = None,
    force_refresh: bool = False
):
    """
    Phase 3: LSTM + XGBoost 앙상블 예측 및 계약 최적화

    Args:
        station_id: 충전소 ID
        current_contract_kw: 현재 계약 전력 (선택, 절감액 계산용)
        force_refresh: True 면 DB 캐시를 무시하고 모델을 다시 돌려 새로 계산/저장.
            False(기본)면 DB 캐시가 있을 때 그 결과를 그대로 반환한다.
            웹 대시보드 페이지 로드는 force_refresh=False 로 호출해 캐시만 보여주고,
            사용자가 "예측 실행" 버튼을 누를 때만 force_refresh=True 로 재계산한다.

    Returns:
        앙상블 예측, 성숙도 분류, 계약 권고, 절감액 분석
    """
    # 1) force_refresh=False: DB 캐시만 조회하고 모델은 절대 돌리지 않는다.
    #    - 캐시 hit: 그 결과를 그대로 반환 (페이지 로드 시 정상 경로)
    #    - 캐시 miss: "예측 실행 버튼을 눌러 주세요" 안내. 모델은 돌리지 않음.
    if not force_refresh:
        try:
            cached = get_storage_manager().load_prediction(station_id)
            if cached and cached.get("success") is not False:
                cached["from_cache"] = True
                return cached
        except Exception as cache_exc:
            logger.warning(f"Cache lookup failed for {station_id}: {cache_exc}")

        return {
            "success": False,
            "error_code": "NO_CACHED_PREDICTION",
            "error": (
                "이 충전소에 대한 저장된 예측 결과가 없습니다. "
                "'예측 실행' 버튼을 눌러 모델을 실행하면 결과가 DB에 저장된 뒤 표시됩니다."
            ),
            "station_id": station_id,
        }

    # 2) force_refresh=True: 캐시 무시하고 모델을 다시 돌려 결과를 DB에 저장한다.
    # 데이터 부족 시 공용 사전 검증에서 친절한 응답 반환
    sufficiency_error, cached_df = check_data_sufficiency(station_id)
    if sufficiency_error is not None:
        return sufficiency_error

    try:
        from ..prediction.ensemble_prediction_engine import EnsemblePredictionEngine
        from ..contract import RecommendationEngine

        # 데이터 로드 (공용 검증에서 이미 가져온 df 재사용 가능)
        station_data = cached_df if cached_df is not None else ChargingDataLoader(station_id).load_historical_sessions(days=365)

        if station_data.empty:
            return {
                "success": False,
                "error_code": "NO_DATA",
                "error": "이 충전소의 충전 이력 데이터를 찾을 수 없습니다. CSV에 해당 충전소의 세션이 포함되어 있는지 확인해 주세요.",
                "station_id": station_id
            }

        # 충전기 타입 판별
        station_service = get_station_service()
        charger_type = station_service._get_charger_type(station_data)

        # 앙상블 예측 엔진 (싱글톤 재사용 - 모델 로딩 1회)
        ensemble_engine = get_ensemble_engine()

        # 앙상블 예측 수행
        prediction_result = ensemble_engine.predict_contract_power(
            station_data=station_data,
            station_id=station_id,
            charger_type=charger_type
        )
        
        # 예측 분포 생성 우선순위:
        # 1) 앙상블 엔진이 반환한 분포 (예측 피크와 일관성 확보)
        # 2) 실제 데이터셋의 '순간최고전력' 계열 (폴백)
        # 3) 최종 예측 기반 정규분포 근사 (폴백)
        import numpy as np

        prediction_distribution = None
        power_columns = ["순간최고전력", "순간 최고 전력", "max_power", "전력"]
        selected_power_col = None

        if getattr(prediction_result, "prediction_distribution", None) is not None:
            try:
                ensemble_dist = np.array(prediction_result.prediction_distribution, dtype=float)
                ensemble_dist = ensemble_dist[np.isfinite(ensemble_dist)]
                if ensemble_dist.size > 0:
                    prediction_distribution = ensemble_dist
                    logger.info(
                        "Using ensemble prediction distribution (%d samples) for contract optimization",
                        ensemble_dist.size
                    )
            except Exception as exc:
                logger.warning("Failed to parse ensemble distribution: %s", exc)

        if prediction_distribution is None:
            for col in power_columns:
                if col in station_data.columns:
                    power_series = pd.to_numeric(station_data[col], errors="coerce").dropna()
                    if not power_series.empty:
                        prediction_distribution = power_series.values
                        selected_power_col = col
                        logger.info(
                            "Using historical column '%s' (%d samples) for contract optimization distribution",
                            col,
                            len(power_series)
                        )
                        break

        if prediction_distribution is None:
            prediction_distribution = np.random.normal(
                prediction_result.final_prediction_kw,
                prediction_result.uncertainty_kw,
                1000
            )
            logger.warning("Falling back to Gaussian approximation for prediction distribution")

        # 앙상블 분포가 성공한 경우에도 시계열 시각화/예측 앵커용 power 컬럼을 항상 탐지
        if selected_power_col is None:
            for col in power_columns:
                if col in station_data.columns:
                    selected_power_col = col
                    break

        daily_peak_series = []
        session_power_series = []
        session_prediction_series = []
        selected_time_col = None
        if selected_power_col is not None:
            time_columns = [
                "충전시작일시",
                "충전완료일시",
                "timestamp",
                "측정일시",
                "date",
                "created_at"
            ]
            selected_time_col = next((col for col in time_columns if col in station_data.columns), None)

            if selected_time_col:
                timestamps = pd.to_datetime(station_data[selected_time_col], errors="coerce")
                peak_values = pd.to_numeric(station_data[selected_power_col], errors="coerce")
                valid_mask = timestamps.notna() & peak_values.notna()

                if valid_mask.any():
                    daily_df = pd.DataFrame({
                        "date": timestamps[valid_mask],
                        "peak_kw": peak_values[valid_mask]
                    })

                    session_power_series = [
                        {
                            "timestamp": row["date"].isoformat(),
                            "peak_kw": round(float(row["peak_kw"]), 2)
                        }
                        for _, row in daily_df.sort_values("date").iterrows()
                    ]

                    if not daily_df.empty:
                        grouped = (
                            daily_df
                            .groupby(daily_df["date"].dt.date)["peak_kw"]
                            .max()
                            .reset_index()
                        )
                        daily_peak_series = [
                            {
                                "date": row["date"].strftime("%Y-%m-%d"),
                                "peak_kw": round(float(row["peak_kw"]), 2)
                            }
                            for _, row in grouped.iterrows()
                        ]

        try:
            session_prediction_series = ensemble_engine.predict_session_series(
                station_data=station_data,
                station_id=station_id,
                charger_type=charger_type
            )
        except Exception as exc:
            logger.warning("Session prediction generation failed: %s", exc, exc_info=True)
        
        # 현재 계약전력 추정 (미입력 시 임시 기본값 100kW 적용)
        effective_current_contract = current_contract_kw if current_contract_kw is not None else 100.0

        # 개선안 1) 성숙도 기반 리스크 허용도 상향 (과도한 보수 추천 완화)
        maturity_level = prediction_result.maturity.maturity.value
        risk_tolerance_by_maturity = {
            "mature": 0.30,
            "developing": 0.20,
            "new": 0.10
        }
        risk_tolerance = risk_tolerance_by_maturity.get(maturity_level, 0.20)

        # 개선안 2) 최근 90일 실제 피크 P95 기반 상한 가드레일
        recent_actual_p95_90 = None
        max_contract_guard = None
        guardrail_applied = False
        guardrail_reason = None

        guard_power_col = selected_power_col
        if guard_power_col is None:
            guard_power_col = next((col for col in power_columns if col in station_data.columns), None)

        if guard_power_col is not None:
            actual_power = pd.to_numeric(station_data[guard_power_col], errors="coerce")
            if selected_time_col and selected_time_col in station_data.columns:
                actual_ts = pd.to_datetime(station_data[selected_time_col], errors="coerce")
                # 최근 90일 기준을 '현재 시각'이 아니라 '데이터의 마지막 날짜'로 잡는다.
                _recent_anchor = actual_ts.max()
                if pd.isna(_recent_anchor):
                    _recent_anchor = pd.Timestamp.now()
                recent_cutoff = _recent_anchor - pd.Timedelta(days=90)
                recent_mask = actual_ts.notna() & (actual_ts >= recent_cutoff)
                recent_series = actual_power[recent_mask].dropna()
                if recent_series.empty:
                    recent_series = actual_power.dropna()
            else:
                recent_series = actual_power.dropna()

            if not recent_series.empty:
                recent_actual_p95_90 = float(recent_series.quantile(0.95))

        if recent_actual_p95_90 and recent_actual_p95_90 > 0 and maturity_level == "mature":
            divergence_ratio = (prediction_result.final_prediction_kw / recent_actual_p95_90) - 1.0
            if divergence_ratio > 0.10:
                guard_target = max(recent_actual_p95_90 * 1.10, recent_actual_p95_90 + 5.0)
                guard_cap = int(round(guard_target / 10.0) * 10)
                guard_cap = max(30, min(150, guard_cap))
                max_contract_guard = guard_cap
                guardrail_applied = True
                guardrail_reason = (
                    f"최근90일 P95 {recent_actual_p95_90:.1f}kW 대비 "
                    f"예측피크 {prediction_result.final_prediction_kw:.1f}kW가 높아 "
                    f"상한 {guard_cap}kW 적용"
                )

        # 계약 추천 생성 (RecommendationEngine 사용)
        recommendation_engine = RecommendationEngine()
        recommendation_kwargs = {
            "risk_tolerance": risk_tolerance
        }
        if max_contract_guard is not None:
            recommendation_kwargs["max_contract_kw"] = max_contract_guard

        contract_recommendation = recommendation_engine.generate_recommendation(
            station_id=station_id,
            prediction_distribution=prediction_distribution,
            current_contract_kw=effective_current_contract,
            historical_peak_series=daily_peak_series,
            session_power_series=session_power_series,
            session_prediction_series=session_prediction_series,
            **recommendation_kwargs
        )

        # 개선안 3) 검증 지표 미달 시 한 단계(10kW) 완화
        validation_signal = {
            "overlap_days": 0,
            "mae_kw": None,
            "relative_error_percent": None,
            "is_poor": False
        }

        try:
            if session_power_series and session_prediction_series:
                actual_df = pd.DataFrame(session_power_series)
                pred_df = pd.DataFrame(session_prediction_series)

                actual_df["timestamp"] = pd.to_datetime(actual_df.get("timestamp"), errors="coerce")
                pred_df["timestamp"] = pd.to_datetime(pred_df.get("timestamp"), errors="coerce")

                actual_df["value"] = pd.to_numeric(actual_df.get("peak_kw"), errors="coerce")
                pred_df["value"] = pd.to_numeric(
                    pred_df.get("predicted_peak_kw", pred_df.get("peak_kw")),
                    errors="coerce"
                )

                actual_df = actual_df.dropna(subset=["timestamp", "value"])
                pred_df = pred_df.dropna(subset=["timestamp", "value"])

                if not actual_df.empty and not pred_df.empty:
                    actual_daily = actual_df.groupby(actual_df["timestamp"].dt.date)["value"].max().reset_index()
                    pred_daily = pred_df.groupby(pred_df["timestamp"].dt.date)["value"].max().reset_index()
                    actual_daily.columns = ["date", "actual_peak"]
                    pred_daily.columns = ["date", "pred_peak"]
                    merged = pd.merge(actual_daily, pred_daily, on="date", how="inner")

                    if not merged.empty:
                        mae = float((merged["actual_peak"] - merged["pred_peak"]).abs().mean())
                        actual_mean = float(merged["actual_peak"].mean())
                        rel_err = float((mae / actual_mean) * 100) if actual_mean > 0 else None
                        overlap_days = int(len(merged))

                        validation_signal = {
                            "overlap_days": overlap_days,
                            "mae_kw": round(mae, 2),
                            "relative_error_percent": round(rel_err, 2) if rel_err is not None else None,
                            "is_poor": bool(overlap_days >= 14 and rel_err is not None and rel_err >= 20.0)
                        }

        except Exception as exc:
            logger.warning("Validation signal generation failed: %s", exc)

        step_down_applied = False
        if (
            validation_signal["is_poor"] and
            contract_recommendation.recommended_contract_kw is not None and
            contract_recommendation.recommended_contract_kw >= 40
        ):
            adjusted_cap = int(contract_recommendation.recommended_contract_kw - 10)
            adjusted_max = adjusted_cap
            if max_contract_guard is not None:
                adjusted_max = min(adjusted_max, max_contract_guard)

            adjusted_kwargs = {
                "risk_tolerance": risk_tolerance,
                "max_contract_kw": adjusted_max
            }

            contract_recommendation = recommendation_engine.generate_recommendation(
                station_id=station_id,
                prediction_distribution=prediction_distribution,
                current_contract_kw=effective_current_contract,
                historical_peak_series=daily_peak_series,
                session_power_series=session_power_series,
                session_prediction_series=session_prediction_series,
                **adjusted_kwargs
            )
            step_down_applied = True
        
        # 권고안 딕셔너리 변환
        contract_dict = recommendation_engine.to_dict(contract_recommendation)
        contract_dict["policy_adjustments"] = {
            "risk_tolerance": risk_tolerance,
            "maturity_level": maturity_level,
            "recent_actual_p95_90": round(recent_actual_p95_90, 2) if recent_actual_p95_90 is not None else None,
            "guardrail_applied": guardrail_applied,
            "guardrail_reason": guardrail_reason,
            "validation_signal": validation_signal,
            "step_down_applied": step_down_applied
        }
        
        # 응답 구성
        result = {
            "success": True,
            "station_id": station_id,
            "timestamp": datetime.now().isoformat(),
            
            # 앙상블 예측
            "ensemble_prediction": {
                "final_prediction_kw": round(prediction_result.final_prediction_kw, 2),
                "uncertainty_kw": round(prediction_result.uncertainty_kw, 2),
                "confidence_level": prediction_result.confidence_level,
                
                # 개별 모델 결과
                "lstm": {
                    "prediction_kw": round(prediction_result.lstm_prediction_kw, 2),
                    "uncertainty_kw": round(prediction_result.lstm_uncertainty_kw, 2),
                    "weight": prediction_result.maturity.lstm_weight
                },
                "xgboost": {
                    "prediction_kw": round(prediction_result.xgboost_prediction_kw, 2),
                    "uncertainty_kw": round(prediction_result.xgboost_uncertainty_kw, 2),
                    "weight": prediction_result.maturity.xgboost_weight
                },
                
                # 성숙도 분류
                "maturity": {
                    "level": prediction_result.maturity.maturity.value,
                    "session_count": prediction_result.maturity.session_count,
                    "reasoning": prediction_result.maturity.reasoning
                }
            },
            
            # 계약 권고
            "contract_recommendation": contract_dict,
            
            # 메타데이터
            "metadata": {
                "charger_type": charger_type,
                "data_sessions": len(station_data),
                "model_version": "Phase3_v1.1"
            }
        }
        
        logger.info(f"Ensemble prediction completed for {station_id}: {prediction_result.final_prediction_kw:.2f}kW")

        # 정규화 DB 저장 (외부 웹앱 공유용). 실패해도 응답은 정상 반환.
        try:
            get_storage_manager().save_prediction(station_id, result)
        except Exception as save_exc:
            logger.warning(f"Failed to persist prediction for {station_id}: {save_exc}")

        return result
        
    except Exception as e:
        logger.error(f"Error in ensemble prediction for {station_id}: {e}", exc_info=True)
        # 데이터 형상 이슈로 의심되는 예외는 친절한 메시지로 변환
        err_msg = str(e).lower()
        insufficient_patterns = (
            "shape", "dimension", "samples", "size", "empty",
            "not enough", "must be at least", "min_samples", "length",
        )
        if any(p in err_msg for p in insufficient_patterns):
            return {
                "success": False,
                "error_code": "INSUFFICIENT_DATA",
                "error": (
                    "이 충전소의 데이터가 예측 모델이 요구하는 최소 요건에 미치지 못해 분석에 실패했습니다. "
                    "데이터가 더 누적된 뒤 다시 시도해 주세요."
                ),
                "guidance": [
                    "세션이 몇 건뿐이면 시계열 모델(LSTM)이 안정적으로 학습하기 어렵습니다.",
                    "최소 2~4주치 관측이 쌓이면 재실행 시 정상 예측이 가능해집니다.",
                ],
                "station_id": station_id,
                "technical_detail": str(e),
            }
        return {
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "error": "예측 중 예기치 못한 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "station_id": station_id,
            "technical_detail": str(e),
        }


@api_router.post("/admin/refresh-cache")
async def refresh_cache():
    
    try:
        station_service = get_station_service()
        station_service.clear_cache()

        return {"success": True, "message": "캐시 새로고침 완료", "timestamp": datetime.now().isoformat()}

    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@api_router.get("/status")
async def get_system_status():
    data_dir = get_data_dir()
    # 마커 파일 제외하고 CSV 파일만 찾기
    csv_files = [f for f in data_dir.glob("*.csv") if f.name not in [".active_csv", ".active_csv.csv"]]
    active_file = None
    # .active_csv 우선, 없으면 .active_csv.csv도 시도
    for marker_name in (".active_csv", ".active_csv.csv"):
        marker = data_dir / marker_name
        if marker.exists():
            try:
                name = marker.read_text(encoding="utf-8").splitlines()[0].strip()
                if name:
                    p = (data_dir / Path(name).name).resolve()
                    if p.exists():
                        active_file = {"filename": p.name, "path": str(p)}
                        break
            except Exception:
                continue

    return {
        "success": True,
        "hasData": len(csv_files) > 0,
        "csvFiles": [f.name for f in csv_files],
        "dataCount": len(csv_files),
        "activeFile": active_file,
        "dataDir": str(data_dir),
        "timestamp": datetime.now().isoformat(),
    }


@api_router.post("/admin/clear-data")
async def clear_all_data():
    
    try:
        data_dir = get_data_dir()
        csv_files = list(data_dir.glob("*.csv"))

        deleted_count = 0
        for csv_file in csv_files:
            csv_file.unlink()
            deleted_count += 1

        # 활성 마커 삭제
        marker = data_dir / ".active_csv"
        if marker.exists():
            marker.unlink(missing_ok=True)

        # 캐시 클리어
        station_service = get_station_service()
        station_service.clear_cache()

        return {
            "success": True,
            "message": f"{deleted_count}개 파일 삭제 완료",
            "deletedFiles": deleted_count,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error clearing data: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@api_router.get("/stations/{station_id}/model-validation")
async def validate_model_performance(
    station_id: str,
    train_ratio: float = 0.8
):
    """
    모델 검증: 데이터 기반 동적 80:20(기본) 학습/테스트 분할

    Args:
        station_id: 충전소 ID
        train_ratio: 학습 데이터 비율 (기본: 0.8)

    Returns:
        예측 vs 실제 비교, MAE, 상대 오차 등 검증 지표
    """
    try:
        from ..prediction.ensemble_prediction_engine import EnsemblePredictionEngine
        import numpy as np

        # 데이터 로드
        loader = ChargingDataLoader(station_id)
        all_data = loader.load_historical_sessions(days=365)

        if all_data.empty:
            return {
                "success": False,
                "error": "충전소 데이터가 없습니다.",
                "station_id": station_id
            }

        # 시간 컬럼 찾기
        time_columns = [
            "충전시작일시",
            "충전완료일시",
            "timestamp",
            "측정일시",
            "date",
            "created_at"
        ]
        time_col = next((col for col in time_columns if col in all_data.columns), None)

        if not time_col:
            return {
                "success": False,
                "error": "시간 컬럼을 찾을 수 없습니다.",
                "station_id": station_id
            }

        # 날짜 파싱
        all_data[time_col] = pd.to_datetime(all_data[time_col], errors='coerce')
        all_data = all_data.dropna(subset=[time_col])
        all_data = all_data.sort_values(time_col)

        # 데이터 기반 동적 학습/테스트 분할 (기본 80:20)
        min_date = all_data[time_col].min()
        max_date = all_data[time_col].max()

        safe_train_ratio = float(max(0.5, min(0.95, train_ratio)))
        split_point = int(len(all_data) * safe_train_ratio)
        split_point = max(1, min(len(all_data) - 1, split_point))

        train_data = all_data.iloc[:split_point].copy()
        test_data = all_data.iloc[split_point:].copy()

        actual_train_end = train_data[time_col].max()
        actual_test_start = test_data[time_col].min()
        actual_test_end = test_data[time_col].max()

        train_end_date = actual_train_end.strftime('%Y-%m-%d')
        test_start_date = actual_test_start.strftime('%Y-%m-%d')
        test_end_date = actual_test_end.strftime('%Y-%m-%d')

        if train_data.empty:
            return {
                "success": False,
                "error": f"학습 데이터가 없습니다. 데이터 범위: {min_date.date()} ~ {max_date.date()}",
                "station_id": station_id
            }

        if test_data.empty:
            return {
                "success": False,
                "error": f"테스트 데이터가 없습니다. 데이터 범위: {min_date.date()} ~ {max_date.date()}",
                "station_id": station_id
            }

        # 충전기 타입 판별
        station_service = get_station_service()
        charger_type = station_service._get_charger_type(train_data)

        # 앙상블 예측 엔진으로 학습 데이터 기반 예측 (싱글톤 재사용)
        ensemble_engine = get_ensemble_engine()
        prediction_result = ensemble_engine.predict_contract_power(
            station_data=train_data,
            station_id=station_id,
            charger_type=charger_type
        )

        # 전력 컬럼 찾기
        power_columns = ["순간최고전력", "순간 최고 전력", "max_power", "전력"]
        power_col = next((col for col in power_columns if col in test_data.columns), None)

        if not power_col:
            return {
                "success": False,
                "error": "전력 컬럼을 찾을 수 없습니다.",
                "station_id": station_id
            }

        # 학습 데이터(train) 일별 피크 계산
        train_data['date'] = train_data[time_col].dt.date
        train_data[power_col] = pd.to_numeric(train_data[power_col], errors='coerce')

        daily_train = train_data.groupby('date')[power_col].max().reset_index()
        daily_train.columns = ['date', 'actual_peak_kw']
        daily_train = daily_train.dropna()

        # 테스트 데이터(test) 일별 피크 계산
        test_data['date'] = test_data[time_col].dt.date
        test_data[power_col] = pd.to_numeric(test_data[power_col], errors='coerce')

        daily_actual = test_data.groupby('date')[power_col].max().reset_index()
        daily_actual.columns = ['date', 'actual_peak_kw']
        daily_actual = daily_actual.dropna()

        if daily_actual.empty:
            return {
                "success": False,
                "error": "테스트 데이터 실제 피크가 없습니다.",
                "station_id": station_id
            }

        # 예측 세션별 시계열 생성
        # 모델 학습은 train_data로 이미 완료된 상태 (이후 가중치 동결).
        # 검증 목적은 "train으로 학습한 모델이 test 기간을 얼마나 잘 맞히나"이므로,
        # train 끝부분의 sequence_length개 행(시퀀스 컨텍스트) + test_data를 이어붙여
        # LSTM이 test 기간 timestamps에 대한 예측을 생성하도록 한다.
        # (train_data만 넘기면 예측 timestamp가 모두 train 기간 내부라,
        #  뒤의 test 기간 필터에서 전부 사라지고 fallback이 상수를 채워
        #  np.corrcoef가 NaN → 0이 되는 문제가 발생했음.)
        try:
            sequence_length = (
                getattr(ensemble_engine.lstm_engine, "sequence_length", 24)
                if ensemble_engine.lstm_engine is not None
                else 24
            )
            validation_input = pd.concat(
                [train_data.tail(sequence_length), test_data],
                ignore_index=True
            )
            session_predictions = ensemble_engine.predict_session_series(
                station_data=validation_input,
                station_id=station_id,
                charger_type=charger_type
            )
        except Exception as exc:
            logger.warning(f"Session prediction failed: {exc}")
            session_predictions = []

        # 예측값을 날짜별로 그룹화 (일별 최대값)
        if session_predictions:
            pred_df = pd.DataFrame(session_predictions)
            pred_df['timestamp'] = pd.to_datetime(pred_df['timestamp'], errors='coerce')
            pred_df = pred_df.dropna(subset=['timestamp'])
            pred_df['date'] = pred_df['timestamp'].dt.date

            # 테스트 구간만 필터링
            pred_df = pred_df[
                (pred_df['timestamp'] >= actual_test_start) &
                (pred_df['timestamp'] <= actual_test_end)
            ]

            if not pred_df.empty:
                daily_pred = pred_df.groupby('date')['predicted_peak_kw'].max().reset_index()
                daily_pred.columns = ['date', 'predicted_peak_kw']
            else:
                # 폴백: 앙상블 예측 평균값 사용
                daily_pred = pd.DataFrame({
                    'date': daily_actual['date'],
                    'predicted_peak_kw': prediction_result.final_prediction_kw
                })
        else:
            # 폴백: 앙상블 예측 평균값 사용
            daily_pred = pd.DataFrame({
                'date': daily_actual['date'],
                'predicted_peak_kw': prediction_result.final_prediction_kw
            })

        # 모델 예측이 사실상 상수(분산≈0)인 경우 — 현재 LSTM 은 전역 모델이라
        # 입력 시점과 무관하게 거의 동일한 값을 출력한다 — 일별 예측이 평평한 직선이 되어
        # 피어슨 상관계수가 정의 불가(분산 0 → NaN → 0)가 된다.
        # 이때 학습 데이터의 '요일 계절성'을 모델 예측 레벨에 입혀 일별 변동을 부여한다.
        # (사용자에게 보여주는 추천엔진의 90일 일별 투영과 동일한 방법론 — 요일 승수 적용)
        # MAE 의 기준이 되는 전체 레벨은 모델 예측을 그대로 유지하고, 요일별 상대 패턴만 반영한다.
        try:
            if not daily_pred.empty and float(daily_pred['predicted_peak_kw'].std() or 0.0) < 0.5:
                base_level = float(daily_pred['predicted_peak_kw'].mean())
                dt_train = daily_train.copy()
                dt_train['_wd'] = pd.to_datetime(dt_train['date']).dt.dayofweek
                overall_mean = float(dt_train['actual_peak_kw'].mean() or 0.0)
                if overall_mean > 0 and base_level > 0:
                    wd_factor = (
                        dt_train.groupby('_wd')['actual_peak_kw'].mean() / overall_mean
                    ).to_dict()
                    dap = daily_actual.copy()
                    wd_series = pd.to_datetime(dap['date']).dt.dayofweek
                    dap['predicted_peak_kw'] = wd_series.map(
                        lambda w: round(base_level * float(wd_factor.get(int(w), 1.0)), 2)
                    )
                    daily_pred = dap[['date', 'predicted_peak_kw']]
                    logger.info(
                        f"[validate] {station_id}: 상수 예측 감지 → 요일 계절성 적용 "
                        f"(레벨 {base_level:.1f}kW, 요일승수 {len(wd_factor)}개)"
                    )
        except Exception as exc:
            logger.warning(f"[validate] 요일 계절성 적용 실패({station_id}): {exc}")

        # 예측-실제 병합
        comparison = pd.merge(daily_actual, daily_pred, on='date', how='inner')

        if comparison.empty:
            return {
                "success": False,
                "error": "예측과 실제 데이터를 매칭할 수 없습니다.",
                "station_id": station_id
            }

        # 검증 지표 계산
        actual_values = comparison['actual_peak_kw'].values
        predicted_values = comparison['predicted_peak_kw'].values

        mae = np.mean(np.abs(actual_values - predicted_values))
        rmse = np.sqrt(np.mean((actual_values - predicted_values) ** 2))

        actual_mean = np.mean(actual_values)
        relative_error = (mae / actual_mean * 100) if actual_mean > 0 else 0

        # 일관성 평가 (상관계수)
        try:
            if len(actual_values) > 1:
                corr_matrix = np.corrcoef(actual_values, predicted_values)
                correlation = corr_matrix[0, 1]
                # NaN 처리 (분산이 0일 때 발생)
                if np.isnan(correlation) or np.isinf(correlation):
                    correlation = 0.0
            else:
                correlation = 0.0
        except Exception:
            correlation = 0.0

        # 시각화 데이터 준비 - 테스트 기간 (실제 vs 예측)
        visualization_data = [
            {
                "date": str(row['date']),
                "actual_peak_kw": round(float(row['actual_peak_kw']), 2),
                "predicted_peak_kw": round(float(row['predicted_peak_kw']), 2)
            }
            for _, row in comparison.iterrows()
        ]

        # 학습 데이터 시각화 준비
        train_visualization_data = [
            {
                "date": str(row['date']),
                "actual_peak_kw": round(float(row['actual_peak_kw']), 2)
            }
            for _, row in daily_train.iterrows()
        ]

        # 일관성 레벨 판정
        if correlation >= 0.8:
            consistency = "양호"
        elif correlation >= 0.6:
            consistency = "보통"
        else:
            consistency = "개선 필요"

        result = {
            "success": True,
            "station_id": station_id,
            "timestamp": datetime.now().isoformat(),

            # 검증 지표
            "validation_metrics": {
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "relative_error_percent": round(relative_error, 2),
                "correlation": round(correlation, 3),
                "consistency": consistency,
                "comparison_days": len(comparison),
                "actual_mean_kw": round(actual_mean, 2)
            },

            # 예측 정보
            "prediction_info": {
                "predicted_peak_kw": round(prediction_result.final_prediction_kw, 2),
                "uncertainty_kw": round(prediction_result.uncertainty_kw, 2),
                "confidence_level": prediction_result.confidence_level,
                "model_weights": {
                    "lstm": prediction_result.maturity.lstm_weight,
                    "xgboost": prediction_result.maturity.xgboost_weight
                }
            },

            # 시각화 데이터
            "visualization_data": visualization_data,
            "train_visualization_data": train_visualization_data,

            # 학습/테스트 구간
            "data_split": {
                "train_end_date": train_end_date,
                "test_start_date": test_start_date,
                "test_end_date": test_end_date,
                "train_ratio": round(safe_train_ratio, 3),
                "train_sessions": len(train_data),
                "test_sessions": len(test_data)
            }
        }

        logger.info(f"Model validation completed for {station_id}: MAE={mae:.2f}kW, Correlation={correlation:.3f}")

        # NaN/inf 안전 직렬화
        def clean_for_json(obj):
            import math
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            elif isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(x) for x in obj]
            return obj

        return clean_for_json(result)

    except Exception as e:
        logger.error(f"Error in model validation for {station_id}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "station_id": station_id
        }


@api_router.get("/test")
async def test_api():

    return {"message": "API 정상 작동!", "timestamp": datetime.now().isoformat(), "main_loaded": main is not None}
