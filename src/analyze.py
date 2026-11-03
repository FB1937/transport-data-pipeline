from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import matplotlib
import pandas as pd
from scipy.stats import ttest_ind

from .config import (
    CLEAN_FILE,
    HOURLY_CLEAN_FILE,
    PERSON_CLEAN_FILE,
    PROJECT_ROOT,
    SQLITE_FILE,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

if any(font.name == "Malgun Gothic" for font in font_manager.fontManager.ttflist):
    plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


REPORT_DIR = PROJECT_ROOT / "reports"
FIGURE_DIR = REPORT_DIR / "figures"
SUMMARY_FILE = REPORT_DIR / "analysis_summary.csv"
PERSON_SUMMARY_FILE = REPORT_DIR / "person_summary.csv"
MONTHLY_FILE = REPORT_DIR / "monthly_summary.csv"
BUSAN_MONTHLY_FILE = REPORT_DIR / "busan_monthly_summary.csv"
BUSAN_TRANSPORT_SHARE_FILE = REPORT_DIR / "busan_transport_share.csv"
BUSAN_HOURLY_FILE = REPORT_DIR / "busan_hourly_summary.csv"
BUSAN_PERIOD_FILE = REPORT_DIR / "busan_time_period_summary.csv"
BUSAN_SEASONAL_FILE = REPORT_DIR / "busan_seasonal_summary.csv"
BUSAN_HYPOTHESIS_FILE = REPORT_DIR / "busan_hypothesis_test.csv"
BUSAN_DISTRICT_PROFILE_FILE = REPORT_DIR / "busan_district_profile.csv"
BUSAN_SIDO_CODE = 26


def aggregate_by_sido(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby("sido_name", as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values("total_usage", ascending=False, ignore_index=True)
    )


def aggregate_person_by_sido(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby("sido_name", as_index=False)["person_count"]
        .sum()
        .rename(columns={"person_count": "total_person_count"})
        .sort_values("total_person_count", ascending=False, ignore_index=True)
    )


def aggregate_busan_by_sigungu(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.loc[(frame["sido_code"] == BUSAN_SIDO_CODE) & (frame["sigungu_code"] != 26000)]
        .groupby("sigungu_name", as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values("total_usage", ascending=False, ignore_index=True)
    )


def aggregate_busan_transport(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.loc[(frame["sido_code"] == BUSAN_SIDO_CODE) & (frame["sigungu_code"] != 26000)]
        .groupby(["sigungu_name", "transport_type"], as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values(["sigungu_name", "total_usage"], ascending=[True, False], ignore_index=True)
    )


def aggregate_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    monthly = frame.copy()
    monthly["month"] = pd.to_datetime(monthly["operation_date"]).dt.to_period("M").astype(str)
    return (
        monthly.groupby("month", as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values("month", ignore_index=True)
    )


def _busan_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[(frame["sido_code"] == BUSAN_SIDO_CODE) & (frame["sigungu_code"] != 26000)].copy()


def aggregate_busan_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    monthly = _busan_frame(frame)
    monthly["month"] = pd.to_datetime(monthly["operation_date"]).dt.to_period("M").astype(str)
    result = (
        monthly.groupby("month", as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values("month", ignore_index=True)
    )
    result["change_from_previous"] = result["total_usage"].pct_change().mul(100).round(2)
    result["change_from_previous"] = result["change_from_previous"].fillna(0)
    result["quarter"] = pd.PeriodIndex(result["month"], freq="M").quarter
    result["quarter"] = "Q" + result["quarter"].astype(str)
    return result


def aggregate_busan_transport_share(frame: pd.DataFrame) -> pd.DataFrame:
    result = (
        _busan_frame(frame)
        .groupby("transport_type", as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values("total_usage", ascending=False, ignore_index=True)
    )
    result["share_percent"] = (
        result["total_usage"].div(result["total_usage"].sum()).mul(100).round(2)
    )
    return result


def aggregate_busan_district_profile(
    frame: pd.DataFrame, person_frame: pd.DataFrame
) -> pd.DataFrame:
    usage = aggregate_busan_by_sigungu(frame).rename(columns={"total_usage": "usage_count"})
    people = (
        person_frame.loc[
            (person_frame["sido_code"] == BUSAN_SIDO_CODE)
            & (person_frame["sigungu_code"] != 26000)
        ]
        .groupby("sigungu_name", as_index=False)["person_count"]
        .sum()
    )
    profile = usage.merge(people, on="sigungu_name", how="left")
    profile["usage_per_person"] = (
        profile["usage_count"].div(profile["person_count"]).round(2)
    )
    return profile.sort_values("usage_count", ascending=False, ignore_index=True)


def aggregate_busan_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    busan = frame.loc[(frame["sido_code"] == BUSAN_SIDO_CODE) & (frame["sigungu_code"] != 26000)]
    return (
        busan.groupby("hour", as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
        .sort_values("hour", ignore_index=True)
    )


def aggregate_busan_time_period(frame: pd.DataFrame) -> pd.DataFrame:
    periods = pd.cut(
        frame["hour"],
        bins=[-1, 5, 9, 16, 19, 23],
        labels=["심야(00-05)", "출근(06-09)", "주간(10-16)", "퇴근(17-19)", "저녁(20-23)"],
    )
    result = (
        frame.loc[(frame["sido_code"] == BUSAN_SIDO_CODE) & (frame["sigungu_code"] != 26000)]
        .assign(time_period=periods)
        .groupby("time_period", observed=False, as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
    )
    result["time_period"] = result["time_period"].astype(str)
    return result


def aggregate_busan_seasonal(frame: pd.DataFrame) -> pd.DataFrame:
    busan = _busan_frame(frame)
    busan["month"] = pd.to_datetime(busan["operation_date"]).dt.month
    busan["season"] = busan["month"].map(
        {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄",
         6: "여름", 7: "여름", 8: "여름", 9: "가을", 10: "가을", 11: "가을"}
    )
    return (
        busan.groupby("season", as_index=False)["usage_count"]
        .agg(total_usage="sum", average_observation_usage="mean")
        .assign(average_observation_usage=lambda data: data["average_observation_usage"].round(2))
        .sort_values("total_usage", ascending=False, ignore_index=True)
    )


def calculate_busan_hypothesis_test(hourly_frame: pd.DataFrame) -> pd.DataFrame:
    busan = hourly_frame.loc[
        (hourly_frame["sido_code"] == BUSAN_SIDO_CODE) & (hourly_frame["sigungu_code"] != 26000)
    ]
    district_hour = busan.groupby(["sigungu_name", "hour"], as_index=False)["usage_count"].sum()
    commute = district_hour.loc[district_hour["hour"].between(17, 19)].groupby("sigungu_name")["usage_count"].sum()
    off_peak = district_hour.loc[district_hour["hour"].between(0, 5)].groupby("sigungu_name")["usage_count"].sum()
    statistic, p_value = ttest_ind(commute, off_peak, equal_var=False)
    return pd.DataFrame([{
        "comparison": "퇴근(17-19) vs 심야(00-05)",
        "commute_mean": commute.mean(),
        "off_peak_mean": off_peak.mean(),
        "t_statistic": round(statistic, 4),
        "p_value": round(p_value, 8),
        "significant_at_05": bool(p_value < 0.05),
    }])


def _read_sql_aggregates() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    queries = (
        """
        SELECT sido_name, SUM(usage_count) AS total_usage
        FROM transport_usage
        GROUP BY sido_name
        ORDER BY total_usage DESC
        """,
        """
        SELECT sigungu_name, SUM(usage_count) AS total_usage
        FROM transport_usage
        WHERE sido_code = 26
          AND sigungu_code != 26000
        GROUP BY sigungu_name
        ORDER BY total_usage DESC
        """,
        """
        SELECT sigungu_name, transport_type, SUM(usage_count) AS total_usage
        FROM transport_usage
        WHERE sido_code = 26
          AND sigungu_code != 26000
        GROUP BY sigungu_name, transport_type
        ORDER BY sigungu_name, total_usage DESC
        """,
    )
    with sqlite3.connect(SQLITE_FILE) as connection:
        results = [pd.read_sql_query(query, connection) for query in queries]
    return results[0], results[1], results[2]


def _read_sql_monthly() -> pd.DataFrame:
    query = """
        SELECT strftime('%Y-%m', operation_date) AS month,
               SUM(usage_count) AS total_usage
        FROM transport_usage
        GROUP BY month
        ORDER BY month
    """
    with sqlite3.connect(SQLITE_FILE) as connection:
        return pd.read_sql_query(query, connection)


def _read_sql_busan_hourly() -> pd.DataFrame:
    query = """
        SELECT hour, SUM(usage_count) AS total_usage
        FROM transport_hourly
        WHERE sido_code = 26 AND sigungu_code != 26000
        GROUP BY hour
        ORDER BY hour
    """
    with sqlite3.connect(SQLITE_FILE) as connection:
        return pd.read_sql_query(query, connection)


def _assert_equal(left: pd.DataFrame, right: pd.DataFrame, keys: list[str]) -> None:
    left_sorted = left.sort_values(keys).reset_index(drop=True)
    right_sorted = right.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(left_sorted, right_sorted, check_dtype=False, check_like=True)


def _save_bar_chart(data: pd.DataFrame, category: str, title: str, path: Path) -> None:
    chart = data.sort_values("total_usage")
    height = max(5, len(chart) * 0.3)
    figure, axis = plt.subplots(figsize=(10, height))
    bars = axis.barh(chart[category], chart["total_usage"], color="#1769aa")
    axis.set_title(title)
    axis.set_xlabel("Usage count (comma-separated)")
    axis.set_ylabel("")
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    max_usage = chart["total_usage"].max()
    for bar, value in zip(bars, chart["total_usage"]):
        axis.text(
            bar.get_width() + max_usage * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,.0f}",
            va="center",
            fontsize=8,
        )
    axis.set_xlim(0, max_usage * 1.16)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_monthly_chart(data: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(12, 6))
    bars = axis.bar(data["month"], data["total_usage"], color="#1769aa")
    axis.set_title("Monthly public transit usage")
    axis.set_xlabel("Month")
    axis.set_ylabel("Usage count (comma-separated)")
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    axis.tick_params(axis="x", rotation=45)
    max_usage = data["total_usage"].max()
    for bar, value in zip(bars, data["total_usage"]):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_usage * 0.01,
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=7,
            rotation=90,
        )
    axis.set_ylim(0, max_usage * 1.18)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_hourly_chart(data: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(12, 6))
    bars = axis.bar(data["hour"].astype(str).str.zfill(2), data["total_usage"], color="#5b2cff")
    axis.set_title("Busan usage by hour")
    axis.set_xlabel("Hour of day")
    axis.set_ylabel("Usage count")
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    peak = data["total_usage"].max()
    for bar, value in zip(bars, data["total_usage"]):
        axis.text(bar.get_x() + bar.get_width() / 2, value + peak * 0.01, f"{value:,.0f}",
                  ha="center", va="bottom", fontsize=7, rotation=90)
    axis.set_ylim(0, peak * 1.18)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_busan_transport_chart(data: pd.DataFrame, path: Path) -> None:
    pivot = data.pivot(index="sigungu_name", columns="transport_type", values="total_usage").fillna(0)
    figure, axis = plt.subplots(figsize=(12, 8))
    pivot.plot.barh(ax=axis, stacked=True)
    axis.set_title("Busan usage by district and transport type")
    axis.set_xlabel("Usage count (comma-separated)")
    axis.set_ylabel("")
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    totals = pivot.sum(axis=1)
    max_total = totals.max()
    for y_position, (district, total) in enumerate(totals.items()):
        axis.text(total + max_total * 0.01, y_position, f"{total:,.0f}", va="center", fontsize=8)
    axis.set_xlim(0, max_total * 1.14)
    axis.legend(title="Transport type", bbox_to_anchor=(1.02, 1), loc="upper left")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def run_analysis() -> dict[str, pd.DataFrame]:
    required_files = (CLEAN_FILE, PERSON_CLEAN_FILE, HOURLY_CLEAN_FILE)
    if any(not path.exists() for path in required_files):
        raise FileNotFoundError(f"정제 파일이 없습니다: {required_files}")
    if not SQLITE_FILE.exists():
        raise FileNotFoundError(f"SQLite 파일이 없습니다: {SQLITE_FILE}")

    frame = pd.read_csv(CLEAN_FILE)
    person_frame = pd.read_csv(PERSON_CLEAN_FILE)
    hourly_frame = pd.read_csv(HOURLY_CLEAN_FILE)
    python_results = {
        "sido": aggregate_by_sido(frame),
        "person_sido": aggregate_person_by_sido(person_frame),
        "busan_sigungu": aggregate_busan_by_sigungu(frame),
        "busan_transport": aggregate_busan_transport(frame),
        "monthly": aggregate_monthly(frame),
        "busan_monthly": aggregate_busan_monthly(frame),
        "busan_transport_share": aggregate_busan_transport_share(frame),
        "busan_hourly": aggregate_busan_hourly(hourly_frame),
        "busan_period": aggregate_busan_time_period(hourly_frame),
        "busan_seasonal": aggregate_busan_seasonal(frame),
        "busan_hypothesis": calculate_busan_hypothesis_test(hourly_frame),
        "busan_district_profile": aggregate_busan_district_profile(frame, person_frame),
    }
    sql_results = _read_sql_aggregates()
    _assert_equal(python_results["sido"], sql_results[0], ["sido_name", "total_usage"])
    _assert_equal(python_results["busan_sigungu"], sql_results[1], ["sigungu_name", "total_usage"])
    _assert_equal(
        python_results["busan_transport"],
        sql_results[2],
        ["sigungu_name", "transport_type", "total_usage"],
    )
    _assert_equal(python_results["monthly"], _read_sql_monthly(), ["month", "total_usage"])
    _assert_equal(python_results["busan_hourly"], _read_sql_busan_hourly(), ["hour", "total_usage"])

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    summary = python_results["sido"].copy()
    summary.insert(0, "analysis", "sido_total")
    summary.to_csv(SUMMARY_FILE, index=False, encoding="utf-8-sig")
    python_results["person_sido"].to_csv(PERSON_SUMMARY_FILE, index=False, encoding="utf-8-sig")
    python_results["monthly"].to_csv(MONTHLY_FILE, index=False, encoding="utf-8-sig")
    python_results["busan_monthly"].to_csv(BUSAN_MONTHLY_FILE, index=False, encoding="utf-8-sig")
    python_results["busan_transport_share"].to_csv(
        BUSAN_TRANSPORT_SHARE_FILE, index=False, encoding="utf-8-sig"
    )
    python_results["busan_hourly"].to_csv(BUSAN_HOURLY_FILE, index=False, encoding="utf-8-sig")
    python_results["busan_period"].to_csv(BUSAN_PERIOD_FILE, index=False, encoding="utf-8-sig")
    python_results["busan_seasonal"].to_csv(BUSAN_SEASONAL_FILE, index=False, encoding="utf-8-sig")
    python_results["busan_hypothesis"].to_csv(BUSAN_HYPOTHESIS_FILE, index=False, encoding="utf-8-sig")
    python_results["busan_district_profile"].to_csv(
        BUSAN_DISTRICT_PROFILE_FILE, index=False, encoding="utf-8-sig"
    )
    _save_bar_chart(
        python_results["sido"],
        "sido_name",
        "Public transit usage by province",
        FIGURE_DIR / "usage_by_sido.png",
    )
    _save_bar_chart(
        python_results["busan_sigungu"],
        "sigungu_name",
        "Busan public transit usage by district",
        FIGURE_DIR / "busan_usage_by_sigungu.png",
    )
    _save_busan_transport_chart(
        python_results["busan_transport"],
        FIGURE_DIR / "busan_usage_by_transport.png",
    )
    _save_monthly_chart(
        python_results["monthly"],
        FIGURE_DIR / "usage_by_month.png",
    )
    _save_hourly_chart(python_results["busan_hourly"], FIGURE_DIR / "busan_usage_by_hour.png")
    return python_results


def main() -> int:
    try:
        results = run_analysis()
    except (AssertionError, FileNotFoundError, OSError, ValueError) as error:
        print(f"[ERROR] 분석 실패: {error}")
        return 1

    print("[OK] Python·SQL 집계 일치 검증 완료")
    print(f"[OK] 분석 요약: {SUMMARY_FILE}")
    print(f"[OK] 그래프 생성: {FIGURE_DIR}")
    print("\n전국 이용량 상위 5개:")
    for row in results["sido"].head(5).itertuples(index=False):
        print(f"- {row.sido_name}: {row.total_usage:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
