import pandas as pd
import pytest

from src.clean_data import clean_frame


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "운행일자": ["2025-01-01"],
            "시도코드(법정동)": ["26"],
            "시도명": ["부산광역시"],
            "시군구코드(법정동)": ["26110"],
            "시군구명": ["중구"],
            "교통수단명": ["버스"],
            "이용량": ["10"],
        }
    )


def test_clean_frame_standardizes_schema():
    result = clean_frame(valid_frame())
    assert list(result.columns) == [
        "operation_date",
        "sido_code",
        "sido_name",
        "sigungu_code",
        "sigungu_name",
        "transport_type",
        "usage_count",
    ]
    assert result.loc[0, "usage_count"] == 10
    assert str(result.loc[0, "operation_date"].date()) == "2025-01-01"


def test_clean_frame_rejects_negative_usage():
    frame = valid_frame()
    frame.loc[0, "이용량"] = -1
    with pytest.raises(ValueError, match="음수"):
        clean_frame(frame)
