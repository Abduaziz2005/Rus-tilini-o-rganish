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
  // Grammar lesson mode
  gmRules: [],
  gmIndex: 0,
  gmXP: 0,
  gmCurrentExIndex: 0,
  gmCurrentExAnswers: [],
  // Category test
  catTest: { cat:"", words:[], index:0, score:0, answers:[], start:null },
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
    home:       loadHome,
    vocabulary: loadVocabulary,
    flashcards: ()=>{},
    grammar:    loadGrammar,
    games:      loadGameHighscores,
    quiz:       ()=>{},
    chat:       ()=>{ loadChatHistory(); _updateOfflineBadge(); },
    schedule:   loadSchedule,
    progress:   loadProgress,
    settings:   loadSettings,
    adaptive:   loadAdaptivePage,
    roleplay:   loadRoleplayPage,
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
  const catNames = {
    general:"Umumiy", greeting:"Salomlashish", numbers:"Raqamlar",
    colors:"Ranglar", family:"Oila asoslari", food:"Oziq-ovqat",
    verbs:"Fe'llar", adjectives:"Sifatlar", travel:"Sayohat",
    work:"Ish", health:"Sog'liq", nature:"Tabiat", time:"Vaqt (asos)",
    emotions:"His-tuyg'ular", shopping:"Xarid", introduction:"🤝 Tanishish",
    navigation:"🗺️ Yo'l", time_ext:"⏰ Vaqt to'liq", places:"🏛️ Joylar",
    math:"🔢 Matematika", family_ext:"👨‍👩‍👧‍👦 Oila to'liq", clothing:"👗 Kiyim",
    animals:"🐾 Hayvonlar", transport:"🚗 Transport", body:"🫀 Tana",
    school:"🏫 Maktab", weather:"🌤️ Ob-havo", house:"🏠 Uy-joy", sport:"⚽ Sport",
  };
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
let _grammarCat   = "";

async function loadGrammar(){
  const lvl = _grammarLevel==="all"?"":_grammarLevel;
  let url = `/api/grammar${lvl?`?level=${lvl}`:""}`;
  if(_grammarCat) url = `/api/grammar?category=${_grammarCat}`;
  const rules = await api(url);
  if(!rules||rules.error) return;
  State.grammar=rules;

  // ── Bosqichlar paneli ──
  await renderGrammarSteps();

  const list=$("grammarList");
  if(!rules.length){
    list.innerHTML=`<div class="empty-state"><div class="empty-icon">📝</div>
      <p>Grammatika qoidalari topilmadi</p></div>`;
    return;
  }
  const catLabels={alphabet:"🔤 Alifbo",nouns:"🏷 Otlar",pronouns:"👤 Olmoshlar",
    adjectives:"🎨 Sifatlar",verbs:"⚡ Fe'llar",cases:"📐 Kelshiklar",grammar:"📝 Grammatika"};
  list.innerHTML=rules.map((r,i)=>`
    <div class="grammar-card" id="gc-${r.id}" onclick="openGrammarDetail(${r.id})">
      <div class="gc-top">
        <div>
          <div class="gc-step-num">${i+1}</div>
          <div class="gc-title">${r.title}</div>
          <div class="gc-preview">${r.content.slice(0,80).replace(/\n/g," ")}...</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
          <span class="wc-level level-${r.level}">${levelEmoji(r.level)}</span>
          <span class="gc-cat-badge">${catLabels[r.category]||r.category}</span>
        </div>
      </div>
      <div class="gc-actions">
        <button class="btn btn-sm btn-primary" onclick="event.stopPropagation();startGrammarLessonFrom(${r.id})">▶ O'rganish</button>
        <button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();openGrammarEditById(${r.id})">✏️ Tahrirlash</button>
      </div>
    </div>`).join("");
}

async function renderGrammarSteps(){
  const all = await api("/api/grammar");
  const track=$("grammarStepsTrack");
  if(!track||!all) return;
  const steps=[
    {key:"alphabet",label:"Alifbo",icon:"🔤"},
    {key:"nouns",label:"Otlar",icon:"🏷"},
    {key:"pronouns",label:"Olmoshlar",icon:"👤"},
    {key:"adjectives",label:"Sifatlar",icon:"🎨"},
    {key:"verbs",label:"Fe'llar",icon:"⚡"},
    {key:"cases",label:"Kelshiklar",icon:"📐"},
    {key:"introduction", label:"Tanishish",  icon:"🤝"},
    {key:"navigation",   label:"Yo'l",        icon:"🗺️"},
    {key:"time_ext",     label:"Vaqt",        icon:"⏰"},
    {key:"places",       label:"Joylar",      icon:"🏛️"},
    {key:"math",         label:"Matematika",  icon:"🔢"},
    {key:"family_ext",   label:"Oila",        icon:"👨‍👩‍👧‍👦"},
    {key:"clothing",     label:"Kiyim",       icon:"👗"},
    {key:"animals",      label:"Hayvonlar",   icon:"🐾"},
    {key:"transport",    label:"Transport",   icon:"🚗"},
    {key:"body",         label:"Tana",        icon:"🫀"},
    {key:"school",       label:"Maktab",      icon:"🏫"},
    {key:"weather",      label:"Ob-havo",     icon:"🌤️"},
    {key:"house",        label:"Uy-joy",      icon:"🏠"},
    {key:"sport",        label:"Sport",       icon:"⚽"},
  ];
  track.innerHTML=steps.map((s,i)=>{
    const count=all.filter(r=>r.category===s.key).length;
    const done=count>0;
    return `<div class="step-item${done?" done":""}" onclick="filterGrammarCat('${s.key}')">
      <div class="step-circle">${done?"✓":i+1}</div>
      <div class="step-label">${s.icon} ${s.label}</div>
      <div class="step-count">${count} qoida</div>
    </div>${i<steps.length-1?`<div class="step-connector${done?" done":""}"></div>`:""}`;
  }).join("");
}

function filterGrammar(lvl, el){
  _grammarLevel=lvl; _grammarCat="";
  document.querySelectorAll(".g-tab").forEach(t=>t.classList.remove("active"));
  if(el) el.classList.add("active");
  loadGrammar();
}

