import pandas as pd

from src.analyze import (
    aggregate_busan_monthly,
    aggregate_busan_by_sigungu,
    aggregate_busan_transport_share,
    aggregate_busan_transport,
    aggregate_by_sido,
)


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sido_code": [26, 26, 11],
            "sido_name": ["부산광역시", "부산광역시", "서울특별시"],
            "sigungu_code": [26110, 26110, 11110],
            "sigungu_name": ["중구", "중구", "종로구"],
            "transport_type": ["버스", "도시철도", "버스"],
            "usage_count": [10, 5, 20],
        }
    )


def test_aggregates_by_region():
    result = aggregate_by_sido(sample_frame())
    assert result.to_dict("records") == [
        {"sido_name": "서울특별시", "total_usage": 20},
        {"sido_name": "부산광역시", "total_usage": 15},
    ]


def test_busan_aggregates_use_region_code():
    frame = sample_frame()
    assert aggregate_busan_by_sigungu(frame).to_dict("records") == [
        {"sigungu_name": "중구", "total_usage": 15}
    ]
    assert aggregate_busan_transport(frame).to_dict("records") == [
        {"sigungu_name": "중구", "transport_type": "버스", "total_usage": 10},
        {"sigungu_name": "중구", "transport_type": "도시철도", "total_usage": 5},
    ]


def test_busan_monthly_changes_and_transport_shares():
    frame = sample_frame()
    frame["operation_date"] = ["2025-01-01", "2025-02-01", "2025-01-01"]
    monthly = aggregate_busan_monthly(frame)
    assert monthly["total_usage"].tolist() == [10, 5]
    assert monthly["change_from_previous"].tolist() == [0.0, -50.0]
    shares = aggregate_busan_transport_share(frame)
    assert shares["share_percent"].sum() == 100.0
