---
name: performance-dashboard
description: >
  Build và update Pinpoint Performance Monitoring Dashboard — đọc data từ Google Sheets,
  tính toán metrics (GP2, DPPC, Efficiency, Function breakdown), render HTML dashboard
  với Chart.js, deploy lên GitHub Pages. Trigger khi user nói "update dashboard",
  "refresh dashboard", "cập nhật dashboard", "build dashboard pinpoint",
  "update pod performance", "update project detail", hoặc bất kỳ yêu cầu liên quan
  đến dashboard monitoring hiệu quả kinh doanh Pinpoint.
---

# SKILL: Performance Dashboard

## Purpose (Intent Layer)

Skill này dùng để build và cập nhật Pinpoint Monitoring Dashboard — một trang HTML tự chứa
(self-contained) hiển thị 8 mảng theo dõi hiệu quả vận hành của Pinpoint BU.

Kết quả được xem là hoàn thành khi:
- Dashboard HTML được cập nhật với data mới nhất từ Google Sheets
- Tất cả scorecards (H1, Q2) hiển thị đúng số liệu
- Charts (GP2 Monthly, Efficiency, Doughnut, Function) render đúng
- Bảng chi tiết theo tháng T1→T6 đầy đủ
- Project Detail có đầy đủ T1→T6 với matching status
- File được deploy lên GitHub Pages

Skill này KHÔNG xử lý: tạo dashboard mới từ đầu, thay đổi layout/design, hoặc thêm section mới.

## Use When

- User yêu cầu update/refresh dashboard sau khi cập nhật Google Sheets
- Cần cập nhật data POD Performance (GP2, DPPC, Efficiency)
- Cần cập nhật data Project Detail (forecast vs actual theo project)
- Đầu tuần/tháng khi có data mới

## Required Inputs

- **Google Sheet ID**: `1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8` (Pinpoint Operation System_2026)
- **Dashboard HTML file**: `/Users/tungnguyen/Pinpoint-dashboard/pinpoint-monitoring-dashboard.html`
- **Tháng hiện tại**: Xác định tháng nào đã có data actual (T1→T4 tính đến Q2/2026)

## Expected Output

- **Format**: Self-contained HTML file với inline CSS/JS + Chart.js CDN
- **Deploy**: Copy thành `index.html` → push GitHub Pages
- **URL**: https://ntt9d1130-creator.github.io/Pinpoint-dashboard/

## Knowledge Layer

### Data Sources — 3 Tabs trong Google Sheet

Đọc `references/data-schema.md` để hiểu chi tiết schema từng tab, column indices, data types.

**Tab 1: "1. POD Performance H1"**
- Chứa Budget GP2 theo tháng (row cuối, col B→G) và DPPC (col B→G dòng DPPC)
- Dùng cho: Budget values, DPPC values
- KHÔNG dùng cho forecast — forecast lấy từ Tab 2

**Tab 2: "2. Project Detailed Planning Data"**
- Chứa forecast GP2 theo từng project
- Cột AF (index 31) = FINAL GP (forecast) của từng project
- Sum theo tháng để ra forecast GP2 tổng
- Dùng cho: Forecast values, Project-level forecast, Function breakdown

**Tab 3: "3. Project Detailed Actual Data"**
- Chứa actual GP2 theo từng project
- Cột J (index 9) = GP2.5 — ĐÂY LÀ CỘT ĐÚNG, KHÔNG phải cột F (GP2)
- Sum theo tháng để ra actual GP2 tổng
- Dùng cho: Actual values, Project-level actual, Function breakdown actual

### Critical Rules

