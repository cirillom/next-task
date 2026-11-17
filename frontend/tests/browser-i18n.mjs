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
  const confirmations = [];
  let acceptConfirmation = true;
  socket.onmessage = event => {
    const item = JSON.parse(event.data);
    if (item.id) {
      const call = pending.get(item.id);
      pending.delete(item.id);
      if (item.error) call.reject(new Error(JSON.stringify(item.error)));
      else call.resolve(item.result);
    } else if (item.method === 'Runtime.exceptionThrown') errors.push(item.params.exceptionDetails.exception?.description || item.params.exceptionDetails.text);
    else if (item.method === 'Page.javascriptDialogOpening') {
      confirmations.push(item.params.message);
      void send('Page.handleJavaScriptDialog', {accept: acceptConfirmation}, item.sessionId);
      acceptConfirmation = true;
    }
  };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
  });
  const {targetId} = await send('Target.createTarget', {url: 'about:blank'});
  const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
  await send('Runtime.enable', {}, sessionId);
  await send('Page.enable', {}, sessionId);
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
    throw new Error(`Timed out: ${expression}; errors: ${JSON.stringify(errors)}; page: ${await evaluate('document.body.innerText')}`);
  };
  const fill = (selector, value) => evaluate(`{const input = document.querySelector(${JSON.stringify(selector)}); if (!input) throw new Error('Missing input'); input.focus(); const prototype = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(value)}); input.dispatchEvent(new Event('input', {bubbles:true}));}`);
  const press = async (key, modifiers = 0) => {
    const codes = {Escape:27, Enter:13, Tab:9, Home:36, ArrowDown:40, ArrowUp:38, ArrowLeft:37, ArrowRight:39, '/':191, '?':191};
    const code = key.length === 1 && /[a-z]/i.test(key) ? `Key${key.toUpperCase()}` : key === '/' || key === '?' ? 'Slash' : key;
    const params = {key, code, modifiers, windowsVirtualKeyCode: codes[key] || key.toUpperCase().charCodeAt(0)};
    if (!(modifiers & 7) && (key.length === 1 || key === 'Enter')) params.text = key === 'Enter' ? '\r' : key;
    await send('Input.dispatchKeyEvent', {type:'keyDown', ...params}, sessionId);
    await send('Input.dispatchKeyEvent', {type:'keyUp', ...params}, sessionId);
  };
  const fillEditor = async (selector, value) => {
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
    await press('a', 2);
    await send('Input.insertText', {text: value}, sessionId);
  };
  const blur = () => evaluate(`document.activeElement?.blur()`);
  const changeLanguage = value => evaluate(`{const select = document.querySelector('.language-selector select'); select.value = ${JSON.stringify(value)}; select.dispatchEvent(new Event('change', {bubbles:true}));}`);
  const navigate = async hash => {await evaluate(`location.hash=${JSON.stringify(hash)}`); await delay(150);};
  const checkScrolledHeader = async () => {
    const result = await evaluate(`(() => {
      const toolbar=document.querySelector('.tasks-toolbar'),header=document.querySelector('.topbar');
      window.scrollBy(0,toolbar.getBoundingClientRect().top-8);
      const t=toolbar.getBoundingClientRect(),h=header.getBoundingClientRect();
      const top=Math.max(t.top,h.top),bottom=Math.min(t.bottom,h.bottom);
      const hit=document.elementFromPoint((t.left+t.right)/2,(top+bottom)/2);
      const buttons=[...header.querySelectorAll('button')];
      return {overlap:bottom>top,headerOnTop:header.contains(hit),buttonsReachable:buttons.every(button=>{const r=button.getBoundingClientRect();return button.contains(document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2));})};
    })()`);
    assert.ok(result.overlap && result.headerOnTop && result.buttonsReachable, `Search toolbar covers scrolled header: ${JSON.stringify(result)}`);
    await evaluate(`window.scrollTo(0,0)`);
  };
  const checkCardHeading = async selector => {
    const layout=await evaluate(`(() => {
      const card=document.querySelector(${JSON.stringify(selector)});
      const rect=selector=>{const r=card.querySelector(selector).getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width};};
      const parent=card.querySelector('.parent-link button');
      return {header:rect('.card-heading'),title:rect('.card-title'),actions:rect('.card-header-actions'),score:rect('.score'),hierarchy:rect('.task-hierarchy'),boost:rect('.ranking-boost'),parentOverflow:parent.scrollWidth>parent.clientWidth+1};
    })()`);
    assert.ok(Math.abs(layout.title.top-layout.actions.top)<1 && layout.title.right<=layout.actions.left, JSON.stringify(layout));
    assert.ok(Math.abs(layout.hierarchy.top-layout.boost.top)<1 && layout.hierarchy.right<=layout.boost.left, JSON.stringify(layout));
    assert.ok(Math.abs(layout.title.left-layout.hierarchy.left)<1 && Math.abs(layout.score.right-layout.boost.right)<1, JSON.stringify(layout));
    assert.ok(layout.hierarchy.top>=layout.title.bottom && layout.boost.top>=layout.actions.bottom && layout.title.width>=layout.header.width*.45 && !layout.parentOverflow, JSON.stringify(layout));
  };
  const checkQueueTags = async () => {
    const rows = await evaluate(`Promise.all([...document.querySelectorAll('.queue-row')].map(async row => {
      const id=row.querySelector('.queue-title .task-id').textContent.trim().slice(1);
      const task=await fetch('/api/tasks/'+id).then(r=>r.json());
      const badges=[...row.querySelectorAll('.queue-tags .tag-badge')];
      return {expected:task.direct_tags.map(tag=>tag.display_name),actual:badges.map(badge=>badge.textContent.trim()),
        contained:badges.every(badge=>{const b=badge.getBoundingClientRect(),r=row.getBoundingClientRect();return b.left>=r.left && b.right<=r.right && badge.scrollWidth<=badge.clientWidth+1;})};
    }))`);
    assert.ok(rows.some(row=>row.expected.length), 'Queue fixture must include tagged tasks');
    for (const row of rows) {assert.deepEqual(row.actual,row.expected); assert.ok(row.contained,JSON.stringify(row));}
  };
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
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false},sessionId);
  const contentLeft = await evaluate(`document.querySelector('.content').getBoundingClientRect().left`);
  await evaluate(`document.querySelector('.sidebar-toggle').focus()`);
  await press('Enter');
  assert.ok(await evaluate(`document.querySelector('.sidebar-toggle').getAttribute('aria-expanded')==='false' && getComputedStyle(document.querySelector('#sidebar-navigation')).display==='none' && document.querySelector('#desktop-sidebar').getBoundingClientRect().width<=32 && document.querySelector('.sidebar-toggle').getClientRects().length>0`));
  assert.ok(await evaluate(`document.querySelector('.content').getBoundingClientRect().left < ${contentLeft}`));
  await navigate('/tasks');
  assert.equal(await evaluate(`document.querySelector('.sidebar-toggle').getAttribute('aria-label')`), 'Show sidebar');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:740,deviceScaleFactor:1,mobile:true},sessionId);
  assert.ok(await evaluate(`document.querySelector('.sidebar-toggle').getClientRects().length===0 && getComputedStyle(document.querySelector('.mobile-nav')).display!=='none' && document.documentElement.scrollWidth<=innerWidth+1`));
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false},sessionId);
  await evaluate(`document.querySelector('.sidebar-toggle').focus()`);
  await press(' ');
  assert.ok(await evaluate(`document.querySelector('.sidebar-toggle').getAttribute('aria-expanded')==='true' && getComputedStyle(document.querySelector('#sidebar-navigation')).display!=='none'`));
  assert.equal(await evaluate(`document.querySelector('.content').getBoundingClientRect().left`), contentLeft);
  await navigate('/settings');
  await wait(`document.querySelector('.code-input')?.value.length > 0`);
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

  await wait(`document.querySelector('.quick-capture-modal') === null`);
  assert.equal(await evaluate(`document.querySelector('.sidebar > button:not(.sidebar-toggle)') === null`), true);
  await evaluate(`Array.from(document.querySelectorAll('.content .app-button')).find(button=>button.textContent.includes('Show keyboard shortcuts')).click()`);
  await wait(`document.querySelector('.shortcut-dialog') !== null`);
  assert.ok(await evaluate(`!!document.querySelector('.shortcut-dialog .app-button')`));
  await press('Escape');
  await wait(`document.querySelector('.shortcut-dialog') === null`);
  // Always-on shortcuts, context priority, dirty dialogs, native newlines, and save validation.
  await blur(); await press('n');
  await wait(`document.querySelector('.capture-field textarea') === document.activeElement`);
  await press('Escape');
  await wait(`document.querySelector('.quick-capture-modal') === null`);
  await blur(); await press('n');
  await wait(`document.querySelector('.capture-field textarea') !== null`);
  await fill('.capture-field textarea', 'Keyboard draft');
  await press('s',2);
  await wait(`document.querySelector('.quick-capture-modal') === null`);
  assert.ok(await evaluate(`fetch('/api/drafts').then(r=>r.json()).then(drafts=>drafts.some(d=>d.title==='Keyboard draft'))`));
  const checklistDraftId = await evaluate(`(async()=>{
    const draft=(await fetch('/api/drafts').then(r=>r.json())).find(d=>d.title==='Keyboard draft');
    await fetch('/api/tasks/'+draft.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:'- [ ] draft item'})});
    return draft.id;
  })()`);
  await navigate('/drafts');
  await wait(`Array.from(document.querySelectorAll('.draft-card')).find(c=>c.textContent.includes('Keyboard draft'))?.querySelector('input:not(:disabled)')`);
  await evaluate(`Array.from(document.querySelectorAll('.draft-card')).find(c=>c.textContent.includes('Keyboard draft')).querySelector('input').click()`);
  await wait(`fetch('/api/tasks/${checklistDraftId}').then(r=>r.json()).then(t=>t.description==='- [x] draft item' && t.priority===0)`);
  await navigate('/settings');
  await wait(`document.querySelector('.language-selector select') !== null`);
  await blur(); await press('?', 8);
  await wait(`document.querySelector('.shortcut-dialog') !== null`);
  await wait(`document.activeElement === document.querySelector('.shortcut-dialog .app-button')`);
  assert.doesNotMatch(await evaluate(`document.querySelector('.shortcut-dialog').textContent`), /[\u2190-\u2193]|Shift\+Tab/);
  assert.equal(await evaluate(`{const event = new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true});document.querySelector('.shortcut-dialog .app-button').dispatchEvent(event);event.defaultPrevented;}`), false);
  await evaluate(`document.querySelector('.brand').focus()`);
  assert.ok(await evaluate(`document.activeElement === document.querySelector('.brand')`));
  await press('Escape');
  await wait(`document.querySelector('.shortcut-dialog') === null`);
  await navigate('/tasks');
  await wait(`document.querySelector('.task-card') !== null`);
  // Tab and page arrows retain browser behavior; no custom focus navigation remains.
  await evaluate(`document.querySelector('.brand').focus()`); await press('Tab');
  assert.ok(await evaluate(`document.activeElement === document.querySelector('.new-task-button')`));
  for (const key of ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight']) {
    assert.equal(await evaluate(`{const event = new KeyboardEvent('keydown',{key:${JSON.stringify(key)},bubbles:true,cancelable:true});document.activeElement.dispatchEvent(event);event.defaultPrevented;}`), false);
    await press(key);
    assert.ok(await evaluate(`document.activeElement === document.querySelector('.new-task-button')`));
  }
  await blur(); await press('/');
  await wait(`document.activeElement?.matches('.content input[type="search"]')`);
  await press('n');
  assert.equal(await evaluate(`document.querySelector('.quick-capture-modal') === null`), true);
  assert.match(await evaluate(`document.activeElement.value`), /n/);
  await fill('.content input[type="search"]', '');
  await send('Input.insertText', {text:'test'}, sessionId);
  await press('ArrowLeft');
  assert.equal(await evaluate(`document.activeElement.selectionStart`), 3);
  await fill('.content input[type="search"]', '');
  await blur();
  assert.equal(await evaluate(`{const e = new KeyboardEvent('keydown',{key:'n',ctrlKey:true,bubbles:true,cancelable:true});document.body.dispatchEvent(e);e.defaultPrevented;}`), false);
  await evaluate(`document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'n',isComposing:true,bubbles:true}));document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'n',repeat:true,bubbles:true}));`);
  assert.equal(await evaluate(`document.querySelector('.quick-capture-modal') === null`), true);
  await press('n');
  await wait(`document.querySelector('.capture-field textarea') !== null`);
  await fill('.capture-field textarea', 'Keyboard task');
  await press('Enter');
  assert.equal(await evaluate(`document.querySelector('.capture-field textarea').value`), 'Keyboard task\n');
  await send('Input.insertText', {text:'Keyboard notes'}, sessionId);
  const beforeCancel = confirmations.length;
  acceptConfirmation = false;
  await press('Escape');
  assert.equal(confirmations.length, beforeCancel + 1);
  assert.ok(await evaluate(`document.querySelector('.capture-field textarea').value.includes('Keyboard notes')`));
  await press('Enter', 2);
  await wait(`document.querySelector('.quick-capture-modal .shared-task-form') !== null`);
  const tagInput = '.quick-capture-modal .tag-picker input[role="combobox"]';
  await evaluate(`document.querySelector(${JSON.stringify(tagInput)}).focus()`);
  await wait(`document.querySelector('.tag-options button') !== null`);
  for (const key of ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Tab']) {
    assert.equal(await evaluate(`{const event = new KeyboardEvent('keydown',{key:${JSON.stringify(key)},bubbles:true,cancelable:true});document.querySelector(${JSON.stringify(tagInput)}).dispatchEvent(event);event.defaultPrevented;}`), false);
  }
  // Removing navigation leaves the existing click selection available.
  await evaluate(`document.querySelector('.tag-options button').click()`);
  await wait(`document.querySelector('.selected-tags .tag-badge') !== null`);
  await evaluate(`document.querySelector(${JSON.stringify(tagInput)}).focus()`);
  await press('Escape');
  assert.equal(await evaluate(`document.querySelector('.tag-options') === null && !!document.querySelector('.quick-capture-modal')`), true);
  await press('ArrowDown');
  assert.equal(await evaluate(`document.querySelector('.tag-options') === null`), true);
  await fill('.quick-capture-modal .title-row input', '');
  await press('Enter', 2);
  assert.ok(await evaluate(`document.querySelector('.quick-capture-modal .title-row input').validationMessage.length > 0`));
  await fill('.quick-capture-modal .title-row input', 'Keyboard task');
  await press('Enter', 2);
  await wait(`document.querySelector('.quick-capture-modal') === null`);
  await navigate('/tasks');
  await wait(`Array.from(document.querySelectorAll('.title-button')).some(b=>b.textContent.includes('Keyboard task'))`);
  await evaluate(`Array.from(document.querySelectorAll('.title-button')).find(b=>b.textContent.includes('Keyboard task')).click()`);
  await wait(`document.querySelector('.shared-task-form') !== null`);
  await fill('.shared-task-form .title-row input', 'Keyboard task renamed');
  await press('Enter');
  await wait(`document.querySelector('.task-editor') === null`);
  await wait(`Array.from(document.querySelectorAll('.title-button')).some(b=>b.textContent.includes('Keyboard task renamed'))`);
  await evaluate(`Array.from(document.querySelectorAll('.title-button')).find(b=>b.textContent.includes('Keyboard task renamed')).click()`);
  await wait(`document.querySelector('.shared-task-form') !== null`);
  await fill('.shared-task-form .title-row input', 'Keyboard task updated');
  await press('s', 2);
  await wait(`document.querySelector('.task-editor') === null`);
  await wait(`Array.from(document.querySelectorAll('.title-button')).some(b=>b.textContent.includes('Keyboard task updated'))`);
  const conflictTaskId = await evaluate(`(async()=>{
    const task=(await fetch('/api/tasks').then(r=>r.json())).find(t=>t.title==='Keyboard task updated');
    await fetch('/api/tasks/'+task.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:${JSON.stringify('A\r\nB\nC')}})});
    return task.id;
  })()`);
  await evaluate(`Array.from(document.querySelectorAll('.title-button')).find(b=>b.textContent.includes('Keyboard task updated')).click()`);
  await wait(`document.querySelector('.shared-task-form') !== null`);
  await evaluate(`{const modes=document.querySelectorAll('.task-editor .modes button'); modes[1].click();modes[2].click();modes[0].click();}`);
  assert.equal(await evaluate(`fetch('/api/tasks/${conflictTaskId}').then(r=>r.json()).then(t=>t.description)`), 'A\r\nB\nC');
  await evaluate(`fetch('/api/tasks/${conflictTaskId}',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:'Changed elsewhere'})})`);
  await fill('.shared-task-form .title-row input', 'Unsaved title');
  await press('s', 2);
  await wait(`document.querySelector('.shared-task-form [role="alert"]')?.textContent.includes('description changed')`);
  assert.equal(await evaluate(`document.querySelector('.shared-task-form .title-row input').value`), 'Unsaved title');
  assert.deepEqual(await evaluate(`fetch('/api/tasks/${conflictTaskId}').then(r=>r.json()).then(t=>[t.title,t.description])`), ['Keyboard task updated', 'Changed elsewhere']);
  await evaluate(`{const confirm=window.confirm; window.confirm=()=>true; document.querySelector('.task-editor .close-icon').click(); window.confirm=confirm;}`);
  await wait(`document.querySelector('.task-editor') === null`);
  await evaluate(`Array.from(document.querySelectorAll('.title-button')).find(b=>b.textContent.includes('Keyboard task updated')).click()`);
  await wait(`document.querySelector('.editor-header-actions .block-action') !== null`);
  await evaluate(`document.querySelector('.editor-header-actions .block-action').click()`);
  await wait(`document.querySelector('#blocking-reason') !== null`);
  await fillEditor('#blocking-reason', 'x'.repeat(4001));
  await wait(`document.querySelector('.block-modal .reason-field [role="alert"]') !== null`);
  assert.equal(await evaluate(`document.querySelector('.block-modal button[type="submit"]').disabled`), true);
  await fillEditor('#blocking-reason', 'x'.repeat(4000));
  assert.equal(await evaluate(`document.querySelector('.block-modal button[type="submit"]').disabled`), false);
  await fillEditor('#blocking-reason', '#');
  await wait(`document.querySelector('.block-modal .task-options') !== null`);
  await press('Escape');
  assert.ok(await evaluate(`!document.querySelector('.block-modal .task-options') && !!document.querySelector('.block-modal')`));
  for (const value of ['# heading', '##heading', '`#task`', '[[task:1]]']) {
    await fillEditor('#blocking-reason', value);
    await delay(250);
    assert.equal(await evaluate(`document.querySelector('.block-modal .task-options')`), null);
  }
  await fillEditor('#blocking-reason', '#1');
  await wait(`document.querySelector('.block-modal .task-options') !== null`);
  await press('Escape');
  await press('Escape');
  await wait(`document.querySelector('.block-modal') === null`);
  assert.ok(await evaluate(`!!document.querySelector('.task-editor')`));
  await press('Escape');
  await wait(`document.querySelector('.task-editor') === null`);
  await evaluate(`document.querySelector('[aria-label="Filter tasks"]').click()`);
  await press('Escape');
  await wait(`document.querySelector('.filter-popover') === null`);
  // Preserve wide Markdown/code inside cards rather than allowing grid tracks to overflow the page.
  const referenceTagId = await evaluate(`fetch('/api/tags').then(r=>r.json()).then(tags=>tags.find(t=>t.name==='Personal').id)`);
  const stressPatch = {title: 'Keyboard task updated ' + 'x'.repeat(350), priority:40, description: ['```text', 'x'.repeat(4000), '```', '', '- [ ] first', '- [x] second', '', '==highlight== $x^2$ note[^one]', '', '> [!note]- More', '> Callout body', '', '```mermaid', 'graph TD', 'A --> B', '```', '', `[[task:${taskId}]] [[task:999999|Unavailable alias]] [[tag:${referenceTagId}]]`, '', '[^one]: footnote content', '', '<input type="checkbox" data-markdown-control="forged">', '<img src="x" onerror="window.markdownInjected=true">', '<a href="javascript&#58;alert(1)">Unsafe link</a>', '<img src="data:image/svg+xml,evil">', '<svg onload="window.markdownInjected=true"></svg>'].join('\n')};
  const boostedTask = await evaluate(`(async()=>{
    const tasks=await fetch('/api/tasks').then(r=>r.json());const task=tasks.find(t=>t.title==='Keyboard task updated');
    const parent=await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'High-priority parent',priority:10000})}).then(r=>r.json());
    await fetch('/api/tasks/'+task.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({...${JSON.stringify(stressPatch)},parent_task_id:parent.id,due_date:new Date().toISOString().slice(0,10)})});
    return {id:task.id,parentId:parent.id};
  })()`);
  await navigate('/settings'); await navigate('/tasks');
  await wait(`document.querySelector('.task-card') !== null`);
  await wait(`document.querySelector('.task-card:has(.ranking-boost) .markdown input') !== null`);
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown input')).map(i=>[i.checked,i.disabled])`), [[false,false],[true,false]]);
  assert.equal(await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown [data-markdown-control="forged"]')`), null);
  assert.equal(await evaluate(`window.markdownInjected === true`), false);
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown a')).find(a=>a.textContent==='Unsafe link')?.hasAttribute('href')`), false);
  assert.equal(await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown img[src^="data:"]')`), null);
  assert.equal(await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown mark')?.textContent`), 'highlight');
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .description-toggle').click()`);
  await wait(`document.querySelector('.task-card:has(.ranking-boost) .markdown [data-markdown-math]') !== null`);
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown [data-markdown-math]').scrollIntoView()`);
  await wait(`document.querySelector('.task-card:has(.ranking-boost) .markdown math') !== null`);
  assert.equal(await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown details.callout')?.open`), false);
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown details.callout summary').click()`);
  assert.equal(await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown details.callout')?.open`), true);
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown pre[data-markdown-diagram]').scrollIntoView()`);
  await wait(`document.querySelector('.task-card:has(.ranking-boost) .markdown pre[data-markdown-diagram] svg') !== null`);
  assert.ok(await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown .footnotes')?.textContent.includes('footnote content')`));
  await wait(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown [data-markdown-reference]')).some(a=>a.textContent==='Meet your next task' && a.hasAttribute('href'))`);
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown [data-markdown-reference]')).find(a=>a.textContent==='Unavailable alias').hasAttribute('href')`), false);
  const hashBeforeFootnote = await evaluate(`location.hash`);
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown sup a').click()`);
  assert.equal(await evaluate(`location.hash`), hashBeforeFootnote);
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown input').click()`);
  await wait(`fetch('/api/tasks/${boostedTask.id}').then(r=>r.json()).then(t=>t.description===${JSON.stringify(stressPatch.description.replace('- [ ] first', '- [x] first'))} && t.priority===40 && !t.finished_at)`);
  await wait(`document.querySelector('.task-card:has(.ranking-boost) .markdown input:checked') !== null`);
  await evaluate(`document.querySelector('.task-card:has(.ranking-boost) .markdown input').click()`);
  await wait(`fetch('/api/tasks/${boostedTask.id}').then(r=>r.json()).then(t=>t.description===${JSON.stringify(stressPatch.description)})`);
  await wait(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown [data-markdown-reference]')).some(a=>a.textContent==='Meet your next task' && a.hasAttribute('href'))`);
  await evaluate(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown [data-markdown-reference]')).find(a=>a.textContent==='Meet your next task').click()`);
  await wait(`document.querySelector('.task-editor .header-task-id')?.textContent.includes('#${taskId}')`);
  await wait(`document.querySelector('.task-editor .cm-content') !== null`);
  await evaluate(`document.querySelectorAll('.task-editor .modes button')[1].click()`);
  await fillEditor('.task-editor .cm-content', `[[tag:${referenceTagId}|Open tag]]\nUnsaved notes`);
  await evaluate(`document.querySelectorAll('.task-editor .modes button')[2].click()`);
  await wait(`Array.from(document.querySelectorAll('.task-editor .reading-surface [data-markdown-reference]')).some(a=>a.textContent==='Open tag' && a.hasAttribute('href'))`);
  const confirmationsBeforeReference = confirmations.length;
  acceptConfirmation = false;
  await evaluate(`Array.from(document.querySelectorAll('.task-editor .reading-surface [data-markdown-reference]')).find(a=>a.textContent==='Open tag').click()`);
  assert.equal(confirmations.length, confirmationsBeforeReference + 1);
  assert.ok(await evaluate(`document.querySelector('.task-editor .reading-surface').textContent.includes('Unsaved notes')`));
  await evaluate(`document.querySelector('.task-editor .close-icon').click()`);
  await wait(`document.querySelector('.task-editor') === null`);
  await evaluate(`Array.from(document.querySelectorAll('.task-card:has(.ranking-boost) .markdown [data-markdown-reference]')).find(a=>a.textContent==='Personal').click()`);
  await wait(`location.hash === '#/tags?tag=${referenceTagId}'`);
  await wait(`document.querySelector('.tag-details form input')?.value === 'Personal'`);
  await navigate('/tasks');
  await wait(`document.querySelector('.task-card:has(.ranking-boost)') !== null`);
  for (const width of [320, 390, 760, 1024, 1640]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600},sessionId);
    await delay(50);
    assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth + 1`), `Tasks overflow at ${width}px`);
    assert.ok(await evaluate(`Array.from(document.querySelectorAll('.task-card')).every(card=>card.getBoundingClientRect().right <= document.querySelector('.content').getBoundingClientRect().right + 1)`), `Card escapes its column at ${width}px`);
    await checkCardHeading('.task-card:has(.ranking-boost)');
  }
  for (const language of ['en', 'pt-BR']) {
    await navigate('/settings');
    await wait(`document.querySelector('.language-selector select') !== null`);
    await changeLanguage(language);
    await wait(`document.documentElement.lang === '${language}'`);
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:740,deviceScaleFactor:1,mobile:true},sessionId);
    for (const view of ['next','tasks','drafts','tags','settings']) {
      await navigate('/'+view);
      assert.equal(await evaluate(`document.querySelectorAll('.mobile-nav [aria-current="page"]').length`),1);
      assert.ok(await evaluate(`document.querySelector('.mobile-nav button:nth-child(${['next','tasks','drafts','tags','settings'].indexOf(view)+1})').matches('.active[aria-current="page"]')`));
      assert.ok(await evaluate(`getComputedStyle(document.querySelector('.mobile-nav .active')).backgroundColor !== getComputedStyle(document.querySelector('.mobile-nav button:not(.active)')).backgroundColor`));
      if (view==='next') {
        await wait(`document.querySelector('.recommended-card .ranking-boost') !== null`);
        await checkCardHeading('.recommended-card');
        await wait(`document.querySelector('.queue-tags .tag-badge') !== null`);
        await checkQueueTags();
      }
    }
    await navigate('/tasks');
    await wait(`document.querySelector('.task-card .ranking-boost') !== null`);
    for (const width of [320,390,640]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:740,deviceScaleFactor:1,mobile:true},sessionId);
      await evaluate(`window.scrollTo(0,0)`);
      await delay(50);
      assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth+1`), `${language} overflow at ${width}px`);
      await checkCardHeading('.task-card:has(.ranking-boost)');
      await checkScrolledHeader();
      for (const [index, panel] of [[1,'sort'],[0,'filter']]) {
        await evaluate(`document.querySelectorAll('.tasks-toolbar .toolbar-icon')[${index}].click()`);
        await wait(`document.querySelector('.${panel}-popover') !== null`);
        const layout=await evaluate(`(() => {
          const button=document.querySelectorAll('.tasks-toolbar .toolbar-icon')[${index}],panel=document.querySelector('.${panel}-popover');
          const b=button.getBoundingClientRect(),p=panel.getBoundingClientRect();
          return {gap:p.top-b.bottom,left:p.left,right:p.right,bottom:p.bottom,listTop:document.querySelector('.task-list').getBoundingClientRect().top,linked:button.getAttribute('aria-controls')===panel.id};
        })()`);
        assert.ok(layout.gap>=0 && layout.gap<=24 && layout.left>=0 && layout.right<=width+1 && layout.listTop>=layout.bottom && layout.linked, `${language} ${panel} panel ${width}px: ${JSON.stringify(layout)}`);
        await checkScrolledHeader();
        if (panel==='sort') {
          await evaluate(`{const select=document.querySelector('.sort-popover select');select.value='due_date';select.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('.direction-options button').click();}`);
          await wait(`document.querySelector('.task-card .title-button .task-id')?.textContent.trim() === '#${boostedTask.id}'`);
        } else {
          await evaluate(`{const select=document.querySelector('.filter-grid select');select.value='only';select.dispatchEvent(new Event('change',{bubbles:true}));}`);
          await wait(`document.querySelectorAll('.task-card').length === 0 && document.querySelector('.clear-button') !== null`);
          await evaluate(`document.querySelector('.clear-button').click()`);
          await wait(`document.querySelector('.task-card') !== null`);
          await evaluate(`document.querySelector('.filter-popover').scrollIntoView({block:'center'})`);
          assert.ok(await evaluate(`{const panel=document.querySelector('.filter-popover').getBoundingClientRect();panel.top>=document.querySelector('.topbar').getBoundingClientRect().bottom && panel.bottom<=document.querySelector('.mobile-nav').getBoundingClientRect().top;}`), `Filter controls obscured at ${width}px`);
        }
        await press('Escape');
        await wait(`document.querySelector('.toolbar-popover') === null`);
      }
      await evaluate(`document.querySelectorAll('.tasks-toolbar .toolbar-icon')[1].click()`);
      await evaluate(`document.querySelectorAll('.tasks-toolbar .toolbar-icon')[0].click()`);
      await wait(`!!document.querySelector('.filter-popover') && !document.querySelector('.sort-popover')`);
      await evaluate(`document.querySelector('.popover-backdrop').click()`);
      await wait(`document.querySelector('.toolbar-popover') === null`);
    }
  }
  await evaluate(`(async()=>{await fetch('/api/tasks/${boostedTask.id}',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent_task_id:null,due_date:null,priority:1})});await fetch('/api/tasks/${boostedTask.parentId}',{method:'DELETE'});})()`);
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false},sessionId);
  await navigate('/settings');
  await wait(`document.querySelector('.language-selector select') !== null`);
  await changeLanguage('en');
  await wait(`document.documentElement.lang === 'en'`);
  await navigate('/tags');
  await wait(`document.querySelector('.tag-tree .tag-select') !== null`);
  await evaluate(`document.querySelector('.tag-tree .tag-select').click()`);
  await wait(`document.querySelector('.tag-details form[data-shortcut-save] .cm-content') !== null`);
  await fillEditor('.tag-details form[data-shortcut-save] .cm-content', 'Keyboard tag notes');
  await press('s',4);
  await wait(`fetch('/api/tags').then(r=>r.json()).then(tags=>tags.some(t=>t.description==='Keyboard tag notes'))`);
  await wait(`document.querySelector('.tag-details .cm-content')?.textContent === 'Keyboard tag notes'`);
  const conflictTagId = await evaluate(`(async()=>{
    const tag=(await fetch('/api/tags').then(r=>r.json())).find(t=>t.description==='Keyboard tag notes');
    await fetch('/api/tags/'+tag.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:'Changed elsewhere'})});
    return tag.id;
  })()`);
  await fillEditor('.tag-details .cm-content', 'Unsaved tag notes');
  await press('s',4);
  await wait(`document.querySelector('.error[role="alert"]')?.textContent.includes('description changed')`);
  assert.equal(await evaluate(`document.querySelector('.tag-details .cm-content').textContent`), 'Unsaved tag notes');
  assert.equal(await evaluate(`fetch('/api/tags').then(r=>r.json()).then(tags=>tags.find(t=>t.id===${conflictTagId}).description)`), 'Changed elsewhere');
  await navigate('/settings');
  await wait(`document.querySelector('.language-selector select') !== null`);
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
  await blur(); await press('?',8);
  await wait(`document.querySelector('.shortcut-dialog') !== null`);
  assert.match(await evaluate(`document.querySelector('.shortcut-dialog').textContent`), /Atalhos de teclado/);
  await press('Escape');
  await navigate('/next');
  await wait(`document.querySelector('.pomodoro-launcher .start-button:not(:disabled)') !== null`);
  await evaluate(`fetch('/api/tasks/${taskId}',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:'- [ ] next item'})})`);
  await navigate('/settings'); await navigate('/next');
  await wait(`document.querySelector('.recommended-card .markdown input:not(:disabled)') !== null`);
  await evaluate(`document.querySelector('.recommended-card .markdown input').click()`);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description==='- [x] next item' && !t.finished_at)`);
  const raceTaskId = await evaluate(`fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Focus race second',description:'B base'})}).then(r=>r.json()).then(t=>t.id)`);
  await evaluate(`document.querySelector('.pomodoro-launcher .start-button').click()`);
  await wait(`document.querySelector('.focus-screen .period-button:not(:disabled)') !== null`);
  await evaluate(`document.querySelector('.focus-screen .period-button').click()`);
  await wait(`document.querySelector('.running-label') !== null`);
  const active = await evaluate(`fetch('/api/pomodoro/session').then(r=>r.json())`);
  assert.equal(active.state, 'running');
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[1].click()`);
  await fillEditor('.focus-description-editor .cm-content', 'Saved with keyboard');
  await press('Enter',2);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description==='Saved with keyboard')`);
  await wait(`document.querySelector('.focus-description-editor .save-state')?.textContent.includes('Salvo')`);
  await evaluate(`fetch('/api/tasks/${taskId}',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:'Remote focus notes'})})`);
  await fillEditor('.focus-description-editor .cm-content', 'Local focus notes');
  await press('s',2);
  await wait(`document.querySelector('.focus-description-editor [role="alert"]') !== null`);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-content').textContent`), 'Local focus notes');
  assert.equal(await evaluate(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description)`), 'Remote focus notes');
  await evaluate(`Array.from(document.querySelectorAll('.focus-description-editor button')).find(b=>b.textContent.includes('Salvar minhas anotações')).click()`);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description==='Local focus notes')`);
  await wait(`document.querySelector('.focus-description-editor .save-state')?.textContent.includes('Salvo')`);
  await evaluate(`{window.modeFetch=window.fetch; window.modeSaves=0; window.fetch=(input,init)=>{if(String(input)==='/api/tasks/${taskId}' && init?.method==='PATCH' && 'description' in JSON.parse(init.body)) window.modeSaves++; return window.modeFetch(input,init);};}`);
  await evaluate(`{const modes=document.querySelectorAll('.focus-description-editor .modes button');modes[0].click();modes[2].click();modes[1].click();}`);
  await delay(800);
  assert.equal(await evaluate(`window.modeSaves`), 0);
  await evaluate(`window.fetch=window.modeFetch`);
  await fillEditor('.focus-description-editor .cm-content', 'Intro\n\n- [ ] one\n- [X] two\n\n- ordinary');
  await press('Home',2);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[0].click()`);
  await wait(`document.querySelectorAll('.focus-description-editor .cm-content input[type="checkbox"]').length===2`);
  const checklistLayout = await evaluate(`Array.from(document.querySelectorAll('.focus-description-editor .cm-content input[type="checkbox"]')).map(input => ({width:input.getBoundingClientRect().width,height:input.closest('.cm-line').getBoundingClientRect().height}))`);
  assert.ok(checklistLayout.every(item => item.width < 24 && item.height < 40), JSON.stringify(checklistLayout));
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.focus-description-editor .cm-content input[type="checkbox"]')).map(input => input.closest('.cm-line').textContent.trim())`), ['one', 'two']);
  assert.ok(await evaluate(`document.querySelector('.focus-description-editor .cm-content').textContent.includes('- ordinary')`));
  await evaluate(`document.querySelector('.focus-description-editor .cm-content').focus()`);
  await press('Home',2);
  await press('ArrowDown');
  await press('ArrowDown');
  await wait(`document.querySelector('.focus-description-editor .cm-content').textContent.includes('- [ ] one')`);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[1].click()`);
  assert.ok(await evaluate(`document.querySelector('.focus-description-editor .cm-content').textContent.includes('- [ ] one')`));
  await fillEditor('.focus-description-editor .cm-content', '- [ ] one\n- [X] two');
  await press('s',2);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description===${JSON.stringify('- [ ] one\n- [X] two')})`);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[2].click()`);
  await wait(`document.querySelectorAll('.focus-description-editor .reading-surface input[type="checkbox"]').length===2`);
  await evaluate(`document.querySelector('.focus-description-editor .reading-surface input').click()`);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description===${JSON.stringify('- [x] one\n- [X] two')})`);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[1].click(); document.querySelector('.focus-description-editor .cm-content').focus()`);
  await press('z',2);
  await press('s',2);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description===${JSON.stringify('- [ ] one\n- [X] two')})`);
  await fillEditor('.focus-description-editor .cm-content', 'Before\n\n| A | B |\n| --- | --- |\n| 1 | 2 |');
  await press('Home',2);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[0].click()`);
  await wait(`document.querySelector('.focus-description-editor .cm-md-table table') !== null`);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-table td')?.textContent`), '1');
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-table td').click()`);
  await wait(`document.querySelector('.focus-description-editor .cm-md-table table') === null`);
  assert.ok(await evaluate(`document.querySelector('.focus-description-editor .cm-content').textContent.includes('| 1 | 2 |')`));
  await press('s',2);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[1].click()`);
  await fillEditor('.focus-description-editor .cm-content', 'Intro\n\n> [!note]- Details\n> Callout body\n>\n> - [ ] nested\n\n$$\nx^2\n$$\n\n```mermaid\ngraph TD\nA --> B\n```');
  await press('Home',2);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[0].click()`);
  await wait(`document.querySelector('.focus-description-editor .cm-md-block .callout') !== null`);
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-block .callout summary').click()`);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-block .callout').open`), true);
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-block .callout input').click()`);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description.includes('> - [x] nested'))`);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-block .callout').open`), true);
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-block [data-markdown-math]').scrollIntoView()`);
  await wait(`document.querySelector('.focus-description-editor .cm-md-block [data-markdown-math] math') !== null`);
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-block [data-markdown-diagram]').scrollIntoView()`);
  await wait(`document.querySelector('.focus-description-editor .cm-md-block [data-markdown-diagram] svg') !== null`);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[1].click()`);
  await fillEditor('.focus-description-editor .cm-content', 'Intro\n\nHeading\n=======\n\n```js\nconst x = 1;\n```\n\n[Reference link][site] and ![Picture](/api/health) with footnote[^note]\n\n[site]: https://example.com\n\n[^note]: Footnote body');
  await press('Home',2);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[0].click()`);
  await wait(`document.querySelector('.focus-description-editor .cm-md-inline a') !== null`);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-block pre code')?.textContent.trim()`), 'const x = 1;');
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-heading')?.textContent`), 'Heading');
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-inline a')?.getAttribute('href')`), 'https://example.com');
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-inline img')?.getAttribute('alt')`), 'Picture');
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-md-footnote a')?.textContent`), '1');
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-footnote a').click()`);
  await wait(`document.getSelection()?.anchorNode?.parentElement?.closest('.cm-line')?.textContent.includes('[^note]: Footnote body')`);
  await press('Home',2);
  await wait(`document.querySelector('.focus-description-editor .cm-md-block .footnotes li')?.textContent.includes('Footnote body')`);
  await evaluate(`document.querySelector('.focus-description-editor .cm-md-block .footnotes a').click()`);
  await wait(`document.getSelection()?.anchorNode?.parentElement?.closest('.cm-line')?.textContent.includes('footnote[^note]')`);
  await evaluate(`document.querySelectorAll('.focus-description-editor .modes button')[1].click()`);
  await fillEditor('.focus-description-editor .cm-content', '[[Meet');
  await wait(`document.querySelector('.focus-description-editor .cm-tooltip-autocomplete')?.textContent.includes('Meet your next task')`);
  await delay(125);
  await press('Enter');
  await wait(`document.querySelector('.focus-description-editor .cm-content')?.textContent===${JSON.stringify(`[[task:${taskId}]]`)}`);
  await fillEditor('.focus-description-editor .cm-content', '`[[Meet`');
  await delay(400);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-tooltip-autocomplete')`), null);
  await press('s',2);
  await wait(`document.querySelector('.focus-description-editor .save-state')?.textContent.includes('Salvo')`);
  await evaluate(`{window.realFocusFetch=window.fetch; window.heldFocusSaves=[]; window.fetch=(input,init)=>{
    if (String(input)==='/api/tasks/${taskId}' && init?.method==='PATCH' && JSON.parse(init.body).description==='A pending') {
      return new Promise((resolve,reject)=>window.heldFocusSaves.push(()=>window.realFocusFetch(input,init).then(resolve,reject)));
    }
    return window.realFocusFetch(input,init);
  };}`);
  await fillEditor('.focus-description-editor .cm-content', 'A pending');
  await press('s',2);
  await wait(`window.heldFocusSaves.length===1`);
  await evaluate(`document.querySelector('.choose-task-toggle').click()`);
  await wait(`Array.from(document.querySelectorAll('.queue-row')).some(row=>row.textContent.includes('Focus race second') && row.querySelector('.queue-action'))`);
  await checkQueueTags();
  await evaluate(`Array.from(document.querySelectorAll('.queue-row')).find(row=>row.textContent.includes('Focus race second')).querySelector('.queue-action').click()`);
  await wait(`document.querySelector('.focus-task-area .task-id')?.textContent.includes('#${raceTaskId}')`);
  await fillEditor('.focus-description-editor .cm-content', 'B notes');
  await press('s',2);
  await wait(`window.realFocusFetch('/api/tasks/${raceTaskId}').then(r=>r.json()).then(t=>t.description==='B notes')`);
  await evaluate(`window.heldFocusSaves[0]()`);
  await wait(`window.realFocusFetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description==='A pending')`);
  assert.equal(await evaluate(`document.querySelector('.focus-description-editor .cm-content').textContent`), 'B notes');
  await evaluate(`window.fetch=window.realFocusFetch`);
  await evaluate(`Array.from(document.querySelectorAll('.queue-row')).find(row=>row.textContent.includes('Meet your next task')).querySelector('.queue-action').click()`);
  await wait(`document.querySelector('.focus-task-area .task-id')?.textContent.includes('#${taskId}')`);
  await wait(`document.querySelector('.focus-description-editor .cm-content')?.textContent === 'A pending'`);
  await fillEditor('.focus-description-editor .cm-content', 'A before debounce');
  await evaluate(`Array.from(document.querySelectorAll('.queue-row')).find(row=>row.textContent.includes('Focus race second')).querySelector('.queue-action').click()`);
  await wait(`document.querySelector('.focus-task-area .task-id')?.textContent.includes('#${raceTaskId}')`);
  await wait(`fetch('/api/tasks/${taskId}').then(r=>r.json()).then(t=>t.description==='A before debounce')`);
  await evaluate(`Array.from(document.querySelectorAll('.queue-row')).find(row=>row.textContent.includes('Meet your next task')).querySelector('.queue-action').click()`);
  await wait(`document.querySelector('.focus-task-area .task-id')?.textContent.includes('#${taskId}')`);
  await wait(`document.querySelector('.focus-description-editor .cm-content')?.textContent === 'A before debounce'`);
  await evaluate(`document.querySelector('.session-scope-heading button').click()`);
  await wait(`document.querySelector('.scope-editor') !== null`);
  await press('Escape');
  await wait(`document.querySelector('.scope-editor') === null`);
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
