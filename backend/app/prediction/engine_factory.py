"""
예측 엔진 팩토리 - 싱글톤 패턴으로 모델 재사용

웹 앱에서 모델 로딩 시간을 최소화하기 위한 팩토리
"""

import logging
from typing import Optional
from pathlib import Path

from .lstm_prediction_engine import LSTMPredictionEngine
from .prediction_engine import PredictionEngine
from .ensemble_prediction_engine import EnsemblePredictionEngine

logger = logging.getLogger(__name__)


class PredictionEngineFactory:
    """
    예측 엔진 싱글톤 팩토리

    모델을 한 번만 로드하고 재사용하여 로딩 시간 최소화
    """

    _lstm_engine: Optional[LSTMPredictionEngine] = None
    _traditional_engine: Optional[PredictionEngine] = None
    _ensemble_engine: Optional[EnsemblePredictionEngine] = None
    _use_lstm: bool = False
    _use_ensemble: bool = False
    _model_path: Optional[str] = None

    @classmethod
    def initialize(cls, use_lstm: bool = False, use_ensemble: bool = False, model_path: str = "models/lstm_model"):
        """
        팩토리 초기화 (앱 시작 시 한 번만 호출)

        Args:
            use_lstm: LSTM 모델 사용 여부
            use_ensemble: 앙상블 모델 사용 여부 (LSTM + XGBoost)
            model_path: LSTM 모델 경로
        """
        cls._use_lstm = use_lstm
        cls._use_ensemble = use_ensemble
        cls._model_path = model_path

        # 앙상블 모드 (최우선)
        if use_ensemble:
            logger.info("Initializing Ensemble prediction engine (LSTM + XGBoost)...")
            try:
                cls._ensemble_engine = EnsemblePredictionEngine(
                    lstm_model_path="app/prediction/models/lstm_trained",
                    xgboost_model_path="app/prediction/models/xgboost_trained",
                    use_dynamic_weights=True
                )
                logger.info("✓ Ensemble engine initialized (LSTM + XGBoost)")
            except Exception as e:
                logger.error(f"Failed to initialize Ensemble engine: {e}")
                logger.info("Falling back to LSTM-only mode")
                cls._use_ensemble = False
                cls._use_lstm = True
        
        # LSTM 단독 모드
        if use_lstm and not use_ensemble:
            logger.info("Initializing LSTM prediction engine...")
            try:
                # 모델 파일 존재 여부 확인
                model_dir = Path(model_path)
                if model_dir.exists() and (model_dir / "lstm_model.h5").exists():
                    cls._lstm_engine = LSTMPredictionEngine(model_path=model_path)
                    logger.info(f"✓ LSTM engine initialized from {model_path}")
                else:
                    logger.warning(f"LSTM model not found at {model_path}, initializing without pre-trained model")
                    cls._lstm_engine = LSTMPredictionEngine()
                    logger.info("✓ LSTM engine initialized (no pre-trained model)")
            except Exception as e:
                logger.error(f"Failed to initialize LSTM engine: {e}")
                logger.info("Falling back to traditional engine")
                cls._use_lstm = False
                cls._traditional_engine = PredictionEngine()
        else:
            logger.info("Initializing traditional prediction engine...")
            cls._traditional_engine = PredictionEngine()
            logger.info("✓ Traditional engine initialized")

    @classmethod
    def get_engine(cls):
        """
        예측 엔진 인스턴스 반환 (캐시된 인스턴스)

        Returns:
            EnsemblePredictionEngine, LSTMPredictionEngine 또는 PredictionEngine
        """
        # 초기화되지 않았으면 기본 설정으로 초기화
        if cls._lstm_engine is None and cls._traditional_engine is None and cls._ensemble_engine is None:
            logger.warning("Engine not initialized, using default initialization")
            cls.initialize(use_lstm=False, use_ensemble=False)

        # 앙상블 모드 우선
        if cls._use_ensemble and cls._ensemble_engine is not None:
            return cls._ensemble_engine
        # LSTM 모드
        elif cls._use_lstm and cls._lstm_engine is not None:
            return cls._lstm_engine
        # 전통적 모드
        else:
            if cls._traditional_engine is None:
                cls._traditional_engine = PredictionEngine()
            return cls._traditional_engine

    @classmethod
    def switch_to_lstm(cls, model_path: str = "models/lstm_model"):
        """
        LSTM 모델로 전환 (런타임 중 전환)

        Args:
            model_path: LSTM 모델 경로
        """
        logger.info(f"Switching to LSTM engine with model from {model_path}")
        try:
            cls._lstm_engine = LSTMPredictionEngine(model_path=model_path)
            cls._use_lstm = True
            cls._model_path = model_path
            logger.info("✓ Switched to LSTM engine")
            return {"success": True, "message": "Switched to LSTM engine"}
        except Exception as e:
            logger.error(f"Failed to switch to LSTM: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def switch_to_traditional(cls):
        """기존 통계 모델로 전환 (런타임 중 전환)"""
        logger.info("Switching to traditional engine")
        if cls._traditional_engine is None:
            cls._traditional_engine = PredictionEngine()
        cls._use_lstm = False
        logger.info("✓ Switched to traditional engine")
        return {"success": True, "message": "Switched to traditional engine"}

    @classmethod
    def reload_model(cls):
        """
        모델 재로드 (새로운 학습된 모델로 업데이트)

        Returns:
            Dict with success status
        """
        if cls._use_lstm:
            logger.info("Reloading LSTM model...")
            try:
                cls._lstm_engine = LSTMPredictionEngine(model_path=cls._model_path)
                logger.info("✓ LSTM model reloaded")
                return {"success": True, "message": "LSTM model reloaded"}
            except Exception as e:
                logger.error(f"Failed to reload LSTM model: {e}")
                return {"success": False, "error": str(e)}
        else:
            logger.info("Reloading traditional engine...")
            cls._traditional_engine = PredictionEngine()
            logger.info("✓ Traditional engine reloaded")
            return {"success": True, "message": "Traditional engine reloaded"}

    @classmethod
    def switch_to_ensemble(cls):
        """앙상블 모델로 전환 (런타임 중 전환)"""
        logger.info("Switching to Ensemble engine (LSTM + XGBoost)")
        try:
            cls._ensemble_engine = EnsemblePredictionEngine(
                lstm_model_path="app/prediction/models/lstm_trained",
                xgboost_model_path="app/prediction/models/xgboost_trained",
                use_dynamic_weights=True
            )
            cls._use_ensemble = True
            cls._use_lstm = False
            logger.info("✓ Switched to Ensemble engine")
            return {"success": True, "message": "Switched to Ensemble engine"}
        except Exception as e:
            logger.error(f"Failed to switch to Ensemble: {e}")
            return {"success": False, "error": str(e)}
    
    @classmethod
    def get_info(cls) -> dict:
        """
        현재 엔진 정보 반환

        Returns:
            Dict with engine information
        """
        engine_type = "Ensemble" if cls._use_ensemble else ("LSTM" if cls._use_lstm else "Traditional")
        return {
            "engine_type": engine_type,
            "ensemble_initialized": cls._ensemble_engine is not None,
            "lstm_initialized": cls._lstm_engine is not None,
            "traditional_initialized": cls._traditional_engine is not None,
            "model_path": cls._model_path if cls._use_lstm else None,
            "tensorflow_available": cls._lstm_engine is not None and hasattr(cls._lstm_engine, 'model') and cls._lstm_engine.model is not None if cls._lstm_engine else False
        }


# 전역 헬퍼 함수 (하위 호환성)
def get_prediction_engine():
    """
    예측 엔진 가져오기 (캐시된 인스턴스)

    사용 예:
        from app.prediction.engine_factory import get_prediction_engine

        engine = get_prediction_engine()
        result = engine.predict_contract_power(data, station_id)
    """
    return PredictionEngineFactory.get_engine()


def initialize_prediction_engine(use_lstm: bool = False, use_ensemble: bool = False, model_path: str = "models/lstm_model"):
    """
    예측 엔진 초기화 (앱 시작 시 호출)

    사용 예 (main.py):
        from app.prediction.engine_factory import initialize_prediction_engine

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 앱 시작 시 앙상블 모델 미리 로드
            initialize_prediction_engine(use_ensemble=True)
            yield
    """
    PredictionEngineFactory.initialize(use_lstm=use_lstm, use_ensemble=use_ensemble, model_path=model_path)
