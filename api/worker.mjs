// Dependency-free Worker ES module. Stored scores remain user reports.
import { timingSafeEqual } from 'node:crypto';

export const MAX_BODY_BYTES = 128 * 1024;
export const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
export const MAX_PAGE_SIZE = 30;
export const SUBMISSIONS_PER_HOUR = 20;
const encoder = new TextEncoder();
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DELETE_TOKEN = /^[0-9a-f]{64}$/;
const DEFAULT_ORIGIN = 'https://ghelper.optiwork.co.kr';

class HttpError extends Error {
  constructor(status, code, message, headers = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.headers = headers;
  }
}

function fail(status, code, message, headers) {
  throw new HttpError(status, code, message, headers);
}

function json(value, status = 200, extraHeaders = {}) {
  const body = JSON.stringify(value);
  if (encoder.encode(body).byteLength > MAX_RESPONSE_BYTES) {
    fail(503, 'response_too_large', '자료실 응답 크기 제한을 초과했습니다.');
  }
  return new Response(body, {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      ...extraHeaders,
    },
  });
}

function serviceOrigin(env) {
  const value = env.SERVICE_ORIGIN || DEFAULT_ORIGIN;
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.origin !== value) throw new Error('Invalid SERVICE_ORIGIN');
  return value;
}

function checkOrigin(request, env) {
  const origin = request.headers.get('Origin');
  if (origin !== null && origin !== serviceOrigin(env)) {
    fail(403, 'origin_not_allowed', '허용되지 않은 출처입니다.');
  }
}

export async function readJson(request, maximum = MAX_BODY_BYTES) {
  const sizeMessage = `JSON 본문은 ${maximum / 1024}KiB 이하여야 합니다.`;
  const contentType = (request.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (contentType !== 'application/json') fail(415, 'json_required', 'application/json 요청이 필요합니다.');
  const contentLength = request.headers.get('Content-Length');
  if (contentLength !== null) {
    if (!/^\d+$/.test(contentLength)) fail(400, 'invalid_length', '요청 길이가 올바르지 않습니다.');
    if (Number(contentLength) > maximum) fail(413, 'body_too_large', sizeMessage);
  }
  if (!request.body) fail(400, 'invalid_json', 'JSON 본문이 필요합니다.');
  const reader = request.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let byteCount = 0;
  let source = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      byteCount += value.byteLength;
      if (byteCount > maximum) {
        await reader.cancel();
        fail(413, 'body_too_large', sizeMessage);
      }
      source += decoder.decode(value, { stream: true });
    }
    source += decoder.decode();
  } catch (error) {
    if (error instanceof HttpError) throw error;
    fail(400, 'invalid_json', 'UTF-8 JSON 본문을 확인하세요.');
  } finally {
    reader.releaseLock();
  }
  try { return JSON.parse(source); }
  catch { fail(400, 'invalid_json', 'JSON 형식이 올바르지 않습니다.'); }
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  }
  return value;
}

function equalHash(left, right) {
  return typeof left === 'string' && typeof right === 'string' &&
    left.length === 64 && right.length === 64 &&
    timingSafeEqual(encoder.encode(left), encoder.encode(right));
}

function validId(id) {
  if (typeof id !== 'string' || id.length !== 36 || !UUID.test(id)) fail(400, 'invalid_id', 'UUID 형식의 게시물 ID가 필요합니다.');
  return id;
}

const PRODUCT_FAMILIES = [
      { ids: ['GU605CX', 'GU605CW', 'GU605CR', 'GU605CM'], family: 'G16', year: '2025' },
  { ids: ['GU605MI', 'GU605MY', 'GU605MZ'], family: 'G16', year: '2024' },
  { ids: ['GA403UI'], family: 'G14', year: '2024' },
  { ids: ['GZ302EA'], family: 'Z13', year: '2025' },
];

