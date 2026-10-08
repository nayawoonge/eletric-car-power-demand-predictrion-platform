import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class PredictionDatabase:
    def __init__(self, db_path: str = "data/predictions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._validate_db_file()
        self._init_database()
        self._verify_integrity()

    def _validate_db_file(self):
        """DB 파일이 손상되어 있으면(=SQLite 매직 바이트가 없거나 16 byte 미만) 즉시 삭제 후 재생성.
        이전에 1 byte 짜리 가짜 파일이 남아 모든 저장/조회가 silently 실패했던 사고를 재발 방지."""
        try:
            if self.db_path.exists():
                size = self.db_path.stat().st_size
                if size == 0:
                    logger.warning(f"DB 파일 크기 0 — 손상으로 판단, 삭제 후 재생성: {self.db_path}")
                    self.db_path.unlink()
                    return
                if size < 100:
                    # SQLite 헤더는 최소 100 byte. 그 이하면 정상 DB가 아님.
                    with open(self.db_path, "rb") as fh:
                        head = fh.read(16)
                    if head[:16] != b"SQLite format 3\x00":
                        logger.warning(
                            f"DB 파일이 SQLite 형식이 아님(크기 {size}B). 백업 후 재생성: {self.db_path}"
                        )
                        backup = self.db_path.with_suffix(".db.corrupt")
                        try:
                            self.db_path.replace(backup)
                            logger.warning(f"손상된 파일을 보존: {backup}")
                        except Exception:
                            try:
                                self.db_path.unlink()
                            except Exception:
                                pass
        except Exception as e:
            logger.error(f"DB 파일 검증 중 예외: {e}", exc_info=True)

    def _verify_integrity(self):
        """_init_database() 직후 호출. 모든 필수 테이블이 실제로 존재하는지 검증.
        하나라도 없으면 ERROR 로그 + RuntimeError — silent failure 방지."""
        required = {
            "prediction_results", "batch_progress", "prediction_runs",
            "daily_predictions", "monthly_predictions", "contract_scenarios",
            "endpoint_cache",
        }
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing = {row[0] for row in cur.fetchall()}
            missing = required - existing
            if missing:
                msg = f"필수 테이블 누락: {sorted(missing)} (db={self.db_path})"
                logger.error(msg)
                raise RuntimeError(msg)
            # 무결성 검사 — 손상된 페이지가 있으면 'ok' 외 다른 값 반환
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result and result[0] != "ok":
                    logger.error(f"DB 무결성 검사 실패: {result[0]}")
                else:
                    logger.info(f"DB 무결성 검사 통과 (tables={len(existing)}, path={self.db_path})")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"DB 무결성 검사 중 예외: {e}", exc_info=True)

    def _init_database(self):
        """데이터베이스 테이블 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL,
                    file_hash TEXT,
                    prediction_data TEXT NOT NULL,  -- JSON 형태로 저장
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(station_id, file_hash)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_hash TEXT UNIQUE NOT NULL,
                    total_stations INTEGER NOT NULL,
                    completed_stations INTEGER DEFAULT 0,
                    failed_stations INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'processing',  -- processing, completed, failed
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT
                )
            """)

            # ============================================================
            # 외부 웹앱 공유용 정규화 스키마
            # ------------------------------------------------------------
            # prediction_runs    : 1 row = 1 예측 실행 (요약 카드 값)
            # daily_predictions  : 일별 P50/P95 시계열
            # monthly_predictions: 월별 집계 (일별에서 파생)
            # contract_scenarios : 후보 계약별 시나리오 표 행
            # ============================================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    model_version TEXT,
                    charger_type TEXT,
                    maturity_level TEXT,
                    session_count INTEGER,

                    current_contract_kw REAL,
                    recommended_contract_kw REAL,

                    ensemble_p95_kw REAL,
                    ensemble_uncertainty_kw REAL,
                    confidence_level REAL,

                    predicted_peak_p50 REAL,
                    predicted_peak_p95 REAL,

                    annual_savings_krw REAL,
                    savings_percent REAL,
                    overage_probability REAL,
                    waste_probability REAL,
                    urgency_level TEXT,
                    recommendation_summary TEXT,

                    is_latest INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_predictions (
                    run_id INTEGER NOT NULL,
                    prediction_date TEXT NOT NULL,
                    p10 REAL,
                    p50 REAL,
                    p90 REAL,
                    p95 REAL,
                    PRIMARY KEY (run_id, prediction_date),
                    FOREIGN KEY (run_id) REFERENCES prediction_runs(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS monthly_predictions (
                    run_id INTEGER NOT NULL,
                    year_month TEXT NOT NULL,  -- 'YYYY-MM'
                    peak_p50 REAL,
                    peak_p95 REAL,
                    p10_avg REAL,
                    p90_avg REAL,
                    day_count INTEGER,
                    is_max_month INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (run_id, year_month),
                    FOREIGN KEY (run_id) REFERENCES prediction_runs(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS contract_scenarios (
                    run_id INTEGER NOT NULL,
                    contract_kw REAL NOT NULL,
                    scenario_label TEXT,
                    expected_annual_cost REAL,
                    monthly_basic_fee REAL,
                    overage_probability REAL,
                    waste_probability REAL,
                    risk_score REAL,
                    is_recommended INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (run_id, contract_kw),
                    FOREIGN KEY (run_id) REFERENCES prediction_runs(id) ON DELETE CASCADE
                )
            """)

            # 보조 엔드포인트 응답 캐시 (station-analysis, prediction, monthly-contract 등).
            # 키는 (station_id, endpoint_name). 페이지 로드 시 CSV 재계산을 피하기 위해 사용한다.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS endpoint_cache (
                    station_id TEXT NOT NULL,
                    endpoint_name TEXT NOT NULL,
                    cache_key TEXT NOT NULL DEFAULT '',
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (station_id, endpoint_name, cache_key)
                )
            """)

            # 인덱스 생성
            conn.execute("CREATE INDEX IF NOT EXISTS idx_station_file ON prediction_results(station_id, file_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_endpoint_cache ON endpoint_cache(station_id, endpoint_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON batch_progress(file_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_station_run_at ON prediction_runs(station_id, run_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_station_latest ON prediction_runs(station_id, is_latest)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_run ON daily_predictions(run_id, prediction_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_monthly_run ON monthly_predictions(run_id, year_month)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenario_run ON contract_scenarios(run_id, contract_kw)")

            conn.commit()

    def count_predictions(self) -> int:
        """저장된 예측 결과 행 수 (prediction_results 기준). 앱 시작 시 '예측 없음' 판별용."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                return int(conn.execute("SELECT COUNT(*) FROM prediction_results").fetchone()[0])
        except Exception as e:
            logger.warning(f"count_predictions 실패: {e}")
            return 0

    def clear_all(self) -> bool:
        """모든 예측 결과/캐시 데이터를 삭제한다 (스키마는 유지).

        CSV 재업로드 시 이전 데이터로 만든 예측이 DB에 남아 계속 로드되는
        stale 문제를 원천 차단하기 위해 사용. 충전소 목록이 바뀌어도(이전 데이터에만
        있던 충전소 포함) 전부 비워지므로 재실행 후에는 새 데이터 예측만 남는다.
        """
        tables = [
            "prediction_runs",      # 자식(daily/monthly/contract_scenarios)은 CASCADE
            "prediction_results",
            "daily_predictions",
            "monthly_predictions",
            "contract_scenarios",
            "endpoint_cache",
            "batch_progress",
        ]
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                cur = conn.cursor()
                for t in tables:
                    cur.execute(f"DELETE FROM {t}")
                conn.commit()
            logger.info("clear_all: 모든 예측/캐시 테이블을 비웠습니다.")
            return True
        except Exception as e:
            logger.error(f"clear_all 실패: {e}")
            return False

    def save_endpoint_cache(
        self,
        station_id: str,
        endpoint_name: str,
        response: Dict[str, Any],
        cache_key: str = "",
    ) -> bool:
        """보조 엔드포인트(station-analysis, prediction, monthly-contract 등) 응답을
        (station_id, endpoint_name, cache_key) 키로 upsert 저장."""
        now = datetime.now().isoformat()
        try:
            payload = json.dumps(response, default=str)
        except Exception as e:
            logger.error(
                f"[EndpointCacheSave] JSON 직렬화 실패 station={station_id} endpoint={endpoint_name}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO endpoint_cache
                        (station_id, endpoint_name, cache_key, response_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(station_id, endpoint_name, cache_key)
                    DO UPDATE SET response_json = excluded.response_json,
                                  updated_at = excluded.updated_at
                """, (station_id, endpoint_name, cache_key, payload, now, now))
                conn.commit()
            logger.debug(f"[EndpointCacheSave] OK station={station_id} endpoint={endpoint_name} bytes={len(payload)}")
            return True
        except Exception as e:
            logger.error(
                f"[EndpointCacheSave] SQLite 저장 실패 station={station_id} endpoint={endpoint_name}: "
                f"{type(e).__name__}: {e} (db={self.db_path})",
                exc_info=True,
            )
            return False

    def load_endpoint_cache(
        self,
        station_id: str,
        endpoint_name: str,
        cache_key: str = "",
    ) -> Optional[Dict[str, Any]]:
        """저장된 보조 엔드포인트 응답 로드. 미스면 None."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT response_json, updated_at FROM endpoint_cache
                    WHERE station_id = ? AND endpoint_name = ? AND cache_key = ?
                """, (station_id, endpoint_name, cache_key))
                row = cursor.fetchone()
                if row:
                    data = json.loads(row["response_json"])
                    if isinstance(data, dict):
                        data["_cached_at"] = row["updated_at"]
                    return data
            return None
        except Exception as e:
            logger.error(f"Failed to load endpoint cache for {station_id}/{endpoint_name}: {e}")
            return None

    def save_prediction(self, station_id: str, prediction_data: Dict[str, Any],
                       file_hash: str = None) -> bool:
        """예측 결과 저장 — JSON 직렬화 실패와 SQLite 오류를 분리해서 상세 로그."""
        now = datetime.now().isoformat()
        # 1) JSON 직렬화 — 실패 시 어떤 필드 때문인지 즉시 파악
        try:
            payload = json.dumps(prediction_data, default=str)
        except Exception as e:
            logger.error(
                f"[CacheSave] JSON 직렬화 실패 station={station_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            return False

        # 2) SQLite 저장
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO prediction_results
                    (station_id, file_hash, prediction_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (station_id, file_hash, payload, now, now))
                conn.commit()
            logger.debug(f"[CacheSave] OK station={station_id} bytes={len(payload)}")
            return True
        except Exception as e:
            logger.error(
                f"[CacheSave] SQLite 저장 실패 station={station_id}: {type(e).__name__}: {e} "
                f"(db={self.db_path})",
                exc_info=True,
            )
            return False
    
    def load_prediction(self, station_id: str, file_hash: str = None) -> Optional[Dict[str, Any]]:
        """저장된 예측 결과 로드"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT prediction_data, created_at FROM prediction_results 
                    WHERE station_id = ? AND (file_hash = ? OR file_hash IS NULL)
                    ORDER BY updated_at DESC LIMIT 1
                """, (station_id, file_hash))
                
                row = cursor.fetchone()
                if row:
                    data = json.loads(row['prediction_data'])
                    data['_cached_at'] = row['created_at']
                    return data
            return None
        except Exception as e:
            logger.error(f"Failed to load prediction for {station_id}: {e}")
            return None
    
    def get_all_predictions(self, file_hash: str = None) -> List[Dict[str, Any]]:
        """파일별 모든 예측 결과 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT station_id, prediction_data, created_at FROM prediction_results 
                    WHERE file_hash = ?
                    ORDER BY station_id
                """, (file_hash,))
                
                results = []
                for row in cursor.fetchall():
                    data = json.loads(row['prediction_data'])
                    data['station_id'] = row['station_id']
                    data['_cached_at'] = row['created_at']
                    results.append(data)
                
                return results
        except Exception as e:
            logger.error(f"Failed to get predictions for file {file_hash}: {e}")
            return []
    
    def create_batch_progress(self, file_hash: str, total_stations: int) -> bool:
        """배치 처리 진행상황 생성"""
        try:
            now = datetime.now().isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO batch_progress 
                    (file_hash, total_stations, started_at, status)
                    VALUES (?, ?, ?, 'processing')
                """, (file_hash, total_stations, now))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create batch progress for {file_hash}: {e}")
            return False
    
    def update_batch_progress(self, file_hash: str, completed: int = None, 
                            failed: int = None, status: str = None) -> bool:
        """배치 처리 진행상황 업데이트"""
        try:
            updates = []
            params = []
            
            if completed is not None:
                updates.append("completed_stations = ?")
                params.append(completed)
            
            if failed is not None:
                updates.append("failed_stations = ?")
                params.append(failed)
                
            if status is not None:
                updates.append("status = ?")
                params.append(status)
                if status == 'completed':
                    updates.append("completed_at = ?")
                    params.append(datetime.now().isoformat())
            
            if updates:
                params.append(file_hash)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(f"""
                        UPDATE batch_progress 
                        SET {', '.join(updates)}
                        WHERE file_hash = ?
                    """, params)
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update batch progress for {file_hash}: {e}")
            return False
    
    def get_batch_progress(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """배치 처리 진행상황 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM batch_progress WHERE file_hash = ?
                """, (file_hash,))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
            return None
        except Exception as e:
            logger.error(f"Failed to get batch progress for {file_hash}: {e}")
            return None
    
    # ====================================================================
    # 정규화 스키마용 메서드 (외부 웹앱 공유)
    # ====================================================================

    def save_normalized_prediction(
        self,
        station_id: str,
        ensemble_response: Dict[str, Any]
    ) -> Optional[int]:
        """
        /api/stations/{id}/ensemble-prediction 응답을 4개 정규화 테이블로 분해 저장.

        Returns:
            새로 생성된 run_id (실패 시 None)
        """
        try:
            now = datetime.now().isoformat()

            ens = ensemble_response.get("ensemble_prediction", {}) or {}
            contract = ensemble_response.get("contract_recommendation", {}) or {}
            meta = ensemble_response.get("metadata", {}) or {}
            maturity = ens.get("maturity", {}) or {}
            risk = contract.get("risk_assessment", {}) or {}

            recommended_kw = contract.get("recommended_contract_kw")
            opt_details = contract.get("optimization_details") or {}
            candidates = opt_details.get("all_candidates") or contract.get("candidate_analysis_data") or []
            session_pred_series = opt_details.get("session_prediction_series") or []

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # ON DELETE CASCADE가 자식 테이블(daily/monthly/contract_scenarios)을
                # 자동으로 비우려면 SQLite에서는 연결 단위로 외래키 제약을 켜야 함.
                conn.execute("PRAGMA foreign_keys = ON")
                cur = conn.cursor()

                # 1) 이 충전소의 모든 이전 run 을 삭제 (자식 테이블도 CASCADE로 함께 정리).
                #    이로써 station_id 당 prediction_runs 행은 항상 1개로 유지되고,
                #    예측을 반복 실행해도 DB가 누적되지 않는다.
                cur.execute(
                    "DELETE FROM prediction_runs WHERE station_id = ?",
                    (station_id,)
                )

                # 2) prediction_runs 새 행 삽입
                cur.execute("""
                    INSERT INTO prediction_runs (
                        station_id, run_at, model_version, charger_type,
                        maturity_level, session_count,
                        current_contract_kw, recommended_contract_kw,
                        ensemble_p95_kw, ensemble_uncertainty_kw, confidence_level,
                        predicted_peak_p50, predicted_peak_p95,
                        annual_savings_krw, savings_percent,
                        overage_probability, waste_probability, urgency_level,
                        recommendation_summary,
                        is_latest, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                """, (
                    station_id,
                    ensemble_response.get("timestamp") or now,
                    meta.get("model_version"),
                    meta.get("charger_type"),
                    maturity.get("level"),
                    maturity.get("session_count"),
                    contract.get("current_contract_kw"),
                    recommended_kw,
                    ens.get("final_prediction_kw"),
                    ens.get("uncertainty_kw"),
                    ens.get("confidence_level"),
                    contract.get("predicted_peak_p50"),
                    contract.get("predicted_peak_p95"),
                    contract.get("annual_savings_won") or contract.get("expected_annual_savings"),
                    contract.get("savings_percentage") or contract.get("savings_percent"),
                    risk.get("overage_probability") or contract.get("overage_probability"),
                    risk.get("waste_probability") or contract.get("waste_probability"),
                    risk.get("risk_level") or contract.get("urgency_level"),
                    contract.get("recommendation") or contract.get("recommendation_summary"),
                    now,
                ))
                run_id = cur.lastrowid

                # 3) daily_predictions — session 시계열을 날짜별로 집계
                daily_rows = self._aggregate_daily(session_pred_series)
                if daily_rows:
                    cur.executemany("""
                        INSERT OR REPLACE INTO daily_predictions
                            (run_id, prediction_date, p10, p50, p90, p95)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, [
                        (run_id, d["date"], d.get("p10"), d.get("p50"), d.get("p90"), d.get("p95"))
                        for d in daily_rows
                    ])

                # 4) monthly_predictions — 일별 집계 위에서 월별 집계
                monthly_rows = self._aggregate_monthly(daily_rows)
                if monthly_rows:
                    cur.executemany("""
                        INSERT OR REPLACE INTO monthly_predictions
                            (run_id, year_month, peak_p50, peak_p95,
                             p10_avg, p90_avg, day_count, is_max_month)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        (run_id, m["year_month"], m["peak_p50"], m["peak_p95"],
                         m["p10_avg"], m["p90_avg"], m["day_count"], m["is_max_month"])
                        for m in monthly_rows
                    ])

                # 5) contract_scenarios — 후보 계약별 시나리오
                if candidates:
                    cur.executemany("""
                        INSERT OR REPLACE INTO contract_scenarios
                            (run_id, contract_kw, scenario_label,
                             expected_annual_cost, monthly_basic_fee,
                             overage_probability, waste_probability,
                             risk_score, is_recommended)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        (
                            run_id,
                            float(c.get("contract_kw")) if c.get("contract_kw") is not None else None,
                            self._scenario_label(c.get("contract_kw"), recommended_kw),
                            c.get("expected_annual_cost") or c.get("annual_cost"),
                            (float(c.get("contract_kw")) * 8320) if c.get("contract_kw") is not None else None,
                            c.get("overage_probability"),
                            c.get("waste_probability"),
                            c.get("risk_score"),
                            1 if (recommended_kw is not None
                                  and c.get("contract_kw") is not None
                                  and float(c.get("contract_kw")) == float(recommended_kw)) else 0,
                        )
                        for c in candidates
                    ])

                conn.commit()
                logger.info(f"Saved normalized prediction run_id={run_id} for {station_id}")
                return run_id

        except Exception as e:
            logger.error(f"save_normalized_prediction failed for {station_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def _scenario_label(contract_kw, recommended_kw) -> str:
        if contract_kw is None or recommended_kw is None:
            return "기타"
        c = float(contract_kw)
        r = float(recommended_kw)
        if abs(c - r) < 1e-6:
            return "최적"
        return "과소" if c < r else "과다"

    @staticmethod
    def _aggregate_daily(session_pred_series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """세션 단위 예측 시계열 → 날짜별 P10/P50/P90/P95."""
        if not session_pred_series:
            return []
        try:
            import statistics
            from collections import defaultdict

            by_date: Dict[str, List[float]] = defaultdict(list)
            for row in session_pred_series:
                ts = row.get("timestamp") or row.get("date")
                if not ts:
                    continue
                date_part = str(ts)[:10]
                value = row.get("predicted_peak_kw") or row.get("peak_kw")
                if value is None:
                    continue
                try:
                    by_date[date_part].append(float(value))
                except (TypeError, ValueError):
                    continue

            out: List[Dict[str, Any]] = []
            for date_str in sorted(by_date.keys()):
                vals = sorted(by_date[date_str])
                if not vals:
                    continue
                p50 = statistics.median(vals)
                p10 = vals[max(0, int(len(vals) * 0.10) - 1)] if len(vals) > 1 else vals[0]
                p90 = vals[min(len(vals) - 1, int(len(vals) * 0.90))]
                p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
                out.append({
                    "date": date_str,
                    "p10": round(p10, 2),
                    "p50": round(p50, 2),
                    "p90": round(p90, 2),
                    "p95": round(p95, 2),
                })
            return out
        except Exception as e:
            logger.warning(f"_aggregate_daily failed: {e}")
            return []

    @staticmethod
    def _aggregate_monthly(daily_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """일별 → 월별 (peak_p50 = 그 달 일별 P50 최댓값)."""
        if not daily_rows:
            return []
        try:
            from collections import defaultdict

            buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for d in daily_rows:
                ym = d["date"][:7]
                buckets[ym].append(d)

            monthly: List[Dict[str, Any]] = []
            for ym in sorted(buckets.keys()):
                rows = buckets[ym]
                p50s = [r["p50"] for r in rows if r.get("p50") is not None]
                p95s = [r["p95"] for r in rows if r.get("p95") is not None]
                p10s = [r["p10"] for r in rows if r.get("p10") is not None]
                p90s = [r["p90"] for r in rows if r.get("p90") is not None]
                monthly.append({
                    "year_month": ym,
                    "peak_p50": round(max(p50s), 2) if p50s else None,
                    "peak_p95": round(max(p95s), 2) if p95s else None,
                    "p10_avg": round(sum(p10s) / len(p10s), 2) if p10s else None,
                    "p90_avg": round(sum(p90s) / len(p90s), 2) if p90s else None,
                    "day_count": len(rows),
                    "is_max_month": 0,
                })

            # is_max_month 표시
            if monthly:
                best = max(monthly, key=lambda m: m["peak_p50"] or 0)
                best["is_max_month"] = 1

            return monthly
        except Exception as e:
            logger.warning(f"_aggregate_monthly failed: {e}")
            return []

    # ------ 조회 (외부 API 용) ------

    def get_latest_run(self, station_id: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM prediction_runs WHERE station_id = ? AND is_latest = 1 "
                    "ORDER BY run_at DESC LIMIT 1",
                    (station_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_latest_run failed: {e}")
            return None

    def list_stations_with_predictions(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT station_id, MAX(run_at) AS latest_run_at, COUNT(*) AS run_count "
                    "FROM prediction_runs GROUP BY station_id ORDER BY station_id"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"list_stations_with_predictions failed: {e}")
            return []

    def get_daily_predictions(
        self,
        station_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            sql = (
                "SELECT d.prediction_date, d.p10, d.p50, d.p90, d.p95 "
                "FROM daily_predictions d "
                "JOIN prediction_runs r ON r.id = d.run_id "
                "WHERE r.station_id = ? AND r.is_latest = 1"
            )
            params: List[Any] = [station_id]
            if date_from:
                sql += " AND d.prediction_date >= ?"
                params.append(date_from)
            if date_to:
                sql += " AND d.prediction_date <= ?"
                params.append(date_to)
            sql += " ORDER BY d.prediction_date"
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception as e:
            logger.error(f"get_daily_predictions failed: {e}")
            return []

    def get_monthly_predictions(self, station_id: str) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT m.year_month, m.peak_p50, m.peak_p95, m.p10_avg, m.p90_avg, "
                    "       m.day_count, m.is_max_month "
                    "FROM monthly_predictions m "
                    "JOIN prediction_runs r ON r.id = m.run_id "
                    "WHERE r.station_id = ? AND r.is_latest = 1 "
                    "ORDER BY m.year_month",
                    (station_id,)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_monthly_predictions failed: {e}")
            return []

    def get_scenarios(self, station_id: str) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT s.contract_kw, s.scenario_label, s.expected_annual_cost, "
                    "       s.monthly_basic_fee, s.overage_probability, s.waste_probability, "
                    "       s.risk_score, s.is_recommended "
                    "FROM contract_scenarios s "
                    "JOIN prediction_runs r ON r.id = s.run_id "
                    "WHERE r.station_id = ? AND r.is_latest = 1 "
                    "ORDER BY s.contract_kw",
                    (station_id,)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_scenarios failed: {e}")
            return []

    def cleanup_old_predictions(self, days_old: int = 30) -> int:
        """오래된 예측 결과 정리"""
        try:
            cutoff_date = datetime.now()
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_old)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM prediction_results 
                    WHERE created_at < ?
                """, (cutoff_date.isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleaned up {deleted_count} old prediction records")
                return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup old predictions: {e}")
            return 0