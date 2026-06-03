/* ═══════════════════════════════════════════════════
   RusLearn Pro — app.js  (asosiy JavaScript logikasi)
   ═══════════════════════════════════════════════════ */
"use strict";

// ── Global holat ─────────────────────────────────
const State = {
  profile: {},
  settings: {},
  internetAllowed: true,
  currentPage: "home",
  words: [],
  wordOffset: 0,
  wordLimit: 24,
  wordTotal: 0,
  fcCards: [],
  fcIndex: 0,
  fcCorrect: 0,
  fcWrong: 0,
  fcFlipped: false,
  fcSessionStart: null,
  grammar: [],
  currentGrammarItem: null,
  quizQuestions: [],
  quizIndex: 0,
  quizScore: 0,
  quizAnswers: [],
  game: { type: null, score: 0, timer: null, timeLeft: 60, words: [], index: 0 },
  scheduleList: [],
  historyList: [],
  searchTimer: null,
  chartInstance: null,
};


// ── Yordamchi funksiyalar ────────────────────────
function $(id){ return document.getElementById(id); }
function toast(msg, type="info", dur=3000){
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast ${type} show`;
  clearTimeout(t._t);
  t._t = setTimeout(()=>{ t.className="toast"; }, dur);
}
function fmt(dt){
  if(!dt) return "—";
  const d = new Date(dt.replace(" ","T"));
  return d.toLocaleString("uz-UZ",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});
}
function fmtDate(dt){
  if(!dt) return "—";
  const d = new Date(dt.replace(" ","T"));
  return d.toLocaleDateString("uz-UZ",{day:"2-digit",month:"long",year:"numeric"});
}
function fmtTime(dt){
  if(!dt) return "—";
  const d = new Date(dt.replace(" ","T"));
  return d.toLocaleTimeString("uz-UZ",{hour:"2-digit",minute:"2-digit"});
}
function timeAgo(dt){
  if(!dt) return "";
  const diff = (Date.now() - new Date(dt.replace(" ","T")).getTime())/1000;
  if(diff < 60) return "hozirgina";
  if(diff < 3600) return `${Math.round(diff/60)} daqiqa oldin`;
  if(diff < 86400) return `${Math.round(diff/3600)} soat oldin`;
  return `${Math.round(diff/86400)} kun oldin`;
}
function levelEmoji(lvl){
  return {beginner:"🟢",intermediate:"🟡",advanced:"🔴"}[lvl]||"⚪";
}
function lessonTypeEmoji(t){
  return {vocabulary:"📖",grammar:"📝",flashcards:"🃏",quiz:"❓",chat:"🤖",game:"🎮"}[t]||"📚";
}
function statusLabel(s){
  const m={pending:"Kutilmoqda",completed:"Tugallandi",started:"Boshlandi",missed:"O'tkazildi"};
  return m[s]||s;
}
function secToMin(s){ return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`; }
async function api(url, opts={}){
  try{
    const r = await fetch(url, {headers:{"Content-Type":"application/json"}, ...opts});
    return await r.json();
  } catch(e){ return {error: e.message}; }
}
function closeModal(id){ $(id).style.display="none"; }
function openModal(id){ $(id).style.display="flex"; }


// ── Navigatsiya ──────────────────────────────────
function navigate(page){
  document.querySelectorAll(".page").forEach(p=>p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n=>n.classList.remove("active"));
  const pg = $(`page-${page}`);
  if(pg) pg.classList.add("active");
  const nb = document.querySelector(`.nav-item[data-page="${page}"]`);
  if(nb) nb.classList.add("active");
  State.currentPage = page;
  window.scrollTo(0,0);
  // Sahifaga mos ma'lumot yuklash
  const loaders = {
    home: loadHome,
    vocabulary: loadVocabulary,
    flashcards: ()=>{},
    grammar: loadGrammar,
    games: loadGameHighscores,
    quiz: ()=>{},
    chat: loadChatHistory,
    schedule: loadSchedule,
    progress: loadProgress,
    settings: loadSettings,
  };
  if(loaders[page]) loaders[page]();
}

document.querySelectorAll(".nav-item[data-page]").forEach(btn=>{
  btn.addEventListener("click",()=>navigate(btn.dataset.page));
});


// ── Profil va sidebar ────────────────────────────
async function loadProfile(){
  const p = await api("/api/profile");
  if(p.error) return;
  State.profile = p;
  $("profileName").textContent = p.name||"O'quvchi";
  $("profileXP").textContent = p.total_xp||0;
  $("profileStreak").textContent = p.streak_days||0;
  const av = $("profileAvatar");
  av.textContent = (p.name||"O")[0].toUpperCase();

  // Missed badge
  const missed = p.missed_lessons||0;
  const mb = $("missedBadge");
  if(mb) mb.style.display = missed>0 ? "inline-block" : "none";
}

async function loadSettings(){
  const s = await api("/api/settings");
  if(s.error) return;
  State.settings = s;
  if($("sName")) $("sName").value = State.profile.name||"";
  if($("sLevel")) $("sLevel").value = State.profile.level||"beginner";
  if($("sNotifMin")) $("sNotifMin").value = s.notification_before_min||"30";
  if($("sDailyGoal")) $("sDailyGoal").value = s.daily_goal_min||"30";
  if($("sAiLevel")) $("sAiLevel").value = s.ai_conversation_level||"beginner";
  updateInternetUI(s.internet_allowed!=="off");
  loadDownloadStats();
  loadOfflineStats();
}

async function saveProfile(){
  const name = $("sName").value.trim()||"O'quvchi";
  const level = $("sLevel").value;
  await api("/api/profile",{method:"POST",body:JSON.stringify({name,level})});
  await loadProfile();
  toast("✅ Profil saqlandi","success");
}

async function saveNotifSettings(){
  const notif = $("sNotifMin").value;
  const goal = $("sDailyGoal").value;
  await api("/api/settings",{method:"POST",body:JSON.stringify({
    notification_before_min: notif,
    daily_goal_min: goal,
  })});
  toast("✅ Saqlandi","success");
}

async function saveAiSettings(){
  const lvl = $("sAiLevel").value;
  await api("/api/settings",{method:"POST",body:JSON.stringify({ai_conversation_level:lvl})});
  toast("✅ AI sozlamalari saqlandi","success");
}

async function savePassword(){
  const pwd = $("sPassword").value;
  await api("/api/auth/set-password",{method:"POST",body:JSON.stringify({password:pwd})});
  $("sPassword").value="";
  toast(pwd?"✅ Parol o'rnatildi":"✅ Parol o'chirildi","success");
}

async function testNotif(){
  await api("/api/notify/test",{method:"POST"});
  toast("🔔 Test xabarnoma yuborildi","info");
}

function openNotifTest(){ testNotif(); }


// ── Internet toggle ──────────────────────────────
async function toggleInternet(){
  const r = await api("/api/internet/status");
  const newState = !(r.allowed);
  await api("/api/internet/toggle",{method:"POST",body:JSON.stringify({allowed:newState})});
  updateInternetUI(newState);
  toast(newState?"🌐 Internet yoqildi":"🚫 Internet o'chirildi", newState?"success":"warn");
  State.internetAllowed = newState;
}

function updateInternetUI(allowed){
  State.internetAllowed = allowed;
  const btn = $("netToggleBtn");
  const icon = $("netIcon");
  const label = $("netLabel");
  const togBtn = $("internetToggleBtn");
  const togLabel = $("internetToggleLabel");
  if(btn){
    btn.className = `net-toggle-btn${allowed?"":" blocked"}`;
    if(icon) icon.textContent = allowed?"🌐":"🚫";
    if(label) label.textContent = allowed?"Internet: ON":"Internet: OFF";
  }
  if(togBtn){
    togBtn.className = `toggle-btn${allowed?"":" off"}`;
    if(togLabel) togLabel.textContent = allowed?"ON":"OFF";
  }
}

async function loadOfflineStats(){
  const st = await api("/api/downloads/stats");
  const el = $("offlineStats");
  if(el && st){
    el.innerHTML=`<div style="font-size:12px;color:var(--text2)">
      📖 Lug'at: <b>${st.words_dl||0}</b>/${st.total_words||0} yuklab olingan<br>
      📝 Grammatika: <b>${st.grammar_dl||0}</b>/${st.total_grammar||0} yuklab olingan
    </div>`;
  }
}

