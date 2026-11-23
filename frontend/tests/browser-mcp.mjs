import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

const chrome = spawn(process.env.CHROME_BIN, ['--headless=new', '--no-sandbox', '--disable-gpu',
  '--disable-background-networking', '--remote-debugging-port=0',
  `--user-data-dir=${process.env.NEXT_TASK_BROWSER_PROFILE}`, 'about:blank'],
  { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
try {
  let output = '';
  const endpoint = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Chrome did not start: ${output}`)), 30000);
    chrome.stderr.on('data', chunk => {
      output += chunk;
      const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
    chrome.once('error', reject);
    chrome.once('exit', code => reject(new Error(`Chrome exited: ${code}`)));
  });
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  socket.onmessage = event => {
    const item = JSON.parse(event.data);
    if (!item.id) return;
    const call = pending.get(item.id);
    pending.delete(item.id);
    if (item.error) call.reject(new Error(JSON.stringify(item.error))); else call.resolve(item.result);
  };
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  await send('Runtime.enable', {}, sessionId);
  await send('Page.enable', {}, sessionId);
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true }, sessionId);
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  };
  const wait = async expression => {
    for (let attempt = 0; attempt < 150; attempt++) {
      if (await evaluate(expression)) return;
      await delay(50);
    }
    throw new Error(`Timed out: ${expression}; page: ${await evaluate('document.body.innerText')}`);
  };
  await send('Page.navigate', { url: process.env.NEXT_TASK_TEST_URL }, sessionId);
  await wait(`document.querySelector('.login-card input[autocomplete="username"]') !== null`);
  await evaluate(`(() => {
    for (const [selector, value] of [['input[autocomplete="username"]','mcp-browser@example.com'],['#account-password','correct horse']]) {
      const input = document.querySelector(selector);
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    document.querySelector('.login-card form').requestSubmit();
  })()`);
  await wait(`document.body.innerText.includes('Browser fixture')`);
  const body = await evaluate('document.body.innerText');
  assert.match(body, /mcp-browser@example.com/);
  const portuguese = process.env.NEXT_TASK_MCP_LANGUAGE === 'pt-BR';
  assert.match(body, portuguese ? /não foram verificados/ : /not been verified/);
  assert.match(body, portuguese ? /leia suas tarefas/ : /read your tasks/);
  assert.equal(await evaluate('document.body.scrollWidth <= innerWidth + 1'), true);
  const connections = await evaluate(`fetch('/api/settings/mcp').then(response => response.json())`);
  assert.equal(connections.connections.length, 0);
  await evaluate(`location.hash = '#/settings'`);
  await wait(`document.body.innerText.includes(${JSON.stringify(portuguese ? 'Conexões autorizadas' : 'Authorized connections')})`);
  assert.match(await evaluate('document.body.innerText'), portuguese ? /Nenhuma conexão autorizada/ : /No authorized connections/);
  await send('Page.navigate', { url: process.env.NEXT_TASK_TEST_URL }, sessionId);
  await wait(`document.body.innerText.includes('Browser fixture')`);
  const action = process.env.NEXT_TASK_MCP_ALLOW === 'True' ? (portuguese ? 'Permitir' : 'Allow') : (portuguese ? 'Negar' : 'Deny');
  await evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.trim() === ${JSON.stringify(action)}).click()`);
  await delay(500);
  await send('Browser.close');
} finally {
  socket?.close();
  chrome.kill();
}
