import os
import threading

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

from app.auth import admin_required, authenticate, create_user, init_auth, list_users, login_required
from app.batch import run_all
from app.db import (
    dashboard_summary,
    get_keywords,
    init_db,
    list_stores,
    recent_reviews,
    reanalyze_all,
    replace_keywords,
    set_review_action,
    upsert_store,
)
from app.naver_crawler import CrawlError
from app.review_analyzer import analyze_review
from app.service import inspect_store

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1")
init_db()
init_auth()
_collect_lock = threading.Lock()

LOGIN_PAGE = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>로그인</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f6f8;font-family:Arial,"Noto Sans KR",sans-serif;color:#18181b}.box{max-width:420px;margin:12vh auto;background:#fff;border:1px solid #e4e4e7;border-radius:20px;padding:30px}.box h1{margin:0 0 8px}.muted{color:#71717a}.field{margin-top:16px}.field input{width:100%;padding:13px;border:1px solid #d4d4d8;border-radius:11px;font-size:15px}.btn{margin-top:18px;width:100%;padding:13px;border:0;border-radius:11px;background:#18181b;color:#fff;font-weight:700}.err{color:#b91c1c;margin-top:12px}</style></head><body><div class="box"><h1>청년다방 리뷰 모니터링</h1><div class="muted">본사/운영 담당자 로그인</div><form method="post"><div class="field"><input name="username" placeholder="아이디" required></div><div class="field"><input name="password" type="password" placeholder="비밀번호" required></div><button class="btn">로그인</button>{% if error %}<div class="err">{{ error }}</div>{% endif %}</form></div></body></html>'''

