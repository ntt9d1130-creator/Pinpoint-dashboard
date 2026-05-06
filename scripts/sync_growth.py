#!/usr/bin/env python3
"""
Sync section "Tăng trưởng" của Pinpoint dashboard từ Google Sheet "Total Dashboard".

Source: tab "4. Summary Sales Performance"
Target: index.html arrays + HTML funnel/KPI

Usage:
    python3 scripts/sync_growth.py            # dry-run, show diff
    python3 scripts/sync_growth.py --apply    # write to index.html
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# Config
SHEET_ID = "1hDlwoQ8KgMaWsOLrooBQmlL4KQgY3c70gU0x3bJw4hI"
TAB = "4. Summary Sales Performance"
GWS = "/usr/local/bin/gws"
REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"
DATA_JS = REPO / "data" / "data.js"


def read_data_js():
    """Read and parse data/data.js → dict."""
    if not DATA_JS.exists():
        return {}
    text = DATA_JS.read_text(encoding="utf-8").strip()
    # Format: window.DASHBOARD_DATA = {...};
    m = re.match(r"^window\.DASHBOARD_DATA\s*=\s*(\{[\s\S]*\});?\s*$", text)
    if not m:
        return {}
    return json.loads(m.group(1))


def write_data_js(data):
    """Write dict to data/data.js."""
    DATA_JS.parent.mkdir(parents=True, exist_ok=True)
    text = "window.DASHBOARD_DATA = " + json.dumps(data, ensure_ascii=False) + ";"
    DATA_JS.write_text(text, encoding="utf-8")

# Stage order matches sheet column order (col C..J for Source/Vertical, col C..I for Quarter)
STAGES = ["lead", "ql", "brief", "qb", "qs", "vc", "nvc", "contract"]


def gws_read(rng):
    """Read a range using gws CLI, return values list."""
    cmd = [
        GWS, "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps({"spreadsheetId": SHEET_ID, "range": f"'{TAB}'!{rng}"}),
        "--format", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    text = out.stdout
    if text.startswith("Using keyring"):
        text = text.split("\n", 1)[1]
    data = json.loads(text)
    return data.get("values", [])


def to_int(s):
    if s is None or s == "":
        return 0
    try:
        return int(float(str(s).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def fmt_num(n):
    """Format integer with thousands separator."""
    return f"{n:,}"


def parse_quarter_summary(values):
    """Rows 1-12: quarter target/actual/CR/achievement/runrate.
    Returns dict keyed by metric name -> dict of stage->value."""
    result = {}
    for row in values:
        if len(row) < 3:
            continue
        label = (row[1] or "").strip()
        if not label:
            continue
        # Quarter has 7 stages (Lead..Contract). Cols C..I.
        stages_q = ["lead", "ql", "brief", "qb", "qs", "vc", "contract"]
        vals = {}
        for i, stage in enumerate(stages_q):
            cell = row[2 + i] if 2 + i < len(row) else ""
            vals[stage] = cell
        result[label] = vals
    return result


def parse_weekly(values, expect_label):
    """Parse a 'Weekly' block. Returns list of dicts with date string + funnel.
    Block headers: 'Weekly Target' or 'Actual Target'.
    Funnel header columns: Lead, QL, Brief, QB, Quotation sent, Verbal confirm, Contract."""
    weeks = []
    in_block = False
    for row in values:
        if len(row) < 2:
            if in_block:
                # blank row ends the data block
                break
            continue
        label = (row[1] or "").strip()
        if label == expect_label:
            in_block = True
            continue
        if not in_block:
            continue
        # We're inside the block — first row is header, rest is data
        # Skip header (already past)
        # Date pattern: m/d/yyyy
        if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", label):
            d = label
            # Convert "4/1/2026" -> "4/1"
            short = "/".join(d.split("/")[:2])
            week = {"w": short}
            # Cols C..I: Lead, QL, Brief, QB, QS, VC, Contract (7 stages)
            stages_w = ["lead", "ql", "brief", "qb", "qs", "vc", "contract"]
            for i, stage in enumerate(stages_w):
                cell = row[2 + i] if 2 + i < len(row) else ""
                week[stage] = to_int(cell)
            weeks.append(week)
        elif label and not re.match(r"^\d", label):
            # Non-date label encountered — block ended
            break
    return weeks


def parse_breakdown(values, header_label):
    """Parse Sources or Vertical breakdown. Returns list of dicts.
    The 'header_label' row IS the column header row (label in col B, col headers C..J).
    Data starts on next non-empty row. Stop on 'Total' row.
    Cols C..J: Lead, QL, Brief, QB, QS, VC, NVC, Contract (8 stages)."""
    items = []
    in_block = False
    for row in values:
        if len(row) < 2:
            continue
        label = (row[1] or "").strip()
        if not in_block:
            if label == header_label:
                in_block = True
            continue
        # In block — process data rows
        if label == "Total":
            break
        if not label:
            continue  # skip blank/spacer rows
        item = {"name": label}
        for i, stage in enumerate(STAGES):
            cell = row[2 + i] if 2 + i < len(row) else ""
            item[stage] = to_int(cell)
        items.append(item)
    return items


def js_format_num(v):
    return str(v)


def build_weekly_array(weeks):
    """List of dicts. Drop weeks with all zeros (no actual yet)."""
    out = []
    for w in weeks:
        if all(w.get(s, 0) == 0 for s in ["lead", "ql", "brief", "qb", "qs", "vc", "contract"]):
            continue
        out.append({
            "w": w["w"], "lead": w["lead"], "ql": w["ql"], "brief": w["brief"],
            "qb": w["qb"], "qs": w["qs"], "vc": w["vc"], "contract": w["contract"],
        })
    return out


def build_vertical_array(verticals):
    return [
        {
            "v": v["name"], "lead": v["lead"], "ql": v["ql"], "brief": v["brief"],
            "qb": v["qb"], "qs": v["qs"], "vc": v["vc"], "nvc": v["nvc"],
            "contract": v["contract"], "exec": 0,
        }
        for v in sorted(verticals, key=lambda x: x["name"])
    ]


def build_source_array(sources):
    return [
        {
            "s": s["name"], "lead": s["lead"], "ql": s["ql"], "brief": s["brief"],
            "qb": s["qb"], "qs": s["qs"], "vc": s["vc"], "nvc": s["nvc"],
            "contract": s["contract"], "exec": 0,
        }
        for s in sorted(sources, key=lambda x: -x["lead"])
    ]


def compute_grouped(sources):
    """Sum sources by prefix group (Scrapping/Marketing/Direct/Referral)."""
    groups = {
        "Scrapping": {"lead": 0, "ql": 0, "brief": 0, "contract": 0, "color": "#3b82f6"},
        "Marketing": {"lead": 0, "ql": 0, "brief": 0, "contract": 0, "color": "#eab308"},
        "Direct":    {"lead": 0, "ql": 0, "brief": 0, "contract": 0, "color": "#22c55e"},
        "Referral":  {"lead": 0, "ql": 0, "brief": 0, "contract": 0, "color": "#a855f7"},
    }
    for s in sources:
        prefix = s["name"].split("_", 1)[0] if "_" in s["name"] else "Other"
        if prefix in groups:
            for stage in ("lead", "ql", "brief", "contract"):
                groups[prefix][stage] += s.get(stage, 0)
    return [
        {"g": name, "lead": vals["lead"], "ql": vals["ql"],
         "brief": vals["brief"], "contract": vals["contract"], "color": vals["color"]}
        for name, vals in groups.items()
    ]


def replace_funnel(html, q):
    """Update the static HTML funnel block in section #growth.
    Uses unique markers from current HTML structure.
    q: dict from parse_quarter_summary."""
    actual = q.get("Actual (Quarter)", {})
    target = q.get("Target (Quarter)", {})
    crq = q.get("CR actual realtime", {})

    # Compute % achievement = actual/target * 100
    def pct(stage):
        a = to_int(actual.get(stage, 0))
        t = to_int(target.get(stage, 0))
        return f"{(a/t*100):.0f}%" if t else "—"

    # Pattern: each funnel-step contains label + value + sub. Replace by stage label.
    # Stages in funnel: Lead, QL, Brief, QB, "Gửi báo giá", "Xác nhận", "Hợp đồng"
    funnel_map = [
        ("Lead",        "lead",     "blue",   None),
        ("QL",          "ql",       "cyan",   "ql"),
        ("Brief",       "brief",    "purple", "brief"),
        ("QB",          "qb",       "orange", "qb"),
        ("Gửi báo giá", "qs",       "yellow", "qs"),
        ("Xác nhận",    "vc",       "pink",   "vc"),
        ("Hợp đồng",    "contract", "green",  "contract"),
    ]

    new_funnel_steps = []
    prev_actual = None
    for label, stage, color, cr_key in funnel_map:
        a = to_int(actual.get(stage, 0))
        t = to_int(target.get(stage, 0))
        pct_str = f"{(a/t*100):.0f}%" if t else "—"
        # CR from sheet (realtime)
        cr_str = ""
        if cr_key and cr_key in crq:
            cr_val = crq.get(cr_key, "").replace("%", "").strip()
            try:
                cr_str = f"CR: {float(cr_val):.1f}% | "
            except ValueError:
                cr_str = ""
        sub = f"{cr_str}Target: {t} | {pct_str}" if not cr_str else f"{cr_str}Target {t}"
        # Sub color based on achievement
        a_pct = (a/t*100) if t else 0
        sub_color = "var(--green)" if a_pct >= 25 else "var(--yellow)" if a_pct >= 15 else "var(--red)"
        # Special wrap for Hợp đồng (last step has border)
        extra_attr = ' style="border:2px solid var(--green);"' if stage == "contract" else ""
        new_funnel_steps.append(
            f'<div class="funnel-step"{extra_attr}>'
            f'<div class="funnel-lbl">{label}</div>'
            f'<div class="funnel-val" style="color:var(--{color})">{a}</div>'
            f'<div class="funnel-sub" style="color:{sub_color}">{sub}</div>'
            f'</div>'
        )

    new_funnel_html = '\n        '.join([
        new_funnel_steps[0],
        '<div class="funnel-arr">→</div>',
        new_funnel_steps[1],
        '<div class="funnel-arr">→</div>',
        new_funnel_steps[2],
        '<div class="funnel-arr">→</div>',
        new_funnel_steps[3],
        '<div class="funnel-arr">→</div>',
        new_funnel_steps[4],
        '<div class="funnel-arr">→</div>',
        new_funnel_steps[5],
        '<div class="funnel-arr">→</div>',
        new_funnel_steps[6],
    ])

    # Replace the funnel block — anchored by "<!-- Funnel -->" comment + class="funnel"
    pattern = re.compile(
        r'(<!-- Funnel -->\s*<div class="funnel">\s*)([\s\S]*?)(\s*</div>\s*<div class="kpi-row">)',
        re.MULTILINE
    )
    if not pattern.search(html):
        raise RuntimeError("Funnel block not found in HTML")
    return pattern.sub(rf"\1{new_funnel_html}\3", html, count=1)


def replace_kpi_growth(html, q):
    """Update 4 KPI cards in section #growth (Lead/Contract/VC/QB Achievement & Runrate)."""
    ach = q.get("Achievement EOQ4", {})
    rr = q.get("Run-rate EOQ4", {})

    def card(label, stage, color_class):
        a = ach.get(stage, "0%")
        r = rr.get(stage, "0%")
        # Determine color & sub class
        try:
            a_num = float(str(a).replace("%", "").strip() or 0)
        except ValueError:
            a_num = 0
        try:
            r_num = float(str(r).replace("%", "").strip() or 0)
        except ValueError:
            r_num = 0
        accent = "accent-green" if r_num >= 100 else ("accent-yellow" if r_num >= 80 else "accent-red")
        val_color = "var(--green)" if r_num >= 100 else ("var(--yellow)" if r_num >= 80 else "var(--red)")
        sub_class = "good" if r_num >= 100 else ("warn" if r_num >= 80 else "bad")
        return (
            f'<div class="kpi {accent}">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-val" style="color:{val_color}">{a}</div>'
            f'<div class="kpi-sub {sub_class}">Runrate: {r}</div>'
            f'</div>'
        )

    new_kpi_html = (
        card("Lead đạt EOQ", "lead", "")
        + card("Hợp đồng đạt EOQ", "contract", "")
        + card("Xác nhận đạt EOQ", "vc", "")
        + card("QB đạt EOQ", "qb", "")
    )

    # Anchor: match the 4 EOQ cards in growth section by finding the FIRST occurrence
    # of '<div class="kpi accent' that contains 'Lead đạt EOQ' and consume all 4 cards
    # ending with the '</div>' that closes the kpi-row.
    # Strategy: find the unique "Lead đạt EOQ" string and walk back to its `<div class="kpi`,
    # then forward through 3 more KPI cards.
    idx = html.find("Lead đạt EOQ")
    if idx == -1:
        raise RuntimeError("'Lead đạt EOQ' marker not found")
    # Walk back to nearest '<div class="kpi '
    start = html.rfind('<div class="kpi ', 0, idx)
    if start == -1:
        raise RuntimeError("Cannot find KPI card start before 'Lead đạt EOQ'")
    # Walk forward to find the </div> that closes the 4th KPI card.
    # Each KPI card is exactly: <div class="kpi ..."> ... </div>
    # We need to consume 4 KPI cards — match by counting balanced div blocks.
    # Simpler: anchor on QB đạt EOQ (last card label) and then close with </div>
    qb_idx = html.find("QB đạt EOQ", start)
    if qb_idx == -1:
        raise RuntimeError("'QB đạt EOQ' marker not found after Lead đạt EOQ")
    # End of QB card is the next </div></div> sequence (kpi-sub closes, then kpi closes)
    # Search forward for '</div></div>' that ends the 4th card.
    end_search = html.find("</div></div>", qb_idx)
    if end_search == -1:
        raise RuntimeError("End of KPI growth row not found")
    end = end_search + len("</div></div>")
    return html[:start] + new_kpi_html + html[end:]


