# Changelog — Performance Dashboard Skill

## v1.0 (2026-04-16)

**Khởi tạo skill** — Document toàn bộ quy trình build/update Pinpoint Monitoring Dashboard.

### Files created
- `SKILL.md` — Hướng dẫn chính với 5 lớp (Intent, Knowledge, Execution, Verification, Evolution)
- `references/data-schema.md` — Schema chi tiết 3 tabs Google Sheet (column indices, data types, parse logic)
- `references/html-structure.md` — Cấu trúc HTML dashboard (8 sections, line positions, regex patterns update)
- `scripts/compute_dashboard.py` — Reference Python script tính toán metrics (POD, Function, Project Detail)
- `verification/checklist.md` — 4C verification checklist + smoke test

### Key decisions documented
- Actual GP2 = Cột J (GP2.5), KHÔNG phải cột F (GP2) — confirmed by user
- Forecast = Sum cột AF từ Tab 2, KHÔNG dùng Tab 1 "Forecast GP2"
- gws CLI output thiếu `{` mở đầu → phải prepend khi parse
- Function name normalize: Tab 2 Title Case → UPPER, Tab 3 đã UPPER
- T5/T6 hiển thị full, không dim — user muốn so Budget vs Forecast
- Bảng Function Breakdown là bảng riêng biệt, KHÔNG nhầm với bảng chi tiết theo tháng

### Lessons learned (từ quá trình build)
- Lần đầu dùng sai cột actual (cột F thay vì J) → ra 262.9M thay vì 403.2M
- Lần đầu dùng sai source forecast (Tab 1 thay vì Tab 2) → chênh ~500M
- Đã nhầm xoá bảng Function Breakdown khi user nói "không cần breakdown theo function" (ý là bảng tháng)
- Tab 2 có >1000 rows, cần đọc range đủ lớn (AH1100)