PAGE = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>청년다방 리뷰 모니터링</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#18181b;font-family:Arial,"Noto Sans KR",sans-serif}.wrap{max-width:1280px;margin:auto;padding:26px}.head{display:flex;justify-content:space-between;gap:16px;align-items:flex-end}.head h1{margin:0;font-size:28px}.muted{color:#71717a;font-size:13px}.card{background:#fff;border:1px solid #e4e4e7;border-radius:18px;padding:17px}.summary{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:16px 0}.metric b{display:block;font-size:25px;margin-top:5px}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.btn{border:0;border-radius:10px;padding:10px 14px;background:#18181b;color:#fff;font-weight:700;cursor:pointer}.btn.alt{background:#fff;color:#18181b;border:1px solid #d4d4d8}.search{display:grid;grid-template-columns:1fr 1.5fr auto auto;gap:8px}.search input,textarea,select{border:1px solid #d4d4d8;border-radius:10px;padding:11px;font-size:14px;width:100%}.status{margin-top:10px;padding:11px;border-radius:10px;background:#fafafa}.layout{display:grid;grid-template-columns:1fr 1.35fr;gap:14px;margin-top:14px}.tabs{display:flex;gap:8px;margin-top:14px}.tabs button{border:1px solid #d4d4d8;background:#fff;border-radius:999px;padding:8px 12px}.tabs .active{background:#18181b;color:#fff}.row,.review{padding:13px 0;border-bottom:1px solid #eee}.bad{background:#fee2e2;color:#b91c1c;padding:2px 5px;border-radius:5px;font-weight:700}.good{background:#dcfce7;color:#166534;padding:2px 5px;border-radius:5px;font-weight:700}.pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700}.danger{background:#fee2e2;color:#b91c1c}.warn{background:#fef3c7;color:#92400e}.ok{background:#dcfce7;color:#166534}.hidden{display:none}.action{display:grid;grid-template-columns:120px 1fr 1.5fr auto;gap:7px;margin-top:10px}.fail{color:#b91c1c}.toplink{color:#18181b;text-decoration:none;border:1px solid #d4d4d8;border-radius:9px;padding:8px 10px;background:#fff}@media(max-width:850px){.summary,.layout,.search,.action{grid-template-columns:1fr}.wrap{padding:15px}}</style></head><body><div class="wrap"><div class="head"><div><h1>청년다방 리뷰 모니터링</h1><div class="muted">최신 리뷰 수집 · 불량언어 체크 · 미조치 리뷰 집중관리</div></div><div class="toolbar"><span class="muted">{{ user.username }} · {{ user.role }}</span><a class="toplink" href="/logout">로그아웃</a></div></div><div class="summary"><div class="card metric"><span class="muted">등록 매장</span><b id="mStores">-</b></div><div class="card metric"><span class="muted">누적 리뷰</span><b id="mReviews">-</b></div><div class="card metric"><span class="muted">불량 리뷰</span><b id="mBad">-</b></div><div class="card metric"><span class="muted">미조치 불량</span><b id="mOpen">-</b></div><div class="card metric"><span class="muted">집중관리 매장</span><b id="mCritical">-</b></div><div class="card metric"><span class="muted">주의 매장</span><b id="mWarning">-</b></div></div><div class="card"><div class="search"><input id="name" value="청년다방" placeholder="매장명"><input id="address" placeholder="주소 또는 지점명"><button id="checkBtn" class="btn">이 매장 검사</button><button id="allBtn" class="btn alt">전체 검사</button></div><div id="status" class="status">실제 리뷰 수집 결과와 오류를 여기서 확인합니다.</div></div><div class="tabs"><button class="active" data-tab="stores">매장 현황</button><button data-tab="reviews">최신 리뷰</button><button data-tab="keywords">키워드 설정</button><button data-tab="users">사용자</button></div><div id="tab-stores" class="layout"><div class="card"><b>위험 매장 우선순위</b><div id="stores"></div></div><div class="card"><b>선택 매장 검사 결과</b><div id="checked" class="muted" style="margin-top:10px">아직 검사하지 않았습니다.</div></div></div><div id="tab-reviews" class="card hidden"><b>미조치 불량 우선 최신 리뷰</b><div id="recent"></div></div><div id="tab-keywords" class="layout hidden"><div class="card"><b>불량언어</b><textarea id="badWords" rows="14"></textarea><button class="btn alt" data-save="bad" style="margin-top:8px">저장 + 전체 재분석</button></div><div class="card"><b>좋은언어</b><textarea id="goodWords" rows="14"></textarea><button class="btn alt" data-save="good" style="margin-top:8px">저장 + 전체 재분석</button></div></div><div id="tab-users" class="card hidden"><b>공유 사용자 관리</b><div id="users" class="muted" style="margin:10px 0">관리자만 추가할 수 있습니다.</div><div class="search"><input id="newUser" placeholder="아이디"><input id="newPass" type="password" placeholder="비밀번호 8자 이상"><select id="newRole"><option value="viewer">viewer</option><option value="manager">manager</option><option value="admin">admin</option></select><button id="addUser" class="btn">사용자 추가</button></div></div></div><script>const $=id=>document.getElementById(id);function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}function split(s){return (s||'').split(',').filter(Boolean)}function hl(text,bad,good){let s=esc(text);[...bad].sort((a,b)=>b.length-a.length).forEach(w=>s=s.replaceAll(esc(w),'<span class="bad">'+esc(w)+'</span>'));[...good].sort((a,b)=>b.length-a.length).forEach(w=>s=s.replaceAll(esc(w),'<span class="good">'+esc(w)+'</span>'));return s}function badge(l){return '<span class="pill '+(l==='집중관리'?'danger':l==='주의'?'warn':'ok')+'">'+esc(l)+'</span>'}async function api(u,o){const r=await fetch(u,o);const d=await r.json();if(!r.ok)throw new Error(d.error||'요청 실패');return d}function reviewHtml(x){return '<div class="review">'+badge(x.level)+' <b>'+esc(x.store_name||'')+'</b><div style="margin:8px 0;line-height:1.7">'+hl(x.body||x.text,split(x.bad_hits),split(x.good_hits))+'</div><div class="muted">불량 '+esc(x.bad_hits||'-')+' · 좋은 '+esc(x.good_hits||'-')+' · 점수 '+(x.score||0)+'</div>'+(x.id?'<div class="action"><select data-st="'+x.id+'"><option value="open" '+(x.action_status==='open'?'selected':'')+'>미조치</option><option value="in_progress" '+(x.action_status==='in_progress'?'selected':'')+'>조치중</option><option value="done" '+(x.action_status==='done'?'selected':'')+'>완료</option></select><input data-as="'+x.id+'" value="'+esc(x.assignee||'')+'" placeholder="담당자"><input data-me="'+x.id+'" value="'+esc(x.action_memo||'')+'" placeholder="조치 메모"><button class="btn alt" data-action="'+x.id+'">저장</button></div>':'')+'</div>'}async function refresh(){const [s,stores,reviews,keys]=await Promise.all([api('/api/summary'),api('/api/stores'),api('/api/reviews?limit=120'),api('/api/keywords')]);$('mStores').textContent=s.stores;$('mReviews').textContent=s.reviews;$('mBad').textContent=s.bad_reviews;$('mOpen').textContent=s.open_bad_reviews;$('mCritical').textContent=s.critical_stores;$('mWarning').textContent=s.warning_stores;$('stores').innerHTML=stores.map(x=>'<div class="row"><b>'+esc(x.name)+'</b><div class="muted">'+esc(x.address||'')+'</div><div class="muted">리뷰 '+x.review_count+' · 불량 '+(x.bad_review_count||0)+' · 미조치 '+(x.open_bad_count||0)+' · 상태 '+esc(x.last_status)+(x.last_error?' · <span class="fail">'+esc(x.last_error)+'</span>':'')+'</div></div>').join('')||'등록 매장이 없습니다.';$('recent').innerHTML=reviews.map(reviewHtml).join('')||'아직 리뷰가 없습니다.';$('badWords').value=keys.bad.join('\n');$('goodWords').value=keys.good.join('\n');bindActions();loadUsers()}function bindActions(){document.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{const id=b.dataset.action;await api('/api/reviews/'+id+'/action',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:document.querySelector('[data-st="'+id+'"]').value,assignee:document.querySelector('[data-as="'+id+'"]').value,memo:document.querySelector('[data-me="'+id+'"]').value})});$('status').textContent='조치 상태를 저장했습니다.';refresh()})}async function loadUsers(){try{const u=await api('/api/users');$('users').innerHTML=u.map(x=>esc(x.username)+' · '+esc(x.role)).join('<br>')}catch(e){$('users').textContent='관리자 계정에서만 사용자 목록을 볼 수 있습니다.'}}$('checkBtn').onclick=async()=>{try{$('status').textContent='네이버 최신 리뷰 수집 중…';const d=await api('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('name').value,address:$('address').value})});$('status').textContent='완료 · 신규 '+d.new_reviews+'건';$('checked').innerHTML=d.reviews.map(x=>reviewHtml({...x,body:x.text})).join('');refresh()}catch(e){$('status').innerHTML='<span class="fail">수집 실패 · '+esc(e.message)+'</span>'}};$('allBtn').onclick=async()=>{try{const d=await api('/api/run-all',{method:'POST'});$('status').textContent=d.message}catch(e){$('status').textContent=e.message}};document.querySelectorAll('[data-save]').forEach(b=>b.onclick=async()=>{const kind=b.dataset.save;const text=(kind==='bad'?$('badWords'):$('goodWords')).value;const d=await api('/api/keywords/'+kind,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({words:text.split(/\n/).map(x=>x.trim()).filter(Boolean)})});$('status').textContent='저장 완료 · 기존 리뷰 '+d.reanalyzed+'건 재분석';refresh()});$('addUser').onclick=async()=>{try{await api('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('newUser').value,password:$('newPass').value,role:$('newRole').value})});$('newPass').value='';loadUsers()}catch(e){$('status').textContent=e.message}};document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));b.classList.add('active');['stores','reviews','keywords','users'].forEach(t=>$('tab-'+t).classList.toggle('hidden',t!==b.dataset.tab))});refresh().catch(e=>$('status').textContent=e.message)</script></body></html>'''


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = authenticate(request.form.get("username", ""), request.form.get("password", ""))
        if user:
            session["user"] = user
            return redirect(url_for("dashboard"))
        return render_template_string(LOGIN_PAGE, error="아이디 또는 비밀번호가 올바르지 않습니다"), 401
    return render_template_string(LOGIN_PAGE, error=None)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    return render_template_string(PAGE, user=session["user"])


