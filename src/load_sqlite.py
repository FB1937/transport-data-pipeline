from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import datetime, timezone

import pandas as pd

from .config import (
    CLEAN_FILE,
    HOURLY_CLEAN_FILE,
    PERSON_CLEAN_FILE,
    PROCESSED_DIR,
    SQLITE_FILE,
)


TABLE_KEYS = {
    "transport_usage": ("operation_date", "sido_code", "sigungu_code", "transport_type"),
    "transport_person": ("operation_date", "sido_code", "sigungu_code"),
    "transport_hourly": ("operation_date", "sido_code", "sigungu_code", "hour"),
}


def _upsert_frame(connection: sqlite3.Connection, table: str, frame: pd.DataFrame) -> int:
    staging = f"_staging_{table}"
    frame.to_sql(staging, connection, if_exists="replace", index=False)
    if not connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone():
        frame.head(0).to_sql(table, connection, if_exists="replace", index=False)
    key_columns = TABLE_KEYS[table]
    index_name = f"ux_{table}_natural_key"
    quoted_keys = ", ".join(f'"{column}"' for column in key_columns)
    connection.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" ON "{table}" ({quoted_keys})'
    )
    columns = list(frame.columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    connection.execute(
        f"""
        INSERT OR REPLACE INTO "{table}" ({quoted_columns})
        SELECT {quoted_columns} FROM "{staging}"
        """
    )
    connection.execute(f'DROP TABLE "{staging}"')
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def main() -> int:
    required_files = (CLEAN_FILE, PERSON_CLEAN_FILE, HOURLY_CLEAN_FILE)
    if any(not path.exists() for path in required_files):
        print("[ERROR] 정제 파일이 없습니다. 먼저 python -m src.clean_data를 실행하세요.")
        return 1

    frame = pd.read_csv(CLEAN_FILE, parse_dates=["operation_date"])
    person_frame = pd.read_csv(PERSON_CLEAN_FILE, parse_dates=["operation_date"])
    hourly_frame = pd.read_csv(HOURLY_CLEAN_FILE, parse_dates=["operation_date"])
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(SQLITE_FILE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                error TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, NULL, 'running', '{}', '')",
            (run_id, started_at),
        )
        try:
            stored_counts = {
                "transport_usage": _upsert_frame(connection, "transport_usage", frame),
                "transport_person": _upsert_frame(connection, "transport_person", person_frame),
                "transport_hourly": _upsert_frame(connection, "transport_hourly", hourly_frame),
            }
        except Exception as error:
            connection.execute(
                """
                UPDATE pipeline_runs
                SET completed_at=?, status='failed', error=?
                WHERE run_id=?
                """,
                (datetime.now(timezone.utc).isoformat(), str(error), run_id),
            )
            connection.commit()
            print(f"[ERROR] 증분 SQLite 적재 실패: {error}")
            return 1
        counts = {
            "transport_usage": (len(frame), stored_counts["transport_usage"]),
            "transport_person": (len(person_frame), stored_counts["transport_person"]),
            "transport_hourly": (len(hourly_frame), stored_counts["transport_hourly"]),
        }
        for table, (csv_count, db_count) in counts.items():
            if csv_count != db_count:
                raise RuntimeError(f"CSV·DB 건수 불일치 ({table}): CSV {csv_count:,}행, DB {db_count:,}행")
        import json

        details = {
            table: {
                "source_rows": len(source),
                "stored_rows": stored_counts[table],
                "start_date": source["operation_date"].min().date().isoformat(),
                "end_date": source["operation_date"].max().date().isoformat(),
            }
            for table, source in (
                ("transport_usage", frame),
                ("transport_person", person_frame),
                ("transport_hourly", hourly_frame),
            )
        }
        connection.execute(
            """
            UPDATE pipeline_runs
            SET completed_at=?, status='success', details_json=?
            WHERE run_id=?
            """,
            (datetime.now(timezone.utc).isoformat(), json.dumps(details), run_id),
        )
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