function filterGrammarCat(cat, el){
  _grammarCat=cat; _grammarLevel="all";
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
// ══════════════════════════════════════════════════
// AI CHAT v3 — ERKIN MAVZU + TTS OVOZ
// ══════════════════════════════════════════════════

// ══════════════════════════════════════════════════
// AI CHAT v4 — SMART, IKKI TIL, AI O'QITISH
// ══════════════════════════════════════════════════

const Chat = {
  mode: "text", level: "beginner", topic: "free",
  customTopic: "", personality: "teacher",
  isTyping: false, msgCount: 0,
  ttsEnabled: true, ttsSpeed: 0.9, ttsVoice: null,
  micActive: false, recognition: null,
  uiLang: "auto",        // "auto" | "uz" | "ru"
  pendingTeach: null,    // { question, hint }
};

const TOPIC_META = {
  free:{icon:"✨",label:"Erkin"},greet:{icon:"👋",label:"Salomlashish"},
  travel:{icon:"✈️",label:"Sayohat"},food:{icon:"🍎",label:"Ovqat"},
  family:{icon:"👨‍👩‍👧",label:"Oila"},weather:{icon:"🌤️",label:"Ob-havo"},
  numbers:{icon:"🔢",label:"Raqamlar"},hobbies:{icon:"🎯",label:"Qiziqishlar"},
  school:{icon:"🏫",label:"Maktab"},work:{icon:"💼",label:"Ish"},
  health:{icon:"🏥",label:"Sog'liq"},sport:{icon:"⚽",label:"Sport"},
  city:{icon:"🏙️",label:"Shahar"},shopping:{icon:"🛍️",label:"Xarid"},
  cinema:{icon:"🎬",label:"Kino"},tech:{icon:"💻",label:"Texno"},
};


// ══════════════════════════════════════════════════
// TTS
// ══════════════════════════════════════════════════
function ttsInit(){
  if(!window.speechSynthesis) return;
  const set=()=>{
    const vs=speechSynthesis.getVoices();
    Chat.ttsVoice=vs.find(v=>v.lang.startsWith("ru"))||vs.find(v=>v.lang.startsWith("en"))||vs[0]||null;
  };
  if(speechSynthesis.getVoices().length) set();
  speechSynthesis.addEventListener("voiceschanged",set);
}

function ttsSpeak(text,auto=false){
  if(!window.speechSynthesis) return;
  if(!auto&&!Chat.ttsEnabled) return;
  speechSynthesis.cancel();
  const clean=text.replace(/\(.*?\)/g,"").replace(/\[.*?\]/g,"")
    .replace(/[🎉✅❌📝💡👋🤖🇷🇺🇺🇿⭐🔊📵✨❓]/gu,"")
    .replace(/\n+/g,". ").replace(/[*_~`]/g,"").trim();
  if(!clean) return;
  const u=new SpeechSynthesisUtterance(clean);
  u.lang="ru-RU"; u.rate=Chat.ttsSpeed; u.pitch=1;
  if(Chat.ttsVoice) u.voice=Chat.ttsVoice;
  u.onend=u.onerror=()=>document.querySelectorAll(".tts-msg-btn.playing").forEach(b=>{b.classList.remove("playing");b.textContent="🔊";});
  speechSynthesis.speak(u);
}

function ttsSpeakEl(btn){
  const text=btn.dataset.text||""; if(!text) return;
  if(btn.classList.contains("playing")){speechSynthesis.cancel();btn.classList.remove("playing");btn.textContent="🔊";return;}
  document.querySelectorAll(".tts-msg-btn.playing").forEach(b=>{b.classList.remove("playing");b.textContent="🔊";});
  btn.classList.add("playing"); btn.textContent="⏹";
  const u=new SpeechSynthesisUtterance(text);
  u.lang="ru-RU"; u.rate=Chat.ttsSpeed;
  if(Chat.ttsVoice) u.voice=Chat.ttsVoice;
  u.onend=u.onerror=()=>{btn.classList.remove("playing");btn.textContent="🔊";};
  speechSynthesis.speak(u);
}

function ttsToggleGlobal(){
  Chat.ttsEnabled=!Chat.ttsEnabled;
  const lbl=$("ttsGlobalLabel"),btn=$("ttsGlobalBtn"),ctb=$("ctbTts");
  if(lbl) lbl.textContent=Chat.ttsEnabled?"ON":"OFF";
  if(btn) btn.classList.toggle("tts-off",!Chat.ttsEnabled);
  if(ctb) ctb.textContent=Chat.ttsEnabled?"🔊":"🔇";
  _activateGroup("cspTts",Chat.ttsEnabled?"on":"off");
  if(!Chat.ttsEnabled) speechSynthesis.cancel?.();
  api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_tts_enabled:Chat.ttsEnabled?"on":"off"})});
  toast(Chat.ttsEnabled?"🔊 Ovoz yoqildi":"🔇 Ovoz o'chirildi","info",1500);
}

function ttsSpeedChange(val){
  Chat.ttsSpeed=parseFloat(val);
  const lbl=$("ttsSpeedLabel"); if(lbl) lbl.textContent=val+"x";
  api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_tts_speed:val})});
}


// ══════════════════════════════════════════════════
// STT — Mikrofon
// ══════════════════════════════════════════════════
function toggleMic(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){toast("❌ Mikrofon qo'llab-quvvatlanmaydi","warn",3000);return;}
  const btn=$("micBtn");
  if(Chat.micActive){Chat.recognition?.stop();Chat.micActive=false;if(btn){btn.textContent="🎤";btn.classList.remove("mic-active");}return;}
  const rec=new SR();
  // til: o'zbek STT yo'q, rus STT ishlaydi
  rec.lang=Chat.uiLang==="uz"?"uz-UZ":"ru-RU";
  rec.continuous=false; rec.interimResults=true;
  Chat.recognition=rec; Chat.micActive=true;
  if(btn){btn.textContent="🔴";btn.classList.add("mic-active");}
  toast("🎤 Gapiring...","info",3000);
  rec.onresult=e=>{
    const t=Array.from(e.results).map(r=>r[0].transcript).join("");
    const inp=$("chatInput"); if(inp) inp.value=t;
  };
  rec.onend=()=>{Chat.micActive=false;if(btn){btn.textContent="🎤";btn.classList.remove("mic-active");}};
  rec.onerror=e=>{toast("🎤 Xato: "+e.error,"warn",2000);Chat.micActive=false;if(btn){btn.textContent="🎤";btn.classList.remove("mic-active");}};
  rec.start();
}


// ══════════════════════════════════════════════════
// SAHIFANI YUKLASH
// ══════════════════════════════════════════════════
async function loadChatHistory(){
  const s=await api("/api/chat/settings");
  if(s&&!s.error){
    if(s.ai_conversation_level) Chat.level=s.ai_conversation_level;
    if(s.ai_chat_mode)          Chat.mode=s.ai_chat_mode;
    if(s.ai_topic)              Chat.topic=s.ai_topic;
    if(s.ai_personality)        Chat.personality=s.ai_personality;
    if(s.ai_custom_topic)       Chat.customTopic=s.ai_custom_topic;
    if(s.ai_tts_speed)          Chat.ttsSpeed=parseFloat(s.ai_tts_speed)||0.9;
    if(s.ai_ui_lang)            Chat.uiLang=s.ai_ui_lang||"auto";
    Chat.ttsEnabled=s.ai_tts_enabled!=="off";
  }
  _applyChatSettings(); _updateTopicBar(); ttsInit(); _updateOfflineBadge();
  const history=await api("/api/chat/history");
  if(history&&history.length){
    const msgs=$("chatMessages");
    msgs.querySelectorAll(".chat-msg:not(:first-child)").forEach(m=>m.remove());
    [...history].reverse().forEach(h=>{if(h.id) appendChatMsg(h.role,h.content,h.id,h.correction);});
    msgs.scrollTop=msgs.scrollHeight;
  }
}

function _applyChatSettings(){
  _activateGroup("cspLevel",Chat.level);
  _activateGroup("cspPersonality",Chat.personality);
  _activateGroup("cspMode",Chat.mode);
  _activateGroup("cspTopic",Chat.topic);
  _activateGroup("cspTts",Chat.ttsEnabled?"on":"off");
  _activateGroup("langSwitch",Chat.uiLang);
  _setModeTab(Chat.mode);
  const inp=$("customTopicInput"); if(inp&&Chat.customTopic) inp.value=Chat.customTopic;
  const wrap=$("customTopicWrap"); if(wrap) wrap.style.display=Chat.topic==="free"?"flex":"none";
  const rng=$("ttsSpeedRange"); if(rng) rng.value=Chat.ttsSpeed;
  const lbl=$("ttsSpeedLabel"); if(lbl) lbl.textContent=Chat.ttsSpeed+"x";
  const glbl=$("ttsGlobalLabel"); if(glbl) glbl.textContent=Chat.ttsEnabled?"ON":"OFF";
  const gbtn=$("ttsGlobalBtn"); if(gbtn) gbtn.classList.toggle("tts-off",!Chat.ttsEnabled);
  const ctbTts=$("ctbTts"); if(ctbTts) ctbTts.textContent=Chat.ttsEnabled?"🔊":"🔇";
}

function _activateGroup(groupId,val){
  const el=$(groupId); if(!el) return;
  el.querySelectorAll("[data-val],[data-lang]").forEach(b=>{
    const bval=b.dataset.val||b.dataset.lang;
    b.classList.toggle("active",bval===val);
  });
}

function _setModeTab(mode){
  $("modeBtnText")?.classList.toggle("active",mode==="text");
  $("modeBtnChoice")?.classList.toggle("active",mode==="choice");
  const ta=$("textInputArea"),ca=$("choiceArea");
  if(ta) ta.style.display=mode==="text"?"flex":"none";
  if(ca) ca.style.display=mode==="choice"?"flex":"none";
  const hint=$("chatModeHint");
  if(hint) hint.textContent=mode==="text"?"⌨️ Sen yozasan — AI javob beradi":"🔘 AI yozadi — Sen tugma bosasan";
}

function _updateOfflineBadge(){
  const b=$("chatOfflineBadge"); if(b) b.style.display=State.internetAllowed?"none":"inline-flex";
}

function _updateTopicBar(){
  const meta=TOPIC_META[Chat.topic]||TOPIC_META.free;
  const icon=$("ctbIcon"),label=$("ctbLabel"),level=$("ctbLevel"),tts=$("ctbTts");
  if(icon)  icon.textContent=meta.icon;
  if(label) label.textContent=(Chat.topic==="free"&&Chat.customTopic)?`✨ ${Chat.customTopic}`:meta.label;
  if(level){const lm={beginner:"🟢 Boshlang'ich",intermediate:"🟡 O'rta",advanced:"🔴 Yuqori"};level.textContent=lm[Chat.level]||Chat.level;}
  if(tts)   tts.textContent=Chat.ttsEnabled?"🔊":"🔇";
}


// ══════════════════════════════════════════════════
// SOZLAMALAR
// ══════════════════════════════════════════════════
function toggleChatSettings(){
  const p=$("chatSettingsPanel"); if(!p) return;
  p.style.display=p.style.display==="none"?"block":"none";
}

async function setChatSetting(type,val,btn){
  if(type==="level")       Chat.level=val;
  if(type==="personality") Chat.personality=val;
  if(type==="tts"){
    Chat.ttsEnabled=val==="on";
    $("ttsGlobalLabel").textContent=Chat.ttsEnabled?"ON":"OFF";
    $("ttsGlobalBtn")?.classList.toggle("tts-off",!Chat.ttsEnabled);
    if(!Chat.ttsEnabled) speechSynthesis.cancel?.();
  }
  const gmap={level:"cspLevel",personality:"cspPersonality",tts:"cspTts"};
  if(gmap[type]) _activateGroup(gmap[type],val);
  _updateTopicBar();
  await api("/api/chat/settings",{method:"POST",body:JSON.stringify({
    ai_conversation_level:Chat.level, ai_personality:Chat.personality,
    ai_tts_enabled:Chat.ttsEnabled?"on":"off",
  })});
}

async function setChatTopic(topic,btn){
  Chat.topic=topic; _activateGroup("cspTopic",topic);
  const wrap=$("customTopicWrap"); if(wrap) wrap.style.display=topic==="free"?"flex":"none";
  _updateTopicBar();
  await api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_topic:topic})});
}

async function applyCustomTopic(){
  const inp=$("customTopicInput"); const val=inp?.value.trim()||"";
  Chat.customTopic=val; Chat.topic="free";
  _activateGroup("cspTopic","free"); _updateTopicBar();
  await api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_topic:"free",ai_custom_topic:val})});
  toast(`✅ Mavzu: "${val||'Erkin'}"`, "success",1500);
}

async function switchChatMode(mode){
  Chat.mode=mode; _setModeTab(mode); _activateGroup("cspMode",mode);
  await api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_chat_mode:mode})});
  if(mode==="choice") await startChoiceMode();
}

async function setUiLang(lang,btn){
  Chat.uiLang=lang;
  _activateGroup("langSwitch",lang);
  await api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_ui_lang:lang})});
  const lnames={auto:"🌐 Avtomatik",uz:"🇺🇿 O'zbek",ru:"🇷🇺 Rus"};
  toast(lnames[lang]||lang,"info",1200);
}


// ══════════════════════════════════════════════════
// XABAR QO'SHISH — appendChatMsg
// ══════════════════════════════════════════════════
function appendChatMsg(role,content,id=null,correction="",isOffline=false){
  const msgs=$("chatMessages");
  const div=document.createElement("div");
  div.className=`chat-msg ${role}`;
  const avatar=role==="assistant"?"🤖":"👤";
  const offTag=isOffline?`<span class="msg-offline-tag">📵offline</span>`:"";
  const corrHTML=correction?`<div class="msg-correction">✏️ ${correction}</div>`:"";
  const editBtn=(role==="assistant"&&id)?`<button class="msg-edit-btn" onclick="editChatMsg(${id},this)">✏️</button>`:"";
  const ttsText=content.split("\n")[0].replace(/[🎉✅❌📝💡👋🤖🇷🇺🇺🇿⭐🔊📵✨❓]/gu,"").trim();

  const fmt=content
    .replace(/\n/g,"<br>")
    .replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>")
    .replace(/❌\s*(.*?)\s*→\s*✅\s*(.*?)(<br>|$)/g,`<span class="err-wrong">❌ $1</span> → <span class="err-right">✅ $2</span>$3`)
    .replace(/«(.*?)»/g,`<em class="msg-ru">«$1»</em>`);

  div.innerHTML=`
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-bubble">${fmt}${offTag}</div>
      ${corrHTML}
      <div class="msg-actions">
        <button class="tts-msg-btn" onclick="ttsSpeakEl(this)"
          data-text="${ttsText.replace(/"/g,'&quot;')}" title="Eshitish">🔊</button>
        ${editBtn}
      </div>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
  Chat.msgCount++;
  if(role==="assistant"&&Chat.ttsEnabled) ttsSpeak(ttsText,true);
}

function _showTyping(){
  if(Chat.isTyping) return; Chat.isTyping=true;
  const div=document.createElement("div");
  div.className="chat-msg assistant typing-msg"; div.id="typingIndicator";
  div.innerHTML=`<div class="msg-avatar">🤖</div><div class="msg-body"><div class="msg-bubble typing-dots"><span></span><span></span><span></span></div></div>`;
  $("chatMessages").appendChild(div); $("chatMessages").scrollTop=$("chatMessages").scrollHeight;
}
function _hideTyping(){ Chat.isTyping=false; $("typingIndicator")?.remove(); }


// ══════════════════════════════════════════════════
// DYNAMIC ACTION TUGMALAR (Telegram bot uslubi)
// ══════════════════════════════════════════════════
function showActions(actions, contextQuestion=""){
  _hideActions();
  if(!actions||!actions.length) return;
  const area=$("actionArea"),btnsEl=$("actionBtns"),hint=$("actionHint");
  if(!area||!btnsEl) return;
  if(hint) hint.textContent="Tanlovingizni bosing:";

  btnsEl.innerHTML=actions.map((a,i)=>`
    <button class="action-btn action-${a.action||'default'}"
            onclick="handleAction('${a.action||''}','${(a.question||contextQuestion).replace(/'/g,"\\'")}','${(a.hint||'').replace(/'/g,"\\'")}','${(a.label||'').replace(/'/g,"\\'")}',${i})">
      ${a.label||a.action}
    </button>`).join("");

  area.style.display="flex";
  area.scrollIntoView({behavior:"smooth",block:"nearest"});
}

function _hideActions(){
  const area=$("actionArea"); if(!area) return;
  area.style.display="none";
  const btns=$("actionBtns"); if(btns) btns.innerHTML="";
}

async function handleAction(action, question, hint, label, idx){
  _hideActions();

  if(action==="teach"){
    // Inline teach input ko'rsatish
    openTeachInput(question, hint);
    return;
  }

  if(action==="skip"){
    _showTyping();
    const r=await api("/api/chat",{method:"POST",body:JSON.stringify({
      action:"skip", message:"", mode:Chat.mode, topic:Chat.topic,
      custom_topic:Chat.customTopic, ui_lang:Chat.uiLang,
    })});
    _hideTyping();
    if(r?.ok) appendChatMsg("assistant",r.response,null,"",r.offline||false);
    return;
  }

  if(action==="confirm"){
    // Umumiy tasdiqlash
    appendChatMsg("user",label);
    _showTyping();
    const r=await api("/api/chat",{method:"POST",body:JSON.stringify({
      message:label, mode:Chat.mode, topic:Chat.topic,
      custom_topic:Chat.customTopic, ui_lang:Chat.uiLang,
    })});
    _hideTyping();
    if(r?.ok){
      appendChatMsg("assistant",r.response,null,"",r.offline||false);
      if(r.actions?.length) showActions(r.actions,question);
      if(r.choices?.length) showChoices(r.choices);
    }
    await loadProfile();
    return;
  }

  // Default: xabar sifatida yuborish
  appendChatMsg("user",label||question);
  await _sendToApi(label||question);
}

// ── Inline teach input ────────────────────────────
function openTeachInput(question, hint="Javobni yozing..."){
  Chat.pendingTeach={question, hint};
  const area=$("teachInputArea"),qEl=$("tiaQuestion"),inp=$("tiaAnswerInput"),title=$("tiaTitle");
  if(!area) return;
  if(title) title.textContent="🧠 AI ga o'rgatish";
  if(qEl)   qEl.textContent=`❓ Savol: "${question}"`;
  if(inp){  inp.placeholder=hint; inp.value=""; }
  area.style.display="block";
  setTimeout(()=>inp?.focus(),100);
}

function closeTeachInput(){
  const area=$("teachInputArea"); if(area) area.style.display="none";
  Chat.pendingTeach=null;
}

async function confirmTeach(){
  if(!Chat.pendingTeach) return;
  const ans=($("tiaAnswerInput")?.value||"").trim();
  if(!ans){toast("Javobni kiriting","warn");return;}
  const {question}=Chat.pendingTeach;
  closeTeachInput();
  appendChatMsg("user",`✅ "${question}" → "${ans}"`);
  _showTyping();
  const r=await api("/api/chat",{method:"POST",body:JSON.stringify({
    action:"confirm_teach",
    teach_question:question,
    teach_answer:ans,
    message:"",
    mode:Chat.mode,
  })});
  _hideTyping();
  if(r?.ok) appendChatMsg("assistant",r.response,null,"",false);
  else toast("❌ Xatolik","error");
}


// ══════════════════════════════════════════════════
// MATNLI REJIM — sendChat
// ══════════════════════════════════════════════════
async function sendChat(){
  const inp=$("chatInput");
  const msg=inp?.value.trim();
  if(!msg||Chat.isTyping) return;
  inp.value=""; inp.focus();
  _hideActions();
  appendChatMsg("user",msg);
  await _sendToApi(msg);
}

async function _sendToApi(msg){
  _showTyping();
  const r=await api("/api/chat",{method:"POST",body:JSON.stringify({
    message:msg, mode:"text", topic:Chat.topic,
    custom_topic:Chat.customTopic, ui_lang:Chat.uiLang,
  })});
  _hideTyping();
  if(r?.ok){
    appendChatMsg("assistant",r.response,null,"",r.offline||false);
    if(r.offline) toast("📵 Offline AI","info",1500);
    // ACTION tugmalar
    if(r.actions?.length) showActions(r.actions, msg);
    // CHOICES (tugmali rejim)
    if(r.choices?.length) showChoices(r.choices);
  } else {
    appendChatMsg("assistant",`❌ ${r?.error||"Xatolik yuz berdi"}`);
    toast("❌ "+(r?.error||"AI xatosi"),"error");
  }
  await loadProfile();
}

function clearChatInput(){ const i=$("chatInput"); if(i){i.value="";i.focus();} }

function insertText(txt){
  const i=$("chatInput"); if(!i) return;
  i.value=(i.value+txt).trimStart(); i.focus();
}

function insertPhrase(){
  const pool=[
    "Меня зовут ","Я из ","Я живу в ","Мне нравится ",
    "Я люблю ","Расскажи мне о ","Я не понимаю.","Повторите, пожалуйста.",
    "Как это по-русски?","Что значит ","Я хочу ","Буgun kun qanday o'tdi?",
    "Men bilmoqchiman: ","Toshkent haqida nima bilasan?",
  ];
  insertText(pool[Math.floor(Math.random()*pool.length)]);
}


// ══════════════════════════════════════════════════
// TUGMALI REJIM
// ══════════════════════════════════════════════════
async function startChoiceMode(){
  _showTyping();
  const r=await api("/api/chat/choices",{method:"POST",body:JSON.stringify({
    topic:Chat.topic, custom_topic:Chat.customTopic, level:Chat.level,
  })});
  _hideTyping();
  if(!r?.ok){appendChatMsg("assistant","❌ AI bilan bog'lanib bo'lmadi");return;}
  appendChatMsg("assistant",r.response,null,"",r.offline||false);
  if(r.actions?.length) showActions(r.actions);
  showChoices(r.choices||[]);
}

function showChoices(choices){
  const area=$("choiceArea"),btnsEl=$("choiceBtns");
  if(!area||!btnsEl||!choices.length){if(area)area.style.display="none";return;}
  btnsEl.innerHTML=choices.map((c,i)=>`
    <button class="choice-option" onclick="pickChoice(this,'${c.replace(/'/g,"\\'")}',${i})" data-idx="${i}">
      <span class="co-num">${i+1}</span>
      <span class="co-text">${c}</span>
      <button class="tts-choice-btn" onclick="event.stopPropagation();ttsSpeak('${c.replace(/'/g,"\\'")}',true)" title="Eshitish">🔊</button>
    </button>`).join("");
  area.style.display="flex";
  if(area._kh) document.removeEventListener("keydown",area._kh);
  area._kh=(e)=>{
    if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA") return;
    const n=parseInt(e.key);
    if(n>=1&&n<=choices.length){const b=btnsEl.querySelectorAll(".choice-option")[n-1];if(b)pickChoice(b,choices[n-1],n-1);}
  };
  document.addEventListener("keydown",area._kh);
}

function _clearChoices(){
  const area=$("choiceArea"); if(!area) return;
  area.style.display="none";
  if(area._kh){document.removeEventListener("keydown",area._kh);area._kh=null;}
  $("choiceBtns").innerHTML="";
}

async function pickChoice(btn,chosenText){
  if(Chat.isTyping) return;
  _clearChoices(); _hideActions();
  appendChatMsg("user",chosenText);
  _showTyping();
  const r=await api("/api/chat",{method:"POST",body:JSON.stringify({
    message:chosenText, mode:"choice", topic:Chat.topic,
    custom_topic:Chat.customTopic, ui_lang:Chat.uiLang,
  })});
  _hideTyping();
  if(r?.ok){
    appendChatMsg("assistant",r.response,null,"",r.offline||false);
    if(r.actions?.length) showActions(r.actions,chosenText);
    const pool={
      free:["Расскажи больше.","Не понимаю.","Хорошо!","Другая тема."],
      greet:["Привет! Как дела?","Меня зовут...","Я из Ташкента.","Рад познакомиться!"],
    };
    showChoices(r.choices?.length?r.choices:(pool[Chat.topic]||pool.free));
  } else {
    appendChatMsg("assistant",`❌ ${r?.error||"Xatolik"}`);
    showChoices(["Davom eting.","Boshqa savol.","Tushunmadim.","Xayr!"]);
  }
  await loadProfile();
}

async function skipChoice(){
  _clearChoices(); if(Chat.isTyping) return;
  _showTyping();
  const r=await api("/api/chat/choices",{method:"POST",body:JSON.stringify({topic:Chat.topic,custom_topic:Chat.customTopic,level:Chat.level})});
  _hideTyping();
  if(r?.ok){appendChatMsg("assistant",r.response,null,"",r.offline||false);showChoices(r.choices||[]);}
}


// ══════════════════════════════════════════════════
// AI O'QITISH MODALI
// ══════════════════════════════════════════════════
function openTeachPanel(){
  loadKnowledgeList();
  openModal("teachModal");
}

async function loadKnowledgeList(){
  const listEl=$("knowledgeList"); if(!listEl) return;
  listEl.innerHTML=`<div class="loading-spinner"><span class="spinner"></span></div>`;
  const items=await api("/api/chat/knowledge");
  if(!items||items.error){listEl.innerHTML=`<div class="empty-state"><p>Yuklab bo'lmadi</p></div>`;return;}
  if(!items.length){
    listEl.innerHTML=`<div class="empty-state"><div class="empty-icon">🧠</div><p>Hali hech narsa o'rgatilmagan.<br>AI ga birinchi ma'lumotni o'rgating!</p></div>`;
    return;
  }
  const catIcons={general:"📦",geo:"🗺️",history:"📜",science:"🔬",culture:"🎭",person:"👤",word:"💬"};
  listEl.innerHTML=items.map(k=>`
    <div class="knowledge-item" id="ki-${k.id}">
      <div class="ki-cat">${catIcons[k.category]||"📦"}</div>
      <div class="ki-body">
        <div class="ki-q">${k.question}</div>
        <div class="ki-a">${k.answer.length>80?k.answer.slice(0,80)+"...":k.answer}</div>
        <div class="ki-meta">
          <span class="ki-lang">${k.lang==="uz"?"🇺🇿":k.lang==="ru"?"🇷🇺":"🌐"}</span>
          <span class="ki-use">${k.use_count} marta ishlatildi</span>
          <span class="ki-date">${fmtDate(k.added_at)}</span>
        </div>
      </div>
      <button class="btn btn-sm btn-danger ki-del" onclick="deleteKnowledge(${k.id})" title="O'chirish">🗑</button>
    </div>`).join("");
}

async function submitTeach(){
  const q=($("teachQ")?.value||"").trim();
  const a=($("teachA")?.value||"").trim();
  const lang=$("teachLang")?.value||"ru";
  const cat=$("teachCat")?.value||"general";
  if(!q||!a){toast("Savol va javob to'ldirilishi shart","warn");return;}
  const r=await api("/api/chat/teach",{method:"POST",body:JSON.stringify({question:q,answer:a,lang,category:cat})});
  if(r?.ok){
    toast("✅ AI o'rgandi: «"+q+"»","success");
    $("teachQ").value=""; $("teachA").value="";
    appendChatMsg("assistant",r.message,null,"",false);
    loadKnowledgeList();
  } else toast("❌ "+(r?.error||"Xatolik"),"error");
}

async function deleteKnowledge(id){
  if(!confirm("Ushbu bilimni o'chirish?")) return;
  await api(`/api/chat/knowledge/${id}`,{method:"DELETE"});
  $(`ki-${id}`)?.remove();
  toast("🗑 O'chirildi","info");
}

// ══════════════════════════════════════════════════
// UMUMIY AMALLAR
// ══════════════════════════════════════════════════
async function clearChat(){
  if(!confirm("Barcha suhbat tarixini tozalash?")) return;
  speechSynthesis.cancel?.();
  await api("/api/chat/clear",{method:"POST"});
  $("chatMessages").querySelectorAll(".chat-msg:not(:first-child)").forEach(m=>m.remove());
  _clearChoices(); _hideActions(); closeTeachInput();
  Chat.msgCount=0; toast("🗑 Tozalandi","info");
}

async function startFreshChat(){
  await clearChat();
  toggleChatSettings(); _updateTopicBar();
  if(Chat.mode==="choice") await startChoiceMode();
  else {
    const meta=TOPIC_META[Chat.topic]||TOPIC_META.free;
    const topic=(Chat.topic==="free"&&Chat.customTopic)?`"${Chat.customTopic}"`:meta.label;
    appendChatMsg("assistant",
      `Yangi suhbat! 🇷🇺🇺🇿\n📂 Mavzu: ${meta.icon} ${topic}\n📊 Daraja: ${Chat.level}\n💬 Til: ${Chat.uiLang==="uz"?"🇺🇿 O'zbek":Chat.uiLang==="ru"?"🇷🇺 Rus":"🌐 Avtomatik"}\n\nYozing yoki gapiring!`,
      null,"",false);
  }
}

function editChatMsg(id,btn){
  const c=prompt("Tuzatishni kiriting:"); if(!c) return;
  api("/api/chat/correct",{method:"POST",body:JSON.stringify({id,correction:c})});
  const d=document.createElement("div"); d.className="msg-correction"; d.textContent="✏️ "+c;
  btn.closest(".msg-body").insertBefore(d,btn.closest(".msg-actions")); btn.remove();
  toast("✅ Saqlandi","success");
}

function exportChat(){
  const msgs=$("chatMessages").querySelectorAll(".chat-msg");
  let text=`RusLearn Pro — AI Suhbat\nSana: ${new Date().toLocaleDateString("uz-UZ")}\n${"─".repeat(40)}\n\n`;
  msgs.forEach(m=>{
    const role=m.classList.contains("user")?"Men":"AI (Alex)";
    const bubble=m.querySelector(".msg-bubble");
    if(bubble) text+=`[${role}]: ${bubble.innerText.replace(/🔊|⏹/g,"").trim()}\n\n`;
  });
  const a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([text],{type:"text/plain;charset=utf-8"}));
  a.download=`ruslearn_chat_${new Date().toISOString().slice(0,10)}.txt`;
  a.click(); toast("📥 Yuklab olindi","success");
}