@app.post("/api/check")
@login_required
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
@login_required
def summary_api():
    return jsonify(dashboard_summary())


@app.get("/api/stores")
@login_required
def stores_api():
    return jsonify(list_stores())


@app.post("/api/stores")
@login_required
def add_store_api():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    address = (payload.get("address") or "").strip()
    if not name:
        return jsonify(error="매장명이 필요합니다"), 400
    return jsonify(id=upsert_store(name, address)), 201


@app.get("/api/reviews")
@login_required
def reviews_api():
    limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    return jsonify(recent_reviews(limit))


@app.put("/api/reviews/<int:review_id>/action")
@login_required
def review_action_api(review_id):
    payload = request.get_json(silent=True) or {}
    try:
        set_review_action(review_id, payload.get("status", "open"), payload.get("memo", ""), payload.get("assignee", ""), session["user"]["username"])
    except (ValueError, KeyError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True)


@app.get("/api/keywords")
@login_required
def keywords_api():
    return jsonify(get_keywords())


@app.put("/api/keywords/<kind>")
@login_required
def keywords_update_api(kind):
    payload = request.get_json(silent=True) or {}
    words = payload.get("words") or []
    if not isinstance(words, list):
        return jsonify(error="words는 배열이어야 합니다"), 400
    try:
        replace_keywords(kind, words)
        count = reanalyze_all(analyze_review)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(keywords=get_keywords(), reanalyzed=count)


@app.get("/api/users")
@admin_required
def users_api():
    return jsonify(list_users())


@app.post("/api/users")
@admin_required
def users_create_api():
    payload = request.get_json(silent=True) or {}
    try:
        create_user(payload.get("username", ""), payload.get("password", ""), payload.get("role", "viewer"))
    except Exception as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True), 201


@app.post("/api/run-all")
def run_all_api():
    token = request.headers.get("X-Job-Token", "")
    logged_in = bool(session.get("user"))
    expected = os.getenv("JOB_TOKEN", "")
    if not logged_in and (not expected or token != expected):
        return jsonify(error="unauthorized"), 401
    if not _collect_lock.acquire(blocking=False):
        return jsonify(message="이미 전체 수집이 실행 중입니다"), 202
    def worker():
        try:
            run_all()
        finally:
            _collect_lock.release()
    threading.Thread(target=worker, daemon=True).start()
    return jsonify(message="전체 매장 수집을 시작했습니다"), 202


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
