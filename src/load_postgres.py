from __future__ import annotations

import os
import sys

import pandas as pd

from .config import CLEAN_FILE, HOURLY_CLEAN_FILE, PERSON_CLEAN_FILE, POSTGRES_DSN


TABLES = {
    "transport_usage": CLEAN_FILE,
    "transport_person": PERSON_CLEAN_FILE,
    "transport_hourly": HOURLY_CLEAN_FILE,
}


def main() -> int:
    missing = [path for path in TABLES.values() if not path.exists()]
    if missing:
        print(f"[ERROR] 정제 파일이 없습니다: {missing}")
        return 1
    if not POSTGRES_DSN:
        print("[ERROR] POSTGRES_DSN 환경 변수가 설정되지 않았습니다.")
        return 1
    try:
        import psycopg
        from psycopg import sql
    except ImportError:
        print("[ERROR] PostgreSQL 적재에는 psycopg가 필요합니다. pip install -r requirements.txt")
        return 1

    try:
        with psycopg.connect(POSTGRES_DSN) as connection:
            for table, path in TABLES.items():
                frame = pd.read_csv(path, parse_dates=["operation_date"])
                columns = list(frame.columns)
                column_sql = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
                connection.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table)))
                definitions = []
                for column in columns:
                    dtype = "DATE" if column == "operation_date" else "BIGINT" if column.endswith(("_code", "_count", "_usage")) or column in {"hour"} else "TEXT"
                    definitions.append(sql.SQL("{} {}").format(sql.Identifier(column), sql.SQL(dtype)))
                connection.execute(sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier(table), sql.SQL(", ").join(definitions)))
                rows = [tuple(None if pd.isna(value) else value for value in row) for row in frame.itertuples(index=False, name=None)]
                with connection.cursor() as cursor:
                    cursor.executemany(
                        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                            sql.Identifier(table), column_sql, placeholders
                        ),
                        rows,
                    )
                count = connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
                if count != len(frame):
                    raise RuntimeError(f"PostgreSQL 행 수 불일치 ({table}): CSV {len(frame):,}, DB {count:,}")
                print(f"[OK] PostgreSQL 적재 완료 ({table}): {count:,}행")
    except (OSError, ValueError, RuntimeError, psycopg.Error) as error:
        print(f"[ERROR] PostgreSQL 적재 실패: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
