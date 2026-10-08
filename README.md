
# 충전소 전력 수요 예측 플랫폼

EV 충전소의 전력 수요를 예측하고, 최적의 계약전력과 비용 절감 방안을 추천하는 AI 기반 통합 플랫폼

## 빠른 시작

### 1단계: 시스템 요구사항 확인
```bash
# Python 3.10+ 필요 (운영 컨테이너는 python:3.11-slim 사용)
python3 --version

# Node.js 18+ 필요 (프론트엔드 빌드 컨테이너는 node:18-alpine 사용)
node --version
npm --version
```

Node가 설치되어 있지 않다면 배포판에 맞게 설치하세요.
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y nodejs npm

# Fedora/RHEL
sudo dnf install -y nodejs npm

# 크로스플랫폼 (권장) — nvm 사용
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 18 && nvm use 18
```

### 2단계: 의존성 설치 & 환경변수 준비
```bash
# (프로젝트 루트에서) 환경변수 파일 생성 — SECRET_KEY, ALLOWED_ORIGINS 등은 실행 전 반드시 수정
cp .env.production .env

# 백엔드 의존성 설치
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # torch, xgboost 포함

# 프론트엔드 의존성 설치
cd ../frontend
npm install   # 재현성을 위해서는 `npm ci` 권장
```

> **GPU(LSTM 학습 가속)를 쓰려면**: `pip install torch` 기본 빌드는 설치된 NVIDIA 드라이버와 CUDA 버전이 맞아야 GPU가 활성화됩니다. 드라이버보다 높은 CUDA 빌드가 깔리면 `torch.cuda.is_available()` 가 `False` 가 됩니다. 예) 드라이버가 CUDA 12.x 면 cu124 빌드를 설치:
> ```bash
> pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu124
> python -c "import torch; print(torch.cuda.is_available())"   # True 확인
> ```
> GPU가 없거나 미설치여도 CPU로 정상 동작합니다(학습/추론 가능, 속도만 차이).

### 3단계: 서버 실행 (Linux)
```bash
# 백엔드 서버 (별도 터미널 1)
cd backend
source .venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 32375 --reload

# 프론트엔드 서버 (별도 터미널 2)
cd frontend
npm run dev
```
---

### CSV 데이터 준비

충전 이력은 보통 월 단위로 내려받게 되는데(엑셀/CSV), **그대로 올리면 안 되고 전처리가 필요**합니다.

```bash
# 1) 월별 원본 파일(.xlsx/.csv)을 data/train_data/ 에 모은다
mkdir -p data/train_data
cp 충전이력리스트_*.xlsx data/train_data/

# 2) 병합 + 전역 중복 제거 → 단일 학습/업로드용 CSV 생성
cd backend && source .venv/bin/activate
python preprocess_train_data.py
#  → data/processed/charging_merged.csv 생성
#    (상단 제목행 제거, 충전기ID+시작/종료시각 기준 전역 dedup, 시간순 정렬)

# 3) 생성된 CSV 를 활성 데이터로 사용
#    - 웹 UI 업로드(대시보드 → CSV 업로드), 또는
#    - data/raw/ 에 복사 후 .active_csv 마커에 파일명 기록
```

> ⚠️ **업로드는 "교체"이지 "병합"이 아닙니다.** 새로 올린 CSV 가 기존 데이터를 대체합니다. **새 월만 올리면 이전 데이터가 모두 사라지므로**, 항상 **처음~최신 월 전체를 포함한 누적 CSV** 를 올려야 합니다(위 전처리로 생성).
>
> - 업로드 한도: **100MB** (앱 + nginx `client_max_body_size` 동일).
> - 업로드 직후 **이전 예측(DB+JSON)이 자동 초기화**된 뒤 전 충전소가 새 데이터로 재예측됩니다(stale 방지).
> - 예측 대상 핵심 컬럼인 **`순간최고전력` 은 데이터에 따라 특정 시점(예: 2024-09)부터만 기록**될 수 있습니다. 그 이전 행은 전력값이 0 이라 학습/예측에서 자동 제외됩니다.

### 접속 정보
- API 서버: `http://127.0.0.1:32375` (로컬)
- API 문서: `/docs` (Swagger UI), `/redoc` (ReDoc)
- 헬스체크: `/health`
- 프론트엔드: `http://localhost:5173` (개발)
- 대시보드: `/dashboard/{stationId}`

##  주요 기능 및 아키텍처


###  동적 패턴 분석 & 앙상블 예측
- **Dynamic Pattern**: 실제 데이터에서 계절/요일/시간대별 패턴 자동 추출, 신뢰도 기반 적응형 예측
- **Ensemble AI**: LSTM(PyTorch) + XGBoost + 통계모델 8종 앙상블, 계약전력/비용/위험도 예측
- **극값 분석(EVT)**: GEV·GPD 분포 기반 극단 피크 확률 추정 (`backend/app/prediction/models/extreme_value_models.py`)
- **확률·비용 시뮬레이션**: 과소/최적/과다/현재/사용자 지정 계약별 연간 비용, 초과·낭비 확률 분석
- **P50·P90 예측 시각화**: 일별 예측 중앙값(P50)과 상위 10% 수준(P90)을 구분해 표시, 80% 신뢰구간 음영 제공
- **실시간 대시보드**: Chart.js 기반 예측/비용/위험도 시각화, 다크모드, 반응형 UI
- **모델 검증 API**: `/api/stations/{station_id}/model-validation` 로 백테스트 결과 확인 가능

