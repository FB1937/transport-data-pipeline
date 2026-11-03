from __future__ import annotations

import sys

from .config import (
    HOURLY_REQUIRED_COLUMNS,
    PERSON_REQUIRED_COLUMNS,
    RAW_FILE,
    RAW_HOURLY_FILE,
    RAW_PERSON_FILE,
    REQUIRED_COLUMNS,
)
from .io_utils import read_csv_with_fallback


def main() -> int:
    if not RAW_FILE.exists():
        print(f"[ERROR] 원천 파일이 없습니다: {RAW_FILE}")
        print("공공데이터포털 CSV를 data/raw/transport_usage.csv로 저장한 뒤 다시 실행하세요.")
        return 1

    frame = read_csv_with_fallback(RAW_FILE)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]

    print(f"행 수: {len(frame):,}")
    print(f"열 수: {len(frame.columns):,}")
    print(f"컬럼: {list(frame.columns)}")
    print("\n자료형:")
    print(frame.dtypes.to_string())
    print("\n결측치:")
    print(frame.isna().sum().to_string())
    print(f"\n중복 행 수: {int(frame.duplicated().sum()):,}")

    if "운행일자" in frame.columns:
        dates = frame["운행일자"].astype("string").str.strip()
        print(f"\n운행일자 범위: {dates.min()} ~ {dates.max()}")
    if "시도명" in frame.columns:
        print("\n시도별 행 수:")
        print(frame["시도명"].value_counts(dropna=False).to_string())
    if "교통수단명" in frame.columns:
        print("\n교통수단별 행 수:")
        print(frame["교통수단명"].value_counts(dropna=False).to_string())

    if missing_columns:
        print(f"\n[ERROR] 필수 컬럼 누락: {missing_columns}")
        return 1
    for path, required_columns, label in (
        (RAW_PERSON_FILE, PERSON_REQUIRED_COLUMNS, "이용인원"),
        (RAW_HOURLY_FILE, HOURLY_REQUIRED_COLUMNS, "시간대"),
    ):
        if not path.exists():
            print(f"\n[ERROR] 추가 원천 파일이 없습니다: {path}")
            return 1
        additional = read_csv_with_fallback(path)
        missing = [column for column in required_columns if column not in additional.columns]
        print(f"\n{label} 원천 파일: {len(additional):,}행, {len(additional.columns):,}열")
        print(f"결측치 합계: {int(additional.isna().sum().sum()):,}")
        print(f"중복 행 수: {int(additional.duplicated().sum()):,}")
        if missing:
            print(f"[ERROR] {label} 필수 컬럼 누락: {missing}")
            return 1
    print("\n[OK] 전체 원천 데이터 구조 확인 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
