/* A local PNG for sharing a captured Time Spy comparison. Nothing is uploaded. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ScoreCard = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const MODES = [{id: 2, name: '조용'}, {id: 0, name: '균형'}, {id: 1, name: '터보'}];
  const valid = run => run && run.binding === 'captured' && run.status === 'valid' &&
    typeof run.settingsHash === 'string' && run.settingsHash.length > 0 &&
    Number.isFinite(run.totalScore) && run.totalScore > 0 && MODES.some(mode => mode.id === run.mode);
  const text = (value, fallback) => typeof value === 'string' && value.trim() ? value.trim() : fallback;
  const number = value => Number(value).toLocaleString('ko-KR');

  function build(runs, hardware) {
    const sorted = [...(runs || [])].filter(valid).sort((a, b) =>
      String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
    if (!sorted.length) return null;
    const matching = sorted.filter(run => run.settingsHash === sorted[0].settingsHash);
    const modes = MODES.map(mode => ({...mode, run: matching.find(run => run.mode === mode.id) || null}));
    const best = modes.filter(mode => mode.run).reduce((a, b) =>
      !a || b.run.totalScore > a.run.totalScore ? b : a, null);
    const gpu = Array.isArray(hardware?.gpu) ? hardware.gpu.find(Boolean) : hardware?.gpu;
    return {
      model: text(hardware?.model, 'ASUS 노트북'),
      cpu: text(hardware?.cpu, 'CPU 정보 없음'),
      gpu: text(gpu, 'GPU 정보 없음'),
      modes, best,
      date: text(sorted[0].createdAt, ''),
    };
  }

  function ellipsis(ctx, value, maxWidth) {
    const input = String(value);
    if (ctx.measureText(input).width <= maxWidth) return input;
    let result = input;
    while (result && ctx.measureText(result + '…').width > maxWidth) result = result.slice(0, -1);
    return result + '…';
  }

  function rounded(ctx, x, y, width, height, radius, fill) {
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.roundRect(x, y, width, height, radius);
    ctx.fill();
  }

  function draw(ctx, data) {
    if (!data?.best) throw new Error('이미지로 저장할 점수가 없습니다.');
    const w = 1200, h = 675;
    const bg = ctx.createLinearGradient(0, 0, w, h);
    bg.addColorStop(0, '#12242a'); bg.addColorStop(.55, '#101b27'); bg.addColorStop(1, '#0c121e');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    ctx.save(); ctx.globalAlpha = .16; ctx.fillStyle = '#6fe7b4';
    ctx.beginPath(); ctx.arc(1110, -70, 290, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    rounded(ctx, 54, 45, 45, 45, 12, '#a9f1d2');
    ctx.fillStyle = '#14352b'; ctx.font = '800 27px "Segoe UI", sans-serif'; ctx.fillText('G', 67, 77);
    ctx.fillStyle = '#ecf8f4'; ctx.font = '700 23px "Segoe UI", "Malgun Gothic", sans-serif';
    ctx.fillText('G-Helper Profile Lab', 113, 77);
    ctx.textAlign = 'right'; ctx.fillStyle = '#a6c6c3'; ctx.font = '600 18px "Segoe UI", sans-serif';
    ctx.fillText('3DMARK  /  TIME SPY', 1147, 76); ctx.textAlign = 'left';

    ctx.fillStyle = '#a9f1d2'; ctx.font = '700 20px "Segoe UI", "Malgun Gothic", sans-serif';
    ctx.fillText('내 노트북 성능 기록', 56, 150);
    ctx.fillStyle = '#f3f8f7'; ctx.font = '800 40px "Segoe UI", "Malgun Gothic", sans-serif';
    ctx.fillText(ellipsis(ctx, data.model, 1090), 54, 203);
    ctx.fillStyle = '#abc1c8'; ctx.font = '18px "Segoe UI", "Malgun Gothic", sans-serif';
    ctx.fillText(ellipsis(ctx, data.cpu + '  ·  ' + data.gpu, 1090), 56, 238);

    ctx.fillStyle = '#9cb9b5'; ctx.font = '700 18px "Segoe UI", "Malgun Gothic", sans-serif';
    ctx.fillText('최고 점수  ·  ' + data.best.name, 56, 314);
    ctx.fillStyle = '#a9f1d2'; ctx.font = '800 110px "Segoe UI", sans-serif';
    ctx.fillText(number(data.best.run.totalScore), 48, 414);
    ctx.fillStyle = '#abc1c8'; ctx.font = '16px "Segoe UI", "Malgun Gothic", sans-serif';
    ctx.fillText('같은 G-Helper 설정으로 측정한 모드별 Time Spy 결과', 56, 448);

    data.modes.forEach((mode, index) => {
      const x = 54 + index * 373, y = 476;
      rounded(ctx, x, y, 354, 135, 16, mode.id === data.best.id ? '#25483f' : '#1b3039');
      ctx.fillStyle = mode.id === data.best.id ? '#baf6dc' : '#a9c6c6';
      ctx.font = '700 18px "Segoe UI", "Malgun Gothic", sans-serif'; ctx.fillText(mode.name, x + 21, y + 33);
      ctx.fillStyle = '#f2faf6'; ctx.font = '750 36px "Segoe UI", sans-serif';
      ctx.fillText(mode.run ? number(mode.run.totalScore) : '—', x + 20, y + 77);
      ctx.fillStyle = '#aec8c7'; ctx.font = '14px "Segoe UI", "Malgun Gothic", sans-serif';
      const noise = mode.run && Number.isFinite(mode.run.noiseDbA) ? mode.run.noiseDbA + ' dBA' : '소음 미입력';
      const fan = mode.run && Number.isFinite(mode.run.fanRpm) ? number(mode.run.fanRpm) + ' RPM' : '팬 미입력';
      ctx.fillText(mode.run ? noise + '  ·  ' + fan : '아직 측정하지 않음', x + 21, y + 109);
    });
    ctx.fillStyle = '#94aeb6'; ctx.font = '14px "Segoe UI", "Malgun Gothic", sans-serif';
    const date = data.date && Number.isFinite(Date.parse(data.date)) ? new Date(data.date).toLocaleDateString('ko-KR') + '  ·  ' : '';
    ctx.fillText(date + '소음·팬 속도는 사용자가 입력한 값 · 점수는 사용자 기록', 56, 648);
    ctx.textAlign = 'right'; ctx.fillText('ghelper.optiwork.co.kr', 1147, 648); ctx.textAlign = 'left';
  }

  async function png(runs, hardware, canvasFactory = () => document.createElement('canvas')) {
    const data = build(runs, hardware);
    if (!data) throw new Error('먼저 Time Spy 비교를 완료해 주세요.');
    const canvas = canvasFactory(); canvas.width = 1200; canvas.height = 675;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('이미지 기능을 사용할 수 없습니다.');
    draw(ctx, data);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('이미지를 만들지 못했습니다.');
    return {blob, fileName: 'TimeSpy-' + String(hardware?.model || 'ASUS').replace(/[^a-zA-Z0-9가-힣_-]+/g, '-').slice(0, 48) + '.png'};
  }

  return {build, draw, png};
});
