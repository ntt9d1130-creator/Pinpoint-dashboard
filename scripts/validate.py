#!/usr/bin/env python3
"""
Validation / sanity check cho Pinpoint dashboard.

So sánh:
1. Sheet totals (Tab 0/1/2/4) vs JS arrays trong index.html
2. Cross-checks: Quarter Actual Lead phải ≈ sum weekly leads
3. Function table sums vs Tab 0 monthly actuals
4. Project totals vs Tab 0 totals

Output:
  ✅ MATCH (sai số < 1%)
  ⚠️  MINOR DRIFT (1-5%)
  ❌ MAJOR DRIFT (> 5%)

Usage:
    python3 scripts/validate.py
    python3 scripts/validate.py --strict   # exit 1 nếu có ❌
"""

import datetime
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SHEET_ID = "1hDlwoQ8KgMaWsOLrooBQmlL4KQgY3c70gU0x3bJw4hI"
GWS = "/usr/local/bin/gws"
REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"

THRESHOLD_OK = 0.01     # 1%
THRESHOLD_WARN = 0.05   # 5%


# ---------- gws helpers ----------
def gws_read(rng):
    cmd = [GWS, "sheets", "spreadsheets", "values", "get",
           "--params", json.dumps({"spreadsheetId": SHEET_ID, "range": rng}),
           "--format", "json"]
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
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_month(s):
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


DATA_JS = REPO / "data" / "data.js"


