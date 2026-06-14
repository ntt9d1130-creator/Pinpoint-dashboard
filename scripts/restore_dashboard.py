#!/usr/bin/env python3
"""Re-apply Qualified Brief by BD + Project dynamic summary patches.
Run after sync_growth/sync_pod nếu chúng vô tình overwrite các section đã tùy biến."""
import re
from pathlib import Path

INDEX = Path("/Users/tungnguyen/Pinpoint-dashboard/index.html")
html = INDEX.read_text(encoding="utf-8")

def sub(pattern, repl, name, flags=0, count=1):
    global html
    new, n = re.subn(pattern, lambda m: repl, html, count=count, flags=flags)
    print(("  OK   " if n else "  !!NOMATCH ") + name + f" ({n})")
    html = new

# 1) Sales section → Qualified Brief by BD
SALES = '''<!-- ===== SECTION 3: HOẠT ĐỘNG SALES ===== -->
<div id="sales" class="sec">
    <div class="sec-title">Hoạt động Sales — Qualified Brief by BD (Q2/2026)</div>
    <div class="highlights"><h4>Điểm nổi bật</h4><ul id="bdHighlights"></ul></div>
    <div id="bdSummaryKPIs" style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap"></div>
    <div class="tbl-wrap"><h3>Qualified Brief theo BD — theo tuần</h3>
        <div style="overflow-x:auto"><table id="tblBD" style="font-size:12px"><thead id="tblBDHead"></thead><tbody id="tblBDBody"></tbody></table></div>
    </div>
</div>

'''
sub(r'<!-- ===== SECTION 3: HOẠT ĐỘNG SALES ===== -->[\s\S]*?(?=<!-- ===== SECTION 4:)', SALES, "sales section", flags=re.S)

# 2) Filter labels
sub(r'<option value="">Tất cả PIC</option>', '<option value="">Tất cả Function</option>', "filterPIC label")
sub(r'<option value="">Tất cả ngành</option>', '<option value="">Tất cả Tháng</option>', "filterVertical label")

# 3) Project highlights → highlights + summary container
PROJ_HL = '''<div class="highlights">
        <h4>Điểm nổi bật</h4>
        <ul>
            <li class="good">Dữ liệu chi tiết từng project — lọc theo Function, Trạng thái, Tháng</li>
            <li class="warn">Tổng quan động theo tháng/quý hiện tại; chi tiết dự án theo từng tháng</li>
        </ul>
    </div>

    <div id="projQuarterSummary" style="display:flex;gap:10px;margin:16px 0;flex-wrap:wrap"></div>'''
sub(r'<div class="highlights">\s*<h4>Điểm nổi bật</h4>\s*<ul>\s*<li class="good">Dữ liệu chi tiết từng project[\s\S]*?</ul>\s*</div>', PROJ_HL, "project highlights", flags=re.S)

# 4) Project table thead
sub(r'<tr><th>Project</th><th>Khách hàng</th><th>PIC</th><th>Ngành</th><th>Trạng thái</th><th>Giai đoạn</th><th>GP2</th><th>Nguồn</th><th>Cập nhật</th></tr>',
    '<tr><th>Project</th><th>Mã KH</th><th>Function</th><th>Tháng</th><th>Trạng thái</th><th style="text-align:right">Forecast tháng</th><th style="text-align:right">Actual tháng</th><th style="text-align:center">Achievement tháng</th></tr>',
    "project thead")

# 5) Project render loop
RENDER = """filtered.slice(0, 200).forEach(d => {
        const pctVal = d.forecast !== 0 ? ((d.actual / d.forecast) * 100) : null;
        const pctClass = pctVal === null ? '' : pctVal >= 100 ? 'badge-green' : pctVal >= 70 ? 'badge-yellow' : 'badge-red';
        const pctDisplay = d.pctForecast || '—';
        const matchMap = {MATCHED:'badge-green', FORECAST_ONLY:'badge-yellow', ACTUAL_ONLY:'badge-blue'};
        const matchClass = matchMap[d.matching] || 'badge-red';
        tbody.innerHTML += `<tr>
            <td><strong style="font-size:11px">${d.name}</strong></td>
            <td>${d.code || ''}</td>
            <td>${d.func || ''}</td>
            <td>${d.month || ''}</td>
            <td><span class="badge ${matchClass}" style="font-size:10px">${d.matching || ''}</span></td>
            <td style="text-align:right">${d.forecast.toFixed(1)}</td>
            <td style="text-align:right">${d.actual.toFixed(1)}</td>
            <td style="text-align:center"><span class="badge ${pctClass}">${pctDisplay}</span></td>
        </tr>`;
    });"""
