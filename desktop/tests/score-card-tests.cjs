'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const ScoreCard = require('../web/score-card.js');

const run = (mode, totalScore, settingsHash = 'current', createdAt = '2026-09-25T07:00:00Z') => ({
  binding: 'captured', status: 'valid', mode, totalScore, settingsHash, createdAt,
  noiseDbA: mode === 1 ? 43.2 : null, fanRpm: mode === 1 ? 4800 : null,
  graphicsScore: 12000, cpuScore: 8000, sourceFile: 'private/path.xml', notes: 'private note',
});

test('score image uses only captured valid results from the latest settings', () => {
  const rows = [run(2, 8100), run(0, 10400), run(1, 13000),
    run(1, 18000, 'old', '2026-09-24T07:00:00Z'),
    {...run(0, 20000), binding: 'imported'},
    {...run(2, 21000), status: 'failed'}];
  const data = ScoreCard.build(rows, {model: 'Zephyrus G16', cpu: 'Core Ultra 9', gpu: ['RTX 5090']});
  assert.equal(data.best.run.totalScore, 13000);
  assert.deepEqual(data.modes.map(mode => mode.run.totalScore), [8100, 10400, 13000]);
  assert.equal(ScoreCard.build([run(1, 18000, '')], {}), null);
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
  assert.ok(drawn.some(value => value.includes('13,000')));
  assert.ok(drawn.some(value => value.includes('43.2 dBA')));
  assert.ok(!drawn.join(' ').includes('private'));
  assert.ok(!drawn.join(' ').includes('current'));
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
