#!/usr/bin/env python3
"""
Sync section "Tổng quan POD" của Pinpoint dashboard.

Sources:
- "0. Summary Performance": monthly target/forecast/actual GP2 + DPPC
- "1. Project Planning Data": granular forecast (per project × month × function) → aggregate by month×function
- "2. Project Actual Performance": granular actual → aggregate by month×function

Targets in index.html:
- H1 KPI cards (4)
- Q2 KPI cards (4)
- chartGP2Monthly data (Budget / Forecast / Actual arrays)
- chartEfficiency data (% achievement arrays)
- Monthly table (T1-T6 + H1 total row)
- Function table (T1-T4 by function with Forecast/Actual)
- chartFunctionT3 doughnut data (latest month by function)
- chartFuncPerf bar data (latest month forecast vs actual)

Usage:
    python3 scripts/sync_pod.py            # dry-run preview
    python3 scripts/sync_pod.py --apply    # write to index.html
"""

import calendar
import datetime
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SHEET_ID = "1hDlwoQ8KgMaWsOLrooBQmlL4KQgY3c70gU0x3bJw4hI"
TAB_SUMMARY = "0. Summary Performance"
TAB_PLAN = "1. Project Planning Data"
TAB_ACTUAL = "2. Project Actual Performance"
GWS = "/usr/local/bin/gws"
REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"

# Tab 1 columns
COL_PLAN_MONTH = 3
COL_PLAN_FUNC = 23
COL_PLAN_GP2 = 50    # AY (NOT AX which has #REF! formula)

# Tab 2 columns
COL_ACT_FUNC = 1
COL_ACT_GP2 = 9      # col J = GP2.5 (raw VND) — dashboard hiển thị "THỰC TẾ GP2.5"
                     # NOTE: col F = GP2 có thể âm do điều chỉnh, GP2.5 = số kết quả cuối cùng
COL_ACT_MONTH = 11

# Latest month with actual data (T4 currently for chartFunctionT3 / chartFuncPerf)
LATEST_ACTUAL_MONTH = "T4"