###  계약전력 추천
- 데이터 기반 최적 계약전력 산출
- 안전 마진 자동 적용
- 월별 변동성 고려

###  비용 및 초과금 산정 기준
- **총 비용(연간)** = `(계약전력 kW × 기본요금 8,320원 × 12개월) + (예상 초과전력 kW × 8,320원 × 1.5 × 12개월)`
	- 첫 항은 계약전력에 대한 연간 기본요금입니다.
	- 두 번째 항은 예측된 피크가 계약전력을 넘는 경우에만 발생하는 **초과 부가금(KEPCO 벌금)** 으로, `backend/app/contract/cost_calculator.py` 의 `KEPCOCostCalculator.calculate_monthly_cost`와 동일한 식을 따릅니다.
- **예상 초과금** = `예상 초과전력 kW × 8,320원 × 1.5 × 12개월`
	- 대시보드의 “예상 초과금” 열은 위 벌금 항만 분리해 보여주며, `peak_kw`가 계약전력을 초과할 확률과 초과 폭을 기반으로 산출됩니다.
- **예상 위험 기여도** = `연간 초과 부가금 × 과소(부족) 발생 확률`
	- 과소 확률(예: 계약전력 부족 위험)이 높을수록 해당 초과금의 기대값이 커지므로, UI에서는 이 값을 위험지표로 함께 노출합니다.

> 참고: 위 식들은 ⚙️ `KEPCOCostCalculator` ( `backend/app/contract/cost_calculator.py` )에서 사용되는 상수 `BASIC_RATE_PER_KW = 8320`과 `OVERAGE_PENALTY_RATE = 1.5`를 그대로 반영합니다. 프런트엔드의 툴팁/도움말과 문서화에도 동일한 수치를 사용해 일관성을 유지하세요.

###  실시간 대시보드
- 인터랙티브 차트 및 그래프 (Chart.js + date-fns + zoom/annotation 플러그인)
- 계약전력 최적화 차트에 **일별 예측 P50(중앙값, 하늘색 실선)** 과 **P90(상위 10%, 분홍 점선)** 을 동시 표시해 "기대치 vs 상한"을 한눈에 비교
- P10 ~ P90 음영 밴드로 80% 신뢰구간 시각화
- 계약선(수동·현재·앙상블 P95) 주석, 마우스 휠/드래그 줌
- 다크모드, 반응형 웹 디자인


##  시스템 아키텍처


```
┌────────────────────────────────────────────────────────────┐
│                Power Demand Prediction Platform            │
├────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │
│  │   Frontend    │  │   Backend     │  │   Data Layer  │   │
│  │ (SvelteKit)   │◄─┼─►(FastAPI)    │◄─┼─►(CSV/DB)     │   │
│  │  • 대시보드     │  │  • REST API   │  │  • 충전 이력    │   │
│  │  • 비용분석     │  │  • 예측엔진     │  │  • 파일저장     │   │
│  │  • 위험분석     │  │  • AI모델      │  │  • 캐시        │   │
│  │  • 관리도구     │  │  • 패턴분석     │  │               │   │
│  └───────────────┘  └───────────────┘  └───────────────┘   │
└────────────────────────────────────────────────────────────┘
```


##  기술 스택


### Backend
- **FastAPI**: 고성능 Python 웹 프레임워크
- **PyTorch**: LSTM 딥러닝 예측 (GPU 지원)
- **XGBoost**: 부스팅 기반 예측
- **Pandas/NumPy/SciPy**: 데이터 분석/통계/극값 이론
- **Uvicorn**: ASGI 서버

### Frontend
- **SvelteKit**: 모던 웹 프레임워크
- **Chart.js**: 인터랙티브 차트
- **Tailwind CSS**: 유틸리티 CSS 프레임워크

### DevOps/Infra
- **Docker/Docker Compose**: 멀티 컨테이너 관리


##  프로젝트 구조