async function loadDownloadStats(){
  const st = await api("/api/downloads/stats");
  const el = $("downloadStats");
  if(!el||!st) return;
  const wpct = st.total_words>0?Math.round(st.words_dl/st.total_words*100):0;
  const gpct = st.total_grammar>0?Math.round(st.grammar_dl/st.total_grammar*100):0;
  el.innerHTML=`
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text2);margin-bottom:4px">
        <span>📖 So'zlar</span><span>${st.words_dl||0}/${st.total_words||0}</span>
      </div>
      <div style="background:var(--bg3);border-radius:99px;height:6px;overflow:hidden">
        <div style="height:100%;width:${wpct}%;background:var(--green);border-radius:99px"></div>
      </div>
    </div>
    <div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text2);margin-bottom:4px">
        <span>📝 Grammatika</span><span>${st.grammar_dl||0}/${st.total_grammar||0}</span>
      </div>
      <div style="background:var(--bg3);border-radius:99px;height:6px;overflow:hidden">
        <div style="height:100%;width:${gpct}%;background:var(--accent);border-radius:99px"></div>
      </div>
    </div>`;
}

async function downloadAllContent(){
  toast("⬇ Yuklanmoqda...","info");
  const r = await api("/api/downloads/all-words",{method:"POST"});
  if(r.ok){ toast(`✅ ${r.count} ta kontent yuklab olindi`,"success"); loadDownloadStats(); }
  else toast("❌ Xatolik: "+r.error,"error");
}


// ══════════════════════════════════════════════════
// HOME PAGE
// ══════════════════════════════════════════════════
async function loadHome(){
  const stats = await api("/api/stats");
  if(stats.error) return;

  // Stats cards
  const goal = parseInt(State.settings.daily_goal_min||"30");
  const todayMin = Math.round(stats.today_min||0);
  const pct = Math.min(100, Math.round(todayMin/goal*100));

  $("homeStats").innerHTML = `
    <div class="stat-card"><div class="stat-val">${stats.total_words||0}</div><div class="stat-lbl">📖 Jami so'zlar</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--green)">${stats.learned_words||0}</div><div class="stat-lbl">✅ O'rganilgan</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--yellow)">${stats.due_reviews||0}</div><div class="stat-lbl">🔁 Takrorlash</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--purple)">${stats.streak_days||0}</div><div class="stat-lbl">🔥 Streak kun</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--orange)">${stats.total_xp||0}</div><div class="stat-lbl">⭐ XP</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--accent)">${stats.week_xp||0}</div><div class="stat-lbl">📈 Haftalik XP</div></div>
  `;

  // Daily goal bar
  $("dailyGoalBar").style.width = pct+"%";
  $("dailyGoalLabel").textContent = `${todayMin} / ${goal} daqiqa (${pct}%)`;

  // Due reviews section
  const dueEl = $("dueReviewSection");
  if(stats.due_reviews>0){
    dueEl.innerHTML = `
      <div class="due-card">
        <span style="font-size:20px">🔁</span>
        <div style="flex:1"><div style="font-weight:600">${stats.due_reviews} ta so'z takrorlashni kutmoqda</div>
        <div style="font-size:11px;color:var(--text3)">Takrorlash yadingizni mustahkamlaydi!</div></div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="navigate('flashcards')">▶ Takrorlashni boshlash</button>`;
  } else {
    dueEl.innerHTML = `<p class="muted">✅ Bugun barcha takrorlashlar tugadi!</p>`;
  }

  // Upcoming lessons
  const sched = await api("/api/schedule?days=3");
  const upEl = $("upcomingSection");
  if(sched.length){
    upEl.innerHTML = sched.slice(0,4).map(l=>`
      <div class="upcoming-item">
        <span>${lessonTypeEmoji(l.lesson_type)}</span>
        <span class="upcoming-time">${fmtTime(l.scheduled_at)}, ${fmtDate(l.scheduled_at)}</span>
        <span style="flex:1;font-size:12px">${l.title}</span>
        <span class="lesson-status status-${l.status}">${statusLabel(l.status)}</span>
      </div>`).join("");
  } else {
    upEl.innerHTML=`<p class="muted">📅 Kelgusi darslar yo'q. <button class="btn btn-ghost btn-sm" onclick="navigate('schedule')">Qo'shish</button></p>`;
  }

  // Missed lessons
  const missed = await api("/api/schedule/missed");
  const missEl = $("missedSection");
  const missListEl = $("missedList");
  if(missed.length){
    missEl.style.display="block";
    missListEl.innerHTML = missed.slice(0,3).map(l=>`
      <div class="lesson-item" style="background:rgba(240,80,96,0.07);border-radius:8px;margin-bottom:6px">
        <span class="lesson-type-badge">${lessonTypeEmoji(l.lesson_type)}</span>
        <div class="lesson-info">
          <div class="lesson-title">${l.title}</div>
          <div class="lesson-meta">${fmt(l.scheduled_at)} · ${l.duration_min} daqiqa</div>
        </div>
        <button class="btn btn-sm btn-primary" onclick="startLessonNow(${l.id},'${l.lesson_type}')">▶ Boshlash</button>
      </div>`).join("");
  } else {
    missEl.style.display="none";
  }

  // Continue section
  const contEl = $("continueSection");
  const todayLessons = sched.filter(l=>l.status==="started"||l.status==="pending");
  if(todayLessons.length){
    const l = todayLessons[0];
    contEl.innerHTML=`
      <div class="lesson-title">${l.title}</div>
      <div class="lesson-meta" style="margin:6px 0">${fmtTime(l.scheduled_at)} · ${l.duration_min} daqiqa</div>
      <button class="btn btn-primary btn-sm" onclick="startLessonNow(${l.id},'${l.lesson_type}')">▶ Davom ettirish</button>`;
  } else {
    contEl.innerHTML=`<p class="muted">Bugun uchun dars yo'q.</p>`;
  }
}

function startLessonNow(id, type){
  api(`/api/schedule/${id}`,{method:"PUT",body:JSON.stringify({status:"started"})});
  const pageMap = {vocabulary:"vocabulary",grammar:"grammar",flashcards:"flashcards",quiz:"quiz",chat:"chat",game:"games"};
  navigate(pageMap[type]||"home");
  toast("▶ Dars boshlandi!","success");
}


// ══════════════════════════════════════════════════
// VOCABULARY PAGE
// ══════════════════════════════════════════════════
async function loadVocabulary(){
  const level = $("wordLevelFilter")?.value||"";
  const cat = $("wordCatFilter")?.value||"";
  const q = $("wordSearch")?.value.trim()||"";
  let words;
  if(q.length>1){
    words = await api(`/api/words/search?q=${encodeURIComponent(q)}`);
  } else {
    words = await api(`/api/words?level=${level}&category=${cat}&limit=${State.wordLimit}&offset=${State.wordOffset}`);
  }
  if(words.error){ toast("❌ Yuklab bo'lmadi","error"); return; }
  State.words = words;
  renderWordGrid(words);
  await loadWordCategories();
}

async function loadWordCategories(){
  const cats = await api("/api/words/categories");
  const sel = $("wordCatFilter");
  if(!sel||!cats) return;
  const cur = sel.value;
  const catNames = {general:"Umumiy",greeting:"Salomlashish",numbers:"Raqamlar",colors:"Ranglar",family:"Oila",food:"Oziq-ovqat",verbs:"Fe'llar",adjectives:"Sifatlar",travel:"Sayohat",work:"Ish",health:"Sog'liq",nature:"Tabiat",time:"Vaqt",emotions:"His-tuyg'ular",shopping:"Xarid"};
  const opts = cats.map(c=>`<option value="${c}"${c===cur?" selected":""}>${catNames[c]||c}</option>`).join("");
  sel.innerHTML=`<option value="">Barcha kategoriyalar</option>${opts}`;
}