// eski muvofiqlik
async function saveChatLevel(){
  const s=$("chatLevelSel"); if(s) Chat.level=s.value;
  await api("/api/chat/settings",{method:"POST",body:JSON.stringify({ai_conversation_level:Chat.level})});
}
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
// ══════════════════════════════════════════════════
// PROGRESS v2 — Charts, Streak Banner, Radar Chart
// ══════════════════════════════════════════════════
const Charts = { week:null, growth:null, radar:null, study:null };
let _weekData  = null;
let _radarData = null;
const _catLabels = {
  greeting:"👋 Salomlashish", numbers:"🔢 Raqamlar", colors:"🎨 Ranglar",
  family:"👨‍👩‍👧 Oila", food:"🍎 Ovqat", verbs:"⚡ Fe'llar",
  adjectives:"🌟 Sifatlar", travel:"✈️ Sayohat", work:"💼 Ish",
  health:"🏥 Sog'liq", nature:"🌿 Tabiat", time_ext:"⏰ Vaqt",
  emotions:"😊 His", navigation:"🗺️ Yo'l", introduction:"🤝 Tanishish",
  transport:"🚗 Transport", animals:"🐾 Hayvon", clothing:"👗 Kiyim",
  school:"🏫 Maktab", sport:"⚽ Sport", math:"🔢 Math",
  body:"🫀 Tana", house:"🏠 Uy", weather:"🌤️ Ob-havo", places:"🏛️ Joylar",
};

function showStreakBanner(notif){
  if(!notif) return;
  const banner=$("streakNotifBanner"); if(!banner) return;
  const iconMap={info:"ℹ️",success:"🔥",gold:"🏆",warn:"⏰"};
  $("snbIcon").textContent=iconMap[notif.type]||"🔥";
  $("snbMsg").textContent=notif.msg;
  banner.className=`streak-notif-banner snb-${notif.type}`;
  banner.style.display="flex";
  clearTimeout(banner._t);
  banner._t=setTimeout(()=>{banner.style.display="none";},8000);
}

function buildWeekChart(days,metric="xp"){
  const canvas=$("weekChart"); if(!canvas||!window.Chart) return;
  if(Charts.week){Charts.week.destroy();Charts.week=null;}
  const M={
    xp:     {key:"xp",     color:"rgba(79,142,247,0.75)", border:"#4f8ef7",label:"XP"},
    minutes:{key:"minutes",color:"rgba(52,201,126,0.75)", border:"#34c97e",label:"Daqiqa"},
    words:  {key:"words",  color:"rgba(240,192,64,0.75)", border:"#f0c040",label:"So'z"},
  };
  const m=M[metric]||M.xp;
  const dt=days.map(d=>d[m.key]||0);
  Charts.week=new Chart(canvas,{
    type:"bar",
    data:{labels:days.map(d=>d.day),datasets:[{
      label:m.label,data:dt,
      backgroundColor:dt.map(v=>v>0?m.color:"rgba(255,255,255,0.05)"),
      borderColor:m.border,borderWidth:2,borderRadius:6,
    }]},
    options:{responsive:true,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:ctx=>`${ctx.raw} ${m.label}`}}},
      scales:{
        y:{beginAtZero:true,ticks:{color:"#9ba3b8",maxTicksLimit:5},grid:{color:"#2a2f40"}},
        x:{ticks:{color:"#9ba3b8"},grid:{display:false}},
      }},
  });
}

function switchWeekTab(metric,btn){
  document.querySelectorAll(".week-tab").forEach(b=>b.classList.remove("active"));
  btn.classList.add("active");
  if(_weekData) buildWeekChart(_weekData,metric);
}

function buildGrowthChart(lh){
  const canvas=$("growthChart"); if(!canvas||!window.Chart) return;
  if(Charts.growth){Charts.growth.destroy();Charts.growth=null;}
  if(!lh?.length) return;
  const items=lh.slice(-30);
  const step=Math.max(1,Math.floor(items.length/6));
  const labels=items.map((d,i)=>i%step===0?d.date.slice(5):"");
  const xpData=items.map(d=>d.xp||0);
  const thresholds=[
    {y:200, label:"Boshlang'ich",color:"rgba(52,201,126,0.35)"},
    {y:500, label:"O'rta",       color:"rgba(79,142,247,0.35)"},
    {y:1000,label:"O'rta-yuqori",color:"rgba(240,192,64,0.35)"},
    {y:2000,label:"Ilg'or",      color:"rgba(240,140,64,0.35)"},
    {y:4000,label:"Ustoz",       color:"rgba(168,120,247,0.35)"},
  ];
  Charts.growth=new Chart(canvas,{
    type:"line",
    data:{labels,datasets:[
      {label:"XP",data:xpData,borderColor:"#4f8ef7",backgroundColor:"rgba(79,142,247,0.1)",
       borderWidth:2.5,pointRadius:3,fill:true,tension:0.35},
      ...thresholds.map(t=>({label:t.label,data:Array(items.length).fill(t.y),
        borderColor:t.color,borderWidth:1,borderDash:[5,5],pointRadius:0,fill:false})),
    ]},
    options:{responsive:true,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:true,labels:{filter:i=>i.text==="XP",color:"#9ba3b8",font:{size:11}}},
        tooltip:{callbacks:{label:ctx=>ctx.datasetIndex===0?`${ctx.raw} XP`:`${ctx.dataset.label}: ${ctx.raw}`}}},
      scales:{
        y:{beginAtZero:false,ticks:{color:"#9ba3b8",maxTicksLimit:6},grid:{color:"#2a2f40"}},
        x:{ticks:{color:"#9ba3b8",maxRotation:0},grid:{display:false}},
      }},
  });
  const colors=["#34c97e","#4f8ef7","#f0c040","#f08c40","#a878f7"];
  const legEl=$("growthLegend");
  if(legEl) legEl.innerHTML=thresholds.map((t,i)=>`
    <span class="growth-leg-item">
      <span style="background:${colors[i]};width:18px;height:2px;display:inline-block;
        vertical-align:middle;border-radius:2px;margin-right:4px"></span>
      ${t.y} XP — ${t.label}</span>`).join("");
}