```
power-demand-prediction-platform/
├── backend/                      # 백엔드 API 서버
│   ├── app/
│   │   ├── api/                 # FastAPI 라우트 (routes.py, batch.py)
│   │   ├── contract/            # 계약전력 최적화·비용 계산·추천 엔진
│   │   │   ├── cost_calculator.py       # KEPCO 기본요금·초과금 산정
│   │   │   ├── optimizer.py             # 최적 계약 탐색
│   │   │   └── recommendation_engine.py # 일별 피크 예측(P10/P50/P90/P95)
│   │   ├── core/                # 설정/로깅
│   │   ├── data/                # CSV 로더/검증
│   │   ├── models/              # 공용 스키마/모델 정의
│   │   ├── prediction/          # 예측 엔진 (LSTM/XGBoost/앙상블)
│   │   │   ├── ensemble_prediction_engine.py
│   │   │   ├── lstm_prediction_engine.py
│   │   │   ├── xgboost_prediction_engine.py
│   │   │   └── models/          # EVT(GEV/GPD) 극값 모델
│   │   ├── services/            # 비즈니스 로직 (station, metrics, chart)
│   │   ├── storage/             # 예측 결과 저장/캐시
│   │   └── main.py              # 앱 진입점
│   ├── preprocess_train_data.py # 월별 원본 병합 + 전역 중복제거 → 단일 CSV
│   ├── train_lstm_model.py      # LSTM 학습/재학습 (GPU 지원)
│   ├── train_xgboost_model.py   # XGBoost 학습/재학습
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                     # 프론트엔드 (SvelteKit)
│   ├── src/
│   │   ├── components/          # Dashboard, BatchProgress, FileUpload 등
│   │   ├── lib/                 # 공용 타입/유틸
│   │   ├── routes/              # 페이지 라우트 (/dashboard/[stationId])
│   │   ├── services/            # API 통신
│   │   ├── stores/              # Svelte store (stationStore 등)
│   │   └── styles/              # 글로벌 스타일
│   └── package.json
├── data/                         # 데이터 저장소
│   ├── train_data/              # 월별 원본 파일(.xlsx/.csv) — 전처리 입력
│   ├── processed/               # 병합·중복제거된 단일 CSV (전처리 출력)
│   ├── raw/                     # 활성 CSV + .active_csv 마커 (앱이 읽는 데이터)
│   ├── predictions.db           # 예측 결과 SQLite DB
│   └── predictions/             # 예측 결과 JSON 백업
├── logs/                         # 로그 파일
├── static/                       # 정적 에셋(랜딩 등)
├── .env.production              # 운영 환경변수 템플릿
└── docker-compose.yml           # 컨테이너 설정 (backend / frontend / prometheus[optional])
```


##  환경 설정 및 보안

###  주요 환경변수


시스템은 민감한 정보를 환경변수로 관리합니다. (API 키 인증, CORS, 파일 업로드 제한 등 보안 권고 적용 필요)

```bash
# 서버 설정
BACKEND_HOST=0.0.0.0
BACKEND_PORT=32375
FRONTEND_PORT=32376
BACKEND_URL=http://127.0.0.1:32375       # 프론트 → 백엔드 호출 기준 URL
ENVIRONMENT=development                   # development | production
LOG_LEVEL=INFO

# CORS — 쉼표로 구분된 허용 Origin 목록
ALLOWED_ORIGINS=http://localhost:5173

# 보안 설정 — 운영 전 반드시 강력한 값으로 교체
SECRET_KEY=your_secret_key_here_change_in_production

# 성능/데이터 설정
CACHE_TTL=300                     # API 응답 캐시 수명(초)
MAX_SESSIONS_PER_QUERY=10000      # 단일 쿼리 최대 세션 수
DEFAULT_DAYS_LOOKBACK=90          # 기본 분석 기간(일)
UVICORN_WORKERS=4                 # ASGI 워커 수
```

###  환경별 설정 파일

- **`.env.production`**: 프로덕션 환경 템플릿 (저장소 포함)
- **`.env`**: 개발/운영용 실행 파일 — 아래 명령으로 템플릿에서 생성
  ```bash
  cp .env.production .env
  # 이후 SECRET_KEY, ALLOWED_ORIGINS 등 실제 값으로 수정
  ```
- **`frontend/.env`**: 프론트엔드 전용 설정 (선택)

###  환경별 실행

```bash
# Linux
cd backend && source .venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 32375 --reload
```


##  주요 API 엔드포인트

전체 스펙은 운영 중인 서버의 `/docs` (Swagger UI) 에서 확인 가능합니다.

###  데이터 관리
- `GET  /api/stations` — 충전소 목록
- `GET  /api/station-analysis/{station_id}` — 충전소 기본 분석(패턴/통계)
- `GET  /api/data-range/{station_id}` — 해당 충전소의 데이터 기간
- `GET  /api/admin/active-csv-info` — **현재 활성 CSV 의 전체 데이터 기간**(시작·종료일·행수). 대시보드 업로드 영역 아래 표시에 사용
- `GET  /api/stations/{station_id}/timeseries` — 시계열 데이터(JSON)
- `GET  /api/stations/{station_id}/timeseries.csv` — 시계열 데이터(CSV 다운로드)
- `POST /api/admin/upload-csv` — CSV 업로드 (인증 필요 권고). 업로드 시 **기존 예측 자동 초기화 → 백그라운드 일괄 예측**이 시작됨
- `POST /api/admin/refresh-cache` — 캐시 강제 갱신
- `POST /api/admin/clear-data` — 데이터 초기화 (주의)
- `GET  /api/status` — 시스템 상태
- `GET  /health` — 헬스체크 (Docker healthcheck에서 사용)

