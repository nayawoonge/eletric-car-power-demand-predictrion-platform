import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import logging
import warnings
from pathlib import Path
import pickle
from dataclasses import dataclass

from .models.prediction_types import ModelPrediction, EnsemblePrediction

warnings.filterwarnings("ignore")

@dataclass
class PatternFactors:
    """Simplified pattern factors"""
    seasonal_factor: float = 1.0
    weekly_factor: float = 1.0
    trend_factor: float = 1.0
    confidence: float = 0.7
    data_quality: str = "medium"

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    logging.warning("PyTorch not available. LSTM prediction will use fallback methods.")


# PyTorch LSTM 모델 정의
class LSTMModel(nn.Module):
    """PyTorch LSTM 모델"""
    
    def __init__(
        self, 
        input_dim: int = 6, 
        hidden_dim: int = 64, 
        num_layers: int = 2,
        dropout: float = 0.2
    ):
        super(LSTMModel, self).__init__()
        
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True
        )
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_dim, 16)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(16, 1)
        
    def forward(self, x):
        """
        Forward pass
        
        Args:
            x: (batch_size, sequence_length, input_dim)
            
        Returns:
            predictions: (batch_size, 1)
        """
        # LSTM forward
        lstm_out, (h_n, c_n) = self.lstm(x)
        
        # 마지막 hidden state 사용
        last_hidden = h_n[-1]  # (batch_size, hidden_dim)
        
        # Fully connected layers
        out = self.fc1(last_hidden)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        
        return out