function searchQuery(value) {
  if (typeof value !== 'string' || value.length > 160 || value.includes('\0')) {
    fail(400, 'invalid_query', '검색어를 확인하세요.');
  }
  const normalized = value.normalize('NFKC').toLocaleLowerCase('ko-KR')
    .replace(/\b(rtx|gtx)(?=\d)/gi, '$1 ').replace(/(?<=\d)(?=gb\b)/gi, ' ')
    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  if ([...normalized].length > 160) fail(400, 'invalid_query', '검색어를 확인하세요.');
  const tokens = normalized.split(/\s+/).filter(Boolean);
  if (tokens.length > 12 || tokens.some(token => [...token].length > 40)) {
    fail(400, 'invalid_query', '검색어는 12개 단어까지 입력할 수 있습니다.');
  }

  const words = new Set(tokens);
  const models = [];
  const searchable = [];
  const requestedYear = tokens.find(token => /^20\d{2}$/.test(token));
  for (const item of PRODUCT_FAMILIES) {
    const familyMatch = item.family === 'G16'
      ? (words.has('g16') && (!requestedYear || words.has(item.year)))
      : item.family === 'G14'
        ? (words.has('g14') && (!requestedYear || words.has(item.year)))
        : ((words.has('z13') || words.has('flow') || words.has('플로우')) && (!requestedYear || words.has(item.year)));
    if (familyMatch) {
      models.push(...item.ids);
      for (const word of [item.family.toLowerCase(), item.year, 'zephyrus', '제피러스', '제피루스', 'rog', 'asus', 'flow', '플로우']) words.delete(word);
    }
  }
  for (const item of PRODUCT_FAMILIES) {
    const matches = item.ids.filter(model => [...words].includes(model.toLowerCase()));
    if (matches.length) {
      models.push(...matches);
      for (const model of matches) words.delete(model.toLowerCase());
      if (requestedYear === item.year) words.delete(item.year);
    }
  }
  for (const word of words) {
    if (/^rtx\d{4}(?:ti)?$/.test(word)) {
      searchable.push(word.startsWith('rtx') ? 'rtx' : word.slice(0, 3), word.replace(/^rtx/, ''));
    } else searchable.push(word);
  }
  const gpuToken = searchable.some(token => /^(?:rtx|gtx)$/.test(token)) &&
    searchable.some(token => /^\d{4}(?:ti)?$/.test(token));
  const explicitModels = models.length && gpuToken ? models : [];
  return { normalized, tokens: [...new Set(searchable)], models: [...new Set(models)], explicitModels: [...new Set(explicitModels)] };
}

function encodeCursor(row, model, query) {
  const bytes = encoder.encode(JSON.stringify({ createdAt: row.created_at, id: row.id, model, query }));
  return btoa(String.fromCharCode(...bytes))
    .replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

function decodeCursor(value, model, query) {
  if (!value || value.length > 1600 || !/^[A-Za-z0-9_-]+$/.test(value)) {
    fail(400, 'invalid_cursor', '목록 커서가 올바르지 않습니다.');
  }
  try {
    const binary = atob(value.replaceAll('-', '+').replaceAll('_', '/'));
    const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
    const decoded = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!decoded || Object.keys(decoded).sort().join(',') !== 'createdAt,id,model,query' ||
        typeof decoded.id !== 'string' || decoded.id.length !== 36 || !UUID.test(decoded.id) || decoded.model !== model || decoded.query !== query ||
        typeof decoded.createdAt !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(decoded.createdAt) ||
        !Number.isFinite(Date.parse(decoded.createdAt))) throw new Error('Invalid cursor');
    return decoded;
    } catch { fail(400, 'invalid_cursor', '목록 커서와 검색 조건을 확인하세요.'); }
}

function postFromRow(row) {
  if (!row || typeof row.payload !== 'string' || encoder.encode(row.payload).byteLength > MAX_BODY_BYTES) {
    throw new Error('Invalid stored payload');
  }
  return { ...JSON.parse(row.payload), id: row.id, createdAt: row.created_at };
}

