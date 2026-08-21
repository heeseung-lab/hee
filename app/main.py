from flask import Flask, jsonify, render_template_string, request

from app.db import (
    dashboard_summary,
    get_keywords,
    init_db,
    list_stores,
    recent_reviews,
    replace_keywords,
    upsert_store,
)
from app.naver_crawler import CrawlError
from app.service import inspect_store

app = Flask(__name__)
init_db()

PAGE = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>청년다방 리뷰 모니터링</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#18181b;font-family:Arial,"Noto Sans KR",sans-serif}.wrap{max-width:1240px;margin:auto;padding:28px}.head{display:flex;justify-content:space-between;align-items:end;margin-bottom:22px}.head h1{margin:0;font-size:28px}.sub,.muted{color:#71717a}.sub{margin-top:7px}.card{background:#fff;border:1px solid #e4e4e7;border-radius:18px;padding:18px}.search{display:grid;grid-template-columns:1fr 1.5fr auto;gap:10px}.search input,textarea{padding:13px;border:1px solid #d4d4d8;border-radius:11px;font-size:14px;width:100%}.btn{border:0;border-radius:11px;background:#18181b;color:#fff;padding:0 20px;font-weight:700;cursor:pointer}.btn.secondary{background:#fff;color:#18181b;border:1px solid #d4d4d8;padding:10px 14px}.summary{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:16px 0}.metric b{font-size:25px;display:block;margin-top:5px}.layout{display:grid;grid-template-columns:1.1fr 1.5fr;gap:14px}.row{padding:13px 0;border-bottom:1px solid #eee}.row:last-child{border:0}.review{padding:15px 0;border-bottom:1px solid #eee}.bad{background:#fee2e2;color:#b91c1c;border-radius:5px;padding:2px 5px;font-weight:700}.good{background:#dcfce7;color:#166534;border-radius:5px;padding:2px 5px;font-weight:700}.pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700}.danger{background:#fee2e2;color:#b91c1c}.warn{background:#fef3c7;color:#92400e}.ok{background:#dcfce7;color:#166534}.failed{color:#b91c1c}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.status{padding:12px;border-radius:11px;background:#fafafa;margin-top:12px}.tabs{display:flex;gap:8px;margin-bottom:12px}.tabs button{border:1px solid #ddd;background:#fff;border-radius:999px;padding:8px 12px;cursor:pointer}.tabs button.active{background:#18181b;color:#fff}.hidden{display:none}@media(max-width:820px){.search,.layout,.summary{grid-template-columns:1fr}.btn{padding:13px}.wrap{padding:16px}}
</style></head><body><div class="wrap">
<div class="head"><div><h1>청년다방 리뷰 모니터링</h1><div class="sub">최신 리뷰 수집 · 불량언어 자동체크 · 위험 매장 우선관리</div></div><div class="muted">자동수집 09:00 / 18:00 KST</div></div>
<div class="summary"><div class="card metric"><span class="muted">등록 매장</span><b id="mStores">-</b></div><div class="card metric"><span class="muted">누적 리뷰</span><b id="mReviews">-</b></div><div class="card metric"><span class="muted">불량 리뷰</span><b id="mBad">-</b></div><div class="card metric"><span class="muted">집중관리 매장</span><b id="mCritical">-</b></div><div class="card metric"><span class="muted">주의 매장</span><b id="mWarning">-</b></div></div>
<div class="card"><div class="search"><input id="name" value="청년다방" placeholder="매장명"><input id="address" placeholder="주소 또는 지점명"><button class="btn" id="checkBtn">이 매장 검사</button></div><div id="status" class="status">매장 하나를 먼저 검사해 실제 리뷰 수집 여부를 확인하세요.</div></div>
<div class="tabs" style="margin-top:16px"><button class="active" data-tab="stores">매장 현황</button><button data-tab="reviews">최신 리뷰</button><button data-tab="keywords">키워드 설정</button></div>
<div id="tab-stores" class="layout"><div class="card"><b>위험 매장 우선순위</b><div id="stores" class="muted" style="margin-top:12px">불러오는 중…</div></div><div class="card"><b>선택 매장 최신 검사 결과</b><div id="checked" class="muted" style="margin-top:12px">아직 검사하지 않았습니다.</div></div></div>
<div id="tab-reviews" class="card hidden"><b>최근 수집 리뷰</b><div id="recent" class="muted" style="margin-top:12px">불러오는 중…</div></div>
<div id="tab-keywords" class="layout hidden"><div class="card"><b>불량언어</b><p class="muted">한 줄에 하나씩 입력</p><textarea id="badWords" rows="13"></textarea><button class="btn secondary" data-save="bad" style="margin-top:10px">불량언어 저장</button></div><div class="card"><b>좋은언어</b><p class="muted">한 줄에 하나씩 입력</p><textarea id="goodWords" rows="13"></textarea><button class="btn secondary" data-save="good" style="margin-top:10px">좋은언어 저장</button></div></div>
</div>
<script>
const $=id=>document.getElementById(id);function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}function hl(text,bad,good){let s=esc(text);[...bad].sort((a,b)=>b.length-a.length).forEach(w=>s=s.replaceAll(esc(w),'<span class="bad">'+esc(w)+'</span>'));[...good].sort((a,b)=>b.length-a.length).forEach(w=>s=s.replaceAll(esc(w),'<span class="good">'+esc(w)+'</span>'));return s}function badge(level){return '<span class="pill '+(level==='집중관리'?'danger':level==='주의'?'warn':'ok')+'">'+esc(level)+'</span>'}
async function api(url,opt){const r=await fetch(url,opt);const d=await r.json();if(!r.ok)throw new Error(d.error||'요청 실패');return d}
async function refresh(){const [s,stores,reviews,keys]=await Promise.all([api('/api/summary'),api('/api/stores'),api('/api/reviews?limit=80'),api('/api/keywords')]);$('mStores').textContent=s.stores;$('mReviews').textContent=s.reviews;$('mBad').textContent=s.bad_reviews;$('mCritical').textContent=s.critical_stores;$('mWarning').textContent=s.warning_stores;$('stores').innerHTML=stores.length?stores.map(x=>'<div class="row"><b>'+esc(x.name)+'</b> <span class="muted">'+esc(x.address||'')+'</span><div class="muted" style="margin-top:5px">리뷰 '+x.review_count+' · 불량 '+(x.bad_review_count||0)+' · 최고 위험점수 '+(x.max_score||0)+' · 상태 '+esc(x.last_status)+(x.last_error?' · <span class="failed">'+esc(x.last_error)+'</span>':'')+'</div></div>').join(''):'등록된 매장이 없습니다.';$('recent').innerHTML=reviews.length?reviews.map(x=>'<div class="review">'+badge(x.level)+' <b>'+esc(x.store_name)+'</b><div style="margin:8px 0;line-height:1.7">'+hl(x.body,(x.bad_hits||'').split(',').filter(Boolean),(x.good_hits||'').split(',').filter(Boolean))+'</div><div class="muted">불량 '+esc(x.bad_hits||'-')+' · 좋은 '+esc(x.good_hits||'-')+' · 점수 '+x.score+'</div></div>').join(''):'아직 저장된 리뷰가 없습니다.';$('badWords').value=keys.bad.join('\n');$('goodWords').value=keys.good.join('\n')}
async function check(){const status=$('status');status.textContent='네이버 최신 리뷰를 확인하고 있습니다…';try{const d=await api('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('name').value,address:$('address').value})});status.innerHTML='<b>검사 완료</b> · 신규 리뷰 '+d.new_reviews+'건 · 전체 '+d.reviews.length+'건 확인';$('checked').innerHTML=d.reviews.map(x=>'<div class="review">'+badge(x.level)+'<div style="margin:8px 0;line-height:1.7">'+hl(x.text,x.bad_hits,x.good_hits)+'</div><div class="muted">불량 '+esc(x.bad_hits.join(', ')||'-')+' · 좋은 '+esc(x.good_hits.join(', ')||'-')+'</div></div>').join('');await refresh()}catch(e){status.innerHTML='<b class="failed">수집 실패</b> · '+esc(e.message)}}
$('checkBtn').addEventListener('click',check);document.querySelectorAll('[data-save]').forEach(b=>b.addEventListener('click',async()=>{const kind=b.dataset.save;const value=(kind==='bad'?$('badWords'):$('goodWords')).value;await api('/api/keywords/'+kind,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({words:value.split(/\n/).map(x=>x.trim()).filter(Boolean)})});$('status').textContent='키워드를 저장했습니다. 이후 수집 리뷰부터 새 기준을 적용합니다.';await refresh()}));document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));b.classList.add('active');['stores','reviews','keywords'].forEach(t=>$('tab-'+t).classList.toggle('hidden',t!==b.dataset.tab))}));refresh().catch(e=>$('status').textContent='초기화 오류: '+e.message);
</script></body></html>'''


@app.get("/")
def dashboard():
    return render_template_string(PAGE)


@app.post("/api/check")
def check_store():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    address = (payload.get("address") or "").strip()
    if not name:
        return jsonify(error="매장명을 입력하세요"), 400
    try:
        result = inspect_store(name, address, limit=30)
    except CrawlError as exc:
        return jsonify(error=str(exc)), 502
    except Exception as exc:
        return jsonify(error=f"예상하지 못한 수집 오류: {type(exc).__name__}: {exc}"), 500
    return jsonify(store=" ".join(x for x in [name, address] if x), **result)


@app.get("/api/summary")
def summary_api():
    return jsonify(dashboard_summary())


@app.get("/api/stores")
def stores_api():
    return jsonify(list_stores())


@app.post("/api/stores")
def add_store_api():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    address = (payload.get("address") or "").strip()
    if not name:
        return jsonify(error="매장명이 필요합니다"), 400
    return jsonify(id=upsert_store(name, address)), 201


@app.get("/api/reviews")
def reviews_api():
    limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    return jsonify(recent_reviews(limit))


@app.get("/api/keywords")
def keywords_api():
    return jsonify(get_keywords())


@app.put("/api/keywords/<kind>")
def keywords_update_api(kind):
    payload = request.get_json(silent=True) or {}
    words = payload.get("words") or []
    if not isinstance(words, list):
        return jsonify(error="words는 배열이어야 합니다"), 400
    try:
        replace_keywords(kind, words)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(get_keywords())


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
