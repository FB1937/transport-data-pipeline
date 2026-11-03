import pandas as pd

from src.analyze import (
    aggregate_busan_district_profile,
    aggregate_busan_seasonal,
    aggregate_busan_time_period,
)


def test_time_periods_cover_all_hours():
    frame = pd.DataFrame({
        "sido_code": [26] * 5,
        "sigungu_code": [26110] * 5,
        "hour": [0, 7, 12, 18, 21],
        "usage_count": [1, 2, 3, 4, 5],
    })
    result = aggregate_busan_time_period(frame)
    assert result["total_usage"].sum() == 15
    assert set(result["time_period"]) == {"심야(00-05)", "출근(06-09)", "주간(10-16)", "퇴근(17-19)", "저녁(20-23)"}


def test_seasonal_summary_uses_busan_rows_only():
    frame = pd.DataFrame({
        "sido_code": [26, 11],
        "sigungu_code": [26110, 11110],
        "operation_date": ["2025-01-01", "2025-01-01"],
        "usage_count": [10, 100],
    })
    result = aggregate_busan_seasonal(frame)
    assert result["total_usage"].sum() == 10
    assert result.iloc[0]["season"] == "겨울"


def test_district_profile_merges_usage_and_people():
    usage = pd.DataFrame({
        "sido_code": [26],
        "sigungu_code": [26110],
        "sigungu_name": ["중구"],
        "usage_count": [100],
    })
    people = pd.DataFrame({
        "sido_code": [26],
        "sigungu_code": [26110],
        "sigungu_name": ["중구"],
        "person_count": [20],
    })
    result = aggregate_busan_district_profile(usage, people)
    assert result.iloc[0]["usage_per_person"] == 5