sub(r'filtered\.slice\(0, 200\)\.forEach\(d => \{[\s\S]*?\n    \}\);', RENDER, "project render loop", flags=re.S)

# 6) JS renderBD + renderProjSummary + init hooks
JS = '''
// ============ QUALIFIED BRIEF BY BD ============
function renderBD() {
    const bd = window.DASHBOARD_DATA.qualifiedBriefByBD;
    if (!bd) return;
    const weeks = bd.weeks || [];
    const head = document.getElementById('tblBDHead');
    if (head) head.innerHTML = `<tr><th>Nhóm BD</th><th>BD</th>${weeks.map(w=>`<th style="text-align:center">${w}</th>`).join('')}<th style="text-align:center">Tổng</th></tr>`;
    const body = document.getElementById('tblBDBody');
    const typeColor = {'Referral PMAX':'badge-purple','Account PP':'badge-blue','Existing BD':'badge-green','New BD':'badge-yellow'};
    let htmlR = '';
    (bd.rows||[]).forEach(r => {
        const cls = typeColor[r.type] || 'badge-blue';
        htmlR += `<tr><td><span class="badge ${cls}" style="font-size:10px">${r.type||''}</span></td><td><strong>${r.name}</strong></td>${r.values.map(v=>`<td style="text-align:center;color:${v>0?'var(--text)':'var(--text2)'}">${v||0}</td>`).join('')}<td style="text-align:center;font-weight:700">${r.total||0}</td></tr>`;
    });
    if (bd.total) htmlR += `<tr style="font-weight:700;border-top:2px solid var(--border);background:var(--bg-card)"><td></td><td>TỔNG</td>${bd.total.map(v=>`<td style="text-align:center">${v||0}</td>`).join('')}<td style="text-align:center">${bd.grandTotal||0}</td></tr>`;
    if (body) body.innerHTML = htmlR;
    const kpi = document.getElementById('bdSummaryKPIs');
    if (kpi) {
        const byType = {};
        (bd.rows||[]).forEach(r => { byType[r.type]=(byType[r.type]||0)+r.total; });
        const cards = [['Tổng Qualified Brief (Quý)', bd.grandTotal||0, 'var(--blue)']];
        Object.keys(byType).forEach(t => cards.push([t, byType[t], 'var(--text2)']));
        kpi.innerHTML = cards.map(c=>`<div style="background:var(--bg-card);padding:10px 16px;border-radius:10px;box-shadow:var(--shadow);border-left:3px solid ${c[2]}"><div style="font-size:0.75rem;color:var(--text2)">${c[0]}</div><div style="font-size:1.1rem;font-weight:700;color:${c[2]}">${c[1]}</div></div>`).join('');
    }
    const hl = document.getElementById('bdHighlights');
    if (hl) {
        const ranked = (bd.rows||[]).filter(r=>r.total>0).sort((a,b)=>b.total-a.total);
        const zero = (bd.rows||[]).filter(r=>r.total===0).length;
        let items = '';
        if (ranked[0]) items += `<li class="good">Top BD: ${ranked[0].name} — ${ranked[0].total} Qualified Brief trong quý</li>`;
        if (ranked[1]) items += `<li class="good">Á quân: ${ranked[1].name} — ${ranked[1].total} QB</li>`;
        items += `<li class="warn">${zero}/${(bd.rows||[]).length} BD chưa có Qualified Brief nào trong quý</li>`;
        hl.innerHTML = items;
    }
}
'''

