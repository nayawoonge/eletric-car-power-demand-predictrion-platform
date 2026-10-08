from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from typing import Dict, Any
import tempfile
import os
import logging

from ..prediction.services import BatchPredictionProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

# 배치 처리기 인스턴스
batch_processor = BatchPredictionProcessor()

@router.post("/batch/start")
async def start_batch_prediction(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    """
    파일 업로드와 함께 배치 예측 시작
    """
    try:
        # 임시 파일에 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # 배치 예측 시작
            result = await batch_processor.start_batch_prediction(
                temp_file_path, 
                content
            )
            
            return result
            
        finally:
            # 임시 파일 정리
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
    except Exception as e:
        logger.error(f"Batch start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batch/progress/{file_hash}")
async def get_batch_progress(file_hash: str) -> Dict[str, Any]:
    """
    배치 처리 진행 상황 조회
    """
    try:
        result = batch_processor.get_progress(file_hash)
        
        if not result.get("success", False):
            raise HTTPException(status_code=404, detail=result.get("error", "Progress not found"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get progress failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stations/{station_id}/prediction/cached")
async def get_cached_prediction(station_id: str, file_hash: str = None) -> Dict[str, Any]:
    """
    캐시된 예측 결과 조회
    """
    try:
        cached_result = batch_processor.storage.load_prediction(station_id, file_hash)
        
        if cached_result:
            return cached_result
        else:
            raise HTTPException(
                status_code=404, 
                detail=f"Cached prediction not found for station {station_id}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get cached prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/batch/clear")
async def clear_all_data() -> Dict[str, Any]:
    """
    모든 예측 데이터와 업로드 파일 삭제
    """
    try:
        result = batch_processor.clear_all_data()
        
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Clear failed"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clear all data failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batch/status")
async def get_batch_status() -> Dict[str, Any]:
    """
    전체 배치 처리 상태 조회
    """
    try:
        active_processes = len(batch_processor.active_processes)
        storage_stats = batch_processor.storage.get_storage_stats()
        
        return {
            "success": True,
            "active_processes": active_processes,
            "storage_stats": storage_stats
        }
        
    except Exception as e:
        logger.error(f"Get batch status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))