function renderWordGrid(words){
  const grid = $("wordGrid");
  if(!words.length){
    grid.innerHTML=`<div class="empty-state"><div class="empty-icon">📭</div><p>So'z topilmadi</p></div>`;
    $("wordCount").textContent="";
    return;
  }
  $("wordCount").textContent=`${words.length} ta so'z topildi`;
  grid.innerHTML = words.map(w=>`
    <div class="word-card" id="wcard-${w.id}">
      <div class="wc-top">
        <div class="wc-russian">${w.russian}</div>
        <span class="wc-level level-${w.level}">${levelEmoji(w.level)}</span>
      </div>
      <div class="wc-uzbek">${w.uzbek}</div>
      ${w.pronunciation?`<div class="wc-pron">🔊 ${w.pronunciation}</div>`:""}
      ${w.example_ru?`<div class="wc-example"><i>${w.example_ru}</i><br><span style="color:var(--text3)">${w.example_uz||""}</span></div>`:""}
      <div class="wc-actions">
        <span class="wc-cat">${w.category||"umumiy"}</span>
        ${w.edited_by_user?`<span class="wc-edited">✏️ tahrirlangan</span>`:""}
        <button class="btn btn-sm btn-ghost" onclick="openEditWord(${w.id})" style="margin-left:auto">✏️</button>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text3);margin-top:8px">
        <span>✅ ${w.times_correct||0} · ❌ ${w.times_wrong||0}</span>
        <span>Keyingi: ${fmtDate(w.next_review)}</span>
      </div>
    </div>`).join("");
}

function debounceWordSearch(){
  clearTimeout(State.searchTimer);
  State.searchTimer = setTimeout(()=>{ State.wordOffset=0; loadVocabulary(); }, 350);
}

function openAddWordModal(){ openModal("addWordModal"); }

async function aiTranslateWord(){
  const ru = $("awRu").value.trim();
  if(!ru){ toast("Ruscha so'z kiriting","warn"); return; }
  if(!State.internetAllowed){ toast("Internet o'chiq","warn"); return; }
  toast("🤖 AI tarjima qilmoqda...","info");
  const r = await api("/api/ai/translate",{method:"POST",body:JSON.stringify({word:ru})});
  if(r.ok){
    if(r.uzbek) $("awUz").value = r.uzbek;
    if(r.pronunciation) $("awPron").value = r.pronunciation;
    if(r.example_ru) $("awExRu").value = r.example_ru;
    if(r.example_uz) $("awExUz").value = r.example_uz;
    toast("✅ AI tarjima qildi","success");
  } else toast("❌ AI xatosi: "+(r.error||""),"error");
}

async function submitAddWord(){
  const ru = $("awRu").value.trim();
  const uz = $("awUz").value.trim();
  if(!ru||!uz){ toast("Ruscha va o'zbekcha maydonlar to'ldirilishi shart","warn"); return; }
  const r = await api("/api/words",{method:"POST",body:JSON.stringify({
    russian:ru, uzbek:uz, pronunciation:$("awPron").value,
    example_ru:$("awExRu").value, example_uz:$("awExUz").value,
    category:$("awCat").value, level:$("awLevel").value,
  })});
  if(r.ok){
    toast("✅ So'z qo'shildi!","success");
    closeModal("addWordModal");
    ["awRu","awUz","awPron","awExRu","awExUz"].forEach(id=>$(id).value="");
    loadVocabulary();
  } else toast("❌ Xatolik","error");
}

async function openEditWord(id){
  const w = await api(`/api/words/${id}`);
  if(!w||w.error){ toast("Topilmadi","error"); return; }
  $("ewId").value=w.id;
  $("ewRu").value=w.russian;
  $("ewUz").value=w.uzbek;
  $("ewPron").value=w.pronunciation||"";
  $("ewExRu").value=w.example_ru||"";
  $("ewExUz").value=w.example_uz||"";
  openModal("editWordModal");
}

async function submitEditWord(){
  const id = $("ewId").value;
  const r = await api(`/api/words/${id}`,{method:"PUT",body:JSON.stringify({
    russian:$("ewRu").value.trim(), uzbek:$("ewUz").value.trim(),
    pronunciation:$("ewPron").value, example_ru:$("ewExRu").value, example_uz:$("ewExUz").value,
  })});
  if(r.ok){ toast("✅ Saqlandi","success"); closeModal("editWordModal"); loadVocabulary(); }
  else toast("❌ Xatolik","error");
}

function openAIFetchModal(){ openModal("aiFetchModal"); }

async function doAIFetch(){
  if(!State.internetAllowed){ toast("Internet o'chiq","warn"); return; }
  const cat = $("aiFetchCat").value;
  const lvl = $("aiFetchLevel").value;
  const cnt = parseInt($("aiFetchCount").value)||10;
  const btn = $("aiFetchBtn");
  btn.disabled=true; btn.textContent="⏳ Yuklanmoqda...";
  toast("🤖 AI so'zlar generatsiya qilmoqda...","info",8000);
  const r = await api("/api/ai/fetch-words",{method:"POST",body:JSON.stringify({category:cat,level:lvl,count:cnt})});
  btn.disabled=false; btn.textContent="🤖 Yuklash";
  if(r.ok){ toast(`✅ ${r.added} ta yangi so'z qo'shildi!`,"success"); closeModal("aiFetchModal"); loadVocabulary(); }
  else toast("❌ "+(r.error||"AI xatosi"),"error");
}


// ══════════════════════════════════════════════════
// FLASHCARDS (Spaced Repetition)
// ══════════════════════════════════════════════════
async function startFlashcards(){
  const level = $("fcLevel")?.value||"";
  const dueOnly = $("fcDueOnly")?.checked;
  const words = await api(`/api/words?level=${level}&limit=30&due_only=${dueOnly}`);
  if(!words||!words.length){ toast("O'rganish uchun so'z topilmadi","warn"); return; }

  State.fcCards = words.sort(()=>Math.random()-0.5);
  State.fcIndex=0; State.fcCorrect=0; State.fcWrong=0;
  State.fcSessionStart = Date.now();

  $("flashcardArea").style.display="block";
  $("fcResult").style.display="none";
  showFlashcard();
}

function showFlashcard(){
  const card = State.fcCards[State.fcIndex];
  if(!card){ endFlashcards(); return; }

  // Progress
  const pct = Math.round(State.fcIndex/State.fcCards.length*100);
  $("fcProgFill").style.width = pct+"%";
  $("fcProgLabel").textContent = `${State.fcIndex+1} / ${State.fcCards.length}`;

  // Reset flip
  const inner = $("fcInner");
  inner.classList.remove("flipped");
  State.fcFlipped=false;
  $("fcButtons").style.display="none";

  // Fill content
  $("fcWord").textContent = card.russian;
  $("fcHint").textContent = "Kartochkani bosing — tarjimani ko'ring";
  $("fcPron").textContent = card.pronunciation||"";
  $("fcTranslation").textContent = card.uzbek;
  $("fcExample").textContent = card.example_ru||"";
  $("fcExampleUz").textContent = card.example_uz||"";
}

function flipCard(){
  if(State.fcFlipped) return;
  State.fcFlipped=true;
  $("fcInner").classList.add("flipped");
  $("fcButtons").style.display="flex";
}

async function answerCard(correct){
  const card = State.fcCards[State.fcIndex];
  if(!card) return;
  await api(`/api/words/${card.id}/review`,{method:"POST",body:JSON.stringify({correct})});
  if(correct) State.fcCorrect++; else State.fcWrong++;
  State.fcIndex++;
  if(State.fcIndex>=State.fcCards.length) endFlashcards();
  else showFlashcard();
}

function fcSkip(){
  State.fcIndex++;
  if(State.fcIndex>=State.fcCards.length) endFlashcards();
  else showFlashcard();
}

function stopFlashcards(){
  endFlashcards();
}

