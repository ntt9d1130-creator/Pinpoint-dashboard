#!/usr/bin/env python3
"""
compute_dashboard.py — Reference script tính toán metrics cho Pinpoint Dashboard.

Script này KHÔNG chạy trực tiếp (vì cần gws CLI trên Mac của user).
Dùng làm tham khảo logic tính toán khi update dashboard.

Workflow:
1. Đọc 3 JSON files từ gws output (đã save ở /tmp/)
2. Tính toán tất cả metrics
3. Output JSON chứa toàn bộ data cần update vào HTML
"""

import json
import re
from collections import defaultdict
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
SPREADSHEET_ID = "1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8"
MONTHS = ['T1/2026', 'T2/2026', 'T3/2026', 'T4/2026', 'T5/2026', 'T6/2026']
MONTH_LABELS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6']

# ============================================================
# HELPER: Parse gws JSON (thiếu { mở đầu)
# ============================================================
def parse_gws_json(filepath):
    """Parse JSON output từ gws CLI — handle missing opening brace."""
    raw = open(filepath).read().strip()
    if not raw.startswith('{'):
        raw = '{' + raw
    data = json.loads(raw)
    return data.get('values', [])


def safe_float(val):
    """Convert value to float, handle empty/None."""
    if val is None or val == '' or val == '—':
        return 0.0
    try:
        return float(str(val).replace(',', ''))
    except (ValueError, TypeError):
        return 0.0


def norm_func(name):
    """Normalize function name to UPPER."""
    if not name:
        return 'UNKNOWN'
    return str(name).strip().upper()


# ============================================================
# STEP 1: Read Tab 1 — POD Performance (Budget + DPPC)
# ============================================================
def read_tab1(filepath='/tmp/tab1.json'):
    """Đọc Budget GP2 và DPPC từ Tab 1."""
    rows = parse_gws_json(filepath)
    budget = {}
    dppc = {}
    
    for row in rows:
        if not row:
            continue
        label = str(row[0]).strip().lower()
        
        if 'budget' in label and 'gp2' in label:
            for i, m in enumerate(MONTHS):
                budget[m] = safe_float(row[i + 1]) if i + 1 < len(row) else 0
        
        if label.startswith('dppc') or label == 'dppc':
            for i, m in enumerate(MONTHS):
                dppc[m] = safe_float(row[i + 1]) if i + 1 < len(row) else 0
    
    return budget, dppc


# ============================================================
# STEP 2: Read Tab 2 — Project Planning (Forecast)
# ============================================================
def read_tab2(filepath='/tmp/tab2.json'):
    """Đọc forecast GP từ Tab 2, cột AF (index 31)."""
    rows = parse_gws_json(filepath)
    header = rows[0] if rows else []
    
    forecast_by_month = defaultdict(float)
    forecast_by_func = defaultdict(float)
    projects_forecast = []  # list of dicts per project
    
    for row in rows[1:]:
        if len(row) < 32:
            continue
        month = str(row[0]).strip()
        if not re.match(r'T\d/2026', month):
            continue
        
        code = str(row[1]).strip() if len(row) > 1 else ''
        name = str(row[2]).strip() if len(row) > 2 else ''
        func = norm_func(row[3]) if len(row) > 3 else 'UNKNOWN'
        final_gp = safe_float(row[31])  # col AF = index 31
        
        forecast_by_month[month] += final_gp
        forecast_by_func[(month, func)] += final_gp
        
        projects_forecast.append({
            'month': month,
            'code': code,
            'name': name,
            'func': func,
            'forecast': round(final_gp, 1)
        })
    
    return forecast_by_month, forecast_by_func, projects_forecast


# ============================================================
# STEP 3: Read Tab 3 — Project Actual (GP2.5)
# ============================================================
def read_tab3(filepath='/tmp/tab3.json'):
    """Đọc actual GP2.5 từ Tab 3, cột J (index 9)."""
    rows = parse_gws_json(filepath)
    
    actual_by_month = defaultdict(float)
    actual_by_func = defaultdict(float)
    projects_actual = []
    
    for row in rows[1:]:
        if len(row) < 10:
            continue
        month = str(row[0]).strip()
        if not re.match(r'T\d/2026', month):
            continue
        
        code = str(row[1]).strip() if len(row) > 1 else ''
        name = str(row[2]).strip() if len(row) > 2 else ''
        func = norm_func(row[3]) if len(row) > 3 else 'UNKNOWN'
        gp25 = safe_float(row[9])  # col J = index 9 = GP2.5
        
        actual_by_month[month] += gp25
        actual_by_func[(month, func)] += gp25
        
        projects_actual.append({
            'month': month,
            'code': code,
            'name': name,
            'func': func,
            'actual': round(gp25, 1)
        })
    
    return actual_by_month, actual_by_func, projects_actual


