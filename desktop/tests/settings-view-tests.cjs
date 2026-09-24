'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {render,parseFan,formatSetting,boostLabel,powerModeLabel,buildModel} = require('../web/settings-view.js');
const curve='14-1E-28-32-3C-46-50-64-00-0A-14-28-3C-50-5A-64';

test('fan parsing preserves the eight temperature/speed pairs and zero',()=>{
  const result=parseFan(curve);assert.equal(result.kind,'valid');assert.equal(result.points.length,8);
  assert.deepEqual(result.points[0],{temperature:20,speed:0});assert.deepEqual(result.points[7],{temperature:100,speed:100});
  assert.deepEqual(parseFan(curve.toLowerCase()),result);
});
test('missing and malformed fan curves remain distinct; no default curve is invented',()=>{
  assert.equal(parseFan(undefined).kind,'default');assert.equal(parseFan(null).kind,'default');
  for(const value of ['',[],{},42,'<svg onload=alert(1)>',curve+'-00',curve.replace('14','GG'),curve.replace(/64$/,'FF'),curve.replace(/^14-1E/,'1E-14'),curve.replace('00-0A','0A-00')]){
    assert.equal(parseFan(value).kind,'invalid');assert.deepEqual(parseFan(value).points,[]);
  }
});
test('equal points are valid and temperature/percentage bounds match profile validation',()=>{
  assert.equal(parseFan('00-00-00-00-00-00-00-00-00-00-00-00-00-00-00-00').kind,'valid');
  assert.equal(parseFan(curve.replace(/^14/,'65')).kind,'invalid');
});
test('numeric rendering distinguishes zero, negative offsets, missing, and invalid values',()=>{
  assert.equal(formatSetting(0,'W',[0,150]).text,'0 W');assert.equal(formatSetting(-20,'MHz',[-500,250],true).text,'-20 MHz');
  assert.equal(formatSetting(20,'MHz',[-500,250],true).text,'+20 MHz');
  assert.equal(formatSetting(undefined).kind,'default');assert.equal(formatSetting(null).kind,'default');
  for(const value of [NaN,Infinity,'30',false,{},-1,151,12.5])assert.equal(formatSetting(value,'W',[0,150]).kind,'invalid');
});
test('boost and Windows power labels use verified mappings, preserving disabled zero',()=>{
  assert.equal(boostLabel(0),'꺼짐');assert.equal(boostLabel(6),'보장 성능에서 효율적');assert.equal(boostLabel(undefined),'BIOS / 기본값');
  assert.equal(boostLabel('0'),'설정값 확인 필요');assert.equal(boostLabel(7),'설정값 확인 필요');
  assert.equal(powerModeLabel('00000000-0000-0000-0000-000000000000'),'균형 조정');
  assert.equal(powerModeLabel('DED574B5-45A0-4F42-8737-46345C09C238'),'최고 성능');
  assert.equal(powerModeLabel('<img src=x onerror=alert(1)>'),'설정값 확인 필요');
  assert.equal(powerModeLabel(undefined),'BIOS / 기본값');
});
test('mode isolation, disabled application, and fallback labels do not claim active settings',()=>{
  const settings={limit_total_0:45,limit_total_1:90,auto_apply_power_0:0,auto_apply_0:0,gpu_core_0:0,auto_boost_0:0,fan_profile_cpu_0:curve};
  const before=JSON.stringify(settings),model=buildModel(settings,{cpu:'Intel Core Ultra 9',gpu:['NVIDIA RTX']},0);
  assert.equal(model.cpu[0].text,'45 W');assert.equal(model.cpu[0].label,'CPU 지속 전력 · PL1');
  assert.equal(model.powerApply.on,false);assert.equal(model.powerApply.text,'꺼짐');assert.equal(model.fanApply.on,false);
  assert.equal(model.boost,'꺼짐');assert.equal(model.gpu.find(m=>m.key==='gpu_core').text,'0 MHz');
  assert.equal(model.fans[0].kind,'valid');assert.equal(model.fans[1].kind,'default');assert.equal(model.power,'BIOS / 기본값');
  assert.equal(buildModel(settings,{},1).cpu[0].text,'90 W');assert.equal(buildModel(settings,{},2).cpu[0].text,'BIOS / 기본값');
  assert.equal(JSON.stringify(settings),before);
});
test('CPU topology and GPU power do not invent total wattage from config',()=>{
  const settings={limit_total_0:45,gpu_power_0:20,gpu_boost_0:10};
  const amd=buildModel(settings,{cpu:'AMD Ryzen 9',gpu:['AMD Radeon']});
  assert.equal(amd.cpu[0].label,'지속 / 총 전력 · SPL / 플랫폼');assert.equal(amd.allAMD,false);
  assert.equal(buildModel(settings,{all_amd_ppt:true}).cpu[0].label,'CPU + GPU 총 전력');
  assert.equal(amd.gpu.find(m=>m.key==='gpu_power').label,'GPU 전력 조정값');assert.equal(amd.gpuBaseKnown,false);
  const known=buildModel(settings,{gpu_base_power_w:60});assert.equal(known.gpu[0].text,'60 W');assert.equal(known.gpuBaseKnown,true);
  assert.equal(known.gpu.find(m=>m.key==='gpu_power').text,'20 W');
});
test('GPU clock limit zero means reset the separate cap, not a 0 MHz operating clock',()=>{
  const zero=buildModel({gpu_clock_limit_0:0,gpu_core_0:0},{}).gpu;
  const limit=zero.find(m=>m.key==='gpu_clock_limit');
  assert.equal(limit.kind,'valid');assert.equal(limit.value,0);assert.equal(limit.text,'기본값 · 별도 상한 없음');assert.equal(limit.range,null);
  assert.equal(zero.find(m=>m.key==='gpu_core').text,'0 MHz');
  assert.equal(buildModel({gpu_clock_limit_0:1800},{}).gpu.find(m=>m.key==='gpu_clock_limit').text,'1800 MHz');
  assert.equal(buildModel({},{}).gpu.find(m=>m.key==='gpu_clock_limit').kind,'default');
});
test('Intel and All-AMD views separate values that current G-Helper applies only on other platforms',()=>{
  const settings={limit_total_0:45,limit_slow_0:60,limit_fast_0:75,limit_cpu_0:40};
  const intel=buildModel(settings,{cpu:'Intel Core Ultra 9 285H'});
  assert.deepEqual(intel.cpu.map(m=>m.key),['limit_total','limit_slow']);assert.equal(intel.cpu[1].label,'CPU 부스트 전력 · PL2');
  assert.deepEqual(intel.cpuExtra.map(m=>m.key),['limit_fast','limit_cpu']);
  const all=buildModel(settings,{cpu:'AMD Ryzen',all_amd_ppt:true});
  assert.deepEqual(all.cpu.map(m=>m.key),['limit_total','limit_cpu']);assert.deepEqual(all.cpuExtra.map(m=>m.key),['limit_slow','limit_fast']);
});
test('invalid outer inputs, flags, unsupported modes and legacy keys are represented safely',()=>{
  assert.equal(buildModel([],null).validSettings,false);assert.equal(buildModel(null,{}).validSettings,false);
  const model=buildModel({auto_apply_0:'1',auto_apply_power_0:true,performance_0:0},[],99);
  assert.equal(model.mode,0);assert.equal(model.fanApply.kind,'invalid');assert.equal(model.powerApply.on,false);
  assert.equal(model.legacyPower.text,'0');assert.equal(model.power,'BIOS / 기본값');
  assert.equal(buildModel(Object.create({limit_total_0:60}),{}).cpu[0].kind,'default');
});

