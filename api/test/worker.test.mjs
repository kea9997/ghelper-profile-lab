import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import worker, { sha, settings, validateBundle, MAX_BODY_BYTES, MAX_RESPONSE_BYTES } from '../worker.mjs';

const ORIGIN = 'https://ghelper.optiwork.co.kr';
const token = () => Array.from(crypto.getRandomValues(new Uint8Array(32)), x => x.toString(16).padStart(2, '0')).join('');

// Real SQLite schema and SQL, with only the D1 JavaScript surface adapted.
class D1Sqlite {
  constructor() {
    this.sqlite = new DatabaseSync(':memory:');
    this.sqlite.exec(readFileSync(new URL('../schema.sql', import.meta.url), 'utf8'));
  }
  prepare(sql) {
    const database = this;
    const statement = {
      values: [],
      bind(...values) { this.values = values; return this; },
      execute() {
        const prepared = database.sqlite.prepare(sql);
        const results = prepared.all(...this.values).map(row => ({ ...row }));
        return { success: true, results, meta: { changes: database.sqlite.prepare('SELECT changes() AS n').get().n } };
      },
      async first() { return this.execute().results[0] ?? null; },
      async all() { return this.execute(); },
      async run() { return this.execute(); },
    };
    return statement;
  }
  async batch(statements) {
    this.sqlite.exec('BEGIN IMMEDIATE');
    try {
      const results = statements.map(statement => statement.execute());
      this.sqlite.exec('COMMIT');
      return results;
    } catch (error) {
      this.sqlite.exec('ROLLBACK');
      throw error;
    }
  }
  close() { this.sqlite.close(); }
}

async function bundle(model = 'GU605CX') {
  const values = { limit_slow_0: 35, auto_apply_power_0: 1 };
  const hash = await sha(JSON.stringify(Object.fromEntries(Object.entries(values).sort())));
  return {
    schemaVersion: 1, kind: 'ghelper-profile-share', author: '테스터',
    profile: {
      schemaVersion: 1, name: '균형 설정', notes: '',
      hardware: { manufacturer: 'ASUS', model, cpu: 'Intel Core Ultra 9 285H', gpu: ['NVIDIA RTX 5090 Laptop GPU'], ram_gb: 64, bios: '310' },
      ghelperVersion: '0.1', settings: values, settingsHash: hash, activeMode: 0,
    },
    runs: [{ totalScore: 12345, graphicsScore: 13000, cpuScore: 11000, mode: 0, createdAt: '2026-09-24T10:00:00Z', noiseDbA: null, fanRpm: null, notes: '', settingsHash: hash }],
    verification: 'user-reported',
  };
}

function fixture(t) {
  const DB = new D1Sqlite();
  t.after(() => DB.close());
  return { DB, SERVICE_ORIGIN: ORIGIN, RELEASE_URL: 'https://github.com/example/profile-lab/releases/latest' };
}

async function request(env, path, method = 'GET', body, headers = {}) {
  return worker.fetch(new Request(ORIGIN + path, {
    method,
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...headers },
    ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
  }), env);
}

async function create(env, data, extra = {}) {
  const deleteToken = extra.deleteToken || token();
  const key = extra.key || crypto.randomUUID();
  const response = await request(env, '/api/profiles', 'POST', data, {
    'Idempotency-Key': key, 'X-Delete-Token': deleteToken,
    'CF-Connecting-IP': extra.ip || '192.0.2.10', ...extra.headers,
  });
  return { response, value: await response.json(), deleteToken, key };
}

