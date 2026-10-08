"""
XGBoost 예측 엔진

현재 데이터에서 추출 가능한 특징으로 학습:
- 시간 특징: 시간, 요일, 월, 주차
- 충전 패턴: 충전량, 충전시간, SOC 변화
- 회원 특징: 개인/법인, 회원 유형
- 충전소 특징: 위치(권역, 시군구), 충전기 타입
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import logging
from pathlib import Path
import pickle

from .models.prediction_types import ModelPrediction, EnsemblePrediction

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("XGBoost not available. Will use fallback methods.")


class XGBoostPredictionEngine:
    """
    XGBoost 기반 전력 수요 예측 엔진
    
    현재 데이터에서 추출 가능한 특징:
    - 시간 특징: 시간대, 요일, 월, 주차, 주말 여부
    - 충전 패턴: 평균 충전량, 평균 충전시간, SOC 패턴
    - 회원 특징: 개인/법인 비율, 회원 유형 분포
    - 충전소 특징: 권역, 시군구, 충전기 타입
    """

    def __init__(self, model_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.model = None
        self.feature_names = []
        self.scaler = None
        
        # XGBoost 파라미터
        self.params = {
            'objective': 'reg:squarederror',
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 100,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42
        }
        
        # 모델 로드 또는 초기화
        if model_path and Path(model_path).exists():
            self._load_model(model_path)
        elif XGBOOST_AVAILABLE:
            self._build_model()
        else:
            self.logger.warning("XGBoost not available. Using statistical fallback.")

    def _build_model(self):
        """XGBoost 모델 초기화"""
        if not XGBOOST_AVAILABLE:
            return
        
        try:
            self.model = xgb.XGBRegressor(**self.params)
            self.logger.info("XGBoost model initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to build XGBoost model: {e}")
            self.model = None

    def _load_model(self, model_path: str):
        """저장된 모델 로드"""
        try:
            model_dir = Path(model_path)
            
            # XGBoost 모델 로드
            if (model_dir / "xgboost_model.json").exists() and XGBOOST_AVAILABLE:
                self.model = xgb.XGBRegressor()
                self.model.load_model(model_dir / "xgboost_model.json")
                self.logger.info(f"XGBoost model loaded from {model_path}")
            
            # Feature names 로드
            if (model_dir / "feature_names.pkl").exists():
                with open(model_dir / "feature_names.pkl", 'rb') as f:
                    self.feature_names = pickle.load(f)
                self.logger.info(f"Feature names loaded: {len(self.feature_names)} features")
            
            # Scaler 로드
            if (model_dir / "scaler.pkl").exists():
                with open(model_dir / "scaler.pkl", 'rb') as f:
                    self.scaler = pickle.load(f)
                self.logger.info("Scaler loaded successfully")
                
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            if XGBOOST_AVAILABLE:
                self._build_model()

    def save_model(self, model_path: str):
        """모델 저장"""
        try:
            model_dir = Path(model_path)
            model_dir.mkdir(parents=True, exist_ok=True)
            
            # XGBoost 모델 저장
            if self.model and XGBOOST_AVAILABLE:
                self.model.save_model(model_dir / "xgboost_model.json")
                self.logger.info(f"XGBoost model saved to {model_path}")
            
            # Feature names 저장
            if self.feature_names:
                with open(model_dir / "feature_names.pkl", 'wb') as f:
                    pickle.dump(self.feature_names, f)
                self.logger.info("Feature names saved successfully")
            
            # Scaler 저장
            if self.scaler:
                with open(model_dir / "scaler.pkl", 'wb') as f:
                    pickle.dump(self.scaler, f)
                self.logger.info("Scaler saved successfully")
                
        except Exception as e:
            self.logger.error(f"Failed to save model: {e}")

    def extract_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        데이터에서 특징 추출
        
        특징 카테고리:
        1. 시간 특징: 시간, 요일, 월, 주차, 주말 여부
        2. 충전 패턴: 충전량, 충전시간, SOC 변화
        3. 회원 특징: 개인/법인 비율
        4. 통계 특징: 평균, 최대, 표준편차
        """
        features = pd.DataFrame()
        
        # 날짜/시간 특징
        if '충전시작일시' in data.columns:
            data['충전시작일시'] = pd.to_datetime(data['충전시작일시'], errors='coerce')
            
            # 시간 특징
            features['hour'] = data['충전시작일시'].dt.hour
            features['day_of_week'] = data['충전시작일시'].dt.dayofweek
            features['month'] = data['충전시작일시'].dt.month
            features['week_of_year'] = data['충전시작일시'].dt.isocalendar().week
            features['is_weekend'] = (data['충전시작일시'].dt.dayofweek >= 5).astype(int)
            features['is_business_hour'] = ((data['충전시작일시'].dt.hour >= 9) & 
                                           (data['충전시작일시'].dt.hour <= 18)).astype(int)
        
        # 충전 패턴 특징
        if '충전량(kWh)' in data.columns:
            data['충전량(kWh)'] = pd.to_numeric(data['충전량(kWh)'], errors='coerce')
            features['charge_amount'] = data['충전량(kWh)'].fillna(0)
        
        if '충전시간' in data.columns:
            # 충전시간을 분으로 변환 (HH:MM:SS 형식)
            try:
                charge_time_minutes = pd.to_timedelta(data['충전시간'], errors='coerce').dt.total_seconds() / 60
                features['charge_duration_minutes'] = charge_time_minutes.fillna(0)
            except:
                features['charge_duration_minutes'] = 0
        
        # SOC 변화
        if '시작SOC(%)' in data.columns and '완료SOC(%)' in data.columns:
            data['시작SOC(%)'] = pd.to_numeric(data['시작SOC(%)'], errors='coerce')
            data['완료SOC(%)'] = pd.to_numeric(data['완료SOC(%)'], errors='coerce')
            features['soc_change'] = (data['완료SOC(%)'] - data['시작SOC(%)']).fillna(0)
            features['start_soc'] = data['시작SOC(%)'].fillna(50)
        
        # 회원 특징
        if '개인/법인' in data.columns:
            features['is_corporate'] = (data['개인/법인'] == '법인').astype(int)
        
        # 충전기 타입
        if '충전기 구분' in data.columns:
            features['is_fast_charger'] = data['충전기 구분'].str.contains('급속', na=False).astype(int)
        
        # 순간최고전력 (목표 변수)
        if '순간최고전력' in data.columns:
            data['순간최고전력'] = pd.to_numeric(data['순간최고전력'], errors='coerce')
            features['peak_power'] = data['순간최고전력'].fillna(0)
        
        # 결측값 처리
        features = features.fillna(0)
        
        return features

    def aggregate_features_hourly(self, features: pd.DataFrame, timestamps: pd.Series) -> pd.DataFrame:
        """시간 단위로 특징 집계"""
        # 시간 인덱스 추가
        features['timestamp'] = pd.to_datetime(timestamps)
        features['hour_key'] = features['timestamp'].dt.floor('h')  # 'H'는 pandas 2.2+에서 deprecated/제거 → 'h'
        
        # 시간별 집계
        hourly = features.groupby('hour_key').agg({
            'hour': 'first',
            'day_of_week': 'first',
            'month': 'first',
            'week_of_year': 'first',
            'is_weekend': 'first',
            'is_business_hour': 'first',
            'charge_amount': ['mean', 'sum', 'count'],
            'charge_duration_minutes': 'mean',
            'soc_change': 'mean',
            'start_soc': 'mean',
            'is_corporate': 'mean',
            'is_fast_charger': 'mean',
            'peak_power': ['max', 'mean', 'std']
        }).reset_index()
        
        # 컬럼명 단순화
        hourly.columns = ['_'.join(col).strip('_') if col[1] else col[0] 
                         for col in hourly.columns.values]
        
        return hourly

    def train_model(
        self,
        training_data: pd.DataFrame,
        validation_split: float = 0.2,
        early_stopping_rounds: int = 10
    ) -> Dict[str, Any]:
        """
        XGBoost 모델 학습
        
        Args:
            training_data: 학습 데이터 (원본 충전 데이터)
            validation_split: 검증 데이터 비율
            early_stopping_rounds: Early stopping 라운드
            
        Returns:
            학습 히스토리
        """
        if not XGBOOST_AVAILABLE:
            return {"success": False, "error": "XGBoost not installed"}
        
        if self.model is None:
            self._build_model()
        
        try:
            # 특징 추출
            self.logger.info("Extracting features from training data...")
            features = self.extract_features(training_data)
            
            # 시간 단위 집계
            if '충전시작일시' in training_data.columns:
                hourly_features = self.aggregate_features_hourly(
                    features, 
                    training_data['충전시작일시']
                )
            else:
                hourly_features = features
            
            # 목표 변수 분리
            target_cols = [col for col in hourly_features.columns if 'peak_power' in col]
            if not target_cols:
                return {"success": False, "error": "No target variable found"}
            
            # peak_power_max를 목표로 사용
            y = hourly_features['peak_power_max']
            
            # 특징 선택 (목표 변수 제외)
            feature_cols = [col for col in hourly_features.columns 
                           if col not in ['hour_key', 'timestamp'] + target_cols]
            X = hourly_features[feature_cols]
            
            self.feature_names = feature_cols
            
            self.logger.info(f"Training with {len(X)} samples, {len(feature_cols)} features")
            self.logger.info(f"Features: {feature_cols}")
            
            # 학습/검증 분할
            split_idx = int(len(X) * (1 - validation_split))
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            
            # 모델 학습
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=True
            )
            
            # 평가
            train_score = self.model.score(X_train, y_train)
            val_score = self.model.score(X_val, y_val)
            
            # 예측
            y_pred_train = self.model.predict(X_train)
            y_pred_val = self.model.predict(X_val)
            
            # MAE 계산
            train_mae = np.mean(np.abs(y_train - y_pred_train))
            val_mae = np.mean(np.abs(y_val - y_pred_val))
            
            self.logger.info(
                f"Training completed: train_r2={train_score:.4f}, "
                f"val_r2={val_score:.4f}, train_mae={train_mae:.2f}, val_mae={val_mae:.2f}"
            )
            
            return {
                "success": True,
                "train_r2_score": float(train_score),
                "val_r2_score": float(val_score),
                "train_mae": float(train_mae),
                "val_mae": float(val_mae),
                "n_features": len(feature_cols),
                "n_samples": len(X),
                "feature_importance": dict(zip(
                    feature_cols, 
                    self.model.feature_importances_
                ))
            }
            
        except Exception as e:
            self.logger.error(f"Model training failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def predict_contract_power(
        self,
        data: pd.DataFrame,
        station_id: str,
        charger_type: str = None
    ) -> EnsemblePrediction:
        """
        계약전력 예측
        
        Args:
            data: 충전소 데이터
            station_id: 충전소 ID
            charger_type: 충전기 타입
            
        Returns:
            EnsemblePrediction: 예측 결과
        """
        if not XGBOOST_AVAILABLE or self.model is None:
            return self._fallback_prediction(station_id, data)
        
        try:
            # 특징 추출
            features = self.extract_features(data)
            
            # 시간 단위 집계
            if '충전시작일시' in data.columns:
                hourly_features = self.aggregate_features_hourly(
                    features,
                    data['충전시작일시']
                )
            else:
                hourly_features = features
            
            # 예측용 특징 선택
            X = hourly_features[self.feature_names]
            
            # 예측
            predictions = self.model.predict(X)
            
            # 통계 계산
            predicted_value = np.percentile(predictions, 95)  # P95 사용
            ci_lower = np.percentile(predictions, 10)
            ci_upper = np.percentile(predictions, 99)
            
            # 모델 예측 객체 생성
            xgboost_prediction = ModelPrediction(
                model_name="XGBoost_TreeBased",
                predicted_value=float(predicted_value),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=0.80,
                method_details={
                    "method": "XGBoost Gradient Boosting",
                    "n_features": len(self.feature_names),
                    "feature_importance_top3": self._get_top_features(3),
                    "description": "XGBoost 기반 시간/충전 패턴 예측",
                    "data_points_used": len(predictions)
                }
            )
            
            # 최종 예측값
            final_prediction = min(int(np.ceil(predicted_value)), 100)
            
            return EnsemblePrediction(
                final_prediction=final_prediction,
                raw_prediction=predicted_value,
                model_predictions=[xgboost_prediction],
                ensemble_method="xgboost_only",
                weights={"XGBoost_TreeBased": 1.0},
                uncertainty=float(np.std(predictions)),
                visualization_data=self._prepare_visualization_data(
                    [xgboost_prediction],
                    predicted_value
                )
            )
            
        except Exception as e:
            self.logger.error(f"XGBoost prediction failed: {e}", exc_info=True)
            return self._fallback_prediction(station_id, data)

    def _get_top_features(self, n: int = 3) -> Dict[str, float]:
        """상위 N개 중요 특징 반환"""
        if self.model is None or not self.feature_names:
            return {}
        
        try:
            importances = self.model.feature_importances_
            top_indices = np.argsort(importances)[-n:][::-1]
            
            return {
                self.feature_names[i]: float(importances[i])
                for i in top_indices
            }
        except:
            return {}

    def _fallback_prediction(self, station_id: str, data: pd.DataFrame) -> EnsemblePrediction:
        """폴백 예측"""
        self.logger.warning(f"Using fallback prediction for station {station_id}")
        
        # 기본 통계 기반 예측
        if '순간최고전력' in data.columns:
            power_data = pd.to_numeric(data['순간최고전력'], errors='coerce').dropna()
            if len(power_data) > 0:
                predicted_value = float(power_data.quantile(0.95))
            else:
                predicted_value = 45.0
        else:
            predicted_value = 45.0
        
        fallback_prediction = ModelPrediction(
            model_name="Statistical_Fallback",
            predicted_value=predicted_value,
            confidence_interval=(predicted_value * 0.9, predicted_value * 1.1),
            confidence_score=0.60,
            method_details={
                "method": "95th Percentile",
                "reason": "XGBoost not available",
                "description": "통계적 백분위수 기반 예측"
            }
        )
        
        return EnsemblePrediction(
            final_prediction=int(np.ceil(predicted_value)),
            raw_prediction=predicted_value,
            model_predictions=[fallback_prediction],
            ensemble_method="fallback",
            weights={"Statistical_Fallback": 1.0},
            uncertainty=20.0,
            visualization_data=self._prepare_visualization_data(
                [fallback_prediction],
                predicted_value
            )
        )

    def _prepare_visualization_data(
        self,
        predictions: List[ModelPrediction],
        ensemble_prediction: float
    ) -> Dict[str, Any]:
        """시각화용 데이터 준비"""
        return {
            "individual_predictions": [
                {
                    "model": pred.model_name,
                    "value": pred.predicted_value,
                    "confidence": pred.confidence_score,
                    "ci_lower": pred.confidence_interval[0],
                    "ci_upper": pred.confidence_interval[1],
                }
                for pred in predictions
            ],
            "ensemble_prediction": ensemble_prediction,
            "model_count": len(predictions),
            "prediction_range": {
                "min": min(p.predicted_value for p in predictions),
                "max": max(p.predicted_value for p in predictions),
                "std": np.std([p.predicted_value for p in predictions]),
            },
        }
