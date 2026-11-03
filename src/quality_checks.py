from __future__ import annotations

import pandas as pd


def validate_clean_frame(frame: pd.DataFrame, *, hourly: bool = False) -> None:
    required = {"operation_date", "sido_code", "sido_name", "sigungu_code", "sigungu_name"}
    required.add("usage_count")
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"필수 컬럼 누락: {sorted(missing)}")
    if frame[list(required)].isna().any().any():
        raise ValueError("핵심 컬럼에 결측값이 있습니다.")
    if frame.duplicated().any():
        raise ValueError("중복 행이 있습니다.")
    if (frame["usage_count"] < 0).any():
        raise ValueError("음수 이용량이 있습니다.")
    if hourly and (not frame["hour"].between(0, 23).all()):
        raise ValueError("시간대가 0~23 범위를 벗어났습니다.")
