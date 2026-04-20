# HTML Dashboard Structure

**File**: `/Users/tungnguyen/Pinpoint-dashboard/pinpoint-monitoring-dashboard.html`
**Total**: ~2643 lines, self-contained HTML với inline CSS/JS + Chart.js CDN

---

## Tổng quan 8 Sections

| # | ID | Tên | Line bắt đầu | Mô tả |
|---|-----|-----|---------------|-------|
| 1 | `pod` | POD Performance | ~363 | GP2, DPPC, Efficiency — **section cần update thường xuyên** |
| 2 | `growth` | Growth Performance | ~547 | Funnel metrics, weekly data |
| 3 | `sales` | Sales Activities | ~745 | Sales PIC performance |
| 4 | `account` | Account Activities | ~813 | Account health, churn risk |
| 5 | `pic` | Account PIC | ~885 | PIC assignment table |
| 6 | `product` | Product Roadmap | ~920 | Roadmap timeline |
| 7 | `okr` | OKR Q1 | ~1025 | OKR tracking |
| 8 | `projectDetail` | Project Detail | ~1147 | Project-level data — **section cần update thường xuyên** |

---

## Section 1: POD Performance (chi tiết)

### Scorecards H1 (~line 367-392)
Cấu trúc KPI cards — mỗi card có 3 phần:
```html
<div class="kpi-card">
    <div class="kpi-label">GP2 Actual H1</div>
    <div class="kpi-value" style="color:var(--accent-yellow)">3,675.5M</div>
    <div class="kpi-sub warning">52.1% vs Forecast</div>
</div>
```

**5 KPI cards H1** (theo thứ tự):
1. GP2 Actual H1 — value + "% vs Forecast"
2. GP2 Forecast H1 — value + "% vs Budget"
3. GP2 Budget H1 — value + "Achievement: %"
4. DPPC H1 — value + "% of GP2 Forecast"
5. % DPPC / GP2 Budget — value + status text

### Scorecards Q2 (~line 395-420)
Cấu trúc tương tự H1, trong `<div class="kpi-row" style="margin-top:8px;">`:
1. GP2 Actual Q2
2. GP2 Forecast Q2
3. GP2 Budget Q2
4. DPPC Q2
5. Q2 Timegone

### Charts (~line 1244-1325)
4 charts trong section POD:

**Chart 1: GP2 Monthly** (line ~1244, id="chartGP2Monthly")
```javascript
new Chart(document.getElementById('chartGP2Monthly'), {
    type: 'bar',
    data: {
        labels: ['T1','T2','T3','T4','T5','T6'],
        datasets: [
            { label: 'Budget', data: [1988, 1097, 2031, 2295, 2295, 2295], ... },
            { label: 'Forecast', data: [1263.6, 974.3, 1271.5, 1012.8, 1199.0, 1328.7], ... },
            { label: 'Actual', data: [1122.3, 880.4, 1269.6, 403.2, 0.0, 0.0], ... }
        ]
    }
});
```

**Chart 2: Efficiency** (line ~1262, id="chartEfficiency")
- Labels: tháng có actual (VD: ['T1','T2','T3','T4'])
- Dataset 1: % Act/Forecast: [88.8, 90.4, 99.9, 39.8]
- Dataset 2: % Actual/Runrate: [88.8, 90.4, 99.9, 91.9]
- Dataset 3: Target 100% line

**Chart 3: Function Doughnut** (line ~1282, id="chartFunctionT3")
- Labels: function names ['MEDIA','CREATIVE','LIVESTREAM',...]
- Data: actual GP2.5 per function cho tháng actual gần nhất

**Chart 4: Function Performance** (line ~1299, id="chartFuncPerf")
- Horizontal bar chart
- Labels: function names
- 2 datasets: Forecast + Actual per function

### Monthly Detail Table (~line 440-510)
Bảng `<table>` với thead 10 cột:
```
Tháng | GP2 Budget | GP2 Forecast | GP2 Actual | Timegone | %F/B | %A/B | %A/Runrate | DPPC | %DPPC/GP2
```

Tbody chứa rows T1→T6 + H1 summary row.

**Cách update**: Replace toàn bộ nội dung `<tbody>` trong bảng "Chi tiết theo tháng".

Badge color logic:
- >= 90%: `badge-green`
- >= 70%: `badge-yellow`  
- < 70%: `badge-red`

### Function Breakdown Table (~line 508-545)
Bảng riêng biệt "Chi tiết Function — T1 đến T4/2026":
```
Tháng | Function | Forecast GP | Actual GP2.5 | % Actual/Forecast | Runrate GP | % Actual/Runrate
```

Grouped by month, mỗi nhóm tháng mới có `border-top: 2px solid`.
Row đầu mỗi nhóm có `<strong>` cho tháng và function đầu tiên.

---

## Section 8: Project Detail (chi tiết)

### Filter UI (~line 1147-1220)
Có dropdown filters cho: Month, Function, Matching status, search box.

### projectData Array (~line 1731-2488)
JavaScript array khoảng 700-800 entries, mỗi entry format:
```javascript
{
    month: 'T4/2026',
    code: 'SEEFQMP001',
    name: 'CIS - Media',
    func: 'MEDIA',
    forecast: 100.0,
    actual: 34.1,
    pctForecast: '34.1%',
    timegone: '43.3%',
    runrate: 78.7,
    pctRunrate: '78.7%',
    matching: 'MATCHED'
}
```

**Matching values**: `MATCHED`, `FORECAST_ONLY`, `ACTUAL_ONLY`

**Cách update**: Tìm `const projectData = [` và replace cho đến `];` đóng.

### Project Detail Table (dynamic rendering ~line 2489+)
Table body được render bằng JS từ `projectData` array — không cần edit HTML table trực tiếp.
Chỉ cần update `projectData` array là table tự render.

---

## Regex Patterns cho Update

### Scorecard values
```python
# GP2 Actual H1
re.sub(r'(GP2 Actual H1</div>\s*<div class="kpi-value"[^>]*>)[\d,.]+M', 
       r'\g<1>{new_value}M', html)

# GP2 Forecast H1
re.sub(r'(GP2 Forecast H1</div>\s*<div class="kpi-value"[^>]*>)[\d,.]+M',
       r'\g<1>{new_value}M', html)

# % vs Forecast / % vs Budget
re.sub(r'(GP2 Actual H1.*?<div class="kpi-sub[^"]*">)[\d.]+(%\s*vs\s*Forecast)',
       r'\g<1>{pct}\2', html, flags=re.DOTALL)
```

### Chart data arrays
```python
# Budget data
re.sub(r"(label:\s*'Budget',\s*data:\s*)\[[^\]]+\]",
       r"\1[{new_budget_array}]", html)

# Forecast data
re.sub(r"(label:\s*'Forecast',\s*data:\s*)\[[^\]]+\]",
       r"\1[{new_forecast_array}]", html)

# Actual data  
re.sub(r"(label:\s*'Actual',\s*data:\s*)\[[^\]]+\]",
       r"\1[{new_actual_array}]", html)
```

### projectData array
```python
# Tìm và replace toàn bộ projectData
re.sub(r'const projectData = \[.*?\];',
       f'const projectData = [{new_entries}];',
       html, flags=re.DOTALL)
```

---

## Deploy Process

```bash
cd /Users/tungnguyen/Pinpoint-dashboard
cp pinpoint-monitoring-dashboard.html index.html
git add pinpoint-monitoring-dashboard.html index.html
git commit -m "Update dashboard data $(date +%Y-%m-%d)"
git push origin main
```

URL sau deploy: https://ntt9d1130-creator.github.io/Pinpoint-dashboard/