###  예측/분석 서비스
- `GET /api/stations/{station_id}/ensemble-prediction?current_contract_kw=100` — LSTM+XGBoost 앙상블 예측, 계약전력/비용/위험도/성숙도 분석
- `GET /api/stations/{station_id}/prediction` — 동적 패턴 기반 최고전력 예측 (Dynamic+SARIMA)
- `GET /api/predict/{station_id}` — 단순 예측 요약 (구버전 호환)
- `GET /api/stations/{station_id}/contract-analysis` — 일별 피크 분포(P10/P50/P90/P95) + 계약전력 추천 상세
- `GET /api/stations/{station_id}/monthly-contract` — 월별 계약전력 추천
- `GET /api/stations/{station_id}/energy-demand-forecast` — 에너지 수요 예측
- `GET /api/stations/{station_id}/model-validation` — 앙상블 모델 백테스트 검증 결과


##  모델 학습 및 재학습

학습된 LSTM/XGBoost 모델은 `backend/app/prediction/models/` 에 저장되어 있고, 서비스는 부팅 시 이 모델을 로드해 **추론만** 합니다 (CSV 업로드/예측 실행 시 가중치는 갱신되지 않습니다). 새 데이터를 반영하려면 아래 스크립트로 명시적으로 재학습해야 합니다.

> **0단계 — 데이터 전처리 먼저**: 학습 입력도 업로드용 CSV 와 마찬가지로 **병합·중복제거된 단일 CSV** 여야 합니다. 월별 원본을 `data/train_data/` 에 모으고 `python preprocess_train_data.py` 로 `data/processed/charging_merged.csv` 를 만든 뒤, 그 경로를 `--data-path` 로 넘기세요.
>
> **GPU**: `train_lstm_model.py` 는 GPU 가 활성화돼 있으면(`torch.cuda.is_available() == True`) 자동으로 GPU 에서 학습합니다. 미설치/미활성 시 CPU 로 진행됩니다(빠른 시작의 GPU 설치 안내 참고).

###  학습 스크립트

| 스크립트 | 모델 | 출력 경로 |
|---|---|---|
| `backend/train_xgboost_model.py` | XGBoost | `app/prediction/models/xgboost_trained/` |
| `backend/train_lstm_model.py`    | LSTM    | `app/prediction/models/lstm_trained/` |

두 스크립트는 동일한 CLI 패턴을 사용합니다. 모든 명령은 `backend/` 디렉토리에서 venv 활성화 후 실행합니다.

```bash
# 공통 옵션
--data-path PATH            # 학습용 CSV. 생략 시 data/raw/ 의 최신 CSV 자동 선택.
--window-months N           # 슬라이딩 윈도우 크기. 생략 시 전체 데이터 사용.
--model-save-path DIR       # 저장 디렉토리.
--validation-split FLOAT    # 검증 비율 (XGBoost, 기본 0.2)
--top-n-stations N          # 상위 N개 충전소 사용 (LSTM, 기본 10)
--epochs N                  # 에포크 (LSTM, 기본 50)
--batch-size N              # 배치 크기 (LSTM, 기본 32)
```

###  사용 예시

```bash
# 1) 첫 학습 — 전체 데이터로 기준 모델 생성
python train_xgboost_model.py
python train_lstm_model.py

# 2) 슬라이딩 윈도우 재학습 (월 1회 운영 권장 패턴)
python train_xgboost_model.py --window-months 12
python train_lstm_model.py    --window-months 12

# 3) 다른 CSV 명시 + 18개월 윈도우
python train_xgboost_model.py \
    --data-path ../data/raw/충전이력.csv \
    --window-months 18

# 4) LSTM 튜닝 (상위 20개 충전소, 에포크 100)
python train_lstm_model.py \
    --window-months 12 \
    --top-n-stations 20 \
    --epochs 100 \
    --batch-size 64

# 5) 모델 버저닝 — 윈도우별 별도 디렉토리에 저장
python train_xgboost_model.py \
    --window-months 12 \
    --model-save-path app/prediction/models/xgboost_w12
```

###  슬라이딩 윈도우 동작 방식

```python
# 데이터 내 최신 날짜를 기준으로 N개월 컷오프
latest_date = df['충전시작일시'].max()
cutoff      = latest_date - pd.DateOffset(months=window_months)
df_filtered = df[df['충전시작일시'] >= cutoff]
```

**`datetime.now()` 가 아니라 데이터 내 최신 날짜 기준인 이유**: 데이터가 며칠~몇 주 지연되어 들어와도 항상 데이터 기준 최근 N개월이 잘리므로 안정적이고, 과거 시점 백테스트에서도 일관되게 동작.

학습 시 예상 로그:
```
슬라이딩 윈도우 적용: 최근 12개월 (2025-06-01 ~ 2026-06-01)
  - 필터 전: 129,359개 → 필터 후: 76,431개 (59.1% 잔존)
```

###  운영 권장 패턴

| 시점 | 권장 명령 | 윈도우 |
|---|---|---|
| 첫 배포 | `python train_*.py` | 없음 (전체) |
| 월 1회 정기 재학습 | `--window-months 12` | 12개월 |
| 분기 1회 정기 재학습 | `--window-months 18` | 18개월 |
| 요금제·정책 급변 직후 | `--window-months 6` | 6개월 (짧은 윈도우로 빠른 적응) |
| 데이터 < 1년 누적 | 전체 데이터 | 없음 |