async function endFlashcards(){
  $("flashcardArea").style.display="none";
  const elapsed = Math.round((Date.now()-State.fcSessionStart)/1000);
  const xp = State.fcCorrect*10+State.fcWrong*2;
  const total = State.fcCorrect+State.fcWrong;
  const pct = total>0?Math.round(State.fcCorrect/total*100):0;
  await api("/api/history",{method:"POST",body:JSON.stringify({
    lesson_type:"flashcards",duration_sec:elapsed,score:pct,xp_earned:xp,
    details:{correct:State.fcCorrect,wrong:State.fcWrong,total}
  })});
  $("fcResultStats").innerHTML=`
    <div style="display:flex;gap:24px;justify-content:center;margin:16px 0">
      <div><div style="font-size:28px;font-weight:700;color:var(--green)">${State.fcCorrect}</div><div style="font-size:12px;color:var(--text2)">To'g'ri</div></div>
      <div><div style="font-size:28px;font-weight:700;color:var(--red)">${State.fcWrong}</div><div style="font-size:12px;color:var(--text2)">Noto'g'ri</div></div>
      <div><div style="font-size:28px;font-weight:700;color:var(--accent)">${pct}%</div><div style="font-size:12px;color:var(--text2)">Natija</div></div>
      <div><div style="font-size:28px;font-weight:700;color:var(--yellow)">${xp}</div><div style="font-size:12px;color:var(--text2)">XP</div></div>
    </div>
    <p style="color:var(--text2);font-size:13px">Sarflangan vaqt: ${secToMin(elapsed)}</p>`;
  $("fcResult").style.display="block";
  await loadProfile();
  toast(`🎉 ${xp} XP qo'shildi!`,"success");
}


// ══════════════════════════════════════════════════
// GRAMMAR PAGE
// ══════════════════════════════════════════════════
let _grammarLevel = "all";

async function loadGrammar(){
  const lvl = _grammarLevel==="all"?"":_grammarLevel;
  const rules = await api(`/api/grammar${lvl?`?level=${lvl}`:""}`);
  if(!rules||rules.error) return;
  State.grammar=rules;
  const list=$("grammarList");
  if(!rules.length){
    list.innerHTML=`<div class="empty-state"><div class="empty-icon">📝</div><p>Grammatika qoidalari topilmadi</p></div>`;
    return;
  }
  list.innerHTML=rules.map(r=>`
    <div class="grammar-card" id="gc-${r.id}" onclick="openGrammarDetail(${r.id})">
      <div class="gc-top">
        <div>
          <div class="gc-title">${r.title}</div>
          <div class="gc-preview">${r.content}</div>
        </div>
        <span class="wc-level level-${r.level}">${levelEmoji(r.level)}</span>
      </div>
      <div class="gc-actions">
        <span class="wc-cat">${r.category||""}</span>
        <button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();openGrammarEditById(${r.id})">✏️</button>
      </div>
    </div>`).join("");
}

function filterGrammar(lvl, el){
  _grammarLevel=lvl;
  document.querySelectorAll(".g-tab").forEach(t=>t.classList.remove("active"));
  if(el) el.classList.add("active");
  loadGrammar();
}

async function openGrammarDetail(id){
  const r = await api(`/api/grammar/${id}`);
  if(!r||r.error) return;
  State.currentGrammarItem=r;
  let ex=[];
  try{ ex=JSON.parse(r.examples_json||"[]"); }catch(e){}
  let exHTML="";
  if(ex.length){
    exHTML=`<div class="grammar-examples"><h4>Misollar</h4>${ex.map(e=>`
      <div class="ge-item"><div class="ge-ru">${e.ru}</div><div class="ge-uz">${e.uz}</div></div>`).join("")}</div>`;
  }
  let exercises=[];
  try{ exercises=JSON.parse(r.exercises_json||"[]"); }catch(e){}
  let exerHTML="";
  if(exercises.length){
    exerHTML=`<div style="margin-top:16px"><h4 style="font-size:13px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">Mashqlar</h4>
    ${exercises.map((q,i)=>`
      <div style="background:var(--bg3);border-radius:8px;padding:12px;margin-bottom:8px">
        <div style="font-weight:600;margin-bottom:8px">${i+1}. ${q.q}</div>
        ${q.options?q.options.map(o=>`<button class="fill-opt" onclick="checkGrammarAnswer(this,'${o}','${q.a}')">${o}</button>`).join("")
          :`<input class="form-input" placeholder="Javob..." onkeydown="if(event.key==='Enter')checkGrammarTextAnswer(this,'${q.a}')">`}
      </div>`).join("")}
    </div>`;
  }
  $("grammarModalContent").innerHTML=`
    <div class="grammar-detail-title">${r.title} <span class="wc-level level-${r.level}">${levelEmoji(r.level)}</span></div>
    <div class="grammar-detail-body">${r.content}</div>
    ${exHTML}${exerHTML}`;
  openModal("grammarModal");
}

function checkGrammarAnswer(btn, chosen, correct){
  const parent=btn.parentElement;
  parent.querySelectorAll(".fill-opt").forEach(b=>b.disabled=true);
  btn.classList.add(chosen===correct?"correct":"wrong");
  if(chosen!==correct){
    parent.querySelectorAll(".fill-opt").forEach(b=>{ if(b.textContent===correct) b.classList.add("correct"); });
  }
}
function checkGrammarTextAnswer(inp, correct){
  const val=inp.value.trim().toLowerCase();
  const ok=val===correct.toLowerCase();
  inp.style.borderColor=ok?"var(--green)":"var(--red)";
  inp.disabled=true;
  const hint=document.createElement("div");
  hint.style.cssText="font-size:12px;margin-top:4px";
  hint.style.color=ok?"var(--green)":"var(--red)";
  hint.textContent=ok?"✅ To'g'ri!":"❌ To'g'ri javob: "+correct;
  inp.after(hint);
}

function openGrammarEdit(){
  if(!State.currentGrammarItem) return;
  openGrammarEditById(State.currentGrammarItem.id);
}

async function openGrammarEditById(id){
  const r = State.grammar.find(g=>g.id===id)||await api(`/api/grammar/${id}`);
  if(!r) return;
  $("geId").value=r.id;
  $("geTitle").value=r.title;
  $("geContent").value=r.content;
  closeModal("grammarModal");
  openModal("grammarEditModal");
}

async function submitGrammarEdit(){
  const id=$("geId").value;
  const r=await api(`/api/grammar/${id}`,{method:"PUT",body:JSON.stringify({
    title:$("geTitle").value.trim(),content:$("geContent").value.trim()
  })});
  if(r.ok){ toast("✅ Grammatika yangilandi","success"); closeModal("grammarEditModal"); loadGrammar(); }
  else toast("❌ Xatolik","error");
}

function openAIGrammarModal(){ openModal("aiGrammarModal"); }

async function doAIGrammar(){
  if(!State.internetAllowed){ toast("Internet o'chiq","warn"); return; }
  const topic=$("aiGrammarTopic").value.trim();
  if(!topic){ toast("Mavzu kiriting","warn"); return; }
  const btn=$("aiGrammarBtn");
  btn.disabled=true; btn.textContent="⏳...";
  const r=await api("/api/ai/explain-grammar",{method:"POST",body:JSON.stringify({topic})});
  btn.disabled=false; btn.textContent="🤖 Tushuntir";
  if(r.ok){
    const res=$("aiGrammarResult");
    res.style.display="block";
    res.textContent=r.explanation;
    toast("✅ AI tushuntirdi","success");
  } else toast("❌ "+(r.error||"AI xatosi"),"error");
}


// ══════════════════════════════════════════════════
// QUIZ PAGE
// ══════════════════════════════════════════════════
async function startQuiz(){
  const level = document.querySelector('input[name="quizLevel"]:checked')?.value||"";
  const count = parseInt(document.querySelector('input[name="quizCount"]:checked')?.value||"10");
  const qtype = document.querySelector('input[name="quizType"]:checked')?.value||"ru_to_uz";

  const words = await api(`/api/words?level=${level}&limit=100`);
  if(!words||words.length<4){ toast("Kamida 4 ta so'z kerak","warn"); return; }

  const shuffled = words.sort(()=>Math.random()-0.5).slice(0,count);
  State.quizQuestions = shuffled.map(w=>{
    const type = qtype==="mixed"?(Math.random()<0.5?"ru_to_uz":"uz_to_ru"):qtype;
    const question = type==="ru_to_uz"?w.russian:w.uzbek;
    const correctAns = type==="ru_to_uz"?w.uzbek:w.russian;
    const wrong = words.filter(x=>x.id!==w.id).sort(()=>Math.random()-0.5).slice(0,3)
      .map(x=>type==="ru_to_uz"?x.uzbek:x.russian);
    const choices = [...wrong,correctAns].sort(()=>Math.random()-0.5);
    return {id:w.id, question, correctAns, choices, type, word:w};
  });
  State.quizIndex=0; State.quizScore=0; State.quizAnswers=[];

  $("quizSetup").style.display="none";
  $("quizResult").style.display="none";
  $("quizPlay").style.display="block";
  showQuizQuestion();
}

