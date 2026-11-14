import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

const address = process.env.NEXT_TASK_TEST_URL;
const chrome = spawn(process.env.CHROME_BIN, ['--headless=new', '--no-sandbox', '--disable-gpu',
  '--disable-background-networking', '--disable-dev-shm-usage', '--password-store=basic',
  '--no-first-run', '--remote-debugging-port=0',
  `--user-data-dir=${process.env.NEXT_TASK_BROWSER_PROFILE}`, 'about:blank'], {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe']});
let socket;
const errors = [];
try {
  let endpoint;
  let startupOutput = '';
  let startupTimeout;
  const ready = new Promise((resolve, reject) => {
    chrome.stderr.on('data', chunk => {
      startupOutput += chunk;
      const match = startupOutput.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {endpoint = match[1]; resolve();}
    });
    chrome.once('error', reject);
    chrome.once('exit', code => reject(new Error(`Chrome exited: ${code}`)));
  });
  try {
    await Promise.race([ready, new Promise((_, reject) => {
      startupTimeout = setTimeout(() => reject(new Error(`Chrome did not start: ${startupOutput}`)), 30000);
    })]);
  } finally { clearTimeout(startupTimeout); }
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
  let nextId = 0;
  const pending = new Map();
  socket.onmessage = event => {
    const item = JSON.parse(event.data);
    if (item.id) {
      const call = pending.get(item.id);
      pending.delete(item.id);
      if (item.error) call.reject(new Error(JSON.stringify(item.error)));
      else call.resolve(item.result);
    } else if (item.method === 'Runtime.exceptionThrown') errors.push(item.params.exceptionDetails.text);
  };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
  });
  const {targetId} = await send('Target.createTarget', {url: 'about:blank'});
  const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
  await send('Runtime.enable', {}, sessionId);
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true, userGesture: true}, sessionId);
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const wait = async expression => {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await evaluate(expression)) return;
      await delay(50);
    }
    throw new Error(`Timed out: ${expression}; page: ${await evaluate('document.body.innerText')}`);
  };
  const fill = (selector, value) => evaluate(`{const input = document.querySelector(${JSON.stringify(selector)}); if (!input) throw new Error('Missing input'); const prototype = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(value)}); input.dispatchEvent(new Event('input', {bubbles:true}));}`);
  const changeLanguage = value => evaluate(`{const select = document.querySelector('.language-selector select'); select.value = ${JSON.stringify(value)}; select.dispatchEvent(new Event('change', {bubbles:true}));}`);
  const navigate = async hash => {await evaluate(`location.hash=${JSON.stringify(hash)}`); await delay(150);};
  await send('Page.navigate', {url: address}, sessionId);
  await wait(`document.querySelector('.login-card form') !== null`);
  await fill('input[name="email"], input[autocomplete="username"]', 'en@example.com');
  await fill('input[autocomplete="current-password"]', 'correct horse');
  await changeLanguage('pt-BR');
  await wait(`document.documentElement.lang === 'pt-BR'`);
  assert.equal(await evaluate(`document.querySelector('input[autocomplete="username"]').value`), 'en@example.com');
  await evaluate(`document.querySelector('.login-card form').requestSubmit()`);
  await wait(`document.querySelector('.recommended-card') !== null`);
  // Saved account language overrides the explicit pre-login selection.
  assert.equal(await evaluate('document.documentElement.lang'), 'en');
  assert.match(await evaluate('document.body.innerText'), /Meet your next task/);
  await navigate('/settings');
  await wait(`document.querySelector('.code-input') !== null`);
  await fill('.code-input', 'priority * 26');
  await fill('#current-password', 'unsaved password');
  await changeLanguage('pt-BR');
  await wait(`document.documentElement.lang === 'pt-BR'`);
  assert.equal(await evaluate(`document.querySelector('.code-input').value`), 'priority * 26');
  assert.equal(await evaluate(`document.querySelector('#current-password').value`), 'unsaved password');
  assert.match(await evaluate('document.body.innerText'), /Configurações/);
  // A task editor stays mounted with its unsaved user content through locale changes.
  const taskId = await evaluate(`fetch('/api/tasks').then(r=>r.json()).then(tasks=>tasks.find(t=>t.title==='Meet your next task').id)`);
  await evaluate(`document.querySelector('.new-task-button').click()`);
  await wait(`document.querySelector('.quick-capture-modal') !== null`);
  await fill('.capture-field textarea', 'User title stays mine');
  await changeLanguage('en');
  await wait(`document.documentElement.lang === 'en'`);
  assert.equal(await evaluate(`document.querySelector('.capture-field textarea').value`), 'User title stays mine');
  await evaluate(`document.querySelector('.quick-capture-modal .icon-button').click()`);
  // Task and tag editing plus fixed date formats remain usable in both languages.
  for (const language of ['en', 'pt-BR']) {
    await changeLanguage(language);
    await wait(`document.documentElement.lang === '${language}'`);
    await navigate('/tags');
    await wait(`document.querySelector('.tag-tree') !== null`);
    assert.match(await evaluate('document.body.innerText'), /Personal/); // Existing examples are never renamed.
    await navigate('/tasks');
    await wait(`document.querySelector('.task-card .edit-button') !== null`);
    await evaluate(`document.querySelector('.task-card .edit-button').click()`);
    await wait(`document.querySelector('.shared-task-form') !== null`);
    assert.ok(await evaluate(`document.querySelector('.shared-task-form .field-label').textContent.length > 0`));
    await evaluate(`document.querySelector('.close-icon').click()`);
    await navigate('/settings');
    await wait(`document.querySelector('.language-selector select') !== null`);
  }
  await navigate('/next');
  await wait(`document.querySelector('.pomodoro-launcher .start-button') !== null`);
  await evaluate(`document.querySelector('.pomodoro-launcher .start-button').click()`);
  await wait(`document.querySelector('.focus-screen .period-button:not(:disabled)') !== null`);
  await evaluate(`document.querySelector('.focus-screen .period-button').click()`);
  await wait(`document.querySelector('.running-label') !== null`);
  const active = await evaluate(`fetch('/api/pomodoro/session').then(r=>r.json())`);
  assert.equal(active.state, 'running');
  await navigate('/settings');
  await wait(`document.querySelector('.language-selector select') !== null`);
  await changeLanguage('pt-BR');
  await wait(`document.documentElement.lang === 'pt-BR'`);
  await navigate('/focus');
  await wait(`document.querySelector('.running-label') !== null`);
  const after = await evaluate(`fetch('/api/pomodoro/session').then(r=>r.json())`);
  assert.equal(after.ends_at, active.ends_at);
  assert.equal(after.task_id, active.task_id);
  assert.equal(after.state, 'running');
  assert.equal(after.task_id, taskId);
  assert.match(await evaluate('document.body.innerText'), /Em andamento|Em execução|Executando/);
  // Catalog HTML must escape task titles before sanitizing/rendering them.
  await evaluate(`fetch('/api/tasks/${taskId}', {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'<img src=x onerror="window.injected=true">'})})`);
  await navigate('/settings');
  await wait(`document.querySelector('.language-selector select') !== null`);
  await navigate('/focus');
  await wait(`document.querySelector('.focus-task-area .task-card') !== null`);
  // Force the pinned task outside the session scope to exercise a rich catalog sentence.
  await evaluate(`(async()=>{const tags=await fetch('/api/tags').then(r=>r.json()); const current=await fetch('/api/pomodoro/session').then(r=>r.json()); await fetch('/api/pomodoro/session/scope',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_scope:current.scope,scope:{include_tag_ids:[tags.find(t=>t.name==='Work').id],exclude_tag_ids:[],tag_match:'all'}})});})()`);
  await wait(`document.querySelector('.scope-warning') !== null`);
  assert.match(await evaluate(`document.querySelector('.scope-warning').textContent`), /<img/);
  assert.equal(await evaluate(`document.querySelector('.scope-warning img') !== null || window.injected === true`), false);
  await evaluate(`fetch('/api/auth/logout',{method:'POST'})`);
  await send('Emulation.setDeviceMetricsOverride', {width:390,height:844,deviceScaleFactor:1,mobile:true}, sessionId);
  for (const language of ['en', 'pt-BR']) {
    await evaluate(`localStorage.setItem('next-task-language', '${language}')`);
    await send('Page.navigate', {url: address + '/?flow=invite-' + language + '#/accept-invite?token=invite-' + language + '-' + 'x'.repeat(32) + '&lang=' + language}, sessionId);
    await wait(`document.querySelector('#invite-password') !== null`);
    assert.equal(await evaluate('document.documentElement.lang'), language);
    assert.ok(await evaluate(`document.body.scrollWidth <= innerWidth + 1`), 'Mobile auth page must not overflow horizontally');
    assert.ok(await evaluate(`document.querySelector('.language-selector').getBoundingClientRect().bottom <= document.querySelector('.login-card').getBoundingClientRect().top`), 'Language selector must not overlap the form');
    const required = await evaluate(`{const field=document.querySelector('input[autocomplete="name"]');field.checkValidity();field.validationMessage;}`);
    assert.equal(required, language === 'en' ? 'This field is required.' : 'Este campo é obrigatório.');
    await fill('input[autocomplete="name"]', 'Invited browser user');
    await fill('#invite-password', 'correct horse');
    await fill('#invite-confirmation', 'correct horse');
    await evaluate(`document.querySelector('.login-card form').requestSubmit()`);
    await wait(`document.querySelector('.notice') !== null`);
    assert.match(await evaluate('document.body.innerText'), language === 'en' ? /Account created/ : /Conta criada/);
    await send('Page.navigate', {url: address + '/?flow=verify-' + language + '#/verify-email?token=verify-' + language + '-' + 'x'.repeat(32) + '&lang=' + language}, sessionId);
    await wait(`document.querySelector('.login-card .primary:not(:disabled)') !== null`);
    await evaluate(`document.querySelector('.login-card .primary').click()`);
    await wait(`document.querySelector('.login-card a') !== null && !document.querySelector('.login-card .primary')`);
    assert.match(await evaluate('document.body.innerText'), language === 'en' ? /Your email is verified/ : /Seu e-mail foi verificado/);
    await send('Page.navigate', {url: address + '/?flow=reset-' + language + '#/reset-password?token=reset-' + language + '-' + 'x'.repeat(32) + '&lang=' + language}, sessionId);
    await wait(`document.querySelector('#reset-password') !== null`);
    await fill('#reset-password', 'new secure password');
    await fill('#reset-confirmation', 'new secure password');
    await evaluate(`document.querySelector('.login-card form').requestSubmit()`);
    await wait(`document.querySelector('.notice') !== null`);
    assert.match(await evaluate('document.body.innerText'), language === 'en' ? /Password changed/ : /Senha alterada/);
    await evaluate(`document.querySelector('.back-link a').click()`);
    await wait(`document.querySelector('.login-card input[autocomplete="username"]') !== null`);
    await navigate('/forgot-password');
    await wait(`document.querySelector('input[autocomplete="email"]') !== null`);
    await fill('input[autocomplete="email"]', 'unknown@example.com');
    await evaluate(`document.querySelector('.login-card form').requestSubmit()`);
    await wait(`document.querySelector('.notice') !== null`);
    assert.match(await evaluate('document.body.innerText'), language === 'en' ? /If this address belongs/ : /Se este endere\u00e7o pertencer/);
  }
  assert.deepEqual(errors, []);
  await send('Browser.close');
} finally {
  socket?.close();
  chrome.kill();
}
