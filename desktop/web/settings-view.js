/* Read-only G-Helper profile view. No settings, devices, or files are changed.
 * Field semantics: seerge/g-helper app/Fans.cs (InitPower, VisualiseGPUSettings,
 * LoadProfile), app/Fans.Designer.cs (comboBoost), app/Mode/PowerNative.cs.
 * A config gpu_power value is GPU_POWER, not GPU_BASE + GPU_POWER.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ProfileSettings = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const MODES = Object.freeze([{id:2,name:'조용'},{id:0,name:'균형'},{id:1,name:'터보'}]);
  const DEFAULT = 'BIOS / 기본값';
  const RANGES = Object.freeze({limit_total:[0,150],limit_slow:[0,150],limit_fast:[0,150],limit_cpu:[0,150],
    gpu_power:[0,80],gpu_boost:[0,25],gpu_core:[-500,250],gpu_memory:[-500,2000],gpu_temp:[60,87],gpu_clock_limit:[0,4000]});
  const BOOST = Object.freeze(['꺼짐','켜짐','적극적','효율적으로 켜짐','효율적·적극적','보장 성능에서 적극적','보장 성능에서 효율적']);
  const POWER = Object.freeze({'961cc777-2547-4f9d-8174-7d86181b8a7a':'최고의 전력 효율',
    '00000000-0000-0000-0000-000000000000':'균형 조정',
    'ded574b5-45a0-4f42-8737-46345c09c238':'최고 성능',
    '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c':'고성능 전원 관리 옵션'});
  const own = (o,k) => !!o && typeof o === 'object' && !Array.isArray(o) && Object.prototype.hasOwnProperty.call(o,k);
  const get = (o,k) => own(o,k) ? o[k] : undefined;
  const isObject = v => !!v && typeof v === 'object' && !Array.isArray(v);
  const validMode = mode => MODES.some(m => m.id === mode);
  const missing = v => v === undefined || v === null;
  const safeText = (v, fallback='') => typeof v === 'string' ? v.slice(0,300) : fallback;
  function parseFan(value) {
    if (missing(value)) return {kind:'default',points:[],reason:DEFAULT};
    if (typeof value !== 'string' || !/^[\da-f]{2}(?:-[\da-f]{2}){15}$/i.test(value))
      return {kind:'invalid',points:[],reason:'팬 곡선 형식을 확인해 주세요.'};
    const bytes = value.split('-').map(v => parseInt(v,16));
    if (bytes.some(v => v > 100)) return {kind:'invalid',points:[],reason:'팬 곡선 범위는 0~100°C / 0~100%입니다.'};
    const temps = bytes.slice(0,8), speeds = bytes.slice(8);
    if (temps.some((v,i) => i && v < temps[i-1]) || speeds.some((v,i) => i && v < speeds[i-1]))
      return {kind:'invalid',points:[],reason:'팬 곡선의 온도·속도 순서를 확인해 주세요.'};
    return {kind:'valid',points:temps.map((temperature,i) => ({temperature,speed:speeds[i]})),reason:''};
  }
  function formatSetting(value, unit='', range=null, signed=false) {
    if (missing(value)) return {kind:'default',text:DEFAULT,value:null};
    if (typeof value !== 'number' || !Number.isFinite(value) || !Number.isInteger(value) ||
      (range && (value < range[0] || value > range[1])))
      return {kind:'invalid',text:'설정값 확인 필요',value:null};
    return {kind:'valid',text:(signed && value > 0 ? '+' : '') + value + (unit ? ' ' + unit : ''),value};
  }
  function boostLabel(value) {
    if (missing(value)) return DEFAULT;
    return Number.isInteger(value) && value >= 0 && value < BOOST.length ? BOOST[value] : '설정값 확인 필요';
  }
  function powerModeLabel(value) {
    if (missing(value)) return DEFAULT;
    if (typeof value !== 'string') return '설정값 확인 필요';
    const id = value.toLowerCase();
    if (own(POWER,id)) return POWER[id];
    return /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(value) ? '사용자 지정 전원 모드' : '설정값 확인 필요';
  }
  function flag(value) {
    if (missing(value)) return {kind:'default',on:false,text:'꺼짐 · 기본값'};
    if (value === 0 || value === 1) return {kind:value === 1 ? 'on' : 'off',on:value === 1,text:value === 1 ? '켬' : '꺼짐'};
    return {kind:'invalid',on:false,text:'설정값 확인 필요'};
  }
  function buildModel(settings, hardware, mode=0) {
    mode = validMode(mode) ? mode : 0;
    const validSettings = isObject(settings);
    settings = validSettings ? settings : {};
    hardware = isObject(hardware) ? hardware : {};
    const read = key => get(settings,key+'_'+mode);
    const cpuName = safeText(get(hardware,'cpu'));
    const amd = /\bAMD\b|\bRyzen\b/i.test(cpuName), intel = /\bIntel\b/i.test(cpuName);
    // Do not infer an All-AMD ACPI power topology from marketing names alone.
    const allAMD = get(hardware,'all_amd_ppt') === true;
    const metric = (key,label,unit='W',signed=false) => {
      const item={key,label,unit,range:RANGES[key],...formatSetting(read(key),unit,RANGES[key],signed)};
      // NvidiaGpuControl.SetMaxGPUClock(0) resets the clock lock (-rgc).
      if(key==='gpu_clock_limit' && item.value===0){item.text='기본값 · 별도 상한 없음';item.range=null;}
      return item;
    };
    const totalLabel = allAMD ? 'CPU + GPU 총 전력' : intel ? 'CPU 지속 전력 · PL1' : amd ? '지속 / 총 전력 · SPL / 플랫폼' : '지속 / 총 전력';
    const slowLabel = intel ? 'CPU 부스트 전력 · PL2' : amd ? 'CPU 장기 부스트 · sPPT' : 'CPU 장기 부스트 전력';
    const cpu = [metric('limit_total',totalLabel)],cpuExtra=[];
    if(allAMD){
      cpu.push(metric('limit_cpu','CPU 별도 전력 한도'));
      for(const [key,label] of [['limit_slow','장기 부스트 · 다른 플랫폼용'],['limit_fast','순간 부스트 · 다른 플랫폼용']])
        if(!missing(read(key)))cpuExtra.push(metric(key,label));
    }else{
      cpu.push(metric('limit_slow',slowLabel));
      if(intel){
        if(!missing(read('limit_fast')))cpuExtra.push(metric('limit_fast','순간 부스트 · AMD용 저장값'));
        if(!missing(read('limit_cpu')))cpuExtra.push(metric('limit_cpu','CPU 별도 전력 · All-AMD용 저장값'));
      }else{
        cpu.push(metric('limit_fast','CPU 순간 부스트 · fPPT'));
        if(!missing(read('limit_cpu')))cpu.push(metric('limit_cpu','CPU 별도 전력 한도 · All-AMD'));
      }
    }
    const gpu = [metric('gpu_power','GPU 전력 조정값'),metric('gpu_boost','다이내믹 부스트'),metric('gpu_core','코어 클록 오프셋','MHz',true),
      metric('gpu_memory','메모리 클록 오프셋','MHz',true),metric('gpu_temp','GPU 목표 온도','°C'),metric('gpu_clock_limit','GPU 클록 상한','MHz')];
    const baseValue = get(hardware,'gpu_base_power_w');
    const base = formatSetting(baseValue,'W',[0,1000]);
    if (!missing(baseValue)) gpu.unshift({key:'gpu_base_power_w',label:'GPU 기기 기본 전력',range:[0,1000],unit:'W',...base});
    const rawPower = read('powermode'), rawBoost = read('auto_boost');
    const legacy = formatSetting(read('performance'),'',[0,4]);
    return {mode,name:MODES.find(m=>m.id===mode).name,validSettings,cpu,cpuExtra,gpu,allAMD,intel,amd,
      cpuName,gpuName:Array.isArray(get(hardware,'gpu')) ? get(hardware,'gpu').filter(v=>typeof v==='string').map(v=>v.slice(0,160)).join(' · ') : safeText(get(hardware,'gpu')),
      powerApply:flag(read('auto_apply_power')),fanApply:flag(read('auto_apply')),
      boost:boostLabel(rawBoost),boostKind:missing(rawBoost)?'default':(Number.isInteger(rawBoost)&&rawBoost>=0&&rawBoost<=6?'valid':'invalid'),
      power:powerModeLabel(rawPower),powerKind:missing(rawPower)?'default':(powerModeLabel(rawPower)==='설정값 확인 필요'?'invalid':'valid'),
      legacyPower:legacy.kind==='default'?null:legacy,
      gpuBaseKnown:base.kind==='valid',
      fans:[['cpu','CPU 팬'],['gpu','GPU 팬'],['mid','보조 팬 · Mid']].map(([id,label])=>({id,label,...parseFan(read('fan_profile_'+id))}))};
  }
  function render(container, settings, hardware, options={}) {
    if (!container || typeof container.replaceChildren !== 'function' || !container.ownerDocument) throw new TypeError('설정을 표시할 DOM 요소가 필요합니다.');
    options = isObject(options) ? options : {};
    const doc = container.ownerDocument, namespace = 'http://www.w3.org/2000/svg';
    let destroyed = false, selected = validMode(options.mode) ? options.mode : 0;
    const root = doc.createElement('section'); root.className='ps-view'+(options.compact?' ps-compact':'');
    const node = (tag,text,cls) => {const e=doc.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
    const svg = (tag,attrs,text) => {const e=doc.createElementNS(namespace,tag);for(const [key,val] of Object.entries(attrs||{}))e.setAttribute(key,String(val));if(text!==undefined)e.textContent=text;return e;};
    const intro=node('div',undefined,'ps-intro'),modeButtons=node('div',undefined,'ps-modes');
    modeButtons.setAttribute('role','group'); modeButtons.setAttribute('aria-label','설정을 볼 모드');
    const buttons=[];
    for(const mode of MODES){const button=node('button',mode.name,'ps-mode');button.type='button';button.addEventListener('click',()=>select(mode.id,true));buttons.push([mode.id,button]);modeButtons.append(button);}
    intro.append(modeButtons,node('p','보기만 전환합니다. G-Helper 설정은 바뀌지 않습니다.','ps-hint'));
    const content=node('div',undefined,'ps-content');
    root.append(intro,content); container.replaceChildren(root);
    function badge(label,status){return node('span',label+' '+status.text,'ps-badge ps-'+status.kind);}
    function card(title,subtitle,status){const el=node('section',undefined,'ps-card'),head=node('div',undefined,'ps-card-head');head.append(node('h4',title));if(status)head.append(status);el.append(head);if(subtitle)el.append(node('p',subtitle,'ps-device'));return el;}
    function metricRow(metric,inactive){
      const row=node('div',undefined,'ps-metric'+(inactive?' ps-inactive':''));row.dataset.setting=metric.key;
      const line=node('div',undefined,'ps-metric-line');line.append(node('span',metric.label,'ps-label'),node('strong',metric.text,'ps-value ps-'+metric.kind));row.append(line);
      if(metric.kind==='valid' && metric.range){
        const min=metric.range[0],max=metric.range[1],size=100*(metric.value-min)/(max-min);
        // A non-interactive SVG gauge: no range input or slider affordance.
        const gauge=svg('svg',{viewBox:'0 0 100 4',preserveAspectRatio:'none',class:'ps-gauge','aria-hidden':'true',focusable:'false'});
        gauge.append(svg('rect',{x:0,y:0,width:100,height:4,rx:2,class:'ps-gauge-track'}));
        if(min<0){const zero=100*(0-min)/(max-min);gauge.append(svg('rect',{x:Math.min(zero,size),y:0,width:Math.abs(size-zero),height:4,rx:1,class:'ps-gauge-fill'}),svg('line',{x1:zero,x2:zero,y1:0,y2:4,class:'ps-gauge-zero'}));}
        else gauge.append(svg('rect',{x:0,y:0,width:size,height:4,rx:2,class:'ps-gauge-fill'}));
        row.append(gauge);
      }
      return row;
    }
    function summaryRow(label,text,kind){const row=node('div',undefined,'ps-summary-row');row.append(node('span',label),node('strong',text,'ps-'+kind));return row;}
    function renderFans(model){
      const el=card('팬 곡선','온도에 따른 저장된 팬 속도 설정',badge('팬 곡선 적용',model.fanApply));el.classList.add('ps-fans');
      const legend=node('div',undefined,'ps-legend');
      for(const fan of model.fans){const item=node('span',undefined,'ps-legend-item ps-fan-'+fan.id);item.append(node('i',undefined,'ps-swatch'),node('span',fan.label+(fan.kind==='default'?' · '+DEFAULT:fan.kind==='invalid'?' · 확인 필요':'')));legend.append(item);}
      el.append(legend);
      const valid=model.fans.filter(f=>f.kind==='valid');
      if(valid.length){
        const chart=svg('svg',{viewBox:'0 0 600 235',class:'ps-fan-chart',role:'img','aria-label':model.name+' 모드 저장된 팬 곡선. 가로축 온도 섭씨, 세로축 팬 속도 백분율.',focusable:'false'});
        chart.append(svg('title',{},'저장된 팬 곡선 · 실측값 아님'));
        const left=44,top=18,width=535,height=170,x=t=>left+width*t/100,y=s=>top+height*(1-s/100);
        for(let tick=0;tick<=100;tick+=25){chart.append(svg('line',{x1:left,x2:left+width,y1:y(tick),y2:y(tick),class:'ps-grid'}),svg('text',{x:left-9,y:y(tick)+4,'text-anchor':'end',class:'ps-axis-tick'},String(tick)));}
        for(let tick=0;tick<=100;tick+=20){chart.append(svg('line',{x1:x(tick),x2:x(tick),y1:top,y2:top+height,class:'ps-grid'}),svg('text',{x:x(tick),y:top+height+19,'text-anchor':'middle',class:'ps-axis-tick'},String(tick)));}
        chart.append(svg('text',{x:4,y:11,class:'ps-axis-label'},'%'),svg('text',{x:598,y:229,'text-anchor':'end',class:'ps-axis-label'},'온도 °C'));
        for(const fan of valid){
          const group=svg('g',{class:'ps-series ps-fan-'+fan.id+(model.fanApply.on?'':' ps-series-stored')});
          group.append(svg('polyline',{points:fan.points.map(p=>x(p.temperature)+','+y(p.speed)).join(' '),fill:'none',class:'ps-curve'}));
          for(const point of fan.points){const dot=svg('circle',{cx:x(point.temperature),cy:y(point.speed),r:3.8,class:'ps-point'});dot.append(svg('title',{},fan.label+' · '+point.temperature+'°C / '+point.speed+'%'));group.append(dot);}
          chart.append(group);
        }
        el.append(chart);
        const values=node('details',undefined,'ps-curve-values');values.append(node('summary','팬 곡선 수치 보기'));
        for(const fan of valid){const line=node('p');line.append(node('strong',fan.label+'  '),node('span',fan.points.map(p=>p.temperature+'°C → '+p.speed+'%').join(' · ')));values.append(line);}
        el.append(values);
      }else el.append(node('div',model.fans.some(f=>f.kind==='invalid')?'읽을 수 있는 팬 곡선이 없습니다.':'저장된 커스텀 곡선이 없습니다. BIOS / 기본값은 이 파일에 포함되지 않습니다.','ps-fan-empty'));
      for(const fan of model.fans.filter(f=>f.kind==='invalid'))el.append(node('p',fan.label+': '+fan.reason,'ps-error'));
      let hint='설정 곡선이며 실측 RPM이 아닙니다.';
      if(model.fanApply.kind==='invalid')hint+=' 적용 스위치 설정값을 확인해 주세요.';
      else if(!model.fanApply.on)hint+=' 적용 스위치는 꺼짐이며, 기종별 전력 설정에 따라 팬 곡선이 연동될 수 있습니다.';
      else hint+=' 실제 동작은 기기·BIOS에 따라 다릅니다.';
      el.append(node('p',hint,'ps-hint'));
      return el;
    }
    function draw(){
      if(destroyed)return;
      const model=buildModel(settings,hardware,selected);
      for(const [id,button] of buttons)button.setAttribute('aria-pressed',String(id===selected));
      content.replaceChildren();
      if(!model.validSettings){content.append(node('p','설정 정보를 읽을 수 없습니다. 연결 상태를 확인해 주세요.','ps-error'));return;}
      const caption=node('div',undefined,'ps-caption');caption.append(node('strong',model.name+' 모드'),node('span','저장된 값 · 읽기 전용'));content.append(caption);
      const grid=node('div',undefined,'ps-grid-cards');
      const cpu=card('CPU 전력',model.cpuName,badge('전력 제한 적용',model.powerApply));
      model.cpu.forEach(m=>cpu.append(metricRow(m,!model.powerApply.on)));
      if(model.cpuExtra.length){const other=node('details',undefined,'ps-other-values');other.append(node('summary','다른 플랫폼용 저장값 '+model.cpuExtra.length+'개'));
        other.append(node('p','현재 기기에 적용되는 항목으로 확인되지 않은 저장값입니다.','ps-hint'));
        model.cpuExtra.forEach(m=>other.append(metricRow(m,true)));cpu.append(other);}
      if(model.powerApply.kind==='invalid')cpu.append(node('p','전력 제한 자동 적용 설정값을 확인해 주세요.','ps-hint'));
      else if(!model.powerApply.on)cpu.append(node('p','저장값의 전력 제한 자동 적용이 꺼져 있습니다.','ps-hint'));
      else cpu.append(node('p','자동 적용 설정이 켜져 있습니다. 실제 적용 여부는 기기 지원에 따라 다릅니다.','ps-hint'));
      const gpu=card('GPU 설정',model.gpuName);
      model.gpu.forEach(m=>gpu.append(metricRow(m,false)));
      if(!model.gpuBaseKnown)gpu.append(node('p','전력 조정값에는 기기 기본 전력이 포함되지 않습니다.','ps-hint'));
      grid.append(cpu,gpu);content.append(grid);
      const system=node('div',undefined,'ps-system');system.append(summaryRow('CPU 부스트',model.boost,model.boostKind),summaryRow('Windows 전원 모드',model.power,model.powerKind));
      if(model.legacyPower)system.append(summaryRow('이전 전원 설정 코드',model.legacyPower.text+' · 현재 전원 모드와 별도',model.legacyPower.kind));
      content.append(system,renderFans(model));
    }
    function select(mode,notify){
      if(destroyed||!validMode(mode)||selected===mode)return;
      selected=mode;draw();
      if(notify&&typeof options.onModeChange==='function')options.onModeChange(mode);
    }
    draw();
    return {setMode(mode){select(mode,false);},destroy(){if(destroyed)return;destroyed=true;root.remove();}};
  }
  return Object.freeze({render,parseFan,formatSetting,boostLabel,powerModeLabel,buildModel,MODES});
});