test('upload, list, detail and idempotent deletion preserve public/private boundaries', async t => {
  const env = fixture(t);
  const data = await bundle();
  const made = await create(env, data);
  assert.equal(made.response.status, 201);
  assert.deepEqual(Object.keys(made.value).sort(), ['createdAt', 'id', 'replayed']);
  assert.equal(made.value.replayed, false);
  const detail = await request(env, `/api/profiles/${made.value.id}`);
  assert.equal(detail.status, 200);
  const { post } = await detail.json();
  assert.deepEqual(post.profile, data.profile);
  assert.equal(post.verification, 'user-reported');
  assert.equal(JSON.stringify(post).includes(made.deleteToken), false);
  const receipt = env.DB.sqlite.prepare('SELECT * FROM submission_receipts').get();
  assert.equal(receipt.delete_hash, await sha(made.deleteToken));
  assert.equal(Object.hasOwn(receipt, 'delete_token'), false);
  assert.equal((await (await request(env, '/api/profiles')).json()).posts.length, 1);
  assert.equal((await request(env, `/api/profiles/${made.value.id}`, 'DELETE', { deleteToken: token() })).status, 404);
  assert.equal((await request(env, `/api/profiles/${made.value.id}`, 'DELETE', { deleteToken: [made.deleteToken] })).status, 400);
  assert.equal((await request(env, `/api/profiles/${made.value.id}`, 'DELETE', { deleteToken: made.deleteToken + '\n' })).status, 400);
  for (let i = 0; i < 2; i++) {
    const deleted = await request(env, `/api/profiles/${made.value.id}`, 'DELETE', { deleteToken: made.deleteToken });
    assert.equal(deleted.status, 200);
    assert.deepEqual(await deleted.json(), { deleted: true });
  }
  assert.equal((await request(env, `/api/profiles/${made.value.id}`)).status, 404);
  const retried = await create(env, data, made);
  assert.equal(retried.response.status, 410);
  assert.equal(env.DB.sqlite.prepare('SELECT COUNT(*) AS n FROM profiles').get().n, 0);
});

test('simultaneous idempotency replay creates one post and uses one rate slot', async t => {
  const env = fixture(t);
  const data = await bundle();
  const credentials = { key: crypto.randomUUID(), deleteToken: token() };
  const results = await Promise.all(Array.from({ length: 8 }, () => create(env, data, credentials)));
  assert.equal(results.filter(x => x.response.status === 201).length, 1);
  assert.equal(results.filter(x => x.response.status === 200).length, 7);
  assert.equal(new Set(results.map(x => x.value.id)).size, 1);
  assert.equal(env.DB.sqlite.prepare('SELECT count FROM submission_limits').get().count, 1);
  const reordered = { ...data, profile: { ...data.profile, settings: { auto_apply_power_0: 1, limit_slow_0: 35 } } };
  assert.equal((await create(env, reordered, credentials)).response.status, 200);
  const changed = structuredClone(data); changed.author = '다른 작성자';
  assert.equal((await create(env, changed, credentials)).response.status, 409);
  assert.equal((await create(env, data, { ...credentials, deleteToken: token() })).response.status, 409);
  assert.equal(env.DB.sqlite.prepare('SELECT count FROM submission_limits').get().count, 1);
});

test('atomic hourly limit permits twenty unique posts and replay after exhaustion', async t => {
  const env = fixture(t);
  const data = await bundle();
  const results = await Promise.all(Array.from({ length: 25 }, () => create(env, data)));
  assert.equal(results.filter(x => x.response.status === 201).length, 20);
  assert.equal(results.filter(x => x.response.status === 429).length, 5);
  assert.equal(env.DB.sqlite.prepare('SELECT count FROM submission_limits').get().count, 20);
  assert.equal(env.DB.sqlite.prepare('SELECT COUNT(*) AS n FROM profiles').get().n, 20);
  const first = results.find(x => x.response.status === 201);
  assert.equal((await create(env, data, first)).response.status, 200);
  assert.equal((await create(env, data, { ip: '192.0.2.11' })).response.status, 201);
  assert.ok(Number(results.find(x => x.response.status === 429).response.headers.get('Retry-After')) > 0);
  for (const row of env.DB.sqlite.prepare('SELECT key FROM submission_limits').all()) {
    assert.match(row.key, /^[0-9a-f]{64}$/);
    assert.equal(row.key.includes('192.0.2'), false);
  }
});

test('failed batch rolls back receipts and rate use, allowing retry with same key', async t => {
  const env = fixture(t);
  env.DB.sqlite.exec("CREATE TRIGGER reject_profile BEFORE INSERT ON profiles BEGIN SELECT RAISE(ABORT, 'injected failure'); END");
  const data = await bundle();
  const failed = await create(env, data);
  assert.equal(failed.response.status, 503);
  assert.equal(env.DB.sqlite.prepare('SELECT COUNT(*) AS n FROM submission_receipts').get().n, 0);
  assert.equal(env.DB.sqlite.prepare('SELECT COUNT(*) AS n FROM submission_limits').get().n, 0);
  env.DB.sqlite.exec('DROP TRIGGER reject_profile');
  assert.equal((await create(env, data, failed)).response.status, 201);
});