```bash
# cron 등록 예시 — 매월 1일 03:00 자동 재학습
0 3 1 * * cd /path/to/backend && \
    /path/to/venv/bin/python train_xgboost_model.py --window-months 12 && \
    /path/to/venv/bin/python train_lstm_model.py    --window-months 12
```

###  안전장치

| 상황 | 동작 |
|---|---|
| `--window-months` 생략 또는 0 | 전체 데이터 사용 (기존 동작 유지) |
| 필터 후 데이터가 비어있음 | `ValueError` 즉시 발생 + 명확한 메시지 |
| 필터 후 데이터 < 1,000건 | `WARNING` 로그 + 학습은 계속 진행 |
| `--data-path` 잘못된 경로 | `FileNotFoundError` |
| CSV 인코딩 불일치 | utf-8 → utf-8-sig → cp949 → euc-kr 순차 fallback |
| 학습 실패 | exit code 1 종료 (cron 실패 감지 가능) |

###  재학습 후 적용

학습 스크립트는 `backend/app/prediction/models/` 의 가중치 파일을 덮어씁니다. 새 모델을 서비스에 반영하려면 **백엔드 프로세스를 재시작**해야 합니다 (부팅 시 모델 로드).

```bash
# 재학습 → 백엔드 재시작
python train_xgboost_model.py --window-months 12
python train_lstm_model.py    --window-months 12
# 백엔드 재시작 (예: systemd)
sudo systemctl restart power-demand-backend
```

서비스 무중단 갱신이 필요하면 `--model-save-path` 로 임시 디렉토리에 학습한 뒤 검증을 거쳐 production 디렉토리로 교체하는 방식이 안전합니다.


##  문제 해결 & 디버깅


###  자주 발생하는 문제

#### 1. 패키지 의존성 오류
**증상**: `ModuleNotFoundError: No module named 'fastapi'`
**해결책**:
```bash
# venv 활성화 확인
cd backend
source .venv/bin/activate
python -c "import fastapi; print(fastapi.__version__)"

# 의존성 재설치
pip install -r requirements.txt

# 개별 패키지 수동 설치
pip install fastapi pandas numpy uvicorn
```

#### 간단한 동작 확인 (진단 대체)
```bash
# 헬스체크 + 충전소 목록 조회로 기본 동작 확인
curl http://127.0.0.1:32375/health
curl http://127.0.0.1:32375/api/stations
curl "http://127.0.0.1:32375/api/stations/BNS0001/ensemble-prediction?current_contract_kw=100"
```

#### 2. CSV 파일 인식 오류
**증상**: "충전소 데이터를 로드할 수 없습니다"
**해결책**:
```bash
# 1. CSV 파일 위치 확인
ls -la data/raw/

# 2. CSV 파일 인코딩 확인 (UTF-8 권장)
file -i data/raw/your_file.csv

# 3. 웹 UI에서 재업로드
```

#### 3. 포트 충돌
**증상**: "Address already in use"
**해결책**:
```bash
# 포트 사용 확인
netstat -tulpn | grep :32375  # Linux
netstat -ano | findstr :32375  # Windows

# 기본 포트 사용
uvicorn app.main:app --host 0.0.0.0 --port 32375
```

#### 4. 메모리 부족
**증상**: 대용량 CSV 처리 시 느린 성능
**해결책**:
- `.env` (없으면 `cp .env.production .env`) 에서 `MAX_SESSIONS_PER_QUERY=5000` 으로 제한
- `CACHE_TTL` 을 늘려 반복 요청 부하 감소
- CSV 파일을 작은 단위로 분할
- 메모리 사용량 모니터링 (`docker stats` 또는 `htop`)

###  디버깅 가이드

#### 로그 확인
```bash
# 실시간 로그 확인
tail -f logs/main.log

# 에러만 필터링
grep ERROR logs/main.log
```

#### JavaScript 디버깅
```javascript
// 브라우저 콘솔에서 디버그 정보 확인
window.dashboardDebug.currentData()
window.dashboardDebug.charts()

// 네트워크 오류 시뮬레이션
window.dashboardDebug.simulateError('network')
```

###  성능 최적화

#### 1. 인메모리 캐시 튜닝 (기본 내장)
- `.env` 의 `CACHE_TTL=300` (초) 로 응답 캐시 수명 조절
- `MAX_SESSIONS_PER_QUERY` 를 낮춰 대용량 충전소의 단일 쿼리 부하 완화

#### 2. 워커 수 조정
- `UVICORN_WORKERS` (기본 4) — CPU 코어 수에 맞춰 조정
- 프로덕션에서는 `2 × CPU + 1` 를 권장

#### 3. 선택적 확장 (docker-compose.yml 주석 해제 후 사용)
- **PostgreSQL**: 대용량 이력을 DB로 전환하려면 `docker-compose.yml` 의 `db` 섹션 활성화
- **Redis**: 공유 캐시가 필요하면 `redis` 섹션 활성화 후 별도 연동 구현 필요
- **Prometheus**: `docker compose --profile monitoring up -d` 로 활성화 (설정: `backend/app/monitoring/prometheus.yml`)

