from __future__ import annotations

import sqlite3
import sys

import pandas as pd

from .config import (
    CLEAN_FILE,
    HOURLY_CLEAN_FILE,
    PERSON_CLEAN_FILE,
    PROCESSED_DIR,
    SQLITE_FILE,
)


def main() -> int:
    required_files = (CLEAN_FILE, PERSON_CLEAN_FILE, HOURLY_CLEAN_FILE)
    if any(not path.exists() for path in required_files):
        print("[ERROR] 정제 파일이 없습니다. 먼저 python -m src.clean_data를 실행하세요.")
        return 1

    frame = pd.read_csv(CLEAN_FILE, parse_dates=["operation_date"])
    person_frame = pd.read_csv(PERSON_CLEAN_FILE, parse_dates=["operation_date"])
    hourly_frame = pd.read_csv(HOURLY_CLEAN_FILE, parse_dates=["operation_date"])
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_FILE) as connection:
        frame.to_sql("transport_usage", connection, if_exists="replace", index=False)
        person_frame.to_sql("transport_person", connection, if_exists="replace", index=False)
        hourly_frame.to_sql("transport_hourly", connection, if_exists="replace", index=False)
        counts = {
            "transport_usage": (len(frame), connection.execute("SELECT COUNT(*) FROM transport_usage").fetchone()[0]),
            "transport_person": (len(person_frame), connection.execute("SELECT COUNT(*) FROM transport_person").fetchone()[0]),
            "transport_hourly": (len(hourly_frame), connection.execute("SELECT COUNT(*) FROM transport_hourly").fetchone()[0]),
        }
        for table, (csv_count, db_count) in counts.items():
            if csv_count != db_count:
                raise RuntimeError(f"CSV·DB 건수 불일치 ({table}): CSV {csv_count:,}행, DB {db_count:,}행")
        top_regions = connection.execute(
            """
            SELECT sido_name, SUM(usage_count) AS total_usage
            FROM transport_usage
            GROUP BY sido_name
            ORDER BY total_usage DESC
            LIMIT 10
            """
        ).fetchall()

    print(f"[OK] SQLite 적재 완료: {SQLITE_FILE}")
    for table, (csv_count, _) in counts.items():
        print(f"[OK] CSV·DB 건수 검증 완료 ({table}): {csv_count:,}행")
    print("\n전국 시도 상위 10개:")
    for region, usage in top_regions:
        print(f"- {region}: {usage:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