test('pagination is stable for equal timestamps and bound to exact Unicode model', async t => {
  const env = fixture(t);
  const model = 'GU605CX 한국';
  for (let i = 0; i < 7; i++) await create(env, await bundle(i === 6 ? 'OTHER' : model));
  env.DB.sqlite.exec("UPDATE profiles SET created_at='2026-09-24T12:00:00.000Z'");
  let cursor = null;
  const ids = [];
  do {
    const query = new URLSearchParams({ model, limit: '2', ...(cursor ? { cursor } : {}) });
    const response = await request(env, '/api/profiles?' + query);
    assert.equal(response.status, 200);
    const page = await response.json();
    ids.push(...page.posts.map(x => x.id));
    assert.ok(page.posts.every(x => x.profile.hardware.model === model));
    cursor = page.nextCursor;
    if (cursor) assert.equal((await request(env, '/api/profiles?' + new URLSearchParams({ model: 'OTHER', cursor }))).status, 400);
  } while (cursor);
  assert.equal(ids.length, 6);
  assert.equal(new Set(ids).size, 6);
  assert.deepEqual(ids, [...ids].sort().reverse());
});

test('body and response byte caps hold for multibyte text and full-size pages', async t => {
  const env = fixture(t);
  const data = await bundle();
  const oversized = ' '.repeat(MAX_BODY_BYTES + 1);
  const rejected = await create(env, oversized);
  assert.equal(rejected.response.status, 413);
  assert.equal(env.DB.sqlite.prepare('SELECT COUNT(*) AS n FROM submission_receipts').get().n, 0);
  data.profile.notes = '한'.repeat(1500);
  data.runs = Array.from({ length: 20 }, () => ({ ...data.runs[0], notes: '한'.repeat(1900) }));
  assert.ok(new TextEncoder().encode(JSON.stringify(data)).length < MAX_BODY_BYTES);
  for (let i = 0; i < 31; i++) {
    const made = await create(env, data, { ip: `192.0.2.${i + 1}` });
    assert.equal(made.response.status, 201);
  }
  const response = await request(env, '/api/profiles');
  const bytes = new Uint8Array(await response.arrayBuffer());
  assert.ok(bytes.byteLength <= MAX_RESPONSE_BYTES);
  const page = JSON.parse(new TextDecoder().decode(bytes));
  assert.equal(page.posts.length, 30);
  assert.equal(typeof page.nextCursor, 'string');
});

test('strict validation rejects private fields, unbound scores and unsupported settings', async () => {
  const mutations = [
    x => { x.serialNumber = 'private'; },
    x => { x.profile.localPath = 'C:/private'; },
    x => { x.profile.hardware.uuid = 'private'; },
    x => { x.runs[0].screenshotPath = 'C:/private'; },
    x => { x.profile.settings.power_plan_0 = 'private'; },
    x => { x.profile.settings.gpu_power_0 = 81; },
    x => { x.profile.settings.limit_slow_0 = 35.5; },
    x => { x.profile.settingsHash = '0'.repeat(64); },
    x => { x.runs[0].settingsHash = '0'.repeat(64); },
    x => { x.runs[0].totalScore = 0; },
    x => { x.runs[0].mode = 3; },
    x => { x.runs[0].createdAt = 'not-a-date'; },
    x => { x.profile.activeMode = 3; },
  ];
  for (const mutate of mutations) { const value = await bundle(); mutate(value); await assert.rejects(validateBundle(value)); }
  assert.throws(() => settings({ fan_profile_cpu_0: '1E-28-32-3C-46-50-5A-64-00-0A-14-1E-28-32-3C-65' }));
  assert.throws(() => settings({ fan_profile_cpu_0: '28-1E-32-3C-46-50-5A-64-00-0A-14-1E-28-32-3C-64' }));
  const valid = '1e-28-32-3c-46-50-5a-64-00-0a-14-1e-28-32-3c-64';
  assert.equal(settings({ fan_profile_cpu_0: valid }).fan_profile_cpu_0, valid.toUpperCase());
  const spoofed = await bundle(); spoofed.verification = 'official';
  assert.equal((await validateBundle(spoofed)).verification, 'user-reported');
});