// Deliberately small DOM contract; unsafe HTML writing throws instead of parsing.
class Element {
  constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.attrs={};this.dataset={};this.listeners={};this.className='';this._text='';
    this.classList={add:(...names)=>{this.className=[this.className,...names].filter(Boolean).join(' ');}};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set innerHTML(value){throw Error('Unsafe HTML assignment');}
  setAttribute(key,value){this.attrs[key]=String(value);if(key==='class')this.className=String(value);}
  append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
  replaceChildren(...items){for(const child of this.children)child.parent=null;this.children=[];this._text='';this.append(...items);}
  addEventListener(type,callback){this.listeners[type]=callback;}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(c=>c!==this);this.parent=null;}
}
const fakeDocument={createElement(tag){return new Element(tag,this);},createElementNS(ns,tag){assert.equal(ns,'http://www.w3.org/2000/svg');return new Element(tag,this);}};
const descendants=root=>[root,...root.children.flatMap(descendants)];

test('DOM view preserves hostile hardware as text and never generates executable markup',()=>{
  const target=new Element('div',fakeDocument),attack='<img src=x onerror=alert(1)>',settings={gpu_core_0:0,fan_profile_cpu_0:curve,fan_profile_gpu_0:attack};
  const view=render(target,settings,{cpu:attack,gpu:[attack]});
  assert.ok(target.textContent.includes(attack));
  const nodes=descendants(target);
  assert.equal(nodes.some(n=>['img','script','input'].includes(n.tag)),false);
  assert.equal(nodes.some(n=>Object.keys(n.attrs).some(k=>/^on/i.test(k))),false);
  assert.equal(nodes.filter(n=>n.tag==='polyline').length,1);
  assert.equal(nodes.filter(n=>n.tag==='circle').length,8);
  assert.ok(target.textContent.includes('0 MHz'));assert.ok(target.textContent.includes('실측 RPM이 아닙니다'));
  assert.ok(nodes.filter(n=>n.tag==='circle').every(n=>Number.isFinite(Number(n.attrs.cx))&&Number.isFinite(Number(n.attrs.cy))));
  view.destroy();assert.equal(target.children.length,0);
});
test('mode buttons only switch the read-only view; API selection, callbacks, and destroy work',()=>{
  const target=new Element('div',fakeDocument),settings={limit_total_0:45,limit_total_1:90,limit_total_2:25},calls=[];
  const original=JSON.stringify(settings),view=render(target,settings,{}, {mode:0,compact:true,onModeChange:m=>calls.push(m)});
  const buttons=()=>descendants(target).filter(n=>n.tag==='button');
  assert.deepEqual(buttons().map(n=>n.textContent),['조용','균형','터보']);
  assert.equal(buttons()[1].attrs['aria-pressed'],'true');
  buttons()[0].listeners.click();assert.deepEqual(calls,[2]);assert.ok(target.textContent.includes('25 W'));
  view.setMode(1);assert.deepEqual(calls,[2]);assert.ok(target.textContent.includes('90 W'));
  assert.equal(buttons()[2].attrs['aria-pressed'],'true');
  view.setMode(99);assert.ok(target.textContent.includes('90 W'));
  assert.equal(JSON.stringify(settings),original);view.destroy();view.setMode(0);view.destroy();assert.equal(target.children.length,0);
});