JS = JS + '''
// ============ PROJECT QUARTER/MONTH SUMMARY (dynamic) ============
function renderProjSummary() {
    const mp = window.DASHBOARD_DATA.monthlyPOD;
    const box = document.getElementById('projQuarterSummary');
    if (!mp || !box) return;
    const now = new Date();
    let cur = now.getMonth() + 1;
    const maxMonth = Math.max.apply(null, mp.map(m=>m.monthNum));
    if (cur > maxMonth) cur = maxMonth;
    const qIdx = Math.floor((cur - 1) / 3);
    const qMonths = [qIdx*3+1, qIdx*3+2, qIdx*3+3];
    const qLabel = 'Q' + (qIdx + 1);
    const inQ = mp.filter(m => qMonths.indexOf(m.monthNum) >= 0);
    const sum = (a,k)=>a.reduce((s,m)=>s+(m[k]||0),0);
    const targetQ = sum(inQ,'target'), forecastQ = sum(inQ,'forecast');
    const elapsed = inQ.filter(m=>m.monthNum<=cur);
    const actualQ = sum(elapsed,'actual');
    let rrTarget = 0;
    elapsed.forEach(m => { rrTarget += (m.monthNum < cur) ? m.target : m.target*(m.progress||0); });
    const rrAch = rrTarget>0 ? (actualQ/rrTarget*100) : 0;
    const achQ = targetQ>0 ? (actualQ/targetQ*100) : 0;
    const curM = mp.filter(m=>m.monthNum===cur)[0] || {label:'T'+cur,target:0,forecast:0,actual:0,progress:0};
    const achM = curM.forecast>0 ? (curM.actual/curM.forecast*100) : 0;
    const elapsedLabels = elapsed.map(m=>m.label).join('–');
    function card(label,val,sub,color){
        return `<div style="background:var(--bg-card);padding:12px 18px;border-radius:10px;box-shadow:var(--shadow);border-left:4px solid ${color};min-width:155px"><div style="font-size:0.75rem;color:var(--text2)">${label}</div><div style="font-size:1.25rem;font-weight:800;color:${color}">${val}</div><div style="font-size:0.72rem;color:var(--text2)">${sub||''}</div></div>`;
    }
    const cQ = achQ>=90?'var(--green)':achQ>=70?'var(--yellow)':'var(--red)';
    const cM = achM>=90?'var(--green)':achM>=70?'var(--yellow)':'var(--red)';
    box.innerHTML =
        card('Target tổng '+qLabel, targetQ.toFixed(0)+'M', qMonths.map(n=>'T'+n).join('+'), 'var(--blue)') +
        card('Forecast tổng '+qLabel, forecastQ.toFixed(0)+'M', 'GP2 dự báo cả quý', 'var(--yellow)') +
        card('Actual '+qLabel+' ('+elapsedLabels+')', actualQ.toFixed(0)+'M', 'Runrate: '+rrAch.toFixed(0)+'% · vs target quý: '+achQ.toFixed(0)+'%', cQ) +
        card('Forecast tháng ('+curM.label+')', (curM.forecast||0).toFixed(0)+'M', 'GP2 dự báo tháng', 'var(--yellow)') +
        card('Actual tháng ('+curM.label+')', (curM.actual||0).toFixed(0)+'M', 'Achievement: '+achM.toFixed(0)+'% vs forecast', cM);
}
'''
sub(r'\n// Init\nfilterProjects\(\);', JS + "\n// Init\nfilterProjects();\nrenderBD();\nrenderProjSummary();", "js add + init")

# 7) Remove orphaned chartSalesPIC / chartSalesMetrics blocks if they exist
removed_chart, n = re.subn(r'// =+ SALES PIC CHARTS =+\n[\s\S]*?(?=// =+ CHART 6: Account Funnel =+)', '', html, count=1)
if n: html = removed_chart; print(f"  OK   removed orphan SALES PIC chart inits ({n})")
else: print("  (no orphan SALES PIC chart block to remove)")

INDEX.write_text(html, encoding="utf-8")
print("DONE — wrote index.html")