async function listProfiles(url, db) {
  for (const key of url.searchParams.keys()) {
    if (!['model', 'cursor', 'limit', 'q'].includes(key) || url.searchParams.getAll(key).length !== 1) {
      fail(400, 'invalid_query', '목록 검색 조건을 확인하세요.');
    }
  }
  const model = (url.searchParams.get('model') || '').trim();
  if (model.length > 200 || model.includes('\0')) fail(400, 'invalid_model', '모델 필터를 확인하세요.');
  const query = searchQuery(url.searchParams.get('q') || '');
  const rawLimit = url.searchParams.get('limit') ?? String(MAX_PAGE_SIZE);
  if (!/^[1-9]\d*$/.test(rawLimit) || Number(rawLimit) > MAX_PAGE_SIZE) {
    fail(400, 'invalid_limit', '목록 크기는 1~30이어야 합니다.');
  }
  const limit = Number(rawLimit);
  const cursor = url.searchParams.has('cursor') ? decodeCursor(url.searchParams.get('cursor'), model, query.normalized) : null;
  const clauses = [];
  const parameters = [];
  if (model) { clauses.push('model = ?'); parameters.push(model); }
  const searchable = [
    'model', "lower(model) || ' ' || json_extract(payload, '$.profile.hardware.model)", 'author', "json_extract(payload, '$.profile.name')",
    "json_extract(payload, '$.profile.notes')", "json_extract(payload, '$.profile.hardware.cpu')",
    "CAST(json_extract(payload, '$.profile.hardware.gpu') AS TEXT)",
    "CAST(CAST(json_extract(payload, '$.profile.hardware.ram_gb') AS INTEGER) AS TEXT) || 'gb'",
  ];
  for (const word of query.tokens) {
    clauses.push(`(${searchable.map(column => `lower(${column}) LIKE ?`).join(' OR ')})`);
    parameters.push(...searchable.map(() => `%${word}%`));
  }
  if (query.explicitModels.length) {
    clauses.push(`model IN (${query.explicitModels.map(() => '?').join(',')})`);
    parameters.push(...query.explicitModels);
  } else if (query.models.length) {
    clauses.push(`model IN (${query.models.map(() => '?').join(',')})`);
    parameters.push(...query.models);
  }
  if (cursor) {
    clauses.push('(created_at < ? OR (created_at = ? AND id < ?))');
    parameters.push(cursor.createdAt, cursor.createdAt, cursor.id);
  }
  const where = clauses.length ? 'WHERE ' + clauses.join(' AND ') : '';
  const result = await db.prepare(`SELECT id, created_at, payload FROM profiles ${where}
    ORDER BY created_at DESC, id DESC LIMIT ?`).bind(...parameters, limit + 1).all();
  const page = result.results.slice(0, limit);
  return json({
    posts: page.map(postFromRow),
    nextCursor: result.results.length > limit ? encodeCursor(page[page.length - 1], model, query.normalized) : null,
  });
}

function replayResponse(receipt, payloadHash, deleteHash, candidateId) {
  if (!equalHash(receipt.payload_hash, payloadHash) || !equalHash(receipt.delete_hash, deleteHash)) {
    fail(409, 'idempotency_conflict', '같은 요청 키에 다른 파일이나 삭제 키를 사용할 수 없습니다.');
  }
  if (receipt.deleted_at !== null) fail(410, 'already_deleted', '이미 삭제된 게시 요청입니다. 새 게시에는 새 요청 키가 필요합니다.');
  const replayed = receipt.profile_id !== candidateId;
  return json({ id: receipt.profile_id, createdAt: receipt.created_at, replayed }, replayed ? 200 : 201);
}