function buildRadarChart(radarData){
  const canvas=$("radarChart"); if(!canvas||!window.Chart) return;
  if(Charts.radar){Charts.radar.destroy();Charts.radar=null;}
  const items=radarData.filter(r=>r.total>0).slice(0,12);
  if(!items.length) return;
  const labels=items.map(r=>(_catLabels[r.category]||r.category).replace(/[^\w\s']/gu,"").trim().slice(0,12));
  const data  =items.map(r=>r.total>0?Math.min(100,Math.round(r.correct/r.total*100)):0);
  Charts.radar=new Chart(canvas,{
    type:"radar",
    data:{labels,datasets:[{label:"O'zlashtirish %",data,
      backgroundColor:"rgba(79,142,247,0.18)",borderColor:"#4f8ef7",
      borderWidth:2,pointBackgroundColor:"#4f8ef7",pointRadius:3}]},
    options:{responsive:true,
      scales:{r:{beginAtZero:true,max:100,
        ticks:{stepSize:25,color:"#9ba3b8",font:{size:10},backdropColor:"transparent"},
        grid:{color:"#2a2f40"},pointLabels:{color:"#9ba3b8",font:{size:10}},
        angleLines:{color:"#2a2f40"}}},
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:ctx=>`${ctx.raw}% o'zlashtirilgan`}}}},
  });
}

function switchRadarView(view,btn){
  document.querySelectorAll(".radar-view-btn").forEach(b=>b.classList.remove("active"));
  btn.classList.add("active");
  const bv=$("radarBarView"),cv=$("radarChartView");
  if(view==="bar"){
    if(bv) bv.style.display="block";
    if(cv) cv.style.display="none";
  } else {
    if(bv) bv.style.display="none";
    if(cv) cv.style.display="block";
    if(_radarData) buildRadarChart(_radarData);
  }
}

async function loadProgress(){
  const [stats,history,weekReport,goalsReport,adaptStats]=await Promise.all([
    api("/api/stats"),api("/api/history?limit=20"),api("/api/weekly-report"),
    api("/api/goals/report"),api("/api/adaptive/stats"),
  ]);
  if(stats?.error) return;

  if(weekReport?.streak_notif) showStreakBanner(weekReport.streak_notif);

  const streak=weekReport?.streak||0;
  const streakEl=$("streakCard");
  if(streakEl){
    $("streakCount").textContent=streak;
    $("streakFire").textContent=streak>=14?"🏆":streak>=7?"🔥🔥":streak>=3?"🔥":"❄️";
    const wDays=weekReport?.days||[];
    $("streakDays").innerHTML=wDays.map(d=>`
      <div class="streak-day ${d.xp>0?"active":""}">
        <div class="sd-dot"></div><div class="sd-label">${d.day}</div>
      </div>`).join("");
    streakEl.classList.remove("streak-gold","streak-fire");
    if(streak>=7) streakEl.classList.add("streak-gold");
    else if(streak>=3) streakEl.classList.add("streak-fire");
  }

  if(goalsReport&&!goalsReport.error){
    const {goals,today,pcts,avg_pct,message}=goalsReport;
    $("goalsList").innerHTML=[
      {icon:"📖",label:"So'zlar",done:today.words,  goal:goals.words,  pct:pcts.words,  color:"var(--green)"},
      {icon:"⏱", label:"Daqiqa", done:today.minutes,goal:goals.minutes,pct:pcts.minutes,color:"var(--accent)"},
      {icon:"⭐", label:"XP",     done:today.xp,     goal:goals.xp,     pct:pcts.xp,    color:"var(--yellow)"},
    ].map(g=>`
      <div class="goal-row">
        <span class="goal-icon">${g.icon}</span>
        <div class="goal-info">
          <div class="goal-label">${g.label}: <b>${g.done}</b>/${g.goal}</div>
          <div class="goal-bar-wrap"><div class="goal-bar" style="width:${g.pct}%;background:${g.color}"></div></div>
        </div>
        <span class="goal-pct" style="color:${g.color}">${g.pct}%</span>
      </div>`).join("");
    $("goalsMsg").textContent=message;
    $("goalsMsg").className=`goals-msg ${avg_pct>=100?"goals-done":avg_pct>=70?"goals-good":"goals-pending"}`;
  }

  const lvlList=[
    {name:"Yangi boshlovchi",min:0,   max:200,  icon:"🌱",color:"var(--green)"},
    {name:"Boshlang'ich",    min:200, max:500,  icon:"📗",color:"var(--green)"},
    {name:"O'rta daraja",   min:500, max:1000, icon:"📘",color:"var(--accent)"},
    {name:"O'rta-yuqori",   min:1000,max:2000, icon:"📙",color:"var(--yellow)"},
    {name:"Ilg'or",         min:2000,max:4000, icon:"📕",color:"var(--orange)"},
    {name:"Ustoz",          min:4000,max:9999, icon:"🏆",color:"var(--purple)"},
  ];
  const xp=stats.total_xp||0;
  const lvl=lvlList.find(l=>xp>=l.min&&xp<l.max)||lvlList[lvlList.length-1];
  const lvlPct=Math.min(100,Math.round((xp-lvl.min)/(lvl.max-lvl.min)*100));
  $("levelCard").innerHTML=`
    <div class="lc-icon">${lvl.icon}</div>
    <div class="lc-info">
      <div class="lc-name" style="color:${lvl.color}">${lvl.name}</div>
      <div class="lc-xp">${xp} XP · Keyingi: ${lvl.max} XP</div>
      <div class="xp-bar-wrap"><div class="xp-bar" style="width:${lvlPct}%;background:${lvl.color}"></div></div>
    </div>
    <div style="text-align:right">
      <div style="font-size:26px;font-weight:800;color:${lvl.color}">${lvlPct}%</div>
      <div class="muted" style="font-size:11px">joriy daraja</div>
    </div>`;

  if(weekReport?.days){
    _weekData=weekReport.days;
    buildWeekChart(_weekData,"xp");
    $("weekTotalXp").textContent    =weekReport.total_xp    ||0;
    $("weekTotalMin").textContent   =weekReport.total_min   ||0;
    $("weekTotalWords").textContent =weekReport.total_words ||0;
    $("weekActiveDays").textContent =weekReport.active_days ||0;
  }

  if(weekReport?.level_history) buildGrowthChart(weekReport.level_history);

  const radarSrc=weekReport?.radar||adaptStats?.all||[];
  _radarData=radarSrc;
  const radarEl=$("radarGrid");
  if(radarEl){
    if(radarSrc.length){
      const sorted=[...radarSrc].sort((a,b)=>{
        const pa=a.total>0?a.correct/a.total:0;
        const pb=b.total>0?b.correct/b.total:0;
        return pb-pa;
      });
      radarEl.innerHTML=sorted.map(r=>{
        const pct=r.total>0?Math.min(100,Math.round(r.correct/r.total*100)):0;
        const bc=pct>=70?"var(--green)":pct>=40?"var(--yellow)":"var(--red)";
        return `
          <div class="radar-item" title="${r.correct}✅ ${r.wrong||(r.total-r.correct)}❌">
            <div class="radar-label">${_catLabels[r.category]||r.category}</div>
            <div class="radar-bar-wrap"><div class="radar-bar" style="width:${pct}%;background:${bc}"></div></div>
            <div class="radar-pct" style="color:${bc}">${pct}%</div>
          </div>`;
      }).join("");
    } else {
      radarEl.innerHTML=`<div class="empty-state"><div class="empty-icon">🕸</div>
        <p>Hali statistika yo'q.<br>So'z o'rganish yoki test ishlashni boshlang!</p></div>`;
    }
  }

  const weakList=$("weakList");
  const weakItems=radarSrc.filter(r=>r.total>0)
    .map(r=>({...r,err:(r.wrong||(r.total-r.correct))/Math.max(r.total,1)}))
    .sort((a,b)=>b.err-a.err).slice(0,5);
  if(weakList){
    weakList.innerHTML=weakItems.length
      ? weakItems.map(r=>{
          const p=r.total>0?Math.min(100,Math.round(r.correct/r.total*100)):0;
          return `<div class="weak-item">
            <span class="weak-cat">${_catLabels[r.category]||r.category}</span>
            <span class="weak-pct" style="color:${p>=50?"var(--yellow)":"var(--red)"}">${p}%</span>
            <span class="weak-stat">${r.correct}✅ ${r.wrong||(r.total-r.correct)}❌</span>
            <button class="btn btn-sm btn-primary" onclick="navigate('adaptive')">Mashq</button>
          </div>`;
        }).join("")
      : `<div class="muted" style="padding:8px">Kuchsiz tomonlarni aniqlash uchun test ishlang!</div>`;
  }

  $("fullStatsGrid").innerHTML=`
    <div class="stat-card"><div class="stat-val">${stats.total_words||0}</div><div class="stat-lbl">📖 Jami so'zlar</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--green)">${stats.learned_words||0}</div><div class="stat-lbl">✅ O'rganilgan</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--yellow)">${stats.due_reviews||0}</div><div class="stat-lbl">🔁 Takrorlash</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--orange)">${streak}</div><div class="stat-lbl">🔥 Streak</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--accent)">${xp}</div><div class="stat-lbl">⭐ Jami XP</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--purple)">${stats.total_sessions||0}</div><div class="stat-lbl">📚 Sessiyalar</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--green)">${stats.grammar_rules||0}</div><div class="stat-lbl">📝 Grammatika</div></div>
    <div class="stat-card"><div class="stat-val" style="color:var(--red)">${stats.missed_lessons||0}</div><div class="stat-lbl">⚠ O'tkazilgan</div></div>`;

  if(Charts.study){Charts.study.destroy();Charts.study=null;}
  const studyCanvas=$("studyChart");
  if(studyCanvas&&window.Chart&&weekReport?.days){
    const d=weekReport.days;
    const mn=d.map(x=>x.minutes||0);
    Charts.study=new Chart(studyCanvas,{
      type:"bar",
      data:{labels:d.map(x=>x.day),datasets:[{label:"Daqiqa",data:mn,
        backgroundColor:mn.map(v=>v>0?"rgba(79,142,247,0.6)":"rgba(255,255,255,0.05)"),
        borderColor:"#4f8ef7",borderWidth:2,borderRadius:6}]},
      options:{responsive:true,plugins:{legend:{display:false}},
        scales:{
          y:{beginAtZero:true,ticks:{color:"#9ba3b8",maxTicksLimit:5},grid:{color:"#2a2f40"}},
          x:{ticks:{color:"#9ba3b8"},grid:{display:false}},
        }},
    });
  }

  const masteryData=[
    {label:"🟢 Boshlang'ich",key:"beginner",    color:"var(--green)"},
    {label:"🟡 O'rta",       key:"intermediate",color:"var(--yellow)"},
    {label:"🔴 Yuqori",      key:"advanced",    color:"var(--red)"},
  ];
  const wStats=await Promise.all(masteryData.map(async m=>{
    const ws=await api(`/api/words?level=${m.key}&limit=1000`);
    const learned=(ws||[]).filter(w=>(w.times_correct||0)>0).length;
    return {...m,total:(ws||[]).length,learned};
  }));
  $("masteryBreakdown").innerHTML=wStats.map(m=>{
    const p=m.total>0?Math.round(m.learned/m.total*100):0;
    return `<div class="mastery-row">
      <div class="mastery-label">${m.label}</div>
      <div class="mastery-bar-wrap"><div class="mastery-bar" style="width:${p}%;background:${m.color}"></div></div>
      <div class="mastery-val">${m.learned}/${m.total} (${p}%)</div>
    </div>`;
  }).join("");

  const histEl=$("historyTable");
  if(history?.length){
    histEl.innerHTML=history.slice(0,15).map(h=>`
      <div class="history-row">
        <span>${lessonTypeEmoji(h.lesson_type)}</span>
        <span style="flex:1">${{vocabulary:"Lug'at",grammar:"Grammatika",
          flashcards:"Kartochkalar",quiz:"Test",chat:"AI Suhbat",game:"O'yin",
          adaptive:"Adaptiv",roleplay:"Roleplay"}[h.lesson_type]||h.lesson_type}</span>
        <span style="color:var(--text3)">${secToMin(h.duration_sec||0)}</span>
        <span style="color:var(--yellow)">${h.score||0}%</span>
        <span style="color:var(--purple)">+${h.xp_earned||0} XP</span>
        <span style="color:var(--text3);font-size:11px">${timeAgo(h.studied_at)}</span>
      </div>`).join("");
  } else {
    histEl.innerHTML=`<div class="empty-state" style="padding:20px"><p>O'qish tarixi yo'q</p></div>`;
  }
}

async function loadGoalsForm(){
  const r = await api("/api/goals");
  if(!r||r.error) return;
  if($("goalWords"))   $("goalWords").value   = r.goals?.words   || 10;
  if($("goalMinutes")) $("goalMinutes").value  = r.goals?.minutes || 30;
  if($("goalXp"))      $("goalXp").value       = r.goals?.xp     || 50;
}

async function saveGoals(){
  const r = await api("/api/goals",{method:"POST",body:JSON.stringify({
    words:   parseInt($("goalWords")?.value)   || 10,
    minutes: parseInt($("goalMinutes")?.value) || 30,
    xp:      parseInt($("goalXp")?.value)      || 50,
  })});
  if(r?.ok){ toast("✅ Maqsadlar saqlandi","success"); closeModal("goalsModal"); loadProgress(); }
}

// ── Xotira modal ──────────────────────────────────
async function loadMemoryForm(){
  const mem = await api("/api/memory");
  if(!mem) return;
  const map = {
    user_name:"memName",user_age:"memAge",user_city:"memCity",
    user_job:"memJob",user_hobbies:"memHobbies",user_goal:"memGoal",user_notes:"memNotes",
  };
  Object.entries(map).forEach(([k,id])=>{ const el=$(id); if(el) el.value=mem[k]||""; });
}

async function saveMemory(){
  const map = {
    memName:"user_name",memAge:"user_age",memCity:"user_city",
    memJob:"user_job",memHobbies:"user_hobbies",memGoal:"user_goal",memNotes:"user_notes",
  };
  const data = {};
  Object.entries(map).forEach(([id,k])=>{ const el=$(id); if(el) data[k]=el.value.trim(); });
  await api("/api/memory",{method:"POST",body:JSON.stringify(data)});
  // Ismni profile ga ham saqlash
  if(data.user_name){
    await api("/api/profile",{method:"POST",body:JSON.stringify({name:data.user_name})});
    await loadProfile();
  }
  toast("✅ AI xotiraga saqlandi! Endi sizni bilaman 😊","success");
  closeModal("memoryModal");
}

// sidebar streak badge yangilash
async function updateStreakBadge(){
  const r = await api("/api/streak");
  if(!r||r.error) return;
  const el = $("profileStreak");
  if(el) el.textContent = `🔥${r.current}`;
}


