from __future__ import annotations

import sys

import pandas as pd

from .config import (
    CLEAN_FILE,
    HOURLY_CLEAN_FILE,
    HOURLY_REQUIRED_COLUMNS,
    PERSON_CLEAN_FILE,
    PERSON_REQUIRED_COLUMNS,
    PROCESSED_DIR,
    RAW_FILE,
    RAW_HOURLY_FILE,
    RAW_PERSON_FILE,
    REQUIRED_COLUMNS,
    STANDARD_COLUMNS,
)
from .io_utils import read_csv_with_fallback
from .quality_checks import validate_clean_frame


TRANSPORT_TYPE_LABELS = {
    "마을": "마을버스",
    "시내": "시내버스",
}


def clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"필수 컬럼 누락: {missing_columns}")

    result = frame[REQUIRED_COLUMNS].copy()
    text_columns = [column for column in REQUIRED_COLUMNS if column not in ("운행일자", "이용량")]
    for column in text_columns:
        result[column] = result[column].astype("string").str.strip()
    result["운행일자"] = pd.to_datetime(result["운행일자"], errors="coerce")
    result["이용량"] = pd.to_numeric(result["이용량"], errors="coerce")

    if result["운행일자"].isna().any():
        raise ValueError("운행일자를 날짜로 변환할 수 없는 행이 있습니다.")
    if result["이용량"].isna().any():
        raise ValueError("이용량을 숫자로 변환할 수 없는 행이 있습니다.")
    if (result["이용량"] < 0).any():
        raise ValueError("음수 이용량이 있습니다.")
    if result.duplicated().any():
        raise ValueError("완전히 동일한 중복 행이 있습니다.")

    result = result.rename(columns=STANDARD_COLUMNS)
    result["transport_type"] = result["transport_type"].replace(TRANSPORT_TYPE_LABELS)
    result["usage_count"] = result["usage_count"].astype("int64")
    validate_clean_frame(result)
    return result


def _clean_aggregate_frame(
    frame: pd.DataFrame, required_columns: list[str], value_column: str, output_value: str
) -> pd.DataFrame:
    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"필수 컬럼 누락: {missing_columns}")
    result = frame[required_columns].copy()
    text_columns = [column for column in required_columns if column not in ("운행일자", value_column)]
    for column in text_columns:
        result[column] = result[column].astype("string").str.strip()
    result["운행일자"] = pd.to_datetime(result["운행일자"], errors="coerce")
    result[value_column] = pd.to_numeric(result[value_column], errors="coerce")
    if result["운행일자"].isna().any():
        raise ValueError("운행일자를 날짜로 변환할 수 없는 행이 있습니다.")
    if result[value_column].isna().any():
        raise ValueError(f"{value_column}을 숫자로 변환할 수 없는 행이 있습니다.")
    if (result[value_column] < 0).any():
        raise ValueError(f"{value_column}에 음수 값이 있습니다.")
    if result.duplicated().any():
        raise ValueError("완전히 동일한 중복 행이 있습니다.")
    result = result.rename(
        columns={
            "운행일자": "operation_date",
            "시도코드(법정동)": "sido_code",
            "시도명": "sido_name",
            "시군구코드(법정동)": "sigungu_code",
            "시군구명": "sigungu_name",
            value_column: output_value,
        }
    )
    result[output_value] = result[output_value].astype("int64")
    return result


def clean_person_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _clean_aggregate_frame(frame, PERSON_REQUIRED_COLUMNS, "이용인원", "person_count")


def clean_hourly_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = _clean_aggregate_frame(frame, HOURLY_REQUIRED_COLUMNS, "이용량", "usage_count")
    result["hour"] = pd.to_numeric(result["시간대"] if "시간대" in result else frame["시간대"], errors="coerce")
    if result["hour"].isna().any() or not result["hour"].between(0, 23).all():
        raise ValueError("시간대는 0~23 범위의 숫자여야 합니다.")
    result = result.drop(columns=["시간대"], errors="ignore")
    validate_clean_frame(result, hourly=True)
    return result


def main() -> int:
    required_files = (RAW_FILE, RAW_PERSON_FILE, RAW_HOURLY_FILE)
    missing_files = [path for path in required_files if not path.exists()]
    if missing_files:
        print(f"[ERROR] 원천 파일이 없습니다: {missing_files}")
        return 1
    try:
        cleaned = clean_frame(read_csv_with_fallback(RAW_FILE))
        person_cleaned = clean_person_frame(read_csv_with_fallback(RAW_PERSON_FILE))
        hourly_cleaned = clean_hourly_frame(read_csv_with_fallback(RAW_HOURLY_FILE))
    except (ValueError, UnicodeError) as error:
        print(f"[ERROR] 정제 실패: {error}")
        return 1

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig")
    person_cleaned.to_csv(PERSON_CLEAN_FILE, index=False, encoding="utf-8-sig")
    hourly_cleaned.to_csv(HOURLY_CLEAN_FILE, index=False, encoding="utf-8-sig")
    print(f"[OK] 정제 완료: {CLEAN_FILE} ({len(cleaned):,}행)")
    print(f"[OK] 이용인원 정제 완료: {PERSON_CLEAN_FILE} ({len(person_cleaned):,}행)")
    print(f"[OK] 시간대 정제 완료: {HOURLY_CLEAN_FILE} ({len(hourly_cleaned):,}행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