# ============================================================
# STEP 4: Compute all metrics
# ============================================================
def compute_metrics(budget, dppc, forecast_by_month, actual_by_month,
                    forecast_by_func, actual_by_func,
                    projects_forecast, projects_actual):
    """Tính toán tất cả metrics cho dashboard."""
    
    result = {
        'monthly': [],
        'scorecards': {},
        'charts': {},
        'function_breakdown': [],
        'project_data': []
    }
    
    # --- Monthly data ---
    for m in MONTHS:
        b = budget.get(m, 0)
        f = forecast_by_month.get(m, 0)
        a = actual_by_month.get(m, 0)
        d = dppc.get(m, 0)
        
        pct_fb = round(f / b * 100, 1) if b else 0
        pct_ab = round(a / f * 100, 1) if f else 0
        timegone = 100 if a > 0 else 0  # simplified; actual tháng hiện tại tính theo ngày
        runrate = round(a / (timegone / 100) if timegone > 0 else 0, 1)
        pct_runrate = round(a / runrate * 100, 1) if runrate > 0 else 0
        
        result['monthly'].append({
            'month': m,
            'budget': round(b, 1),
            'forecast': round(f, 1),
            'actual': round(a, 1),
            'dppc': round(d, 1),
            'pct_forecast_budget': pct_fb,
            'pct_actual_forecast': pct_ab,
            'timegone': timegone,
        })
    
    # --- H1 Scorecards ---
    h1_budget = sum(budget.get(m, 0) for m in MONTHS)
    h1_forecast = sum(forecast_by_month.get(m, 0) for m in MONTHS)
    h1_actual = sum(actual_by_month.get(m, 0) for m in MONTHS)
    h1_dppc = sum(dppc.get(m, 0) for m in MONTHS)
    
    result['scorecards']['h1'] = {
        'budget': round(h1_budget, 1),
        'forecast': round(h1_forecast, 1),
        'actual': round(h1_actual, 1),
        'dppc': round(h1_dppc, 1),
        'pct_actual_forecast': round(h1_actual / h1_forecast * 100, 1) if h1_forecast else 0,
        'pct_forecast_budget': round(h1_forecast / h1_budget * 100, 1) if h1_budget else 0,
        'achievement': round(h1_actual / h1_budget * 100, 1) if h1_budget else 0,
    }
    
    # --- Q2 Scorecards ---
    q2_months = ['T4/2026', 'T5/2026', 'T6/2026']
    q2_budget = sum(budget.get(m, 0) for m in q2_months)
    q2_forecast = sum(forecast_by_month.get(m, 0) for m in q2_months)
    q2_actual = sum(actual_by_month.get(m, 0) for m in q2_months)
    q2_dppc = sum(dppc.get(m, 0) for m in q2_months)
    
    result['scorecards']['q2'] = {
        'budget': round(q2_budget, 1),
        'forecast': round(q2_forecast, 1),
        'actual': round(q2_actual, 1),
        'dppc': round(q2_dppc, 1),
        'pct_actual_forecast': round(q2_actual / q2_forecast * 100, 1) if q2_forecast else 0,
        'pct_forecast_budget': round(q2_forecast / q2_budget * 100, 1) if q2_budget else 0,
    }
    
    # --- Chart data arrays ---
    result['charts'] = {
        'budget': [round(budget.get(m, 0), 1) for m in MONTHS],
        'forecast': [round(forecast_by_month.get(m, 0), 1) for m in MONTHS],
        'actual': [round(actual_by_month.get(m, 0), 1) for m in MONTHS],
        'efficiency_labels': [],
        'efficiency_act_fcast': [],
        'efficiency_act_runrate': [],
    }
    
    for m in MONTHS:
        a = actual_by_month.get(m, 0)
        f = forecast_by_month.get(m, 0)
        if a > 0 and f > 0:
            label = m.split('/')[0]  # "T1"
            pct = round(a / f * 100, 1)
            result['charts']['efficiency_labels'].append(label)
            result['charts']['efficiency_act_fcast'].append(pct)
            # Runrate simplified = actual / timegone * 100
            result['charts']['efficiency_act_runrate'].append(pct)  # placeholder
    
    # --- Function breakdown ---
    all_funcs = set()
    for key in list(forecast_by_func.keys()) + list(actual_by_func.keys()):
        all_funcs.add(key)
    
    func_months = sorted(set(k[0] for k in all_funcs), key=lambda x: int(x[1]))
    func_names = sorted(set(k[1] for k in all_funcs))
    
    for m in func_months:
        for fn in func_names:
            f_val = forecast_by_func.get((m, fn), 0)
            a_val = actual_by_func.get((m, fn), 0)
            if f_val == 0 and a_val == 0:
                continue
            pct = round(a_val / f_val * 100, 1) if f_val > 0 else 0
            result['function_breakdown'].append({
                'month': m.split('/')[0],
                'func': fn,
                'forecast': round(f_val, 1),
                'actual': round(a_val, 1),
                'pct': pct,
            })
    
    # --- Project Detail (merge forecast + actual) ---
    # Index by (month, code)
    fcast_map = {}
    for p in projects_forecast:
        key = (p['month'], p['code'])
        fcast_map[key] = p
    
    actual_map = {}
    for p in projects_actual:
        key = (p['month'], p['code'])
        actual_map[key] = p
    
    all_keys = set(list(fcast_map.keys()) + list(actual_map.keys()))
    
    for key in sorted(all_keys):
        month, code = key
        fp = fcast_map.get(key, {})
        ap = actual_map.get(key, {})
        
        forecast_val = fp.get('forecast', 0)
        actual_val = ap.get('actual', 0)
        name = fp.get('name', '') or ap.get('name', '')
        func = fp.get('func', '') or ap.get('func', 'UNKNOWN')
        
        # Matching status
        if forecast_val > 0 and actual_val > 0:
            matching = 'MATCHED'
        elif forecast_val > 0:
            matching = 'FORECAST_ONLY'
        else:
            matching = 'ACTUAL_ONLY'
        
        # Tính pctForecast
        if forecast_val > 0:
            pct_f = round(actual_val / forecast_val * 100, 1)
            pct_f_str = f'{pct_f}%'
        elif actual_val != 0:
            pct_f_str = '∞'
        else:
            pct_f_str = '—'
        
        # Timegone: 100% cho tháng đã qua, tính theo ngày cho tháng hiện tại
        month_num = int(month[1])  # T4 → 4
        now = datetime.now()
        if now.year == 2026 and now.month == month_num:
            import calendar
            days_in_month = calendar.monthrange(2026, month_num)[1]
            tg = round(now.day / days_in_month * 100, 1)
        elif now.year > 2026 or (now.year == 2026 and now.month > month_num):
            tg = 100.0
        else:
            tg = 0.0
        
        # Runrate
        runrate_val = round(actual_val / (tg / 100), 1) if tg > 0 else 0
        pct_rr = round(actual_val / runrate_val * 100, 1) if runrate_val > 0 else 0
        
        result['project_data'].append({
            'month': month,
            'code': code,
            'name': name,
            'func': func,
            'forecast': forecast_val,
            'actual': actual_val,
            'pctForecast': pct_f_str,
            'timegone': f'{tg}%',
            'runrate': runrate_val,
            'pctRunrate': f'{pct_rr}%' if pct_rr > 0 else '',
            'matching': matching,
        })
    
    return result


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    # Read data (assumes gws output already saved to /tmp/)
    budget, dppc = read_tab1('/tmp/tab1.json')
    forecast_by_month, forecast_by_func, projects_forecast = read_tab2('/tmp/tab2.json')
    actual_by_month, actual_by_func, projects_actual = read_tab3('/tmp/tab3.json')
    
    # Compute
    result = compute_metrics(
        budget, dppc,
        forecast_by_month, actual_by_month,
        forecast_by_func, actual_by_func,
        projects_forecast, projects_actual
    )
    
    # Output
    output_path = '/tmp/dashboard_data.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"Dashboard data written to {output_path}")
    print(f"  Monthly records: {len(result['monthly'])}")
    print(f"  Function breakdown: {len(result['function_breakdown'])}")
    print(f"  Project entries: {len(result['project_data'])}")
    print(f"  H1 Actual: {result['scorecards']['h1']['actual']}M")
    print(f"  Q2 Actual: {result['scorecards']['q2']['actual']}M")
