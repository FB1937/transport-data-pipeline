import sqlite3

import pandas as pd

from src.load_sqlite import _upsert_frame


def test_upsert_updates_existing_natural_key():
    frame = pd.DataFrame(
        [
            {
                "operation_date": "2025-01-01",
                "sido_code": 26,
                "sigungu_code": 26000,
                "sido_name": "부산광역시",
                "sigungu_name": "전체",
                "transport_type": "시내버스",
                "usage_count": 10,
            }
        ]
    )
    updated = frame.copy()
    updated.loc[0, "usage_count"] = 25
    with sqlite3.connect(":memory:") as connection:
        assert _upsert_frame(connection, "transport_usage", frame) == 1
        assert _upsert_frame(connection, "transport_usage", updated) == 1
        assert connection.execute("SELECT usage_count FROM transport_usage").fetchone()[0] == 25