function showQuizQuestion(){
  const q = State.quizQuestions[State.quizIndex];
  if(!q){ endQuiz(); return; }
  const total=State.quizQuestions.length;
  const pct=Math.round(State.quizIndex/total*100);
  $("quizProgFill").style.width=pct+"%";
  $("quizProgLabel").textContent=`${State.quizIndex+1}/${total}`;
  $("quizScoreLabel").textContent=`${State.quizScore} ball`;
  $("quizQuestion").textContent=q.question;
  $("quizFeedback").style.display="none";
  $("quizChoices").innerHTML=q.choices.map((c,i)=>`
    <button class="quiz-choice" onclick="answerQuiz(this,'${c.replace(/'/g,"\\'")}')">${c}</button>`).join("");
}

function answerQuiz(btn, chosen){
  const q=State.quizQuestions[State.quizIndex];
  document.querySelectorAll(".quiz-choice").forEach(b=>b.disabled=true);
  const correct=chosen===q.correctAns;
  btn.classList.add(correct?"correct":"wrong");
  if(!correct){
    document.querySelectorAll(".quiz-choice").forEach(b=>{
      if(b.textContent===q.correctAns) b.classList.add("correct");
    });
  }
  if(correct){ State.quizScore+=10; api(`/api/words/${q.id}/review`,{method:"POST",body:JSON.stringify({correct:true})}); }
  State.quizAnswers.push({...q,chosen,correct});

  const fb=$("quizFeedback");
  fb.className=`quiz-feedback ${correct?"correct":"wrong"}`;
  fb.style.display="block";
  fb.innerHTML=correct?`✅ To'g'ri! +10 ball ${q.word.pronunciation?`<br><em>Talaffuz: ${q.word.pronunciation}</em>`:""}`
    :`❌ Noto'g'ri! To'g'ri javob: <strong>${q.correctAns}</strong>`;

  setTimeout(()=>{ State.quizIndex++; showQuizQuestion(); },1400);
}

async function endQuiz(){
  $("quizPlay").style.display="none";
  const total=State.quizQuestions.length;
  const correct=State.quizAnswers.filter(a=>a.correct).length;
  const pct=Math.round(correct/total*100);
  const emoji=pct>=90?"🏆":pct>=70?"🎉":pct>=50?"😊":"😅";

  await api("/api/history",{method:"POST",body:JSON.stringify({
    lesson_type:"quiz",duration_sec:total*5,score:pct,xp_earned:State.quizScore,
    details:{correct,wrong:total-correct,total,score:State.quizScore}
  })});

  $("quizResultEmoji").textContent=emoji;
  $("quizResultScore").textContent=`${State.quizScore} ball — ${pct}%`;
  $("quizResultDetails").innerHTML=`
    <div style="color:var(--text2);margin-bottom:16px">
      <span style="color:var(--green)">✅ ${correct}</span> to'g'ri · 
      <span style="color:var(--red)">❌ ${total-correct}</span> noto'g'ri · 
      jami ${total} ta savol
    </div>
    <div style="display:flex;flex-direction:column;gap:6px;max-height:200px;overflow-y:auto">
      ${State.quizAnswers.map(a=>`
        <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg3);border-radius:6px;font-size:12px">
          <span>${a.correct?"✅":"❌"}</span>
          <span style="font-weight:600">${a.question}</span>
          <span style="color:var(--text3)">→</span>
          <span style="color:${a.correct?"var(--green)":"var(--red)"}">${a.chosen}</span>
          ${!a.correct?`<span style="color:var(--text3);margin-left:auto">✅ ${a.correctAns}</span>`:""}
        </div>`).join("")}
    </div>`;
  $("quizResult").style.display="block";
  await loadProfile();
  toast(`🎉 ${State.quizScore} XP qo'shildi!`,"success");
}


// ══════════════════════════════════════════════════
// GAMES
// ══════════════════════════════════════════════════
async function loadGameHighscores(){
  const scores=await api("/api/games/leaderboard");
  if(!scores) return;
  const types=["match","scramble","typing","fill"];
  types.forEach(t=>{
    const best=scores.filter(s=>s.game_type===t).sort((a,b)=>b.score-a.score)[0];
    const el=$(t+"HS");
    if(el) el.textContent=best?`${best.score} ball`:"—";
  });
}

async function startGame(type){
  const words=await api("/api/words?limit=20");
  if(!words||words.length<4){ toast("Kamida 4 ta so'z kerak","warn"); return; }
  const gameWords=words.sort(()=>Math.random()-0.5).slice(0,Math.min(10,words.length));
  State.game={type,score:0,timer:null,timeLeft:60,words:gameWords,index:0,matched:[]};
  $("gameArea").style.display="block";
  $("gameName").textContent={match:"🔗 So'z Moslashtirish",scramble:"🔀 Harflarni Joylashtir",typing:"⌨️ Yozuv Poygasi",fill:"📝 Bo'sh joyni to'ldiring"}[type];
  $("gameScore").textContent="0 ball";
  $("gameTimer").textContent="⏱ 60s";
  clearInterval(State.game.timer);
  State.game.timer=setInterval(()=>{
    State.game.timeLeft--;
    $("gameTimer").textContent=`⏱ ${State.game.timeLeft}s`;
    if(State.game.timeLeft<=0){ clearInterval(State.game.timer); finishGame(); }
  },1000);
  const renders={match:renderMatchGame,scramble:renderScrambleGame,typing:renderTypingGame,fill:renderFillGame};
  if(renders[type]) renders[type]();
}

function renderMatchGame(){
  const words=State.game.words.slice(0,6);
  const ruItems=words.map(w=>({id:w.id,text:w.russian,pair:w.id}));
  const uzItems=words.map(w=>({id:w.id+"_uz",text:w.uzbek,pair:w.id}));
  const ruShuf=[...ruItems].sort(()=>Math.random()-0.5);
  const uzShuf=[...uzItems].sort(()=>Math.random()-0.5);
  State.game.matchState={selected:null,matched:[],ruItems:ruShuf,uzItems:uzShuf};
  $("gameContent").innerHTML=`<div class="match-grid">
    <div class="match-col" id="matchLeft">${ruShuf.map(i=>`<div class="match-item" id="mi-${i.id}" data-pair="${i.pair}" data-side="ru" onclick="clickMatchItem(this)">${i.text}</div>`).join("")}</div>
    <div class="match-col" id="matchRight">${uzShuf.map(i=>`<div class="match-item" id="mi-${i.id}" data-pair="${i.pair}" data-side="uz" onclick="clickMatchItem(this)">${i.text}</div>`).join("")}</div>
  </div>`;
}

function clickMatchItem(el){
  if(el.classList.contains("correct")) return;
  const ms=State.game.matchState;
  if(!ms.selected){
    document.querySelectorAll(".match-item.selected").forEach(e=>e.classList.remove("selected"));
    el.classList.add("selected");
    ms.selected=el;
  } else {
    if(ms.selected===el){ el.classList.remove("selected"); ms.selected=null; return; }
    const p1=ms.selected.dataset.pair, p2=el.dataset.pair;
    const s1=ms.selected.dataset.side, s2=el.dataset.side;
    if(p1===p2 && s1!==s2){
      ms.selected.classList.replace("selected","correct");
      el.classList.add("correct");
      ms.matched.push(p1);
      State.game.score+=15;
      $("gameScore").textContent=`${State.game.score} ball`;
      toast("✅ To'g'ri!","success",800);
      if(ms.matched.length===State.game.words.slice(0,6).length){ clearInterval(State.game.timer); finishGame(); }
    } else {
      ms.selected.classList.add("wrong"); el.classList.add("wrong");
      setTimeout(()=>{ ms.selected?.classList.remove("wrong","selected"); el.classList.remove("wrong"); },600);
      State.game.score=Math.max(0,State.game.score-3);
      $("gameScore").textContent=`${State.game.score} ball`;
    }
    ms.selected=null;
  }
}

