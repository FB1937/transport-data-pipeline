from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "",
)
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_FILE = RAW_DIR / "transport_usage.csv"
RAW_PERSON_FILE = RAW_DIR / "국토교통부_시군구별 대중교통이용인원수_20251231.csv"
RAW_HOURLY_FILE = RAW_DIR / "국토교통부_시군구별 시간대별 대중교통이용인원수_20251231.csv"
CLEAN_FILE = PROCESSED_DIR / "transport_usage_clean.csv"
PERSON_CLEAN_FILE = PROCESSED_DIR / "transport_person_clean.csv"
HOURLY_CLEAN_FILE = PROCESSED_DIR / "transport_hourly_clean.csv"
SQLITE_FILE = PROCESSED_DIR / "transport_usage.sqlite"

REQUIRED_COLUMNS = [
    "운행일자",
    "시도코드(법정동)",
    "시도명",
    "시군구코드(법정동)",
    "시군구명",
    "교통수단명",
    "이용량",
]

STANDARD_COLUMNS = {
    "운행일자": "operation_date",
    "시도코드(법정동)": "sido_code",
    "시도명": "sido_name",
    "시군구코드(법정동)": "sigungu_code",
    "시군구명": "sigungu_name",
    "교통수단명": "transport_type",
    "이용량": "usage_count",
}

PERSON_REQUIRED_COLUMNS = [
    "운행일자",
    "시도코드(법정동)",
    "시도명",
    "시군구코드(법정동)",
    "시군구명",
    "이용인원",
]

HOURLY_REQUIRED_COLUMNS = [
    "운행일자",
    "시도코드(법정동)",
    "시도명",
    "시군구코드(법정동)",
    "시군구명",
    "시간대",
    "이용량",
]
