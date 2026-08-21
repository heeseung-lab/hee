from flask import Flask, jsonify, render_template_string, request

from app.naver_crawler import CrawlError, NaverPlaceCrawler
from app.review_analyzer import analyze_review

app = Flask(__name__)
crawler = NaverPlaceCrawler()

PAGE = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>청년다방 리뷰 모니터링</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#18181b;font-family:Arial,"Noto Sans KR",sans-serif}.wrap{max-width:1180px;margin:auto;padding:32px}.head{display:flex;justify-content:space-between;align-items:end;margin-bottom:24px}.head h1{margin:0;font-size:28px}.sub{color:#71717a;margin-top:7px}.card{background:#fff;border:1px solid #e4e4e7;border-radius:18px;padding:20px;box-shadow:0 3px 12px #0000000a}.search{display:grid;grid-template-columns:1fr 1.4fr auto;gap:10px}.search input{padding:14px;border:1px solid #d4d4d8;border-radius:11px;font-size:15px}.btn{border:0;border-radius:11px;background:#18181b;color:white;padding:0 22px;font-weight:700;cursor:pointer}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.metric b{font-size:28px;display:block;margin-top:7px}.muted{font-size:13px;color:#71717a}.grid{display:grid;grid-template-columns:1fr 1.5fr;gap:16px}.status{padding:14px;border-radius:12px;background:#fafafa;margin-top:14px}.review{padding:16px 0;border-bottom:1px solid #eee}.review:last-child{border:0}.bad{background:#fee2e2;color:#b91c1c;border-radius:6px;padding:2px 6px;font-weight:700}.good{background:#dcfce7;color:#166534;border-radius:6px;padding:2px 6px;font-weight:700}.pill{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700}.danger{background:#fee2e2;color:#b91c1c}.warn{background:#fef3c7;color:#92400e}.ok{background:#dcfce7;color:#166534}@media(max-width:760px){.search,.grid,.summary{grid-template-columns:1fr}.btn{padding:14px}.wrap{padding:18px}}
</style></head><body><div class="wrap"><div class="head"><div><h1>청년다방 리뷰 모니터링</h1><div class="sub">매장 검색 → 최신 리뷰 → 불량 키워드 판정</div></div><div class="muted">MVP · 실제 리뷰 객체만 분석</div></div>
<div class="card"><div class="search"><input id="name" value="청년다방" placeholder="매장명"><input id="address" placeholder="주소 또는 지점명 (예: 명동역점)"><button class="btn" onclick="run()">이 매장 검사</button></div><div id="status" class="status">검사할 매장을 입력하세요.</div></div>
<div class="summary"><div class="card metric"><span class="muted">수집 리뷰</span><b id="total">-</b></div><div class="card metric"><span class="muted">불량 리뷰</span><b id="bad">-</b></div><div class="card metric"><span class="muted">주의 리뷰</span><b id="warn">-</b></div><div class="card metric"><span class="muted">정상 리뷰</span><b id="ok">-</b></div></div>
<div class="grid"><div class="card"><b>판정 기준</b><p class="muted">불량 키워드 적중을 우선 반영합니다. 키워드 관리 UI는 다음 단계에서 연결합니다.</p><div id="place" class="status">플레이스 연결 정보가 여기에 표시됩니다.</div></div><div class="card"><b>최신 리뷰</b><div id="reviews" class="muted" style="margin-top:15px">아직 수집하지 않았습니다.</div></div></div></div>
<script>
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function highlight(text,bad,good){let s=esc(text);[...bad].sort((a,b)=>b.length-a.length).forEach(w=>{s=s.replaceAll(esc(w),'<span class="bad">'+esc(w)+'</span>')});[...good].sort((a,b)=>b.length-a.length).forEach(w=>{s=s.replaceAll(esc(w),'<span class="good">'+esc(w)+'</span>')});return s}
async function run(){const status=document.getElementById('status');status.textContent='네이버에서 최신 리뷰를 확인하고 있습니다…';document.getElementById('reviews').textContent='수집 중…';try{const r=await fetch('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('name').value,address:document.getElementById('address').value})});const d=await r.json();if(!r.ok)throw new Error(d.error||'수집 실패');status.textContent='검사 완료';document.getElementById('total').textContent=d.summary.total;document.getElementById('bad').textContent=d.summary.bad;document.getElementById('warn').textContent=d.summary.warn;document.getElementById('ok').textContent=d.summary.ok;document.getElementById('place').innerHTML='<b>'+esc(d.store)+'</b><br><span class="muted">네이버 연결 성공 · 내부 식별값 '+esc(d.place_id)+'</span>';document.getElementById('reviews').innerHTML=d.reviews.map(x=>'<div class="review"><span class="pill '+(x.level==='집중관리'?'danger':x.level==='주의'?'warn':'ok')+'">'+esc(x.level)+'</span><div style="margin:10px 0;line-height:1.7">'+highlight(x.text,x.bad_hits,x.good_hits)+'</div><div class="muted">불량: '+esc(x.bad_hits.join(', ')||'-')+' · 좋은: '+esc(x.good_hits.join(', ')||'-')+(x.created_at?' · '+esc(x.created_at):'')+'</div></div>').join('')}catch(e){status.innerHTML='<b style="color:#b91c1c">수집 실패</b> · '+esc(e.message);document.getElementById('reviews').textContent='실패 원인이 위에 표시되었습니다.'}}
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
        match, reviews, review_url = crawler.fetch_latest_reviews(name, address, limit=30)
    except CrawlError as exc:
        return jsonify(error=str(exc)), 502
    except Exception as exc:
        return jsonify(error=f"예상하지 못한 수집 오류: {type(exc).__name__}: {exc}"), 500

    rows = []
    for review in reviews:
        a = analyze_review(review.text)
        rows.append({
            "id": review.review_id,
            "text": review.text,
            "created_at": review.created_at,
            "rating": review.rating,
            "bad_hits": a.bad_hits,
            "good_hits": a.good_hits,
            "score": a.score,
            "level": a.level,
        })
    summary = {
        "total": len(rows),
        "bad": sum(bool(x["bad_hits"]) for x in rows),
        "warn": sum(x["level"] == "주의" for x in rows),
        "ok": sum(x["level"] == "정상" for x in rows),
    }
    return jsonify(
        store=" ".join(x for x in [name, address] if x),
        place_id=match.place_id,
        review_url=review_url,
        reviews=rows,
        summary=summary,
    )


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
