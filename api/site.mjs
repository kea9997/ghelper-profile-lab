// Read-only public site. Shared data is inserted with textContent in the browser.
export function siteHtml(release) {
  const download = release
    ? `<a class="button button-primary" href="${release}" rel="noopener noreferrer">Windows 앱 다운로드 <span aria-hidden="true">↗</span></a>`
    : '<span class="button button-disabled">다운로드 준비 중</span>';
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="G-Helper Profile Lab에서 ASUS 노트북 설정을 저장하고, Time Spy 결과와 함께 공유된 설정을 찾아보세요.">
  <title>G-Helper Profile Lab | 설정 공유 자료실</title>
  <link rel="stylesheet" href="/site.css">
  <script src="/site.js" defer></script>
</head>
<body>
  <header class="topbar wrap">
    <a class="brand" href="/" aria-label="G-Helper Profile Lab 처음으로"><span class="brand-mark">G<span class="brand-dot">●</span></span><span>G-Helper <strong>Profile Lab</strong></span></a>
    <nav aria-label="바로가기"><a href="#library">공유 설정</a><a href="#how-it-works">사용 방법</a></nav>
    <a class="top-download" href="${release || 'https://github.com/kea9997/ghelper-profile-lab'}" rel="noopener noreferrer">앱 받기 ↗</a>
  </header>
  <main>
    <section class="hero wrap" aria-labelledby="hero-title">
      <div class="hero-copy">
        <div class="eyebrow"><span class="signal"></span> ASUS 노트북 설정 공유</div>
        <h1 id="hero-title">내 노트북 설정을<br><em>저장하고, 비교하고, 공유하세요.</em></h1>
        <p class="hero-lead">G-Helper 설정을 백업하고, 조용·균형·터보 모드의 Time Spy 점수와 소음 기록을 함께 남기는 Windows 앱입니다. 다른 사용자가 공개한 설정도 여기서 바로 살펴볼 수 있습니다.</p>
        <div class="hero-actions">${download}<a class="button button-secondary" href="#library">공유 설정 둘러보기 ↓</a></div>
        <p class="hero-note">웹에서는 공개된 자료를 볼 수 있습니다. 설정 적용과 공유는 Windows 앱에서 진행합니다.</p>
      </div>
      <div class="hero-card" aria-label="공유 설정에서 확인할 수 있는 정보">
        <div class="mock-top"><span class="mock-lights"><i></i><i></i><i></i></span><span>PROFILE LAB / LIBRARY</span><span class="mock-live">LIVE</span></div>
        <div class="mock-body"><span class="mock-kicker">한눈에 확인하는 내 설정</span><strong>노트북 사양부터<br>설정값과 점수까지</strong><div class="mock-chips"><span>CPU · GPU</span><span>전력 · 팬 곡선</span><span>Time Spy</span></div><div class="mock-modes"><span>조용</span><span>균형</span><span>터보</span></div></div>
      </div>
    </section>
    <section id="library" class="library-section">
      <div class="wrap">
        <div class="section-heading"><div><span class="section-kicker">COMMUNITY LIBRARY</span><h2>공유된 설정 찾아보기</h2><p>모델명, 제품군, CPU, GPU로 검색하고 설정과 벤치마크 기록을 확인하세요.</p></div><span class="read-only">읽기 전용 자료실</span></div>
        <form id="search-form" class="search-form" role="search"><label for="search-input" class="sr-only">공유 설정 검색</label><span aria-hidden="true" class="search-icon">⌕</span><input id="search-input" type="search" maxlength="160" placeholder="예: 제피러스 G16 2025 RTX5090" autocomplete="off"><button type="submit">검색</button></form>
        <div class="library-meta"><p id="results-status" role="status" aria-live="polite">공유 설정을 불러오는 중입니다…</p><span>게시된 점수와 설정은 사용자 제공 정보입니다.</span></div>
        <div id="profile-list" class="profile-grid"></div>
        <button id="load-more" class="button button-more" type="button" hidden>더 보기 ↓</button>
        <section id="references" class="reference-section" aria-labelledby="references-title">
          <div class="section-heading"><div><span class="section-kicker">ASUS SPECS · COMMUNITY RESULTS</span><h2 id="references-title">기종별 공식 사양과 측정 기록</h2><p>위 검색창에서 모델 코드나 “제피러스 G14 2025 RTX 5070 Ti”처럼 사양을 입력하세요. 출처의 설정 조건과 Time Spy 점수를 함께 볼 수 있습니다.</p></div></div>
          <p id="references-status" class="reference-status" role="status" aria-live="polite">참고 자료를 불러오는 중입니다…</p>
          <div id="references-list" class="profile-grid"></div>
          <button id="references-more" class="button button-more" type="button" hidden>참고 자료 더 보기 ↓</button>
          <p class="reference-note">ASUS 공식 GPU 전력은 하드웨어 사양이며 G-Helper에 넣을 권장 설정값이 아닙니다. 사용자 점수는 동일한 기종에서도 냉각·BIOS·드라이버에 따라 달라질 수 있습니다. 참고 자료는 자동 적용되지 않습니다.</p>
        </section>
      </div>
    </section>
    <section id="how-it-works" class="how-section wrap"><div class="section-heading"><div><span class="section-kicker">HOW IT WORKS</span><h2>처음이라도 간단하게</h2></div></div><div class="steps"><article><span>01</span><h3>현재 설정 저장</h3><p>Windows 앱에서 G-Helper 설정과 노트북 사양을 읽어 내 프로필로 저장합니다.</p></article><article><span>02</span><h3>결과 기록</h3><p>Time Spy 점수에 모드별 팬 RPM과 소음 기록을 함께 남겨 비교합니다.</p></article><article><span>03</span><h3>공유하고 살펴보기</h3><p>공개한 설정은 이 자료실에 표시됩니다. 적용 전에는 앱에서 설정 내용을 확인할 수 있습니다.</p></article></div></section>
  </main>
  <footer class="footer"><div class="wrap footer-inner"><span>G-Helper Profile Lab</span><span>G-Helper와 별개로 동작하는 사용자 제작 도구 · 게시된 설정과 점수는 검증된 권장값이 아닙니다.</span><a href="https://github.com/kea9997/ghelper-profile-lab" rel="noopener noreferrer">GitHub ↗</a></div></footer>
  <dialog id="profile-dialog" aria-labelledby="detail-title"><div class="dialog-top"><span>공유 설정 상세</span><button id="dialog-close" type="button" aria-label="닫기">×</button></div><div id="dialog-content"></div></dialog>
</body>
</html>`;
}

export const SITE_CSS = String.raw`
:root{color-scheme:dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#0b1018;color:#f2f5fa;font-synthesis:none}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0}button,input{font:inherit}button{cursor:pointer}a{color:inherit;text-decoration:none}.wrap{width:min(1180px,calc(100% - 48px));margin-inline:auto}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid #85e8c4;outline-offset:3px}
.topbar{height:78px;display:flex;align-items:center;gap:36px;border-bottom:1px solid #26313d}.brand{display:flex;align-items:center;gap:12px;font-size:15px;white-space:nowrap}.brand strong{font-weight:750}.brand-mark{width:37px;height:37px;border-radius:11px;background:#b2f0d8;color:#09251b;display:grid;place-items:center;font-size:22px;font-weight:900;position:relative}.brand-dot{position:absolute;font-size:5px;right:5px;bottom:5px}.topbar nav{display:flex;gap:26px;margin-left:auto;color:#b7c6d2;font-size:13px}.topbar nav a:hover,.top-download:hover{color:#b2f0d8}.top-download{font-size:13px;font-weight:700;border:1px solid #3b5f54;border-radius:9px;padding:10px 14px;color:#b2f0d8;white-space:nowrap}
.hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(290px,.75fr);gap:55px;align-items:center;padding-top:100px;padding-bottom:112px}.eyebrow,.section-kicker,.mock-kicker{font-size:11px;font-weight:800;letter-spacing:.16em;color:#9fe8cc}.eyebrow{display:flex;align-items:center;gap:9px}.signal{height:7px;width:7px;border-radius:50%;background:#6aefad;box-shadow:0 0 16px #6aefad}.hero h1{font-size:clamp(38px,5vw,64px);line-height:1.14;letter-spacing:-.055em;margin:22px 0}.hero h1 em{font-style:normal;color:#b3f0d7}.hero-lead{max-width:660px;color:#adbdc9;font-size:17px;line-height:1.9;margin:0}.hero-actions{display:flex;gap:11px;flex-wrap:wrap;margin-top:31px}.button{display:inline-flex;justify-content:center;align-items:center;gap:10px;border-radius:10px;padding:14px 19px;font-size:14px;font-weight:760;border:1px solid transparent;min-height:48px}.button-primary{background:#b7f1da;color:#062117}.button-primary:hover{background:#d5f9e9}.button-secondary{border-color:#3b4855;color:#e2edf3;background:#141d27}.button-secondary:hover,.button-more:hover{border-color:#8caeaa}.button-disabled{background:#26313a;color:#9cabb5}.hero-note{color:#8495a5;font-size:12px;line-height:1.7;margin-top:20px}.hero-card{border:1px solid #35504f;border-radius:20px;background:linear-gradient(155deg,#182a30 0%,#111a25 65%,#151b27 100%);box-shadow:0 25px 80px #0006;overflow:hidden;transform:rotate(1deg)}.mock-top{height:48px;border-bottom:1px solid #344749;display:flex;align-items:center;justify-content:space-between;padding:0 20px;color:#81999b;font-size:9px;font-weight:800;letter-spacing:.11em}.mock-lights{display:flex;gap:5px}.mock-lights i{width:7px;height:7px;background:#597174;border-radius:50%}.mock-lights i:first-child{background:#9ce8bd}.mock-live{color:#9ce8bd}.mock-body{padding:45px 35px 40px;display:flex;flex-direction:column;align-items:flex-start}.mock-body strong{font-size:28px;letter-spacing:-.04em;line-height:1.3;margin:17px 0 28px}.mock-chips,.mock-modes{display:flex;gap:7px;flex-wrap:wrap}.mock-chips span{border:1px solid #3b5a58;color:#b6d5ce;background:#213331;padding:7px 9px;border-radius:6px;font-size:10px}.mock-modes{width:100%;margin-top:31px;padding:12px;border:1px solid #34474c;border-radius:10px;background:#101d25}.mock-modes span{flex:1;text-align:center;color:#a9c0c2;padding:10px 1px;font-size:11px}.mock-modes span:nth-child(2){color:#b7f1da;background:#26433d;border-radius:6px}
.library-section{background:#101823;border-top:1px solid #24313a;border-bottom:1px solid #24313a;padding:73px 0 82px}.section-heading{display:flex;justify-content:space-between;align-items:end;gap:20px}.section-heading h2{font-size:clamp(27px,3vw,37px);letter-spacing:-.04em;margin:10px 0 9px}.section-heading p{color:#aabac7;margin:0;font-size:14px;line-height:1.65}.read-only{font-size:11px;color:#97cdb8;border:1px solid #345348;border-radius:100px;padding:8px 12px;white-space:nowrap}.search-form{margin-top:31px;background:#1a2632;border:1px solid #415361;border-radius:12px;display:flex;align-items:center;padding:6px;box-shadow:0 8px 28px #0002}.search-icon{font-size:26px;color:#9ab0bd;padding:0 12px}.search-form input{flex:1;min-width:0;border:0;outline:0;background:transparent;color:#f2f5fa;padding:12px 0;font-size:15px}.search-form input::placeholder{color:#8b9dac}.search-form button{border:0;background:#b7f1da;color:#0b291e;font-size:13px;font-weight:800;padding:13px 21px;border-radius:8px}.search-form button:hover{background:#d5f9e9}.library-meta{display:flex;align-items:center;justify-content:space-between;gap:14px;color:#91a6b4;font-size:12px;margin:17px 0 18px}.library-meta p{margin:0;color:#c3d6db}.profile-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.profile-card{background:#19232e;border:1px solid #344450;border-radius:14px;padding:22px;display:flex;flex-direction:column;min-height:244px}.profile-card:hover{border-color:#75a995}.card-top{display:flex;justify-content:space-between;gap:10px;color:#a0e8c9;font-size:11px;font-weight:800}.card-date{color:#7e91a1;font-weight:500}.profile-card h3{font-size:19px;line-height:1.4;letter-spacing:-.03em;margin:18px 0 6px;word-break:break-word}.card-hardware{color:#a7b7c2;font-size:12px;line-height:1.6;margin:0;word-break:break-word}.card-scores{display:flex;gap:6px;flex-wrap:wrap;margin:17px 0}.card-scores span{border:1px solid #3f505d;background:#202d39;border-radius:6px;padding:7px 8px;font-size:11px;color:#d3e2e5}.card-bottom{border-top:1px solid #33414d;padding-top:14px;margin-top:auto;display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:11px;color:#8fa3b0}.card-bottom button{border:0;background:none;color:#b7f1da;font-weight:800;font-size:12px;padding:5px 0}.empty-state{grid-column:1/-1;text-align:center;padding:54px 20px;border:1px dashed #4a5a64;border-radius:14px;background:#19232d}.empty-state strong{display:block;font-size:19px;margin-bottom:9px}.empty-state p{color:#9db0bd;font-size:13px;line-height:1.7;margin:0}.button-more{display:flex;margin:27px auto 0;background:#202b36;color:#d3e8e4;border-color:#52636d}.button-more[hidden]{display:none}
.how-section{padding-top:83px;padding-bottom:98px}.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:19px;margin-top:32px}.steps article{border-top:1px solid #46675d;padding-top:21px}.steps article>span{font-size:13px;font-weight:800;color:#9ee0c4}.steps h3{font-size:20px;letter-spacing:-.03em;margin:17px 0 8px}.steps p{color:#a1b4c1;font-size:13px;line-height:1.8;max-width:320px;margin:0}.footer{border-top:1px solid #283743;color:#8196a3;font-size:11px}.footer-inner{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:25px 0}.footer-inner>span:first-child{color:#c5d6d9;font-weight:800}.footer a{color:#b7f1da;white-space:nowrap}
.reference-section{margin-top:72px;padding-top:52px;border-top:1px solid #354650}.reference-section.has-no-posts{margin-top:30px;padding-top:30px}.public-empty{padding:19px 20px}.public-empty strong{font-size:15px;margin-bottom:3px}.public-empty p{font-size:12px}.reference-status{color:#b9ccc9;font-size:13px;margin:25px 0 16px}.reference-card{min-height:240px}.reference-card .card-scores{margin:15px 0 8px}.reference-summary{color:#b7c7cf;font-size:12px;line-height:1.65;margin:9px 0 12px}.reference-card .card-bottom a{color:#b7f1da;font-weight:750}.reference-card .card-bottom a:hover{text-decoration:underline}.reference-note{font-size:12px;line-height:1.7;color:#9fb0bb;margin:23px 0 0}
dialog{border:1px solid #466056;border-radius:16px;color:#f2f5fa;background:#16212b;width:min(780px,calc(100% - 28px));max-height:min(85vh,900px);padding:0;box-shadow:0 30px 100px #000b}dialog::backdrop{background:#03070bc9}.dialog-top{height:55px;padding:0 23px;border-bottom:1px solid #34434b;display:flex;justify-content:space-between;align-items:center;color:#a5dfc9;font-weight:800;font-size:12px}.dialog-top button{background:none;color:#d4e4e7;border:0;font-size:27px;line-height:1}.dialog-body{padding:25px}.dialog-body h2{font-size:26px;margin:0 0 10px;line-height:1.35;word-break:break-word}.dialog-note{color:#abc0ca;font-size:13px;line-height:1.7;margin:0 0 18px;white-space:pre-wrap}.detail-meta{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0 22px}.detail-meta span{background:#253742;color:#ccdfde;border:1px solid #3c5557;border-radius:6px;font-size:11px;padding:7px 9px}.detail-section{border-top:1px solid #34444c;padding:20px 0}.detail-section h3{font-size:15px;margin:0 0 13px}.detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.detail-cell{background:#202e39;border-radius:8px;padding:11px;font-size:11px}.detail-cell span{display:block;color:#9aafba;margin-bottom:6px}.detail-cell strong{font-size:15px;word-break:break-word}.detail-mode{border:1px solid #3b5158;border-radius:9px;padding:13px;margin:10px 0}.detail-mode h4{margin:0 0 11px;font-size:13px;color:#b4efd5}.detail-mode p{color:#c1d0d5;font-size:12px;line-height:1.6;margin:5px 0}.setting-row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid #2e3e46;font-size:12px}.setting-row span{color:#b6c8cf}.setting-row strong{font-weight:700;text-align:right;word-break:break-all}.detail-caution{color:#91a8b3;font-size:11px;line-height:1.7}
@media(max-width:860px){.hero{grid-template-columns:1fr;padding-top:74px;padding-bottom:74px;gap:40px}.hero-card{max-width:480px;transform:none}.profile-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.footer-inner{flex-wrap:wrap}}@media(max-width:600px){.wrap{width:min(100% - 30px,1180px)}.topbar{height:65px;gap:10px}.brand{font-size:13px}.brand-mark{width:31px;height:31px;font-size:19px}.topbar nav{display:none}.top-download{margin-left:auto;padding:8px;font-size:11px}.hero{padding-top:59px;padding-bottom:66px}.hero h1{font-size:39px}.hero-lead{font-size:14px}.hero-actions{flex-direction:column}.hero-actions .button{width:100%}.mock-body{padding:31px}.library-section{padding:58px 0}.section-heading{align-items:start;flex-direction:column}.profile-grid,.steps{grid-template-columns:1fr}.library-meta{flex-direction:column;align-items:start}.search-form input{font-size:13px}.search-form button{padding:12px}.detail-grid{grid-template-columns:repeat(2,1fr)}.dialog-body{padding:18px}.footer-inner{align-items:start;flex-direction:column}.read-only{display:none}}
`;

export const SITE_JS = String.raw`
(() => {
  'use strict';
  const form = document.querySelector('#search-form');
  const input = document.querySelector('#search-input');
  const list = document.querySelector('#profile-list');
  const status = document.querySelector('#results-status');
  const more = document.querySelector('#load-more');
  const dialog = document.querySelector('#profile-dialog');
  const content = document.querySelector('#dialog-content');
  const referencesList = document.querySelector('#references-list');
  const referencesStatus = document.querySelector('#references-status');
  const referencesMore = document.querySelector('#references-more');
  const modeNames = { 0: '균형', 1: '터보', 2: '조용' };
  const settingNames = { limit_total: 'CPU 총 전력', limit_slow: 'CPU 지속 전력', limit_fast: 'CPU 순간 전력', limit_cpu: 'CPU 전력', auto_apply: '팬 설정 자동 적용', auto_apply_power: '전력 설정 자동 적용', auto_boost: 'CPU 부스트', powermode: 'Windows 전원 모드', performance: 'Windows 전원 설정', gpu_temp: 'GPU 목표 온도', gpu_power: 'GPU 전력 설정', gpu_boost: 'GPU 부스트', gpu_core: 'GPU 코어 클록', gpu_memory: 'GPU 메모리 클록', gpu_clock_limit: 'GPU 최대 클록' };
  const units = { limit_total: ' W', limit_slow: ' W', limit_fast: ' W', limit_cpu: ' W', gpu_temp: ' °C', gpu_power: ' W', gpu_boost: ' W', gpu_core: ' MHz', gpu_memory: ' MHz', gpu_clock_limit: ' MHz' };
  const families = { GU605CX: 'ROG 제피러스 G16 2025', GU605CW: 'ROG 제피러스 G16 2025', GU605CR: 'ROG 제피러스 G16 2025', GU605CM: 'ROG 제피러스 G16 2025', GU605MI: 'ROG 제피러스 G16 2024', GU605MY: 'ROG 제피러스 G16 2024', GU605MZ: 'ROG 제피러스 G16 2024', GA403UI: 'ROG 제피러스 G14 2024', GZ302EA: 'ROG Flow Z13 2025' };
  const boostNames = ['꺼짐', '켜짐', '적극적', '효율적으로 켜짐', '효율적·적극적', '보장 성능에서 적극적', '보장 성능에서 효율적'];
  const powerNames = { '961cc777-2547-4f9d-8174-7d86181b8a7a': '최고의 전력 효율', '00000000-0000-0000-0000-000000000000': '균형 조정', 'ded574b5-45a0-4f42-8737-46345c09c238': '최고 성능', '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c': '고성능' };
  let cursor = null;
  let query = '';
  let generation = 0;
  let count = 0;
  let busy = false;
  let references = [];
  let referencesVisible = 18;
  function node(tag, className, value) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (value != null) result.textContent = String(value);
    return result;
  }
  function date(value) {
    const parsed = new Date(value);
    return Number.isFinite(parsed.getTime()) ? new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'numeric', day: 'numeric' }).format(parsed) : '';
  }
  function hardware(post) {
    const h = post.profile && post.profile.hardware || {};
    const gpu = Array.isArray(h.gpu) ? h.gpu.find(x => /RTX|Radeon|Arc/i.test(x)) || h.gpu[0] : '';
    const gpuShort = gpu && gpu.match(/(?:RTX\s*\d{4,5}|Radeon\s*\w+|Arc\s*\w+)/i);
    const model = h.model || '모델 미상';
    return { title: [families[model], model, gpuShort ? gpuShort[0].replace(/RTX\s*/, 'RTX ') : ''].filter(Boolean).join(' · '), line: [h.cpu, gpu, h.ram_gb ? String(h.ram_gb) + 'GB RAM' : ''].filter(Boolean).join(' · '), h };
  }
  function score(run) { return Number(run.totalScore).toLocaleString('ko-KR') + '점'; }
  function fanCurve(value) {
    if (typeof value !== 'string' || !/^[\da-f]{2}(?:-[\da-f]{2}){15}$/i.test(value)) return '팬 곡선 확인 필요';
    const bytes = value.split('-').map(part => parseInt(part, 16));
    return bytes.slice(0, 8).map((temp, index) => temp + '°C → ' + bytes[index + 8] + '%').join(' · ');
  }
  function settingValue(base, value) {
    if (base.startsWith('fan_profile_')) return fanCurve(value);
    if (base === 'auto_apply' || base === 'auto_apply_power') return value ? '켜짐' : '꺼짐';
    if (base === 'auto_boost') return boostNames[value] || String(value);
    if (base === 'powermode') return powerNames[String(value).toLowerCase()] || '사용자 지정 전원 모드';
    return String(value) + (units[base] || '');
  }
  function latestRuns(post) {
    const byMode = new Map();
    for (const run of post.runs || []) {
      const previous = byMode.get(run.mode);
      if (!previous || Date.parse(run.createdAt) > Date.parse(previous.createdAt)) byMode.set(run.mode, run);
    }
    return [2, 0, 1].filter(mode => byMode.has(mode)).map(mode => byMode.get(mode));
  }
  function referenceMatches(entry, search) {
    const tokens = search.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    const values = [entry.title, entry.family, entry.year, entry.model, entry.cpu, entry.gpu, entry.summary, entry.settingsText, entry.timeSpy && entry.timeSpy.total, entry.family && entry.family.replace('제피러스', 'Zephyrus')].filter(Boolean).join(' ').toLocaleLowerCase();
    const compact = values.replace(/[\s·_-]/g, '');
    return tokens.every(token => values.includes(token) || compact.includes(token.replace(/[\s·_-]/g, '')));
  }
  function referenceCard(entry) {
    const item = node('article', 'profile-card reference-card');
    const top = node('div', 'card-top');
    top.append(node('span', '', entry.sourceType === 'official' ? 'ASUS 공식 사양' : entry.timeSpy ? '사용자 Time Spy' : '사용자 설정 참고'), node('span', 'card-date', entry.year || ''));
    item.append(top, node('h3', '', entry.title), node('p', 'card-hardware', [entry.cpu, entry.gpu].filter(Boolean).join(' · ')), node('p', 'reference-summary', entry.summary));
    if (entry.timeSpy) {
      const scores = node('div', 'card-scores');
      scores.append(node('span', '', 'Time Spy 총점 ' + Number(entry.timeSpy.total).toLocaleString('ko-KR')));
      if (entry.timeSpy.graphics != null) scores.append(node('span', '', '그래픽 ' + Number(entry.timeSpy.graphics).toLocaleString('ko-KR')));
      if (entry.timeSpy.cpu != null) scores.append(node('span', '', 'CPU ' + Number(entry.timeSpy.cpu).toLocaleString('ko-KR')));
      item.append(scores);
    }
    const details = node('details', 'reference-details');
    details.append(node('summary', '', '설정 조건과 한계 보기'));
    for (const line of [entry.settingsText, entry.timeSpy && entry.timeSpy.conditions, entry.limitations].filter(Boolean)) details.append(node('p', 'reference-summary', line));
    item.append(details);
    const bottom = node('div', 'card-bottom');
    bottom.append(node('span', '', entry.sourceTitle || '출처'));
    try {
      const url = new URL(entry.sourceUrl);
      if (url.protocol === 'https:') { const link = node('a', '', '원문 ↗'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; bottom.append(link); }
    } catch {}
    item.append(bottom);
    return item;
  }
  function renderReferences() {
    const matches = references.filter(entry => referenceMatches(entry, input.value));
    referencesList.replaceChildren();
    for (const entry of matches.slice(0, referencesVisible)) referencesList.append(referenceCard(entry));
    if (!matches.length) {
      const box = node('div', 'empty-state');
      box.append(node('strong', '', '일치하는 참고 자료가 없습니다.'), node('p', '', '모델 코드, 연도 또는 RTX 그래픽카드 이름으로 다시 검색해 보세요.'));
      referencesList.append(box);
    }
    referencesStatus.textContent = '출처가 있는 참고 자료 ' + matches.length + '개' + (input.value.trim() ? ' · “' + input.value.trim() + '”' : '');
    referencesMore.hidden = matches.length <= referencesVisible;
  }
  async function loadReferences() {
    try {
      const response = await fetch('/api/references', { cache: 'no-store' });
      if (!response.ok) throw new Error('참고 자료 요청 실패');
      const data = await response.json();
      references = Array.isArray(data.entries) ? data.entries : [];
      renderReferences();
    } catch { referencesStatus.textContent = '참고 자료를 불러오지 못했습니다. 새로고침해 주세요.'; }
  }
  function empty(title, description) {
    const box = node('div', 'empty-state public-empty');
    box.append(node('strong', '', title), node('p', '', description));
    list.append(box);
  }
  function card(post) {
    const item = node('article', 'profile-card');
    const top = node('div', 'card-top');
    top.append(node('span', '', '공유 설정'), node('span', 'card-date', date(post.createdAt)));
    const h = hardware(post);
    item.append(top, node('h3', '', h.title), node('p', 'card-hardware', h.line || '사양 정보 없음'));
    const scores = node('div', 'card-scores');
    for (const run of latestRuns(post)) scores.append(node('span', '', modeNames[run.mode] + ' ' + score(run)));
    if (!scores.childElementCount) scores.append(node('span', '', '벤치마크 기록 없음'));
    item.append(scores);
    const bottom = node('div', 'card-bottom');
    bottom.append(node('span', '', (post.author || '익명') + ' · ' + (post.profile && post.profile.name || '이름 없음')));
    const open = node('button', '', '설정 자세히 보기 →');
    open.type = 'button';
    open.addEventListener('click', () => show(post));
    bottom.append(open);
    item.append(bottom);
    return item;
  }
  function detailSection(title, parent) {
    const section = node('section', 'detail-section');
    section.append(node('h3', '', title));
    parent.append(section);
    return section;
  }
  function show(post) {
    content.replaceChildren();
    const body = node('div', 'dialog-body');
    content.append(body);
    const h = hardware(post);
    const title = node('h2', '', h.title);
    title.id = 'detail-title';
    body.append(title, node('p', 'dialog-note', (post.profile && post.profile.name || '이름 없음') + ' · ' + (post.author || '익명') + ' · ' + date(post.createdAt)));
    if (post.profile && post.profile.notes) body.append(node('p', 'dialog-note', post.profile.notes));
    const meta = node('div', 'detail-meta');
    for (const value of [h.h.cpu, ...(Array.isArray(h.h.gpu) ? h.h.gpu : []), h.h.ram_gb ? String(h.h.ram_gb) + 'GB RAM' : '', h.h.bios ? 'BIOS ' + h.h.bios : ''].filter(Boolean)) meta.append(node('span', '', value));
    body.append(meta);
    const runs = detailSection('모드별 최근 Time Spy 기록', body);
    const runGrid = node('div', 'detail-grid');
    const best = latestRuns(post);
    if (!best.length) runs.append(node('p', 'dialog-note', '등록된 점수가 없습니다.'));
    for (const run of best) {
      const cell = node('div', 'detail-cell');
      cell.append(node('span', '', modeNames[run.mode]), node('strong', '', score(run)));
      const extras = [run.noiseDbA == null ? '' : String(run.noiseDbA) + ' dB(A)', run.fanRpm == null ? '' : String(run.fanRpm) + ' RPM'].filter(Boolean);
      if (extras.length) cell.append(node('span', '', extras.join(' · ')));
      runGrid.append(cell);
    }
    runs.append(runGrid);
    const settings = detailSection('저장된 G-Helper 설정값', body);
    const values = post.profile && post.profile.settings || {};
    let shown = 0;
    for (const mode of [2, 0, 1]) {
      const suffix = '_' + mode;
      const entries = Object.entries(values).filter(([key]) => key.endsWith(suffix));
      if (!entries.length) continue;
      shown += entries.length;
      const group = node('div', 'detail-mode');
      group.append(node('h4', '', modeNames[mode] + ' 모드'));
      for (const [key, value] of entries) {
        const base = key.slice(0, -suffix.length);
        const row = node('div', 'setting-row');
        const label = base.startsWith('fan_profile_') ? (base.includes('gpu') ? 'GPU 팬 곡선' : 'CPU 팬 곡선') : (settingNames[base] || base);
        const display = settingValue(base, value);
        row.append(node('span', '', label), node('strong', '', display));
        group.append(row);
      }
      settings.append(group);
    }
    if (!shown) settings.append(node('p', 'dialog-note', '등록된 설정값이 없습니다.'));
    settings.append(node('p', 'detail-caution', '팬 곡선의 %는 저장된 설정값이며 실측 RPM이 아닙니다. 게시된 값과 점수는 사용자가 제공한 기록입니다. 다른 기기에 적용하기 전 Windows 앱에서 호환성과 설정 내용을 확인하세요.'));
    dialog.showModal();
  }
  async function load(reset) {
    if (busy && !reset) return;
    const id = ++generation;
    if (reset) { cursor = null; count = 0; list.replaceChildren(); }
    busy = true;
    more.hidden = true;
    status.textContent = '공유 설정을 불러오는 중입니다…';
    try {
      const params = new URLSearchParams({ limit: '18' });
      if (query) params.set('q', query);
      if (cursor) params.set('cursor', cursor);
      const response = await fetch('/api/profiles?' + params.toString(), { cache: 'no-store' });
      if (!response.ok) throw new Error('목록 요청 실패');
      const data = await response.json();
      if (id !== generation) return;
      for (const post of data.posts || []) list.append(card(post));
      count += (data.posts || []).length;
      cursor = data.nextCursor || null;
      if (!count) empty(query ? '사용자가 공유한 설정은 없습니다.' : '아직 공유된 설정이 없습니다.', query ? '아래에서 공식 사양과 Time Spy 참고 기록을 확인하세요.' : 'Windows 앱에서 첫 설정을 공유하면 이곳에 표시됩니다.');
      document.querySelector('#references').classList.toggle('has-no-posts', count === 0);
      status.textContent = query ? '“' + query + '” 검색 결과 ' + count + '개' : '공개 설정 ' + count + '개';
      more.hidden = !cursor;
    } catch {
      if (id !== generation) return;
      if (!count) empty('자료실을 불러오지 못했습니다.', '잠시 후 다시 시도해 주세요.');
      status.textContent = '자료실 연결을 확인해 주세요.';
      more.hidden = !cursor;
    } finally { if (id === generation) busy = false; }
  }
  form.addEventListener('submit', event => { event.preventDefault(); query = input.value.trim(); referencesVisible = 18; renderReferences(); load(true); });
  input.addEventListener('input', () => { referencesVisible = 18; renderReferences(); });
  referencesMore.addEventListener('click', () => { referencesVisible += 18; renderReferences(); });
  more.addEventListener('click', () => load(false));
  document.querySelector('#dialog-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  load(true);
  loadReferences();
})();
`;
