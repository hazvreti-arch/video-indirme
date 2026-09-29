const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const state={meta:null,jobIds:[],jobs:new Map(),view:'home',theme:localStorage.getItem('vidora_theme')||'system',settings:JSON.parse(localStorage.getItem('vidora_settings')||'{}')};

function toast(t){const x=$('#toast');x.textContent=t;x.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>x.classList.remove('show'),3200)}
function escapeHtml(s=''){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fmtBytes(n){n=Number(n||0);if(!n)return '—';const u=['B','KB','MB','GB','TB'];let i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]}
function fmtTime(sec){sec=Math.max(0,Number(sec||0));const h=Math.floor(sec/3600),m=Math.floor(sec%3600/60),s=Math.floor(sec%60);return h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`}
function jsonOpts(){return {headers:{'Content-Type':'application/json'}}}

function applyTheme(mode){
  document.body.classList.toggle('light',mode==='light'||(mode==='system'&&matchMedia('(prefers-color-scheme: light)').matches));
  state.theme=mode;localStorage.setItem('vidora_theme',mode);if($('#themeSelect'))$('#themeSelect').value=mode;
}
applyTheme(state.theme);

async function api(url,opts={}){const r=await fetch(url,opts);let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);return d}

function showView(view){
  state.view=view;$$('.view').forEach(x=>x.classList.remove('active'));$(`#view-${view}`)?.classList.add('active');
  $$('[data-view]').forEach(x=>x.classList.toggle('active',x.dataset.view===view));
  $('#viewTitle').textContent={home:'Workspace',library:'Library',queue:'Queue',tools:'Tools',profiles:'Presets',settings:'Settings'}[view]||'Workspace';
  if(view==='library')loadHistory();if(view==='queue')loadQueue();if(view==='profiles')loadProfiles();if(view==='tools'){};
}
$$('[data-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));
$('#mobileMenu')?.addEventListener('click',()=>$('#sidebar').classList.toggle('force-open'));

// Mode tabs
$$('[data-mode-tab]').forEach(b=>b.addEventListener('click',()=>{
  $$('[data-mode-tab]').forEach(x=>x.classList.remove('active'));b.classList.add('active');
  $$('.mode-panel').forEach(x=>x.classList.remove('active'));$(`#panel-${b.dataset.modeTab}`).classList.add('active');
}));
$$('[data-mode-tab-jump]').forEach(b=>b.addEventListener('click',()=>{
  showView('home');setTimeout(()=>{const tab=$(`[data-mode-tab="${b.dataset.modeTabJump}"]`);tab?.click();window.scrollTo({top:0,behavior:'smooth'})},50)
}));

// Platform intelligence
$('#url')?.addEventListener('input',()=>{
  const v=$('#url').value.trim();
  const bar=$('#detectedBar'); if(!v){bar.innerHTML='';return}
  const map=[['youtube','YouTube'],['youtu.be','YouTube'],['tiktok','TikTok'],['instagram','Instagram'],['twitter','X'],['x.com','X'],['facebook','Facebook'],['reddit','Reddit'],['vimeo','Vimeo']];
  const hit=map.find(x=>v.toLowerCase().includes(x[0]));bar.innerHTML=hit?`<span class="tag purple">${hit[1]} detected</span>`:'<span class="tag">Generic video</span>';
});

$('#pasteBtn')?.addEventListener('click',async()=>{try{$('#url').value=await navigator.clipboard.readText();$('#url').dispatchEvent(new Event('input'));toast('Bağlantı yapıştırıldı.');}catch{toast('Panoya erişilemedi. Ctrl+V kullan.')}});
$('#copyBtn')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#url').value.trim());toast('Bağlantı kopyalandı.')}catch{toast('Kopyalama başarısız.')}});

// Drag/drop URL
const drop=$('#dropZone');['dragenter','dragover'].forEach(e=>drop?.addEventListener(e,x=>{x.preventDefault();drop.classList.add('drag')}));['dragleave','drop'].forEach(e=>drop?.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('drag')}));drop?.addEventListener('drop',e=>{const t=e.dataTransfer.getData('text');if(t){$('#url').value=t.trim();$('#url').dispatchEvent(new Event('input'));toast('URL alındı.')}});