test('HTTP contract rejects arbitrary origins, unsupported content, invalid IDs and queries', async t => {
  const env = fixture(t);
  const health = await request(env, '/api/health', 'GET', undefined, { Origin: ORIGIN });
  assert.equal(health.status, 200);
  assert.equal(health.headers.get('Access-Control-Allow-Origin'), null);
  assert.equal((await request(env, '/api/health', 'GET', undefined, { Origin: 'https://evil.example' })).status, 403);
  assert.equal((await request(env, '/api/profiles', 'OPTIONS')).status, 405);
  assert.equal((await request(env, '/api/profiles/not-an-id')).status, 400);
  assert.equal((await request(env, '/api/profiles/' + crypto.randomUUID())).status, 404);
  for (const query of ['limit=31', 'limit=0', 'limit=-1', 'limit=1&limit=2', 'cursor=invalid', 'unknown=1']) {
    assert.equal((await request(env, '/api/profiles?' + query)).status, 400, query);
  }
  const invalidCursor = btoa(JSON.stringify({ createdAt: '2026-09-24T12:00:00.000Z', id: [crypto.randomUUID()], model: '' })).replace(/=+$/, '');
  assert.equal((await request(env, '/api/profiles?' + new URLSearchParams({ cursor: invalidCursor }))).status, 400);
  assert.equal((await request(env, '/api/profiles', 'POST', await bundle())).status, 400);
  const headers = { 'Idempotency-Key': crypto.randomUUID(), 'X-Delete-Token': token() };
  assert.equal((await request(env, '/api/profiles', 'POST', 'not-json', headers)).status, 400);
  assert.equal((await request(env, '/api/profiles', 'POST', '{}', { ...headers, 'Content-Type': 'text/plain' })).status, 415);
  const missing = await request({ SERVICE_ORIGIN: ORIGIN }, '/api/health');
  assert.equal(missing.status, 503);
  assert.equal(JSON.stringify(await missing.json()).includes('Missing DB'), false);
});

test('public site serves searchable library and read-only assets', async t => {
  const env = fixture(t);
  const response = await request(env, '/');
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.ok(html.includes(env.RELEASE_URL));
  assert.ok(html.includes('id="profile-list"'));
  assert.ok(html.includes('id="search-input"'));
  assert.ok(html.includes('id="references-list"'));
  assert.ok(html.includes('G-Helper 설정'));
  assert.ok(html.includes('/site.js'));
  assert.ok(response.headers.get('Content-Security-Policy').includes("frame-ancestors 'none'"));
  assert.ok(response.headers.get('Content-Security-Policy').includes("script-src 'self'"));
  const script = await request(env, '/site.js');
  assert.equal(script.status, 200);
  assert.match(script.headers.get('Content-Type'), /^application\/javascript/);
  const scriptText = await script.text();
  assert.ok(scriptText.includes("fetch('/api/profiles?"));
  assert.ok(scriptText.includes("fetch('/api/references'"));
  const css = await request(env, '/site.css');
  assert.equal(css.status, 200);
  assert.match(css.headers.get('Content-Type'), /^text\/css/);
  assert.equal((await request({ ...env, RELEASE_URL: 'javascript:alert(1)' }, '/')).status, 503);
});

test('reference catalog keeps official specifications separate from sourced Time Spy reports', async t => {
  const env = fixture(t);
  const response = await request(env, '/api/references');
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.schemaVersion, 2);
  assert.ok(data.entries.length >= 90);
  const official = data.entries.find(entry => entry.id === 'asus-2025-gu605cx-gpu-spec');
  assert.equal(official.gpu, 'RTX 5090');
  assert.match(official.settingsText, /Turbo 100W \/ Manual 110W/);
  assert.equal(official.timeSpy, undefined);
  const official2024 = data.entries.find(entry => entry.id === 'asus-2024-ga403ui-gpu-spec');
  assert.match(official2024.summary, /GPU 최대 전력 90W/);
  assert.doesNotMatch(official2024.summary, /Manual/);
  const measured = data.entries.find(entry => entry.id === 'ga403ui-timespy-balanced-10413');
  assert.equal(measured.timeSpy.total, 10413);
  assert.match(measured.settingsText, /CPU boost disabled/);
  assert.ok(measured.sourceUrl.startsWith('https://www.reddit.com/'));
  assert.ok(data.entries.every(entry => entry.status === 'reference' && entry.sourceUrl.startsWith('https://')));
  assert.equal((await request(env, '/api/references', 'POST', '{}')).status, 405);
});
