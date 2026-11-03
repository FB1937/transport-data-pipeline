import pandas as pd
import pytest

from src.quality_checks import validate_clean_frame


def test_quality_checks_accept_valid_hourly_frame():
    validate_clean_frame(pd.DataFrame({
        "operation_date": ["2025-01-01"],
        "sido_code": [26],
        "sido_name": ["부산"],
        "sigungu_code": [26110],
        "sigungu_name": ["중구"],
        "usage_count": [10],
        "hour": [17],
    }), hourly=True)


def test_quality_checks_reject_negative_usage():
    frame = pd.DataFrame({
        "operation_date": ["2025-01-01"],
        "sido_code": [26],
        "sido_name": ["부산"],
        "sigungu_code": [26110],
        "sigungu_name": ["중구"],
        "usage_count": [-1],
    })
    with pytest.raises(ValueError, match="음수"):
        validate_clean_frame(frame)
