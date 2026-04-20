# Verification Checklist — Performance Dashboard

Dùng checklist này sau mỗi lần update dashboard để đảm bảo data chính xác.

---

## 1. Correctness — Có đúng không?

### Data Source
- [ ] Actual GP2 đọc từ Tab 3, **cột J (index 9)** — không phải cột F
- [ ] Forecast GP2 tính bằng **sum cột AF (index 31) từ Tab 2** — không dùng Tab 1
- [ ] Budget GP2 và DPPC lấy từ Tab 1
- [ ] gws JSON được parse đúng (prepend `{` nếu thiếu)

### Tính toán
- [ ] H1 Actual = Sum(T1 actual + T2 + T3 + T4 + T5 + T6)
- [ ] H1 Forecast = Sum(T1 forecast + T2 + ... + T6)
- [ ] Q2 Actual = Sum(T4 + T5 + T6) actual
- [ ] Q2 Forecast = Sum(T4 + T5 + T6) forecast
- [ ] % vs Forecast = actual / forecast × 100
- [ ] % vs Budget = forecast / budget × 100
- [ ] Efficiency = actual / forecast × 100 (chỉ tháng có actual > 0)
- [ ] Achievement = actual / budget × 100

### Cross-check
- [ ] Sum actual trong projectData theo T1 ≈ POD actual T1 (sai lệch < 0.5M)
- [ ] Sum actual trong projectData theo T2 ≈ POD actual T2
- [ ] Tương tự cho T3, T4...
- [ ] Sum forecast trong projectData theo tháng ≈ POD forecast tháng đó

## 2. Completeness — Có đủ không?

### Scorecards
- [ ] Có scorecard H1 (5 KPI cards): GP2 Actual, Forecast, Budget, DPPC, % DPPC/GP2
- [ ] Có scorecard Q2 (5 KPI cards): GP2 Actual, Forecast, Budget, DPPC, Timegone

### Bảng chi tiết
- [ ] Bảng tháng có đủ T1 → T6 (6 rows) + H1 summary (1 row)
- [ ] T5, T6 hiển thị full (KHÔNG dim, KHÔNG ẩn)
- [ ] Tháng chưa có actual hiển thị "—" hoặc "0" (không để trống)

### Function Breakdown
- [ ] Bảng function breakdown CÓ MẶT (không bị xoá nhầm)
- [ ] Có đủ tất cả functions xuất hiện trong data
- [ ] Có đủ tất cả tháng đã có actual

### Charts
- [ ] Chart GP2 Monthly có đủ 6 bars (T1→T6)
- [ ] Chart Efficiency chỉ hiển thị tháng có actual
- [ ] Chart Doughnut hiển thị function cho tháng actual gần nhất
- [ ] Chart Function Performance có đủ functions

### Project Detail
- [ ] projectData array có entries cho T1 → T6 (hoặc tất cả tháng có data)
- [ ] Không thiếu T1, T2 (lỗi cũ đã gặp)
- [ ] Filters (Month, Function, Matching) hoạt động đúng

## 3. Context-fit — Có hợp ngữ cảnh không?

- [ ] Số liệu hiển thị đơn vị triệu VND (dạng "1,122.3M" hoặc "1,122.3")
- [ ] Badge colors đúng: green (≥90%), yellow (≥70%), red (<70%)
- [ ] Matching status đúng: MATCHED, FORECAST_ONLY, ACTUAL_ONLY
- [ ] Dashboard title và date badge cập nhật đúng

## 4. Consequence — Dùng thật có ổn không?

- [ ] Dashboard public trên GitHub Pages — đã double-check số trước khi push
- [ ] Không có data nhạy cảm (tên nhân viên, thông tin cá nhân) trong repo public
- [ ] Git commit message mô tả rõ thay đổi gì
- [ ] index.html đã được copy từ pinpoint-monitoring-dashboard.html

---

## Quick Smoke Test

Sau khi deploy, kiểm tra nhanh trên browser:
1. Mở https://ntt9d1130-creator.github.io/Pinpoint-dashboard/
2. Tab POD Performance: scorecards hiển thị đúng?
3. Charts render không lỗi?
4. Tab Project Detail: filter Month → chọn tháng có data → có records?
5. Click qua tất cả 8 tabs — không có tab nào trắng?