1. **Actual GP2 = Cột J (GP2.5)**, KHÔNG phải cột F (GP2). User đã confirm rõ ràng.
2. **Forecast = Sum cột AF từ Tab 2**, KHÔNG dùng dòng "Forecast GP2" ở Tab 1.
3. **gws CLI path**: `/usr/local/bin/gws` (không phải `/opt/homebrew/bin/gws`)
4. **gws JSON output thiếu `{` mở đầu** — phải prepend khi parse: `'{' + raw_output`
5. **Pipe qua `tail -n +2`** để skip dòng "Using keyring backend: keyring"
6. **Function names khác nhau giữa Tab 2 (Title Case) và Tab 3 (UPPER)** — normalize về UPPER
7. **T5, T6 hiển thị full** (không dim) để so sánh Budget vs Forecast dù chưa có actual

### References

- Schema chi tiết: `references/data-schema.md`
- Cấu trúc HTML: `references/html-structure.md`
- Script tính toán: `scripts/compute_dashboard.py`

## Execution Approach

### Bước 1: Đọc data từ Google Sheets

Dùng helper script hoặc gws CLI trực tiếp:

```bash
# Đọc Tab 2 — Planning Data (cần đọc đủ rows, sheet có >1000 rows)
/usr/local/bin/gws read --id 1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8 \
  --range "'2. Project Detailed Planning Data'!A1:AH1100" 2>&1 | tail -n +2 > /tmp/tab2.json

# Đọc Tab 3 — Actual Data
/usr/local/bin/gws read --id 1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8 \
  --range "'3. Project Detailed Actual Data'!A1:K1000" 2>&1 | tail -n +2 > /tmp/tab3.json

# Đọc Tab 1 — POD Performance (cho Budget + DPPC)
/usr/local/bin/gws read --id 1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8 \
  --range "'1. POD Performance H1'!A1:H50" 2>&1 | tail -n +2 > /tmp/tab1.json
```

Lưu ý khi parse JSON từ gws:
```python
import json
raw = open('/tmp/tab2.json').read().strip()
# gws output thiếu { mở đầu
if not raw.startswith('{'):
    raw = '{' + raw
data = json.loads(raw)
rows = data['values']  # 2D array
```

### Bước 2: Tính toán metrics

Từ data đã đọc, tính:

**POD Performance (theo tháng T1→T6):**
- Budget: Lấy từ Tab 1
- Forecast: Sum cột AF (index 31) của Tab 2, group by tháng
- Actual: Sum cột J (index 9) của Tab 3, group by tháng
- DPPC: Lấy từ Tab 1
- Efficiency: actual / forecast × 100 (chỉ cho tháng có actual > 0)

**Scorecards:**
- H1: Sum T1→T6 cho Budget, Forecast, Actual
- Q2: Sum T4→T6 cho Budget, Forecast, Actual
- % vs Forecast: actual_h1 / forecast_h1 × 100
- % vs Budget: forecast_h1 / budget_h1 × 100

**Function Breakdown:**
- Group by function (MEDIA, CREATIVE, TECH, SOCIAL, CRO, ANALYTICS...)
- Sum forecast + actual per function per month
- Normalize function name: Tab 2 dùng Title Case ("Media"), Tab 3 dùng UPPER ("MEDIA") → chuyển hết về UPPER

**Project Detail:**
- Merge Tab 2 (forecast) + Tab 3 (actual) theo project code + month
- Tính: pctForecast = actual / forecast × 100
- Tính: timegone = ngày đã qua / tổng ngày trong tháng × 100
- Tính: runrate = pctForecast / timegone × 100
- Matching: "MATCHED" nếu actual > 0 và forecast > 0

### Bước 3: Cập nhật HTML Dashboard

Dashboard là file HTML tự chứa. Cập nhật bằng cách thay thế trực tiếp các giá trị trong file:

1. **Scorecards**: Tìm và thay các giá trị số trong HTML (regex hoặc string replace)
2. **Chart data arrays**: Thay các array trong `<script>` tags:
   - `budgetData = [1988, 1097, 2031, 2295, 2295, 2295]`
   - `forecastData = [1263.6, 974.3, ...]`
   - `actualData = [1122.3, 880.4, ...]`
