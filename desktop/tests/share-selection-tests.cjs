'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {plan} = require('../web/share-selection.js');
const hardware = {model: 'Test laptop', cpu: 'Test CPU', gpu: ['Test GPU'], bios: '1', ram_gb: 32};
const profiles = [2, 0, 1].map(mode => ({id: 'p' + mode, origin: 'local', hardware, settingsHash: 'hash' + mode,
  settings: {['limit_total_' + mode]: 25 + mode}, createdAt: '2026-09-26T00:00:00Z'}));
const rows = [2, 0, 1].map(mode => ({id: 'r' + mode, profileId: 'p' + mode, settingsHash: 'hash' + mode,
  mode, binding: 'captured', status: 'valid', graphicsScore: 14000 + mode, cpuScore: 8000 + mode, createdAt: '2026-09-26T00:10:00Z'}));

test('three mode-specific captures and scores are selected automatically without matching a global hash', () => {
  const data = plan(profiles, rows, profiles[0]);
  assert.deepEqual(data.map(m => m.profile.id), ['p2', 'p0', 'p1']);
  assert.deepEqual(data.map(m => m.run.id), ['r2', 'r0', 'r1']);
});
test('unbound, failed, missing-score and foreign-machine runs never become automatic shares', () => {
  const bad = [{...rows[0], binding: 'unbound'}, {...rows[1], status: 'failed'}, {...rows[2], cpuScore: null}];
  const foreign = {...profiles[2], id: 'foreign', hardware: {...hardware, gpu: ['Other GPU']}};
  const result = plan([...profiles, foreign], [...bad, {...rows[2], profileId: 'foreign'}], profiles[0]);
  assert.deepEqual(result.map(m => m.run), [null, null, null]);
  assert.deepEqual(result.map(m => m.profile.id), ['p2', 'p2', 'p2']);
});
test('a saved-setting override replaces the score selection and does not relabel an incompatible score', () => {
  const changed = {...profiles[1], id: 'changed', settingsHash: 'changed'};
  const data = plan([...profiles, changed], rows, profiles[0], {0: 'changed'});
  assert.equal(data[1].profile.id, 'changed');
  assert.equal(data[1].run, null);
  assert.equal(data[2].run.id, 'r1');
});
test('manually linked scores remain tied to their exact saved profile', () => {
  const copy = {...profiles[2], id: 'copy'};
  const manual = {...rows[2], binding: 'manual'};
  assert.equal(plan([...profiles, copy], [manual], profiles[0])[2].run.id, 'r1');
  assert.equal(plan([...profiles, copy], [manual], profiles[0], {1: 'copy'})[2].run, null);
});
test('latest results use absolute time and inputs remain unchanged', () => {
  const original = structuredClone({profiles, rows});
  const earlier = {...rows[0], id: 'earlier', createdAt: '2026-09-26T09:00:00+09:00'};
  const later = {...rows[0], id: 'later', createdAt: '2026-09-26T01:00:00Z'};
  assert.equal(plan(profiles, [earlier, later], profiles[0])[0].run.id, 'later');
  plan(profiles, rows, profiles[0]);
  assert.deepEqual({profiles, rows}, original);
  assert.deepEqual(plan([], [], null).map(m => m.profile), [null, null, null]);
});
