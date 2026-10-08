import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import hashlib
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..engine import PredictionEngine
from ...storage import StorageManager
from ...data.loader import ChargingDataLoader

logger = logging.getLogger(__name__)

class BatchPredictionProcessor:
    """배치 예측 처리 서비스"""
    
    def __init__(self, max_workers: int = 4):
        self.prediction_engine = PredictionEngine()
        self.storage = StorageManager()
        self.max_workers = max_workers
        self.active_processes = {}  # file_hash -> ProcessInfo
        
    async def start_batch_prediction(self, file_path: str, file_content: bytes = None) -> Dict[str, Any]:
        """
        파일 업로드 시 모든 충전소에 대해 배치 예측 시작
        
        Args:
            file_path: 업로드된 파일 경로
            file_content: 파일 내용 (해시 생성용)
        
        Returns:
            배치 처리 시작 정보
        """
        try:
            # 파일 해시 생성
            if file_content is None:
                with open(file_path, 'rb') as f:
                    file_content = f.read()
            
            file_hash = self.storage.generate_file_hash(file_content)
            
            # 충전소 목록 추출
            stations = await self._extract_stations_from_file(file_path)
            
            if not stations:
                return {
                    "success": False,
                    "error": "충전소를 찾을 수 없습니다.",
                    "file_hash": file_hash
                }
            
            total_stations = len(stations)
            
            # 배치 처리 시작 기록
            self.storage.start_batch_processing(file_hash, total_stations)
            
            # 프로세스 정보 저장
            self.active_processes[file_hash] = {
                "total": total_stations,
                "completed": 0,
                "failed": 0,
                "started_at": datetime.now(),
                "status": "processing",
                "stations": stations
            }
            
            # 백그라운드에서 배치 처리 시작
            asyncio.create_task(self._process_batch_async(file_hash, file_path, stations))
            
            logger.info(f"Started batch prediction for {total_stations} stations (file: {file_hash})")
            
            return {
                "success": True,
                "file_hash": file_hash,
                "total_stations": total_stations,
                "message": f"{total_stations}개 충전소에 대한 배치 예측이 시작되었습니다.",
                "estimated_time_minutes": total_stations * 0.5  # 충전소당 약 30초 추정
            }
            
        except Exception as e:
            logger.error(f"Failed to start batch prediction: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _extract_stations_from_file(self, file_path: str) -> List[str]:
        """파일에서 충전소 목록 추출"""
        try:
            loader = ChargingDataLoader("ALL")
            
            # CSV 파일 로드
            if file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8-sig', nrows=1000)  # 샘플만 로드
            else:
                raise ValueError("지원하지 않는 파일 형식")
            
            # 충전소 ID 컬럼 찾기
            station_id_cols = ["충전소ID", "station_id", "충전소명", "STATION_ID"]
            station_col = None
            
            for col in station_id_cols:
                if col in df.columns:
                    station_col = col
                    break
            
            if not station_col:
                logger.warning("충전소 ID 컬럼을 찾을 수 없습니다.")
                return []
            
            # 고유 충전소 목록 추출
            unique_stations = df[station_col].dropna().unique().tolist()
            
            # 상위 50개 충전소로 제한 (성능상 이유)
            if len(unique_stations) > 50:
                # 데이터가 많은 충전소 우선 선택
                station_counts = df[station_col].value_counts()
                unique_stations = station_counts.head(50).index.tolist()
            
            logger.info(f"Extracted {len(unique_stations)} stations from file")
            return [str(station) for station in unique_stations]
            
        except Exception as e:
            logger.error(f"Failed to extract stations: {e}")
            return []
    
    async def _process_batch_async(self, file_hash: str, file_path: str, stations: List[str]):
        """비동기적으로 배치 처리 실행"""
        try:
            completed = 0
            failed = 0
            
            # ThreadPoolExecutor로 병렬 처리
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 각 충전소에 대한 예측 태스크 생성
                future_to_station = {
                    executor.submit(self._predict_single_station, station_id, file_hash): station_id
                    for station_id in stations
                }
                
                # 완료된 태스크들을 순차적으로 처리
                for future in as_completed(future_to_station, timeout=300):  # 5분 타임아웃
                    station_id = future_to_station[future]
                    try:
                        result = future.result()
                        if result and result.get('success', False):
                            completed += 1
                            logger.debug(f"Completed prediction for station {station_id}")
                        else:
                            failed += 1
                            logger.warning(f"Failed prediction for station {station_id}")
                    except Exception as e:
                        failed += 1
                        logger.error(f"Exception in prediction for station {station_id}: {e}")
                    
                    # 진행 상황 업데이트
                    self._update_progress(file_hash, completed, failed)
            
            # 최종 상태 업데이트
            final_status = "completed" if failed == 0 else "partial_success" if completed > 0 else "failed"
            self._update_progress(file_hash, completed, failed, final_status)
            
            logger.info(f"Batch prediction completed: {completed} success, {failed} failed (file: {file_hash})")
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}", exc_info=True)
            self._update_progress(file_hash, completed, failed, "error")
    
    def _predict_single_station(self, station_id: str, file_hash: str) -> Dict[str, Any]:
        """단일 충전소에 대한 예측 수행"""
        try:
            # 기존 캐시 확인
            cached_result = self.storage.load_prediction(station_id, file_hash)
            if cached_result:
                logger.debug(f"Using cached prediction for station {station_id}")
                return {"success": True, "cached": True}
            
            # ChargingDataLoader로 데이터 로드
            loader = ChargingDataLoader(station_id)
            df = loader.load_historical_sessions(days=365)
            
            if df.empty:
                logger.warning(f"No data found for station {station_id}")
                return {"success": False, "error": "No data"}
            
            # 충전기 타입 확인
            charger_type = self._determine_charger_type(df)
            
            # 예측 수행
            prediction_result = self.prediction_engine.predict_contract_power(
                df, station_id, charger_type
            )
            
            # 결과를 API 형식으로 변환
            api_result = self._convert_to_api_format(prediction_result, station_id)
            
            # 저장
            success = self.storage.save_prediction(station_id, api_result, file_hash)
            
            if success:
                logger.debug(f"Saved prediction for station {station_id}")
                return {"success": True, "predicted": True}
            else:
                return {"success": False, "error": "Save failed"}
                
        except Exception as e:
            logger.error(f"Prediction failed for station {station_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def _determine_charger_type(self, df: pd.DataFrame) -> str:
        """충전기 타입 결정"""
        try:
            power_cols = ["순간최고전력", "max_power", "전력"]
            
            for col in power_cols:
                if col in df.columns:
                    power_data = df[col].dropna()
                    if len(power_data) > 0:
                        max_power = power_data.max()
                        mean_power = power_data.mean()
                        
                        if max_power >= 30 and mean_power >= 15:
                            return "급속충전기 (DC)"
                        else:
                            return "완속충전기 (AC)"
            
            return "미상"
        except Exception:
            return "미상"
    
    def _convert_to_api_format(self, prediction_result, station_id: str) -> Dict[str, Any]:
        """PredictionEngine 결과를 API 형식으로 변환"""
        try:
            # EnsemblePrediction을 API 응답 형식으로 변환
            from ..engine import EnsemblePrediction
            
            if not isinstance(prediction_result, EnsemblePrediction):
                # Fallback 형식 처리
                return {
                    "success": True,
                    "station_id": station_id,
                    "predicted_peak": 50.0,
                    "confidence": 0.5,
                    "method": "fallback"
                }
            
            # 실제 결과 변환
            result = {
                "success": True,
                "station_id": station_id,
                "predicted_peak": prediction_result.raw_prediction,
                "confidence": min([pred.confidence_score for pred in prediction_result.model_predictions]) if prediction_result.model_predictions else 0.5,
                "recommended_contract_kw": prediction_result.final_prediction,
                "algorithm_prediction_kw": prediction_result.raw_prediction,
                "method": prediction_result.ensemble_method,
                "timestamp": datetime.now().isoformat(),
                "advanced_model_prediction": {
                    "final_prediction": prediction_result.final_prediction,
                    "raw_prediction": prediction_result.raw_prediction,
                    "ensemble_method": prediction_result.ensemble_method,
                    "model_count": len(prediction_result.model_predictions),
                    "uncertainty": prediction_result.uncertainty,
                    "model_weights": prediction_result.weights,
                }
            }
            
            # Pattern factors 추가
            if prediction_result.pattern_factors:
                result["pattern_analysis"] = {
                    "confidence": prediction_result.pattern_factors.confidence,
                    "data_quality": prediction_result.pattern_factors.data_quality,
                    "analysis_method": "dynamic_pattern_analysis"
                }
            
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to convert prediction result: {e}")
            return {
                "success": False,
                "error": str(e),
                "station_id": station_id
            }
    
    def _update_progress(self, file_hash: str, completed: int, failed: int, status: str = None):
        """진행 상황 업데이트"""
        try:
            # 메모리 상태 업데이트
            if file_hash in self.active_processes:
                self.active_processes[file_hash]["completed"] = completed
                self.active_processes[file_hash]["failed"] = failed
                if status:
                    self.active_processes[file_hash]["status"] = status
                    if status in ["completed", "partial_success", "failed", "error"]:
                        self.active_processes[file_hash]["completed_at"] = datetime.now()
            
            # 저장소 업데이트
            self.storage.update_batch_progress(file_hash, completed, failed, status)
            
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
    
    def get_progress(self, file_hash: str) -> Dict[str, Any]:
        """배치 처리 진행 상황 조회"""
        try:
            # 메모리에서 먼저 확인
            if file_hash in self.active_processes:
                process_info = self.active_processes[file_hash]
                return {
                    "success": True,
                    "file_hash": file_hash,
                    "total": process_info["total"],
                    "completed": process_info["completed"],
                    "failed": process_info["failed"],
                    "status": process_info["status"],
                    "percentage": (process_info["completed"] + process_info["failed"]) / process_info["total"] * 100 if process_info["total"] > 0 else 0,
                    "started_at": process_info["started_at"].isoformat(),
                    "completed_at": process_info.get("completed_at").isoformat() if process_info.get("completed_at") else None
                }
            
            # 저장소에서 확인
            stored_progress = self.storage.get_batch_progress(file_hash)
            if stored_progress:
                total = stored_progress["total_stations"]
                completed = stored_progress["completed_stations"]
                failed = stored_progress["failed_stations"]
                
                return {
                    "success": True,
                    "file_hash": file_hash,
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "status": stored_progress["status"],
                    "percentage": (completed + failed) / total * 100 if total > 0 else 0,
                    "started_at": stored_progress["started_at"],
                    "completed_at": stored_progress.get("completed_at")
                }
            
            return {
                "success": False,
                "error": "배치 처리 정보를 찾을 수 없습니다."
            }
            
        except Exception as e:
            logger.error(f"Failed to get progress: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def clear_all_data(self) -> Dict[str, Any]:
        """모든 예측 데이터와 업로드 파일 삭제"""
        try:
            # 활성 프로세스 정리
            self.active_processes.clear()
            
            # 저장소 데이터 정리
            cleanup_stats = self.storage.cleanup_old_data(days_old=0)  # 모든 데이터 삭제
            
            # 업로드 파일 삭제 (data 디렉토리)
            upload_files_deleted = self._clear_upload_files()
            
            total_cleared = cleanup_stats.get("database_cleaned", 0) + cleanup_stats.get("files_cleaned", 0) + upload_files_deleted
            
            logger.info(f"Cleared all data: {total_cleared} items deleted")
            
            return {
                "success": True,
                "message": "모든 데이터가 삭제되었습니다.",
                "details": {
                    "database_cleared": cleanup_stats.get("database_cleaned", 0),
                    "prediction_files_cleared": cleanup_stats.get("files_cleaned", 0),
                    "upload_files_cleared": upload_files_deleted,
                    "total_cleared": total_cleared
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to clear all data: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _clear_upload_files(self) -> int:
        """업로드 파일들 삭제"""
        try:
            upload_dirs = [
                Path("data/uploads"),
                Path("uploads"),
                Path("temp"),
            ]
            
            deleted_count = 0
            for upload_dir in upload_dirs:
                if upload_dir.exists():
                    for file_path in upload_dir.rglob("*"):
                        if file_path.is_file():
                            file_path.unlink()
                            deleted_count += 1
                    
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to clear upload files: {e}")
            return 0