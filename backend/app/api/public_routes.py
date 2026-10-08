"""
외부 웹앱이 예측 결과를 조회할 수 있도록 공개되는 REST API.

prefix: /api/public
모든 엔드포인트는 GET 이며, 정규화 테이블 (prediction_runs / daily_predictions /
monthly_predictions / contract_scenarios) 의 is_latest 행만 노출합니다.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .routes import get_storage_manager


public_router = APIRouter(prefix="/public", tags=["public"])


@public_router.get("/stations")
def list_stations():
    """예측 결과가 저장된 충전소 목록.

    반환: [{station_id, latest_run_at, run_count}, ...]
    """
    db = get_storage_manager().db
    if db is None:
        raise HTTPException(status_code=503, detail="storage backend not available")
    return {
        "success": True,
        "stations": db.list_stations_with_predictions(),
    }


@public_router.get("/predictions/{station_id}")
def get_prediction_summary(station_id: str):
    """충전소의 최신 예측 요약 (카드 3장에 해당하는 값).

    반환: {success, station_id, run_at, summary{...}}
    """
    db = get_storage_manager().db
    if db is None:
        raise HTTPException(status_code=503, detail="storage backend not available")

    row = db.get_latest_run(station_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"no prediction found for station_id={station_id}",
        )

    summary = {
        "run_id": row["id"],
        "run_at": row["run_at"],
        "model_version": row["model_version"],
        "maturity": {
            "level": row["maturity_level"],
            "session_count": row["session_count"],
        },
        "charger_type": row["charger_type"],

        "ensemble_prediction": {
            "final_prediction_kw": row["ensemble_p95_kw"],
            "uncertainty_kw": row["ensemble_uncertainty_kw"],
            "confidence_level": row["confidence_level"],
        },
        "contract": {
            "current_kw": row["current_contract_kw"],
            "recommended_kw": row["recommended_contract_kw"],
            "annual_savings_krw": row["annual_savings_krw"],
            "savings_percent": row["savings_percent"],
        },
        "predicted_peak": {
            "p50": row["predicted_peak_p50"],
            "p95": row["predicted_peak_p95"],
        },
        "risk": {
            "overage_probability": row["overage_probability"],
            "waste_probability": row["waste_probability"],
            "urgency_level": row["urgency_level"],
        },
        "recommendation_summary": row["recommendation_summary"],
    }
    return {"success": True, "station_id": station_id, "summary": summary}


@public_router.get("/predictions/{station_id}/daily")
def get_daily_predictions(
    station_id: str,
    date_from: Optional[str] = Query(None, alias="from", description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="YYYY-MM-DD"),
):
    """일별 P10/P50/P90/P95 시계열 (최신 run 기준)."""
    db = get_storage_manager().db
    if db is None:
        raise HTTPException(status_code=503, detail="storage backend not available")

    rows = db.get_daily_predictions(station_id, date_from=date_from, date_to=date_to)
    return {
        "success": True,
        "station_id": station_id,
        "count": len(rows),
        "daily": rows,
    }


@public_router.get("/predictions/{station_id}/monthly")
def get_monthly_predictions(station_id: str):
    """월별 집계 (최신 run 기준)."""
    db = get_storage_manager().db
    if db is None:
        raise HTTPException(status_code=503, detail="storage backend not available")

    rows = db.get_monthly_predictions(station_id)
    return {
        "success": True,
        "station_id": station_id,
        "count": len(rows),
        "monthly": rows,
    }


@public_router.get("/predictions/{station_id}/scenarios")
def get_contract_scenarios(station_id: str):
    """후보 계약전력별 시나리오 표 (최신 run 기준)."""
    db = get_storage_manager().db
    if db is None:
        raise HTTPException(status_code=503, detail="storage backend not available")

    rows = db.get_scenarios(station_id)
    return {
        "success": True,
        "station_id": station_id,
        "count": len(rows),
        "scenarios": rows,
    }