class LSTMPredictionEngine:
    """PyTorch 기반 LSTM 예측 엔진"""

    def __init__(self, model_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.max_contract_power = 100  # 최대 계약 전력 100kW

        # 충전기 타입별 최대 전력 제한
        self.charger_limits = {
            "완속충전기 (AC)": 7,
            "급속충전기 (DC)": 100,
            "미상": 50,
        }

        # LSTM 모델 설정
        self.sequence_length = 24  # 24시간(또는 24개 데이터 포인트) 시퀀스
        self.feature_dim = 6  # 입력 특징 개수
        self.hidden_dim = 64
        self.num_layers = 2
        self.dropout = 0.2
        
        self.model = None
        self.scaler = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if PYTORCH_AVAILABLE else None

        # 모델 로드 또는 초기화
        if model_path and Path(model_path).exists():
            self._load_model(model_path)
        else:
            if PYTORCH_AVAILABLE:
                self._build_model()
            else:
                self.logger.warning("PyTorch not available. Using statistical fallback.")

    def _build_model(self):
        """PyTorch LSTM 모델 생성"""
        if not PYTORCH_AVAILABLE:
            return

        try:
            self.model = LSTMModel(
                input_dim=self.feature_dim,
                hidden_dim=self.hidden_dim,
                num_layers=self.num_layers,
                dropout=self.dropout
            )
            
            if self.device:
                self.model.to(self.device)
            
            self.logger.info(f"LSTM model built successfully on {self.device}")

        except Exception as e:
            self.logger.error(f"Failed to build LSTM model: {e}")
            self.model = None

    def _load_model(self, model_path: str):
        """저장된 모델 로드"""
        try:
            model_dir = Path(model_path)

            # PyTorch 모델 로드
            model_file = model_dir / "lstm_model.pt"
            if model_file.exists() and PYTORCH_AVAILABLE:
                self._build_model()  # 모델 구조 먼저 생성
                self.model.load_state_dict(torch.load(model_file, map_location=self.device))
                self.model.eval()
                self.logger.info(f"LSTM model loaded from {model_path}")

            # Scaler 로드
            scaler_file = model_dir / "scaler.pkl"
            if scaler_file.exists():
                with open(scaler_file, 'rb') as f:
                    self.scaler = pickle.load(f)
                self.logger.info("Scaler loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            if PYTORCH_AVAILABLE:
                self._build_model()

    def save_model(self, model_path: str):
        """모델 저장"""
        try:
            model_dir = Path(model_path)
            model_dir.mkdir(parents=True, exist_ok=True)

            # PyTorch 모델 저장
            if self.model and PYTORCH_AVAILABLE:
                torch.save(self.model.state_dict(), model_dir / "lstm_model.pt")
                self.logger.info(f"LSTM model saved to {model_path}")

            # Scaler 저장
            if self.scaler:
                with open(model_dir / "scaler.pkl", 'wb') as f:
                    pickle.dump(self.scaler, f)
                self.logger.info("Scaler saved successfully")

        except Exception as e:
            self.logger.error(f"Failed to save model: {e}")

    def predict_contract_power(
        self,
        data: pd.DataFrame,
        station_id: str,
        charger_type: str = None
    ) -> EnsemblePrediction:
        """
        계약전력 예측 (메인 메서드)

        Args:
            data: 충전소 데이터
            station_id: 충전소 ID
            charger_type: 충전기 타입

        Returns:
            EnsemblePrediction: 예측 결과
        """

        if data.empty or "순간최고전력" not in data.columns:
            return self._fallback_prediction(station_id)

        # 데이터 전처리
        power_data = self._preprocess_data(data)

        if len(power_data) < self.sequence_length:
            return self._fallback_prediction(station_id)

        try:
            # LSTM 예측
            if self.model and PYTORCH_AVAILABLE:
                lstm_prediction = self._lstm_predict(data, power_data)
            else:
                # PyTorch가 없으면 통계적 방법 사용
                lstm_prediction = self._statistical_fallback(power_data)

            # 충전기 타입 제한 적용
            if charger_type and charger_type in self.charger_limits:
                max_limit = self.charger_limits[charger_type]
                lstm_prediction.final_prediction = min(
                    lstm_prediction.final_prediction,
                    max_limit
                )

            self.logger.info(
                f"Station {station_id}: LSTM prediction completed, "
                f"result: {lstm_prediction.final_prediction}kW"
            )

            return lstm_prediction

        except Exception as e:
            self.logger.error(f"LSTM prediction failed: {e}", exc_info=True)
            return self._fallback_prediction(station_id)

    def _preprocess_data(self, data: pd.DataFrame) -> np.ndarray:
        """데이터 전처리"""
        try:
            # 숫자 타입으로 변환 (날짜/시간 문제 방지)
            power_data = pd.to_numeric(data["순간최고전력"], errors='coerce').values

            # 결측값 및 이상값 제거
            power_data = power_data[~np.isnan(power_data)]
            power_data = power_data[power_data > 0]
            power_data = power_data[power_data < 1000]

            # IQR 기반 이상치 제거
            if len(power_data) > 10:
                Q1, Q3 = np.percentile(power_data, [25, 75])
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                power_data = power_data[
                    (power_data >= lower_bound) & (power_data <= upper_bound)
                ]

            return power_data

        except Exception as e:
            self.logger.error(f"Data preprocessing failed: {e}", exc_info=True)
            return np.array([])

    def _extract_features(self, data: pd.DataFrame, power_data: np.ndarray) -> np.ndarray:
        """
        시계열 데이터에서 특징 추출

        Features:
        1. 전력값 (normalized)
        2. 시간 (hour of day) - 주기적 인코딩
        3. 요일 (day of week) - 주기적 인코딩
        4. 월 (month) - 주기적 인코딩
        5. 트렌드 (선형 트렌드)
        6. 이동평균 (rolling mean)
        """
        try:
            # DatetimeIndex가 없으면 충전시작일시 컬럼에서 생성
            if not isinstance(data.index, pd.DatetimeIndex):
                # 충전시작일시 컬럼 찾기
                date_col = None
                for col in ['충전시작일시', '충전완료일시', 'timestamp']:
                    if col in data.columns:
                        date_col = col
                        break
                
                if date_col:
                    # DatetimeIndex 설정
                    data_copy = data.copy()
                    data_copy[date_col] = pd.to_datetime(data_copy[date_col], errors='coerce')
                    data_copy = data_copy.dropna(subset=[date_col])
                    data_copy = data_copy.set_index(date_col)
                    
                    if len(data_copy) > 0:
                        return self._extract_features_from_datetime_index(data_copy, power_data)
                
                # 날짜 정보가 없으면 기본 특징만 사용
                self.logger.warning("No datetime information found, using basic features")
                features = self._extract_basic_features(power_data)
                return features
            
            # DatetimeIndex가 있으면 정상 처리
            return self._extract_features_from_datetime_index(data, power_data)

        except Exception as e:
            self.logger.error(f"Feature extraction failed: {e}", exc_info=True)
            return self._extract_basic_features(power_data)
    
    def _extract_features_from_datetime_index(
        self, 
        data: pd.DataFrame, 
        power_data: np.ndarray
    ) -> np.ndarray:
        """DatetimeIndex가 있는 데이터에서 특징 추출"""
        features_list = []

        for i in range(len(data)):
            timestamp = data.index[i]
            power = power_data[i] if i < len(power_data) else 0

            # 1. 정규화된 전력값
            normalized_power = power / 100.0  # 0-100kW 범위를 0-1로

            # 2. 시간 (주기적 인코딩: sin/cos)
            hour = timestamp.hour
            hour_sin = np.sin(2 * np.pi * hour / 24)
            hour_cos = np.cos(2 * np.pi * hour / 24)

            # 3. 요일 (주기적 인코딩)
            weekday = timestamp.weekday()
            weekday_sin = np.sin(2 * np.pi * weekday / 7)
            weekday_cos = np.cos(2 * np.pi * weekday / 7)

            # 4. 월 (주기적 인코딩)
            month = timestamp.month
            month_sin = np.sin(2 * np.pi * month / 12)

            features = [
                normalized_power,
                hour_sin,
                weekday_sin,
                month_sin,
                hour_cos,  # 추가 시간 정보
                weekday_cos  # 추가 요일 정보
            ]

            features_list.append(features)

        return np.array(features_list)

    def _extract_basic_features(self, power_data: np.ndarray) -> np.ndarray:
        """기본 특징 추출 (시간 정보가 없을 때)"""
        features_list = []

        for i in range(len(power_data)):
            power = power_data[i]
            normalized_power = power / 100.0

            # 기본 특징: 전력값 + 더미 시간 특징
            features = [
                normalized_power,
                0.0,  # hour_sin
                0.0,  # weekday_sin
                0.0,  # month_sin
                1.0,  # hour_cos
                1.0   # weekday_cos
            ]
            features_list.append(features)

        return np.array(features_list)

    def _create_sequences(self, features: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """시퀀스 데이터 생성 (sliding window)"""
        X, y = [], []

        for i in range(len(features) - self.sequence_length):
            X.append(features[i:i + self.sequence_length])
            # 다음 시점의 전력값 예측
            y.append(features[i + self.sequence_length, 0] * 100.0)  # denormalize

        return np.array(X), np.array(y)

    def predict_with_uncertainty(
        self,
        data: pd.DataFrame,
        power_data: np.ndarray,
        n_iterations: int = 1000
    ) -> np.ndarray:
        """
        Monte Carlo Dropout을 사용한 불확실성 추정

        Args:
            data: 입력 데이터프레임
            power_data: 전력 데이터
            n_iterations: Monte Carlo 시뮬레이션 반복 횟수

        Returns:
            np.ndarray: 예측 분포 (shape: (n_iterations,))
        """
        try:
            # 모델이 없으면 통계 기반 분포 반환
            if self.model is None or not PYTORCH_AVAILABLE:
                mean = np.mean(power_data)
                std = np.std(power_data)
                return np.random.normal(mean, std, n_iterations)

            # 특징 추출
            features = self._extract_features(data, power_data)

            if len(features) < self.sequence_length:
                # 데이터 부족 시 통계 기반 분포 생성
                mean = np.mean(power_data)
                std = np.std(power_data)
                return np.random.normal(mean, std, n_iterations)

            # 마지막 시퀀스로 예측
            last_sequence = features[-self.sequence_length:]

            # PyTorch 텐서로 변환 후 배치 차원으로 n_iterations 만큼 복제
            # (1, seq_len, features) -> (n_iterations, seq_len, features)
            # Monte Carlo Dropout 1000회를 파이썬 루프 대신 단일 배치 forward로 실행.
            # 동일 입력이라도 Dropout이 활성(train mode)이라 샘플마다 다른 출력이 나온다.
            x_tensor = torch.FloatTensor(last_sequence).unsqueeze(0)  # (1, seq_len, features)
            x_batch = x_tensor.repeat(n_iterations, 1, 1)  # 연속 메모리 보장 (LSTM/cuDNN 호환)
            if self.device:
                x_batch = x_batch.to(self.device)

            # Monte Carlo Dropout: 모델을 train mode로 설정하여 dropout 활성화
            self.model.train()

            with torch.no_grad():  # gradient 계산은 불필요
                preds = self.model(x_batch)  # (n_iterations, 1) - 단일 배치 forward

            # 예측 후 다시 eval mode로
            self.model.eval()

            # 1차원 분포로 반환 (GPU↔CPU 동기화는 한 번만)
            # 모델은 원본 kW 스케일로 출력하도록 학습됨(_create_sequences 의 target = power).
            # predict_session_series 등 다른 추론 경로와 동일하게 추가 스케일링 없이 사용한다.
            # (과거 여기서 ×100 을 곱해 이중 역정규화로 값이 100배 부풀던 버그를 제거)
            predictions = preds.reshape(-1).cpu().numpy()

            return np.asarray(predictions)
            
        except Exception as e:
            self.logger.error(f"Monte Carlo prediction failed: {e}")
            # 폴백: 통계 기반 분포
            mean = np.mean(power_data)
            std = np.std(power_data)
            return np.random.normal(mean, std, n_iterations)

    def _lstm_predict(self, data: pd.DataFrame, power_data: np.ndarray) -> EnsemblePrediction:
        """LSTM 모델을 사용한 예측 (Monte Carlo Dropout 포함)"""
        try:
            # Monte Carlo Dropout으로 확률분포 생성
            prediction_distribution = self.predict_with_uncertainty(
                data, power_data, n_iterations=1000
            )
            
            # 분포 통계 계산
            prediction = np.mean(prediction_distribution)
            ci_lower = np.percentile(prediction_distribution, 2.5)
            ci_upper = np.percentile(prediction_distribution, 97.5)
            
            # 분포 정보를 method_details에 저장
            distribution_stats = {
                "mean": float(np.mean(prediction_distribution)),
                "std": float(np.std(prediction_distribution)),
                "min": float(np.min(prediction_distribution)),
                "max": float(np.max(prediction_distribution)),
                "p10": float(np.percentile(prediction_distribution, 10)),
                "p50": float(np.percentile(prediction_distribution, 50)),
                "p90": float(np.percentile(prediction_distribution, 90)),
                "p95": float(np.percentile(prediction_distribution, 95)),
                "p99": float(np.percentile(prediction_distribution, 99)),
            }

            # 기본 통계 계산
            base_stats = self._compute_base_statistics(power_data)

            # 모델 예측 객체 생성 (Monte Carlo Dropout 적용)
            lstm_model_prediction = ModelPrediction(
                model_name="LSTM_PyTorch",
                predicted_value=float(prediction),
                confidence_interval=(float(ci_lower), float(ci_upper)),
                confidence_score=0.85,  # LSTM은 높은 신뢰도
                method_details={
                    "method": "PyTorch LSTM with Monte Carlo Dropout",
                    "framework": "PyTorch",
                    "device": str(self.device),
                    "sequence_length": self.sequence_length,
                    "feature_dim": self.feature_dim,
                    "hidden_dim": self.hidden_dim,
                    "num_layers": self.num_layers,
                    "monte_carlo_iterations": 1000,
                    "description": "PyTorch LSTM + Monte Carlo Dropout 불확실성 추정",
                    "data_points_used": len(power_data),
                    "percentile_95_comparison": base_stats["q95"],
                    "distribution": distribution_stats,
                    "prediction_distribution": prediction_distribution.tolist()
                }
            )

            # 보조 통계 예측 추가 (앙상블 효과)
            statistical_prediction = ModelPrediction(
                model_name="Statistical_Baseline",
                predicted_value=base_stats["q95"],
                confidence_interval=(base_stats["q90"], base_stats["q99"]),
                confidence_score=0.70,
                method_details={
                    "method": "95th Percentile",
                    "description": "통계적 기준선"
                }
            )

            # 가중 앙상블 (LSTM 70%, Statistical 30%)
            predictions = [lstm_model_prediction, statistical_prediction]
            weights = {
                "LSTM_PyTorch": 0.70,
                "Statistical_Baseline": 0.30
            }

            weighted_prediction = (
                lstm_model_prediction.predicted_value * 0.70 +
                statistical_prediction.predicted_value * 0.30
            )

            # 불확실성 계산
            uncertainty = np.sqrt(
                0.70 * (lstm_model_prediction.predicted_value - weighted_prediction) ** 2 +
                0.30 * (statistical_prediction.predicted_value - weighted_prediction) ** 2
            )

            # 최종 예측값 (올림)
            final_prediction = min(
                int(np.ceil(weighted_prediction)),
                self.max_contract_power
            )

            return EnsemblePrediction(
                final_prediction=final_prediction,
                raw_prediction=weighted_prediction,
                model_predictions=predictions,
                ensemble_method="weighted_pytorch_lstm_statistical",
                weights=weights,
                uncertainty=float(uncertainty),
                visualization_data=self._prepare_visualization_data(
                    predictions,
                    weighted_prediction
                )
            )

        except Exception as e:
            self.logger.error(f"LSTM prediction failed: {e}", exc_info=True)
            return self._statistical_fallback(power_data)

    def _statistical_fallback(self, power_data: np.ndarray) -> EnsemblePrediction:
        """통계적 방법을 사용한 폴백 예측"""
        base_stats = self._compute_base_statistics(power_data)

        # 95th percentile 기반 예측
        predicted_value = base_stats["q95"]

        fallback_prediction = ModelPrediction(
            model_name="Statistical_Fallback",
            predicted_value=predicted_value,
            confidence_interval=(base_stats["q90"], base_stats["q99"]),
            confidence_score=0.75,
            method_details={
                "method": "95th Percentile",
                "reason": "PyTorch not available or insufficient data",
                "description": "통계적 백분위수 기반 예측"
            }
        )

        final_prediction = min(
            int(np.ceil(predicted_value)),
            self.max_contract_power
        )

        return EnsemblePrediction(
            final_prediction=final_prediction,
            raw_prediction=predicted_value,
            model_predictions=[fallback_prediction],
            ensemble_method="statistical_fallback",
            weights={"Statistical_Fallback": 1.0},
            uncertainty=base_stats["std"],
            visualization_data=self._prepare_visualization_data(
                [fallback_prediction],
                predicted_value
            )
        )

    def _detect_time_column(self, data: pd.DataFrame) -> Optional[str]:
        """세션 데이터에서 시간 컬럼 탐지"""
        time_candidates = [
            "충전시작일시",
            "충전완료일시",
            "timestamp",
            "측정일시",
            "date",
            "created_at"
        ]
        for col in time_candidates:
            if col in data.columns:
                return col
        return None

    def predict_session_series(
        self,
        data: pd.DataFrame,
        station_id: str,
        max_points: int = 1600,
        charger_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """세션 단위 예측 시계열 생성"""
        try:
            power_col = None
            for candidate in ["순간최고전력", "순간 최고 전력", "max_power", "전력"]:
                if candidate in data.columns:
                    power_col = candidate
                    break

            if power_col is None:
                return []

            working_df = data[[power_col]].copy()
            working_df.rename(columns={power_col: "peak_kw"}, inplace=True)

            time_col = self._detect_time_column(data)
            if time_col and time_col in data.columns:
                timestamps = pd.to_datetime(data[time_col], errors="coerce")
                working_df["timestamp"] = timestamps
                working_df = working_df.dropna(subset=["timestamp", "peak_kw"])
                if working_df.empty:
                    return []
                working_df = working_df.sort_values("timestamp")
                working_df = working_df.set_index("timestamp")
            elif isinstance(data.index, pd.DatetimeIndex):
                working_df.index = pd.to_datetime(data.index, errors="coerce")
                working_df = working_df.dropna(subset=["peak_kw"])
                working_df = working_df.sort_index()
            else:
                return []

            if working_df.empty:
                return []

            # 분석 범위 제한 (최근 max_points + sequence_length)
            cutoff_count = max_points + self.sequence_length + 1
            if len(working_df) > cutoff_count:
                working_df = working_df.iloc[-cutoff_count:]

            numeric_power = pd.to_numeric(working_df["peak_kw"], errors="coerce").dropna()
            working_df = working_df.loc[numeric_power.index]

            if working_df.empty:
                return []

            if not PYTORCH_AVAILABLE or self.model is None:
                return self._session_series_baseline(working_df)

            features = self._extract_features(working_df, numeric_power.values)
            if len(features) <= self.sequence_length:
                return self._session_series_baseline(working_df)

            sequences: List[np.ndarray] = []
            timestamps: List[pd.Timestamp] = []
            feature_array = np.asarray(features, dtype=np.float32)

            for idx in range(len(feature_array) - self.sequence_length):
                window = feature_array[idx: idx + self.sequence_length]
                target_timestamp = working_df.index[idx + self.sequence_length]
                sequences.append(window)
                timestamps.append(target_timestamp)

            if not sequences:
                return []

            input_tensor = torch.tensor(np.stack(sequences), dtype=torch.float32)
            if self.device:
                input_tensor = input_tensor.to(self.device)

            self.model.eval()
            with torch.no_grad():
                outputs = self.model(input_tensor).squeeze(-1)
                predictions = outputs.detach().cpu().numpy()

            max_limit = self.charger_limits.get(charger_type, self.max_contract_power) if charger_type else self.max_contract_power
            series: List[Dict[str, Any]] = []
            for ts, pred in zip(timestamps, predictions):
                clamped = float(np.clip(pred, 0, max_limit))
                series.append({
                    "timestamp": ts.isoformat(),
                    "predicted_peak_kw": round(clamped, 2)
                })

            return series[-max_points:]

        except Exception as exc:
            self.logger.warning("Session-level prediction failed: %s", exc, exc_info=True)
            backup_df = locals().get("working_df")
            if isinstance(backup_df, pd.DataFrame):
                try:
                    return self._session_series_baseline(backup_df)
                except Exception:
                    pass
            return []

    def _session_series_baseline(self, session_df: pd.DataFrame, window: int = 12) -> List[Dict[str, Any]]:
        """PyTorch 미사용 시 이동평균 기반 예측"""
        if session_df.empty:
            return []

        rolling = session_df["peak_kw"].rolling(window=window, min_periods=1).mean()
        results: List[Dict[str, Any]] = []
        for ts, value in rolling.items():
            if pd.isna(ts) or pd.isna(value):
                continue
            results.append({
                "timestamp": pd.Timestamp(ts).isoformat(),
                "predicted_peak_kw": round(float(value), 2)
            })
        return results

    def _compute_base_statistics(self, power_data: np.ndarray) -> Dict[str, float]:
        """기본 통계량 계산"""
        try:
            return {
                "mean": np.mean(power_data),
                "std": np.std(power_data),
                "min": np.min(power_data),
                "max": np.max(power_data),
                "q25": np.percentile(power_data, 25),
                "q50": np.percentile(power_data, 50),
                "q75": np.percentile(power_data, 75),
                "q90": np.percentile(power_data, 90),
                "q95": np.percentile(power_data, 95),
                "q98": np.percentile(power_data, 98),
                "q99": np.percentile(power_data, 99),
            }
        except Exception:
            return {
                "mean": 45.0, "std": 15.0, "min": 0.0, "max": 100.0,
                "q25": 35.0, "q50": 45.0, "q75": 55.0, "q90": 65.0,
                "q95": 70.0, "q98": 75.0, "q99": 80.0
            }

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

    def _fallback_prediction(self, station_id: str) -> EnsemblePrediction:
        """폴백 예측 (데이터 부족 시)"""
        self.logger.warning(f"Using fallback prediction for station {station_id}")

        fallback_prediction = ModelPrediction(
            model_name="Fallback_Default",
            predicted_value=45.0,
            confidence_interval=(35.0, 55.0),
            confidence_score=0.5,
            method_details={
                "method": "Default Fallback",
                "reason": "Insufficient data",
                "description": "기본값 사용 (데이터 부족)"
            }
        )

        return EnsemblePrediction(
            final_prediction=45,
            raw_prediction=45.0,
            model_predictions=[fallback_prediction],
            ensemble_method="fallback",
            weights={"Fallback_Default": 1.0},
            uncertainty=20.0,
            visualization_data=self._prepare_visualization_data(
                [fallback_prediction],
                45.0
            )
        )

    def train_model(
        self,
        training_data: pd.DataFrame,
        epochs: int = 50,
        batch_size: int = 32,
        validation_split: float = 0.2,
        learning_rate: float = 0.001
    ) -> Dict[str, Any]:
        """
        PyTorch LSTM 모델 학습

        Args:
            training_data: 학습 데이터 (컬럼: 순간최고전력 필수)
            epochs: 학습 에포크 수
            batch_size: 배치 크기
            validation_split: 검증 데이터 비율
            learning_rate: 학습률

        Returns:
            학습 히스토리
        """
        if not PYTORCH_AVAILABLE:
            self.logger.error("PyTorch not available. Cannot train LSTM model.")
            return {"success": False, "error": "PyTorch not installed"}

        if self.model is None:
            self._build_model()

        try:
            # 데이터 전처리
            power_data = self._preprocess_data(training_data)

            if len(power_data) < self.sequence_length * 2:
                return {
                    "success": False,
                    "error": f"Insufficient data. Need at least {self.sequence_length * 2} points"
                }

            # 특징 추출
            features = self._extract_features(training_data, power_data)

            # 시퀀스 생성
            X, y = self._create_sequences(features)

            if len(X) == 0:
                return {"success": False, "error": "Failed to create sequences"}

            # Train/Validation split
            split_idx = int(len(X) * (1 - validation_split))
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            # PyTorch 텐서로 변환
            X_train_tensor = torch.FloatTensor(X_train)
            y_train_tensor = torch.FloatTensor(y_train).unsqueeze(1)
            X_val_tensor = torch.FloatTensor(X_val)
            y_val_tensor = torch.FloatTensor(y_val).unsqueeze(1)

            # DataLoader 생성
            train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
            val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
            
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

            # 손실 함수 및 옵티마이저
            criterion = nn.MSELoss()
            optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
            scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                optimizer, mode='min', factor=0.5, patience=5, min_lr=0.00001
            )

            # 학습 히스토리
            history = {
                'train_loss': [],
                'val_loss': [],
                'train_mae': [],
                'val_mae': []
            }

            best_val_loss = float('inf')
            patience_counter = 0
            early_stop_patience = 10

            self.logger.info(f"Training PyTorch LSTM with {len(X_train)} sequences")

            # 학습 루프
            for epoch in range(epochs):
                # Training
                self.model.train()
                train_loss = 0.0
                train_mae = 0.0
                
                for batch_X, batch_y in train_loader:
                    if self.device:
                        batch_X = batch_X.to(self.device)
                        batch_y = batch_y.to(self.device)
                    
                    # Forward pass
                    optimizer.zero_grad()
                    outputs = self.model(batch_X)
                    loss = criterion(outputs, batch_y)
                    
                    # Backward pass
                    loss.backward()
                    optimizer.step()
                    
                    train_loss += loss.item()
                    train_mae += torch.mean(torch.abs(outputs - batch_y)).item()
                
                train_loss /= len(train_loader)
                train_mae /= len(train_loader)
                
                # Validation
                self.model.eval()
                val_loss = 0.0
                val_mae = 0.0
                
                with torch.no_grad():
                    for batch_X, batch_y in val_loader:
                        if self.device:
                            batch_X = batch_X.to(self.device)
                            batch_y = batch_y.to(self.device)
                        
                        outputs = self.model(batch_X)
                        loss = criterion(outputs, batch_y)
                        
                        val_loss += loss.item()
                        val_mae += torch.mean(torch.abs(outputs - batch_y)).item()
                
                val_loss /= len(val_loader)
                val_mae /= len(val_loader)
                
                # 히스토리 저장
                history['train_loss'].append(train_loss)
                history['val_loss'].append(val_loss)
                history['train_mae'].append(train_mae)
                history['val_mae'].append(val_mae)
                
                # Learning rate scheduling
                scheduler.step(val_loss)
                
                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                else:
                    patience_counter += 1
                
                if patience_counter >= early_stop_patience:
                    self.logger.info(f"Early stopping at epoch {epoch+1}")
                    break
                
                # 로그 출력 (10 epoch마다)
                if (epoch + 1) % 10 == 0:
                    self.logger.info(
                        f"Epoch {epoch+1}/{epochs} - "
                        f"train_loss: {train_loss:.4f}, val_loss: {val_loss:.4f}, "
                        f"train_mae: {train_mae:.4f}, val_mae: {val_mae:.4f}"
                    )

            self.logger.info(
                f"Training completed: "
                f"final_train_loss={history['train_loss'][-1]:.4f}, "
                f"final_val_loss={history['val_loss'][-1]:.4f}, "
                f"final_mae={history['val_mae'][-1]:.4f}"
            )

            return {
                "success": True,
                "final_loss": float(history['train_loss'][-1]),
                "final_val_loss": float(history['val_loss'][-1]),
                "final_mae": float(history['val_mae'][-1]),
                "epochs_trained": len(history['train_loss']),
                "training_samples": len(X_train),
                "history": history
            }

        except Exception as e:
            self.logger.error(f"Model training failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def predict_energy_demand(
        self,
        data: pd.DataFrame,
        station_id: str,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        에너지 수요 예측 (기존 메서드 유지 - 하위 호환성)
        """
        try:
            if data.empty:
                return {
                    "success": False,
                    "message": "데이터가 없습니다.",
                    "station_id": station_id
                }

            energy_col = "충전전력량(kWh)"
            if energy_col not in data.columns:
                return {
                    "success": False,
                    "message": "에너지 데이터 컬럼이 없습니다.",
                    "station_id": station_id
                }

            energy_data = data[energy_col].dropna()
            if len(energy_data) == 0:
                return {
                    "success": False,
                    "message": "유효한 에너지 데이터가 없습니다.",
                    "station_id": station_id
                }

            # 기본 통계
            daily_avg = energy_data.mean()
            daily_max = energy_data.max()
            daily_min = energy_data.min()

            # 예측
            forecast_daily = daily_avg
            forecast_total = forecast_daily * days

            # 신뢰구간
            std = energy_data.std()
            ci_lower = max(0, forecast_daily - 1.96 * std)
            ci_upper = forecast_daily + 1.96 * std

            return {
                "success": True,
                "station_id": station_id,
                "forecast_period_days": days,
                "daily_forecast": {
                    "average": round(float(forecast_daily), 2),
                    "min": round(float(daily_min), 2),
                    "max": round(float(daily_max), 2),
                    "confidence_interval": {
                        "lower": round(float(ci_lower), 2),
                        "upper": round(float(ci_upper), 2)
                    }
                },
                "total_forecast": {
                    "kwh": round(float(forecast_total), 2),
                    "confidence_interval": {
                        "lower": round(float(ci_lower * days), 2),
                        "upper": round(float(ci_upper * days), 2)
                    }
                },
                "data_quality": {
                    "sample_size": len(energy_data),
                    "data_range_days": (data.index.max() - data.index.min()).days if len(data) > 1 else 0
                },
                "method": "pytorch_lstm_enhanced" if self.model else "statistical_average"
            }

        except Exception as e:
            self.logger.error(f"Energy demand prediction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "station_id": station_id
            }