#### 4. 모니터링
```python
# 성능 로깅 활성화
import logging
logging.getLogger("performance").setLevel(logging.INFO)
```


##  데이터/CSV 형식

### CSV 파일 요구사항
```csv
충전소ID,충전시작일시,충전종료일시,순간최고전력,충전량
BNS0001,2024-01-01 09:00:00,2024-01-01 10:30:00,45.2,28.5
BNS0001,2024-01-01 14:20:00,2024-01-01 15:45:00,52.1,32.8
```

#### 필수 컬럼
- **충전소ID**: 충전소 고유 식별자
- **충전시작일시**: 충전 시작 시간 (YYYY-MM-DD HH:MM:SS)
- **순간최고전력**: 충전 중 최대 전력 (kW)

#### 선택 컬럼
- **충전종료일시**: 충전 종료 시간
- **충전량**: 총 충전량 (kWh)
- **충전소명**: 충전소 이름

###  백엔드 라이브러리 버전 (requirements.txt 기준)

현재 백엔드는 최소 버전 제약(`>=`)으로 관리됩니다.

| 패키지 | 버전 정책 |
|---|---|
| pandas | >=2.0.0 |
| numpy | >=1.24.0 |
| scipy | >=1.10.0 |
| fastapi | >=0.104.0 |
| uvicorn[standard] | >=0.24.0 |
| pydantic | >=2.4.0 |
| python-multipart | >=0.0.6 |
| apscheduler | >=3.10.4 |
| httpx | >=0.25.0 |
| statsmodels | >=0.14.0 |
| torch | >=2.0.0 |
| xgboost | >=2.0.0 |
| scikit-learn | >=1.3.0 |
| python-dotenv | >=1.0.0 |
| python-dateutil | >=2.8.0 |
| pyyaml | >=6.0.1 |
| loguru | >=0.7.2 |
| openpyxl | >=3.1.0 |
| xlrd | >=2.0.1 |
| pytest | >=7.4.0 |
| pytest-asyncio | >=0.21.0 |
| pytest-cov | >=4.1.0 |
| black | >=23.0.0 |
| flake8 | >=6.0.0 |
| mypy | >=1.6.0 |

운영 재현성을 높이려면 신규 서버 배포 전에 아래처럼 고정 버전 파일 생성 권장:
```bash
cd backend
pip freeze > requirements.lock.txt
```

---

###  프론트엔드 라이브러리 버전 (현재 설치 기준)

`frontend/package-lock.json` 및 `npm ls --depth=0` 기준:

| 패키지 | 설치 버전 |
|---|---|
| @sveltejs/adapter-static | 3.0.9 |
| @sveltejs/kit | 2.33.0 |
| @sveltejs/vite-plugin-svelte | 3.1.2 |
| svelte | 4.2.20 |
| svelte-check | 3.8.6 |
| svelte-preprocess | 6.0.3 |
| vite | 5.4.19 |
| typescript | 5.9.2 |
| postcss | 8.5.6 |
| autoprefixer | 10.4.21 |
| chart.js | 4.5.1 |
| chartjs-adapter-date-fns | 3.0.0 |
| chartjs-plugin-annotation | 3.1.0 |
| chartjs-plugin-zoom | 2.2.0 |
| date-fns | 4.1.0 |
| hammerjs | 2.0.8 |

참고:
- `frontend/package.json`은 일부 패키지를 `^` 범위로 선언하므로, 설치 시점에 마이너/패치가 변할 수 있습니다.
- 동일 결과 재현을 위해 `npm ci` 사용을 권장합니다.

---

# 예측 결과 DB 저장 가이드

> `/api/stations/{id}/ensemble-prediction` 호출 시마다 예측 결과가 자동으로 SQLite DB에 저장됩니다. 이 문서는 **무엇이, 어디에, 어떻게 저장되는지**를 설명합니다.

---

## 1. 파일 위치 및 구조

```
power-demand-prediction-platform/
└── data/
    ├── predictions.db        ← 예측 결과 SQLite DB (이 문서의 대상)
    └── predictions/          ← 파일 백업 (JSON, 보조용)
```

DB 파일 한 개에 **6개 테이블**이 들어있습니다.

| 테이블 | 분류 | 용도 |
|---|---|---|
| `prediction_runs` | 정규화 (신규) | 예측 실행 메타 + 카드 요약 값 |
| `daily_predictions` | 정규화 (신규) | 일별 P10/P50/P90/P95 |
| `monthly_predictions` | 정규화 (신규) | 월별 집계 |
| `contract_scenarios` | 정규화 (신규) | 후보 계약별 시나리오 표 |
| `prediction_results` | 캐시 (기존) | 응답 전체를 JSON 한 컬럼에 저장 (내부 캐시용) |
| `batch_progress` | 캐시 (기존) | 배치 처리 진행 상태 |

