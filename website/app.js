// v23: published MongoDB content only; no demo titles or fake chapters.
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const small=s=>String(s).replace(/[a-z]/gi,c=>({a:'ᴀ',b:'ʙ',c:'ᴄ',d:'ᴅ',e:'ᴇ',f:'ғ',g:'ɢ',h:'ʜ',i:'ɪ',j:'ᴊ',k:'ᴋ',l:'ʟ',m:'ᴍ',n:'ɴ',o:'ᴏ',p:'ᴘ',q:'ǫ',r:'ʀ',s:'s',t:'ᴛ',u:'ᴜ',v:'ᴠ',w:'ᴡ',x:'x',y:'ʏ',z:'ᴢ'}[c.toLowerCase()]||c));
const names={manga:'Manga',manhwa:'Manhwa',webtoon:'Webtoon',manhua:'Manhua',adult_manga:'18+ Manga',adult_manhwa:'18+ Manhwa',adult_webtoon:'18+ Webtoon'};
let state={page:1,filter:'',query:'',user:null,items:[],loading:false,genres:[]};
let genrePanelOpen=false;
let genreDraft=new Set();
const genreCache=new Map();
let catalogRequest=0;
let readerRequest=0;
const cover=x=>(x.has_cover||x.cover_url)
 ? `<img class="cover-art" loading="lazy" decoding="async" src="/api/cover?category=${encodeURIComponent(x.category)}&slug=${encodeURIComponent(x.slug)}" alt="Cover artwork for ${esc(x.title)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="cover-placeholder" hidden>MIKO</span>`
 : '<span class="cover-placeholder">MIKO</span>';
