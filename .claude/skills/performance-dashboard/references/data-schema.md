# Data Schema — Pinpoint Operation System 2026

**Spreadsheet ID**: `1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8`

---

## Tab 1: "1. POD Performance H1"

### Mục đích
Chứa data tổng hợp POD Performance: Budget GP2, DPPC theo tháng.

### Cấu trúc
- **Range**: `A1:H50` (nhỏ, đọc nhanh)
- **Dạng**: Bảng tổng hợp, không phải dạng danh sách project

### Columns quan trọng
| Col | Index | Nội dung |
|-----|-------|----------|
| A | 0 | Label (tên metric) |
| B | 1 | T1/2026 |
| C | 2 | T2/2026 |
| D | 3 | T3/2026 |
| E | 4 | T4/2026 |
| F | 5 | T5/2026 |
| G | 6 | T6/2026 |
| H | 7 | H1 Total |

### Rows quan trọng (vị trí có thể thay đổi, tìm theo label cột A)
- Row "GP2 Budget": Budget GP2 theo tháng
- Row "DPPC": DPPC theo tháng

### Lưu ý
- KHÔNG dùng row "Forecast GP2" từ tab này — forecast phải sum từ Tab 2 cột AF
- Budget và DPPC lấy từ tab này là chính xác

---

## Tab 2: "2. Project Detailed Planning Data"

### Mục đích
Chứa forecast GP theo từng project, từng tháng. Dùng để tính forecast GP2 tổng và function breakdown.

### Cấu trúc
- **Range**: `A1:AH1100` (>1000 rows, phải đọc đủ)
- **Dạng**: Mỗi row = 1 project trong 1 tháng

### Columns quan trọng
| Col | Index | Tên | Mô tả |
|-----|-------|-----|-------|
| A | 0 | Month | Tháng dạng "T1/2026", "T2/2026"... |
| B | 1 | Project Code | Mã project (VD: SEEFQMP001) |
| C | 2 | Project Name | Tên project |
| D | 3 | Function/Title | Function dạng Title Case ("Media", "Creative") |
| AF | 31 | FINAL GP | **Forecast GP — CỘT CHÍNH ĐỂ TÍNH FORECAST** |

### Cách tính
```python
# Forecast GP2 theo tháng
forecast_by_month = {}
for row in tab2_rows[1:]:  # skip header
    month = row[0]  # "T1/2026"
    final_gp = float(row[31] or 0)  # col AF = index 31
    forecast_by_month[month] = forecast_by_month.get(month, 0) + final_gp

# Forecast theo function
forecast_by_func = {}
for row in tab2_rows[1:]:
    month = row[0]
    func = row[3].upper()  # Normalize: "Media" → "MEDIA"
    final_gp = float(row[31] or 0)
    key = (month, func)
    forecast_by_func[key] = forecast_by_func.get(key, 0) + final_gp
```

### Lưu ý
- Function name ở đây là Title Case ("Media", "Creative", "Livestream")
- Phải normalize về UPPER khi merge với Tab 3
- Có thể có rows trống hoặc row tổng — filter by month format "T\d/2026"

---

## Tab 3: "3. Project Detailed Actual Data"

### Mục đích
Chứa actual GP2.5 theo từng project, từng tháng. Dùng để tính actual GP2 tổng.

### Cấu trúc
- **Range**: `A1:K1000` (thường ~300-400 rows có data)
- **Dạng**: Mỗi row = 1 project trong 1 tháng

### Columns quan trọng
| Col | Index | Tên | Mô tả |
|-----|-------|-----|-------|
| A | 0 | Month | Tháng dạng "T1/2026", "T2/2026"... |
| B | 1 | Project Code | Mã project |
| C | 2 | Project Name | Tên project |
| D | 3 | Function | Function dạng UPPER ("MEDIA", "CREATIVE") |
| F | 5 | GP2 | ❌ KHÔNG DÙNG — đây là GP2 cũ |
| J | 9 | GP2.5 | ✅ **CỘT ĐÚNG — Actual GP2.5** |

### Cách tính
```python
# Actual GP2 theo tháng
actual_by_month = {}
for row in tab3_rows[1:]:  # skip header
    month = row[0]  # "T1/2026"
    gp25 = float(row[9] or 0)  # col J = index 9 ← GP2.5
    actual_by_month[month] = actual_by_month.get(month, 0) + gp25

# Actual theo function
actual_by_func = {}
for row in tab3_rows[1:]:
    month = row[0]
    func = row[3].upper()  # Đã là UPPER nhưng normalize cho chắc
    gp25 = float(row[9] or 0)
    key = (month, func)
    actual_by_func[key] = actual_by_func.get(key, 0) + gp25
```

### Lưu ý
- **Cột J (index 9) = GP2.5** — đây là metric chính, user đã confirm
- Cột F (index 5) = GP2 cũ — KHÔNG dùng (sẽ ra số thấp hơn, VD: 262.9M thay vì 403.2M)
- Function name ở Tab 3 đã là UPPER ("MEDIA", "CREATIVE")

---

## gws CLI — Cách đọc data

### Command format
```bash
/usr/local/bin/gws read \
  --id 1yvc6IeHdoYX6WAzOz2PQ4AgWa3R9tF4iVw3XXvH5JG8 \
  --range "'TAB_NAME'!A1:Z999" 2>&1 | tail -n +2 > /tmp/output.json
```

### Parse JSON output
gws trả về JSON nhưng **thiếu ký tự `{` mở đầu**. Phải prepend:
```python
raw = open('/tmp/output.json').read().strip()
if not raw.startswith('{'):
    raw = '{' + raw
data = json.loads(raw)
rows = data['values']  # 2D array: [[row1_col1, row1_col2, ...], ...]
```

### Gotchas
- Dòng đầu tiên của gws stdout là "Using keyring backend: keyring" → `tail -n +2` để skip
- gws path: `/usr/local/bin/gws` (KHÔNG phải `/opt/homebrew/bin/gws`)
- Nếu range quá nhỏ sẽ thiếu data — Tab 2 cần ít nhất AH1100
- Empty cells trả về `""` hoặc missing từ array → handle `float(val or 0)`
