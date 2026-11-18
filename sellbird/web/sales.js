/* Product-scoped sales-agent UI. All data reads/writes use authenticated same-origin API calls. */
(() => {
  'use strict';
  const state = {companies: [], products: [], prospects: [], companyId: '', productId: '', prospectId: '', lastEmail: null};
  const $ = id => document.getElementById(id);
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  let noticeTimer;

  async function api(path, options = {}) {
    const response = await authFetch(path, options);
    let data = {};
    try { data = await response.json(); } catch { /* a status-only response */ }
    if (!response.ok) {
      const detail = data.detail;
      let message = typeof detail === 'string' ? detail : (detail?.error || data.error || `Request failed (${response.status})`);
      if (detail?.task_id) message += ` Queued as ${detail.task_id}; open System & inference to retry it.`;
      throw new Error(message);
    }
    return data;
  }
  function jsonOptions(method, value) {
    return {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)};
  }
  function say(message, kind = 'success') {
    const box = $('notice'); box.textContent = message; box.className = `notice ${kind}`;
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { box.textContent = ''; box.className = ''; }, 6500);
  }
  function showError(error) { say(error?.message || String(error), 'error'); }
  function setOutput(id, value) { const node = $(id); node.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); node.classList.remove('hidden'); }
  function formData(form) { return Object.fromEntries(new FormData(form).entries()); }
  function commaList(text) { return String(text || '').split(',').map(x => x.trim()).filter(Boolean); }
  function asText(value) { return value == null ? '' : String(value); }

  document.querySelectorAll('.nav[data-panel]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('.nav').forEach(item => item.classList.toggle('active', item === button));
    document.querySelectorAll('.panel').forEach(item => item.classList.toggle('active', item.id === `panel-${button.dataset.panel}`));
    if (button.dataset.panel === 'system') refreshSystem();
  }));

  async function refreshAll() {
    try {
      const [companies, products, health] = await Promise.all([
        api('/api/sales/companies'), api('/api/sales/products'), api('/api/health')
      ]);
      state.companies = companies.companies || [];
      state.products = products.products || [];
      if (!state.companyId || !state.companies.some(x => x.id === state.companyId)) state.companyId = state.companies[0]?.id || '';
      state.products = state.products.filter(x => x.company_id === state.companyId);
      if (!state.productId || !state.products.some(x => x.id === state.productId)) state.productId = state.products[0]?.id || '';
      const prospectQuery = new URLSearchParams({company_id: state.companyId, product_id: state.productId});
      const prospects = await api(`/api/sales/prospects?${prospectQuery}`);
      state.prospects = prospects.prospects || [];
      renderSelectors(); renderProspects(); renderOverview(health.local_ai);
      await loadSelectedForms();
      await loadSampleReplies();
      if (document.querySelector('#panel-system.active')) refreshSystem();
    } catch (error) { showError(error); }
  }

  function renderSelectors() {
    const company = $('company-select'); company.replaceChildren();
    for (const item of state.companies) company.add(new Option(item.name, item.id));
    company.value = state.companyId;
    if (!state.companies.length) company.add(new Option('Create a business first', ''));
    const product = $('product-select'); product.replaceChildren();
    for (const item of state.products) product.add(new Option(item.name, item.id));
    if (!state.products.length) product.add(new Option('Create a product first', ''));
    product.value = state.productId;
  }

  $('company-select').addEventListener('change', async event => {
    state.companyId = event.target.value; state.productId = ''; state.prospectId = '';
    try {
      const result = await api(`/api/sales/products?company_id=${encodeURIComponent(state.companyId)}`);
      state.products = result.products || [];
      state.productId = state.products[0]?.id || '';
      const prospects = await api(`/api/sales/prospects?company_id=${encodeURIComponent(state.companyId)}&product_id=${encodeURIComponent(state.productId)}`);
      state.prospects = prospects.prospects || [];
      renderSelectors(); renderProspects(); await loadSelectedForms(); await loadSampleReplies(); await refreshOverview();
    } catch (error) { showError(error); }
  });
  $('product-select').addEventListener('change', async event => {
    state.productId = event.target.value; state.prospectId = '';
    try {
      const prospects = await api(`/api/sales/prospects?company_id=${encodeURIComponent(state.companyId)}&product_id=${encodeURIComponent(state.productId)}`);
      state.prospects = prospects.prospects || [];
      renderProspects();
    } catch (error) { showError(error); }
    await loadSelectedForms(); await loadSampleReplies(); await refreshOverview();
  });

  async function loadSelectedForms() {
    if (state.companyId) {
      const company = state.companies.find(x => x.id === state.companyId);
      if (company) {
        fillForm($('company-form'), company);
        $('profile-edit').value = company.profile ? JSON.stringify(company.profile, null, 2) : '';
      }
    } else { $('company-form').reset(); $('profile-edit').value = ''; }
    if (state.productId) {
      const product = state.products.find(x => x.id === state.productId);
      if (product) {
        fillForm($('product-form'), {...product,
          features: (product.features || []).join(', '), benefits: (product.benefits || []).join(', '),
          customer_pain_points: (product.customer_pain_points || []).join(', '),
          icp_criteria: JSON.stringify(product.icp_criteria || {}, null, 2)});
        $('icp-edit').value = product.icp ? JSON.stringify(product.icp, null, 2) : '';
      }
    } else { $('product-form').reset(); $('icp-edit').value = ''; }
    $('generate-profile').disabled = !state.companyId;
    $('generate-icp').disabled = !state.productId;
    await refreshOverview();
  }
  function fillForm(form, value) {
    for (const [key, field] of new FormData(form).entries()) void field;
    for (const element of form.elements) if (element.name && value[element.name] != null) element.value = value[element.name];
  }

  $('company-form').addEventListener('submit', async event => {
    event.preventDefault();
    const payload = formData(event.currentTarget);
    try {
      if (state.companyId) await api(`/api/sales/companies/${state.companyId}`, jsonOptions('PUT', payload));
      else { const created = await api('/api/sales/companies', jsonOptions('POST', payload)); state.companyId = created.id; }
      say('Business profile saved locally.'); await refreshAll();
    } catch (error) { showError(error); }
  });
  $('generate-profile').addEventListener('click', async () => {
    if (!state.companyId) return say('Save a business before generating its profile.', 'error');
    try { const result = await api(`/api/sales/companies/${state.companyId}/generate-profile`, {method: 'POST'}); setOutput('profile-output', result); $('profile-edit').value = JSON.stringify(result, null, 2); say('Business profile generated by local Ollama inference.'); await refreshAll(); await refreshSystem(); }
    catch (error) { showError(error); }
  });
  $('save-profile').addEventListener('click', async () => {
    if (!state.companyId) return say('Save a business first.', 'error');
    try {
      const profile = JSON.parse($('profile-edit').value);
      await api(`/api/sales/companies/${state.companyId}/profile`, jsonOptions('PUT', profile));
      setOutput('profile-output', profile); say('Edited business profile saved locally.'); await refreshAll();
    } catch (error) { showError(error instanceof SyntaxError ? new Error('Profile must be valid JSON.') : error); }
  });

  $('product-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!state.companyId) return say('Save a business before adding a product.', 'error');
    const values = formData(event.currentTarget);
    let icpCriteria = {};
    try { icpCriteria = values.icp_criteria.trim() ? JSON.parse(values.icp_criteria) : {}; }
    catch { return say('ICP criteria must be valid JSON.', 'error'); }
    const payload = {company_id: state.companyId, name: values.name, description: values.description,
      features: commaList(values.features), benefits: commaList(values.benefits), target_market: values.target_market,
      pricing: values.pricing, value_proposition: values.value_proposition,
      competitive_differentiation: values.competitive_differentiation,
      customer_pain_points: commaList(values.customer_pain_points), sales_positioning: values.sales_positioning,
      icp_criteria: icpCriteria};
    try {
      if (state.productId) await api(`/api/sales/products/${state.productId}`, jsonOptions('PUT', payload));
      else { const created = await api('/api/sales/products', jsonOptions('POST', payload)); state.productId = created.id; }
      say('Product context saved.'); await refreshAll();
    } catch (error) { showError(error); }
  });
  $('generate-icp').addEventListener('click', async () => {
    if (!state.productId) return say('Save a product first.', 'error');
    try { const result = await api(`/api/sales/products/${state.productId}/generate-icp`, {method: 'POST'}); setOutput('icp-output', result); $('icp-edit').value = JSON.stringify(result, null, 2); say('Product-specific ICP generated and saved.'); await refreshSystem(); await refreshAll(); }
    catch (error) { showError(error); }
  });
  $('save-icp').addEventListener('click', async () => {
    if (!state.productId) return say('Save a product first.', 'error');
    try {
      const icp = JSON.parse($('icp-edit').value);
      await api(`/api/sales/products/${state.productId}/icp`, jsonOptions('PUT', icp));
      setOutput('icp-output', icp); say('Edited product ICP saved.'); await refreshAll();
    } catch (error) { showError(error instanceof SyntaxError ? new Error('ICP must be valid JSON.') : error); }
  });

  $('prospect-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!state.companyId) return say('Create/select a business first.', 'error');
    const raw = formData(event.currentTarget);
    const payload = {...raw, company_id: state.companyId,
      employee_count: raw.employee_count ? Number(raw.employee_count) : null,
      field_provenance: Object.fromEntries(Object.entries(raw).filter(([, value]) => value).map(([key]) => [key, 'user_provided']))};
    try {
      await api('/api/sales/prospects', jsonOptions('POST', payload)); event.currentTarget.reset();
      say('Prospect saved.'); await refreshAll();
    } catch (error) { showError(error); }
  });
  $('import-csv').addEventListener('click', async () => {
    if (!state.companyId) return say('Create/select a business before importing prospects.', 'error');
    const file = $('csv-file').files[0]; if (!file) return say('Choose a CSV file first.', 'error');
    try {
      const csvText = await file.text();
      const result = await api('/api/sales/prospects/import', jsonOptions('POST', {company_id: state.companyId, csv_text: csvText}));
      $('import-result').textContent = `${result.imported} imported · ${result.skipped} duplicates · ${result.errors.length} invalid rows`;
      setOutput('prospect-output', result); say('CSV import finished.'); await refreshAll();
    } catch (error) { showError(error); }
  });
  $('discover-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!state.companyId || !state.productId) return say('Create/select a business and product first.', 'error');
    const raw = formData(event.currentTarget);
    const payload = {...raw, company_id: state.companyId, product_id: state.productId,
      radius_km: Number(raw.radius_km), limit: Number(raw.limit)};
    try {
      const task = await api('/api/sales/discover', jsonOptions('POST', payload));
      say('OpenStreetMap search queued. Public map services may take several minutes to respond.');
      for (let count = 0; count < 220; count++) {
        await sleep(1000);
        const result = await api(`/api/sales/tasks/${task.task_id}`);
        if (result.status === 'completed') {
          setOutput('discovery-output', result.result);
          say(`${result.result.imported} businesses imported · ${result.result.duplicates} duplicates skipped.`);
          await refreshAll();
          return;
        }
        if (result.status === 'failed') throw new Error(result.error || 'OpenStreetMap discovery failed.');
      }
      say('Discovery is still running. Refresh the prospect list shortly.', 'error');
    } catch (error) { showError(error); }
  });

  function renderProspects() {
    const target = $('prospect-list'); target.replaceChildren();
    if (!state.companyId) { target.className = 'empty'; target.textContent = 'Create a business first.'; return; }
    const query = $('prospect-filter').value.trim().toLowerCase();
    const rows = state.prospects.filter(item => item.company_id === state.companyId &&
      (!query || [item.company_name, item.industry, item.location, item.contact_name, item.job_title, item.business_email]
        .some(value => asText(value).toLowerCase().includes(query))));
    if (!rows.length) { target.className = 'empty'; target.textContent = query ? 'No prospects match this filter.' : 'No prospects yet. Add one above, import a CSV, or search OpenStreetMap.'; return; }
    target.className = 'table-wrap';
    const table = document.createElement('table'); table.className = 'prospect-table';
    const head = document.createElement('thead'); head.innerHTML = '<tr><th>Prospect</th><th>Priority</th><th>Contact</th><th>Research</th><th>Product workflows</th></tr>'; table.append(head);
    const body = document.createElement('tbody');
    for (const prospect of rows) {
      const tr = document.createElement('tr');
      const company = document.createElement('td'); company.innerHTML = `<span class="prospect-name">${escapeHtml(prospect.company_name)}</span><br><span class="muted">${escapeHtml(prospect.industry || prospect.location || 'Industry/location missing')}</span>`;
      const priority = document.createElement('td'); priority.textContent = prospect.priority_score == null ? 'Not scored' : `${Math.round(Number(prospect.priority_score))} / 100`;
      const contact = document.createElement('td'); contact.textContent = [prospect.contact_name, prospect.job_title, prospect.business_email].filter(Boolean).join(' · ') || 'Contact details missing';
      const research = document.createElement('td'); research.textContent = `${prospect.research_status} · ${prospect.researched_at || 'no cached research'}`;
      const actions = document.createElement('td'); actions.className = 'prospect-actions';
      const buttons = [
        ['Research website', () => runResearch(prospect)], ['Cached analysis', () => runProspectWorkflow(prospect, 'analyze-research')],
        ['Buying signals', () => runProspectWorkflow(prospect, 'classify-signals')], ['Problem', () => runProspectWorkflow(prospect, 'generate-problem')],
        ['Score', () => runProspectWorkflow(prospect, 'score')], ['Draft email', () => runProspectWorkflow(prospect, 'generate-email')],
        ['Index locally', () => indexResearch(prospect)], ['Select', () => selectProspect(prospect)],
      ];
      for (const [label, callback] of buttons) { const btn = document.createElement('button'); btn.className = 'button secondary'; btn.type = 'button'; btn.textContent = label; btn.addEventListener('click', callback); actions.append(btn); }
      tr.append(company, priority, contact, research, actions); body.append(tr);
    }
    table.append(body); target.append(table);
  }
  function escapeHtml(value) { return asText(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }

  async function selectProspect(prospect) {
    state.prospectId = prospect.id;
    try { const result = await api(`/api/sales/prospects/${prospect.id}?product_id=${encodeURIComponent(state.productId)}`); setOutput('prospect-output', {prospect: result, product_id: state.productId}); }
    catch (error) { showError(error); }
  }
  async function runProspectWorkflow(prospect, workflow) {
    if (!state.productId) return say('Create/select a product before running prospect workflows.', 'error');
    state.prospectId = prospect.id;
    const url = `/api/sales/prospects/${prospect.id}/${workflow}`;
    const payload = {product_id: state.productId};
    if (workflow === 'generate-email') payload.style = $('email-style').value;
    try {
      const result = await api(url, jsonOptions('POST', payload));
      if (workflow === 'generate-email') state.lastEmail = result;
      setOutput('prospect-output', {product: state.products.find(x => x.id === state.productId)?.name, workflow, result});
      say(`${workflow.replaceAll('-', ' ')} completed and saved.`);
      await refreshAll(); await refreshSystem();
    } catch (error) { showError(error); }
  }
  async function runResearch(prospect) {
    if (!state.productId) return say('Select a product context first.', 'error');
    try {
      const task = await api(`/api/sales/prospects/${prospect.id}/research`, jsonOptions('POST', {max_pages: 4}));
      say('Public research queued. The task status will update here.');
      for (let count = 0; count < 45; count++) {
        await sleep(900); const result = await api(`/api/sales/tasks/${task.task_id}`);
        if (['completed', 'failed'].includes(result.status)) {
          setOutput('prospect-output', result);
          if (result.status === 'completed') { say('Permitted public pages cached with source URLs.'); await refreshAll(); }
          else say(result.error || 'Research failed.', 'error');
          return;
        }
      }
      say('Research is still running; refresh the prospect shortly.', 'error');
    } catch (error) { showError(error); }
  }
  async function indexResearch(prospect) {
    try { const result = await api(`/api/sales/prospects/${prospect.id}/index-research`, {method: 'POST'}); setOutput('prospect-output', result); say(`${result.indexed} cached source(s) indexed using the local embedding model.`); }
    catch (error) { showError(error); }
  }
  $('refresh-prospects').addEventListener('click', async () => {
    try { const result = await api(`/api/sales/prospects?company_id=${encodeURIComponent(state.companyId)}&product_id=${encodeURIComponent(state.productId)}`); state.prospects = result.prospects; renderProspects(); say('Prospect list refreshed.'); }
    catch (error) { showError(error); }
  });
  $('prospect-filter').addEventListener('input', renderProspects);
  $('copy-email').addEventListener('click', async () => {
    if (!state.lastEmail?.body) return say('Generate an email first.', 'error');
    try { await navigator.clipboard.writeText(`Subject: ${state.lastEmail.subject}\n\n${state.lastEmail.body}`); say('Email copied to clipboard.'); }
    catch { say('Clipboard access was denied by the browser.', 'error'); }
  });

  async function loadSampleReplies() {
    const root = $('sample-buttons'); root.replaceChildren();
    if (!state.productId) { root.textContent = 'Select a product to load its stored sample conversations.'; return; }
    try {
      const data = await api(`/api/sales/conversations/samples?product_id=${encodeURIComponent(state.productId)}`);
      if (!(data.conversations || []).length) { root.textContent = 'No stored sample conversations for this product. Add sample data with the demo initializer.'; return; }
      for (const item of data.conversations) {
        const button = document.createElement('button'); button.className = 'button secondary'; button.type = 'button';
        button.textContent = `Load sample · ${item.reply_text.slice(0, 58)}${item.reply_text.length > 58 ? '…' : ''}`;
        button.title = 'Stored demonstration conversation; not a real customer interaction';
        button.addEventListener('click', () => { $('reply-text').value = item.reply_text; $('reply-sample').checked = true; });
        root.append(button);
      }
    } catch (error) { showError(error); }
  }
  $('classify-reply').addEventListener('click', async () => {
    if (!state.productId) return say('Create/select a product before classifying a reply.', 'error');
    const reply_text = $('reply-text').value.trim();
    if (!reply_text) return say('Enter the reply text to classify.', 'error');
    try {
      const result = await api('/api/sales/conversations/classify', jsonOptions('POST', {
        product_id: state.productId, reply_text, sample: $('reply-sample').checked
      }));
      setOutput('reply-output', result); $('reply-output').classList.remove('hidden');
      say(result.sample ? 'Sample reply classified (demonstration data).' : 'Reply classified and saved locally.');
      await refreshOverview(); await refreshSystem();
    } catch (error) { showError(error); }
  });

  async function refreshOverview() {
    try {
      const [result, artifacts] = await Promise.all([api('/api/sales/overview'), api(`/api/sales/artifacts?product_id=${encodeURIComponent(state.productId)}`)]);
      const labels = [['companies','Businesses'], ['products','Products'], ['prospects','Prospects'], ['qualified_prospects','Qualified'], ['high_priority_prospects','High priority'], ['buying_signals','Buying signals'], ['outreach_generated','Emails generated'], ['recent_research','Research summaries'], ['pending_tasks','Pending tasks']];
      $('metrics').replaceChildren(...labels.map(([key,label]) => {
        const card = document.createElement('div'); card.className = 'metric';
        const number = document.createElement('strong'); number.textContent = String(result.metrics?.[key] ?? 0);
        const caption = document.createElement('span'); caption.textContent = label; card.append(number, caption); return card;
      }));
      const company = state.companies.find(x => x.id === state.companyId);
      const product = state.products.find(x => x.id === state.productId);
      $('selected-context').textContent = company && product ? `${company.name} · ${product.name}. ${product.description || 'Add product details for stronger, product-specific workflows.'}` : 'Create a business and at least one product to begin.';
      $('workflow-status').textContent = result.local_ai.model_available ? `Ollama is ready with ${result.local_ai.configured_model}. New web research is ${result.offline_mode ? 'disabled in offline mode' : 'available when needed'}.` : `${result.local_ai.error}. Local AI workflows are waiting for Ollama; deterministic scoring and SQLite remain available.`;
      const recent = (artifacts.artifacts || []).slice(0, 6);
      const recentNode = $('recent-artifacts'); recentNode.replaceChildren();
      if (!recent.length) { recentNode.className = 'empty'; recentNode.textContent = 'No generated workflows yet.'; }
      else { recentNode.className = ''; for (const row of recent) { const div = document.createElement('div'); div.className = 'log-row'; div.innerHTML = `<time>${escapeHtml(row.created_at)}</time><span>${escapeHtml(row.workflow)} · ${escapeHtml(row.prospect_id || 'business/product')}</span><span>${escapeHtml(state.products.find(p=>p.id===row.product_id)?.name || '')}</span>`; recentNode.append(div); } }
      updateAiPill(result.local_ai);
    } catch (error) { showError(error); }
  }
  async function renderOverview(ai) {
    updateAiPill(ai);
    await refreshOverview();
  }
  function updateAiPill(ai) {
    const pill = $('ai-status'); if (!ai) return;
    pill.textContent = ai.model_available ? `Local model ready · ${ai.configured_model}` : `Local model unavailable · ${ai.configured_model}`;
    pill.className = `pill ${ai.model_available ? 'good' : 'bad'}`;
  }
  $('refresh-overview').addEventListener('click', refreshAll);

  async function refreshSystem() {
    try {
      const [models, mode, logs, queued] = await Promise.all([api('/api/system/models'), api('/api/sales/offline-mode'), api('/api/system/inference-logs?limit=60'), api('/api/sales/tasks?status_filter=queued&limit=100')]);
      $('offline-toggle').checked = !!mode.enabled; $('offline-toggle').disabled = !!mode.environment_forced;
      const modelNode = $('model-status'); modelNode.textContent = JSON.stringify({status: models.status, endpoint: 'local/private Ollama endpoint', configured_model: models.configured_model, installed_models: models.installed_models, model_available: models.model_available, offline_mode: mode.enabled, error: models.error, setup: `Install Ollama, then run: ollama pull ${models.configured_model}`}, null, 2);
      const hw = $('hardware-status'); hw.replaceChildren();
      const summary = document.createElement('pre'); summary.className = 'output'; summary.textContent = JSON.stringify(models.hardware, null, 2); hw.append(summary);
      for (const item of models.recommendations || []) {
        const row = document.createElement('div'); row.className = 'recommendation';
        const diskState = item.disk_space_available == null ? 'drive space unknown' : item.disk_space_available ? 'drive space available' : 'free drive space may be insufficient';
        row.innerHTML = `<strong>${escapeHtml(item.profile)} · ${escapeHtml(item.model)}</strong><br>${escapeHtml(item.note)}<br>RAM guide ${escapeHtml(item.minimum_system_ram_gib)} GiB · GPU VRAM ${escapeHtml(item.minimum_gpu_vram_gib)} GiB · CPU-only ${item.cpu_only_supported ? 'supported' : 'not recommended'}<br>${escapeHtml(item.quantization)} · download about ${escapeHtml(item.estimated_download_gib)} GiB · ${escapeHtml(diskState)}`;
        hw.append(row);
      }
      const logNode = $('inference-logs'); logNode.replaceChildren();
      if (!(logs.logs || []).length) { logNode.className = 'empty'; logNode.textContent = 'No local inference has been recorded.'; }
      else { logNode.className = ''; for (const log of logs.logs) { const row = document.createElement('div'); row.className = 'log-row'; row.innerHTML = `<time>${escapeHtml(log.created_at)}</time><span>${escapeHtml(log.workflow)} · ${escapeHtml(log.model)}</span><span class="status ${log.status === 'ok' ? '' : 'error'}">${escapeHtml(log.status)} · ${escapeHtml(log.duration_ms)} ms</span>${log.error ? `<span class="error-detail">${escapeHtml(log.error)}</span>` : ''}`; logNode.append(row); } }
      const queueNode = $('queued-tasks'); queueNode.replaceChildren();
      const retryable = (queued.tasks || []).filter(task => task.task_type.startsWith('ai:'));
      if (!retryable.length) { queueNode.className = 'empty'; queueNode.textContent = 'No queued workflows.'; }
      else {
        queueNode.className = '';
        for (const task of retryable) {
          const row = document.createElement('div'); row.className = 'log-row';
          const label = document.createElement('span'); label.textContent = `${task.task_type.slice(3)} · ${task.error || task.id}`;
          const button = document.createElement('button'); button.className = 'button secondary'; button.type = 'button'; button.textContent = 'Retry locally';
          button.addEventListener('click', async () => {
            button.disabled = true;
            try { const result = await api(`/api/sales/tasks/${task.id}/retry`, {method: 'POST'}); setOutput('task-output', result); say('Queued local workflow completed.'); await refreshSystem(); await refreshAll(); }
            catch (error) { showError(error); button.disabled = false; }
          });
          row.append(label, button); queueNode.append(row);
        }
      }
      updateAiPill(models);
    } catch (error) { showError(error); }
  }
  $('refresh-system').addEventListener('click', refreshSystem);
  $('offline-toggle').addEventListener('change', async event => {
    try { const result = await api('/api/sales/offline-mode', jsonOptions('PUT', {enabled: event.target.checked})); say(result.enabled ? 'Offline mode enabled. Fresh web research is disabled.' : 'Offline mode disabled. Public research can run when requested.'); await refreshSystem(); }
    catch (error) { event.target.checked = !event.target.checked; showError(error); }
  });

  refreshAll();
})();