async function createProfile(request, db) {
  const key = request.headers.get('Idempotency-Key') || '';
  const deleteToken = request.headers.get('X-Delete-Token') || '';
  if (key.length !== 36 || !UUID.test(key)) fail(400, 'idempotency_key_required', 'UUID 형식의 Idempotency-Key가 필요합니다.');
  if (deleteToken.length !== 64 || !DELETE_TOKEN.test(deleteToken)) fail(400, 'delete_token_required', '32바이트 소문자 hex 삭제 키가 필요합니다.');
  const input = await readJson(request);
  let bundle;
  try { bundle = await validateBundle(input); }
  catch (error) { fail(400, 'invalid_bundle', error.message); }
  const payload = JSON.stringify(canonical(bundle));
  const payloadBytes = encoder.encode(payload).byteLength;
  if (payloadBytes > MAX_BODY_BYTES) fail(413, 'body_too_large', '정규화된 공유 파일이 128KiB를 초과합니다.');
  const [payloadHash, deleteHash] = await Promise.all([sha(payload), sha(deleteToken)]);
  const previous = await db.prepare('SELECT * FROM submission_receipts WHERE idempotency_key = ?').bind(key).first();
  if (previous) return replayResponse(previous, payloadHash, deleteHash, null);

  const now = Date.now();
  const hour = Math.floor(now / 3600000);
  // Only this hourly hash is stored. CF supplies this header in production.
  const rateKey = await sha(`${hour}:${request.headers.get('CF-Connecting-IP') || 'shared'}`);
  const id = crypto.randomUUID();
  const createdAt = new Date(now).toISOString();
  const results = await db.batch([
    db.prepare('DELETE FROM submission_limits WHERE expires_at <= ?').bind(Math.floor(now / 1000)),
    db.prepare(`INSERT INTO submission_receipts
      (idempotency_key, profile_id, payload_hash, delete_hash, created_at, deleted_at)
      SELECT ?, ?, ?, ?, ?, NULL
      WHERE NOT EXISTS (SELECT 1 FROM submission_receipts WHERE idempotency_key = ?)
        AND COALESCE((SELECT count FROM submission_limits WHERE key = ?), 0) < ?
      ON CONFLICT(idempotency_key) DO NOTHING`)
      .bind(key, id, payloadHash, deleteHash, createdAt, key, rateKey, SUBMISSIONS_PER_HOUR),
    db.prepare(`INSERT INTO profiles (id, created_at, author, model, payload, payload_bytes)
      SELECT profile_id, created_at, ?, ?, ?, ? FROM submission_receipts WHERE profile_id = ?`)
      .bind(bundle.author, bundle.profile.hardware.model, payload, payloadBytes, id),
    db.prepare(`INSERT INTO submission_limits (key, count, expires_at)
      SELECT ?, 1, ? WHERE EXISTS (SELECT 1 FROM submission_receipts WHERE profile_id = ?)
      ON CONFLICT(key) DO UPDATE SET count = count + 1`)
      .bind(rateKey, (hour + 2) * 3600, id),
    db.prepare('SELECT * FROM submission_receipts WHERE idempotency_key = ?').bind(key),
  ]);
  const receipt = results[4].results[0];
  if (!receipt) {
    const seconds = Math.max(1, Math.ceil(((hour + 1) * 3600000 - now) / 1000));
    fail(429, 'rate_limited', '시간당 게시 한도 20건을 초과했습니다.', { 'Retry-After': String(seconds) });
  }
  return replayResponse(receipt, payloadHash, deleteHash, id);
}

async function deleteProfile(request, id, db) {
  const body = await readJson(request, 1024);
  if (!body || typeof body !== 'object' || Array.isArray(body) ||
      Object.keys(body).length !== 1 || typeof body.deleteToken !== 'string' ||
      body.deleteToken.length !== 64 || !DELETE_TOKEN.test(body.deleteToken)) {
    fail(400, 'invalid_delete_token', '삭제 키만 포함한 JSON 본문이 필요합니다.');
  }
  const deleteHash = await sha(body.deleteToken);
  const results = await db.batch([
    db.prepare(`DELETE FROM profiles WHERE id = ? AND EXISTS (
      SELECT 1 FROM submission_receipts WHERE profile_id = ? AND delete_hash = ?)`)
      .bind(id, id, deleteHash),
    db.prepare(`UPDATE submission_receipts SET deleted_at = COALESCE(deleted_at, ?)
      WHERE profile_id = ? AND delete_hash = ?`)
      .bind(new Date().toISOString(), id, deleteHash),
    db.prepare('SELECT profile_id FROM submission_receipts WHERE profile_id = ? AND delete_hash = ?')
      .bind(id, deleteHash),
  ]);
  if (!results[2].results.length) fail(404, 'not_found', '게시물 또는 삭제 키가 일치하지 않습니다.');
  return json({ deleted: true });
}

function landing(env) {
  let release = null;
  if (env.RELEASE_URL) {
    const url = new URL(env.RELEASE_URL);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com' || url.username || url.password) {
      throw new Error('RELEASE_URL must be an HTTPS GitHub release URL');
    }
    release = url.href.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
  }
  return new Response(`<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>G-Helper Profile Lab 자료실</title><style>body{font:18px/1.7 system-ui;max-width:660px;margin:12vh auto;padding:24px;color:#eaf0ff;background:#101522}a{color:#94c9ff}small{color:#b0bdd4}</style><main><h1>G-Helper Profile Lab</h1><p>프리셋 자료실은 Windows 앱에서 사용할 수 있습니다.</p>${release ? `<p><a href="${release}" rel="noopener noreferrer">GitHub에서 Windows 앱 받기</a></p>` : '<p>앱 다운로드 링크가 아직 설정되지 않았습니다.</p>'}<small>게시된 설정과 점수는 사용자가 제공한 자료입니다.</small></main></html>`, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    },
  });
}

