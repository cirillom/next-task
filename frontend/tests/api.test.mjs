import assert from 'node:assert/strict';
import test from 'node:test';
import { get } from 'svelte/store';
import { sourceModule } from './sourceModule.mjs';
const { request, ApiError, api } = await import(sourceModule(new URL('../src/lib/api/client.ts', import.meta.url)));
const { setLanguage, text } = await import(sourceModule(new URL('../src/lib/i18n/index.ts', import.meta.url)));

for (const [body, expected] of [
  [{detail: 'opaque', code: 'api.waitOneMinuteBeforeSendingAnotherEmail', params: {}}, 'Aguarde um minuto antes de enviar outro e-mail'],
  [{detail: [{code: 'validation.minLength', params: {count: 10}, msg: 'English server detail'}]}, 'Use pelo menos 10 caracteres.'],
  [{detail: '<script>unsafe exception</script>'}, 'A solicitação falhou (422)']
]) {
  test(`API failures use stable codes: ${expected}`, async (t) => {
    setLanguage('pt-BR', false);
    t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(body), {status: 422}));
    await assert.rejects(request('/api/auth/email'), (error) =>
      error instanceof ApiError && error.status === 422 && get(text)(error.translation) === expected
    );
  });
}
test('saved errors and success notices translate again after changing language; user content stays intact', async (t) => {
  setLanguage('en', false);
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({message: 'Password changed', code: 'api.passwordChanged', params: {}})));
  const result = await request('/api/auth/change-password');
  assert.equal(get(text)(result.message), 'Password changed');
  setLanguage('pt-BR', false);
  assert.equal(get(text)(result.message), 'Senha alterada');
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify([{title: 'ui.app.tasks', description: 'My words'}])));
  assert.deepEqual(await request('/api/tasks'), [{title: 'ui.app.tasks', description: 'My words'}]);
});
test('invitation acceptance sends the language selected before login', async (t) => {
  setLanguage('pt-BR', false);
  t.mock.method(globalThis, 'fetch', async (_path, init) => {
    assert.equal(JSON.parse(init.body).language, 'pt-BR');
    assert.equal(init.credentials, 'same-origin');
    return new Response('{}');
  });
  await api.acceptInvitation('opaque', 'Test', 'correct horse');
});