> **외부 웹앱은 위 4개 정규화 테이블만 사용**하면 됩니다. `prediction_results` 는 내부 캐시 용도라 스키마가 자유롭게 바뀔 수 있습니다.

---

## 2. 테이블 상세

### 2.1 `prediction_runs` — 예측 실행 1건당 1행

요약 카드 3장(앙상블 P95 / 권장 계약 / 절감액)에 해당하는 핵심 값이 모두 들어있습니다.

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `id` | INTEGER PK | 실행 고유 ID (외부 키 참조 대상) |
| `station_id` | TEXT | 충전소 ID (예: `AAC0001`) |
| `run_at` | TEXT | 예측 실행 시각 (ISO 8601) |
| `model_version` | TEXT | 예: `Phase3_v1.1` |
| `charger_type` | TEXT | 충전기 타입 (급속/완속 등) |
| `maturity_level` | TEXT | `new` / `developing` / `mature` |
| `session_count` | INTEGER | 학습에 사용된 세션 수 |
| `current_contract_kw` | REAL | 사용자가 입력한 현재 계약전력 |
| `recommended_contract_kw` | REAL | 추천 계약전력 |
| `ensemble_p95_kw` | REAL | **카드: 앙상블 최종 예측 (P95)** |
| `ensemble_uncertainty_kw` | REAL | 모델 예측 표준편차 |
| `confidence_level` | REAL | 신뢰도 (0~1) |
| `predicted_peak_p50` | REAL | 예측 피크 중앙값 |
| `predicted_peak_p95` | REAL | 예측 피크 95백분위 |
| `annual_savings_krw` | REAL | **카드: 연간 예상 절감액 (원)** |
| `savings_percent` | REAL | 절감률 (%) |
| `overage_probability` | REAL | 초과 확률 (%) |
| `waste_probability` | REAL | 낭비 확률 (%) |
| `urgency_level` | TEXT | `high` / `medium` / `low` |
| `recommendation_summary` | TEXT | 자연어 요약 문장 |
| `is_latest` | INTEGER | **1 = 최신, 0 = 과거 실행** |
| `created_at` | TEXT | DB 저장 시각 |

### 2.2 `daily_predictions` — 일별 시계열

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `run_id` | INTEGER FK | `prediction_runs.id` 참조 |
| `prediction_date` | TEXT | 예측 대상 날짜 (`YYYY-MM-DD`) |
| `p10` | REAL | 하위 10% 분위 (kW) |
| `p50` | REAL | 중앙값 (kW) — 그래프 분홍 실선 |
| `p90` | REAL | 상위 90% 분위 (kW) |
| `p95` | REAL | 상위 95% 분위 (kW) |

> 세션 단위 예측 시계열을 **날짜별로 집계**해서 생성합니다.

### 2.3 `monthly_predictions` — 월별 요약

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `run_id` | INTEGER FK | `prediction_runs.id` 참조 |
| `year_month` | TEXT | `YYYY-MM` |
| `peak_p50` | REAL | 그 달 일별 P50 중 **최댓값** |
| `peak_p95` | REAL | 그 달 일별 P95 중 최댓값 |
| `p10_avg` / `p90_avg` | REAL | 그 달 신뢰구간 평균 |
| `day_count` | INTEGER | 데이터가 있는 일수 |
| `is_max_month` | INTEGER | 6개월 중 최고 피크 월이면 1 |

> `daily_predictions` 에서 자동 파생됩니다.

### 2.4 `contract_scenarios` — 시나리오 비교표 1줄당 1행

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `run_id` | INTEGER FK | `prediction_runs.id` 참조 |
| `contract_kw` | REAL | 후보 계약전력 (30 ~ 150kW) |
| `scenario_label` | TEXT | `과소` / `최적` / `과다` |
| `expected_annual_cost` | REAL | 연간 기대 비용 |
| `monthly_basic_fee` | REAL | 월 기본요금 = `contract_kw × 8,320` |
| `overage_probability` | REAL | 초과 확률 (%) |
| `waste_probability` | REAL | 낭비 확률 (%) |
| `risk_score` | REAL | 리스크 점수 (낮을수록 좋음) |
| `is_recommended` | INTEGER | 추천된 행이면 1 |

---

## 3. 저장 트리거: 언제, 어떻게 쓰여지나

```
[웹/외부] GET /api/stations/{station_id}/ensemble-prediction
    │
    ▼
[routes.py] 앙상블 예측 + 시나리오 생성 → result dict
    │
    ▼
[StorageManager.save_prediction(station_id, result)]
    │
    ├─→ ① prediction_results 에 JSON blob 저장 (캐시)
    │
    ├─→ ② save_normalized_prediction()
    │       ├─ 같은 station_id 의 기존 row → is_latest = 0
    │       ├─ prediction_runs INSERT (is_latest = 1)
    │       ├─ daily_predictions 일괄 INSERT
    │       ├─ monthly_predictions 일괄 INSERT
    │       └─ contract_scenarios 일괄 INSERT
    │
    └─→ ③ data/predictions/*.json 파일 백업
    │
    ▼
[웹/외부] 200 OK + 결과 응답
```

