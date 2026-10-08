"""
월별 충전이력 엑셀(.xlsx) 병합 + 전역 중복 제거 → 단일 학습용 CSV

배경:
  data/train_data/ 에 한 달 단위 엑셀이 다수 저장돼 있다.
  - 파일 상단 3행이 제목/내보낸시각이라 실제 헤더는 4번째 행(header=3)
  - 같은 달을 여러 번 내려받은 '파일 단위 중복본'이 섞여 있음
  - 월 범위가 [M-01 ~ (M+1)-01] 이라 월 경계 세션이 인접 두 파일에 겹칠 수 있음
  → 중복 제거는 모든 파일을 합친 뒤 전역으로 해야 정확하다.

사용:
  python preprocess_train_data.py
  python preprocess_train_data.py --input ../data/train_data --output ../data/processed/charging_merged.csv
"""

import argparse
import glob
import os
import sys
from pathlib import Path

import pandas as pd

HEADER_ROW = 3  # 제목 2행 + 내보낸시각 1행 다음(0-indexed 3)이 실제 컬럼 헤더
START_COL = "충전시작일시"
END_COL = "충전종료일시"
CHARGER_COL = "충전기ID"
POWER_COL = "순간최고전력"
# 한 세션의 고유 식별 키(같은 충전기가 같은 시작/종료 시각에 두 세션을 가질 수 없음)
DEDUP_KEYS = [CHARGER_COL, START_COL, END_COL]


def find_files(input_dir: Path):
    files = sorted(
        glob.glob(str(input_dir / "*.xlsx")),
        key=lambda f: os.path.getmtime(f),
    )
    # 엑셀 임시 파일(~$) 제외
    return [f for f in files if not os.path.basename(f).startswith("~$")]


def read_one(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, header=HEADER_ROW)
    # 완전 빈 행 제거
    df = df.dropna(how="all")
    return df


def main():
    ap = argparse.ArgumentParser(description="월별 충전이력 엑셀 병합 + 전역 중복 제거")
    ap.add_argument("--input", default="../data/train_data", help="엑셀이 있는 디렉토리")
    ap.add_argument(
        "--output",
        default="../data/processed/charging_merged.csv",
        help="저장할 단일 CSV 경로",
    )
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    input_dir = (base / args.input).resolve() if not os.path.isabs(args.input) else Path(args.input)
    output_path = (base / args.output).resolve() if not os.path.isabs(args.output) else Path(args.output)

    files = find_files(input_dir)
    if not files:
        print(f"[오류] 엑셀을 찾지 못했습니다: {input_dir}")
        sys.exit(1)

    print(f"입력 디렉토리: {input_dir}")
    print(f"엑셀 파일 수 : {len(files)}개\n")

    frames = []
    per_file_months = {}
    total_raw = 0
    for i, f in enumerate(files, 1):
        try:
            df = read_one(f)
        except Exception as e:
            print(f"  [건너뜀] {os.path.basename(f)[-22:]}: {e}")
            continue
        if START_COL not in df.columns or POWER_COL not in df.columns:
            print(f"  [건너뜀] {os.path.basename(f)[-22:]}: 필수 컬럼 없음")
            continue
        total_raw += len(df)
        # 파일이 대표하는 월(가장 흔한 연-월) 기록
        s = pd.to_datetime(df[START_COL], errors="coerce")
        if s.notna().any():
            ym = s.dt.to_period("M").mode()
            if len(ym):
                per_file_months[f] = str(ym.iloc[0])
        frames.append(df)
        if i % 10 == 0:
            print(f"  ...{i}/{len(files)} 읽음")

    merged = pd.concat(frames, ignore_index=True)
    print(f"\n병합 원시 행수      : {total_raw:,}")
    print(f"concat 후 행수       : {len(merged):,}")

    # 시작일시가 없는 행(잔존 제목/요약행 등) 제거
    merged[START_COL] = merged[START_COL].astype(str).str.strip()
    parsed = pd.to_datetime(merged[START_COL], errors="coerce")
    before = len(merged)
    merged = merged[parsed.notna()].copy()
    parsed = parsed[parsed.notna()]
    print(f"시작일시 결측 제거    : -{before - len(merged):,} → {len(merged):,}")

    # 전역 중복 제거 (업무 키 기준)
    before = len(merged)
    merged = merged.drop_duplicates(subset=DEDUP_KEYS, keep="first")
    print(f"전역 중복 제거        : -{before - len(merged):,} → {len(merged):,}  (키={DEDUP_KEYS})")

    # 시간순 정렬
    merged = merged.assign(_sort=pd.to_datetime(merged[START_COL], errors="coerce"))
    merged = merged.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)

    # 기간/개월 리포트
    s_all = pd.to_datetime(merged[START_COL], errors="coerce")
    months = sorted(set(per_file_months.values()))
    dup_files = len(files) - len(months)
    print("\n================ 요약 ================")
    print(f"고유 세션(행) 수     : {len(merged):,}")
    print(f"데이터 기간          : {s_all.min()} ~ {s_all.max()}")
    print(f"포함 개월 수         : {len(months)}개월 ({months[0]} ~ {months[-1]})")
    print(f"중복 파일(같은 달)   : 약 {dup_files}개 (파일 {len(files)} - 개월 {len(months)})")
    print(f"충전소 수            : {merged['충전소ID'].nunique() if '충전소ID' in merged.columns else '?'}")

    # 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False, encoding="utf-8")
    print(f"\n저장 완료 → {output_path}")
    print(f"파일 크기            : {output_path.stat().st_size/1e6:.1f} MB")
    print("\n학습 시 사용 예:")
    print(f"  python train_lstm_model.py --data-path {output_path}")


if __name__ == "__main__":
    main()