function renderScrambleGame(){
  const w=State.game.words[State.game.index];
  const scrambled=w.russian.split("").sort(()=>Math.random()-0.5).join("");
  $("gameContent").innerHTML=`
    <div class="scramble-word">${scrambled}</div>
    <div class="scramble-hint">O'zbekcha: <b>${w.uzbek}</b></div>
    <input type="text" class="form-input scramble-input" id="scrambleInp" placeholder="Ruscha so'zni yozing..."
           onkeydown="if(event.key==='Enter')checkScramble()">
    <div style="display:flex;gap:8px;margin-top:12px;justify-content:center">
      <button class="btn btn-primary" onclick="checkScramble()">✅ Tekshirish</button>
      <button class="btn btn-ghost" onclick="skipScramble()">⏭ O'tkazish</button>
    </div>
    <div id="scrambleFb" style="text-align:center;margin-top:8px;font-size:13px"></div>`;
  setTimeout(()=>$("scrambleInp")?.focus(),100);
}

function checkScramble(){
  const w=State.game.words[State.game.index];
  const ans=($("scrambleInp")?.value||"").trim();
  const ok=ans.toLowerCase()===w.russian.toLowerCase();
  $("scrambleFb").innerHTML=ok?`<span style="color:var(--green)">✅ To'g'ri! +20 ball</span>`
    :`<span style="color:var(--red)">❌ To'g'ri javob: ${w.russian}</span>`;
  if(ok){ State.game.score+=20; $("gameScore").textContent=`${State.game.score} ball`; }
  setTimeout(()=>{ State.game.index=(State.game.index+1)%State.game.words.length; renderScrambleGame(); },1200);
}
function skipScramble(){ State.game.index=(State.game.index+1)%State.game.words.length; renderScrambleGame(); }

function renderTypingGame(){
  const w=State.game.words[State.game.index];
  $("gameContent").innerHTML=`
    <div class="typing-word">${w.uzbek}</div>
    <div class="typing-hint">Ruscha tarjimasini yozing</div>
    <input type="text" class="form-input typing-input" id="typingInp" placeholder="Ruscha..."
           onkeydown="if(event.key==='Enter')checkTyping()">
    <div id="typingFb" style="text-align:center;margin-top:8px;font-size:13px"></div>`;
  setTimeout(()=>$("typingInp")?.focus(),100);
}

function checkTyping(){
  const w=State.game.words[State.game.index];
  const ans=($("typingInp")?.value||"").trim();
  const ok=ans.toLowerCase()===w.russian.toLowerCase();
  $("typingFb").innerHTML=ok?`<span style="color:var(--green)">✅ +15 ball</span>`:`<span style="color:var(--red)">❌ ${w.russian}</span>`;
  if(ok){ State.game.score+=15; $("gameScore").textContent=`${State.game.score} ball`; }
  setTimeout(()=>{ State.game.index=(State.game.index+1)%State.game.words.length; renderTypingGame(); },900);
}

function renderFillGame(){
  const w=State.game.words[State.game.index];
  const sentence=w.example_ru||(w.russian+" — bu so'z.");
  const blanked=sentence.replace(new RegExp(w.russian,"i"),"_____");
  const wrong=State.game.words.filter(x=>x.id!==w.id).sort(()=>Math.random()-0.5).slice(0,3).map(x=>x.russian);
  const opts=[...wrong,w.russian].sort(()=>Math.random()-0.5);
  $("gameContent").innerHTML=`
    <div style="font-size:12px;color:var(--text2);margin-bottom:8px">O'zbekcha: ${w.example_uz||w.uzbek}</div>
    <div class="fill-sentence">${blanked}</div>
    <div class="fill-options">${opts.map(o=>`<button class="fill-opt" onclick="checkFill(this,'${o.replace(/'/g,"\\'")}','${w.russian.replace(/'/g,"\\'")}')">${o}</button>`).join("")}</div>`;
}

function checkFill(btn,chosen,correct){
  const ok=chosen===correct;
  document.querySelectorAll(".fill-opt").forEach(b=>b.disabled=true);
  btn.classList.add(ok?"correct":"wrong");
  if(!ok) document.querySelectorAll(".fill-opt").forEach(b=>{if(b.textContent===correct)b.classList.add("correct");});
  if(ok){ State.game.score+=10; $("gameScore").textContent=`${State.game.score} ball`; }
  setTimeout(()=>{ State.game.index=(State.game.index+1)%State.game.words.length; renderFillGame(); },1200);
}

async function stopGame(){ clearInterval(State.game.timer); finishGame(); }

async function finishGame(){
  clearInterval(State.game.timer);
  const {type,score,words}=State.game;
  $("gameContent").innerHTML=`
    <div style="text-align:center;padding:32px">
      <div style="font-size:48px;margin-bottom:12px">🏆</div>
      <h2 style="margin-bottom:8px">O'yin tugadi!</h2>
      <div style="font-size:28px;font-weight:700;color:var(--accent);margin:12px 0">${score} ball</div>
      <div style="color:var(--text2);margin-bottom:20px">Sarflangan vaqt: ${60-State.game.timeLeft}s</div>
      <button class="btn btn-primary" onclick="startGame('${type}')">🔄 Qayta o'ynash</button>
      <button class="btn btn-ghost" style="margin-left:8px" onclick="$('gameArea').style.display='none'">⏹ Yopish</button>
    </div>`;
  await api("/api/games/score",{method:"POST",body:JSON.stringify({game_type:type,score,max_score:words.length*20,time_sec:60-State.game.timeLeft})});
  await loadProfile();
  toast(`🏆 ${score} ball!`,"success");
  loadGameHighscores();
}


// ══════════════════════════════════════════════════
// AI CHAT
// ══════════════════════════════════════════════════
async function loadChatHistory(){
  const history=await api("/api/chat/history");
  if(!history||history.error) return;
  if(!history.length) return;
  const msgs=$("chatMessages");
  const existing=msgs.querySelectorAll(".chat-msg:not(:first-child)");
  existing.forEach(m=>m.remove());
  const sorted=[...history].reverse();
  sorted.forEach(h=>{
    if(h.id) appendChatMsg(h.role, h.content, h.id, h.correction);
  });
  msgs.scrollTop=msgs.scrollHeight;
}