**즉, 사용자가 대시보드에서 [예측 실행] 을 누르거나, 외부에서 API 를 호출할 때마다 자동으로 DB에 한 행이 추가됩니다.**

### `is_latest` 동작 예시

같은 충전소(`BNS0001`)를 3번 예측하면:

```
id=3  station_id=BNS0001  run_at=2026-05-12 10:46:36  is_latest=0
id=4  station_id=BNS0001  run_at=2026-05-12 10:46:46  is_latest=0
id=5  station_id=BNS0001  run_at=2026-05-12 10:46:51  is_latest=0
id=6  station_id=BNS0001  run_at=2026-05-12 10:47:56  is_latest=1  ← 최신
```

→ **과거 실행 기록은 보존**되지만, "현재 추천"은 항상 `is_latest = 1` 한 행으로 식별됩니다.

---

## 4. 외부 웹앱에서 데이터 가져가는 두 가지 방법

### 4-A. REST API (권장)

| 엔드포인트 | 반환 |
|---|---|
| `GET /api/public/stations` | 예측이 있는 충전소 목록 + 각 충전소 최신 `run_at` |
| `GET /api/public/predictions/{station_id}` | 카드 요약 |
| `GET /api/public/predictions/{station_id}/daily?from=&to=` | 일별 시계열 |
| `GET /api/public/predictions/{station_id}/monthly` | 월별 요약 |
| `GET /api/public/predictions/{station_id}/scenarios` | 시나리오 표 |

예시:

```bash
curl http://웹주소/api/public/predictions/AAC0001
```

### 4-B. DB 직접 조회 (필요 시)

`data/predictions.db` 파일을 읽기 전용으로 마운트해 외부 앱에서 SQLite 로 직접 쿼리:

```sql
-- 특정 충전소의 현재 추천
SELECT recommended_contract_kw, ensemble_p95_kw, annual_savings_krw
FROM prediction_runs
WHERE station_id = 'AAC0001' AND is_latest = 1;

-- 모든 충전소의 최신 추천 한 번에
SELECT station_id, recommended_contract_kw, annual_savings_krw, run_at
FROM prediction_runs
WHERE is_latest = 1
ORDER BY station_id;

-- 특정 run 의 일별 시계열
SELECT prediction_date, p50, p95
FROM daily_predictions
WHERE run_id = (SELECT id FROM prediction_runs
                WHERE station_id = 'AAC0001' AND is_latest = 1);

-- 추천된 계약전력의 상세
SELECT contract_kw, scenario_label, expected_annual_cost, risk_score
FROM contract_scenarios s
JOIN prediction_runs r ON r.id = s.run_id
WHERE r.station_id = 'AAC0001' AND r.is_latest = 1 AND s.is_recommended = 1;
```

---

## 5. 특징

### 같은 데이터에서 예측을 다시 실행하면
새 row 가 추가되고, 이전 row 의 `is_latest` 만 `0` 으로 강등됩니다. 과거 실행 이력은 그대로 남습니다.

### 새 CSV 를 업로드하면 (데이터 자체가 바뀌면)
업로드 직후 **모든 예측 테이블 + JSON 백업이 초기화**된 뒤(`StorageManager.clear_all_predictions()`), 새 데이터로 전 충전소가 다시 예측됩니다. 이전 데이터에만 있던 충전소의 옛 예측이 계속 로드되는 stale 문제를 원천 차단하기 위함입니다. (즉, "같은 데이터 재실행"은 이력 누적, "새 데이터 업로드"는 전체 초기화)

### DB 가 너무 커질 때 일정 주기로 삭제 가능
`StorageManager.cleanup_old_data(days_old=30)` 호출로 30일 이상 된 기록 삭제 가능. APScheduler 등으로 주기 실행을 붙여도 됩니다.

### PostgreSQL/MySQL 로 환경 변경 가능
모든 SQL 은 표준에 가깝게 작성돼 있어서, `sqlite3.connect()` 부분만 `psycopg2`/`mysql.connector` 로 바꾸고 컬럼 타입을 그쪽 표준에 맞추면 됩니다. 외부 앱 코드는 영향 없음 (REST API 사용 시).

### 외부 앱에서 쓰기 방지
쓰기는 본 플랫폼만 합니다. 외부 앱이 데이터를 변경할 일은 없으므로 DB 파일을 `read-only` 모드로 마운트해도 무방합니다.

---

## 6. 관련 파일

| 파일 | 역할 |
|---|---|
| [backend/app/storage/prediction_db.py](../backend/app/storage/prediction_db.py) | 스키마 정의 + 저장/조회 메서드 |
| [backend/app/storage/storage_manager.py](../backend/app/storage/storage_manager.py) | DB + 파일 백업 통합 |
| [backend/app/api/routes.py](../backend/app/api/routes.py) | `/ensemble-prediction` 응답 직전에 저장 호출 |
| [backend/app/api/public_routes.py](../backend/app/api/public_routes.py) | 외부 앱용 5개 GET 엔드포인트 |
| [backend/app/main.py](../backend/app/main.py) | public_router 등록 |