def extract_js_array(name):
    """Return list from data/data.js (post-refactor) or fallback to regex from index.html."""
    # Try data.js first
    if DATA_JS.exists():
        js_code = (
            f"const fs=require('fs');"
            f"const txt=fs.readFileSync('{DATA_JS}','utf8');"
            f"const ctx={{window:{{}}}};"
            f"new Function('window',txt)(ctx.window);"
            f"console.log(JSON.stringify(ctx.window.DASHBOARD_DATA['{name}']));"
        )
        out = subprocess.run(["node", "-e", js_code], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip() and out.stdout.strip() != "undefined":
            return json.loads(out.stdout)

    # Fallback: extract from index.html as JS literal
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(rf"const {name} = (\[[\s\S]*?\]);", html)
    if not m:
        return None
    js_code = f"console.log(JSON.stringify({m.group(1)}));"
    out = subprocess.run(["node", "-e", js_code], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def extract_html_value(label_text, after=None):
    """Find a number near a label like 'GP2 Thực tế H1' in index.html.
    Returns first integer/float found in the same kpi card."""
    html = INDEX.read_text(encoding="utf-8")
    start = html.find(label_text, after or 0)
    if start == -1:
        return None
    # Look for kpi-val span/div containing number+M
    region = html[start:start + 500]
    m = re.search(r'kpi-val[^>]*>([0-9,\.\-]+)M?</div>', region)
    if not m:
        m = re.search(r'>([0-9,\.\-]+)M?<', region)
    if m:
        return to_float(m.group(1))
    return None


# ---------- check helpers ----------
def fmt_diff(actual, expected):
    """Return (status_emoji, pct_diff_str)."""
    if expected == 0 and actual == 0:
        return "✅", "0%"
    if expected == 0:
        return "❌", "∞ (expected 0)"
    diff_pct = abs(actual - expected) / abs(expected)
    if diff_pct < THRESHOLD_OK:
        return "✅", f"{diff_pct*100:.2f}%"
    if diff_pct < THRESHOLD_WARN:
        return "⚠️ ", f"{diff_pct*100:.2f}%"
    return "❌", f"{diff_pct*100:.2f}%"


def check(label, dashboard_value, sheet_value, unit=""):
    """Print one check line, return status."""
    emoji, pct = fmt_diff(dashboard_value, sheet_value)
    line = (f"  {emoji} {label:<55} | dashboard: {dashboard_value:>10.1f}{unit:>4} "
            f"| sheet: {sheet_value:>10.1f}{unit:>4} | diff: {pct}")
    print(line)
    return emoji


# ---------- checks ----------
def check_growth_section():
    print("\n=== SECTION TĂNG TRƯỞNG ===")
    issues = []

    # Read Tab 4 quarter summary
    rows = gws_read("'4. Summary Sales Performance'!A1:I12")
    quarter_actual = {}
    for row in rows:
        if len(row) > 2 and row[1].strip() == "Actual (Quarter)":
            stages = ["lead", "ql", "brief", "qb", "qs", "vc", "contract"]
            for i, stage in enumerate(stages):
                quarter_actual[stage] = to_float(row[2 + i] if 2 + i < len(row) else 0)

    # Check weeklyData sum vs quarter actual
    weekly = extract_js_array("weeklyData") or []
    sum_weekly_lead = sum(w.get("lead", 0) for w in weekly)
    sum_weekly_contract = sum(w.get("contract", 0) for w in weekly)
    issues.append(check("weeklyData lead sum vs Quarter Actual Lead",
                        sum_weekly_lead, quarter_actual.get("lead", 0)))
    issues.append(check("weeklyData contract sum vs Quarter Actual Contract",
                        sum_weekly_contract, quarter_actual.get("contract", 0)))

    # vertical sum lead vs sheet vertical Total
    rows = gws_read("'4. Summary Sales Performance'!B73:J90")
    vt_lead = vt_contract = 0
    for row in rows:
        if len(row) > 1 and row[0].strip() == "Total":
            vt_lead = to_float(row[1] if len(row) > 1 else 0)
            vt_contract = to_float(row[8] if len(row) > 8 else 0)
            break
    vertical = extract_js_array("verticalData") or []
    sum_v_lead = sum(v.get("lead", 0) for v in vertical)
    sum_v_contract = sum(v.get("contract", 0) for v in vertical)
    issues.append(check("verticalData lead sum vs sheet Vertical Total",
                        sum_v_lead, vt_lead))
    issues.append(check("verticalData contract sum vs sheet Vertical Total",
                        sum_v_contract, vt_contract))

    # source sum lead vs sheet source Total
    rows = gws_read("'4. Summary Sales Performance'!B49:J72")
    st_lead = st_contract = 0
    for row in rows:
        if len(row) > 1 and row[0].strip() == "Total":
            st_lead = to_float(row[1] if len(row) > 1 else 0)
            st_contract = to_float(row[8] if len(row) > 8 else 0)
            break
    source = extract_js_array("sourceData") or []
    sum_s_lead = sum(s.get("lead", 0) for s in source)
    sum_s_contract = sum(s.get("contract", 0) for s in source)
    issues.append(check("sourceData lead sum vs sheet Source Total",
                        sum_s_lead, st_lead))
    issues.append(check("sourceData contract sum vs sheet Source Total",
                        sum_s_contract, st_contract))

    # cross-check: Quarter Actual lead vs vertical/source totals
    print("\n  Cross-checks:")
    print(f"  Quarter Actual Lead   : {quarter_actual.get('lead', 0):>5.0f}")
    print(f"  Vertical Total Lead   : {sum_v_lead:>5.0f}")
    print(f"  Source Total Lead     : {sum_s_lead:>5.0f}")
    if abs(sum_v_lead - sum_s_lead) > 5:
        print(f"  ⚠️  Vertical vs Source lệch {abs(sum_v_lead - sum_s_lead):.0f} leads")

    return issues


def check_pod_section():
    print("\n=== SECTION TỔNG QUAN POD ===")
    issues = []

    # Read Tab 0 summary monthly data
    rows = gws_read("'0. Summary Performance'!A2:J20")
    months = []
    for row in rows:
        if not row or not row[0]:
            continue
        if len(row) < 10:
            row = row + [""] * (10 - len(row))
        m_label, mnum, year = parse_month(row[0])
        if not m_label:
            continue
        months.append({
            "month_num": mnum, "year": year, "label": f"T{mnum}",
            "gp2_target": to_float(row[4]),
            "gp2_forecast": to_float(row[6]),
            "gp2_actual": to_float(row[8]),
            "dppc_actual": to_float(row[9]),
        })

    h1 = [m for m in months if m["month_num"] <= 6]
    sheet_h1_actual = sum(m["gp2_actual"] for m in h1)
    sheet_h1_forecast = sum(m["gp2_forecast"] for m in h1)
    sheet_h1_budget = sum(m["gp2_target"] for m in h1)
    sheet_h1_dppc = sum(m["dppc_actual"] for m in h1)

    # Extract from HTML KPI cards
    dash_h1_actual = extract_html_value("GP2 Thực tế H1") or 0
    dash_h1_forecast = extract_html_value("GP2 Dự báo H1") or 0
    dash_h1_budget = extract_html_value("GP2 Ngân sách H1") or 0
    dash_h1_dppc = extract_html_value("DPPC H1") or 0

    issues.append(check("H1 GP2 Actual", dash_h1_actual, sheet_h1_actual, "M"))
    issues.append(check("H1 GP2 Forecast", dash_h1_forecast, sheet_h1_forecast, "M"))
    issues.append(check("H1 GP2 Budget", dash_h1_budget, sheet_h1_budget, "M"))
    issues.append(check("H1 DPPC Actual", dash_h1_dppc, sheet_h1_dppc, "M"))

    return issues


def check_project_section():
    print("\n=== SECTION CHI TIẾT PROJECT ===")
    issues = []

    # Read Tab 0 summary
    rows = gws_read("'0. Summary Performance'!A2:J20")
    sheet_actual_by_month = {}
    sheet_forecast_by_month = {}
    for row in rows:
        if not row or not row[0]:
            continue
        if len(row) < 10:
            row = row + [""] * (10 - len(row))
        m_label, mnum, year = parse_month(row[0])
        if not m_label:
            continue
        sheet_actual_by_month[m_label] = to_float(row[8])
        sheet_forecast_by_month[m_label] = to_float(row[6])

    project = extract_js_array("projectData") or []
    proj_actual_by_month = defaultdict(float)
    proj_forecast_by_month = defaultdict(float)
    for p in project:
        proj_actual_by_month[p.get("month", "")] += p.get("actual", 0)
        proj_forecast_by_month[p.get("month", "")] += p.get("forecast", 0)

    # Compare monthly totals (only months with sheet actual > 0)
    print("\n  Per-month actual GP2 (project sum vs sheet):")
    for month_str in sorted(sheet_actual_by_month.keys(),
                             key=lambda m: (int(m.split("/")[1]),
                                            int(m.split("/")[0][1:]))):
        sheet_a = sheet_actual_by_month[month_str]
        proj_a = proj_actual_by_month.get(month_str, 0)
        if sheet_a > 0 or proj_a > 0:
            issues.append(check(f"  {month_str} actual", proj_a, sheet_a, "M"))

    print("\n  Per-month forecast GP2 (project sum vs sheet):")
    for month_str in sorted(sheet_forecast_by_month.keys(),
                             key=lambda m: (int(m.split("/")[1]),
                                            int(m.split("/")[0][1:]))):
        sheet_f = sheet_forecast_by_month[month_str]
        proj_f = proj_forecast_by_month.get(month_str, 0)
        if sheet_f > 0 or proj_f > 0:
            issues.append(check(f"  {month_str} forecast", proj_f, sheet_f, "M"))

    return issues


# ---------- main ----------
def main():
    strict = "--strict" in sys.argv

    print("Pinpoint Dashboard — Validation")
    print(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not INDEX.exists():
        print(f"❌ {INDEX} not found")
        sys.exit(1)

    all_issues = []
    try:
        all_issues.extend(check_growth_section())
    except Exception as e:
        print(f"❌ Growth check error: {e}")
    try:
        all_issues.extend(check_pod_section())
    except Exception as e:
        print(f"❌ POD check error: {e}")
    try:
        all_issues.extend(check_project_section())
    except Exception as e:
        print(f"❌ Project check error: {e}")

    # Summary
    n_ok = sum(1 for x in all_issues if x == "✅")
    n_warn = sum(1 for x in all_issues if x == "⚠️ ")
    n_err = sum(1 for x in all_issues if x == "❌")
    print(f"\n=== SUMMARY ===")
    print(f"  Total checks: {len(all_issues)}")
    print(f"  ✅ OK     : {n_ok}")
    print(f"  ⚠️  Warn  : {n_warn}  (drift 1-5%)")
    print(f"  ❌ Error  : {n_err}  (drift > 5%)")

    if strict and n_err > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
