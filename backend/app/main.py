from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .core.logger import setup_logger
from .core.config import settings

# ===== Global Variables =====
logger: Any = None


async def initialize_services():
    """Initialize application services."""
    global logger
    logger.info("Initializing services...")
    try:
        # API routes가 main을 참조할 수 있도록 설정
        from .api.routes import set_main_module

        # 배치 처리를 위한 디렉토리 생성
        import os
        os.makedirs("data/predictions", exist_ok=True)
        os.makedirs("data/uploads", exist_ok=True)
        logger.info("Created data directories")

        set_main_module(sys.modules[__name__])
        logger.info("Main module reference set for routes")

        # 예측 엔진 초기화 (싱글톤 - 앱 시작 시 한 번만 로드)
        # NOTE: Phase 3 앙상블 엔진은 API 호출 시 동적으로 초기화됨
        # from .prediction.engine_factory import initialize_prediction_engine
        # from pathlib import Path

        # # LSTM 모델 사용 여부 체크
        # lstm_model_path = Path("models/lstm_model")
        # use_lstm = lstm_model_path.exists() and (lstm_model_path / "lstm_model.h5").exists()

        # if use_lstm:
        #     logger.info("LSTM model detected, initializing LSTM engine...")
        #     initialize_prediction_engine(use_lstm=True, model_path="models/lstm_model")
        # else:
        #     logger.info("No LSTM model found, using traditional engine")
        #     initialize_prediction_engine(use_lstm=False)

        # logger.info("✓ Prediction engine initialized")
        logger.info("✓ Prediction engines ready for on-demand initialization")

        # 활성 CSV 가 있는데 예측 DB 가 비어 있으면(예: git clone 한 새 환경에 CSV 만 존재)
        # 업로드 없이도 전 충전소 예측이 채워지도록 시작 시 1회 일괄 예측을 백그라운드로 실행.
        # (DB 에 예측이 이미 있으면 건너뜀 — run_bulk_prediction_if_needed 내부에서 판단)
        try:
            import asyncio
            from .api.routes import run_bulk_prediction_if_needed
            asyncio.create_task(run_bulk_prediction_if_needed(force=False))
            logger.info("Scheduled startup bulk prediction (DB가 비어 있을 때만 실행)")
        except Exception as e:
            logger.warning(f"Failed to schedule startup bulk prediction: {e}")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        raise


async def shutdown_services():
    """Shutdown application services."""
    global logger
    if logger:
        logger.info("Services shut down successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan management."""
    global logger
    logger.info("=== Starting EV Charging Station Peak Predictor ===")
    try:
        await initialize_services()
        logger.info("Startup completed")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    yield
    logger.info("=== Shutting down ===")
    await shutdown_services()


def setup_routes():
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|220\.69\.200\.55):\d+$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=86400,
    )

    from .api.routes import api_router
    from .api.public_routes import public_router
    # Batch API 일시적으로 비활성화 (engine 모듈 의존성 때문)
    # from .api.batch import router as batch_router

    app.include_router(api_router, prefix="/api")
    app.include_router(public_router, prefix="/api")  # /api/public/...
    # app.include_router(batch_router, prefix="/api")
    if logger:
        logger.info("Routes configured")


# ===== FastAPI App =====
app = FastAPI(title="EV Charging Station Peak Predictor", version="1.0.0", lifespan=lifespan)

# Initialize logger once
logger = setup_logger("charging_predictor", level=settings.log_level)
setup_routes()


# 프리플라이트 로깅(디버그용)
@app.middleware("http")
async def log_cors(request: Request, call_next):
    if request.method == "OPTIONS":
        logger.info(
            f"Preflight - Origin={request.headers.get('origin')} "
            f"ACRM={request.headers.get('access-control-request-method')} "
            f"ACRH={request.headers.get('access-control-request-headers')}"
        )
    return await call_next(request)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/")
async def root():
    return {
        "message": "EV Charging Station Peak Predictor API",
        "timestamp": datetime.now().isoformat(),
        "docs": "/docs",
        "api": "/api",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=32375, reload=True)