function appendChatMsg(role, content, id=null, correction=""){
  const msgs=$("chatMessages");
  const div=document.createElement("div");
  div.className=`chat-msg ${role}`;
  div.innerHTML=`<div>
    <div class="msg-bubble">${content.replace(/\n/g,"<br>")}</div>
    ${correction?`<div class="msg-correction">✏️ Tuzatish: ${correction}</div>`:""}
    ${role==="assistant"&&id?`<div class="msg-edit-btn" onclick="editChatMsg(${id},this)">✏️ Tuzatish qo'shish</div>`:""}
  </div>`;
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
}

async function sendChat(){
  const inp=$("chatInput");
  const msg=inp.value.trim();
  if(!msg) return;
  if(!State.internetAllowed){ toast("Internet o'chiq — AI bilan suhbat uchun Internet kerak","warn"); return; }
  inp.value="";
  appendChatMsg("user",msg);
  const thinking=document.createElement("div");
  thinking.className="chat-msg assistant";
  thinking.id="thinkingMsg";
  thinking.innerHTML=`<div class="msg-bubble"><span class="spinner"></span> AI yozmoqda...</div>`;
  $("chatMessages").appendChild(thinking);
  $("chatMessages").scrollTop=$("chatMessages").scrollHeight;
  const r=await api("/api/chat",{method:"POST",body:JSON.stringify({message:msg})});
  thinking.remove();
  if(r.ok) appendChatMsg("assistant",r.response);
  else{
    appendChatMsg("assistant",`❌ ${r.error||"Xatolik yuz berdi"}`);
    toast("❌ "+(r.error||"AI xatosi"),"error");
  }
  await loadProfile();
}

async function clearChat(){
  if(!confirm("Barcha suhbat tarixini tozalash?")) return;
  await api("/api/chat/clear",{method:"POST"});
  const msgs=$("chatMessages");
  const toRemove=msgs.querySelectorAll(".chat-msg:not(:first-child)");
  toRemove.forEach(m=>m.remove());
  toast("🗑 Tozalandi","info");
}

function editChatMsg(id, btn){
  const correction=prompt("Tuzatishni kiriting:");
  if(!correction) return;
  api("/api/chat/correct",{method:"POST",body:JSON.stringify({id,correction})});
  const corrDiv=document.createElement("div");
  corrDiv.className="msg-correction";
  corrDiv.textContent="✏️ Tuzatish: "+correction;
  btn.parentNode.insertBefore(corrDiv, btn);
  btn.remove();
  toast("✅ Tuzatish saqlandi","success");
}

async function saveChatLevel(){
  const lvl=$("chatLevelSel").value;
  await api("/api/settings",{method:"POST",body:JSON.stringify({ai_conversation_level:lvl})});
}


// ══════════════════════════════════════════════════
// SCHEDULE PAGE
// ══════════════════════════════════════════════════
async function loadSchedule(){
  const sched=await api("/api/schedule?days=14");
  const missed=await api("/api/schedule/missed");
  State.scheduleList=sched||[];

  // Missed warning
  const warnEl=$("missedWarning");
  if(missed&&missed.length){
    warnEl.style.display="flex";
    $("missedWarningText").textContent=`${missed.length} ta dars o'tkazib yuborilgan: ${missed.slice(0,2).map(l=>l.title).join(", ")}${missed.length>2?` va yana ${missed.length-2} ta`:""}`;
  } else warnEl.style.display="none";

  // Render schedule
  const listEl=$("scheduleList");
  if(!sched||!sched.length){
    listEl.innerHTML=`<div class="empty-state" style="padding:24px"><div class="empty-icon">📅</div><p>Kelgusi 14 kunda dars yo'q. Dars qo'shing!</p></div>`;
  } else {
    let lastDate="";
    listEl.innerHTML=sched.map(l=>{
      const dt=fmtDate(l.scheduled_at);
      let header="";
      if(dt!==lastDate){ lastDate=dt; header=`<div style="font-size:11px;font-weight:700;color:var(--text3);padding:8px 12px 4px;text-transform:uppercase;letter-spacing:.5px">${dt}</div>`; }
      const now=new Date();
      const scheduled=new Date(l.scheduled_at.replace(" ","T"));
      const diffMin=Math.round((scheduled-now)/60000);
      const urgentClass=diffMin>=0&&diffMin<=30?" style='background:rgba(240,192,64,0.07)'":"";
      return `${header}<div class="lesson-item"${urgentClass}>
        <span class="lesson-type-badge">${lessonTypeEmoji(l.lesson_type)}</span>
        <div class="lesson-info">
          <div class="lesson-title">${l.title}</div>
          <div class="lesson-meta">⏰ ${fmtTime(l.scheduled_at)} · ⏱ ${l.duration_min} daqiqa · ${l.description||""}</div>
        </div>
        <span class="lesson-status status-${l.status}">${statusLabel(l.status)}</span>
        <div class="lesson-actions">
          ${l.status==="pending"?`<button class="btn btn-sm btn-primary" onclick="startLesson(${l.id},'${l.lesson_type}')">▶</button>`:""}
          ${l.status==="started"?`<button class="btn btn-sm btn-primary" onclick="completeLesson(${l.id})">✅</button>`:""}
          <button class="btn btn-sm btn-danger" onclick="deleteLesson(${l.id})">🗑</button>
        </div>
      </div>`;
    }).join("");
  }
  loadAllLessons();
}

async function loadAllLessons(){
  const all=await api("/api/schedule/all");
  const el=$("allLessonsList");
  if(!el) return;
  if(!all||!all.length){ el.innerHTML=`<div class="empty-state" style="padding:20px"><p>Hech qanday dars yo'q</p></div>`; return; }
  el.innerHTML=`<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="background:var(--bg3);color:var(--text2)">
      <th style="padding:8px 12px;text-align:left">Dars</th>
      <th style="padding:8px 12px;text-align:left">Vaqt</th>
      <th style="padding:8px 12px;text-align:left">Tur</th>
      <th style="padding:8px 12px;text-align:left">Holat</th>
      <th style="padding:8px 12px;text-align:left">Ball</th>
      <th style="padding:8px 12px;text-align:left">Amal</th>
    </tr></thead>
    <tbody>${all.map(l=>`<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:8px 12px;font-weight:500">${l.title}</td>
      <td style="padding:8px 12px;color:var(--text3)">${fmt(l.scheduled_at)}</td>
      <td style="padding:8px 12px">${lessonTypeEmoji(l.lesson_type)} ${l.lesson_type}</td>
      <td style="padding:8px 12px"><span class="lesson-status status-${l.status}">${statusLabel(l.status)}</span></td>
      <td style="padding:8px 12px;color:var(--yellow)">${l.score||"—"}</td>
      <td style="padding:8px 12px;display:flex;gap:4px">
        ${l.status==="pending"?`<button class="btn btn-sm btn-primary" onclick="startLesson(${l.id},'${l.lesson_type}')">▶</button>`:""}
        ${l.status==="started"?`<button class="btn btn-sm btn-primary" onclick="completeLesson(${l.id})">✅</button>`:""}
        <button class="btn btn-sm btn-danger" onclick="deleteLesson(${l.id})">🗑</button>
      </td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function openAddLessonModal(){
  const now=new Date(); now.setMinutes(now.getMinutes()-now.getTimezoneOffset());
  $("alTime").value=now.toISOString().slice(0,16);
  openModal("addLessonModal");
}

async function submitAddLesson(){
  const title=$("alTitle").value.trim();
  const time=$("alTime").value;
  if(!title||!time){ toast("Dars nomi va vaqti kiritilishi shart","warn"); return; }
  const r=await api("/api/schedule",{method:"POST",body:JSON.stringify({
    title,scheduled_at:time.replace("T"," ")+":00",
    duration_min:parseInt($("alDur").value)||30,
    lesson_type:$("alType").value,description:$("alDesc").value,
  })});
  if(r.ok){
    toast("✅ Dars qo'shildi","success"); closeModal("addLessonModal");
    $("alTitle").value=""; $("alDesc").value="";
    loadSchedule();
  } else toast("❌ Xatolik","error");
}

function startLesson(id, type){
  api(`/api/schedule/${id}`,{method:"PUT",body:JSON.stringify({status:"started"})});
  const pageMap={vocabulary:"vocabulary",grammar:"grammar",flashcards:"flashcards",quiz:"quiz",chat:"chat",game:"games"};
  navigate(pageMap[type]||"home");
  toast("▶ Dars boshlandi!","success");
  loadSchedule();
}

async function completeLesson(id){
  const score=prompt("Ball kiriting (0-100):")||"0";
  await api(`/api/schedule/${id}`,{method:"PUT",body:JSON.stringify({status:"completed",score:parseInt(score)})});
  toast("✅ Dars tugallandi!","success"); loadSchedule(); loadProfile();
}

async function deleteLesson(id){
  if(!confirm("Darsni o'chirish?")) return;
  await api(`/api/schedule/${id}`,{method:"DELETE"});
  toast("🗑 O'chirildi","info"); loadSchedule();
}


// ══════════════════════════════════════════════════
// PROGRESS PAGE
// ══════════════════════════════════════════════════
async function loadProgress(){
  const stats=await api("/api/stats");
  const history=await api("/api/history?limit=30");
  if(stats.error) return;

  // Level card
  const levels=[
    {name:"Yangi boshlovchi",min:0,max:200,icon:"🌱",color:"var(--green)"},
    {name:"Boshlang'ich",min:200,max:500,icon:"📗",color:"var(--green)"},
    {name:"O'rta daraja",min:500,max:1000,icon:"📘",color:"var(--accent)"},
    {name:"O'rta-yuqori",min:1000,max:2000,icon:"📙",color:"var(--yellow)"},
    {name:"Ilg'or",min:2000,max:4000,icon:"📕",color:"var(--orange)"},
    {name:"Ustoz",min:4000,max:9999,icon:"🏆",color:"var(--purple)"},
  ];
  const xp=stats.total_xp||0;
  const lvl=levels.find(l=>xp>=l.min&&xp<l.max)||levels[levels.length-1];
  const pct=Math.min(100,Math.round((xp-lvl.min)/(lvl.max-lvl.min)*100));
  $("levelCard").innerHTML=`
    <div class="lc-icon">${lvl.icon}</div>
    <div class="lc-info">
      <div class="lc-name" style="color:${lvl.color}">${lvl.name}</div>
      <div class="lc-xp">${xp} XP · Keyingi daraja: ${lvl.max} XP</div>
      <div class="xp-bar-wrap"><div class="xp-bar" style="width:${pct}%;background:${lvl.color}"></div></div>
    </div>
    <div style="text-align:right">
      <div style="font-size:28px;font-weight:700;color:${lvl.color}">${pct}%</div>
      <div style="font-size:11px;color:var(--text3)">joriy daraja</div>
    </div>`;

  // Stats grid
  $("fullStatsGrid").innerHTML=`
    <div class="stat-card"><div class="stat-val">${stats.total_words||0}</div><div class="stat-lbl">📖 Jami so'zlar</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--green)">${stats.learned_words||0}</div><div class="stat-lbl">✅ O'rganilgan</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--yellow)">${stats.due_reviews||0}</div><div class="stat-lbl">🔁 Takrorlash</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--purple)">${stats.streak_days||0}</div><div class="stat-lbl">🔥 Streak</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--orange)">${stats.total_xp||0}</div><div class="stat-lbl">⭐ Jami XP</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--accent)">${stats.total_sessions||0}</div><div class="stat-lbl">📚 Sessiyalar</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--green)">${stats.grammar_rules||0}</div><div class="stat-lbl">📝 Grammatika</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--red)">${stats.missed_lessons||0}</div><div class="stat-lbl">⚠ O'tkazilgan</div></div>`;

  // Chart — so'nggi 7 kun
  const days=[];const labels=[];
  for(let i=6;i>=0;i--){
    const d=new Date(); d.setDate(d.getDate()-i);
    labels.push(d.toLocaleDateString("uz-UZ",{weekday:"short",day:"numeric"}));
    const dayStr=d.toISOString().slice(0,10);
    const dayHistory=(history||[]).filter(h=>h.studied_at&&h.studied_at.startsWith(dayStr));
    days.push(dayHistory.reduce((sum,h)=>sum+(h.duration_sec||0),0)/60);
  }
  const canvas=$("studyChart");
  if(State.chartInstance){ State.chartInstance.destroy(); State.chartInstance=null; }
  if(canvas&&window.Chart){
    State.chartInstance=new Chart(canvas,{
      type:"bar",
      data:{labels,datasets:[{label:"Daqiqa",data:days,backgroundColor:"rgba(79,142,247,0.6)",borderColor:"#4f8ef7",borderWidth:2,borderRadius:6}]},
      options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{color:"#9ba3b8"},grid:{color:"#2a2f40"}},x:{ticks:{color:"#9ba3b8"},grid:{display:false}}}}
    });
  }

  // Mastery breakdown
  const masteryData=[
    {label:"Boshlang'ich so'zlar",key:"beginner",color:"var(--green)"},
    {label:"O'rta so'zlar",key:"intermediate",color:"var(--yellow)"},
    {label:"Yuqori so'zlar",key:"advanced",color:"var(--red)"},
  ];
  const wStats=await Promise.all(masteryData.map(async m=>{
    const total=await api(`/api/words?level=${m.key}&limit=1000`);
    const learned=(total||[]).filter(w=>(w.times_correct||0)>0).length;
    return {...m,total:(total||[]).length,learned};
  }));
  $("masteryBreakdown").innerHTML=wStats.map(m=>{
    const pct=m.total>0?Math.round(m.learned/m.total*100):0;
    return `<div class="mastery-row">
      <div class="mastery-label">${m.label}</div>
      <div class="mastery-bar-wrap"><div class="mastery-bar" style="width:${pct}%;background:${m.color}"></div></div>
      <div class="mastery-val">${m.learned}/${m.total} (${pct}%)</div>
    </div>`;
  }).join("");

  // History table
  const histEl=$("historyTable");
  if(history&&history.length){
    histEl.innerHTML=history.slice(0,15).map(h=>`
      <div class="history-row">
        <span>${lessonTypeEmoji(h.lesson_type)}</span>
        <span style="flex:1">${{vocabulary:"Lug'at",grammar:"Grammatika",flashcards:"Kartochkalar",quiz:"Test",chat:"AI Suhbat",game:"O'yin"}[h.lesson_type]||h.lesson_type}</span>
        <span style="color:var(--text3)">${secToMin(h.duration_sec||0)}</span>
        <span style="color:var(--yellow)">${h.score||0}%</span>
        <span style="color:var(--purple)">+${h.xp_earned||0} XP</span>
        <span style="color:var(--text3);font-size:11px">${timeAgo(h.studied_at)}</span>
      </div>`).join("");
  } else histEl.innerHTML=`<div class="empty-state" style="padding:20px"><p>O'qish tarixi yo'q</p></div>`;
}


