'use strict';
const library={posts:[],cursor:null,loaded:false,loading:false,error:'',owned:[],request:0};
let librarySearchTimer;
function compatibleHardware(h){return !!state&&['model','cpu','gpu'].every(k=>h?.[k]&&JSON.stringify(h[k])===JSON.stringify(state.hardware[k]));}
const productAliases=[
  {models:['GU605CX','GU605CW','GU605CR','GU605CM'],family:'ROG 제피러스 G16',english:'ROG Zephyrus G16',year:'2025'},
  {models:['GU605MI','GU605MY','GU605MZ'],family:'ROG 제피러스 G16',english:'ROG Zephyrus G16',year:'2024'},
  {models:['GA403UI'],family:'ROG 제피러스 G14',english:'ROG Zephyrus G14',year:'2024'},
  {models:['GZ302EA'],family:'ROG 플로우 Z13',english:'ROG Flow Z13',year:'2025'}
];
function productAlias(h){return productAliases.find(entry=>entry.models.includes(String(h?.model||'').toUpperCase()));}
function shortGpu(h){
  const values=Array.isArray(h?.gpu)?h.gpu:typeof h?.gpu==='string'?[h.gpu]:[];
  const name=values.find(x=>/NVIDIA/i.test(x))||values.find(x=>/AMD Radeon/i.test(x))||values[0]||'';
  const match=name.match(/\b(?:RTX|GTX)\s*\d{4}\s*(?:Ti)?/i)||name.match(/\bRadeon\s+(?:RX\s+)?[\w+]+/i);
  return match?.[0]?.replace(/\s+/g,' ').trim()||name.replace(/^(?:NVIDIA|AMD)\s+/i,'').replace(/\s+(?:Laptop GPU|Graphics)$/i,'').trim();
}
function displayHardware(h){
  const alias=productAlias(h),model=alias?alias.family+' '+alias.year:(h?.model||'모델 정보 없음');
  const specs=[model,shortGpu(h),h?.ram_gb?number(h.ram_gb)+' GB':'' ].filter(Boolean);
  return specs.join(' \u00b7 ');
}
function searchTokens(value){
  return value.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/([a-z])(?=\d)|(?<=\d)(?=[a-z])/gi,' ').replace(/[^\p{L}\p{N}]+/gu,' ').trim().split(/\s+/).filter(Boolean);
}
function searchableHardware(h){
  const alias=productAlias(h),gpus=Array.isArray(h?.gpu)?h.gpu:typeof h?.gpu==='string'?[h.gpu]:[];
  const specs=gpus.flatMap(gpu=>{const match=gpu.match(/\b(RTX|GTX)\s*(\d{4})\s*(Ti)?/i);return match?[match[1],match[2],match[3]]:[gpu];});
  return [h?.model,h?.cpu,...specs,...gpus,h?.ram_gb&&number(h.ram_gb)+' GB',alias?.family,alias?.english,alias?.year,'Zephyrus','제피러스','제피루스'].filter(Boolean).join(' ').normalize('NFKC').toLocaleLowerCase('ko-KR');
}
function scheduleLibraryLoad(){if(state&&!library.loaded&&!library.loading)loadLibrary();}
async function loadLibrary(more=false){
  const request=++library.request,filter=$('library-search').value.trim(),modelFilter=$('library-compatible').checked&&state?.hardware.model?state.hardware.model:'';
  library.loading=true;library.error='';renderLibrary();
  try{
    const query=new URLSearchParams();
    if(modelFilter)query.set('model',modelFilter);
    if(filter)query.set('q',filter);
    if(more&&library.cursor)query.set('cursor',library.cursor);
    const result=await api('/api/community/browse?'+query);
    if(request!==library.request)return;
    const old=more?library.posts:[];
    const ids=new Set(old.map(p=>p.id));
    library.posts=old.concat(result.posts.filter(p=>!ids.has(p.id)));
    library.cursor=result.nextCursor||null;library.loaded=true;
  }catch(e){if(request===library.request)library.error=e.message||'자료실을 불러오지 못했어요.';}
  finally{if(request===library.request){library.loading=false;renderLibrary();await loadOwned();}}
}
function scoreStrip(runs){
  const strip=node('div',null,'score-strip');
  for(const mode of [2,0,1]){
    const r=[...(runs||[])].filter(r=>r.mode===mode).sort((a,b)=>String(b.createdAt).localeCompare(String(a.createdAt)))[0];
    const cell=node('div');cell.append(node('small',modeName(mode)),node('small','그래픽 점수'),node('strong',r?number(r.graphicsScore)+'점':'—'),node('small',r?'CPU 점수 '+number(r.cpuScore)+'점':'CPU 점수 —'));
    cell.append(node('small',r?(r.noiseDbA==null?'소음 미입력':r.noiseDbA+' dBA'):'점수 없음'));
    if(r?.notes?.startsWith('[직접 연결 · 측정 당시 설정 미검증]'))cell.append(node('small','사용자가 직접 설정 연결'));
    if(r?.fanRpm!=null)cell.append(node('small',number(r.fanRpm)+' RPM'));
    strip.append(cell);
  }
  return strip;
}
function renderLibrary(){
  const list=$('library-list');if(!list)return;
  $('library-refresh').disabled=library.loading;
  $('library-compatible').disabled=library.loading;
  $('library-more').disabled=library.loading;
  $('library-more').hidden=!library.cursor;
  const q=$('library-search').value.trim(),tokens=searchTokens(q),matching=$('library-compatible').checked;
  const posts=library.posts.filter(p=>(!matching||compatibleHardware(p.profile?.hardware))&&tokens.every(token=>[p.profile?.name,p.profile?.hardware?.model,p.author,p.profile?.notes,searchableHardware(p.profile?.hardware)].join(' ').normalize('NFKC').toLocaleLowerCase('ko-KR').includes(token)));
  const signature=JSON.stringify([posts,matching,q,library.error,library.loaded,library.loading,!!library.cursor]);
  $('library-status').textContent=library.loading?'설정을 불러오고 있어요…':library.error||posts.length+'개 · 점수와 소음은 사용자가 공유한 기록입니다.';
  if(cache.libraryCards===signature)return;cache.libraryCards=signature;list.replaceChildren();
  if(!posts.length){
    const empty=node('div',null,'empty library-empty');
    const title=library.error?'지금 자료실에 연결할 수 없어요':library.loading?'자료실을 확인하고 있어요':q?'검색 결과가 없어요':matching?'내 사양으로 공유된 설정이 아직 없어요':'아직 공유된 설정이 없어요';
    empty.append(node('strong',title));
    empty.append(node('p',library.error?'잠시 후 새로고침해 주세요. 저장해 둔 내 설정은 계속 사용할 수 있습니다.':matching?'기종·CPU·GPU가 같은 설정만 보여드리고 있습니다.': '내 설정을 공유하면 다른 사용자가 이곳에서 바로 적용할 수 있어요.'));
    if(matching&&!library.error&&!library.loading){const all=button('다른 기종도 둘러보기',()=>{$('library-compatible').checked=false;resetLibraryFilter();});empty.append(all);}
    list.append(empty);
  }
  for(const post of posts){
    const p=post.profile,h=p.hardware,card=node('article',null,'library-card');
    const title=node('div',null,'row between');title.append(node('h3',p.name),pill(compatibleHardware(h)?'내 사양과 같음':'다른 사양',compatibleHardware(h)?'good':''));
    card.append(title,node('p',displayHardware(h),'device-spec-title'),node('p',[h.model,h.cpu,post.author].filter(Boolean).join(' · '),'small muted'),node('p',p.notes||'설정 메모 없음','card-note'),scoreStrip(post.runs));
    const view=button('설정 보기 · 적용',()=>act(view,()=>openCommunityPost(post.id)),'btn secondary');card.append(view);list.append(card);
  }
}
async function openCommunityPost(id){
  const {post}=await api('/api/community/post?id='+encodeURIComponent(id));
  const p=post.profile,h=p.hardware,body=node('div',null,'stack'),compatible=compatibleHardware(h);
  body.append(node('p',post.author+' · '+date(post.createdAt),'small muted'),detailsList([['제품명',displayHardware(h)],['모델 코드',h.model],['CPU',h.cpu],['GPU',(h.gpu||[]).join(' / ')]]));
  if(p.notes)body.append(node('p',p.notes));
  if(!compatible)body.append(notice('내 노트북과 기종·CPU·GPU가 달라 적용할 수 없어요.','warn'));
  body.append(scoreStrip(post.runs),node('p','사용자가 공유한 기록입니다. 같은 설정도 사용 환경에 따라 결과가 달라집니다.','small muted'));
  const visual=node('div');body.append(visual);ProfileSettings.render(visual,p.settings,h,{mode:p.activeMode??0});
  openModal(p.name,body,compatible?'이 설정 사용':'',compatible?async()=>{
    if(isActive())throw Error('성능 비교를 마친 뒤 적용해 주세요.');
    const local=await api('/api/community/import',{id});
    await refresh();await openApply(local);return false;
  }:null);
}
async function loadOwned(){
  try{const result=await api('/api/community/owned');library.owned=result.posts||[];renderOwned();}
  catch(e){$('owned-list').replaceChildren(notice(e.message,'warn'));}
}
function renderOwned(){
  memo('owned-list',library.owned,target=>{
    if(!library.owned.length){target.append(node('p','이 컴퓨터에서 공유한 설정이 아직 없어요.','small muted'));return;}
    for(const post of library.owned){
      const row=node('div',null,'saved-row'),info=node('div',null,'saved-main');
      info.append(node('strong',post.name||'내 공유 설정'),node('p',post.id?'자료실에 게시됨':'연결 확인이 필요한 업로드','small muted'));row.append(info);
      if(post.id){
        const del=button('게시 취소',()=>{
          openModal('공유한 설정을 내릴까요?',node('p','자료실에서 이 게시물을 삭제합니다. 이 컴퓨터에 저장한 설정은 남습니다.'),'게시물 삭제',async()=>{
            await api('/api/community/delete',{id:post.id});await loadOwned();await loadLibrary();showToast('자료실에서 게시물을 내렸어요.');
          });
        },'btn text');row.append(del);
      }else{
        const retry=button('업로드 다시 확인',()=>act(retry,async()=>{
          await api('/api/community/retry',{requestId:post.requestId});await loadOwned();await loadLibrary();showToast('게시를 확인했어요.');
        }),'btn secondary');row.append(retry);
      }
      target.append(row);
    }
  });
}
async function openPublish(){
  if(!(state.profiles||[]).length){
    openModal('공유할 설정을 먼저 저장해 주세요',node('p','지금 사용 중인 설정을 저장하면 노트북 사양과 함께 공유할 수 있어요.'),'현재 설정 저장',async()=>{
      await saveCurrent();await openPublish();return true;
    });return;
  }
  await loadOwned();
  if(library.owned.some(p=>!p.id)){
    openModal('이전 업로드를 먼저 확인해 주세요',node('p','연결이 끊긴 업로드가 있습니다. 중복으로 올리지 않도록 「내가 공유한 설정」에서 다시 확인해 주세요.'),'업로드 확인하기',async()=>{$('owned-details').open=true;$('owned-details').scrollIntoView({behavior:'smooth',block:'center'});});return;
  }
  renderCommunity();$('publish-modal').showModal();
}
async function prepareShare(){
  const p=state.profiles.find(p=>p.id===$('public-profile').value);
  if(!p)throw Error('공유할 설정을 먼저 저장해 주세요.');
  const profileId=p.id,runIds=[...publicSelection],author=$('public-author').value.trim()||'익명';
  const payload=await api('/api/community/prepare',{profileId,runIds,author});
  const body=node('div',null,'stack');
  body.append(node('p','아래 내용을 공개 자료실에 올립니다.'),detailsList([['설정',payload.profile.name],['작성자',payload.author],['제품명',displayHardware(payload.profile.hardware)],['모델 코드',payload.profile.hardware.model],['함께 올릴 점수',payload.runs.length+'개'],['메모',payload.profile.notes||'없음']]));
  if(payload.runs.length)body.append(scoreStrip(payload.runs));
  if(payload.runs.some(r=>r.notes?.startsWith('[직접 연결 · 측정 당시 설정 미검증]')))body.append(notice('직접 연결한 점수는 측정 당시 설정을 앱에서 검증하지 못했습니다. 게시물의 측정 메모에 이 사실이 표시됩니다.'));
  for(const r of payload.runs)if(r.notes)body.append(node('p',modeName(r.mode)+' 측정 메모: '+r.notes,'small'));
  body.append(notice('공개하고 싶지 않은 이름이나 메모가 없는지 확인해 주세요.'));
  const visual=node('div');body.append(detail('공유할 설정 보기',visual));ProfileSettings.render(visual,payload.profile.settings,payload.profile.hardware,{mode:payload.profile.activeMode??0,compact:true});
  body.append(detail('공개되는 전체 내용',node('pre',JSON.stringify(payload,null,2),'code')));
  $('publish-modal').close();
  const requestId=crypto.randomUUID();
  openModal('이 내용을 공유할까요?',body,'자료실에 게시',async()=>{
    try{
      await api('/api/community/publish',{profileId,runIds,author,requestId});
      library.loaded=false;await loadLibrary();
      openModal('자료실에 올렸어요',node('p','다른 사용자가 프로그램 안에서 확인하고 적용할 수 있습니다. 「내가 공유한 설정」에서 게시를 취소할 수 있어요.'));return false;
    }catch(e){await loadOwned();throw e;}
  });
}
function initLibrary(){
  $('library-refresh').addEventListener('click',()=>loadLibrary());
  $('library-more').addEventListener('click',()=>loadLibrary(true));
  $('library-search').addEventListener('input',()=>{clearTimeout(librarySearchTimer);catalogVisible=18;renderCatalog();if($('library-search').value.trim())$('catalog-details').open=true;renderLibrary();librarySearchTimer=setTimeout(()=>{library.posts=[];library.cursor=null;library.loaded=false;loadLibrary();},350);});
  $('library-compatible').addEventListener('change',resetLibraryFilter);
  $('open-publish').addEventListener('click',()=>openPublish().catch(report));
  $('publish-close').addEventListener('click',()=>$('publish-modal').close());
  $('owned-details').addEventListener('toggle',()=>{if($('owned-details').open)loadOwned();});
}
function resetLibraryFilter(){library.posts=[];library.cursor=null;library.loaded=false;loadLibrary();}
