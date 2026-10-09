// v23: published MongoDB content only; no demo titles or fake chapters.
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const small=s=>String(s).replace(/[a-z]/gi,c=>({a:'ᴀ',b:'ʙ',c:'ᴄ',d:'ᴅ',e:'ᴇ',f:'ғ',g:'ɢ',h:'ʜ',i:'ɪ',j:'ᴊ',k:'ᴋ',l:'ʟ',m:'ᴍ',n:'ɴ',o:'ᴏ',p:'ᴘ',q:'ǫ',r:'ʀ',s:'s',t:'ᴛ',u:'ᴜ',v:'ᴠ',w:'ᴡ',x:'x',y:'ʏ',z:'ᴢ'}[c.toLowerCase()]||c));
const names={manga:'Manga',manhwa:'Manhwa',webtoon:'Webtoon',manhua:'Manhua',adult_manga:'18+ Manga',adult_manhwa:'18+ Manhwa',adult_webtoon:'18+ Webtoon'};
let state={page:1,filter:'',query:'',user:null,items:[],loading:false};
let catalogRequest=0;
let readerRequest=0;
const cover=x=>x.cover_url
 ? `<img class="cover-art" loading="lazy" decoding="async" src="/api/cover?category=${encodeURIComponent(x.category)}&slug=${encodeURIComponent(x.slug)}" alt="Cover artwork for ${esc(x.title)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="cover-placeholder" hidden>MIKO</span>`
 : '<span class="cover-placeholder">MIKO</span>';