function card(x){const fresh=x.updated_at&&Date.now()-Date.parse(x.updated_at)<86400000;const genres=[...new Set([...(Array.isArray(x.genres)?x.genres:[]),...(Array.isArray(x.tags)?x.tags:[])].filter(v=>typeof v==='string'))].slice(0,3);return `<a class="card" href="#/title/${esc(x.category)}/${encodeURIComponent(x.slug)}"><div class="cover">${cover(x)}${fresh?'<span class="new-label">NEW</span>':''}</div><div class="card-info"><h3>${esc(x.title)}</h3><div class="meta">${small(names[x.category]||x.category)} · ${x.chapters?.length||0} ${small('chapters')}</div>${genres.length?`<div class="card-genres">${genres.map(g=>`<span>${esc(g)}</span>`).join('')}</div>`:''}</div></a>`}
// Retry interrupted GET requests, but never repeat a login or registration POST.
// Reader jobs run on the server, so retrying a GET only checks their status.
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(path,opts={}){
 const {retries=0,timeoutMs=15000,...request}=opts;
 const canRetry=(!request.method || request.method.toUpperCase()==='GET');
 const maxRetries=canRetry?Math.min(3,Math.max(0,retries)):0;
 for(let attempt=0;attempt<=maxRetries;attempt++){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  let r;
  try{
   r=await fetch('/api/'+path,{credentials:'same-origin',...request,signal:controller.signal});
  }catch(err){
   clearTimeout(timer);
   if(attempt<maxRetries){await wait(750*(attempt+1));continue;}
   const msg=location.protocol==='http:'
    ? 'Secure connection required. Open the HTTPS website.'
    : 'Connection interrupted. Tap Retry to continue reading.';
   throw Error(msg);
  }
  clearTimeout(timer);
  let d;
  try{d=await r.json();}
  catch(err){
   if(attempt<maxRetries && [502,503,504].includes(r.status)){
    await wait(750*(attempt+1));continue;
   }
   throw Error('Website API returned an invalid response (HTTP '+r.status+').');
  }
  if(!r.ok){
   if(attempt<maxRetries && [429,502,503,504].includes(r.status)){
    await wait(750*(attempt+1));continue;
   }
   const error=Error(d.error||'Request failed (HTTP '+r.status+').');
   error.httpStatus=r.status;
   error.code=d.code||'';
   throw error;
  }
  return d;
 }
 throw Error('Reader request was interrupted.');
}
function pager(total){if(total<=1)return '';return `<div class="pager"><button ${state.page<=1?'disabled':''} data-page="${state.page-1}">${small('Previous')}</button><b>${state.page} / ${total}</b><button ${state.page>=total?'disabled':''} data-page="${state.page+1}">${small('Next')}</button></div>`}
// v56: permanent AniList core genres + common manga themes (not title metadata).
// Selected choices still match real published-record genres OR tags only.
function genreControlMarkup(category, options=[], warning='', panelId='homeGenrePanel', coreGenres=[]){
 const active=state.genres.length;
 const values=[...new Set([...options,...genreDraft])].sort((a,b)=>a.localeCompare(b));
 const core=new Set(coreGenres.map(s=>s.toLowerCase()));
 const draw=(names,label)=>names.length?`<div class="genre-choice-group"><h4>${esc(label)} <span>${names.length}</span></h4><div class="genre-choice-group-items">${names.map(genre=>{
  const index=values.indexOf(genre);
  return `<label class="genre-choice${genreDraft.has(genre)?' checked':''}"><input type="checkbox" data-genre-index="${index}" ${genreDraft.has(genre)?'checked':''}><span>${esc(genre)}</span></label>`;
 }).join('')}</div></div>`:'';
 const coreNames=values.filter(n=>core.has(n.toLowerCase()));
 const otherNames=values.filter(n=>!core.has(n.toLowerCase()));
 const tags=draw(coreNames,'AniList genres')+draw(otherNames,'Themes & more');
 return `<div class="genre-filter-bar"><button type="button" class="genre-open" aria-expanded="${genrePanelOpen}" aria-controls="${panelId}">☷ ${small('Genres')} ${active?`<strong>${active}</strong>`:''}<span class="genre-chevron">${genrePanelOpen?'−':'+'}</span></button>${active?`<span class="genre-active-summary">${state.genres.map(esc).join(' · ')}</span><button class="genre-quick-clear" type="button">${small('Clear')}</button>`:`<span class="genre-helper">${small('Select multiple genres')}</span>`}</div>
 <div class="genre-panel" id="${panelId}" ${genrePanelOpen?'':'hidden'}><div class="genre-panel-intro"><h3>${small('Choose genres & themes')}</h3><p>Match ANY selected genre or theme (OR). Up to 16 selections. Only published titles with matching metadata appear.</p></div><label class="genre-search-label"><span>⌕</span><input type="search" placeholder="Search Action, Isekai, School Life…" autocomplete="off" aria-label="Find genre"></label>
 <div class="genre-choice-list">${tags||`<p class="genre-empty">${small(warning||'Genres are loading…')}</p>`}</div><p class="genre-limit" role="status" hidden>Choose up to 16 genres.</p><div class="genre-buttons"><button type="button" class="genre-apply">${small('Apply filters')} (${genreDraft.size})</button><button type="button" class="genre-clear">${small('Clear all')}</button></div>${warning&&tags?`<p class="genre-warning">${esc(warning)}</p>`:''}</div>`;
}
function renderGenreControls(category,warning=''){
 const mount=document.querySelector('#routePage:not([hidden]) .genre-mount') || document.querySelector('#homeContent:not([hidden]) .genre-mount');
 if(!mount)return;
 const inside=selector=>mount.querySelector(selector);
 const cached=genreCache.get(category||'all');
 const options=cached?.genres||[];
 const values=[...new Set([...options,...genreDraft])].sort((a,b)=>a.localeCompare(b));
 mount.innerHTML=genreControlMarkup(category,options,warning||(!cached?'Loading available genres...':''),mount.closest('#routePage')?'categoryGenrePanel':'homeGenrePanel',cached?.anilist_genres||[]);
 inside('.genre-open').onclick=()=>{genrePanelOpen=!genrePanelOpen;genreDraft=new Set(state.genres);renderGenreControls(category,warning)};
 const quick=inside('.genre-quick-clear');
 if(quick)quick.onclick=()=>{state.genres=[];genreDraft=new Set();state.page=1;genrePanelOpen=false;loadCatalog()};
 const panel=inside('.genre-panel');
 if(!genrePanelOpen)return;
 panel.querySelectorAll('[data-genre-index]').forEach(input=>{
  input.onchange=()=>{
   const genre=values[Number(input.dataset.genreIndex)];
   if(input.checked && genreDraft.size>=16){input.checked=false;inside('.genre-limit').hidden=false;return;}
   inside('.genre-limit').hidden=true;
   if(input.checked)genreDraft.add(genre);else genreDraft.delete(genre);
   input.closest('.genre-choice').classList.toggle('checked',input.checked);
   inside('.genre-apply').textContent=small('Apply filters')+` (${genreDraft.size})`;
  };
 });
 inside('.genre-search-label input').oninput=e=>{
  const needle=e.target.value.trim().toLocaleLowerCase();
  panel.querySelectorAll('.genre-choice').forEach(label=>{
   label.hidden=Boolean(needle && !label.textContent.toLocaleLowerCase().includes(needle));
  });
  panel.querySelectorAll('.genre-choice-group').forEach(group=>{
   group.hidden=![...group.querySelectorAll('.genre-choice')].some(label=>!label.hidden);
  });
 };
 inside('.genre-apply').onclick=()=>{
  state.genres=[...genreDraft];state.page=1;genrePanelOpen=false;loadCatalog();
 };
 inside('.genre-clear').onclick=()=>{
  state.genres=[];genreDraft=new Set();state.page=1;genrePanelOpen=false;loadCatalog();
 };
}
async function loadGenreOptions(category, requestId){
 const key=category||'all';
 const cached=genreCache.get(key);
 if(cached && Date.now()-cached.fetched<60000){renderGenreControls(category);return;}
 renderGenreControls(category);
 try{
  const data=await api('genres'+(category?'?category='+encodeURIComponent(category):''));
  if(requestId!==catalogRequest)return;
  genreCache.set(key,{genres:data.genres||[],anilist_genres:data.anilist_genres||[],fetched:Date.now()});
  renderGenreControls(category,data.partial?'Some genre options are temporarily unavailable.':'');
 }catch(err){
  if(requestId!==catalogRequest)return;
  renderGenreControls(category,'Genre options are currently unavailable. Try again later.');
 }
}
async function loadCatalog(){
 const requestId=++catalogRequest;
 const route=location.hash.match(/^#\/category\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)/);
 const category=route?route[1]:state.filter;
 const params=new URLSearchParams({page:state.page,q:state.query});
 if(category)params.set('category',category);
 state.genres.forEach(genre=>params.append('genre',genre));
 const target=route?$('routePage'):$('cards');
 target.innerHTML='<p class="catalog-state">'+small('Loading published stories...')+'</p>';
 try{
  const data=await api('catalog?'+params);
  if(requestId!==catalogRequest)return;
  state.items=data.items;
  const cards=data.items.map(card).join('')||`<div class="catalog-state">${small(data.partial?'Some categories are currently unavailable. Please retry.':state.genres.length?'No stories match your selected genres. Try fewer filters.':'No published stories yet.')}</div>`;
  const notice=data.partial?`<p class="catalog-state partial-warning">${small('Some categories are temporarily unavailable. Showing available stories.')}</p>`:'';
  if(route){
   target.innerHTML=`<div class="page-breadcrumb"><a href="#/">${small('Home')}</a> / ${small(names[category])}</div><div class="listing-heading"><h1>${small(names[category])}</h1><span>${data.total} ${small('stories')}</span></div><div class="genre-mount" aria-label="Filter by genres"></div>${notice}<div class="cards category-cards">${cards}</div>${pager(data.pages)}`;
  }else{
   target.innerHTML=notice+cards;
   $('resultCount').textContent=data.total+' '+small('published titles');
   $('catalogPager').innerHTML=pager(data.pages);
  }
  genreDraft=new Set(state.genres);
  loadGenreOptions(category,requestId);
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{
   state.page=+b.dataset.page;loadCatalog();window.scrollTo({top:0,behavior:'smooth'});
  });
 }catch(e){
  if(requestId!==catalogRequest)return;
  target.innerHTML='<p class="catalog-state">'+small('Catalog temporarily unavailable. Please try again later.')+'</p><button class="retry-catalog" type="button">'+small('Retry')+'</button>';
  const retry=target.querySelector('.retry-catalog');if(retry)retry.onclick=loadCatalog;
  if(!route)$('catalogPager').innerHTML='';
 }
}
async function titlePage(cat,slug){$('routePage').innerHTML='<p class="catalog-state">'+small('Loading...')+'</p>';try{const x=await api('title?category='+cat+'&slug='+encodeURIComponent(slug));if(!x){$('routePage').innerHTML='<p class="catalog-state">'+small('Title not found on this page.')+'</p>';return}const chapters=(x.chapters||[]).map(ch=>`<a class="chapter" href="#/read/${encodeURIComponent(cat)}/${encodeURIComponent(slug)}/${encodeURIComponent(ch.number)}"><b>${small('Chapter')} ${esc(ch.number)}</b><span>${small('Read now')} →</span></a>`).join('');$('routePage').innerHTML=`<div class="page-breadcrumb"><a href="#/">${small('Home')}</a> / <a href="#/category/${cat}">${small(names[cat])}</a></div><div class="detail-hero"><div class="detail-poster cover">${cover(x)}</div><div class="detail-info"><span class="kicker">${small(names[cat])}</span><h1>${esc(x.title)}</h1><div class="story-facts">${x.status?`<span>${small(x.status)}</span>`:''}${x.year?`<span>${esc(x.year)}</span>`:''}${[...new Set([...(Array.isArray(x.genres)?x.genres:[]),...(Array.isArray(x.tags)?x.tags:[])])].filter(g=>typeof g==='string').slice(0,8).map(g=>`<span>${esc(g)}</span>`).join('')}</div><h3>${small('Synopsis')}</h3><p class="story-synopsis">${esc(x.description||'Synopsis not available from verified metadata sources yet.')}</p>${Array.isArray(x.authors)&&x.authors.length?`<p class="story-credit"><b>${small('Author')}:</b> ${esc(x.authors.join(', '))}</p>`:''}${Array.isArray(x.artists)&&x.artists.length?`<p class="story-credit"><b>${small('Artist')}:</b> ${esc(x.artists.join(', '))}</p>`:''}${x.metadata_source_urls?`<p class="story-credit metadata-credit">${small('Metadata')}: ${Object.keys(x.metadata_source_urls).map(k=>esc(k)).join(' · ')}</p>`:''}</div></div><div class="listing-heading"><h2>${small('Chapter list')}</h2><span>${x.chapters?.length||0}</span></div><div class="chapter-list">${chapters}</div>`}catch(e){$('routePage').innerHTML='<p class="catalog-state">'+small('Unable to load story.')+'</p>'}}
function readerFailure(cat,slug,chapter,message){
 const status=$('readerStatus');
 if(!status)return;
 status.hidden=false;
 status.replaceChildren();
 const description=document.createElement('p');
 description.className='reader-failure-text';
 description.textContent=message;
 const action=document.createElement('button');
 action.className='reader-retry';
 action.type='button';
 action.textContent=small('Retry chapter');
 action.onclick=()=>readerPage(cat,slug,chapter);
 status.append(description,action);
}
// A simple first-party 18+ acknowledgement replaces the old permanent 403.
// It does not collect identity documents or pretend to independently verify age.
function showAdultConfirmation(cat,slug,chapter){
 const status=$('readerStatus');
 if(!status)return;
 status.hidden=false;
 status.replaceChildren();
 const panel=document.createElement('section');
 panel.className='adult-confirmation';
 panel.setAttribute('aria-labelledby','adultConfirmTitle');
 panel.innerHTML=`<span class="adult-confirm-label">18+ ${small('Restricted content')}</span><h2 id="adultConfirmTitle">${small('Adults only')}</h2><p>${small('This chapter is intended for adults aged 18 or older. Confirm your age to continue reading.')}</p><div class="adult-confirm-actions"><button type="button" class="adult-confirm-yes">${small('I am 18+ — Continue')}</button><a class="adult-confirm-back" href="#/title/${encodeURIComponent(cat)}/${encodeURIComponent(slug)}">${small('Back to chapters')}</a></div><p class="adult-confirm-feedback" role="alert" aria-live="polite"></p>`;
 status.appendChild(panel);
 const button=panel.querySelector('.adult-confirm-yes');
 const feedback=panel.querySelector('.adult-confirm-feedback');
 button.onclick=async()=>{
  button.disabled=true;
  feedback.textContent=small('Saving confirmation...');
  try{
   await api('age/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({over_18:true})});
   readerPage(cat,slug,chapter);
  }catch(error){
   feedback.textContent=error.message;
   button.disabled=false;
  }
 };
}
// Reader tap navigation: LEFT half scrolls UP, RIGHT half scrolls DOWN.
// Keep normal swipe scrolling intact; do not treat drags or long presses as taps.
function bindReaderTapScroll(container){
 let press=null;
 let tapAllowed=false;
 container.addEventListener('pointerdown',event=>{
  tapAllowed=false;
  if(!event.isPrimary || event.button!==0 || !(event.target instanceof Element) || !event.target.closest('img')){
   press=null;return;
  }
  press={id:event.pointerId,x:event.clientX,y:event.clientY,scrollY:window.scrollY,time:Date.now(),moved:false};
 },{passive:true});
 container.addEventListener('pointermove',event=>{
  if(press && event.pointerId===press.id && Math.hypot(event.clientX-press.x,event.clientY-press.y)>14){
   press.moved=true;
  }
 },{passive:true});
 container.addEventListener('pointercancel',()=>{press=null;tapAllowed=false;},{passive:true});
 container.addEventListener('pointerup',event=>{
  tapAllowed=Boolean(press && press.id===event.pointerId && !press.moved &&
   Math.abs(window.scrollY-press.scrollY)<6 && Date.now()-press.time<700);
  press=null;
 },{passive:true});
 container.addEventListener('click',event=>{
  if(!tapAllowed || !(event.target instanceof Element) || !event.target.closest('img'))return;
  tapAllowed=false;
  if(!document.body.classList.contains('reader-mode'))return;
  const bounds=container.getBoundingClientRect();
  const right=event.clientX>=bounds.left+bounds.width/2;
  const viewportHeight=window.visualViewport?.height||window.innerHeight;
  const distance=Math.max(220,Math.round(viewportHeight*.72));
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollBy({top:right?distance:-distance,behavior:reduced?'auto':'smooth'});
 },{passive:true});
}
async function readerPage(cat,slug,chapter){
 const id=++readerRequest;
 const target=$('routePage');
 const back=`#/title/${encodeURIComponent(cat)}/${encodeURIComponent(slug)}`;
 const query=new URLSearchParams({category:cat,slug,chapter});
 target.innerHTML=`<section class="reader-shell"><div class="reader-toolbar"><a href="${back}">← ${small('Chapters')}</a><strong>${small('Chapter')} ${esc(chapter)}</strong><span id="readerCount"></span></div><div class="reader-tap-hint" aria-label="Tap left to scroll up. Tap right to scroll down.">${small('Left tap: up  |  Right tap: down')}</div><div id="readerStatus" class="catalog-state reader-progress" role="status" aria-live="polite"><b>${small('Preparing chapter...')}</b><div class="reader-progress-track"><div id="readerProgressBar" class="reader-progress-bar"></div></div><span id="readerProgressText">${small('Connecting to Telegram storage...')}</span></div><div id="readerPages" class="reader-images"></div><a class="reader-bottom" href="${back}">← ${small('Back to chapters')}</a></section>`;
 const pages=$('readerPages');
 bindReaderTapScroll(pages);
 const status=$('readerStatus');
 let appended=0;
 const appendPages=(targetCount)=>{
  const total=Math.max(0,Math.min(600,Number(targetCount)||0));
  if(total<=appended)return;
  const fragment=document.createDocumentFragment();
  for(let n=appended+1;n<=total;n++){
   const image=document.createElement('img');
   image.loading=n<=2?'eager':'lazy';
   image.decoding='async';
   image.alt='Page '+n;
   const source='/api/chapter/page?'+query.toString()+'&page='+n;
   image.onerror=()=>{
    const tries=Number(image.dataset.retries||0);
    if(tries>=2)return;
    image.dataset.retries=String(tries+1);
    setTimeout(()=>{if(image.isConnected && id===readerRequest)image.src=source+'&retry='+String(tries+1);},1300*(tries+1));
   };
   image.src=source;
   fragment.appendChild(image);
  }
  pages.appendChild(fragment);
  appended=total;
 };
 const showProgress=(result)=>{
  if(!status || status.hidden)return;
  const text=$('readerProgressText');
  const bar=$('readerProgressBar');
  const stage=result.stage||'queued';
  let message='Preparing chapter...';
  let percentage=0;
  if(stage==='queued'){message='Waiting for reader worker...';}
  if(stage==='connecting'){message='Connecting to Telegram storage...';}
  if(stage==='downloading'){
   const part=Number(result.part||1),total=Number(result.parts||1);
   const bytes=Number(result.downloaded_bytes||0),size=Number(result.download_total||0);
   message=`Downloading PDF ${part}/${total}`;
   if(size>0){percentage=Math.min(100,Math.round(bytes/size*100));message+=` · ${percentage}%`;}
  }
  if(stage==='rendering'){
   const done=Number(result.pages_ready||0),total=Number(result.pages_total||0);
   message=`Preparing page ${done}/${total||'...'} · You can read available pages now`;
   if(total>0)percentage=Math.min(100,Math.round(done/total*100));
  }
  if(text)text.textContent=small(message);
  if(bar)bar.style.width=percentage+'%';
  const ready=Number(result.pages_ready||0);
  if(ready>0)appendPages(ready);
  if(ready>0){
   $('readerCount').textContent=ready+'/'+(result.pages_total||'?')+' '+small('pages');
   status.classList.add('reader-loading-compact');
   const title=status.querySelector('b');
   if(title)title.textContent=small('Keep reading - more pages are loading');
  }
 };
 // Rendering is progressive: readers can see page 1 while the rest renders.
 // The server can be slow downloading very large chapters, so do not impose
 // the old artificial 225-second frontend cutoff.
 const deadline=Date.now()+25*60*1000;
 while(Date.now()<deadline){
  if(id!==readerRequest || !location.hash.startsWith('#/read/'))return;
  try{
   const result=await api('chapter?'+query.toString(),{retries:2,timeoutMs:20000});
   if(id!==readerRequest || !location.hash.startsWith('#/read/'))return;
   if(result.status==='error')throw Error(result.error||'Chapter is temporarily unavailable.');
   if(result.status==='ready'){
    const count=Math.min(Number(result.pages)||0,600);
    if(count<1)throw Error('No readable pages were found for this chapter.');
    appendPages(count);
    $('readerCount').textContent=count+' '+small('pages');
    status.hidden=true;
    return;
   }
   showProgress(result);
  }catch(err){
   if(id!==readerRequest)return;
   if(err.code==='adult_confirmation_required'){
    showAdultConfirmation(cat,slug,chapter);
   }else{
    readerFailure(cat,slug,chapter,err.message);
   }
   return;
  }
  await wait(appended<3?1200:2300);
 }
 if(id===readerRequest)readerFailure(cat,slug,chapter,'Chapter is taking too long. Tap Retry to check again.');
}
function route(){let h=decodeURIComponent(location.hash||'#/');const cat=h.match(/^#\/category\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)/),title=h.match(/^#\/title\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)\/(.+)$/),read=h.match(/^#\/read\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)\/([^/]+)\/(.+)$/);const auth=h.match(/^#\/auth\/(login|signup)$/),profile=h==='#/profile';const home=!cat&&!title&&!read&&!auth&&!profile;document.body.classList.toggle('reader-mode',Boolean(read));document.documentElement.classList.toggle('reader-mode',Boolean(read));$('homeContent').hidden=!home;$('routePage').hidden=home;$('nav').classList.remove('open');$('menuBtn').setAttribute('aria-expanded','false');state.page=1;genrePanelOpen=false;readerRequest++;if(auth){catalogRequest++;authPage(auth[1]);}else if(profile){catalogRequest++;profilePage();}else if(read){catalogRequest++;readerPage(read[1],read[2],read[3]);}else if(title){catalogRequest++;titlePage(title[1],title[2]);}else loadCatalog();if(!home)window.scrollTo(0,0)}
$('menuBtn').onclick=()=>{let open=$('nav').classList.toggle('open');$('menuBtn').setAttribute('aria-expanded',String(open))};
document.querySelectorAll('.category[data-filter]').forEach(b=>b.onclick=()=>location.hash='#/category/'+(b.dataset.filter.toLowerCase()));
document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{state.filter=b.dataset.filter==='All'?'':b.dataset.filter.toLowerCase();state.page=1;document.querySelectorAll('.filter').forEach(z=>z.classList.toggle('selected',z===b));loadCatalog()});
$('searchInput').oninput=e=>{state.query=e.target.value;state.page=1;clearTimeout(window.searchTimer);window.searchTimer=setTimeout(loadCatalog,350)};
$('searchToggle').onclick=()=>{location.hash='#/';$('searchInput').focus();$('library').scrollIntoView({behavior:'smooth'})};
function modal(content){$('modalBody').innerHTML=content;$('overlay').hidden=false}
$('closeModal').onclick=()=>{$('overlay').hidden=true};$('overlay').onclick=e=>{if(e.target===$('overlay'))$('overlay').hidden=true};
async function refreshUser(){try{state.user=(await api('me')).user}catch(e){state.user=null}let b=$('adminBtn');b.textContent=state.user?small('Profile'):small('Sign in');b.title=state.user?.email||'Sign in';$('accountNav').href=state.user?'#/profile':'#/auth/login';$('accountNav').textContent=small(state.user?'My profile':'Sign in / Sign up')}
function authPage(mode){
 const signup=mode==='signup';
 const passwordField=(name,label,auto)=>`<label class="auth-label" for="auth-${name}">${small(label)}</label><div class="password-wrap"><input id="auth-${name}" name="${name}" type="password" minlength="8" maxlength="128" autocomplete="${auto}" required><button class="password-toggle" type="button" data-for="auth-${name}" aria-label="Show password" aria-pressed="false" title="Show password"><svg viewBox="0 0 24 24" width="23" height="23" aria-hidden="true"><path d="M2 12s3.7-6 10-6 10 6 10 6-3.7 6-10 6S2 12 2 12Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg></button></div>`;
 $('routePage').innerHTML=`<section class="account-page"><a href="#/" class="account-back">${small('Back to home')}</a><div class="account-panel"><span class="kicker">${small('MIKO ACCOUNT')}</span><h1>${signup?'Create Account':'Sign In'}</h1><p class="auth-intro">${small(signup?'Create your reading account.':'Welcome back. Continue reading.')}</p><form id="authPageForm" class="auth-form"><label class="auth-label" for="auth-email">${small('Email address')}</label><input id="auth-email" name="email" type="email" autocomplete="email" required maxlength="254">${passwordField('password','Password',signup?'new-password':'current-password')}${signup?passwordField('confirm','Confirm password','new-password'):''}${signup?`<p class="auth-hint">${small('8-128 characters, including 1 number and 1 special character.')}</p>`:''}<button type="submit" class="primary">${small(signup?'Create account':'Sign in')}</button><p id="authFeedback" role="status" aria-live="polite"></p></form><p class="account-switch">${small(signup?'Already have an account?':'New to MIKO?')} <a href="#/auth/${signup?'login':'signup'}">${small(signup?'Sign in':'Create account')}</a></p></div></section>`;
 document.querySelectorAll('.password-toggle').forEach(btn=>btn.onclick=()=>{const el=$(btn.dataset.for);const showing=el.type==='password';el.type=showing?'text':'password';btn.classList.toggle('visible',showing);btn.innerHTML=showing?'&#9673;':'&#9678;';btn.title=showing?'Hide password':'Show password';btn.setAttribute('aria-label',showing?'Hide password':'Show password');btn.setAttribute('aria-pressed',String(showing));});
 $('authPageForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);const email=f.get('email'),password=f.get('password');const feedback=$('authFeedback');if(signup){if(!/^(?=.{8,128}$)(?=.*[0-9])(?=.*[^A-Za-z0-9\s])[^\s]+$/.test(password)){feedback.textContent=small('Use 8-128 characters, including a number and a special character.');return}if(password!==f.get('confirm')){feedback.textContent=small('Passwords do not match.');return}}const submit=e.target.querySelector('[type=submit]');submit.disabled=true;feedback.textContent=small('Please wait...');try{await api(signup?'register':'login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});if(signup){location.hash='#/auth/login';setTimeout(()=>{const el=$('authFeedback');if(el)el.textContent=small('Account created. Please sign in.')},0)}else{await refreshUser();location.hash='#/profile'}}catch(err){feedback.textContent=err.message}finally{submit.disabled=false}};
}

function profilePage(){if(!state.user){location.hash='#/auth/login';return}const isOwner=state.user.role==='owner';$('routePage').innerHTML=`<section class="account-page"><a href="#/" class="account-back">${small('Back to home')}</a><div class="account-panel"><span class="kicker">${small('My account')}</span><h1>${small('Profile')}</h1><p><b>${small('Email')}:</b> ${esc(state.user.email)}</p><p><b>${small('Role')}:</b> ${small(state.user.role)}</p>${isOwner?`<div class="owner-note"><b>${small('Owner access verified')}</b><p>${small('Administration features will appear here when publishing controls are enabled.')}</p></div>`:''}<button id="profileLogout" class="primary">${small('Log out')}</button></div></section>`;$('profileLogout').onclick=async()=>{await api('logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await refreshUser();location.hash='#/auth/login'};}
$('adminBtn').onclick=()=>{location.hash=state.user?'#/profile':'#/auth/login'};
window.addEventListener('hashchange',route);refreshUser().then(()=>{if(location.hash==='#/profile')route()});route();
