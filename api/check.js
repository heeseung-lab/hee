import { cors, getText, getPage, extractPlace, balancedJson, walkReviews } from './_lib.js';

const KST_OFFSET_MS=9*60*60*1000;
function kstToday(){const now=new Date(Date.now()+KST_OFFSET_MS);return new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate()));}
function parseReviewDate(value){if(!value)return null;const s=String(value).trim();const today=kstToday();if(s.includes('오늘')||/\d+시간 전/.test(s)||/\d+분 전/.test(s))return today;if(s.includes('어제'))return new Date(today.getTime()-86400000);let m=s.match(/(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})/);if(m)return new Date(Date.UTC(+m[1],+m[2]-1,+m[3]));m=s.match(/(\d{1,2})일 전/);if(m)return new Date(today.getTime()-(+m[1])*86400000);const d=new Date(s);if(!Number.isNaN(d.getTime())){const k=new Date(d.getTime()+KST_OFFSET_MS);return new Date(Date.UTC(k.getUTCFullYear(),k.getUTCMonth(),k.getUTCDate()));}return null;}
function filterByDays(reviews,days){const n=Math.max(1,Math.min(30,Number(days)||7));const start=new Date(kstToday().getTime()-(n-1)*86400000);return reviews.filter(r=>{const d=parseReviewDate(r.created_at);return d&&d>=start;});}

async function resolvePlace(name,address){
  const raw=`${name} ${address||''}`.trim();
  const query=raw.startsWith('청년다방')?raw:`청년다방 ${raw}`;
  const q=encodeURIComponent(query);
  const attempts=[];

  // 1) Naver Map search first. Exact matches often redirect to /p/search/.../place/{placeId}.
  try{
    const map=await getPage(`https://map.naver.com/p/search/${q}`,{headers:{referer:'https://map.naver.com/'}});
    let p=extractPlace(map.url)||extractPlace(map.text);
    if(p)return{...p,resolved_by:'naver-map',source_url:map.url};
    attempts.push('네이버지도: 장소ID 없음');
  }catch(e){attempts.push(`네이버지도: ${String(e.message||e)}`);}

  // 2) A shorter map query can recover stores whose official address text has building/floor suffixes.
  try{
    const shortName=name.startsWith('청년다방')?name:`청년다방 ${name}`;
    const map=await getPage(`https://map.naver.com/p/search/${encodeURIComponent(shortName)}`,{headers:{referer:'https://map.naver.com/'}});
    let p=extractPlace(map.url)||extractPlace(map.text);
    if(p)return{...p,resolved_by:'naver-map-name',source_url:map.url};
    attempts.push('네이버지도(매장명): 장소ID 없음');
  }catch(e){attempts.push(`네이버지도(매장명): ${String(e.message||e)}`);}

  // 3) Legacy integrated search remains only as a fallback.
  try{
    const html=await getText(`https://search.naver.com/search.naver?query=${q}`,{headers:{referer:'https://www.naver.com/'}});
    const p=extractPlace(html);
    if(p)return{...p,resolved_by:'naver-search-fallback',source_url:`https://search.naver.com/search.naver?query=${q}`};
    attempts.push('통합검색 폴백: 장소ID 없음');
  }catch(e){attempts.push(`통합검색 폴백: ${String(e.message||e)}`);}

  throw new Error(`네이버 지도에서 플레이스를 찾지 못했습니다 · ${attempts.join(' / ')}`);
}
async function fetchReviews(p){let last='';for(const type of [...new Set([p.type,'restaurant','place'])]){const url=`https://m.place.naver.com/${type}/${p.id}/review/visitor?reviewSort=recent`;try{const html=await getText(url,{headers:{referer:`https://map.naver.com/p/entry/place/${p.id}`}});const state=balancedJson(html,'window.__APOLLO_STATE__')||balancedJson(html,'__APOLLO_STATE__');if(!state){last='APOLLO_STATE 없음';continue}const rows=walkReviews(state);const seen=new Set();const reviews=[];for(const r of rows){if(seen.has(r.id))continue;seen.add(r.id);reviews.push(r);if(reviews.length>=50)break}if(reviews.length)return{url,reviews};last='구조화 리뷰 객체 없음';}catch(e){last=String(e.message||e)}}throw new Error(last||'리뷰 수집 실패')}
export default async function handler(req,res){cors(res);if(req.method==='OPTIONS')return res.status(204).end();if(!['GET','POST'].includes(req.method))return res.status(405).json({ok:false,error:'GET/POST only'});try{const body=req.method==='GET'?req.query:(typeof req.body==='string'?JSON.parse(req.body||'{}'):(req.body||{}));const name=String(body.name||'').trim(),address=String(body.address||'').trim(),days=Math.max(1,Math.min(30,Number(body.days)||7));if(!name)return res.status(400).json({ok:false,error:'매장명이 없습니다',example:'/api/check?name=청년다방%20명동역점&days=7'});const p=await resolvePlace(name,address);const result=await fetchReviews(p);const reviews=filterByDays(result.reviews,days);return res.status(200).json({ok:true,store:name,address,place_id:p.id,resolved_by:p.resolved_by,map_url:p.source_url,review_url:result.url,window_days:days,count:reviews.length,reviews});}catch(e){return res.status(502).json({ok:false,error:String(e.message||e)});}}