// ══════════════════════════════════════════════════
// ADAPTIV TEST
// ══════════════════════════════════════════════════
const AdaptState = { questions:[], index:0, score:0, xp:0, answers:[], type:"words", start:null };

async function loadAdaptivePage(){
  // Kuchsiz kategoriyalarni ko'rsatish
  const stats = await api("/api/adaptive/stats");
  const panel = $("weakFocusPanel");
  if(!panel) return;
  const weakest = stats?.weakest || [];
  if(weakest.length){
    const catLabels={
      greeting:"👋 Salomlashish",numbers:"🔢 Raqamlar",colors:"🎨 Ranglar",
      family:"👨‍👩‍👧 Oila",food:"🍎 Ovqat",verbs:"⚡ Fe'llar",adjectives:"🌟 Sifatlar",
      travel:"✈️ Sayohat",navigation:"🗺️ Yo'l",school:"🏫 Maktab",
      introduction:"🤝 Tanishish",sport:"⚽ Sport",math:"🔢 Math",
      weather:"🌤️ Ob-havo",body:"🫀 Tana",clothing:"👗 Kiyim",
    };
    panel.innerHTML=`
      <div class="weak-focus-title">⚠️ Bu kategoriyalar ayniqsa kuchsiz:</div>
      <div class="weak-focus-chips">
        ${weakest.map(w=>`<span class="weak-chip">${catLabels[w.category]||w.category} (${Math.round(w.wrong/(w.correct+w.wrong||1)*100)}% xato)</span>`).join("")}
      </div>`;
  } else {
    panel.innerHTML=`<div class="muted" style="padding:8px">Test ishlashingiz bilan kuchsiz tomonlaringiz aniqlanadi.</div>`;
  }
}

async function startAdaptiveTest(){
  const type  = document.querySelector('input[name="adaptType"]:checked')?.value || "words";
  const count = parseInt(document.querySelector('input[name="adaptCount"]:checked')?.value || "10");
  AdaptState.type    = type;
  AdaptState.index   = 0;
  AdaptState.score   = 0;
  AdaptState.xp      = 0;
  AdaptState.answers = [];
  AdaptState.start   = Date.now();

  let questions = [];
  if(type === "cloze"){
    const clozeList = await api(`/api/cloze?limit=${count}`);
    questions = (clozeList||[]).map(c=>({
      type:"cloze", id:c.id, category:c.category,
      sentence_ru:c.sentence_ru, sentence_uz:c.sentence_uz,
      answer:c.answer,
      choices: JSON.parse(c.options_json||"[]"),
    }));
  } else {
    const words = await api(`/api/adaptive/words?limit=${count*3}`);
    const pool  = (words||[]).sort(()=>Math.random()-0.5).slice(0,count);
    questions   = pool.map(w=>{
      const wrong = pool.filter(x=>x.id!==w.id)
        .sort(()=>Math.random()-0.5).slice(0,3).map(x=>x.uzbek);
      const choices = [...wrong, w.uzbek].sort(()=>Math.random()-0.5);
      return { type:"word", id:w.id, category:w.category||"general",
               question:w.russian, answer:w.uzbek, choices, pron:w.pronunciation||"" };
    });
    if(type==="mixed"){
      const clozeList = await api(`/api/cloze?limit=${Math.floor(count/2)}`);
      const clozeQ    = (clozeList||[]).map(c=>({
        type:"cloze", id:c.id, category:c.category,
        sentence_ru:c.sentence_ru, sentence_uz:c.sentence_uz,
        answer:c.answer, choices:JSON.parse(c.options_json||"[]"),
      }));
      questions = [...questions.slice(0,Math.ceil(count/2)), ...clozeQ]
        .sort(()=>Math.random()-0.5).slice(0,count);
    }
  }

  if(!questions.length){ toast("Savollar topilmadi","warn"); return; }
  AdaptState.questions = questions;
  $("adaptiveSetup").style.display = "none";
  $("adaptiveResult").style.display = "none";
  $("adaptivePlay").style.display  = "block";
  showAdaptQuestion();
}

function showAdaptQuestion(){
  const q = AdaptState.questions[AdaptState.index];
  if(!q){ endAdaptiveTest(); return; }
  const total = AdaptState.questions.length;
  $("adaptProgFill").style.width  = `${Math.round(AdaptState.index/total*100)}%`;
  $("adaptProgLabel").textContent = `${AdaptState.index+1}/${total}`;
  $("adaptScoreLabel").textContent= `${AdaptState.score} ball`;
  $("adaptFeedback").style.display= "none";
  $("adaptQuestionType").textContent = q.type==="cloze" ? "✏️ Bo'shliq to'ldirish" : "📖 So'z testi";
  $("adaptQuestionType").className   = `adapt-type-badge ${q.type}`;

  if(q.type === "cloze"){
    $("adaptQuestion").textContent  = q.sentence_ru;
    const ctxEl = $("adaptClozeContext");
    ctxEl.style.display  = "block";
    ctxEl.textContent    = `🇺🇿 ${q.sentence_uz}`;
  } else {
    $("adaptQuestion").textContent  = q.question;
    $("adaptClozeContext").style.display = "none";
    if(q.pron) $("adaptQuestion").title = `🔊 ${q.pron}`;
  }

  $("adaptChoices").innerHTML = q.choices.map((c,i)=>`
    <button class="quiz-choice" onclick="answerAdapt(this,'${c.replace(/'/g,"\\'")}',${i})">
      ${c}
    </button>`).join("");
}

function answerAdapt(btn, chosen, idx){
  const q       = AdaptState.questions[AdaptState.index];
  const correct = chosen === q.answer;
  document.querySelectorAll(".quiz-choice").forEach(b=>b.disabled=true);
  btn.classList.add(correct?"correct":"wrong");
  if(!correct)
    document.querySelectorAll(".quiz-choice")
      .forEach(b=>{ if(b.textContent.trim()===q.answer) b.classList.add("correct"); });

  const pts = correct ? 10 : 0;
  AdaptState.score += pts;
  AdaptState.answers.push({...q, chosen, correct});

  // Backend ga statistika yuborish
  api("/api/adaptive/update",{method:"POST",
    body:JSON.stringify({category:q.category||"general", correct})});
  if(q.type==="word" && q.id)
    api(`/api/words/${q.id}/review`,{method:"POST",body:JSON.stringify({correct})});
  if(q.type==="cloze" && q.id)
    api(`/api/cloze/${q.id}/result`,{method:"POST",
      body:JSON.stringify({correct, category:q.category})});

  const fb = $("adaptFeedback");
  fb.className = `quiz-feedback ${correct?"correct":"wrong"}`;
  fb.style.display = "block";
  fb.innerHTML = correct
    ? `✅ To'g'ri! +10 ball${q.pron?` <em>🔊 ${q.pron}</em>`:""}`
    : `❌ Noto'g'ri! To'g'ri: <strong>${q.answer}</strong>`;

  setTimeout(()=>{ AdaptState.index++; showAdaptQuestion(); }, 1300);
}

async function endAdaptiveTest(){
  $("adaptivePlay").style.display   = "none";
  const total    = AdaptState.questions.length;
  const correct  = AdaptState.answers.filter(a=>a.correct).length;
  const pct      = Math.round(correct/total*100);
  const elapsed  = Math.round((Date.now()-AdaptState.start)/1000);
  const emoji    = pct>=90?"🏆":pct>=70?"🎉":pct>=50?"😊":"💪";

  AdaptState.xp = AdaptState.score;
  await api("/api/history",{method:"POST",body:JSON.stringify({
    lesson_type:"adaptive", duration_sec:elapsed,
    score:pct, xp_earned:AdaptState.xp,
    details:{correct, wrong:total-correct, total, type:AdaptState.type},
  })});
  await loadProfile();

  // Maslahat
  const weakCats = [...new Set(AdaptState.answers.filter(a=>!a.correct).map(a=>a.category))];
  const adviceEl = $("adaptResultAdvice");
  adviceEl.innerHTML = weakCats.length
    ? `<div class="adapt-advice-text">
        💡 <b>Maslahat:</b> ${weakCats.join(", ")} mavzularida ko'proq mashq qiling!
        <button class="btn btn-sm btn-ghost" onclick="navigate('vocabulary')">📖 Lug'atga o'tish</button>
       </div>`
    : "";

  $("adaptResultEmoji").textContent = emoji;
  $("adaptResultScore").textContent = `${AdaptState.score} ball — ${pct}%`;
  $("adaptResultDetails").innerHTML = `
    <div style="color:var(--text2);margin-bottom:12px">
      ✅ ${correct} to'g'ri · ❌ ${total-correct} noto'g'ri · ⏱ ${secToMin(elapsed)}
    </div>`;
  $("adaptiveResult").style.display = "block";
  toast(`🎉 ${AdaptState.xp} XP qo'shildi!`, "success");
}

// ══════════════════════════════════════════════════
// ROLEPLAY (Dialog Mashqi)
// ══════════════════════════════════════════════════
const RpState = { sessionId:null, scenario:null, isTyping:false };

const RP_HINTS = {
  shop:    ["Сколько стоит?","Мне нравится.","Это дорого.","Я возьму это."],
  doctor:  ["Болит голова.","Мне плохо.","Какие таблетки?","Спасибо, доктор."],
  cafe:    ["Дайте меню.","Я буду...","Это вкусно!","Счёт, пожалуйста."],
  airport: ["У меня есть билет.","Где выход?","Мой багаж.","Где туалет?"],
  hotel:   ["Есть свободные номера?","Сколько стоит?","Когда выезд?","Спасибо!"],
  bank:    ["Хочу открыть счёт.","Курс доллара?","Есть карта?","Переведите деньги."],
  friend:  ["Как дела?","Что нового?","Пойдём погуляем?","Увидимся!"],
  job:     ["Я ищу работу.","У меня опыт 3 года.","Какая зарплата?","Когда начать?"],
};

async function loadRoleplayPage(){
  const scenarios = await api("/api/roleplay/scenarios");
  const grid      = $("rpGrid");
  if(!grid||!scenarios) return;
  grid.innerHTML = (scenarios||[]).map(s=>`
    <div class="rp-card" onclick="startRoleplay('${s.id}')">
      <div class="rp-icon">${s.icon||"🎭"}</div>
      <div class="rp-info">
        <div class="rp-title">${s.title}</div>
        <div class="rp-roles">
          <span>Sen: ${s.user_role}</span>
          <span>AI: ${s.ai_role}</span>
        </div>
      </div>
      <button class="btn btn-primary btn-sm">▶ Boshlash</button>
    </div>`).join("");
}

async function startRoleplay(scenarioId){
  $("rpScenarios").style.display = "none";
  $("rpResult").style.display    = "none";
  $("rpChat").style.display      = "block";
  $("rpEndBtn").style.display    = "inline-flex";
  $("rpMessages").innerHTML      = "";
  RpState.scenario = scenarioId;

  const r = await api("/api/roleplay/start",{method:"POST",
    body:JSON.stringify({scenario:scenarioId})});
  if(!r?.ok){ toast("❌ Xatolik","error"); return; }

  RpState.sessionId = r.session_id;
  $("rpHeader").innerHTML = `
    <div class="rp-active-header">
      <span>${r.icon||"🎭"} ${r.title}</span>
      <div style="font-size:12px;color:var(--text2)">
        Sen: <b>${r.user_role}</b> · AI: <b>${r.ai_role}</b>
      </div>
    </div>`;

  appendRpMsg("assistant", r.response, r.offline||false);
  // Foydali iboralarni ko'rsatish
  const hints = RP_HINTS[scenarioId] || RP_HINTS.friend;
  $("rpHints").innerHTML = hints.map(h=>
    `<button class="rp-hint-chip" onclick="insertRpText('${h}')">${h}</button>`
  ).join("");
  if(r.offline) toast("📵 Offline rejim","info",1500);
}

function appendRpMsg(role, content, offline=false){
  const msgs = $("rpMessages");
  const div  = document.createElement("div");
  div.className = `chat-msg ${role}`;
  const avatar = role==="assistant"?"🤖":"👤";
  const offTag = offline?`<span class="msg-offline-tag">📵</span>`:"";
  const ttsText = content.split("\n")[0].replace(/[()]/g,"").trim();
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-bubble">${content.replace(/\n/g,"<br>").replace(/\[(.*?)\]/g,"<span class='err-right'>[$1]</span>")}${offTag}</div>
      <div class="msg-actions">
        <button class="tts-msg-btn" onclick="ttsSpeakEl(this)"
          data-text="${ttsText.replace(/"/g,'&quot;')}" title="Eshitish">🔊</button>
      </div>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  if(role==="assistant"&&Chat.ttsEnabled) ttsSpeak(ttsText, true);
}

async function sendRoleplay(){
  const inp = $("rpInput");
  const msg = inp?.value.trim();
  if(!msg||RpState.isTyping) return;
  inp.value = "";
  appendRpMsg("user", msg);
  RpState.isTyping = true;

  const div = document.createElement("div");
  div.className="chat-msg assistant typing-msg"; div.id="rpTyping";
  div.innerHTML=`<div class="msg-avatar">🤖</div><div class="msg-body"><div class="msg-bubble typing-dots"><span></span><span></span><span></span></div></div>`;
  $("rpMessages").appendChild(div); $("rpMessages").scrollTop=$("rpMessages").scrollHeight;

  const r = await api("/api/roleplay/chat",{method:"POST",
    body:JSON.stringify({session_id:RpState.sessionId, message:msg})});
  document.getElementById("rpTyping")?.remove();
  RpState.isTyping = false;

  if(r?.ok) appendRpMsg("assistant", r.response, r.offline||false);
  else      appendRpMsg("assistant","❌ Xatolik yuz berdi");
}

function insertRpText(txt){
  const inp=$("rpInput"); if(inp){inp.value=txt;inp.focus();}
}

function toggleRpMic(){
  // Mavjud toggleMic funksiyasini roleplay uchun moslashtirish
  const btn=$("rpMicBtn");
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){toast("❌ Mikrofon qo'llab-quvvatlanmaydi","warn");return;}
  if(Chat.micActive){Chat.recognition?.stop();return;}
  const rec=new SR(); rec.lang="ru-RU"; rec.continuous=false;
  Chat.recognition=rec; Chat.micActive=true;
  if(btn){btn.textContent="🔴";}
  rec.onresult=e=>{
    const t=Array.from(e.results).map(r=>r[0].transcript).join("");
    const inp=$("rpInput"); if(inp) inp.value=t;
  };
  rec.onend=()=>{Chat.micActive=false;if(btn)btn.textContent="🎤";};
  rec.onerror=()=>{Chat.micActive=false;if(btn)btn.textContent="🎤";};
  rec.start();
}

