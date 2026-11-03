from __future__ import annotations

import html
import json
import base64
import sqlite3
import sys
from pathlib import Path

import matplotlib
import pandas as pd

from .analyze import (
    FIGURE_DIR,
    REPORT_DIR,
    aggregate_busan_by_sigungu,
    aggregate_busan_monthly,
    aggregate_busan_hourly,
    aggregate_busan_district_profile,
    aggregate_busan_time_period,
    aggregate_busan_seasonal,
    calculate_busan_hypothesis_test,
    aggregate_busan_transport_share,
)
from .config import CLEAN_FILE, HOURLY_CLEAN_FILE, PERSON_CLEAN_FILE, PROJECT_ROOT, RAW_DIR, SQLITE_FILE

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter


GEOJSON_FILE = PROJECT_ROOT / "data" / "geo" / "busan_sgg.geojson"
DASHBOARD_PNG = REPORT_DIR / "dashboard.png"
DASHBOARD_HTML = REPORT_DIR / "dashboard.html"
BUSAN_CODE_PREFIX = "26"


def _operational_status() -> tuple[str, str, str]:
    if not SQLITE_FILE.exists():
        return "기록 없음", "SQLite 이력 데이터베이스가 없습니다.", ""
    with sqlite3.connect(SQLITE_FILE) as connection:
        collection = connection.execute(
            """
            SELECT status, completed_at, details_json, error
            FROM collection_runs
            ORDER BY run_id DESC LIMIT 1
            """
        ).fetchone() if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
        ).fetchone() else None
        load = connection.execute(
            """
            SELECT status, completed_at, details_json, error
            FROM pipeline_runs
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone() if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pipeline_runs'"
        ).fetchone() else None
    collection_text = "기록 없음"
    load_text = "기록 없음"
    source_text = "수집 이력 없음"
    if collection:
        status, completed_at, details_json, error = collection
        source_text = f"{status} · {completed_at or '-'}"
        if error:
            source_text += f" · {error}"
        try:
            details = json.loads(details_json)
            files = [
                f"{Path(name).stem}: {int(value.get('rows', 0)):,}행"
                for name, value in details.items()
                if isinstance(value, dict) and "rows" in value
            ]
            collection_text = " / ".join(files) or "파일 상세 정보 없음"
        except (TypeError, ValueError):
            collection_text = "수집 상세 정보를 읽을 수 없습니다."
    elif (RAW_DIR / "collection_manifest.json").exists():
        try:
            manifest = json.loads((RAW_DIR / "collection_manifest.json").read_text(encoding="utf-8"))
            files = [
                f"{Path(name).stem}: {int(value.get('rows', 0)):,}행"
                for name, value in manifest.items()
                if isinstance(value, dict) and "rows" in value
            ]
            fetched_at = next(
                (
                    value.get("fetched_at")
                    for value in manifest.values()
                    if isinstance(value, dict) and value.get("fetched_at")
                ),
                None,
            )
            source_text = f"매니페스트 기준 · {fetched_at or '시각 없음'}"
            collection_text = " / ".join(files) or "매니페스트 상세 정보 없음"
        except (OSError, TypeError, ValueError):
            collection_text = "수집 매니페스트를 읽을 수 없습니다."
    if load:
        status, completed_at, details_json, error = load
        load_text = f"{status} · {completed_at or '-'}"
        if error:
            load_text += f" · {error}"
    return source_text, collection_text, load_text


def _polygon_parts(geometry: dict) -> list[list[tuple[float, float]]]:
    if geometry["type"] == "Polygon":
        return [ring for ring in geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    return []


def _busan_features() -> list[dict]:
    with GEOJSON_FILE.open(encoding="utf-8") as file:
        collection = json.load(file)
    return [
        feature
        for feature in collection["features"]
        if str(feature["properties"]["code"]).startswith(BUSAN_CODE_PREFIX)
    ]


def _draw_map(axis, values: pd.DataFrame, title: str, colors: dict[str, str] | None = None) -> None:
    value_by_code = values.set_index("sigungu_code")
    features = _busan_features()
    numeric = values["total_usage"]
    normalizer = Normalize(vmin=float(numeric.min()), vmax=float(numeric.max()))
    cmap = plt.get_cmap("Blues")
    for feature in features:
        code = int(feature["properties"]["code"])
        if code not in value_by_code.index:
            continue
        row = value_by_code.loc[code]
        color = colors.get(row["dominant_transport"], "#d9e8f5") if colors else cmap(normalizer(row["total_usage"]))
        for ring in _polygon_parts(feature["geometry"]):
            polygon = Polygon(ring, facecolor=color, edgecolor="white", linewidth=0.8)
            axis.add_patch(polygon)
        coordinates = [
            point
            for ring in _polygon_parts(feature["geometry"])
            for point in ring
        ]
        x = sum(point[0] for point in coordinates) / len(coordinates)
        y = sum(point[1] for point in coordinates) / len(coordinates)
        axis.text(x, y, row["sigungu_name"], ha="center", va="center", fontsize=7)
    axis.autoscale()
    axis.set_aspect("equal")
    axis.axis("off")
    axis.set_title(title)


def _create_dashboard_image(frame: pd.DataFrame) -> None:
    busan = frame.loc[
        (frame["sido_code"] == 26) & (frame["sigungu_code"] != 26000)
    ].copy()
    district = (
        busan.groupby(["sigungu_code", "sigungu_name"], as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
    )
    transport = (
        busan.groupby(["sigungu_code", "sigungu_name", "transport_type"], as_index=False)["usage_count"]
        .sum()
        .rename(columns={"usage_count": "total_usage"})
    )
    dominant = transport.sort_values("total_usage", ascending=False).drop_duplicates("sigungu_code")
    map_values = district.merge(
        dominant[["sigungu_code", "transport_type"]].rename(columns={"transport_type": "dominant_transport"}),
        on="sigungu_code",
    )
    monthly = aggregate_busan_monthly(frame)
    monthly_transport = (
        frame.loc[(frame["sido_code"] == 26) & (frame["sigungu_code"] != 26000)]
        .assign(month=lambda data: pd.to_datetime(data["operation_date"]).dt.to_period("M").astype(str))
        .groupby(["month", "transport_type"], as_index=False)["usage_count"]
        .sum()
        .pivot(index="month", columns="transport_type", values="usage_count")
        .fillna(0)
    )
    transport_colors = {
        "도시철도": "#4575b4",
        "시내버스": "#66bd63",
        "마을버스": "#fdae61",
        "좌석": "#984ea3",
        "시외": "#d73027",
    }
    fallback_colors = ["#8073ac", "#e08214", "#1b9e77", "#d95f02"]
    for index, name in enumerate(monthly_transport.columns):
        transport_colors.setdefault(name, fallback_colors[index % len(fallback_colors)])

    figure, axes = plt.subplots(2, 2, figsize=(16, 11))
    _draw_map(axes[0, 0], map_values, "Busan district annual usage")
    _draw_map(axes[0, 1], map_values, "Dominant transport type by district", transport_colors)
    axes[0, 1].legend(
        handles=[
            plt.Line2D([0], [0], marker="s", color="w", markerfacecolor=color, label=label, markersize=9)
            for label, color in transport_colors.items()
            if label in set(map_values["dominant_transport"])
        ],
        loc="lower left",
        fontsize=8,
    )
    axes[1, 0].plot(monthly["month"], monthly["total_usage"], marker="o", color="#1769aa")
    axes[1, 0].set_title("Monthly usage trend")
    axes[1, 0].set_ylabel("Usage count")
    axes[1, 0].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    axes[1, 0].tick_params(axis="x", rotation=45)
    monthly_transport.plot.bar(ax=axes[1, 1], stacked=True, color=[transport_colors.get(c) for c in monthly_transport.columns])
    axes[1, 1].set_title("Monthly usage by transport type")
    axes[1, 1].set_xlabel("Month")
    axes[1, 1].set_ylabel("Usage count")
    axes[1, 1].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    axes[1, 1].legend(title="Transport type", fontsize=8)
    figure.suptitle("Busan public transit usage dashboard", fontsize=18)
    figure.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(DASHBOARD_PNG, dpi=160)
    plt.close(figure)


def _save_busan_hour_heatmap(hourly_frame: pd.DataFrame) -> Path:
    busan = hourly_frame.loc[
        (hourly_frame["sido_code"] == 26) & (hourly_frame["sigungu_code"] != 26000)
    ].copy()
    pivot = (
        busan.pivot_table(
            index="sigungu_name",
            columns="hour",
            values="usage_count",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(columns=range(24), fill_value=0)
    )
    figure, axis = plt.subplots(figsize=(15, 8))
    image = axis.imshow(pivot.values, aspect="auto", cmap="YlGnBu")
    axis.set_title("Busan district hourly usage heatmap")
    axis.set_xlabel("Hour of day")
    axis.set_ylabel("District")
    axis.set_xticks(range(24), [f"{hour:02d}" for hour in range(24)])
    axis.set_yticks(range(len(pivot.index)), pivot.index)
    figure.colorbar(image, ax=axis, label="Usage count")
    figure.tight_layout()
    path = FIGURE_DIR / "busan_hourly_heatmap.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def _create_dashboard_html(frame: pd.DataFrame) -> None:
    collection_status, collection_files, load_status = _operational_status()
    district_all = aggregate_busan_by_sigungu(frame)
    district = district_all.head(5)
    transport = aggregate_busan_transport_share(frame)
    person_frame = pd.read_csv(PERSON_CLEAN_FILE)
    hourly_frame = pd.read_csv(HOURLY_CLEAN_FILE)
    monthly = aggregate_busan_monthly(frame)
    hourly = aggregate_busan_hourly(hourly_frame)
    periods = aggregate_busan_time_period(hourly_frame)
    seasonal = aggregate_busan_seasonal(frame)
    hypothesis = calculate_busan_hypothesis_test(hourly_frame)
    district_profile = aggregate_busan_district_profile(frame, person_frame)
    total_usage = int(
        person_frame.loc[
            (person_frame["sido_code"] == 26) & (person_frame["sigungu_code"] != 26000),
            "person_count",
        ].sum()
    )
    top_district = district.iloc[0]
    top_transport = transport.iloc[0]
    peak_month = monthly.loc[monthly["total_usage"].idxmax()]
    peak_hour = hourly.loc[hourly["total_usage"].idxmax()]
    monthly_latest = monthly.tail(6)
    person_busan = (
        person_frame.loc[
            (person_frame["sido_code"] == 26) & (person_frame["sigungu_code"] != 26000)
        ]
        .groupby("sigungu_name", as_index=False)["person_count"]
        .sum()
        .rename(columns={"person_count": "total_person_count"})
        .sort_values("total_person_count", ascending=False)
    )
    busan_hourly_detail = (
        hourly_frame.loc[
            (hourly_frame["sido_code"] == 26) & (hourly_frame["sigungu_code"] != 26000)
        ]
        .groupby(["sigungu_name", "hour"], as_index=False)["usage_count"]
        .sum()
    )
    busan_transport_detail = (
        frame.loc[(frame["sido_code"] == 26) & (frame["sigungu_code"] != 26000)]
        .groupby(["sigungu_name", "transport_type"], as_index=False)["usage_count"]
        .sum()
    )

    def table(data: pd.DataFrame) -> str:
        labels = {
            "sigungu_name": "구·군",
            "transport_type": "교통수단",
            "total_usage": "이용량",
            "total_person_count": "이용인원",
            "share_percent": "비중(%)",
            "month": "월",
            "change_from_previous": "전월 대비(%)",
            "quarter": "분기",
            "time_period": "시간대 구간",
            "season": "계절",
            "average_observation_usage": "평균 관측 이용량",
            "comparison": "비교",
            "commute_mean": "퇴근 평균",
            "off_peak_mean": "심야 평균",
            "t_statistic": "t 통계량",
            "p_value": "p-value",
            "significant_at_05": "유의수준 5%",
            "usage_count": "이용량",
            "person_count": "이용인원",
            "usage_per_person": "이용량/이용인원",
        }
        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{html.escape(f'{int(value):,}' if column in ('total_usage', 'total_person_count', 'usage_count', 'commute_mean', 'off_peak_mean') else f'{value:.2f}' if column in ('share_percent', 'change_from_previous', 'average_observation_usage', 't_statistic') else f'{value:.8f}' if column == 'p_value' else str(value))}</td>"
                for column, value in zip(data.columns, row)
            )
            + "</tr>"
            for row in data.itertuples(index=False, name=None)
        )
        headers = "".join(f"<th>{labels.get(column, column)}</th>" for column in data.columns)
        return f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"

    def embed_image(filename: str) -> str:
        return base64.b64encode((FIGURE_DIR / filename).read_bytes()).decode("ascii")

    heatmap_path = _save_busan_hour_heatmap(hourly_frame)
    heatmap_data = base64.b64encode(heatmap_path.read_bytes()).decode("ascii")
    district_chart_data = embed_image("busan_usage_by_sigungu.png")
    transport_chart_data = embed_image("busan_usage_by_transport.png")
    monthly_chart_data = embed_image("usage_by_month.png")
    hourly_chart_data = embed_image("busan_usage_by_hour.png")
    district_options = "".join(
        f'<option value="{html.escape(str(name))}">{html.escape(str(name))}</option>'
        for name in sorted(busan_hourly_detail["sigungu_name"].unique())
    )
    detail_json = json.dumps(
        {
            "hourly": busan_hourly_detail.to_dict("records"),
            "transport": busan_transport_detail.to_dict("records"),
        },
        ensure_ascii=False,
    )
    content = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Busan Transit Insights</title>
<style>
:root{{--ink:#18283d;--muted:#6d7b8d;--purple:#5b2cff;--purple-dark:#4520c9;--line:#e6eaf0;--soft:#f6f8fc;--green:#42b883}}
*{{box-sizing:border-box}} body{{margin:0;background:#f5f7fb;color:var(--ink);font-family:Arial,"Malgun Gothic",sans-serif}}
.topbar{{background:linear-gradient(90deg,#4c20e9,#7131ff);color:#fff;font-size:12px;padding:8px 5%;text-align:center}}
.topbar b{{font-weight:700}} .shell{{max-width:1420px;margin:auto;padding:0 28px}}
.header{{height:78px;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:24px}}
.brand{{display:flex;align-items:center;gap:10px;font-size:23px;font-weight:800;letter-spacing:-.7px}}
.brand-mark{{width:35px;height:35px;border-radius:11px;background:var(--purple);color:#fff;display:grid;place-items:center;font-size:20px}}
.nav{{background:var(--ink);color:#fff;border-radius:12px;padding:12px 20px;display:flex;align-items:center;gap:28px;font-size:14px}}
.nav a{{color:#fff;text-decoration:none;padding:0 0 5px}} .nav a.active{{font-weight:700;border-bottom:2px solid #8e75ff}}
.hero{{margin-top:24px;background:linear-gradient(120deg,#17283d 0%,#203b59 60%,#31577b 100%);border-radius:18px;padding:34px 42px;color:#fff;display:flex;justify-content:space-between;align-items:center;overflow:hidden}}
.hero h1{{font-size:38px;line-height:1.12;margin:8px 0 12px;max-width:570px;letter-spacing:-1.6px}}
.hero p{{color:#d5e0ed;max-width:560px;line-height:1.7;margin:0 0 20px}} .eyebrow{{font-size:13px;font-weight:700;color:#9be0c3}}
.hero-badge{{background:#fff;color:var(--ink);border-radius:999px;padding:11px 18px;font-size:13px;font-weight:700;display:inline-block}}
.hero-visual{{font-size:110px;opacity:.95;transform:rotate(-8deg);padding:0 35px}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}}
.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:0 4px 14px #26364d0b}}
.card-label{{font-size:12px;color:var(--muted);font-weight:700;margin-bottom:10px}} .card-value{{font-size:22px;font-weight:800;letter-spacing:-.5px}}
.card-note{{font-size:11px;color:var(--green);margin-top:8px}} .section-title{{display:flex;justify-content:space-between;align-items:end;margin:28px 0 12px}}
.section-title h2{{margin:0;font-size:22px}} .section-title span{{font-size:12px;color:var(--muted)}}
.dashboard-image{{width:100%;display:block;border-radius:16px;border:1px solid var(--line);box-shadow:0 8px 24px #26364d12;background:#fff}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:18px 0 36px}}
.panel{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px;box-shadow:0 4px 14px #26364d0b}}
.panel h3{{margin:0 0 15px;font-size:17px}} table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{border-bottom:1px solid var(--line);padding:12px 8px;text-align:left}} th{{font-size:11px;color:var(--muted);font-weight:700}}
td:last-child,th:last-child{{text-align:right;font-weight:700}} tr:last-child td{{border-bottom:0}}
.footer{{background:var(--ink);color:#c6d0dc;padding:22px 5%;font-size:12px;text-align:center}}
.anchor{{scroll-margin-top:20px}} .about{{line-height:1.7;color:var(--muted)}} .tab-panel{{display:none}} .tab-panel.active{{display:block}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0 18px}} select{{border:1px solid var(--line);border-radius:8px;padding:10px 14px;background:#fff;color:var(--ink)}}
.filter-result{{min-height:110px}} .mini-table{{max-height:260px;overflow:auto}}
pre{{margin:12px 0;padding:14px 16px;background:#18283d;color:#d9f5e5;border-radius:8px;overflow:auto;font-size:13px}}
@media(max-width:850px){{.nav{{gap:12px;font-size:12px}}.hero{{padding:28px}}.hero h1{{font-size:29px}}.hero-visual{{font-size:65px;padding:0}}.cards{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}
@media(max-width:520px){{.shell{{padding:0 14px}}.header{{height:auto;padding:16px 0;flex-wrap:wrap}}.nav{{width:100%;justify-content:space-between}}.hero-visual{{display:none}}.cards{{grid-template-columns:1fr}}}}
</style></head>
<body><div class="topbar">✦ 2025 부산 대중교통 데이터 인사이트 &nbsp;|&nbsp; 원천 데이터 품질 검증 완료</div>
<div class="shell"><header class="header"><div class="brand"><span class="brand-mark">↗</span>BusanTransit</div>
<nav class="nav" aria-label="Dashboard sections"><a class="active" href="#dashboard">Dashboard</a><a href="#districts">Districts</a><a href="#transport">Transport</a><a href="#monthly">Monthly</a><a href="#explorer">Explorer</a><a href="#about">About</a></nav></header>
<main>
<div id="tab-dashboard" class="tab-panel active">
<section class="hero"><div><div class="eyebrow">PUBLIC TRANSIT ANALYTICS</div>
<h1>부산의 이동을<br>한눈에 확인하세요</h1>
<p>2025년 운행일자 데이터를 바탕으로 부산 구·군별 이용량과 교통수단별 흐름을 분석했습니다.</p>
<span class="hero-badge">2025.01 — 2025.12&nbsp; · &nbsp;315,505 rows</span></div>
<div class="hero-visual">✦</div></section>
<section class="cards"><div class="card"><div class="card-label">BUSAN TOTAL USAGE</div><div class="card-value">{total_usage:,}</div><div class="card-note">▲ 전체 부산 이용량</div></div>
<div class="card"><div class="card-label">TOP DISTRICT</div><div class="card-value">{html.escape(str(top_district["sigungu_name"]))}</div><div class="card-note">{int(top_district["total_usage"]):,} 이용량</div></div>
<div class="card"><div class="card-label">TOP TRANSPORT</div><div class="card-value">{html.escape(str(top_transport["transport_type"]))}</div><div class="card-note">{int(top_transport["total_usage"]):,} 이용량</div></div>
<div class="card"><div class="card-label">PEAK MONTH</div><div class="card-value">{html.escape(str(peak_month["month"]))}</div><div class="card-note">{int(peak_month["total_usage"]):,} 이용량</div></div>
<div class="card"><div class="card-label">PEAK HOUR</div><div class="card-value">{int(peak_hour["hour"]):02d}:00</div><div class="card-note">{int(peak_hour["total_usage"]):,} 이용량</div></div></section>
<div id="dashboard" class="anchor section-title"><h2>Busan usage overview</h2><span>전체 분석 요약</span></div>
<div class="grid"><section class="panel"><h3>대시보드 안내</h3><p class="about">이 화면은 부산 대중교통의 핵심 지표만 요약합니다. 구·군, 교통수단, 월별 흐름은 각 분석 탭에서 중복 없이 확인할 수 있습니다.</p></section><section class="panel"><h3>주요 관찰</h3><p class="about">{html.escape(str(top_district["sigungu_name"]))}의 이용량이 가장 높고, {html.escape(str(top_transport["transport_type"]))}이 부산 전체 교통수단 중 가장 큰 비중을 차지합니다.</p></section></div>
<section class="panel"><h3>파이프라인 운영 상태</h3><div class="grid"><div><p class="about"><b>최근 수집:</b> {html.escape(collection_status)}</p><p class="about"><b>수집 파일:</b> {html.escape(collection_files)}</p></div><div><p class="about"><b>최근 SQLite 적재:</b> {html.escape(load_status)}</p><p class="about">수집·적재 이력은 SQLite의 <code>collection_runs</code>, <code>pipeline_runs</code>에 기록됩니다.</p></div></div></section>
</div>
<div id="tab-districts" class="tab-panel">
<div id="districts" class="anchor section-title"><h2>Districts</h2><span>부산 구·군별 이용량</span></div>
<div class="grid"><section class="panel"><h3>부산 구·군 TOP 5</h3>{table(district)}</section>
<section class="panel"><h3>구·군별 해석</h3><p class="about">부산진구와 해운대구 등 이용량 상위 지역을 중심으로 수요가 집중됩니다. 전체 순위는 아래 그래프에서 비교하세요.</p></section></div>
<img class="dashboard-image" src="data:image/png;base64,{district_chart_data}" alt="부산 구·군별 이용량 순위">
<div class="grid"><section class="panel"><h3>구·군별 이용인원 TOP 5</h3>{table(person_busan.head(5))}</section><section class="panel"><h3>지역별 읽는 법</h3><p class="about">이용량은 교통수단별 관측값의 합계이며, 이용인원 데이터와는 집계 기준이 다를 수 있습니다. 두 지표를 함께 비교해 지역별 수요 규모를 파악할 수 있습니다.</p></section></div>
<section class="panel"><h3>지역별 수요 프로필</h3>{table(district_profile)}</section>
</div>
<div id="tab-transport" class="tab-panel">
<div id="transport" class="anchor section-title"><h2>Transport</h2><span>교통수단별 이용량과 점유율</span></div>
<div class="grid"><section class="panel"><h3>교통수단별 이용량·점유율</h3>{table(transport)}</section>
<section class="panel"><h3>핵심 해석</h3><p class="about">시내버스, 도시철도, 마을버스의 점유율을 비교해 부산의 교통수단 의존도를 확인합니다. 아래 그래프는 구·군별 구성 차이를 보여줍니다.</p></section></div>
<img class="dashboard-image" src="data:image/png;base64,{transport_chart_data}" alt="부산 구·군별 교통수단 이용량">
</div>
<div id="tab-monthly" class="tab-panel">
<div id="monthly" class="anchor section-title"><h2>Monthly</h2><span>월별·시간대별 이용 패턴</span></div>
<section class="panel"><h3>최근 6개월</h3>{table(monthly_latest)}</section>
<img class="dashboard-image" src="data:image/png;base64,{monthly_chart_data}" alt="전국 월별 이용량">
<img class="dashboard-image" src="data:image/png;base64,{hourly_chart_data}" alt="부산 시간대별 이용량">
<div class="grid"><section class="panel"><h3>시간대 구간 비교</h3>{table(periods)}</section><section class="panel"><h3>계절성 요약</h3>{table(seasonal)}</section></div>
<section class="panel"><h3>통계적 비교</h3>{table(hypothesis)}<p class="about">부산 구·군별 합계에서 퇴근 시간대와 심야 시간대의 평균 이용량을 Welch t-test로 비교했습니다. p-value가 0.05보다 작으면 두 구간의 차이를 통계적으로 유의하다고 해석합니다.</p></section>
<div class="section-title"><h2>District × Hour heatmap</h2><span>구·군별 시간대 패턴</span></div>
<img class="dashboard-image" src="data:image/png;base64,{heatmap_data}" alt="부산 구·군별 시간대 히트맵">
</div>
<div id="tab-explorer" class="tab-panel">
<div id="explorer" class="anchor section-title"><h2>Explorer</h2><span>구·군과 교통수단을 선택해 상세 분석</span></div>
<div class="section-title"><h2>Explore the data</h2><span>구·군과 교통수단을 선택하세요</span></div>
<div class="controls"><label>구·군 <select id="districtFilter"><option value="">전체 구·군</option>{district_options}</select></label>
<label>교통수단 <select id="transportFilter"><option value="">전체 교통수단</option></select></label></div>
<div class="grid"><section class="panel filter-result"><h3 id="filterTitle">선택 지역 시간대별 이용량</h3><div class="mini-table" id="hourlyResult"></div></section>
<section class="panel filter-result"><h3>선택 조건 교통수단 구성</h3><div class="mini-table" id="transportResult"></div></section></div>
</div>
<div id="tab-about" class="tab-panel">
<div id="about" class="anchor section-title"><h2>About</h2><span>처음 방문한 분을 위한 안내</span></div>
<section class="panel about"><h3>이 대시보드는 무엇을 보여주나요?</h3><p>국토교통부의 2025년 대중교통 데이터를 바탕으로 부산의 어느 지역에서, 어떤 교통수단이, 언제 많이 이용되었는지 보여줍니다.</p><p>모든 이용량은 건수 기준이며, 사람 수와는 다른 지표입니다. 이용인원 자료는 별도로 표시해 두 지표를 혼동하지 않도록 했습니다.</p></section>
<div class="grid"><section class="panel about"><h3>화면 이용 방법</h3><p><b>Districts:</b> 부산 구·군별 이용량과 이용인원 순위를 비교합니다.</p><p><b>Transport:</b> 시내버스·마을버스·도시철도 등 교통수단별 비중을 확인합니다.</p><p><b>Monthly:</b> 월별 변화와 시간대별 이용 패턴을 살펴봅니다.</p><p><b>Explorer:</b> 구·군과 교통수단을 선택해 원하는 조건만 자세히 봅니다.</p></section><section class="panel about"><h3>데이터 범위</h3><p><b>기간:</b> 2025년 1월~12월</p><p><b>지역:</b> 부산 16개 구·군</p><p><b>출처:</b> 국토교통부 시군구별 대중교통 이용인원수·교통수단별 이용량·시간대별 이용량</p></section></div>
<section class="panel about"><h3>운영 이력</h3><p><b>최근 수집 상태:</b> {html.escape(collection_status)}</p><p><b>수집 파일 요약:</b> {html.escape(collection_files)}</p><p><b>최근 적재 상태:</b> {html.escape(load_status)}</p><p>자동 수집 실패와 재시도 여부는 <code>logs/pipeline.log</code> 및 SQLite 이력 테이블에서 확인할 수 있습니다.</p></section>
<div class="grid"><section class="panel about"><h3>데이터를 믿을 수 있도록 한 점</h3><p>분석 전에 빈 값, 중복 행, 음수 이용량, 잘못된 시간대 값을 점검했습니다.</p><p>정제된 CSV와 SQLite 데이터베이스의 행 수를 비교하고, Python과 SQL로 계산한 결과도 대조했습니다.</p></section><section class="panel about"><h3>분석 시 참고할 점</h3><p>이용량과 이용인원은 서로 다른 원천 자료에서 계산된 값이므로 직접 같은 의미로 비교하면 안 됩니다.</p><p>이 대시보드는 2025년 자료를 기준으로 하며, 노선·환승·요일별 이용 목적까지 설명하지는 않습니다.</p></section></div>
<section class="panel about"><h3>재현하고 싶은 분께</h3><p>Python이 설치된 환경에서 프로젝트 폴더를 연 뒤 아래 명령을 실행하면 원천 데이터 점검부터 대시보드 생성까지 다시 수행합니다.</p><pre><code>python -m src.run_pipeline</code></pre><p>완료 후 생성되는 결과는 <code>reports/dashboard.html</code>, 그래프는 <code>reports/figures</code>, 데이터베이스는 <code>data/processed/transport_usage.sqlite</code>, 실행 기록은 <code>logs/pipeline.log</code>에서 확인할 수 있습니다.</p></section></div>
</div>
</main>
<footer class="footer">Data source: 국토교통부 시군구별 대중교통 이용 데이터 &nbsp;·&nbsp; Python · SQLite · Matplotlib</footer>
<script>
const links = [...document.querySelectorAll('.nav a')];
const panels = [...document.querySelectorAll('.tab-panel')];
const validTabs = ['dashboard', 'districts', 'transport', 'monthly', 'explorer', 'about'];
function showTab(tab) {{
  if (!validTabs.includes(tab)) tab = 'dashboard';
  panels.forEach(panel => panel.classList.toggle('active', panel.id === 'tab-' + tab));
  links.forEach(item => item.classList.toggle('active', item.getAttribute('href') === '#' + tab));
  window.scrollTo(0, 0);
}}
links.forEach(link => link.addEventListener('click', event => {{
  event.preventDefault();
  showTab(link.getAttribute('href').slice(1));
}}));
showTab(window.location.hash.slice(1) || 'dashboard');

const detail = {detail_json};
const districtFilter = document.getElementById('districtFilter');
const transportFilter = document.getElementById('transportFilter');
const transportNames = [...new Set(detail.transport.map(row => row.transport_type))].sort();
transportNames.forEach(name => transportFilter.add(new Option(name, name)));
const formatNumber = value => Number(value).toLocaleString('ko-KR');
function renderTable(target, headers, rows) {{
  const head = '<table><thead><tr>' + headers.map(value => '<th>' + value + '</th>').join('') + '</tr></thead><tbody>';
  const body = rows.map(row => '<tr>' + row.map((value, index) => '<td>' + (index > 0 ? formatNumber(value) : value) + '</td>').join('') + '</tr>').join('');
  target.innerHTML = head + body + '</tbody></table>';
}}
function updateExplorer() {{
  const district = districtFilter.value;
  const transport = transportFilter.value;
  const hourly = detail.hourly.filter(row => !district || row.sigungu_name === district);
  const hourlyTotals = Object.values(hourly.reduce((result, row) => {{
    result[row.hour] = (result[row.hour] || 0) + row.usage_count; return result;
  }}, {{}})).map((value, index) => [index, value]);
  renderTable(document.getElementById('hourlyResult'), ['시간', '이용량'], hourlyTotals);
  const transportRows = detail.transport.filter(row => (!district || row.sigungu_name === district) && (!transport || row.transport_type === transport));
  const grouped = Object.entries(transportRows.reduce((result, row) => {{
    result[row.transport_type] = (result[row.transport_type] || 0) + row.usage_count; return result;
  }}, {{}})).map(([name, value]) => [name, value]);
  renderTable(document.getElementById('transportResult'), ['교통수단', '이용량'], grouped);
  document.getElementById('filterTitle').textContent = (district || '전체') + ' 시간대별 이용량';
}}
districtFilter.addEventListener('change', updateExplorer);
transportFilter.addEventListener('change', updateExplorer);
updateExplorer();
</script>
</body></html>"""
    DASHBOARD_HTML.write_text(content, encoding="utf-8")


def main() -> int:
    if not CLEAN_FILE.exists() or not PERSON_CLEAN_FILE.exists() or not HOURLY_CLEAN_FILE.exists() or not GEOJSON_FILE.exists():
        print(f"[ERROR] 정제 데이터 또는 지도 경계 파일이 없습니다: {CLEAN_FILE}, {GEOJSON_FILE}")
        return 1
    _create_dashboard_image(pd.read_csv(CLEAN_FILE))
    _create_dashboard_html(pd.read_csv(CLEAN_FILE))
    print(f"[OK] PNG 대시보드: {DASHBOARD_PNG}")
    print(f"[OK] HTML 대시보드: {DASHBOARD_HTML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