export default {
  async fetch(request, env) {
    try {
      checkOrigin(request, env);
      const url = new URL(request.url);
      const path = url.pathname;
      if (path === '/' && request.method === 'GET') return landing(env);
      const known = path === '/api/health' || path === '/api/profiles' || path.startsWith('/api/profiles/');
      if (!known) fail(404, 'not_found', '요청한 주소가 없습니다.');
      if (path === '/api/health') {
        if (request.method !== 'GET') fail(405, 'method_not_allowed', 'GET 요청만 지원합니다.', { Allow: 'GET' });
        if (!env.DB) throw new Error('Missing DB binding');
        await env.DB.prepare('SELECT 1 FROM profiles LIMIT 1').all();
        return json({ ok: true, service: 'ghelper-profile-api', schemaVersion: 1 });
      }
      if (path === '/api/profiles') {
        if (request.method === 'GET') return await listProfiles(url, env.DB);
        if (request.method === 'POST') return await createProfile(request, env.DB);
        fail(405, 'method_not_allowed', 'GET 또는 POST 요청만 지원합니다.', { Allow: 'GET, POST' });
      }
      const id = validId(path.slice('/api/profiles/'.length));
      if (request.method === 'GET') {
        const row = await env.DB.prepare('SELECT id, created_at, payload FROM profiles WHERE id = ?').bind(id).first();
        if (!row) fail(404, 'not_found', '게시물을 찾을 수 없습니다.');
        return json({ post: postFromRow(row) });
      }
      if (request.method === 'DELETE') return await deleteProfile(request, id, env.DB);
      fail(405, 'method_not_allowed', 'GET 또는 DELETE 요청만 지원합니다.', { Allow: 'GET, DELETE' });
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message, code: error.code }, error.status, error.headers);
      // Do not log request bodies, IPs, deletion tokens or database error strings.
      console.error(JSON.stringify({ event: 'profile_api_unavailable' }));
      return json({ error: '자료실에 연결하지 못했습니다. 잠시 후 다시 시도하세요.', code: 'service_unavailable' }, 503);
    }
  },
};

// ProfileLibrary validation — dependency-free ES module for Cloudflare Worker.
// settingsHash integrity is untrusted user-reported consistency, not authentication.

export const ranges = {
  limit_total: [0, 150],
  limit_slow: [0, 150],
  limit_fast: [0, 150],
  limit_cpu: [0, 150],
  auto_apply: [0, 1],
  auto_apply_power: [0, 1],
  auto_boost: [0, 6],
  performance: [0, 4],
  gpu_temp: [60, 87],
  gpu_power: [0, 80],
  gpu_boost: [0, 25],
  gpu_core: [-500, 250],
  gpu_memory: [-500, 2000],
  gpu_clock_limit: [0, 4000]
};

function object(x) {
  if (!x || typeof x !== 'object' || Array.isArray(x)) {
    throw new Error('객체 형식이 올바르지 않습니다.');
  }
  return x;
}

function fields(x, keys) {
  object(x);
  if (Object.keys(x).some((k) => !keys.includes(k))) {
    throw new Error(
      '공유할 수 없는 정보가 포함되어 있습니다. 프로그램에서 공개 공유 파일을 다시 만드세요.'
    );
  }
}

function text(x, max) {
  if (typeof x !== 'string' || x.length > max || x.includes('\0')) {
    throw new Error('텍스트 형식 또는 길이를 확인하세요.');
  }
  return x.trim();
}

function number(x, min, max, nullable = false) {
  if (x === null && nullable) return null;
  if (typeof x !== 'number' || !Number.isFinite(x) || x < min || x > max) {
    throw new Error('숫자 범위를 확인하세요.');
  }
  return x;
}

export async function sha(value) {
  const bytes = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value)
  );
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

const FAN_KEY = /^fan_profile_(cpu|gpu|mid)_[012]$/;
const RANGE_KEY = /^(.+)_[012]$/;
const FAN_HEX = /^[0-9a-f]{2}(-[0-9a-f]{2}){15}$/i;

