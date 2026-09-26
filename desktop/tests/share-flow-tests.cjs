'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Load the real app functions without starting timers, network or a browser.
function app() {
  const elements = new Map();
  const element = () => {
    const classes = new Set();
    return {open: false, disabled: false, value: '', textContent: '', isConnected: true,
      children: [], dataset: {}, classList: {add: value => classes.add(value), contains: value => classes.has(value)},
      addEventListener() {}, focus() {}, setAttribute() {}, querySelectorAll: () => [],
      append(...items) { this.children.push(...items); },
      replaceChildren(...items) { this.children = items; },
      showModal() { this.open = true; }, close() { this.open = false; }};
  };
  const get = id => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  const context = vm.createContext({document: {
    getElementById: get, createElement: element, querySelectorAll: () => [], activeElement: get('focus')
  }, window: {addEventListener() {}}, setInterval() {}, clearTimeout() {},
  setTimeout() {}, console, ProfileSettings: require('../web/settings-view.js'),
  ShareSelection: require('../web/share-selection.js')});
  for (const file of ['app.js', 'library.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web', file), 'utf8'), context);
  }
  return {context, get};
}

test('returning from review keeps the edited title and notes in the sharing form', () => {
  const {context, get} = app();
  get('public-name').value = 'My laptop'; get('public-notes').value = 'My public notes';
  context.openModal('Review', {}, 'Share', () => {}, () => get('publish-modal').showModal());
  assert.equal(get('modal-cancel').textContent, '← 수정하기');
  context.closeModal();
  assert.equal(get('modal').open, false);
  assert.equal(get('publish-modal').open, true);
  assert.equal(get('public-name').value, 'My laptop');
  assert.equal(get('public-notes').value, 'My public notes');
});

test('successful confirmation closes review without returning to the edit form', async () => {
  const {context, get} = app(); let returned = 0;
  context.openModal('Review', {}, 'Share', async () => true, () => returned++);
  await context.confirmModal();
  assert.equal(get('modal').open, false);
  assert.equal(returned, 0);
});

test('editing is blocked while publication is pending and available afterward', async () => {
  const {context, get} = app(); let finish, returned = 0;
  context.openModal('Review', {}, 'Share', () => new Promise(resolve => { finish = resolve; }), () => returned++);
  const pending = context.confirmModal();
  context.closeModal();
  assert.equal(get('modal').open, true);
  assert.equal(returned, 0);
  finish(false); await pending;
  context.closeModal();
  assert.equal(returned, 1);
});

test('an unresolved upload cannot create another publication after returning to edit', async () => {
  const {context} = app();
  vm.runInContext("library.owned=[{requestId:'pending',id:null}];", context);
  await assert.rejects(context.prepareShare(), /이전 게시 요청/);
});

test('home summaries read each mode separately and mark only the current mode', () => {
  const {context, get} = app();
  vm.runInContext("state={hardware:{cpu:'Intel Core'},config:{performance_mode:0,limit_total_2:25,limit_total_0:45,limit_total_1:85,gpu_power_2:0,gpu_power_0:10,gpu_power_1:20}};", context);
  context.renderHomeModes();
  const cards = get('home-modes').children;
  assert.equal(cards.length, 3);
  assert.deepEqual(cards.map(card => card.children[0].children[0].textContent), ['조용','균형','터보']);
  assert.deepEqual(cards.map(card => card.children[1].children[1].textContent), ['25 W','45 W','85 W']);
  assert.deepEqual(cards.map(card => card.children[1].children[3].textContent), ['0 W','10 W','20 W']);
  assert.deepEqual(cards.map(card => card.classList.contains('active')), [false,true,false]);
  context.renderHomeModes();
  assert.equal(get('home-modes').children, cards);
});

test('share form automatically includes all three mode results in one-post summary', () => {
  const {context, get} = app();
  const hardware = {model:'This laptop',cpu:'Intel Core',gpu:['RTX 4070'],ram_gb:32};
  const profiles = [2,0,1].map(mode => ({id:'p'+mode,origin:'local',hardware,settingsHash:'h'+mode,createdAt:'2026-09-26T00:00:00Z'}));
  const runs = [2,0,1].map(mode => ({id:'r'+mode,profileId:'p'+mode,settingsHash:'h'+mode,mode,binding:'captured',status:'valid',graphicsScore:14000+mode,cpuScore:8000+mode}));
  vm.runInContext('state='+JSON.stringify({profiles,runs,hardware})+';',context);
  get('public-profile').value='p2';
  context.renderPublicRuns();
  assert.equal(get('share-summary').textContent,'설정 3개 모드 + 점수 3개 → 게시물 하나');
  assert.equal(get('public-runs').children[0].children.length,3);
  assert.equal(vm.runInContext('publicSelection.size',context),3);
});