async function analyzeUrl(){
  const url=$('#url').value.trim();if(!url)return toast('Önce bir bağlantı gir.');
  const btn=$('#analyzeBtn');btn.disabled=true;btn.textContent='Analyzing…';
  try{
    const d=await api('/api/analyze',{...jsonOpts(),method:'POST',body:JSON.stringify({url,playlist:true})});state.meta=d;
    $('#analyzeResult').style.display='block';$('#videoTitle').textContent=d.title||'Video';$('#videoSub').textContent=d.channel||d.uploader||'—';$('#platformTag').textContent=d.platform||'Video';$('#kindTag').textContent=(d.kind||'video').toUpperCase();
    const img=$('#thumb');img.src=d.thumbnail||'';img.style.display=d.thumbnail?'block':'none';$('.thumb-fallback').style.display=d.thumbnail?'none':'grid';
    const specs=[d.duration?fmtTime(d.duration):'',d.width&&d.height?`${d.width}×${d.height}`:'',d.fps?`${Math.round(d.fps)} FPS`:'',d.vcodec&&d.vcodec!=='none'?String(d.vcodec):'',d.acodec&&d.acodec!=='none'?String(d.acodec):''].filter(Boolean);
    $('#specRow').innerHTML=specs.map(x=>`<span>${escapeHtml(x)}</span>`).join('');
    const rec=d.recommended||{quality:'720',container:'mp4'};$('#recommendText').textContent=`${rec.quality}p ${rec.container.toUpperCase()} · ${rec.reason}`;
    $$('#videoQualities button').forEach(b=>b.classList.toggle('active',b.dataset.q===rec.quality));$('#container').value=rec.container||'mp4';
    $('#subtitleLang').innerHTML='<option value="">No subtitle</option>'+[...(d.subtitles||[]),...(d.automatic_captions||[])].filter((v,i,a)=>a.indexOf(v)===i).map(s=>`<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
    renderChapters(d.chapters||[]);state.meta=d;localStorage.setItem('vidora_last_url',url);toast('Analiz tamamlandı.');
  }catch(e){toast(e.message)}finally{btn.disabled=false;btn.textContent='Smart Analyze'}
}
$('#analyzeBtn')?.addEventListener('click',analyzeUrl);$('#url')?.addEventListener('keydown',e=>{if(e.key==='Enter')analyzeUrl()});

$('#applyRecommendation')?.addEventListener('click',()=>{const q=state.meta?.recommended?.quality||'720';$$('#videoQualities button').forEach(b=>b.classList.toggle('active',b.dataset.q===q));$('#container').value=state.meta?.recommended?.container||'mp4';toast('Akıllı ayar uygulandı.')});
$$('#videoQualities button')?.forEach(b=>b.addEventListener('click',()=>{$$('#videoQualities button').forEach(x=>x.classList.remove('active'));b.classList.add('active')}));
$('#advancedToggle')?.addEventListener('click',()=>{const x=$('#advancedMore');x.style.display=x.style.display==='grid'?'none':'grid'});

function renderChapters(chapters){
 const box=$('#chapterBox');if(!chapters.length){box.style.display='none';box.innerHTML='';return}box.style.display='block';box.innerHTML='<div class="section-label">Chapters</div>'+chapters.map((c,i)=>`<div class="chapter"><button class="ghost-square chapter-pick" data-i="${i}">▶</button><b>${escapeHtml(c.title||'Chapter '+(i+1))}</b><span>${fmtTime(c.start_time)} — ${fmtTime(c.end_time)}</span></div>`).join('');
 $$('.chapter-pick').forEach(b=>b.addEventListener('click',()=>{const c=chapters[Number(b.dataset.i)];$('#trimStart').value=c.start_time||0;$('#trimEnd').value=c.end_time||'';$('#advancedMore').style.display='grid';toast('Chapter aralığı trim alanına aktarıldı.')}));
}
$('#previewBtn')?.addEventListener('click',()=>{
  const u=state.meta?.preview_url;
  if(!u) return toast('Bu platform doğrudan önizleme URLsi vermedi. İndirme ile devam edebilirsin.');
  $('#modalInner').innerHTML=`<button class="modal-close" id="modalClose">×</button><h3>Mini player</h3><video controls autoplay style="width:100%;border-radius:14px;background:#000" src="${u}"></video>`;
  $('#modal').classList.add('open');$('#modalClose').onclick=()=>$('#modal').classList.remove('open');
});

$('#downloadThumb')?.addEventListener('click',async()=>{if(!$('#url').value.trim())return toast('Önce URL gir.');try{const d=await api('/api/thumbnail',{...jsonOpts(),method:'POST',body:JSON.stringify({url:$('#url').value.trim()})});window.location.href=d.download_url}catch(e){toast(e.message)}});

function selectedQuality(){return $('#videoQualities button.active')?.dataset.q||'720'}
$('#preset')?.addEventListener('change',()=>{
 const p=$('#preset').value;const map={phone:['720','mp4'],whatsapp:['480','mp4'],instagram:['1080','mp4'],tiktok:['1080','mp4'],archive:['best','mkv'],hq:['1080','mp4']};const [q,c]=map[p]||map.phone;$$('#videoQualities button').forEach(b=>b.classList.toggle('active',b.dataset.q===q));$('#container').value=c;toast(`${p} preset uygulandı.`);
});
async function startDownload(){
 if(!$('#url').value.trim())return toast('Önce URL gir.');
 const options={url:$('#url').value.trim(),quality:selectedQuality(),container:$('#container').value,mode:$('#audioFormat').value?'audio':'video',audio_format:$('#audioFormat').value||'mp3',subtitle_lang:$('#subtitleLang').value,subtitle_embed:$('#subtitleEmbed').checked,playlist:false,naming:$('#naming').value||'{title}-{quality}.{ext}',trim_start:$('#trimStart').value===''?null:Number($('#trimStart').value),trim_end:$('#trimEnd').value===''?null:Number($('#trimEnd').value)};
 const btn=$('#downloadBtn');btn.disabled=true;btn.textContent='Başlatılıyor…';
 try{const d=await api('/api/download',{...jsonOpts(),method:'POST',body:JSON.stringify(options)});addJob(d.job_id);showView('queue');toast('İş kuyruğa alındı.')}catch(e){toast(e.message)}finally{btn.disabled=false;btn.textContent='İndirmeyi Başlat'}
}
$('#downloadBtn')?.addEventListener('click',startDownload);
function addJob(id){state.jobIds.push(id);$('#queueBadge').textContent=state.jobIds.length;openEventStream(id)}
function openEventStream(id){
 const es=new EventSource('/api/events/'+id);es.onmessage=e=>{const d=JSON.parse(e.data);state.jobs.set(id,d);renderQueue();metrics();if(d.status==='ready'){toast('✓ İndirme tamamlandı.');es.close();}if(d.status==='error'){toast(d.error||'İndirme başarısız.');es.close()}};es.onerror=()=>{es.close();pollOnce(id)}
}
async function pollOnce(id){try{const d=await api('/api/status/'+id);state.jobs.set(id,d);renderQueue();if(!['ready','error','cancelled'].includes(d.status))setTimeout(()=>pollOnce(id),1200)}catch(e){}}
function renderQueue(){const box=$('#queueList');if(!state.jobs.size){box.innerHTML='<div class="queue-row"><div><h4>Queue boş</h4><p>Yeni bir iş başlat.</p></div></div>';return}box.innerHTML=[...state.jobs.values()].map(j=>`<div class="queue-row"><div><h4>${escapeHtml(j.title||j.id)}</h4><p>${escapeHtml(j.status)} · ${fmtBytes(j.bytes_done)} / ${fmtBytes(j.bytes_total)} · ${escapeHtml(j.speed||'')} · ETA ${escapeHtml(j.eta||'')}</p><div class="progress"><i style="width:${j.progress||0}%"></i></div></div><div class="row-actions">${j.download_url?`<button onclick="location.href='${j.download_url}'">Download</button>`:''}${['queued','downloading'].includes(j.status)?`<button data-pause="${j.id}">Pause</button>`:''}${j.status==='paused'?`<button data-resume="${j.id}">Resume</button>`:''}<button data-cancel="${j.id}">Cancel</button></div></div>`).join('');$$('[data-cancel]').forEach(b=>b.onclick=()=>cancelJob(b.dataset.cancel));$$('[data-pause]').forEach(b=>b.onclick=()=>controlJob(b.dataset.pause,'pause'));$$('[data-resume]').forEach(b=>b.onclick=()=>controlJob(b.dataset.resume,'resume'))}
async function cancelJob(id){try{await api('/api/jobs/'+id+'/cancel',{method:'POST'});toast('İş iptal edildi.')}catch(e){toast(e.message)}}
async function controlJob(id,action){try{const d=await api('/api/jobs/'+id+'/'+action,{method:'POST'});const j=state.jobs.get(id);if(j)j.status=d.status;renderQueue();toast(action==='pause'?'İş duraklatıldı.':'İş devam ediyor.')}catch(e){toast(e.message)}}
$('#refreshQueue')?.addEventListener('click',renderQueue);
async function bulkQueue(action){try{const d=await api('/api/jobs/bulk/'+action,{method:'POST'});toast(`${d.count} iş güncellendi.`);loadQueue()}catch(e){toast(e.message)}}
$('#pauseAll')?.addEventListener('click',()=>bulkQueue('pause'));$('#resumeAll')?.addEventListener('click',()=>bulkQueue('resume'));$('#cancelAll')?.addEventListener('click',()=>bulkQueue('cancel'));

// Batch
function openBatch(){
 $('#toolsConsole').innerHTML=`<h3>Batch Lab</h3><p>Her satıra bir URL yaz. Maksimum 50 görev.</p><textarea id="batchUrls" class="batch-area" placeholder="https://...\nhttps://..."></textarea><div class="convert-controls"><select id="batchQ"><option>1080</option><option selected>720</option><option>480</option><option>360</option><option>best</option></select><select id="batchFormat"><option>mp4</option><option>webm</option><option>mkv</option></select><button class="primary-btn" id="batchGo">Queue all</button></div>`;
 $('#batchGo').onclick=async()=>{try{const d=await api('/api/batch',{...jsonOpts(),method:'POST',body:JSON.stringify({urls:$('#batchUrls').value,quality:$('#batchQ').value,container:$('#batchFormat').value})});d.job_ids.forEach(addJob);toast(`${d.count} görev kuyruğa eklendi.`);showView('queue')}catch(e){toast(e.message)}};
}

async function openPlaylist(){
 const url=$('#url').value.trim()||prompt('Playlist URL');if(!url)return;$('#toolsConsole').innerHTML='<div class="tool-result">Playlist analiz ediliyor…</div>';
 try{const d=await api('/api/playlist',{...jsonOpts(),method:'POST',body:JSON.stringify({url})});$('#toolsConsole').innerHTML=`<h3>${escapeHtml(d.title||'Playlist')}</h3><div>${(d.entries||[]).map((e,i)=>`<label class="chapter"><input type="checkbox" class="pl-item" data-url="${escapeHtml(e.url||'')}" checked><b>${i+1}. ${escapeHtml(e.title||'Video')}</b><span>${fmtTime(e.duration)}</span></label>`).join('')}</div><button class="primary-btn" id="queueSelected">Seçilenleri kuyruğa ekle</button>`;$('#queueSelected').onclick=async()=>{const urls=$$('.pl-item:checked').map(x=>x.dataset.url).filter(Boolean);if(!urls.length)return toast('Bir içerik seç.');try{const q=await api('/api/batch',{...jsonOpts(),method:'POST',body:JSON.stringify({urls:urls.join('\n'),quality:selectedQuality(),container:$('#container').value})});q.job_ids.forEach(addJob);showView('queue')}catch(e){toast(e.message)}}}catch(e){toast(e.message)}
}

$$('.tool-card').forEach(b=>b.addEventListener('click',()=>{const tool=b.dataset.tool;if(tool==='batch')openBatch();else if(tool==='playlist')openPlaylist();else if(tool==='thumbnail')$('#downloadThumb').click();else if(tool==='metadata')showMetadata();else if(tool==='subtitle')showSubtitleStudio();else if(tool==='local')showLocalMode();}));
$$('[data-tool-page]').forEach(b=>b.addEventListener('click',()=>{showView('tools');setTimeout(()=>({batch:openBatch,playlist:openPlaylist,thumbnail:()=>$('#downloadThumb').click(),metadata:showMetadata}[b.dataset.toolPage]||showLocalMode)(),50)}));

function showMetadata(){
 $('#toolsConsole').innerHTML=`<h3>Metadata Editor</h3><p style="color:var(--muted)">Dosyayı yükle, etiketleri değiştir ve yeni medya dosyasını al.</p><input type="file" id="metaFile" accept="video/*,audio/*"><div class="settings-grid" style="margin-top:10px"><input class="mini-input" id="mTitle" placeholder="Title"><input class="mini-input" id="mArtist" placeholder="Artist"><input class="mini-input" id="mAlbum" placeholder="Album"><input class="mini-input" id="mGenre" placeholder="Genre"><input class="mini-input" id="mYear" placeholder="Year"></div><button class="primary-btn" id="metaGo" style="margin-top:10px">Save metadata</button><div id="metaOut" class="tool-result"></div>`;
 $('#metaGo').onclick=async()=>{const f=$('#metaFile').files[0];if(!f)return toast('Dosya seç.');const fd=new FormData();fd.append('file',f);[['title','#mTitle'],['artist','#mArtist'],['album','#mAlbum'],['genre','#mGenre'],['year','#mYear']].forEach(([k,s])=>fd.append(k,$(s).value));try{const d=await api('/api/metadata',{method:'POST',body:fd});$('#metaOut').innerHTML=`✓ ${escapeHtml(d.filename)} · <a href="${d.download_url}">İndir</a>`;toast('Metadata güncellendi.')}catch(e){toast(e.message)}};
}

function showSubtitleStudio(){
 const langs=[...(state.meta?.subtitles||[]),...(state.meta?.automatic_captions||[])].filter((x,i,a)=>a.indexOf(x)===i);
 $('#toolsConsole').innerHTML=`<h3>Subtitle Studio</h3><p style="color:var(--muted)">Dil seç, formatı belirle ve doğrudan altyazı dosyasını al.</p><div class="convert-controls"><select id="subLang">${langs.length?langs.map(x=>`<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join(''):'<option value="">Dil bulunamadı</option>'}</select><select id="subFormat"><option>srt</option><option>vtt</option></select><button class="primary-btn" id="subGo">Download subtitle</button></div><div id="subOut" class="tool-result"></div>`;
 $('#subGo').onclick=async()=>{if(!$('#subLang').value)return toast('Altyazı dili yok.');try{const d=await api('/api/subtitles',{...jsonOpts(),method:'POST',body:JSON.stringify({url:$('#url').value.trim(),lang:$('#subLang').value,format:$('#subFormat').value})});$('#subOut').innerHTML=`✓ ${escapeHtml(d.filename)} · <a href="${d.download_url}">İndir</a>`}catch(e){toast(e.message)}};
}

function showLocalMode(){
 $('#toolsConsole').innerHTML=`<h3>Local Mode</h3><p style="color:var(--muted)">Video cihazında açılır. Chromium destekliyorsa seçtiğin bölümü WebM olarak doğrudan tarayıcıda kaydedebilir.</p><input type="file" id="localProbe" accept="video/*,audio/*"><div id="localInfo" class="tool-result"></div><div id="localStudio"></div>`;
 $('#localProbe').onchange=e=>{
  const f=e.target.files[0];if(!f)return;const url=URL.createObjectURL(f);
  $('#localInfo').innerHTML=`<b>${escapeHtml(f.name)}</b><br>${fmtBytes(f.size)} · ${escapeHtml(f.type||'unknown')}`;
  $('#localStudio').innerHTML=`<video id="localVideo" controls style="width:100%;max-height:320px;border-radius:14px;background:#000;margin-top:10px"></video><div class="convert-controls"><input class="mini-input" id="localStart" type="number" min="0" value="0" placeholder="Başlangıç"><input class="mini-input" id="localEnd" type="number" min="1" placeholder="Bitiş"><button class="primary-btn" id="localClipBtn">Local clip</button></div><div id="localOut" class="tool-result"></div>`;
  const v=$('#localVideo');v.src=url;
  $('#localClipBtn').onclick=async()=>{const start=Number($('#localStart').value||0),end=Number($('#localEnd').value||0);if(!end||end<=start)return toast('Bitiş zamanı başlangıçtan büyük olmalı.');if(!v.captureStream)return toast('Tarayıcı local recording desteklemiyor.');try{v.currentTime=start;await new Promise(r=>v.addEventListener('seeked',r,{once:true}));const stream=v.captureStream();const chunks=[];const rec=new MediaRecorder(stream,{mimeType:'video/webm'});rec.ondataavailable=e=>e.data.size&&chunks.push(e.data);rec.onstop=()=>{stream.getTracks().forEach(t=>t.stop());const blob=new Blob(chunks,{type:'video/webm'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='vidora-local-clip.webm';a.textContent='Download local clip';a.className='primary-btn';$('#localOut').replaceChildren(a);};rec.start(250);v.play();setTimeout(()=>{v.pause();rec.stop()},Math.max(100,end-start)*1000)}catch(err){toast('Local clip oluşturulamadı: '+err.message)}};
 };
}

// Convert/clip uploads
$('#chooseConvert')?.addEventListener('click',()=>$('#convertFile').click());$('#chooseClip')?.addEventListener('click',()=>$('#clipFile').click());
$('#convertBtn')?.addEventListener('click',async()=>{const f=$('#convertFile').files[0];if(!f)return toast('Dosya seç.');const fd=new FormData();fd.append('file',f);fd.append('target',$('#convertTarget').value);fd.append('mode',$('#convertMode').value);try{const d=await api('/api/convert',{method:'POST',body:fd});$('#convertResult').innerHTML=`✓ Hazır: ${escapeHtml(d.filename)} — <a href="${d.download_url}">Download</a>`;toast('Dönüştürme tamamlandı.')}catch(e){toast(e.message)}});
$('#clipBtn')?.addEventListener('click',async()=>{const f=$('#clipFile').files[0];if(!f)return toast('Video seç.');const fd=new FormData();fd.append('file',f);fd.append('start',$('#clipStart').value||0);fd.append('end',$('#clipEnd').value||'');try{const d=await api('/api/clip',{method:'POST',body:fd});$('#clipResult').innerHTML=`✓ Klip hazır: ${escapeHtml(d.filename)} — <a href="${d.download_url}">Download</a>`;toast('Klip oluşturuldu.')}catch(e){toast(e.message)}});

// Library
async function loadHistory(){try{const rows=await api('/api/history');renderHistory(rows)}catch(e){toast(e.message)}}
function renderHistory(rows){const q=($('#librarySearch')?.value||'').toLowerCase();const filter=$('#libraryFilter')?.value||'all';rows=rows.filter(r=>(!q||r.title.toLowerCase().includes(q)||r.url.toLowerCase().includes(q))&&(filter==='all'||r.kind===filter));$('#libraryList').innerHTML=rows.length?rows.map(r=>`<div class="library-row"><div><h4>${escapeHtml(r.title||'Video')}</h4><p>${escapeHtml(r.quality||'')} · ${escapeHtml(r.format||'')} · ${new Date(r.created_at).toLocaleString('tr-TR')}</p></div><div class="row-actions"><button data-reuse="${encodeURIComponent(r.url)}">Use again</button>${r.filename?`<button onclick="location.href='${urlForSafe(r.filename)}'">File</button>`:''}</div></div>`).join(''):'<div class="library-row"><div><h4>Library boş</h4><p>İndirmeler tamamlandığında burada görünür.</p></div></div>';$('[data-reuse]')&&$$('[data-reuse]').forEach(b=>b.onclick=()=>{$('#url').value=decodeURIComponent(b.dataset.reuse);showView('home');toast('URL workspace alanına alındı.')})}
function urlForSafe(){return '#'}
$('#librarySearch')?.addEventListener('input',loadHistory);$('#libraryFilter')?.addEventListener('change',loadHistory);$('#clearHistory')?.addEventListener('click',async()=>{try{await api('/api/history/clear',{method:'POST'});loadHistory();toast('Geçmiş temizlendi.')}catch(e){toast(e.message)}});

async function loadQueue(){for(const id of state.jobIds)pollOnce(id);renderQueue()}
function metrics(){const vals=[...state.jobs.values()];$('#metricActive').textContent=vals.filter(x=>['queued','downloading'].includes(x.status)).length;$('#metricDone').textContent=vals.filter(x=>x.status==='ready').length;$('#metricQueue').textContent=vals.length}

async function loadProfiles(){const box=$('#profileList');try{const rows=await api('/api/profiles');box.innerHTML=rows.length?rows.map(r=>`<div class="profile-card"><h3>${escapeHtml(r.name)}</h3><p>${escapeHtml(JSON.stringify(r.settings))}</p><div class="row-actions"><button data-apply-profile="${encodeURIComponent(JSON.stringify(r.settings))}">Apply</button><button data-delete-profile="${r.id}">Delete</button></div></div>`).join(''):`<div class="profile-card"><h3>Henüz preset yok</h3><p>Bir hesapla giriş yapıp kendi preset'in oluştur.</p></div>`;
 $$('#profileList [data-apply-profile]').forEach(b=>b.onclick=()=>{const s=JSON.parse(decodeURIComponent(b.dataset.applyProfile));if(s.quality)$$('#videoQualities button').forEach(x=>x.classList.toggle('active',x.dataset.q===s.quality));if(s.container)$('#container').value=s.container;if(s.mode==='audio')$('#audioFormat').value=s.audio_format||'mp3';showView('home');toast('Preset uygulandı.')});
 $$('#profileList [data-delete-profile]').forEach(b=>b.onclick=async()=>{await api('/api/profiles/'+b.dataset.deleteProfile,{method:'DELETE'});loadProfiles()});
 }catch(e){box.innerHTML='<div class="profile-card"><h3>Login gerekli</h3><p>Presets hesabına bağlıdır.</p></div>'}}
$('#newProfile')?.addEventListener('click',async()=>{const name=prompt('Preset adı?','My Phone');if(!name)return;try{await api('/api/profiles',{...jsonOpts(),method:'POST',body:JSON.stringify({name,settings:{quality:selectedQuality(),container:$('#container').value,mode:$('#audioFormat').value?'audio':'video',audio_format:$('#audioFormat').value||''}})});loadProfiles();toast('Preset oluşturuldu.')}catch(e){toast(e.message)}});

// Account
async function loadMe(){try{const d=await api('/api/me');const u=d.user;$('#accountLabel').textContent=u?u.email.split('@')[0]:'Guest';$('.avatar').textContent=u?'U':'G';}catch(e){}}
$('#accountButton')?.addEventListener('click',async()=>{const m=await api('/api/me');if(!m.user){$('#modalInner').innerHTML=`<button class="modal-close" id="modalClose">×</button><h3>Vidora account</h3><p>Library, presets ve API için giriş yap.</p><div class="row-actions"><a class="ghost-btn" href="/login">Login</a><a class="primary-btn" href="/register">Create account</a></div>`}else{$('#modalInner').innerHTML=`<button class="modal-close" id="modalClose">×</button><h3>${escapeHtml(m.user.email)}</h3><p>Role: ${escapeHtml(m.user.role)}</p><div class="row-actions"><button class="ghost-btn" id="logoutBtn">Logout</button></div>`;$('#logoutBtn').onclick=async()=>{await api('/logout',{method:'POST'});location.reload()}}$('#modal').classList.add('open');$('#modalClose').onclick=()=>$('#modal').classList.remove('open')});
$('#modal')?.addEventListener('click',e=>{if(e.target.id==='modal')e.currentTarget.classList.remove('open')});

// Share
$('#shareBtn')?.addEventListener('click',async()=>{const ids=[...state.jobs.values()].filter(j=>j.status==='ready');const j=ids[ids.length-1];if(!j)return toast('Önce bir indirme tamamla.');try{const d=await api('/api/share/'+j.id,{...jsonOpts(),method:'POST',body:JSON.stringify({hours:1,max_downloads:10})});await navigator.clipboard?.writeText(d.url);$('#modalInner').innerHTML=`<h3>Temporary share</h3><p>1 saat geçerli · ${d.max_downloads} indirme.</p><input class="mini-input" value="${escapeHtml(d.url)}" readonly><p><a href="${d.url}" target="_blank">Bağlantıyı aç</a></p><img src="/api/qr?data=${encodeURIComponent(d.url)}" style="width:180px;height:180px;border-radius:12px;background:#fff;padding:8px" alt="QR"><p><a href="/api/qr?data=${encodeURIComponent(d.url)}" download>QR indir</a></p>`;$('#modal').classList.add('open')}catch(e){toast(e.message)}});

// Theme/settings
$('#themeButton')?.addEventListener('click',()=>applyTheme(state.theme==='dark'?'system':state.theme==='system'?'light':'dark'));
$('#themeSelect')?.addEventListener('change',e=>applyTheme(e.target.value));
$('#compactMode')?.addEventListener('change',e=>{document.documentElement.classList.toggle('compact-mode',e.target.checked);state.settings.compact=e.target.checked;localStorage.setItem('vidora_settings',JSON.stringify(state.settings))});

// Command palette
const commands=[['Download video','home'],['My library','library'],['Queue','queue'],['Tools','tools'],['Presets','profiles'],['Settings','settings'],['Batch Lab','batch'],['Playlist Lab','playlist']];
function renderCommands(q=''){const res=$('#commandResults');res.innerHTML=commands.filter(c=>c[0].toLowerCase().includes(q.toLowerCase())).map((c,i)=>`<div class="command-item" data-cmd="${c[1]}">${c[0]} <span style="margin-left:auto;color:#555">${i+1}</span></div>`).join('');$$('[data-cmd]').forEach(x=>x.onclick=()=>{const cmd=x.dataset.cmd;$('#commandOverlay').classList.remove('open');if(cmd==='batch'){showView('tools');openBatch()}else if(cmd==='playlist'){showView('tools');openPlaylist()}else showView(cmd)})}
function openCommand(){renderCommands();$('#commandOverlay').classList.add('open');$('#commandInput').value='';setTimeout(()=>$('#commandInput').focus(),40)}
$('#closeCommand')?.addEventListener('click',()=>$('#commandOverlay').classList.remove('open'));$('#commandInput')?.addEventListener('input',e=>renderCommands(e.target.value));$('#commandOverlay')?.addEventListener('click',e=>{if(e.target.id==='commandOverlay')e.currentTarget.classList.remove('open')});

window.addEventListener('keydown',e=>{
 const mod=e.ctrlKey||e.metaKey;if(mod&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand()}if(e.key==='Escape'){$('#commandOverlay')?.classList.remove('open');$('#modal')?.classList.remove('open')}if(!mod&&e.key.toLowerCase()==='d'&&state.view==='home'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();startDownload()}}
);

// PWA
if('serviceWorker' in navigator){navigator.serviceWorker.register('/assets/sw.js?v=4.1').then(r=>r.update()).catch(()=>{});}

// Load persisted state
const last=localStorage.getItem('vidora_last_url');if(last)$('#url').value=last;$('#compactMode').checked=!!state.settings.compact;document.documentElement.classList.toggle('compact-mode',!!state.settings.compact);loadMe();renderQueue();metrics();