async function endRoleplay(){
  if(!RpState.sessionId) return;
  const r = await api("/api/roleplay/end",{method:"POST",
    body:JSON.stringify({session_id:RpState.sessionId})});
  $("rpChat").style.display    = "none";
  $("rpEndBtn").style.display  = "none";
  $("rpResult").style.display  = "block";
  const score   = r?.score||0;
  const turns   = r?.turns||0;
  const emoji   = score>=70?"🏆":score>=40?"🎉":"💪";
  $("rpScore").textContent  = `${score} ball · ${turns} ta gap`;
  $("rpFeedback").innerHTML = `
    <div class="rp-feedback">
      ${emoji} ${score>=70?"Ajoyib suhbat!":score>=40?"Yaxshi mashq!":"Davom eting, har safar yaxshilanasiz!"}
      <br><span class="muted">Streak yangilandi 🔥 +${Math.round(score/2)} XP</span>
    </div>`;
  await loadProfile();
  if(r?.ok) toast(`🎭 ${r.score} ball! +${Math.round(r.score/2)} XP`,"success");
}

function showRpScenarios(){
  $("rpResult").style.display    = "none";
  $("rpScenarios").style.display = "block";
  RpState.sessionId = null;
}

// ══════════════════════════════════════════════════
// AI O'QITISH PANELI — to'liq logika
// ══════════════════════════════════════════════════

// ── Panel holat ───────────────────────────────────
const Panel = {
  open:    false,
  tab:     "qwords",
  qwords:  [],
  names:   [],
  qa:      [],
  synonyms:[],
  banned:  [],
};

// ── Panel ochish / yopish ─────────────────────────
function openAIPanel(){
  Panel.open = true;
  const col    = $("aiPanelCol");
  const layout = $("chatLayout");
  const btn    = $("panelOpenBtn");
  if(col)    col.style.display    = "flex";
  if(layout) layout.classList.add("panel-open");
  if(btn){
    btn.textContent = "🧠 Yopish";
    btn.onclick     = closeAIPanel;
  }
  loadPanelStats();
  switchApTab(Panel.tab);
}

function closeAIPanel(){
  Panel.open = false;
  const col    = $("aiPanelCol");
  const layout = $("chatLayout");
  const btn    = $("panelOpenBtn");
  if(col)    col.style.display    = "none";
  if(layout) layout.classList.remove("panel-open");
  if(btn){
    btn.textContent = "🧠 O'qitish";
    btn.onclick     = openAIPanel;
  }
}

// ── Tab almashtirish ──────────────────────────────
function switchApTab(tab, btn){
  Panel.tab = tab;
  document.querySelectorAll(".ap-tab")
    .forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".ap-section")
    .forEach(s => s.classList.toggle("active", s.id === `apTab-${tab}`));
  // Tab ma'lumotlarini yuklash
  const loaders = {
    qwords:   loadQWords,
    names:    loadNames,
    qa:       loadQA,
    synonyms: loadSynonyms,
    banned:   loadBanned,
    default:  loadDefault,
    test:     ()=>{},
  };
  if(loaders[tab]) loaders[tab]();
}

// ── Panel statistika ──────────────────────────────
async function loadPanelStats(){
  const s = await api("/api/panel/stats");
  if(!s || s.error) return;
  $("apStat1").textContent = `❓ ${s.q_words}`;
  $("apStat2").textContent = `🏷 ${s.names}`;
  $("apStat3").textContent = `🔗 ${s.qa_pairs}`;
  $("apStat4").textContent = `♻️ ${s.synonyms}`;
  $("apStat5").textContent = `🚫 ${s.banned}`;
}

// ══════════════════════════════════════════════════
// 1. SAVOL SO'ZLAR
// ══════════════════════════════════════════════════
async function loadQWords(){
  const list = await api("/api/panel/qwords");
  Panel.qwords = list || [];
  const el = $("qwList"); if(!el) return;
  if(!list?.length){
    el.innerHTML = `<div class="ap-empty">Hali savol so'z yo'q. Yuqoridan qo'shing.</div>`;
    return;
  }
  el.innerHTML = list.map(w => `
    <div class="ap-item" id="qwi-${w.id}">
      <span class="ap-item-text ${w.enabled ? '' : 'disabled'}">${w.word}</span>
      <span class="ap-item-badge">${w.lang === 'ru' ? '🇷🇺' : '🇺🇿'}</span>
      <div class="ap-item-actions">
        <button class="ap-btn ap-btn-toggle ${w.enabled ? 'on' : 'off'}"
                onclick="toggleQWord(${w.id}, this)"
                title="${w.enabled ? 'O\'chirish' : 'Yoqish'}">
          ${w.enabled ? '✅' : '⭕'}
        </button>
        <button class="ap-btn ap-btn-del" onclick="deleteQWord(${w.id})" title="O'chirish">🗑</button>
      </div>
    </div>`).join("");
  // datalist yangilash
  _updateQWDatalist();
}

async function addQWord(){
  const inp  = $("qwInput");
  const lang = $("qwLang")?.value || "uz";
  const word = inp?.value.trim().toLowerCase();
  if(!word){ toast("So'z kiriting","warn"); return; }
  const r = await api("/api/panel/qwords", {
    method: "POST",
    body: JSON.stringify({ word, lang }),
  });
  if(r?.ok){
    toast(`✅ "${word}" qo'shildi`, "success", 1500);
    if(inp) inp.value = "";
    loadQWords(); loadPanelStats();
  } else {
    toast(r?.error || "❌ Xatolik", "error");
  }
}

async function deleteQWord(id){
  await api(`/api/panel/qwords/${id}`, { method: "DELETE" });
  $(`qwi-${id}`)?.remove();
  loadPanelStats();
  toast("🗑 O'chirildi", "info", 1200);
}

async function toggleQWord(id, btn){
  const r = await api(`/api/panel/qwords/${id}/toggle`, { method: "POST" });
  if(!r?.ok) return;
  const item = $(`qwi-${id}`);
  if(!item) return;
  const txt  = item.querySelector(".ap-item-text");
  if(r.enabled){
    txt?.classList.remove("disabled");
    btn.className  = "ap-btn ap-btn-toggle on";
    btn.textContent = "✅";
    btn.title       = "O'chirish";
  } else {
    txt?.classList.add("disabled");
    btn.className  = "ap-btn ap-btn-toggle off";
    btn.textContent = "⭕";
    btn.title       = "Yoqish";
  }
}

function _updateQWDatalist(){
  const dl = $("qwDatalist"); if(!dl) return;
  dl.innerHTML = Panel.qwords.map(w => `<option value="${w.word}">`).join("");
}

// ══════════════════════════════════════════════════
// 2. NOMLAR
// ══════════════════════════════════════════════════
async function loadNames(){
  const list = await api("/api/panel/names");
  Panel.names = list || [];
  const el = $("nmList"); if(!el) return;
  if(!list?.length){
    el.innerHTML = `<div class="ap-empty">Hali nom yo'q. Yuqoridan qo'shing.</div>`;
    _updateNMDatalist();
    return;
  }
  el.innerHTML = list.map(n => `
    <div class="ap-item" id="nmi-${n.id}">
      <span class="ap-item-text">${n.name}</span>
      ${n.q_words ? `<span class="ap-item-badge">${n.q_words}</span>` : ""}
      <div class="ap-item-actions">
        <button class="ap-btn ap-btn-del" onclick="deleteName(${n.id})" title="O'chirish">🗑</button>
      </div>
    </div>`).join("");
  _updateNMDatalist();
}