def gws_read(rng):
    cmd = [
        GWS, "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps({"spreadsheetId": SHEET_ID, "range": rng}),
        "--format", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    text = out.stdout
    if text.startswith("Using keyring"):
        text = text.split("\n", 1)[1]
    return json.loads(text).get("values", [])


def to_float(s):
    if s is None or s == "":
        return 0.0
    s = str(s).strip().replace(",", "")
    if s.startswith("#") or s == "—":
        return 0.0
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_month_str(s):
    """'2026-01-01' or '1/1/2026' -> ('T1/2026', 1, 2026)."""
    if not s:
        return None, None, None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            return f"T{d.month}/{d.year}", d.month, d.year
        except ValueError:
            continue
    return None, None, None


def normalize_func(f):
    if not f:
        return ""
    f = str(f).strip().upper()
    if f in ("MED",):
        return "MEDIA"
    return f


def read_summary():
    """Read tab 0. Returns list of dicts per month."""
    rows = gws_read(f"'{TAB_SUMMARY}'!A2:J20")
    months = []
    for row in rows:
        if not row or not row[0]:
            continue
        if len(row) < 10:
            row = row + [""] * (10 - len(row))
        m_label, mnum, year = parse_month_str(row[0])
        if not m_label:
            continue
        months.append({
            "label": f"T{mnum}",
            "month_num": mnum,
            "year": year,
            "month_str": m_label,
            "progress": to_float(row[3]),     # 0-1
            "gp2_target": to_float(row[4]),
            "dppc_target": to_float(row[5]),
            "gp2_forecast": to_float(row[6]),
            "dppc_forecast": to_float(row[7]),
            "gp2_actual": to_float(row[8]),
            "dppc_actual": to_float(row[9]),
        })
    return months


def aggregate_planning_by_func():
    """Sum Adjust GP2 by (month_str, func)."""
    rows = gws_read(f"'{TAB_PLAN}'!A2:AY12500")
    agg = defaultdict(float)
    for row in rows:
        if len(row) <= COL_PLAN_GP2:
            row = row + [""] * (COL_PLAN_GP2 + 1 - len(row))
        m_label, mnum, year = parse_month_str(row[COL_PLAN_MONTH])
        if not m_label:
            continue
        func = normalize_func(row[COL_PLAN_FUNC])
        if not func:
            continue
        gp2 = to_float(row[COL_PLAN_GP2])
        agg[(m_label, func)] += gp2
    return agg


def aggregate_actual_by_func():
    """Sum GP2 (in millions) by (month_str, func)."""
    rows = gws_read(f"'{TAB_ACTUAL}'!A2:M1000")
    agg = defaultdict(float)
    for row in rows:
        if len(row) <= COL_ACT_MONTH:
            row = row + [""] * (COL_ACT_MONTH + 1 - len(row))
        m_label, mnum, year = parse_month_str(row[COL_ACT_MONTH])
        if not m_label:
            continue
        func = normalize_func(row[COL_ACT_FUNC])
        if not func:
            continue
        gp2 = to_float(row[COL_ACT_GP2]) / 1_000_000.0
        agg[(m_label, func)] += gp2
    return agg


def fmt_int(n):
    return f"{int(round(n)):,}"


def fmt_dec(n, digits=1):
    if n == 0:
        return "0"
    return f"{n:.{digits}f}"


def fmt_pct(n, digits=1):
    return f"{n:.{digits}f}%"


def class_for_pct(p):
    """Return badge class based on % achievement."""
    if p >= 100:
        return "badge-green"
    if p >= 80:
        return "badge-yellow"
    if p > 0:
        return "badge-red"
    return "badge-red"


def render_h1_kpi_cards(months):
    """Build new HTML for H1 KPI row (sum T1-T6)."""
    h1 = [m for m in months if m["month_num"] <= 6]
    gp2_actual = sum(m["gp2_actual"] for m in h1)
    gp2_forecast = sum(m["gp2_forecast"] for m in h1)
    gp2_budget = sum(m["gp2_target"] for m in h1)
    dppc_actual = sum(m["dppc_actual"] for m in h1)
    pct_actual_forecast = (gp2_actual / gp2_forecast * 100) if gp2_forecast else 0
    pct_forecast_budget = (gp2_forecast / gp2_budget * 100) if gp2_budget else 0
    pct_achieve = (gp2_actual / gp2_budget * 100) if gp2_budget else 0
    pct_dppc = (dppc_actual / gp2_actual * 100) if gp2_actual else 0

    return (
        f'<div class="kpi accent-yellow">'
        f'<div class="kpi-label">GP2 Thực tế H1</div>'
        f'<div class="kpi-val" style="color:var(--yellow)">{fmt_int(gp2_actual)}M</div>'
        f'<div class="kpi-sub warn">{fmt_pct(pct_actual_forecast)} so với Forecast</div>'
        f'</div>'
        f'<div class="kpi">'
        f'<div class="kpi-label">GP2 Dự báo H1</div>'
        f'<div class="kpi-val">{fmt_int(gp2_forecast)}M</div>'
        f'<div class="kpi-sub warn">{fmt_pct(pct_forecast_budget)} so với Budget</div>'
        f'</div>'
        f'<div class="kpi">'
        f'<div class="kpi-label">GP2 Ngân sách H1</div>'
        f'<div class="kpi-val">{fmt_int(gp2_budget)}M</div>'
        f'<div class="kpi-sub muted">Hoàn thành: {fmt_pct(pct_achieve)}</div>'
        f'</div>'
        f'<div class="kpi accent-cyan">'
        f'<div class="kpi-label">DPPC H1</div>'
        f'<div class="kpi-val" style="color:var(--cyan)">{fmt_int(dppc_actual)}M</div>'
        f'<div class="kpi-sub muted">{fmt_pct(pct_dppc)} GP2 Forecast</div>'
        f'</div>'
    )


def render_q2_kpi_cards(months):
    """Build new HTML for Q2 KPI row (sum T4-T6)."""
    q2 = [m for m in months if 4 <= m["month_num"] <= 6]
    gp2_actual = sum(m["gp2_actual"] for m in q2)
    gp2_forecast = sum(m["gp2_forecast"] for m in q2)
    gp2_budget = sum(m["gp2_target"] for m in q2)
    pct_actual_forecast = (gp2_actual / gp2_forecast * 100) if gp2_forecast else 0
    pct_forecast_budget = (gp2_forecast / gp2_budget * 100) if gp2_budget else 0
    pct_achieve = (gp2_actual / gp2_budget * 100) if gp2_budget else 0

    # Q2 time elapsed: avg of T4-T6 progress
    q2_progress = sum(m["progress"] for m in q2) / len(q2) if q2 else 0
    last_month_with_actual = max((m for m in q2 if m["gp2_actual"] > 0), key=lambda m: m["month_num"], default=None)
    last_progress = (last_month_with_actual["progress"] * 100) if last_month_with_actual else 0
    last_label = last_month_with_actual["label"] if last_month_with_actual else "—"

    return (
        f'<div class="kpi accent-orange">'
        f'<div class="kpi-label">GP2 Thực tế Q2</div>'
        f'<div class="kpi-val" style="color:var(--orange)">{fmt_int(gp2_actual)}M</div>'
        f'<div class="kpi-sub warn">{fmt_pct(pct_actual_forecast)} so với Forecast</div>'
        f'</div>'
        f'<div class="kpi">'
        f'<div class="kpi-label">GP2 Dự báo Q2</div>'
        f'<div class="kpi-val">{fmt_int(gp2_forecast)}M</div>'
        f'<div class="kpi-sub warn">{fmt_pct(pct_forecast_budget)} so với Budget</div>'
        f'</div>'
        f'<div class="kpi">'
        f'<div class="kpi-label">GP2 Ngân sách Q2</div>'
        f'<div class="kpi-val">{fmt_int(gp2_budget)}M</div>'
        f'<div class="kpi-sub muted">Hoàn thành: {fmt_pct(pct_achieve)}</div>'
        f'</div>'
        f'<div class="kpi accent-cyan">'
        f'<div class="kpi-label">Q2 Thời gian đã qua</div>'
        f'<div class="kpi-val" style="color:var(--cyan)">{fmt_pct(q2_progress * 100)}</div>'
        f'<div class="kpi-sub muted">{last_label}: hoàn tất {fmt_pct(last_progress)}</div>'
        f'</div>'
    )


def render_monthly_table(months):
    """T1-T6 rows + H1 total row."""
    h1 = [m for m in months if m["month_num"] <= 6]
    rows = []
    for m in h1:
        progress = m["progress"] * 100
        gp2_t = m["gp2_target"]
        gp2_f = m["gp2_forecast"]
        gp2_a = m["gp2_actual"]
        dppc_a = m["dppc_actual"]
        pct_fb = (gp2_f / gp2_t * 100) if gp2_t else 0
        pct_ab = (gp2_a / gp2_t * 100) if gp2_t else 0
        runrate = gp2_f * m["progress"]
        pct_ar = (gp2_a / runrate * 100) if runrate else 0
        pct_dppc = (dppc_a / gp2_a * 100) if gp2_a else 0
        # Style for future months (no actual)
        opacity = ' style="opacity:0.5"' if gp2_a == 0 and progress < 100 else ""
        ab_badge = f'<span class="badge {class_for_pct(pct_ab)}">{fmt_pct(pct_ab)}</span>' if gp2_a > 0 else "—"
        ar_badge = f'<span class="badge {class_for_pct(pct_ar)}">{fmt_pct(pct_ar)}</span>' if gp2_a > 0 else "—"
        actual_str = f"{fmt_int(gp2_a)}" if gp2_a > 0 else "—"
        dppc_str = f"{fmt_int(dppc_a)}" if dppc_a > 0 else "—"
        progress_str = f"{int(progress)}%" if progress > 0 else "0%"
        rows.append(
            f'<tr{opacity}><td><strong>{m["label"]}</strong></td>'
            f'<td>{fmt_int(gp2_t)}</td><td>{fmt_int(gp2_f)}</td>'
            f'<td>{actual_str}</td><td>{progress_str}</td>'
            f'<td>{fmt_pct(pct_fb)}</td><td>{ab_badge}</td><td>{ar_badge}</td>'
            f'<td>{dppc_str}</td><td>{fmt_pct(pct_dppc)}</td></tr>'
        )

    # Total H1 row
    t = sum(m["gp2_target"] for m in h1)
    f = sum(m["gp2_forecast"] for m in h1)
    a = sum(m["gp2_actual"] for m in h1)
    d = sum(m["dppc_actual"] for m in h1)
    pct_fb = (f / t * 100) if t else 0
    pct_ab = (a / t * 100) if t else 0
    # Sum of runrate vs sum of actual for H1
    sum_runrate = sum(mm["gp2_forecast"] * mm["progress"] for mm in h1)
    pct_ar = (a / sum_runrate * 100) if sum_runrate else 0
    pct_dppc = (d / a * 100) if a else 0
    rows.append(
        f'<tr style="font-weight:700; border-top:2px solid var(--border);">'
        f'<td>H1 2026</td>'
        f'<td>{fmt_int(t)}</td><td>{fmt_int(f)}</td><td>{fmt_int(a)}</td>'
        f'<td></td><td>{fmt_pct(pct_fb)}</td>'
        f'<td><span class="badge {class_for_pct(pct_ab)}">{fmt_pct(pct_ab)}</span></td>'
        f'<td><span class="badge {class_for_pct(pct_ar)}">{fmt_pct(pct_ar)}</span></td>'
        f'<td>{fmt_int(d)}</td><td>{fmt_pct(pct_dppc)}</td></tr>'
    )
    return "\n                ".join(rows)


def render_function_table(planning, actual, months):
    """Build T1-T4 by function: Forecast / Actual / runrate."""
    # Get past months (gp2_actual > 0 OR progress = 100%)
    past_months = [m for m in months if m["gp2_actual"] > 0 or m["progress"] >= 1.0]
    past_months = sorted(past_months, key=lambda m: m["month_num"])

    # Group by month, then function
    rows_html = []
    for m in past_months:
        m_label = m["month_str"]
        # Find all funcs that have non-zero forecast or actual in this month
        funcs_in_month = set()
        for (mlabel, func), v in planning.items():
            if mlabel == m_label and v != 0:
                funcs_in_month.add(func)
        for (mlabel, func), v in actual.items():
            if mlabel == m_label and v != 0:
                funcs_in_month.add(func)
        # Order: MEDIA first, then by forecast desc
        func_order = []
        if "MEDIA" in funcs_in_month:
            func_order.append("MEDIA")
            funcs_in_month.discard("MEDIA")
        # Sort remaining by forecast value desc
        remaining = sorted(funcs_in_month, key=lambda f: -planning.get((m_label, f), 0))
        func_order.extend(remaining)

        for i, func in enumerate(func_order):
            forecast = planning.get((m_label, func), 0)
            act = actual.get((m_label, func), 0)
            pct_fcast = (act / forecast * 100) if forecast else 0
            runrate = forecast * m["progress"]
            pct_runrate = (act / runrate * 100) if runrate else 0
            label_td = f'<td><strong>{m["label"]}</strong></td>' if i == 0 else f'<td>{m["label"]}</td>'
            func_td = f'<td><strong>{func}</strong></td>' if func == "MEDIA" else f'<td>{func}</td>'
            top_border = ' style="border-top:2px solid var(--border);"' if i == 0 else ""
            fcast_badge = f'<span class="badge {class_for_pct(pct_fcast)}">{fmt_pct(pct_fcast)}</span>'
            runrate_badge = f'<span class="badge {class_for_pct(pct_runrate)}">{fmt_pct(pct_runrate)}</span>'
            rows_html.append(
                f'<tr{top_border}>{label_td}{func_td}'
                f'<td>{fmt_dec(forecast)}</td><td>{fmt_dec(act)}</td>'
                f'<td>{fcast_badge}</td>'
                f'<td>{fmt_dec(runrate)}</td>'
                f'<td>{runrate_badge}</td></tr>'
            )

    return "\n                ".join(rows_html)


def render_chart_gp2_monthly(months):
    """T1-T6 Budget/Forecast/Actual arrays."""
    h1 = [m for m in months if m["month_num"] <= 6]
    h1 = sorted(h1, key=lambda m: m["month_num"])
    labels = [m["label"] for m in h1]
    budgets = [int(round(m["gp2_target"])) for m in h1]
    forecasts = [round(m["gp2_forecast"], 1) for m in h1]
    actuals = [round(m["gp2_actual"], 1) for m in h1]
    return labels, budgets, forecasts, actuals


def render_chart_efficiency(months):
    """Past months only (where actual > 0): % Act/Forecast and % Act/Runrate."""
    past = [m for m in months if m["gp2_actual"] > 0]
    past = sorted(past, key=lambda m: m["month_num"])
    labels = [m["label"] for m in past]
    pct_af = []
    pct_ar = []
    for m in past:
        af = (m["gp2_actual"] / m["gp2_forecast"] * 100) if m["gp2_forecast"] else 0
        runrate = m["gp2_forecast"] * m["progress"]
        ar = (m["gp2_actual"] / runrate * 100) if runrate else 0
        pct_af.append(round(af, 1))
        pct_ar.append(round(ar, 1))
    return labels, pct_af, pct_ar


def latest_actual_month_str(months):
    past = [m for m in months if m["gp2_actual"] > 0]
    if not past:
        return None
    last = max(past, key=lambda m: m["month_num"])
    return last["month_str"], last["label"]


def render_chart_function_doughnut(actual_agg, latest_month_str):
    """Latest month — funcs with actual > 0."""
    items = [(f, v) for (m, f), v in actual_agg.items() if m == latest_month_str and v > 0]
    items.sort(key=lambda x: -x[1])
    return [i[0] for i in items], [round(i[1], 1) for i in items]


def render_chart_func_perf(planning_agg, actual_agg, latest_month_str):
    """Latest month forecast vs actual by function."""
    funcs = set()
    for (m, f), v in planning_agg.items():
        if m == latest_month_str and v > 0:
            funcs.add(f)
    for (m, f), v in actual_agg.items():
        if m == latest_month_str and v != 0:
            funcs.add(f)
    # Order: MEDIA, CREATIVE, LIVESTREAM, then rest
    order = ["MEDIA", "CREATIVE", "LIVESTREAM", "INFLUENCER", "TECH_DATA", "CCM"]
    ordered = [f for f in order if f in funcs] + [f for f in funcs if f not in order]
    forecasts = [round(planning_agg.get((latest_month_str, f), 0), 1) for f in ordered]
    actuals = [round(actual_agg.get((latest_month_str, f), 0), 1) for f in ordered]
    return ordered, forecasts, actuals


def replace_block(html, marker_start, marker_end_re, new_inner, *, label):
    """Replace inner content between marker_start and the first matching marker_end_re after it."""
    idx = html.find(marker_start)
    if idx == -1:
        raise RuntimeError(f"Marker not found ({label}): {marker_start[:60]}")
    end_match = re.search(marker_end_re, html[idx + len(marker_start):])
    if not end_match:
        raise RuntimeError(f"End marker not found ({label})")
    end_idx = idx + len(marker_start) + end_match.start()
    return html[:idx + len(marker_start)] + new_inner + html[end_idx:]


def patch_kpi_row(html, label_first_card, last_card_label, new_inner_html):
    """Replace a kpi-row block that spans from kpi card containing label_first_card
    through kpi card containing last_card_label.
    Match end: kpi-sub closing </div> + (whitespace) + kpi outer closing </div>."""
    start = html.find(label_first_card)
    if start == -1:
        raise RuntimeError(f"First card label not found: {label_first_card}")
    # Walk back to outer card opening — match `<div class="kpi"` or `<div class="kpi accent-...`
    # NOT kpi-label/kpi-val/kpi-sub.
    outer_card_pattern = re.compile(r'<div class="kpi(?:["\s])')
    matches = list(outer_card_pattern.finditer(html, 0, start))
    if not matches:
        raise RuntimeError(f"Cannot find outer KPI card before {label_first_card}")
    card_start = matches[-1].start()
    end_label_idx = html.find(last_card_label, card_start)
    if end_label_idx == -1:
        raise RuntimeError(f"Last card label not found: {last_card_label}")
    # The last card structure: outer <div class="kpi"> contains kpi-label, kpi-val, kpi-sub.
    # Find the kpi-sub div in this card, then take its closing </div> + outer </div>.
    sub_idx = html.find('<div class="kpi-sub', end_label_idx)
    if sub_idx == -1:
        raise RuntimeError(f"kpi-sub not found after {last_card_label}")
    # Find closing </div> of kpi-sub
    sub_close = html.find("</div>", sub_idx)
    if sub_close == -1:
        raise RuntimeError("kpi-sub closing div not found")
    # Find next </div> after that — closes the outer kpi card
    outer_close = html.find("</div>", sub_close + len("</div>"))
    if outer_close == -1:
        raise RuntimeError("outer kpi closing div not found")
    end = outer_close + len("</div>")
    return html[:card_start] + new_inner_html + html[end:]


def patch_chart_data(html, chart_id, new_arrays):
    """Replace data inside a Chart() block by chart_id.
    new_arrays: dict keyed by dataset label OR list per dataset position."""
    # Find the Chart block by ID
    pattern_start = f"new Chart(document.getElementById('{chart_id}')"
    idx = html.find(pattern_start)
    if idx == -1:
        raise RuntimeError(f"Chart not found: {chart_id}")
    # Find end of this chart block (closing `});` followed by newline)
    # Look for `});` after a newline at depth 0
    # Simpler: find the next occurrence of `\n});` and assume that's the end
    end_idx = html.find("\n});", idx)
    if end_idx == -1:
        raise RuntimeError(f"Chart block end not found: {chart_id}")
    block = html[idx:end_idx]

    # Replace data: { labels: [...], datasets: [...] }
    # Keep style/options intact. Use a regex on the data block.
    new_data_str = json.dumps(new_arrays)
    # We'll use targeted replacements — see callers.
    return idx, end_idx, block


def update_chart_arrays(html, chart_id, replacements):
    """Replace specific arrays inside a chart block.
    replacements: list of (regex_pattern, replacement_string).
    Pattern is applied only to text within that chart block."""
    pattern_start = f"new Chart(document.getElementById('{chart_id}')"
    idx = html.find(pattern_start)
    if idx == -1:
        raise RuntimeError(f"Chart not found: {chart_id}")
    end_idx = html.find("\n});", idx)
    if end_idx == -1:
        raise RuntimeError(f"Chart block end not found: {chart_id}")
    block = html[idx:end_idx]
    new_block = block
    for pat, repl in replacements:
        new_block = re.sub(pat, repl, new_block, count=1)
    return html[:idx] + new_block + html[end_idx:]


def main():
    apply = "--apply" in sys.argv

    print("Đang đọc Tab 0. Summary Performance...")
    months = read_summary()
    print(f"  Tháng đọc được: {[m['label'] for m in months]}")

    print("Đang aggregate Planning by function...")
    planning = aggregate_planning_by_func()
    print(f"  Planning entries (month, func): {len(planning)}")

    print("Đang aggregate Actual by function...")
    actual = aggregate_actual_by_func()
    print(f"  Actual entries (month, func): {len(actual)}")

    # Build all updates
    new_h1 = render_h1_kpi_cards(months)
    new_q2 = render_q2_kpi_cards(months)
    new_monthly_rows = render_monthly_table(months)
    new_function_rows = render_function_table(planning, actual, months)

    chart_labels, budgets, forecasts, actuals = render_chart_gp2_monthly(months)
    eff_labels, pct_af, pct_ar = render_chart_efficiency(months)
    latest_info = latest_actual_month_str(months)
    if latest_info:
        latest_str, latest_label = latest_info
    else:
        latest_str, latest_label = None, "—"

    # Doughnut & FuncPerf use latest month with actual
    if latest_str:
        donut_labels, donut_data = render_chart_function_doughnut(actual, latest_str)
        fp_labels, fp_forecasts, fp_actuals = render_chart_func_perf(planning, actual, latest_str)
    else:
        donut_labels, donut_data, fp_labels, fp_forecasts, fp_actuals = [], [], [], [], []

    print("\n=== Computed values ===")
    h1 = [m for m in months if m["month_num"] <= 6]
    print(f"H1 Actual: {sum(m['gp2_actual'] for m in h1):.0f}M, "
          f"Forecast: {sum(m['gp2_forecast'] for m in h1):.0f}M, "
          f"Budget: {sum(m['gp2_target'] for m in h1):.0f}M")
    print(f"Chart GP2 labels: {chart_labels}")
    print(f"Chart GP2 actuals: {actuals}")
    print(f"Latest month with actual: {latest_label}")
    print(f"Doughnut latest: {donut_labels} = {donut_data}")
    print(f"FuncPerf latest: {fp_labels}")
    print(f"  forecasts: {fp_forecasts}")
    print(f"  actuals: {fp_actuals}")

    # ============================ APPLY UPDATES ============================
    html = INDEX.read_text(encoding="utf-8")

    # 1. H1 KPI row
    html = patch_kpi_row(html, "GP2 Thực tế H1", "DPPC H1", new_h1)
    # 2. Q2 KPI row
    html = patch_kpi_row(html, "GP2 Thực tế Q2", "Q2 Thời gian đã qua", new_q2)

    # 3. Monthly table — replace tbody contents
    monthly_pattern = re.compile(
        r'(<h3>Chi tiết theo tháng</h3>\s*<table>\s*<thead>[\s\S]*?</thead>\s*<tbody>\s*)([\s\S]*?)(\s*</tbody>\s*</table>)',
        re.MULTILINE,
    )
    if not monthly_pattern.search(html):
        raise RuntimeError("Monthly table not found")
    html = monthly_pattern.sub(rf'\1{new_monthly_rows}\3', html, count=1)

    # 4. Function table — replace tbody contents
    func_pattern = re.compile(
        r'(<h3>Chi tiết theo Function — T1 đến T4/2026</h3>\s*<table>\s*<thead>[\s\S]*?</thead>\s*<tbody>\s*)([\s\S]*?)(\s*</tbody>\s*</table>)',
        re.MULTILINE,
    )
    if not func_pattern.search(html):
        # Title may have changed if T4 → T5. Try fuzzy match
        func_pattern2 = re.compile(
            r'(<h3>Chi tiết theo Function[^<]*</h3>\s*<table>\s*<thead>[\s\S]*?</thead>\s*<tbody>\s*)([\s\S]*?)(\s*</tbody>\s*</table>)',
            re.MULTILINE,
        )
        if not func_pattern2.search(html):
            raise RuntimeError("Function table not found")
        html = func_pattern2.sub(rf'\1{new_function_rows}\3', html, count=1)
    else:
        html = func_pattern.sub(rf'\1{new_function_rows}\3', html, count=1)

    # 5. chartGP2Monthly — replace labels + 3 datasets data arrays
    new_labels_str = "[" + ",".join(f"'{l}'" for l in chart_labels) + "]"
    new_budgets_str = "[" + ", ".join(str(v) for v in budgets) + "]"
    new_forecasts_str = "[" + ", ".join(str(v) for v in forecasts) + "]"
    new_actuals_str = "[" + ", ".join(str(v) for v in actuals) + "]"
    html = update_chart_arrays(html, "chartGP2Monthly", [
        (r"labels: \[[^\]]*\]", f"labels: {new_labels_str}"),
        (r"label: 'Budget', data: \[[^\]]*\]", f"label: 'Budget', data: {new_budgets_str}"),
        (r"label: 'Forecast', data: \[[^\]]*\]", f"label: 'Forecast', data: {new_forecasts_str}"),
        (r"label: 'Actual', data: \[[^\]]*\]", f"label: 'Actual', data: {new_actuals_str}"),
    ])

    # 6. chartEfficiency — labels + 3 datasets (% Act/Forecast, % Actual/Runrate, Target 100%)
    eff_labels_str = "[" + ",".join(f"'{l}'" for l in eff_labels) + "]"
    eff_af_str = "[" + ", ".join(str(v) for v in pct_af) + "]"
    eff_ar_str = "[" + ", ".join(str(v) for v in pct_ar) + "]"
    eff_target_str = "[" + ",".join("100" for _ in eff_labels) + "]"
    html = update_chart_arrays(html, "chartEfficiency", [
        (r"labels: \[[^\]]*\]", f"labels: {eff_labels_str}"),
        (r"label: '% Act/Forecast', data: \[[^\]]*\]", f"label: '% Act/Forecast', data: {eff_af_str}"),
        (r"label: '% Actual/Runrate', data: \[[^\]]*\]", f"label: '% Actual/Runrate', data: {eff_ar_str}"),
        (r"label: 'Target 100%', data: \[[^\]]*\]", f"label: 'Target 100%', data: {eff_target_str}"),
    ])

    # 7. chartFunctionT3 — doughnut for latest month
    donut_labels_str = "[" + ",".join(f"'{l}'" for l in donut_labels) + "]"
    donut_data_str = "[" + ", ".join(str(v) for v in donut_data) + "]"
    # Generate background colors based on label count
    color_palette = ["'#3b82f6'", "'#f97316'", "'#a855f7'", "'#22c55e'", "'#ef4444'", "'#06b6d4'", "'#eab308'", "'#ec4899'"]
    donut_colors = "[" + ",".join(color_palette[:len(donut_labels)]) + "]"
    html = update_chart_arrays(html, "chartFunctionT3", [
        (r"labels: \[[^\]]*\]", f"labels: {donut_labels_str}"),
        (r"data: \[[^\]]*\]", f"data: {donut_data_str}"),
        (r"backgroundColor: \[[^\]]*\]", f"backgroundColor: {donut_colors}"),
    ])
    # Update chart title to reflect latest month
    html = re.sub(
        r'<h3>Phân bổ GP2 theo Function — T\d+/\d+</h3>',
        f'<h3>Phân bổ GP2 theo Function — {latest_label}/2026</h3>',
        html, count=1
    )

    # 8. chartFuncPerf — bar latest month
    fp_labels_str = "[" + ",".join(f"'{l}'" for l in fp_labels) + "]"
    fp_forecasts_str = "[" + ", ".join(str(v) for v in fp_forecasts) + "]"
    fp_actuals_str = "[" + ", ".join(str(v) for v in fp_actuals) + "]"
    html = update_chart_arrays(html, "chartFuncPerf", [
        (r"labels: \[[^\]]*\]", f"labels: {fp_labels_str}"),
        (r"label: 'Forecast', data: \[[^\]]*\]", f"label: 'Forecast', data: {fp_forecasts_str}"),
        (r"label: 'Actual', data: \[[^\]]*\]", f"label: 'Actual', data: {fp_actuals_str}"),
    ])
    html = re.sub(
        r'<h3>Hiệu suất Function vs Runrate — T\d+/\d+</h3>',
        f'<h3>Hiệu suất Function vs Runrate — {latest_label}/2026</h3>',
        html, count=1
    )

    if apply:
        INDEX.write_text(html, encoding="utf-8")
        print(f"\n✅ Đã update {INDEX}")
    else:
        print("\n(Chạy lại với --apply để ghi vào index.html)")


if __name__ == "__main__":
    main()
