// Keep the existing FastAPI chat endpoint. Override this on a deployment if needed.
  const API_BASE_URL = window.VETGPT_API_BASE_URL || 'https://vetgpt-backend.onrender.com';
  const chat = document.getElementById('chat');
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('sendBtn');
  const emptyNote = document.getElementById('emptyNote');
  const toast = document.getElementById('toast');
  const chatForm = document.getElementById('chatForm');
  let history = [];
  let toastTimeout;

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => toast.classList.remove('show'), 2600);
  }

  function addMessage(role, text) {
    if (emptyNote) emptyNote.remove();
    const el = document.createElement('div');
    el.className = 'msg ' + (role === 'user' ? 'user' : 'bot');
    el.textContent = text;
    chat.appendChild(el);
    chat.scrollTop = chat.scrollHeight;
    return el;
  }

  async function handleSend(message) {
    const text = (typeof message === 'string' ? message : input.value).trim();
    if (!text || sendBtn.disabled) return;
    input.value = '';
    sendBtn.disabled = true;
    addMessage('user', text);
    const typingEl = addMessage('bot', 'Thinking through that for you…');
    typingEl.classList.add('typing');

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history })
      });
      if (!response.ok) throw new Error(`The assistant returned status ${response.status}.`);
      const data = await response.json();
      if (typeof data.answer !== 'string' || !data.answer.trim()) throw new Error('The assistant returned an empty response.');
      typingEl.classList.remove('typing');
      typingEl.textContent = data.answer;
      history.push({ role: 'user', content: text }, { role: 'assistant', content: data.answer });
    } catch (error) {
      typingEl.classList.remove('typing');
      typingEl.textContent = 'I couldn’t connect just now. Please try again in a moment.';
      console.error('PetNova chat request failed:', error);
    } finally {
      sendBtn.disabled = false;
      input.focus();
      chat.scrollTop = chat.scrollHeight;
    }
  }

  function newConversation() {
    history = [];
    chat.innerHTML = '<div class="empty-note" id="emptyNote"><div class="mini-spark">✦</div>Your next pet-care question starts here.<br>Tell me what\'s on your mind.</div>';
    showToast('Started a new conversation');
    input.focus();
  }

  chatForm.addEventListener('submit', (event) => {
    event.preventDefault();
    handleSend();
  });
  document.getElementById('clearChat').addEventListener('click', newConversation);
  document.getElementById('newChatTop').addEventListener('click', newConversation);

  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => handleSend(button.dataset.prompt));
  });

  // PetNova account + saved care workspace (separate from the existing /chat flow).
  const workspaceView = document.getElementById('workspaceView');
  const contentRoot = document.querySelector('.content');
  const authBackdrop = document.getElementById('authBackdrop');
  const accountButton = document.getElementById('accountButton');
  const authForm = document.getElementById('authForm');
  const authError = document.getElementById('authError');
  let authMode = 'login';
  let activeView = 'chat';
  let sessionToken = sessionStorage.getItem('petnova_token') || '';
  let sessionUser = null;
  let cachedPets = [];

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (sessionToken) headers.Authorization = 'Bearer ' + sessionToken;
    const response = await fetch(API_BASE_URL + path, { ...options, headers });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || 'Request failed (' + response.status + ').');
    return data;
  }
  function showAuth(mode = 'login') {
    setAuthMode(mode);
    authError.hidden = true;
    authBackdrop.hidden = false;
    setTimeout(() => document.getElementById('authEmail').focus(), 0);
  }
  function hideAuth() { authBackdrop.hidden = true; }
  document.getElementById('authClose').addEventListener('click', hideAuth);
  authBackdrop.addEventListener('click', event => { if (event.target === authBackdrop) hideAuth(); });
  function setAuthMode(mode) {
    authMode = mode;
    document.querySelectorAll('[data-auth-mode]').forEach(el => el.classList.toggle('active', el.dataset.authMode === mode));
    document.getElementById('authNameField').hidden = mode !== 'register';
    document.getElementById('authName').required = mode === 'register';
    document.getElementById('authTitle').textContent = mode === 'register' ? 'Make room for your best friend.' : "Your pet's little world.";
    document.getElementById('authPassword').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
    document.getElementById('authSubmit').textContent = mode === 'register' ? 'Create my account' : 'Sign in to PetNova';
    authError.hidden = true;
  }
  function updateAccountButton() {
    accountButton.textContent = sessionUser ? sessionUser.name : 'Sign in';
    accountButton.title = sessionUser ? sessionUser.email + ' — click to sign out' : 'Sign in or create an account';
  }
  async function restoreSession() {
    if (!sessionToken) { updateAccountButton(); return; }
    try { const data = await api('/auth/me'); sessionUser = data.user; }
    catch (_) { sessionToken = ''; sessionStorage.removeItem('petnova_token'); sessionUser = null; }
    updateAccountButton();
  }
  authForm.addEventListener('submit', async event => {
    event.preventDefault();
    authError.hidden = true;
    const submit = document.getElementById('authSubmit');
    submit.disabled = true;
    submit.textContent = authMode === 'register' ? 'Creating account…' : 'Signing in…';
    const body = { email: document.getElementById('authEmail').value.trim(), password: document.getElementById('authPassword').value };
    if (authMode === 'register') body.name = document.getElementById('authName').value.trim();
    try {
      const data = await api(authMode === 'register' ? '/auth/register' : '/auth/login', { method: 'POST', body: JSON.stringify(body) });
      sessionToken = data.token;
      sessionUser = data.user;
      sessionStorage.setItem('petnova_token', sessionToken);
      updateAccountButton();
      hideAuth();
      showToast(authMode === 'register' ? 'Welcome to PetNova!' : 'Welcome back!');
      if (activeView !== 'chat') await renderWorkspace(activeView);
    } catch (error) {
      authError.textContent = error.message;
      authError.hidden = false;
    } finally {
      submit.disabled = false;
      submit.textContent = authMode === 'register' ? 'Create my account' : 'Sign in to PetNova';
    }
  });
  document.querySelectorAll('[data-auth-mode]').forEach(el => el.addEventListener('click', () => setAuthMode(el.dataset.authMode)));
  accountButton.addEventListener('click', () => {
    if (!sessionUser) return showAuth('login');
    if (confirm('Sign out of PetNova on this device?')) {
      sessionToken = ''; sessionUser = null; sessionStorage.removeItem('petnova_token');
      updateAccountButton(); showToast('You have signed out.');
      if (activeView !== 'chat') showAuth('login');
    }
  });
  function setActiveView(view) {
    activeView = view;
    contentRoot.classList.toggle('workspace-mode', view !== 'chat');
    workspaceView.hidden = view === 'chat';
    document.querySelectorAll('.nav-item').forEach(el => {
      const active = (view === 'chat' && !el.dataset.view) || el.dataset.view === view;
      el.classList.toggle('active', active);
      if (active) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
    });
    const names = {chat:'AI Assistant',pets:'My pets',records:'Health records',reminders:'Reminders'};
    document.querySelector('.crumb').innerHTML = 'Workspace <span aria-hidden="true">/</span> <strong>' + names[view] + '</strong>';
  }
  function emptyState(emoji, title, detail) {
    return '<div class="empty-state"><div class="empty-emoji">' + emoji + '</div><strong>' + title + '</strong><p>' + detail + '</p></div>';
  }
  function heading(title, subtitle, actionLabel, action) {
    return '<div class="workspace-heading"><div><h2>' + title + '</h2><p>' + subtitle + '</p></div><button class="primary-btn" type="button" data-action="' + action + '">' + actionLabel + '</button></div>';
  }
  function petOptions(selected = '') {
    return '<option value="">No specific pet</option>' + cachedPets.map(p => '<option value="' + p.id + '" ' + (String(p.id) === String(selected) ? 'selected' : '') + '>' + escapeHTML(p.name) + '</option>').join('');
  }
  function renderPetForm() {
    return '<form class="inline-form" id="petForm"><h3>Add a pet to your family</h3><div class="form-grid">' +
      '<div class="form-field"><label for="petName">Pet name *</label><input id="petName" name="name" required maxlength="80" placeholder="e.g. Milo"></div>' +
      '<div class="form-field"><label for="petSpecies">Species *</label><select id="petSpecies" name="species" required><option value="Dog">Dog</option><option value="Cat">Cat</option><option value="Bird">Bird</option><option value="Rabbit">Rabbit</option><option value="Other">Other</option></select></div>' +
      '<div class="form-field"><label for="petBreed">Breed</label><input id="petBreed" name="breed" maxlength="80" placeholder="Optional"></div>' +
      '<div class="form-field"><label for="petBirth">Birthday</label><input id="petBirth" name="birth_date" type="date"></div>' +
      '<div class="form-field"><label for="petWeight">Weight (kg)</label><input id="petWeight" name="weight" type="number" min=".01" max="500" step=".01" placeholder="Optional"></div>' +
      '<div class="form-field full"><label for="petNotes">Notes</label><textarea id="petNotes" name="notes" maxlength="2000" placeholder="Personality, dietary notes, or anything useful"></textarea></div></div><div class="form-actions"><button class="secondary-btn" type="button" data-action="cancel-form">Cancel</button><button class="primary-btn" type="submit">Save pet</button></div></form>';
  }
  function renderRecordForm() {
    return '<form class="inline-form" id="recordForm"><h3>Add a health record</h3><div class="form-grid">' +
      '<div class="form-field"><label for="recordPet">Pet *</label><select id="recordPet" name="pet_id" required>' + cachedPets.map(p => '<option value="' + p.id + '">' + escapeHTML(p.name) + '</option>').join('') + '</select></div>' +
      '<div class="form-field"><label for="recordType">Record type</label><select id="recordType" name="record_type"><option>Vaccination</option><option>Vet visit</option><option>Medication</option><option>Allergy</option><option>Weight</option><option>General</option></select></div>' +
      '<div class="form-field"><label for="recordTitle">Title *</label><input id="recordTitle" name="title" required maxlength="120" placeholder="e.g. Annual checkup"></div>' +
      '<div class="form-field"><label for="recordDate">Date *</label><input id="recordDate" name="record_date" type="date" required value="' + new Date().toISOString().slice(0,10) + '"></div>' +
      '<div class="form-field full"><label for="recordNotes">Notes</label><textarea id="recordNotes" name="notes" maxlength="3000" placeholder="Details, vet advice, or follow-up notes"></textarea></div></div><div class="form-actions"><button class="secondary-btn" type="button" data-action="cancel-form">Cancel</button><button class="primary-btn" type="submit">Save record</button></div></form>';
  }
  function renderReminderForm() {
    return '<form class="inline-form" id="reminderForm"><h3>Create a care reminder</h3><div class="form-grid">' +
      '<div class="form-field"><label for="reminderTitle">Reminder *</label><input id="reminderTitle" name="title" required maxlength="120" placeholder="e.g. Flea treatment"></div>' +
      '<div class="form-field"><label for="reminderPet">For which pet?</label><select id="reminderPet" name="pet_id">' + petOptions() + '</select></div>' +
      '<div class="form-field"><label for="reminderDue">Due date & time *</label><input id="reminderDue" name="due_at" type="datetime-local" required value="' + new Date(Date.now()+86400000).toISOString().slice(0,16) + '"></div>' +
      '<div class="form-field"><label for="reminderNotes">Notes</label><input id="reminderNotes" name="notes" maxlength="1000" placeholder="Optional details"></div></div><div class="form-actions"><button class="secondary-btn" type="button" data-action="cancel-form">Cancel</button><button class="primary-btn" type="submit">Save reminder</button></div></form>';
  }
  function renderPetCards(pets) {
    if (!pets.length) return emptyState('🐾','No pets added yet','Create your first pet profile to keep their details, health notes, and care reminders together.');
    return '<div class="workspace-grid">' + pets.map(p => '<article class="data-card"><div class="pet-emoji">' + ({Dog:'🐕',Cat:'🐈',Bird:'🦜',Rabbit:'🐇',Other:'🐾'}[p.species] || '🐾') + '</div><div class="data-card-head"><div><h3>' + escapeHTML(p.name) + '</h3><p>' + escapeHTML([p.breed,p.species].filter(Boolean).join(' · ')) + '</p></div></div><div class="meta-line">' + (p.birth_date ? '<span class="meta-pill">🎂 ' + escapeHTML(p.birth_date) + '</span>' : '') + (p.weight ? '<span class="meta-pill">⚖ ' + escapeHTML(p.weight) + ' kg</span>' : '') + '</div>' + (p.notes ? '<p>' + escapeHTML(p.notes) + '</p>' : '<p>No extra notes yet.</p>') + '<div class="card-actions"><button class="secondary-btn" data-action="pet-records" data-id="' + p.id + '">Health records</button><button class="danger-btn" data-action="delete-pet" data-id="' + p.id + '">Delete</button></div></article>').join('') + '</div>';
  }
  function renderRecords(records) {
    if (!cachedPets.length) return emptyState('📋','Add a pet first','Health records are linked to a pet profile. Add your pet before recording visits, vaccinations, or medication notes.');
    if (!records.length) return emptyState('🩺','No health records yet','Keep vaccination dates, vet visits, medication notes, and other care history in one place.');
    return '<div class="list-stack">' + records.map(r => '<article class="record-card"><div class="record-main"><div class="record-topline"><span class="status-pill">' + escapeHTML(r.record_type) + '</span><span class="meta-pill">' + escapeHTML(r.record_date) + '</span></div><h3>' + escapeHTML(r.title) + ' · ' + escapeHTML(r.pet_name) + '</h3>' + (r.notes ? '<p>' + escapeHTML(r.notes) + '</p>' : '') + '</div><button class="danger-btn" data-action="delete-record" data-id="' + r.id + '">Delete</button></article>').join('') + '</div>';
  }
  function renderReminders(reminders) {
    if (!reminders.length) return emptyState('🗓️','Nothing on the calendar yet','Add reminders for grooming, medication, vaccinations, or the next vet appointment.');
    return '<div class="list-stack">' + reminders.map(r => '<article class="record-card"><div class="record-main"><div class="record-topline"><span class="status-pill ' + (r.completed ? 'done' : '') + '">' + (r.completed ? 'Completed' : 'Upcoming') + '</span><span class="meta-pill">' + escapeHTML((r.due_at || '').replace('T',' ')) + '</span></div><h3>' + escapeHTML(r.title) + (r.pet_name ? ' · ' + escapeHTML(r.pet_name) : '') + '</h3>' + (r.notes ? '<p>' + escapeHTML(r.notes) + '</p>' : '') + '</div><div class="card-actions" style="margin-top:0"><button class="secondary-btn" data-action="toggle-reminder" data-id="' + r.id + '" data-completed="' + (!r.completed) + '">' + (r.completed ? 'Reopen' : 'Mark done') + '</button><button class="danger-btn" data-action="delete-reminder" data-id="' + r.id + '">Delete</button></div></article>').join('') + '</div>';
  }
  async function renderWorkspace(view) {
    setActiveView(view);
    if (!sessionUser) {
      workspaceView.innerHTML = heading('Your care workspace','Sign in to save and manage your pet-care information.','Sign in','sign-in') + emptyState('🔐','A private space for your pets','Create a free account to save pet profiles, health records, and reminders securely to your account.');
      return;
    }
    workspaceView.innerHTML = '<div class="empty-state"><div class="empty-emoji">⏳</div><strong>Loading your workspace…</strong><p>Getting your saved care details.</p></div>';
    try {
      cachedPets = (await api('/pets')).pets;
      if (view === 'pets') {
        workspaceView.innerHTML = heading('My pets','A little profile for every member of your furry (or feathered) family.','+ Add a pet','add-pet') + '<div id="formSlot"></div>' + renderPetCards(cachedPets);
      } else if (view === 'records') {
        const records = (await api('/health-records')).records;
        workspaceView.innerHTML = heading('Health records','Keep important care history and vet notes together.','+ Add record','add-record') + '<div id="formSlot"></div>' + renderRecords(records);
      } else {
        const reminders = (await api('/reminders')).reminders;
        workspaceView.innerHTML = heading('Care reminders','Small reminders make it easier to stay consistent with care.','+ Add reminder','add-reminder') + '<div id="formSlot"></div>' + renderReminders(reminders);
      }
    } catch (error) {
      workspaceView.innerHTML = heading('Could not load this page','' + escapeHTML(error.message),'Try again','refresh') + emptyState('🌱','Let’s try that again','Check your connection and retry. Your existing chatbot remains available.');
    }
  }
  document.querySelectorAll('[data-view]').forEach(el => el.addEventListener('click', () => {
    const view = el.dataset.view;
    renderWorkspace(view);
    if (!sessionUser) showAuth('login');
  }));
  document.querySelector('.nav-item:not([data-view])').addEventListener('click', () => {
    setActiveView('chat');
    workspaceView.hidden = true;
    showToast('You’re back with the AI assistant.');
  });
  workspaceView.addEventListener('click', async event => {
    const btn = event.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === 'sign-in') return showAuth('login');
    if (action === 'refresh') return renderWorkspace(activeView);
    if (action === 'cancel-form') { document.getElementById('formSlot').innerHTML = ''; return; }
    if (action === 'add-pet' || action === 'add-record' || action === 'add-reminder') {
      if (!sessionUser) return showAuth('login');
      if ((action === 'add-record' || action === 'add-reminder') && !cachedPets.length && action === 'add-record') {
        showToast('Add a pet profile before adding health records.'); return;
      }
      const slot = document.getElementById('formSlot');
      slot.innerHTML = action === 'add-pet' ? renderPetForm() : action === 'add-record' ? renderRecordForm() : renderReminderForm();
      slot.scrollIntoView({behavior:'smooth',block:'start'});
      return;
    }
    try {
      if (action === 'delete-pet' && confirm('Delete this pet and its linked health records and reminders?')) {
        await api('/pets/' + btn.dataset.id,{method:'DELETE'}); showToast('Pet profile deleted.'); await renderWorkspace('pets');
      } else if (action === 'pet-records') {
        await renderWorkspace('records');
      } else if (action === 'delete-record' && confirm('Delete this health record?')) {
        await api('/health-records/' + btn.dataset.id,{method:'DELETE'}); showToast('Health record deleted.'); await renderWorkspace('records');
      } else if (action === 'toggle-reminder') {
        await api('/reminders/' + btn.dataset.id,{method:'PATCH',body:JSON.stringify({completed:btn.dataset.completed === 'true'})}); await renderWorkspace('reminders');
      } else if (action === 'delete-reminder' && confirm('Delete this reminder?')) {
        await api('/reminders/' + btn.dataset.id,{method:'DELETE'}); showToast('Reminder deleted.'); await renderWorkspace('reminders');
      }
    } catch (error) { showToast(error.message); }
  });
  workspaceView.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const data = Object.fromEntries(new FormData(form).entries());
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      if (form.id === 'petForm') {
        if (data.weight === '') delete data.weight; else if (data.weight) data.weight = Number(data.weight);
        await api('/pets',{method:'POST',body:JSON.stringify(data)});
        showToast('Pet profile saved!'); await renderWorkspace('pets');
      } else if (form.id === 'recordForm') {
        data.pet_id = Number(data.pet_id);
        await api('/health-records',{method:'POST',body:JSON.stringify(data)});
        showToast('Health record saved.'); await renderWorkspace('records');
      } else if (form.id === 'reminderForm') {
        data.pet_id = data.pet_id ? Number(data.pet_id) : null;
        await api('/reminders',{method:'POST',body:JSON.stringify(data)});
        showToast('Reminder saved.'); await renderWorkspace('reminders');
      }
    } catch (error) { showToast(error.message); submit.disabled = false; }
  });
  document.querySelectorAll('[data-focus-chat]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById('chatInput');
    input?.focus();
    input?.scrollIntoView({behavior:'smooth',block:'center'});
  }));
  restoreSession();