async function addName(){
  const inp  = $("nmInput");
  const name = inp?.value.trim().toLowerCase();
  if(!name){ toast("Nom kiriting","warn"); return; }
  const r = await api("/api/panel/names", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  if(r?.ok){
    toast(`✅ "${name}" qo'shildi`, "success", 1500);
    if(inp) inp.value = "";
    loadNames(); loadPanelStats();
  } else {
    toast(r?.error || "❌ Xatolik", "error");
  }
}

async function deleteName(id){
  if(!confirm("Bu nomni va unga bog'liq barcha ma'lumotlarni o'chirasizmi?")) return;
  await api(`/api/panel/names/${id}`, { method: "DELETE" });
  $(`nmi-${id}`)?.remove();
  loadPanelStats();
  toast("🗑 O'chirildi", "info", 1200);
}

function _updateNMDatalist(){
  const dl = $("nmDatalist"); if(!dl) return;
  dl.innerHTML = Panel.names.map(n => `<option value="${n.name}">`).join("");
}

// ══════════════════════════════════════════════════
// 3. SAVOL + NOM JUFTLIGI (Ma'lumot)
// ══════════════════════════════════════════════════
async function loadQA(){
  const list = await api("/api/panel/qa");
  Panel.qa   = list || [];
  const el   = $("qaList"); if(!el) return;
  if(!list?.length){
    el.innerHTML = `<div class="ap-empty">Hali ma'lumot juftligi yo'q.</div>`;
    return;
  }
  el.innerHTML = list.map(p => `
    <div class="ap-item ap-item-qa" id="qai-${p.id}">
      <div class="ap-qa-header">
        <span class="ap-qa-key">❓ ${p.q_word} + 🏷 ${p.name}</span>
        <span class="ap-qa-use" title="Ishlatilgan soni">${p.use_count}x</span>
        <div class="ap-item-actions">
          <button class="ap-btn ap-btn-edit" onclick="editQA(${p.id})">✏️</button>
          <button class="ap-btn ap-btn-del"  onclick="deleteQA(${p.id})">🗑</button>
        </div>
      </div>
      <div class="ap-qa-answer">${p.answer}</div>
    </div>`).join("");

  // Formga datalist yangilash
  _updateQWDatalist();
  _updateNMDatalist();
}

// QA real-vaqt saqlash — debounce 600ms
let _qaSaveTimer = null;
function _qaAutoSave(){
  clearTimeout(_qaSaveTimer);
  const qw  = ($("qaQWord")?.value  || "").trim().toLowerCase();
  const nm  = ($("qaName")?.value   || "").trim().toLowerCase();
  const ans = ($("qaAnswer")?.value || "").trim();
  if(!qw || !nm || !ans) return;                 // to'liq emas — kutish
  _qaShowSaveStatus("⏳ Saqlanmoqda...", "pending");
  _qaSaveTimer = setTimeout(()=>_doSaveQA(qw,nm,ans), 600);
}

async function _doSaveQA(qw, nm, ans){
  const r = await api("/api/panel/qa",{
    method:"POST",
    body:JSON.stringify({q_word:qw, name:nm, answer:ans}),
  });
  if(r?.ok){
    _qaShowSaveStatus(`✅ Saqlandi (${qw} + ${nm})`, "ok");
    // Ro'yxatni yangilash (formni TOZALAMAYDI — foydalanuvchi davom ettirsin)
    loadQA(); loadNames(); loadQWords(); loadPanelStats();
  } else {
    _qaShowSaveStatus("❌ "+( r?.error||"Xatolik"), "err");
  }
}

function _qaShowSaveStatus(msg, type){
  let el = $("qaSaveStatus");
  if(!el){
    el = document.createElement("div");
    el.id = "qaSaveStatus";
    el.style.cssText="font-size:11px;font-weight:700;padding:4px 8px;border-radius:5px;margin-top:4px;transition:all .2s";
    const form = $("apTab-qa")?.querySelector(".ap-form");
    if(form) form.appendChild(el);
  }
  el.textContent = msg;
  const colors = { ok:"var(--green)", err:"var(--red)", pending:"var(--yellow)" };
  el.style.color = colors[type]||"var(--text2)";
}

async function saveQA(){
  const qw  = ($("qaQWord")?.value  || "").trim().toLowerCase();
  const nm  = ($("qaName")?.value   || "").trim().toLowerCase();
  const ans = ($("qaAnswer")?.value || "").trim();
  if(!qw || !nm || !ans){
    toast("Barcha maydonlarni to'ldiring","warn"); return;
  }
  clearTimeout(_qaSaveTimer);
  _qaShowSaveStatus("⏳...", "pending");
  await _doSaveQA(qw, nm, ans);
}

function editQA(id){
  const p = Panel.qa.find(x => x.id === id);
  if(!p) return;
  $("qaQWord").value  = p.q_word;
  $("qaName").value   = p.name;
  $("qaAnswer").value = p.answer;
  $("qaQWord").focus();
  toast("✏️ Tahrirlash uchun ma'lumotlar forma ga yuklandi","info",2000);
}

async function deleteQA(id){
  await api(`/api/panel/qa/${id}`, { method: "DELETE" });
  $(`qai-${id}`)?.remove();
  loadPanelStats();
  toast("🗑 O'chirildi","info",1200);
}

// ══════════════════════════════════════════════════
// 4. SINONIMLAR
// ══════════════════════════════════════════════════
async function loadSynonyms(){
  const list = await api("/api/panel/synonyms");
  Panel.synonyms = list || [];
  const el   = $("synList"); if(!el) return;
  if(!list?.length){
    el.innerHTML = `<div class="ap-empty">Hali sinonim guruhi yo'q.</div>`;
    return;
  }
  el.innerHTML = list.map(g => `
    <div class="ap-item ap-item-syn" id="syni-${g.id}">
      <div class="ap-qa-header">
        <span class="ap-qa-key">♻️ ${g.group_name}</span>
        <div class="ap-item-actions">
          <button class="ap-btn ap-btn-edit" onclick="editSynonym(${g.id})">✏️</button>
          <button class="ap-btn ap-btn-del"  onclick="deleteSynonym(${g.id})">🗑</button>
        </div>
      </div>
      <div style="font-size:12px;color:var(--text3);margin:3px 0">
        ${(g.synonyms_list||[]).map(s=>`<code>${s}</code>`).join(", ")}
      </div>
      <div class="ap-qa-answer">${g.answer}</div>
    </div>`).join("");
}

async function saveSynonym(){
  const name  = ($("synName")?.value   || "").trim();
  const words = ($("synWords")?.value  || "").trim();
  const ans   = ($("synAnswer")?.value || "").trim();
  const eid   = $("synEditId")?.value  || "";
  if(!words || !ans){ toast("Sinonimlar va javob majburiy","warn"); return; }
  const synArr = words.split(",").map(s=>s.trim()).filter(Boolean);
  const r = await api("/api/panel/synonyms", {
    method: "POST",
    body: JSON.stringify({
      id: eid ? parseInt(eid) : undefined,
      group_name: name || words.split(",")[0].trim(),
      synonyms:   synArr,
      answer:     ans,
    }),
  });
  if(r?.ok){
    toast("✅ Saqlandi","success",1500);
    ["synName","synWords","synAnswer","synEditId"].forEach(id=>{ const el=$(id); if(el) el.value=""; });
    loadSynonyms(); loadPanelStats();
  } else toast(r?.error || "❌ Xatolik","error");
}

function editSynonym(id){
  const g = Panel.synonyms.find(x=>x.id===id); if(!g) return;
  $("synEditId").value  = g.id;
  $("synName").value    = g.group_name;
  $("synWords").value   = (g.synonyms_list||[]).join(", ");
  $("synAnswer").value  = g.answer;
  $("synName").focus();
  toast("✏️ Tahrirlash uchun yuklandi","info",1800);
}

async function deleteSynonym(id){
  await api(`/api/panel/synonyms/${id}`,{method:"DELETE"});
  $(`syni-${id}`)?.remove();
  loadPanelStats(); toast("🗑 O'chirildi","info",1200);
}

// ══════════════════════════════════════════════════
// 5. TAQIQLANGAN SO'ZLAR
// ══════════════════════════════════════════════════
async function loadBanned(){
  const list = await api("/api/panel/banned");
  Panel.banned = list || [];
  const el   = $("banList"); if(!el) return;
  if(!list?.length){
    el.innerHTML = `<div class="ap-empty">Hali taqiqlangan so'z yo'q.</div>`;
    return;
  }
  el.innerHTML = list.map(b => `
    <div class="ap-item" id="bani-${b.id}">
      <div class="ap-qa-header">
        <span class="ap-qa-key">🚫 ${b.word}</span>
        <span class="ap-item-badge ${b.enabled ? 'on' : 'off'}">${b.enabled ? 'Faol':'Nofaol'}</span>
        <div class="ap-item-actions">
          <button class="ap-btn ap-btn-edit" onclick="editBanned(${b.id})">✏️</button>
          <button class="ap-btn ap-btn-del"  onclick="deleteBanned(${b.id})">🗑</button>
        </div>
      </div>
      <div class="ap-qa-answer">${b.answer}</div>
    </div>`).join("");
}

async function saveBanned(){
  const word = ($("banWord")?.value   || "").trim().toLowerCase();
  const ans  = ($("banAnswer")?.value || "").trim();
  const eid  = $("banEditId")?.value  || "";
  if(!word || !ans){ toast("So'z va javob majburiy","warn"); return; }
  const r = await api("/api/panel/banned",{
    method:"POST",
    body:JSON.stringify({ id:eid?parseInt(eid):undefined, word, answer:ans }),
  });
  if(r?.ok){
    toast("✅ Saqlandi","success",1500);
    ["banWord","banAnswer","banEditId"].forEach(id=>{ const el=$(id); if(el) el.value=""; });
    loadBanned(); loadPanelStats();
  } else toast(r?.error||"❌ Xatolik","error");
}

function editBanned(id){
  const b=Panel.banned.find(x=>x.id===id); if(!b) return;
  $("banEditId").value  = b.id;
  $("banWord").value    = b.word;
  $("banAnswer").value  = b.answer;
  $("banWord").focus();
  toast("✏️ Tahrirlash uchun yuklandi","info",1800);
}

async function deleteBanned(id){
  await api(`/api/panel/banned/${id}`,{method:"DELETE"});
  $(`bani-${id}`)?.remove();
  loadPanelStats(); toast("🗑 O'chirildi","info",1200);
}

// ══════════════════════════════════════════════════
// 6. STANDART JAVOB
// ══════════════════════════════════════════════════
async function loadDefault(){
  const r = await api("/api/panel/default");
  const el = $("defaultText"); if(!el) return;
  el.value = r?.text || "";
}

async function saveDefault(){
  const text = ($("defaultText")?.value || "").trim();
  if(!text){ toast("Matn bo'sh bo'lmasin","warn"); return; }
  const r = await api("/api/panel/default",{
    method:"POST", body:JSON.stringify({text}),
  });
  if(r?.ok) toast("✅ Standart javob saqlandi","success");
  else      toast("❌ Xatolik","error");
}

// ══════════════════════════════════════════════════
// 7. REAL-VAQT TEST
// ══════════════════════════════════════════════════
const _testHistory = [];

async function runPanelTest(){
  const inp = $("testInput");
  const msg = inp?.value.trim();
  if(!msg){ toast("Xabar kiriting","warn"); return; }

  const resEl  = $("testResult");
  const srcEl  = $("testSource");
  const ansEl  = $("testAnswer");
  resEl.style.display = "block";
  srcEl.textContent   = "⏳ Tekshirilmoqda...";
  ansEl.textContent   = "";

  const r = await api("/api/panel/test",{
    method:"POST", body:JSON.stringify({message:msg}),
  });

  const sourceMap = {
    banned:      "🚫 Taqiqlangan so'z",
    math:        "🧮 Matematika",
    synonym:     "♻️ Sinonim guruhi",
    qa_pair:     "🔗 Savol+Nom juftligi",
    qa_name_only:"🏷 Faqat nom",
    default:     "💬 Standart javob",
    panel:       "🧠 Panel",
  };

  if(r?.ok){
    const label   = sourceMap[r.source] || r.source;
    const found   = r.found;
    srcEl.textContent   = `${found ? "✅" : "⚪"} Manba: ${label}`;
    srcEl.className     = `atr-source ${found ? "found":"notfound"}`;
    ansEl.textContent   = r.answer;
    ansEl.className     = `atr-answer ${found ? "found":"notfound"}`;

    // Tarixga qo'shish
    _testHistory.unshift({ msg, answer:r.answer, source:label, found });
    if(_testHistory.length > 8) _testHistory.pop();
    _renderTestHistory();
  } else {
    srcEl.textContent = "❌ Server xatosi";
    ansEl.textContent = r?.error || "";
  }
}

function _renderTestHistory(){
  const el = $("testHistory"); if(!el) return;
  if(!_testHistory.length){
    el.innerHTML = ""; return;
  }
  el.innerHTML = `
    <div class="ath-title">📋 Test tarixi</div>
    ${_testHistory.map(t=>`
      <div class="ath-item ${t.found?'found':'notfound'}">
        <div class="ath-q">${t.msg}</div>
        <div class="ath-s">${t.source}</div>
        <div class="ath-a">${t.answer.slice(0,80)}${t.answer.length>80?"...":""}</div>
      </div>`).join("")}`;
}

// ── navigate orqali panel yuklanishi ──────────────
// loadChatHistory ga qo'shimcha
const _origLoadChat = loadChatHistory;
async function loadChatHistory(){
  await _origLoadChat();
  // Agar panel ochiq bo'lsa, statsni yangilash
  if(Panel.open) loadPanelStats();
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
  await updateStreakBadge();
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


// ══════════════════════════════════════════════════
// GRAMMAR LESSON MODE (bosqichma-bosqich o'qitish)
// ══════════════════════════════════════════════════
async function startGrammarLesson(){
  const rules = await api("/api/grammar");
  if(!rules||!rules.length){ toast("Grammatika qoidalari topilmadi","warn"); return; }
  State.gmRules = rules; State.gmIndex = 0; State.gmXP = 0;
  $("grammarList").style.display="none";
  $("grammarStepsPanel").style.display="none";
  document.querySelector(".grammar-tabs").style.display="none";
  $("grammarLessonMode").style.display="block";
  gmShowRule(0);
}

async function startGrammarLessonFrom(ruleId){
  const rules = await api("/api/grammar");
  if(!rules) return;
  State.gmRules = rules;
  const idx = rules.findIndex(r=>r.id===ruleId);
  State.gmIndex = idx>=0?idx:0; State.gmXP = 0;
  $("grammarList").style.display="none";
  $("grammarStepsPanel").style.display="none";
  document.querySelector(".grammar-tabs").style.display="none";
  $("grammarLessonMode").style.display="block";
  gmShowRule(State.gmIndex);
}

function exitGrammarLesson(){
  $("grammarList").style.display="";
  $("grammarStepsPanel").style.display="";
  document.querySelector(".grammar-tabs").style.display="";
  $("grammarLessonMode").style.display="none";
  loadGrammar();
}

function gmShowRule(idx){
  const rules = State.gmRules;
  if(idx>=rules.length){ gmFinishAll(); return; }
  State.gmIndex = idx;
  const r = rules[idx];
  State.currentGrammarItem = r;
  const pct = Math.round(idx/rules.length*100);
  $("gmProgFill").style.width = pct+"%";
  $("gmProgLabel").textContent = `${idx+1} / ${rules.length}`;
  $("gmXPLabel").textContent = `+${State.gmXP} XP`;
  $("gmTitle").textContent = r.title;
  $("gmContent").innerHTML = (r.content||"").replace(/\n/g,"<br>");
  let ex=[]; try{ ex=JSON.parse(r.examples_json||"[]"); }catch(e){}
  $("gmTitleEx").textContent = r.title;
  $("gmExamplesList").innerHTML = ex.map(e=>`
    <div class="gm-example-item">
      <div class="gm-ex-ru">🇷🇺 ${e.ru}</div>
      ${e.uz?`<div class="gm-ex-uz">🇺🇿 ${e.uz}</div>`:""}
    </div>`).join("") || `<p class="muted">Misollar yo'q</p>`;
  $("gmTitleEx2").textContent = r.title;
  State.gmCurrentExIndex = 0; State.gmCurrentExAnswers = [];
  let exs=[]; try{ exs=JSON.parse(r.exercises_json||"[]"); }catch(e){}
  gmRenderExercise(exs);
  gmNextStep("explain");
}

function gmNextStep(step){
  ["explain","examples","exercise"].forEach(s=>{
    const el=$(`gmStep${s.charAt(0).toUpperCase()+s.slice(1)}`);
    if(el) el.style.display = s===step?"block":"none";
  });
  if(step==="exercise"){
    const r = State.gmRules[State.gmIndex];
    let exs=[]; try{ exs=JSON.parse(r.exercises_json||"[]"); }catch(e){}
    if(!exs.length) gmCompleteRule(true);
  }
}

function gmRenderExercise(exs){
  const area=$("gmExerciseArea");
  $("gmExResult").style.display="none";
  if(!exs||!exs.length){
    area.innerHTML=`<div class="empty-state"><p>Bu qoida uchun mashq yo'q</p></div>`;
    $("gmExButtons").innerHTML=`<button class="btn btn-primary btn-lg" onclick="gmCompleteRule(true)">Keyingi qoida →</button>`;
    return;
  }
  area.innerHTML = exs.map((q,i)=>`
    <div class="gm-q-item" id="gmQ-${i}">
      <div class="gm-q-text">${i+1}. ${q.q}</div>
      ${q.options?`<div class="gm-choices">${q.options.map(o=>`
        <button class="gm-choice" data-qi="${i}" data-val="${o}"
          onclick="gmSelectChoice(this,${i},'${o.replace(/'/g,"\\'")}')">${o}</button>`).join("")}</div>`
      :`<input class="form-input gm-text-input" id="gmInp-${i}" placeholder="Javobingizni yozing..."
         onkeydown="if(event.key==='Enter')gmCheckExercise()">`}
    </div>`).join("");
  $("gmExButtons").innerHTML=`<button class="btn btn-primary btn-lg" id="gmCheckBtn" onclick="gmCheckExercise()">✅ Tekshirish</button>`;
  State.gmCurrentExAnswers = new Array(exs.length).fill(null);
}

function gmSelectChoice(btn, qi, val){
  document.querySelectorAll(`.gm-choice[data-qi="${qi}"]`).forEach(b=>b.classList.remove("selected"));
  btn.classList.add("selected");
  State.gmCurrentExAnswers[qi] = val;
}

function gmCheckExercise(){
  const r = State.gmRules[State.gmIndex];
  let exs=[]; try{ exs=JSON.parse(r.exercises_json||"[]"); }catch(e){}
  if(!exs.length){ gmCompleteRule(true); return; }
  let correct=0;
  exs.forEach((q,i)=>{
    const given = q.options ? State.gmCurrentExAnswers[i] : ($(`gmInp-${i}`)?.value||"").trim();
    const ok = (given||"").toLowerCase()===(q.a||"").toLowerCase();
    if(ok) correct++;
    if(q.options){
      document.querySelectorAll(`.gm-choice[data-qi="${i}"]`).forEach(b=>{
        b.disabled=true;
        if(b.dataset.val===q.a) b.classList.add("correct");
        else if(b.classList.contains("selected")) b.classList.add("wrong");
      });
    } else {
      const inp=$(`gmInp-${i}`);
      if(inp){ inp.disabled=true; inp.style.borderColor=ok?"var(--green)":"var(--red)"; }
      const hint=document.createElement("div");
      hint.style.cssText="font-size:12px;margin-top:4px;";
      hint.style.color=ok?"var(--green)":"var(--red)";
      hint.textContent=ok?"✅ To'g'ri!":"❌ To'g'ri: "+q.a;
      $(`gmQ-${i}`)?.appendChild(hint);
    }
  });
  const pct=Math.round(correct/exs.length*100);
  const xpEarned=correct*15;
  State.gmXP+=xpEarned;
  $("gmXPLabel").textContent=`+${State.gmXP} XP`;
  $("gmExResult").style.display="block";
  $("gmExResult").innerHTML=`
    <div class="gm-result-bar ${pct>=60?"success":"retry"}">
      <span>${pct>=90?"🏆":pct>=60?"✅":"😅"}</span>
      <span>${correct}/${exs.length} to'g'ri (${pct}%)</span>
      <span style="color:var(--yellow)">+${xpEarned} XP</span>
    </div>`;
  $("gmExButtons").innerHTML=`
    ${pct<60?`<button class="btn btn-ghost btn-lg" onclick="retryGmExercise()">🔄 Qayta urinish</button>`:""}
    <button class="btn btn-primary btn-lg" onclick="gmCompleteRule(${pct>=60})">
      ${State.gmIndex<State.gmRules.length-1?"Keyingi qoida →":"🏁 Tugatish"}
    </button>`;
}

function retryGmExercise(){
  const r=State.gmRules[State.gmIndex];
  let exs=[]; try{ exs=JSON.parse(r.exercises_json||"[]"); }catch(e){}
  gmRenderExercise(exs); gmNextStep("exercise");
}

async function gmCompleteRule(passed){
  if(passed&&State.gmXP>0){
    await api("/api/history",{method:"POST",body:JSON.stringify({
      lesson_type:"grammar",duration_sec:120,score:passed?100:50,
      xp_earned:State.gmXP,details:{rule:State.currentGrammarItem?.title}
    })});
    await loadProfile();
  }
  const next=State.gmIndex+1;
  if(next>=State.gmRules.length){ gmFinishAll(); return; }
  State.gmXP=0; gmShowRule(next);
}

function gmFinishAll(){
  const gml=$("grammarLessonMode");
  if(gml) gml.innerHTML=`
    <div style="text-align:center;padding:48px 16px">
      <div style="font-size:64px;margin-bottom:16px">🎓</div>
      <h2 style="margin-bottom:8px">Barcha grammatika qoidalari tugadi!</h2>
      <p style="color:var(--text2);margin-bottom:24px">
        Siz ${State.gmRules.length} ta qoidani o'rgandingiz. Ajoyib natija!
      </p>
      <button class="btn btn-primary btn-lg" onclick="exitGrammarLesson()">📝 Grammatikaga qaytish</button>
      <button class="btn btn-ghost btn-lg" style="margin-left:8px" onclick="navigate('quiz')">❓ Test ishlash</button>
    </div>`;
}


// ══════════════════════════════════════════════════
// KATEGORIYA PANELI VA TEST (numbers va boshqalar)
// ══════════════════════════════════════════════════
const CAT_META = {
  numbers:    { icon:"🔢", label:"Raqamlar",      desc:"1 dan 100 000 gacha" },
  greeting:   { icon:"👋", label:"Salomlashish",  desc:"Kundalik muloqot" },
  colors:     { icon:"🎨", label:"Ranglar",        desc:"Asosiy ranglar" },
  family:     { icon:"👨‍👩‍👧", label:"Oila",          desc:"Oila a'zolari" },
  food:       { icon:"🍎", label:"Oziq-ovqat",     desc:"Taom va ichimlik" },
  verbs:      { icon:"⚡", label:"Fe'llar",        desc:"Harakat so'zlari" },
  adjectives: { icon:"🌟", label:"Sifatlar",       desc:"Tavsif so'zlari" },
  travel:     { icon:"✈️", label:"Sayohat",        desc:"Yo'l va manzil" },
  work:       { icon:"💼", label:"Ish",            desc:"Kasb va mehnat" },
  health:     { icon:"🏥", label:"Sog'liq",        desc:"Tana va davo" },
  nature:     { icon:"🌿", label:"Tabiat",         desc:"O'simlik va hayvon" },
  time:       { icon:"⏰", label:"Vaqt",           desc:"Soat va kun" },
  emotions:   { icon:"😊", label:"His-tuyg'ular",  desc:"Kayfiyat va his" },
  introduction: { icon:"🤝", label:"Tanishish",     desc:"O'zini tanishtirish" },
  navigation:   { icon:"🗺️", label:"Yo'l/Sayohat",   desc:"Yo'l so'rash, transport" },
  time_ext:     { icon:"⏰", label:"Vaqt",            desc:"Kunlar, oylar, fasllar" },
  places:       { icon:"🏛️", label:"Joylar",          desc:"Bino va manzillar" },
  math:         { icon:"🔢", label:"Matematika",      desc:"Amallar va shakllar" },
  family_ext:   { icon:"👨‍👩‍👧‍👦", label:"Oila",           desc:"Qarindoshlar" },
  clothing:     { icon:"👗", label:"Kiyim-kechak",    desc:"Kiyimlar va aksessuarlar" },
  animals:      { icon:"🐾", label:"Hayvonlar",       desc:"Uy va yovvoyi hayvonlar" },
  transport:    { icon:"🚗", label:"Transport",       desc:"Harakatlanish vositalari" },
  body:         { icon:"🫀", label:"Inson tanasi",    desc:"A'zolar va organlar" },
  school:       { icon:"🏫", label:"Maktab",          desc:"Ta'lim va dars buyumlari" },
  weather:      { icon:"🌤️", label:"Ob-havo",         desc:"Iqlim va fasllar" },
  house:        { icon:"🏠", label:"Uy-joy",          desc:"Xonalar va mebel" },
  sport:        { icon:"⚽", label:"Sport",           desc:"O'yinlar va mashqlar" },
};

async function loadCategoryPanel(){
  const cats = await api("/api/words/categories");
  if(!cats) return;
  const grid = $("catGrid");
  if(!grid) return;

  const catData = await Promise.all(cats.map(async cat=>{
    const words = await api(`/api/words?category=${cat}&limit=200`);
    const total = (words||[]).length;
    const learned = (words||[]).filter(w=>(w.times_correct||0)>0).length;
    return { cat, total, learned, pct: total>0?Math.round(learned/total*100):0 };
  }));

  grid.innerHTML = catData.map(d=>{
    const m = CAT_META[d.cat]||{icon:"📦",label:d.cat,desc:""};
    const pct = d.pct;
    const barColor = pct>=80?"var(--green)":pct>=40?"var(--yellow)":"var(--accent)";
    return `<div class="cat-card" onclick="selectCategory('${d.cat}')">
      <div class="cat-card-icon">${m.icon}</div>
      <div class="cat-card-info">
        <div class="cat-card-name">${m.label}</div>
        <div class="cat-card-desc">${m.desc}</div>
        <div class="cat-progress-wrap">
          <div class="cat-progress-bar" style="width:${pct}%;background:${barColor}"></div>
        </div>
        <div class="cat-progress-label">${d.learned}/${d.total} o'rganilgan (${pct}%)</div>
      </div>
      <div class="cat-card-actions">
        <button class="btn btn-sm btn-primary" onclick="event.stopPropagation();selectCategoryAndTest('${d.cat}')">🧪 Test</button>
      </div>
    </div>`;
  }).join("");
}

function selectCategory(cat){
  const sel = $("wordCatFilter");
  if(sel){ sel.value = cat; }
  State.wordOffset = 0;
  loadVocabulary();
  // Test banner ko'rsatish
  const m = CAT_META[cat]||{icon:"📦",label:cat};
  $("catTestInfo").innerHTML=`<span>${m.icon} <b>${m.label}</b> kategoriyasi tanlandi</span>`;
  $("catTestBanner").style.display="flex";
  State.catTest.cat = cat;
}

function selectCategoryAndTest(cat){
  State.catTest.cat = cat;
  startCatTest();
}

function onCatFilterChange(){
  const cat = $("wordCatFilter")?.value||"";
  if(cat){ selectCategory(cat); }
  else { hideCatBanner(); loadVocabulary(); }
}

function hideCatBanner(){
  $("catTestBanner").style.display="none";
}

async function startCatTest(){
  const cat = State.catTest.cat || $("wordCatFilter")?.value||"";
  if(!cat){ toast("Avval kategoriya tanlang","warn"); return; }

  const words = await api(`/api/words?category=${cat}&limit=200`);
  if(!words||words.length<4){ toast("Kamida 4 ta so'z kerak","warn"); return; }

  State.catTest = {
    cat, words: words.sort(()=>Math.random()-0.5).slice(0,Math.min(15,words.length)),
    index:0, score:0, answers:[], start:Date.now()
  };

  // Raqamlar kategoriyasi uchun maxsus test
  if(cat==="numbers") return startNumbersTest(words);

  $("wordGrid").style.display="none";
  $("wordCount").style.display="none";
  $("catTestBanner").style.display="none";
  $("catPanel").style.display="none";
  $("catTestArea").style.display="block";
  $("catTestResult").style.display="none";

  const m = CAT_META[cat]||{label:cat};
  $("catTestTitle").textContent=`${m.icon||"📦"} ${m.label} — Test`;
  showCatQuestion();
}

function showCatQuestion(){
  const {words,index} = State.catTest;
  if(index>=words.length){ endCatTest(); return; }

  const pct = Math.round(index/words.length*100);
  $("catProgFill").style.width=pct+"%";
  $("catProgLabel").textContent=`${index+1}/${words.length}`;

  const w = words[index];
  const wrong = words.filter(x=>x.id!==w.id).sort(()=>Math.random()-0.5).slice(0,3).map(x=>x.uzbek);
  const opts = [...wrong, w.uzbek].sort(()=>Math.random()-0.5);

  $("catTestContent").innerHTML=`
    <div class="cat-q-card">
      <div class="cat-q-word">${w.russian}</div>
      ${w.pronunciation?`<div class="cat-q-pron">🔊 ${w.pronunciation}</div>`:""}
      <div class="cat-q-label">O'zbekcha tarjimasi qaysi?</div>
      <div class="cat-choices">
        ${opts.map(o=>`<button class="quiz-choice cat-choice" onclick="answerCatQuestion(this,'${o.replace(/'/g,"\\'")}','${w.uzbek.replace(/'/g,"\\'")}',${w.id})">${o}</button>`).join("")}
      </div>
    </div>`;
}

function answerCatQuestion(btn, chosen, correct, wid){
  document.querySelectorAll(".cat-choice").forEach(b=>b.disabled=true);
  const ok = chosen===correct;
  btn.classList.add(ok?"correct":"wrong");
  if(!ok) document.querySelectorAll(".cat-choice").forEach(b=>{ if(b.textContent===correct) b.classList.add("correct"); });
  if(ok){ State.catTest.score+=10; api(`/api/words/${wid}/review`,{method:"POST",body:JSON.stringify({correct:true})}); }
  State.catTest.answers.push({chosen,correct,ok});
  setTimeout(()=>{ State.catTest.index++; showCatQuestion(); }, 1200);
}

async function endCatTest(){
  const {score,answers,start,words,cat}=State.catTest;
  const correct=answers.filter(a=>a.ok).length;
  const total=answers.length;
  const pct=total>0?Math.round(correct/total*100):0;
  const elapsed=Math.round((Date.now()-start)/1000);
  const emoji=pct>=90?"🏆":pct>=70?"🎉":pct>=50?"😊":"😅";

  await api("/api/history",{method:"POST",body:JSON.stringify({
    lesson_type:"quiz",duration_sec:elapsed,score:pct,xp_earned:score,
    details:{category:cat,correct,total}
  })});
  await loadProfile();

  $("catTestContent").innerHTML="";
  $("catResultEmoji").textContent=emoji;
  $("catResultScore").textContent=`${score} ball — ${pct}%`;
  const m=CAT_META[cat]||{label:cat};
  $("catResultDetails").innerHTML=`
    <p style="color:var(--text2)">${m.icon||"📦"} ${m.label} kategoriyasi</p>
    <p>✅ ${correct} to'g'ri · ❌ ${total-correct} noto'g'ri · ⏱ ${secToMin(elapsed)}</p>
    ${pct<70?`<p style="color:var(--yellow);margin-top:8px">💡 Maslahat: Kartochkalar bilan ko'proq mashq qiling!</p>`:""}`;
  $("catTestResult").style.display="block";
  toast(`🎉 ${score} XP qo'shildi!`,"success");
}

