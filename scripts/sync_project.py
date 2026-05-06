#!/usr/bin/env python3
"""
Sync section "Chi tiết Project" của Pinpoint dashboard.

Source: 2 tabs trong "Total Dashboard":
- "1. Project Planning Data" (forecast Adjust GP2 per project × month × function)
- "2. Project Actual Performance" (actual GP2)

Mapping: theo "Project code and name" (col S Tab1, col A Tab2). Match exact trước,
sau đó fuzzy match (similarity >= 0.85) cho phần còn lại.

Target: const projectData = [...] trong index.html

Usage:
    python3 scripts/sync_project.py            # dry-run
    python3 scripts/sync_project.py --apply    # write to index.html
"""

import calendar
import datetime
import difflib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Config
SHEET_ID = "1hDlwoQ8KgMaWsOLrooBQmlL4KQgY3c70gU0x3bJw4hI"
TAB_PLAN = "1. Project Planning Data"
TAB_ACTUAL = "2. Project Actual Performance"
GWS = "/usr/local/bin/gws"
REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"

# Tab 1 columns (1-indexed → 0-indexed)
COL_PLAN_MONTH = 3       # D = Month (date)
COL_PLAN_NAME = 18       # S = Project code and name
COL_PLAN_CODE = 19       # T = Project Code
COL_PLAN_FUNC = 23       # X = Function
COL_PLAN_GP2 = 50        # AY = numeric Adjust GP2 (col AX has header "Adjust GP2" but formula errors with #REF!)

# Tab 2 columns
COL_ACT_NAME = 0         # A = Project code and name
COL_ACT_FUNC = 1         # B = function
COL_ACT_GP2 = 5          # F = GP2 (raw VND)
COL_ACT_MONTH = 11       # L = Month (date)