3. **Monthly detail table**: Rebuild `<tbody>` với rows T1→T6 + H1 summary
4. **Function breakdown table**: Rebuild tbody với data per function per month
5. **projectData array**: Rebuild toàn bộ array (~700+ entries)

Xem `references/html-structure.md` để biết chính xác vị trí và pattern regex cho từng phần.

### Bước 4: Deploy

```bash
cd /Users/tungnguyen/Pinpoint-dashboard
cp pinpoint-monitoring-dashboard.html index.html
git add -A
git commit -m "Update dashboard data [date]"
git push origin main
```

### Tools & Scripts
- `gws` CLI qua Desktop Commander MCP (chạy trên Mac của user)
- Helper: `~/bin/gsheet-read.sh`, `~/bin/gsheet-meta.sh`
- Python cho data processing (chạy qua Desktop Commander)
- Script tham khảo: `scripts/compute_dashboard.py`

## Quality Criteria

- [ ] Scorecard H1 GP2 Actual = Sum T1→T6 actual (khớp Tab 3 cột J)
- [ ] Scorecard H1 Forecast = Sum T1→T6 forecast (khớp Tab 2 cột AF)
- [ ] Scorecard Q2 tương tự cho T4→T6
- [ ] Chart bars khớp với bảng số liệu
- [ ] Efficiency = actual/forecast chỉ cho tháng có actual > 0
- [ ] Project Detail: tổng actual theo tháng khớp POD actual cùng tháng
- [ ] Tất cả T1→T6 hiển thị trong bảng (không ẩn T5/T6)
- [ ] Function breakdown table có đủ functions và đúng số

## Verification (4C Framework)

### Correctness — Có đúng không?
- Sum GP2 actual trong Project Detail == GP2 actual trong POD Performance (cùng tháng)
- Sum GP2 forecast trong Project Detail == GP2 forecast trong POD Performance (cùng tháng)
- Efficiency % = actual / forecast × 100, rounded 1 decimal
- DPPC values khớp Tab 1

### Completeness — Có đủ không?
- Đủ 6 tháng (T1→T6) trong bảng chi tiết
- Đủ H1 summary row
- Có cả scorecard H1 VÀ Q2
- Project Detail có entries cho tất cả tháng đã có data
- Function breakdown có đủ tất cả functions

### Context-fit — Có hợp ngữ cảnh không?
- Số liệu đơn vị triệu VND (hiển thị dạng "1,122.3M")
- Tháng chưa có actual hiển thị 0 (không để trống)
- T5/T6 không bị dim/ẩn

### Consequence — Dùng thật có ổn không?
- Dashboard public trên GitHub Pages — số liệu phải chính xác
- Nếu sai actual/forecast sẽ gây hiểu lầm về hiệu quả kinh doanh
- Cross-check: POD totals phải khớp Project Detail totals

## Edge Cases

- **Tab 2 có >1000 rows**: Phải đọc đủ range (A1:AH1100), không chỉ 500
- **Tháng chưa có actual**: actual = 0, không tính efficiency cho tháng đó
- **Function name mismatch**: Tab 2 dùng "Media", Tab 3 dùng "MEDIA" → normalize UPPER
- **gws JSON malformed**: Output thiếu `{`, phải prepend
- **Project code trùng giữa các tháng**: Group by month + code, không chỉ code

## Anti-patterns

- KHÔNG dùng cột F (GP2) cho actual — phải dùng cột J (GP2.5)
- KHÔNG dùng Tab 1 "Forecast GP2" cho forecast — phải sum từ Tab 2 cột AF
- KHÔNG dim/ẩn T5 T6 — user muốn xem full để so Budget vs Forecast
- KHÔNG xoá bảng Function Breakdown — đây là bảng quan trọng
- KHÔNG nhầm bảng Function Breakdown với bảng chi tiết theo tháng

## Changelog

- v1.0: Khởi tạo skill — document toàn bộ quy trình build/update dashboard
