'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const ScoreCard = require('../web/score-card.js');

const run = (mode, totalScore, settingsHash = 'current', createdAt = '2026-09-25T07:00:00Z') => ({
  binding: 'captured', status: 'valid', mode, totalScore, settingsHash, createdAt,
  noiseDbA: mode === 1 ? 43.2 : null, fanRpm: mode === 1 ? 4800 : null,
  graphicsScore: totalScore + 500, cpuScore: totalScore - 1000, sourceFile: 'private/path.xml', notes: 'private note',
});

test('score comparison uses the latest valid linked result for each mode', () => {
  const rows = [run(2, 8100), run(0, 10400), run(1, 13000),
    run(1, 18000, 'old', '2026-09-24T07:00:00Z'),
    {...run(0, 20000), binding: 'imported'},
    {...run(2, 21000), status: 'failed'}];
  const data = ScoreCard.build(rows, {model: 'Zephyrus G16', cpu: 'Core Ultra 9', gpu: ['RTX 5090']});
  assert.equal(data.best.run.totalScore, 13000);
  assert.deepEqual(data.modes.map(mode => mode.run.totalScore), [8100, 10400, 13000]);
  assert.equal(ScoreCard.build([run(1, 18000, '')], {}), null);
  assert.equal(ScoreCard.build([{...run(1, 13000), graphicsScore: null}], {}), null);
  assert.equal(ScoreCard.build([{...run(1, 13000), cpuScore: null}], {}), null);
});

test('mode-specific settings hashes do not hide balanced and turbo scores', () => {
  const rows = [run(2, 14000, 'quiet-settings'), run(0, 16000, 'balanced-settings'),
    run(1, 19000, 'turbo-settings')];
  const data = ScoreCard.build(rows, {});
  assert.deepEqual(data.modes.map(mode => mode.run.totalScore), [14000, 16000, 19000]);
  assert.equal(data.mixedSettings, true);
});

test('a new partial comparison preserves older measured modes and ignores unbound records', () => {
  const rows = [run(2, 14000, 'new', '2026-09-26T07:00:00Z'),
    run(0, 16000, 'old'), run(1, 19000, 'old'),
    {...run(1, 22000, 'new', '2026-09-26T08:00:00Z'), binding: 'unbound'},
    {...run(0, 22000, 'new', '2026-09-26T08:00:00Z'), status: 'failed'}];
  const before = structuredClone(rows);
  const data = ScoreCard.build(rows, {});
  assert.deepEqual(data.modes.map(mode => mode.run.totalScore), [14000, 16000, 19000]);
  assert.deepEqual(rows, before);
  assert.deepEqual(ScoreCard.build([rows[0]], {}).modes.map(mode => !!mode.run), [true, false, false]);
});

test('latest scores follow actual time across timezone offsets', () => {
  const older = run(2, 12000, 'old', '2026-09-26T09:00:00+09:00');
  const newer = run(2, 14000, 'new', '2026-09-26T01:00:00Z');
  const invalid = run(2, 22000, 'invalid', 'unknown');
  const data = ScoreCard.build([older, newer, invalid], {});
  assert.equal(data.modes[0].run.totalScore, 14000);
  assert.equal(data.date, newer.createdAt);
  assert.equal(data.mixedSettings, false);
});

test('best mode follows graphics score even when combined score ranks differently', () => {
  const data = ScoreCard.build([
    {...run(0, 18000), graphicsScore: 15500},
    {...run(1, 16000), graphicsScore: 17000},
  ], {});
  assert.equal(data.best.id, 1);
  assert.equal(data.best.run.graphicsScore, 17000);
});

test('manual score can be exported and stays visibly marked', () => {
  const data = ScoreCard.build([{...run(1, 17783), binding: 'manual'}], {});
  assert.equal(data.best.run.totalScore, 17783);
  const drawn = [];
  const ctx = {
    fillText(value) {drawn.push(String(value));}, fillRect() {}, beginPath() {}, roundRect() {},
    fill() {}, arc() {}, save() {}, restore() {},
    measureText(value) {return {width: String(value).length * 14};},
    createLinearGradient() {return {addColorStop() {}};},
  };
  ScoreCard.draw(ctx, data);
  assert.ok(drawn.some(value => value.includes('직접 연결한 점수 포함')));
  assert.ok(drawn.includes('18,283'));
  assert.ok(drawn.includes('CPU 점수 16,783'));
  assert.ok(!drawn.includes('17,783'));
});

test('PNG has expected dimensions and excludes private result fields', async () => {
  const drawn = [];
  const ctx = {
    fillText(value) {drawn.push(String(value));}, fillRect() {}, beginPath() {}, roundRect() {},
    fill() {}, arc() {}, save() {}, restore() {},
    measureText(value) {return {width: String(value).length * 14};},
    createLinearGradient() {return {addColorStop() {}};},
  };
  const canvas = {getContext() {return ctx;}, toBlob(resolve, type) {assert.equal(type, 'image/png'); resolve({type});}};
  const image = await ScoreCard.png([run(1, 13000)], {model: 'GU605CX', cpu: 'Core Ultra 9', gpu: ['RTX 5090']}, () => canvas);
  assert.equal(canvas.width, 1200); assert.equal(canvas.height, 675);
  assert.equal(image.fileName, 'TimeSpy-GU605CX.png');
  assert.equal(image.blob.type, 'image/png');
  assert.ok(drawn.includes('13,500'));
  assert.ok(drawn.includes('CPU 점수 12,000'));
  assert.ok(!drawn.includes('13,000'));
  assert.ok(drawn.some(value => value.includes('43.2 dBA')));
  assert.ok(!drawn.join(' ').includes('private'));
  assert.ok(!drawn.join(' ').includes('current'));
  assert.ok(drawn.some(value => value.includes('모드별 마지막 Time Spy 점수')));
  assert.ok(!drawn.some(value => value.includes('같은 G-Helper 설정으로 측정한')));
});

test('PNG creation reports absent captures and encoder failures', async () => {
  await assert.rejects(ScoreCard.png([], {}), /먼저 Time Spy/);
  const ctx = {
    fillText() {}, fillRect() {}, beginPath() {}, roundRect() {}, fill() {}, arc() {}, save() {}, restore() {},
    measureText(value) {return {width: String(value).length * 14};},
    createLinearGradient() {return {addColorStop() {}};},
  };
  const canvas = {getContext() {return ctx;}, toBlob(resolve) {resolve(null);}};
  await assert.rejects(ScoreCard.png([run(1, 12000)], {}, () => canvas), /이미지를 만들지 못했습니다/);
});