function card(x){const fresh=x.updated_at&&Date.now()-Date.parse(x.updated_at)<86400000;return `<a class="card" href="#/title/${esc(x.category)}/${encodeURIComponent(x.slug)}"><div class="cover">${cover(x)}${fresh?'<span class="new-label">NEW</span>':''}</div><div class="card-info"><h3>${esc(x.title)}</h3><div class="meta">${small(names[x.category]||x.category)} · ${x.chapters?.length||0} ${small('chapters')}</div></div></a>`}
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
   throw error;
  }
  return d;
 }
 throw Error('Reader request was interrupted.');
}
function pager(total){if(total<=1)return '';return `<div class="pager"><button ${state.page<=1?'disabled':''} data-page="${state.page-1}">${small('Previous')}</button><b>${state.page} / ${total}</b><button ${state.page>=total?'disabled':''} data-page="${state.page+1}">${small('Next')}</button></div>`}
async function loadCatalog(){const requestId=++catalogRequest;const route=location.hash.match(/^#\/category\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)/);const category=route?route[1]:state.filter;const params=new URLSearchParams({page:state.page,q:state.query});if(category)params.set('category',category);const target=route?$('routePage'):$('cards');target.innerHTML='<p class="catalog-state">'+small('Loading published stories...')+'</p>';try{const data=await api('catalog?'+params);if(requestId!==catalogRequest)return;state.items=data.items;const cards=data.items.map(card).join('')||`<div class="catalog-state">${small(data.partial?'Some categories are currently unavailable. Please retry.':'No published stories yet.')}</div>`;const notice=data.partial?`<p class="catalog-state partial-warning">${small('Some categories are temporarily unavailable. Showing available stories.')}</p>`:'';if(route){target.innerHTML=`<div class="page-breadcrumb"><a href="#/">${small('Home')}</a> / ${small(names[category])}</div><div class="listing-heading"><h1>${small(names[category])}</h1><span>${data.total} ${small('stories')}</span></div>${notice}<div class="cards category-cards">${cards}</div>${pager(data.pages)}`}else{target.innerHTML=notice+cards;$('resultCount').textContent=data.total+' '+small('published titles');$('catalogPager').innerHTML=pager(data.pages)}document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{state.page=+b.dataset.page;loadCatalog();window.scrollTo({top:0,behavior:'smooth'})})}catch(e){if(requestId!==catalogRequest)return;target.innerHTML='<p class="catalog-state">'+small('Catalog temporarily unavailable. Please try again later.')+'</p><button class="retry-catalog" type="button">'+small('Retry')+'</button>';const retry=target.querySelector('.retry-catalog');if(retry)retry.onclick=loadCatalog;if(!route)$('catalogPager').innerHTML=''}}
async function titlePage(cat,slug){$('routePage').innerHTML='<p class="catalog-state">'+small('Loading...')+'</p>';try{const x=await api('title?category='+cat+'&slug='+encodeURIComponent(slug));if(!x){$('routePage').innerHTML='<p class="catalog-state">'+small('Title not found on this page.')+'</p>';return}const chapters=(x.chapters||[]).map(ch=>`<a class="chapter" href="#/read/${encodeURIComponent(cat)}/${encodeURIComponent(slug)}/${encodeURIComponent(ch.number)}"><b>${small('Chapter')} ${esc(ch.number)}</b><span>${small('Read now')} →</span></a>`).join('');$('routePage').innerHTML=`<div class="page-breadcrumb"><a href="#/">${small('Home')}</a> / <a href="#/category/${cat}">${small(names[cat])}</a></div><div class="detail-hero"><div class="detail-poster cover">${cover(x)}</div><div class="detail-info"><span class="kicker">${small(names[cat])}</span><h1>${esc(x.title)}</h1><div class="story-facts">${x.status?`<span>${small(x.status)}</span>`:''}${x.year?`<span>${esc(x.year)}</span>`:''}${Array.isArray(x.genres)?x.genres.slice(0,5).map(g=>`<span>${esc(g)}</span>`).join(''):''}</div><h3>${small('Synopsis')}</h3><p class="story-synopsis">${esc(x.description||'Synopsis not available from verified metadata sources yet.')}</p>${Array.isArray(x.authors)&&x.authors.length?`<p class="story-credit"><b>${small('Author')}:</b> ${esc(x.authors.join(', '))}</p>`:''}${Array.isArray(x.artists)&&x.artists.length?`<p class="story-credit"><b>${small('Artist')}:</b> ${esc(x.artists.join(', '))}</p>`:''}${x.metadata_source_urls?`<p class="story-credit metadata-credit">${small('Metadata')}: ${Object.keys(x.metadata_source_urls).map(k=>esc(k)).join(' · ')}</p>`:''}</div></div><div class="listing-heading"><h2>${small('Chapter list')}</h2><span>${x.chapters?.length||0}</span></div><div class="chapter-list">${chapters}</div>`}catch(e){$('routePage').innerHTML='<p class="catalog-state">'+small('Unable to load story.')+'</p>'}}
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
// Reader tap navigation: LEFT half scrolls DOWN, RIGHT half scrolls UP.
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
  window.scrollBy({top:right?-distance:distance,behavior:reduced?'auto':'smooth'});
 },{passive:true});
}
async function readerPage(cat,slug,chapter){
 const id=++readerRequest;
 const target=$('routePage');
 const back=`#/title/${encodeURIComponent(cat)}/${encodeURIComponent(slug)}`;
 const query=new URLSearchParams({category:cat,slug,chapter});
 target.innerHTML=`<section class="reader-shell"><div class="reader-toolbar"><a href="${back}">← ${small('Chapters')}</a><strong>${small('Chapter')} ${esc(chapter)}</strong><span id="readerCount"></span></div><div class="reader-tap-hint" aria-label="Tap left to scroll down. Tap right to scroll up.">${small('Left tap: down  |  Right tap: up')}</div><div id="readerStatus" class="catalog-state" role="status" aria-live="polite">${small('Preparing chapter...')}</div><div id="readerPages" class="reader-images"></div><a class="reader-bottom" href="${back}">← ${small('Back to chapters')}</a></section>`;
 bindReaderTapScroll($('readerPages'));
 const status=$('readerStatus');
 for(let attempt=0;attempt<45;attempt++){
  if(id!==readerRequest || !location.hash.startsWith('#/read/'))return;
  try{
   const result=await api('chapter?'+query.toString(),{retries:2,timeoutMs:17000});
   if(id!==readerRequest || !location.hash.startsWith('#/read/'))return;
   if(result.status==='error')throw Error(result.error||'Chapter is temporarily unavailable.');
   if(result.status==='ready'){
    const count=Math.min(Number(result.pages)||0,600);
    if(count<1)throw Error('No readable pages were found for this chapter.');
    $('readerCount').textContent=count+' '+small('pages');
    status.hidden=true;
    const container=$('readerPages');
    container.replaceChildren();
    const fragment=document.createDocumentFragment();
    for(let n=1;n<=count;n++){
     const img=document.createElement('img');
     img.loading=n<=2?'eager':'lazy';img.decoding='async';
     img.alt='Page '+n;
     const source='/api/chapter/page?'+query.toString()+'&page='+n;
     // One reconnect attempt for images affected by an intermittent connection.
     img.onerror=()=>{
      if(img.dataset.retried)return;
      img.dataset.retried='1';
      setTimeout(()=>{if(img.isConnected)img.src=source+'&retry=1';},1200);
     };
     img.src=source;
     fragment.appendChild(img);
    }
    container.appendChild(fragment);
    return;
   }
   status.textContent=small('Downloading and preparing pages. Please wait...');
  }catch(err){
   if(id!==readerRequest)return;
   readerFailure(cat,slug,chapter,err.message);
   return;
  }
  await wait(5000);
 }
 if(id===readerRequest)readerFailure(cat,slug,chapter,'Reader preparation timed out. Tap Retry to try again.');
}
function route(){let h=decodeURIComponent(location.hash||'#/');const cat=h.match(/^#\/category\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)/),title=h.match(/^#\/title\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)\/(.+)$/),read=h.match(/^#\/read\/(manga|manhwa|manhua|webtoon|adult_manga|adult_manhwa|adult_webtoon)\/([^/]+)\/(.+)$/);const auth=h.match(/^#\/auth\/(login|signup)$/),profile=h==='#/profile';const home=!cat&&!title&&!read&&!auth&&!profile;document.body.classList.toggle('reader-mode',Boolean(read));document.documentElement.classList.toggle('reader-mode',Boolean(read));$('homeContent').hidden=!home;$('routePage').hidden=home;$('nav').classList.remove('open');$('menuBtn').setAttribute('aria-expanded','false');state.page=1;readerRequest++;if(auth){catalogRequest++;authPage(auth[1]);}else if(profile){catalogRequest++;profilePage();}else if(read){catalogRequest++;readerPage(read[1],read[2],read[3]);}else if(title){catalogRequest++;titlePage(title[1],title[2]);}else loadCatalog();if(!home)window.scrollTo(0,0)}
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