def main():
    apply = "--apply" in sys.argv

    print("Đang đọc dữ liệu từ Google Sheet...")
    quarter_rows = gws_read("A1:I12")
    weekly_target_rows = gws_read("A14:I28")
    weekly_actual_rows = gws_read("A28:I47")
    sources_rows = gws_read("A49:J72")
    verticals_rows = gws_read("A73:J90")

    quarter = parse_quarter_summary(quarter_rows)
    weekly = parse_weekly(weekly_actual_rows, "Actual Target")
    sources = parse_breakdown(sources_rows, "Sources")
    verticals = parse_breakdown(verticals_rows, "Vertical")

    print(f"\n  Quarter Actual: Lead={quarter.get('Actual (Quarter)',{}).get('lead')}, "
          f"Contract={quarter.get('Actual (Quarter)',{}).get('contract')}")
    print(f"  Weekly rows: {len(weekly)}")
    print(f"  Sources: {len(sources)}")
    print(f"  Verticals: {len(verticals)}")

    # Build new arrays as dicts
    new_weekly = build_weekly_array(weekly)
    new_vertical = build_vertical_array(verticals)
    new_source = build_source_array(sources)
    new_grouped = compute_grouped(sources)

    # Read existing data.js, update arrays
    data = read_data_js()
    data["weeklyData"] = new_weekly
    data["verticalData"] = new_vertical
    data["sourceData"] = new_source
    data["sourceGrouped"] = new_grouped

    # Patch HTML for funnel + KPI cards (still HTML, not JSON)
    html = INDEX.read_text(encoding="utf-8")
    original_html = html
    html = replace_funnel(html, quarter)
    html = replace_kpi_growth(html, quarter)

    html_changed = html != original_html
    data_changed = data != read_data_js()

    if not html_changed and not data_changed:
        print("\nKhông có thay đổi.")
        return

    if apply:
        if html_changed:
            INDEX.write_text(html, encoding="utf-8")
            print(f"  ✅ Updated {INDEX.name}")
        if data_changed:
            write_data_js(data)
            print(f"  ✅ Updated {DATA_JS.relative_to(REPO)}")
    else:
        print("\n--- Preview ---")
        print(f"  weekly: {len(new_weekly)} rows")
        print(f"  vertical: {len(new_vertical)} rows")
        print(f"  source: {len(new_source)} rows")
        print(f"  sourceGrouped: {len(new_grouped)} rows")
        print(f"  HTML changed: {html_changed}, data.js changed: {data_changed}")
        print("\n(Chạy lại với --apply)")


if __name__ == "__main__":
    main()