function closeCatTest(){
  $("catTestArea").style.display="none";
  $("wordGrid").style.display="";
  $("wordCount").style.display="";
  $("catPanel").style.display="";
  loadVocabulary();
}


// ══════════════════════════════════════════════════
// RAQAMLAR MAXSUS TEST (1 - 100 000)
// ══════════════════════════════════════════════════
function startNumbersTest(allWords){
  const nums = allWords.sort(()=>Math.random()-0.5).slice(0,15);
  State.catTest = { ...State.catTest, words:nums, index:0, score:0, answers:[], start:Date.now() };

  $("wordGrid").style.display="none";
  $("wordCount").style.display="none";
  $("catTestBanner").style.display="none";
  $("catPanel").style.display="none";
  $("catTestArea").style.display="block";
  $("catTestResult").style.display="none";
  $("catTestTitle").textContent="🔢 Raqamlar testi";

  showNumbersQuestion();
}

function showNumbersQuestion(){
  const {words,index}=State.catTest;
  if(index>=words.length){ endCatTest(); return; }

  const pct=Math.round(index/words.length*100);
  $("catProgFill").style.width=pct+"%";
  $("catProgLabel").textContent=`${index+1}/${words.length}`;

  const w=words[index];
  // Random: 50% ru→uz, 50% uz→ru
  const mode = Math.random()<0.5?"ru_uz":"uz_ru";
  const question = mode==="ru_uz" ? w.russian : w.uzbek;
  const correctAns = mode==="ru_uz" ? w.uzbek : w.russian;
  const wrong = words.filter(x=>x.id!==w.id).sort(()=>Math.random()-0.5).slice(0,3)
    .map(x=>mode==="ru_uz"?x.uzbek:x.russian);
  const opts=[...wrong,correctAns].sort(()=>Math.random()-0.5);

  $("catTestContent").innerHTML=`
    <div class="cat-q-card">
      <div class="cat-q-label" style="font-size:12px;margin-bottom:4px">
        ${mode==="ru_uz"?"🇷🇺 Ruscha → 🇺🇿 O'zbekcha":"🇺🇿 O'zbekcha → 🇷🇺 Ruscha"}
      </div>
      <div class="cat-q-word num-word">${question}</div>
      ${w.pronunciation&&mode==="ru_uz"?`<div class="cat-q-pron">🔊 ${w.pronunciation}</div>`:""}
      <div class="cat-q-label">To'g'ri javobni tanlang:</div>
      <div class="cat-choices">
        ${opts.map(o=>`<button class="quiz-choice cat-choice"
          onclick="answerCatQuestion(this,'${o.replace(/'/g,"\\'")}','${correctAns.replace(/'/g,"\\'")}',${w.id})">${o}</button>`).join("")}
      </div>
    </div>`;
}

// loadVocabulary ga kategoriya panelini qo'shish uchun patch
const _origLoadVocabulary = loadVocabulary;
async function loadVocabulary(){
  await _origLoadVocabulary();
  await loadCategoryPanel();
}