export function settings(x) {
  object(x);
  const entries = Object.entries(x);
  if (!entries.length || entries.length > 120) {
    throw new Error('설정 항목 수를 확인하세요.');
  }

  const out = {};
  for (const [k, v] of entries) {
    if (FAN_KEY.test(k)) {
      if (typeof v !== 'string' || !FAN_HEX.test(v)) {
        throw new Error('팬 곡선 형식 오류');
      }
      const a = v.split('-').map((part) => parseInt(part, 16));
      if (a.some((v) => v > 100)) {
        throw new Error('팬 곡선 범위·순서 오류');
      }
      if (a.some((v, i) => i > 0 && i !== 8 && v < a[i - 1])) {
        throw new Error('팬 곡선 범위·순서 오류');
      }
      out[k] = v.toUpperCase();
      continue;
    }

    const m = RANGE_KEY.exec(k);
    if (m && Object.hasOwn(ranges, m[1])) {
      const [lo, hi] = ranges[m[1]];
      if (!Number.isInteger(v)) {
        throw new Error('설정은 정수여야 합니다.');
      }
      out[k] = number(v, lo, hi);
      continue;
    }

    throw new Error('허용하지 않는 설정: ' + k);
  }
  return out;
}

export async function validateBundle(input) {
  fields(input, [
    'schemaVersion',
    'kind',
    'author',
    'profile',
    'runs',
    'verification'
  ]);

  if (input.schemaVersion !== 1 || input.kind !== 'ghelper-profile-share') {
    throw new Error('지원하지 않는 공유 파일입니다.');
  }

  const p = object(input.profile);
  fields(p, [
    'schemaVersion',
    'name',
    'notes',
    'hardware',
    'ghelperVersion',
    'settings',
    'settingsHash',
    'activeMode'
  ]);

  if (p.schemaVersion !== 1) {
    throw new Error('프리셋 버전 오류');
  }

  const h = object(p.hardware);
  fields(h, ['manufacturer', 'model', 'cpu', 'gpu', 'ram_gb', 'bios']);

  if (!Array.isArray(h.gpu) || !h.gpu.length || h.gpu.length > 6) {
    throw new Error('GPU 정보를 확인하세요.');
  }

  const hardware = {
    manufacturer: text(h.manufacturer, 200),
    model: text(h.model, 200),
    cpu: text(h.cpu, 200),
    gpu: h.gpu.map((g) => text(g, 200)),
    ram_gb: number(h.ram_gb, 0.1, 2048, true),
    bios: text(h.bios, 200)
  };

  if (!hardware.model || !hardware.cpu) {
    throw new Error('모델과 CPU가 필요합니다.');
  }

  const values = settings(p.settings);
  const sorted = Object.fromEntries(
    Object.entries(values).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
  );
  const hash = await sha(JSON.stringify(sorted));

  if (p.settingsHash !== hash) {
    throw new Error('설정 해시가 일치하지 않습니다.');
  }

  if (p.activeMode !== null && ![0, 1, 2].includes(p.activeMode)) {
    throw new Error('기본 성능 모드만 지원합니다.');
  }

  if (!Array.isArray(input.runs) || input.runs.length > 20) {
    throw new Error('결과는 최대 20개까지 첨부할 수 있습니다.');
  }

  const runs = input.runs.map((r) => {
    fields(r, [
      'totalScore',
      'graphicsScore',
      'cpuScore',
      'mode',
      'createdAt',
      'noiseDbA',
      'fanRpm',
      'notes',
      'settingsHash'
    ]);

    if (r.settingsHash !== hash || ![0, 1, 2].includes(r.mode)) {
      throw new Error('결과와 설정이 연결되지 않았습니다.');
    }

    const createdAt = text(r.createdAt, 80);
    if (!Number.isFinite(Date.parse(createdAt))) {
      throw new Error('날짜 형식 오류');
    }

    const score = (v) => {
      if (!Number.isInteger(v)) {
        throw new Error('점수는 정수여야 합니다.');
      }
      return number(v, 1, 1000000);
    };

    return {
      totalScore: score(r.totalScore),
      graphicsScore: score(r.graphicsScore),
      cpuScore: score(r.cpuScore),
      mode: r.mode,
      createdAt,
      noiseDbA: number(r.noiseDbA, 0, 140, true),
      fanRpm: number(r.fanRpm, 0, 20000, true),
      notes: text(r.notes, 2000),
      settingsHash: hash
    };
  });

  return {
    schemaVersion: 1,
    kind: 'ghelper-profile-share',
    author: text(input.author, 40) || '익명',
    profile: {
      schemaVersion: 1,
      name: text(p.name, 80) || '공유 설정',
      notes: text(p.notes, 2000),
      hardware,
      ghelperVersion: text(p.ghelperVersion, 80),
      settings: values,
      settingsHash: hash,
      activeMode: p.activeMode
    },
    runs,
    verification: 'user-reported'
  };
}