// ══════════════════════════════════════════════════
// CLOCK — Real-vaqt soat va dars eslatmasi
// ══════════════════════════════════════════════════
function startClockChecker(){
  setInterval(async()=>{
    const sched = await api("/api/schedule?days=1");
    if(!sched||!sched.length) return;
    const now=new Date();
    sched.forEach(l=>{
      if(l.status!=="pending") return;
      const dt=new Date(l.scheduled_at.replace(" ","T"));
      const diffMin=(dt-now)/60000;
      if(diffMin>=0&&diffMin<=1 && !l._alerted){
        l._alerted=true;
        showInAppAlert(`⏰ Dars boshlanmoqda: ${l.title}`, "warn");
      } else if(diffMin>0&&diffMin<=30&&diffMin>29){
        showInAppAlert(`📚 30 daqiqadan keyin dars: ${l.title}`, "info");
      }
    });
  }, 60000);
}

function showInAppAlert(msg, type="info"){
  toast(msg, type, 8000);
  if("Notification" in window && Notification.permission==="granted"){
    new Notification("RusLearn Pro", {body:msg, icon:"/static/favicon.ico"});
  }
}

// Browser notification ruxsati so'rash
if("Notification" in window && Notification.permission==="default"){
  setTimeout(()=>Notification.requestPermission(), 3000);
}

// ══════════════════════════════════════════════════
// KEYBOARD SHORTCUTS
// ══════════════════════════════════════════════════
document.addEventListener("keydown",e=>{
  if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA") return;
  const shortcuts = {
    "1":()=>navigate("home"), "2":()=>navigate("vocabulary"),
    "3":()=>navigate("flashcards"), "4":()=>navigate("grammar"),
    "5":()=>navigate("games"), "6":()=>navigate("quiz"),
    "7":()=>navigate("chat"), "8":()=>navigate("schedule"),
    "9":()=>navigate("progress"),
  };
  if(shortcuts[e.key] && (e.ctrlKey||e.altKey)){ e.preventDefault(); shortcuts[e.key](); }
  // Flashcard shortcuts
  if(State.currentPage==="flashcards"){
    if(e.key===" "){ e.preventDefault(); flipCard(); }
    if(e.key==="ArrowLeft"){ answerCard(false); }
    if(e.key==="ArrowRight"){ answerCard(true); }
  }
});

// ══════════════════════════════════════════════════
// MOBILE SIDEBAR
// ══════════════════════════════════════════════════
function toggleSidebar(){
  $("sidebar").classList.toggle("open");
}

// Sidebar tashqarisiga bosishda yopish
document.addEventListener("click", e=>{
  const sidebar=$("sidebar");
  const isOpen=sidebar&&sidebar.classList.contains("open");
  if(isOpen && !sidebar.contains(e.target)){
    sidebar.classList.remove("open");
  }
});

// ══════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════
async function init(){
  await loadProfile();
  await loadSettings();
  const netStatus=await api("/api/internet/status");
  updateInternetUI(netStatus.allowed!==false);
  navigate("home");
  startClockChecker();

  // Settings dagi chat level ni profile bilan sinxronlashtirish
  const chatLvlSel=$("chatLevelSel");
  if(chatLvlSel && State.settings.ai_conversation_level){
    chatLvlSel.value=State.settings.ai_conversation_level;
  }

  console.log("🇷🇺 RusLearn Pro yuklandi!");
  toast("🇷🇺 RusLearn Pro xush kelibsiz!","success",2500);
}

document.addEventListener("DOMContentLoaded", init);