def gws_batch_read(ranges):
    """Read multiple ranges in one batchGet call. Returns dict {range: values}."""
    cmd = [
        GWS, "sheets", "spreadsheets", "values", "batchGet",
        "--params", json.dumps({
            "spreadsheetId": SHEET_ID,
            "ranges": ranges,
        }),
        "--format", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    text = out.stdout
    if text.startswith("Using keyring"):
        text = text.split("\n", 1)[1]
    data = json.loads(text)
    return {vr.get("range", ""): vr.get("values", []) for vr in data.get("valueRanges", [])}


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
    s = str(s).strip()
    # Handle Vietnamese decimals (rare but safe)
    if s.startswith("#"):  # #REF!, #VALUE!, #DIV/0!
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0


def parse_month(date_str):
    """Convert '2026-01-01' or '1/1/2026' -> 'T1/2026' and (year, month)."""
    if not date_str:
        return None, None, None
    s = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            return f"T{d.month}/{d.year}", d.year, d.month
        except ValueError:
            continue
    return None, None, None


def normalize_func(f):
    """Normalize function name to UPPERCASE."""
    if not f:
        return ""
    f = str(f).strip().upper()
    # Map common variants
    if f in ("MEDIA", "MED"):
        return "MEDIA"
    return f


def normalize_name_for_match(name):
    """Normalize project name for fuzzy matching."""
    s = str(name).lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def aggregate_planning():
    """Read Tab 1 columns we need and aggregate by (month_str, name, func) → forecast."""
    print(f"  Reading {TAB_PLAN} (large, ~12k rows)...")
    # Read full range A2:AX12500 for all needed columns in one shot
    rows = gws_read(f"'{TAB_PLAN}'!A2:AY12500")
    print(f"  Got {len(rows)} rows")

    agg = defaultdict(float)
    code_lookup = {}  # name -> code (first seen)
    for row in rows:
        if len(row) <= COL_PLAN_GP2:
            # extend with empties
            row = row + [""] * (COL_PLAN_GP2 + 1 - len(row))
        month_raw = row[COL_PLAN_MONTH]
        name = (row[COL_PLAN_NAME] or "").strip() if COL_PLAN_NAME < len(row) else ""
        code = (row[COL_PLAN_CODE] or "").strip() if COL_PLAN_CODE < len(row) else ""
        func = normalize_func(row[COL_PLAN_FUNC] if COL_PLAN_FUNC < len(row) else "")
        gp2 = to_float(row[COL_PLAN_GP2] if COL_PLAN_GP2 < len(row) else 0)

        if not name or not month_raw:
            continue
        month_str, _, _ = parse_month(month_raw)
        if not month_str:
            continue

        key = (month_str, name, func)
        agg[key] += gp2
        if name not in code_lookup and code:
            code_lookup[name] = code

    return agg, code_lookup


def aggregate_actual():
    """Read Tab 2 and aggregate by (month_str, name, func) → actual GP2 (in millions)."""
    print(f"  Reading {TAB_ACTUAL}...")
    rows = gws_read(f"'{TAB_ACTUAL}'!A2:M1000")
    print(f"  Got {len(rows)} rows")

    agg = defaultdict(float)
    for row in rows:
        if len(row) <= COL_ACT_MONTH:
            row = row + [""] * (COL_ACT_MONTH + 1 - len(row))
        name = (row[COL_ACT_NAME] or "").strip()
        func = normalize_func(row[COL_ACT_FUNC])
        gp2_raw = to_float(row[COL_ACT_GP2])
        month_raw = row[COL_ACT_MONTH]

        if not name or not month_raw:
            continue
        month_str, _, _ = parse_month(month_raw)
        if not month_str:
            continue

        key = (month_str, name, func)
        agg[key] += gp2_raw / 1_000_000.0  # VND -> millions

    return agg


def fuzzy_match(actual_only_keys, planning_only_keys, threshold=0.85):
    """Match each ACTUAL_ONLY key to nearest FORECAST_ONLY key in same (month, func)
    by name similarity. Returns list of (actual_key, planning_key) merge pairs."""
    pairs = []
    used_planning = set()

    # Group planning by (month, func) for fast lookup
    planning_by_mf = defaultdict(list)
    for k in planning_only_keys:
        planning_by_mf[(k[0], k[2])].append(k)

    for ak in actual_only_keys:
        month, aname, func = ak
        candidates = planning_by_mf.get((month, func), [])
        candidates = [c for c in candidates if c not in used_planning]
        if not candidates:
            continue
        norm_a = normalize_name_for_match(aname)
        best_ratio = 0
        best_match = None
        for ck in candidates:
            norm_c = normalize_name_for_match(ck[1])
            ratio = difflib.SequenceMatcher(None, norm_a, norm_c).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = ck
        if best_match and best_ratio >= threshold:
            pairs.append((ak, best_match, best_ratio))
            used_planning.add(best_match)

    return pairs


def compute_timegone(month_str, today=None):
    """Return % of month elapsed (1.0 = full)."""
    if today is None:
        today = datetime.date.today()
    m = re.match(r"T(\d+)/(\d+)", month_str)
    if not m:
        return 1.0
    month = int(m.group(1))
    year = int(m.group(2))
    if (year, month) < (today.year, today.month):
        return 1.0
    if (year, month) > (today.year, today.month):
        return 0.0
    days_in_month = calendar.monthrange(year, month)[1]
    return min(1.0, today.day / days_in_month)


def extract_code(name):
    """Extract project code prefix from 'CODE - rest of name'."""
    if " - " in name:
        return name.split(" - ", 1)[0].strip()
    parts = name.split(" ", 1)
    return parts[0] if parts else ""


def fmt_pct(numerator, denominator):
    if denominator == 0:
        if numerator == 0:
            return "—"
        return "∞"
    return f"{(numerator / denominator * 100):.1f}%"


def render_project(month, code, name, func, forecast, actual, timegone, matching):
    """Render one projectData row as JS object literal."""
    runrate = forecast * timegone
    pct_forecast = fmt_pct(actual, forecast)
    pct_runrate = fmt_pct(actual, runrate) if matching == "MATCHED" else ""
    timegone_str = f"{timegone * 100:.1f}%"
    # Round numbers to 1 decimal, drop trailing 0 if int
    def num(v):
        if v == 0:
            return "0"
        if abs(v - round(v)) < 0.05:
            return f"{v:.1f}"
        return f"{v:.1f}"
    # Escape single quotes in strings
    def esc(s):
        return str(s).replace("\\", "\\\\").replace("'", "\\'")
    return (
        f"{{month:'{esc(month)}',code:'{esc(code)}',name:'{esc(name)}',func:'{esc(func)}',"
        f"forecast:{num(forecast)},actual:{num(actual)},pctForecast:'{pct_forecast}',"
        f"timegone:'{timegone_str}',runrate:{num(runrate)},pctRunrate:'{pct_runrate}',"
        f"matching:'{matching}'}}"
    )


def month_sort_key(month_str):
    m = re.match(r"T(\d+)/(\d+)", month_str)
    if not m:
        return (9999, 99)
    return (int(m.group(2)), int(m.group(1)))


def main():
    apply = "--apply" in sys.argv

    print("Đang đồng bộ Chi tiết Project từ Total Dashboard...")
    planning, code_lookup = aggregate_planning()
    actual = aggregate_actual()

    print(f"\n  Planning entries: {len(planning)}")
    print(f"  Actual entries: {len(actual)}")

    # Find ACTUAL_ONLY and FORECAST_ONLY
    matched_keys = set(planning) & set(actual)
    forecast_only_keys = set(planning) - set(actual)
    actual_only_keys = set(actual) - set(planning)

    print(f"  Exact matched: {len(matched_keys)}")
    print(f"  Forecast only: {len(forecast_only_keys)}")
    print(f"  Actual only: {len(actual_only_keys)}")

    # Fuzzy match the ACTUAL_ONLY entries
    fuzzy_pairs = fuzzy_match(actual_only_keys, forecast_only_keys, threshold=0.85)
    print(f"  Fuzzy matched: {len(fuzzy_pairs)}")

    # Build merged dataset
    rows = []
    fuzzy_actual_used = {p[0] for p in fuzzy_pairs}
    fuzzy_planning_used = {p[1] for p in fuzzy_pairs}

    # 1) MATCHED (exact)
    for key in matched_keys:
        month, name, func = key
        code = code_lookup.get(name) or extract_code(name)
        timegone = compute_timegone(month)
        rows.append((month, code, name, func, planning[key], actual[key], timegone, "MATCHED"))

    # 2) MATCHED (fuzzy) — use planning name as canonical
    for ak, pk, ratio in fuzzy_pairs:
        month, _, func = ak
        pname = pk[1]
        code = code_lookup.get(pname) or extract_code(pname)
        timegone = compute_timegone(month)
        rows.append((month, code, pname, func, planning[pk], actual[ak], timegone, "MATCHED"))

    # 3) FORECAST_ONLY (planning entries not used in fuzzy)
    for key in forecast_only_keys - fuzzy_planning_used:
        month, name, func = key
        code = code_lookup.get(name) or extract_code(name)
        timegone = compute_timegone(month)
        rows.append((month, code, name, func, planning[key], 0.0, timegone, "FORECAST_ONLY"))

    # 4) ACTUAL_ONLY (actual entries not used in fuzzy)
    for key in actual_only_keys - fuzzy_actual_used:
        month, name, func = key
        code = extract_code(name)
        timegone = compute_timegone(month)
        rows.append((month, code, name, func, 0.0, actual[key], timegone, "ACTUAL_ONLY"))

    # Filter out empty rows (forecast=0 AND actual=0) — noise from planning placeholders
    before = len(rows)
    rows = [r for r in rows if r[4] != 0 or r[5] != 0]
    print(f"  Filtered empty rows: {before} → {len(rows)}")

    # Sort by month asc, then code asc
    rows.sort(key=lambda r: (month_sort_key(r[0]), r[1]))

    print(f"  Total project rows: {len(rows)}")

    # Render JS
    js_lines = ["const projectData = ["]
    for r in rows:
        js_lines.append(render_project(*r) + ",")
    js_lines.append("];")
    new_block = "\n".join(js_lines)

    # Replace in index.html
    html = INDEX.read_text(encoding="utf-8")
    pattern = re.compile(r"const projectData = \[[\s\S]*?\n\];", re.MULTILINE)
    if not pattern.search(html):
        print("ERROR: const projectData block not found in index.html")
        sys.exit(1)
    new_html = pattern.sub(new_block, html, count=1)

    if new_html == html:
        print("\nKhông có thay đổi.")
        return

    if apply:
        INDEX.write_text(new_html, encoding="utf-8")
        print(f"\n✅ Đã update {INDEX}")
        # Quick stats
        old_lines = html.count("\n")
        new_lines = new_html.count("\n")
        print(f"  Lines: {old_lines} → {new_lines}")
    else:
        # Print sample of new rows
        print("\n--- Sample 10 rows ---")
        for line in js_lines[1:11]:
            print(line)
        print(f"...({len(rows) - 10} more rows)")
        print("\n(Chạy lại với --apply để ghi vào index.html)")


if __name__ == "__main__":
    main()
