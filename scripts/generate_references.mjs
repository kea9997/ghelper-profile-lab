import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const official = {
  2024: 'https://rog.asus.com/us/articles/rog-gaming-laptops/the-complete-list-of-geforce-gpu-power-specifications-for-2024-rog-and-tuf-gaming-laptops/',
  2025: 'https://rog.asus.com/ca-en/articles/rog-gaming-laptops/the-complete-list-of-geforce-gpu-power-specifications-for-2025-rog-and-tuf-gaming-laptops/',
};
const records = [];
// Each row is transcribed from the ASUS model-number and GPU-power tables above.
// 2025 FX608JP is omitted: ASUS lists the same code under both RTX 5070 and 5060.
function add(year, family, models, gpu, turboBase, boost, manualBase = turboBase, cpu = '') {
  for (const model of models.split(' ')) {
    records.push({ year, family, model, gpu, turboBase, boost, manualBase, cpu });
  }
}
add(2024, 'ROG 제피러스 G14', 'GA403UI', 'RTX 4070', 65, 25, 65, 'AMD Ryzen 9 8945HS');
add(2024, 'ROG 제피러스 G14', 'GA403UV', 'RTX 4060', 65, 25);
add(2024, 'ROG 제피러스 G14', 'GA403UU', 'RTX 4050', 65, 25);
add(2024, 'ROG 제피러스 G16', 'GU605MY', 'RTX 4090', 95, 20, 95, 'Intel Core Ultra 9 185H');
add(2024, 'ROG 제피러스 G16', 'GU605MZ', 'RTX 4080', 95, 20, 95, 'Intel Core Ultra 9 185H');
add(2024, 'ROG 제피러스 G16', 'GU605MI', 'RTX 4070', 85, 20, 85, 'Intel Core Ultra 9 185H');
add(2024, 'ROG 제피러스 G16', 'GU605MV', 'RTX 4060', 85, 15);
add(2024, 'ROG 제피러스 G16', 'GU605MU', 'RTX 4050', 85, 15);
add(2024, 'ROG Strix SCAR 16', 'G634JYR', 'RTX 4090', 150, 25);
add(2024, 'ROG Strix SCAR 18', 'G834JYR', 'RTX 4090', 150, 25);
add(2024, 'ROG Strix SCAR 16', 'G634JZR', 'RTX 4080', 150, 25);
add(2024, 'ROG Strix SCAR 18', 'G834JZR', 'RTX 4080', 150, 25);
add(2024, 'ROG Strix G16', 'G614JZR', 'RTX 4080', 150, 25);
add(2024, 'ROG Strix G18', 'G814JZR', 'RTX 4080', 150, 25);
add(2024, 'ROG Strix G16', 'G614JIR', 'RTX 4070', 115, 25, 115, 'Intel Core i9-14900HX');
add(2024, 'ROG Strix G18', 'G814JIR', 'RTX 4070', 115, 25);
add(2024, 'ROG Strix G16', 'G614JVR', 'RTX 4060', 115, 25);
add(2024, 'ROG Strix G18', 'G814JVR', 'RTX 4060', 115, 25);
add(2024, 'TUF Gaming F16', 'FX607JI FX607JIR', 'RTX 4070', 115, 25);
add(2024, 'TUF Gaming F16', 'FX607JV FX607JVR', 'RTX 4060', 105, 25);
add(2024, 'TUF Gaming F16', 'FX607JU', 'RTX 4050', 105, 25);
add(2024, 'TUF Gaming A16', 'FA607PI', 'RTX 4070', 115, 25);
add(2024, 'TUF Gaming A16', 'FA607PV', 'RTX 4060', 115, 25);
add(2024, 'TUF Gaming A15', 'FA507UI', 'RTX 4070', 115, 25);
add(2024, 'TUF Gaming A15', 'FA507UV', 'RTX 4060', 115, 25);
add(2024, 'TUF Gaming A15', 'FA507UU', 'RTX 4050', 115, 25);

add(2025, 'ROG Strix SCAR 16', 'G635LX', 'RTX 5090', 150, 25);
add(2025, 'ROG Strix SCAR 18', 'G835LX', 'RTX 5090', 150, 25);
add(2025, 'ROG Strix SCAR 16', 'G635LW', 'RTX 5080', 150, 25);
add(2025, 'ROG Strix SCAR 18', 'G835LW', 'RTX 5080', 150, 25);
add(2025, 'ROG Strix SCAR 16', 'G635LR', 'RTX 5070 Ti', 115, 25);
add(2025, 'ROG Strix SCAR 18', 'G835LR', 'RTX 5070 Ti', 115, 25);
add(2025, 'ROG Strix G16', 'G615LW', 'RTX 5080', 150, 25);
add(2025, 'ROG Strix G18', 'G815LW', 'RTX 5080', 150, 25);
add(2025, 'ROG Strix G16', 'G615LR G614FR G614PR', 'RTX 5070 Ti', 115, 25);
add(2025, 'ROG Strix G18', 'G815LR', 'RTX 5070 Ti', 115, 25);
add(2025, 'ROG Strix G16', 'G615LP G615JP G614FP', 'RTX 5070', 100, 15);
add(2025, 'ROG Strix G18', 'G815LP G814FP G814PP', 'RTX 5070', 100, 15);
add(2025, 'ROG Strix G16', 'G615LM G615JM G614FM G614PM', 'RTX 5060', 100, 15);
add(2025, 'ROG Strix G18', 'G815LM G815JM G814FM G814PM', 'RTX 5060', 100, 15);
add(2025, 'ROG Strix G16', 'G615JH G615LG G614FH G614PH', 'RTX 5050', 100, 15);
add(2025, 'ROG Strix G18', 'G814PH', 'RTX 5050', 100, 15);
add(2025, 'ROG 제피러스 G16', 'GU605CX', 'RTX 5090', 100, 20, 110, 'Intel Core Ultra 9 285H');
add(2025, 'ROG 제피러스 G16', 'GU605CW', 'RTX 5080', 100, 20, 110, 'Intel Core Ultra 9 285H');
add(2025, 'ROG 제피러스 G16', 'GU605CR', 'RTX 5070 Ti', 95, 20, 105, 'Intel Core Ultra 9 285H');
add(2025, 'ROG 제피러스 G16', 'GU605CP', 'RTX 5070', 90, 15, 95);
add(2025, 'ROG 제피러스 G16', 'GA605KP', 'RTX 5070', 90, 15);
add(2025, 'ROG 제피러스 G16', 'GU605CM', 'RTX 5060', 90, 15, 95);
add(2025, 'ROG 제피러스 G16', 'GA605KM', 'RTX 5060', 90, 15);
add(2025, 'ROG 제피러스 G16', 'GA605KH', 'RTX 5050', 85, 15);
add(2025, 'ROG 제피러스 G14', 'GA403WW', 'RTX 5080', 85, 25, 95);
add(2025, 'ROG 제피러스 G14', 'GA403WR', 'RTX 5070 Ti', 85, 25, 95);
add(2025, 'ROG 제피러스 G14', 'GA403WP GA403UP', 'RTX 5070', 75, 15, 85);
add(2025, 'ROG 제피러스 G14', 'GA403WM GA403UM', 'RTX 5060', 75, 15, 85);
add(2025, 'ROG 제피러스 G14', 'GA403UH', 'RTX 5050', 75, 15, 85);
add(2025, 'TUF Gaming F16', 'FX608LP', 'RTX 5070', 100, 15);
add(2025, 'TUF Gaming F16', 'FX608LM', 'RTX 5060', 100, 15);
add(2025, 'TUF Gaming A16', 'FA608UP FA608PP', 'RTX 5070', 100, 15);
add(2025, 'TUF Gaming A16', 'FA608WM FA608PM', 'RTX 5060', 100, 15);
add(2025, 'TUF Gaming A16', 'FA608JH', 'RTX 5050', 100, 15);
add(2025, 'TUF Gaming A18', 'FA808UP', 'RTX 5070', 100, 15);
add(2025, 'TUF Gaming A18', 'FA808UM', 'RTX 5060', 100, 15);
add(2025, 'TUF Gaming A18', 'FA808UH', 'RTX 5050', 100, 15);
add(2025, 'TUF Gaming A14', 'FA401KM FA401UM', 'RTX 5060', 90, 15, 95);
add(2025, 'TUF Gaming A14', 'FA401KH FA401UH', 'RTX 5050', 90, 15, 95);

const manual = JSON.parse(readFileSync(path.join(root, 'desktop/catalog.manual.json'), 'utf8'));
const community = [
  {
    id: 'ga403ui-timespy-balanced-10413', title: '제피러스 G14 2024 RTX 4070 · 균형 Time Spy 10,413점', model: 'GA403UI', year: 2024,
    family: 'ROG 제피러스 G14', cpu: 'AMD Ryzen 9 8945HS', gpu: 'RTX 4070', sourceType: 'community',
    sourceTitle: 'Reddit · Some thoughts on 2024 G14 power modes and G-Helper',
    sourceUrl: 'https://www.reddit.com/r/ZephyrusG14/comments/1bb78my/some_thoughts_on_2024_g14_power_modes_and_ghelper/',
    summary: '2024 G14 RTX 4070/32GB 사용자의 Time Spy 실측 공유. 균형 모드·CPU 부스트 끔·Optimus 사용.',
    settingsText: 'G-Helper Balanced, CPU boost disabled, Optimus. CPU/GPU 전력 숫자, 팬 곡선, 소음은 원문에 없습니다.',
    timeSpy: { total: 10413, graphics: 10439, cpu: 10271, mode: '균형', conditions: 'CPU 부스트 끔 · Optimus' },
    limitations: '작성자가 밝힌 제품명과 사양을 공식 ASUS 목록의 GA403UI와 대조했습니다. 지역별 하위 SKU는 미확인. 사용자 보고이며 자동 적용 불가.'
  },
  {
    id: 'ga403ui-timespy-turbo-12234', title: '제피러스 G14 2024 RTX 4070 · 터보 Time Spy 12,234점', model: 'GA403UI', year: 2024,
    family: 'ROG 제피러스 G14', cpu: 'AMD Ryzen 9 8945HS', gpu: 'RTX 4070', sourceType: 'community',
    sourceTitle: 'Reddit · G14 2024 / 4070, some initial benchmarks',
    sourceUrl: 'https://www.reddit.com/r/ZephyrusG14/comments/1b799mh/g14_2024_4070_some_initial_benchmarks/',
    summary: 'Turbo/Ultimate, GPU 오버클록, 벤치 중 팬 100% 조건의 Time Spy 사용자 보고.',
    settingsText: 'Turbo/Ultimate, GPU 코어 +210 MHz·메모리 +1000 MHz(작성자 후속 댓글), CPU 제한 기본값 80W, 벤치 중 팬 100%. 원문의 옛 80W GPU 슬라이더는 작성자가 오류라고 정정했습니다.',
    timeSpy: { total: 12234, graphics: 12322, cpu: 11767, mode: '터보', conditions: 'Ultimate · GPU +210/+1000 MHz · 팬 100% · 주변 약 18°C' },
    limitations: '최대 성능 벤치 설정이며 일상 사용 권장값이 아닙니다. CPU 언더볼트 -30은 원문의 Cinebench 조건이므로 이 Time Spy 조건에 포함하지 않습니다. 자동 적용 불가.'
  },
  {
    id: 'ga403wr-timespy-turbo-14902', title: '제피러스 G14 2025 RTX 5070 Ti · 터보 Time Spy 14,902점', model: 'GA403WR', year: 2025,
    family: 'ROG 제피러스 G14', cpu: '', gpu: 'RTX 5070 Ti', sourceType: 'community',
    sourceTitle: 'Reddit · My G14 5070Ti Everyday Turbo GHelper Settings and TimeSpy Results',
    sourceUrl: 'https://www.reddit.com/r/ZephyrusG14/comments/1n81n8z/my_g14_5070ti_everyday_turbo_ghelper_settings_and/',
    summary: 'G-Helper Turbo와 기본 팬 곡선, Llano V10 냉각 패드 1,200 RPM 조건의 Time Spy 사용자 보고.',
    settingsText: 'G-Helper Turbo, 기본 팬 곡선. 작성자는 세부 튜닝을 사진으로 올렸으나 텍스트에서 숫자 설정을 확인하지 못했습니다.',
    timeSpy: { total: 14902, graphics: null, cpu: null, mode: '터보', conditions: 'Llano V10 냉각 패드 1,200 RPM · 기본 팬 곡선 · GPU 평균 74°C/CPU 평균 84°C' },
    limitations: '냉각 패드 RPM은 노트북 팬 RPM이 아닙니다. 작성자의 모델 코드는 없으나 ASUS 공식 표의 2025 G14 RTX 5070 Ti 조합은 GA403WR입니다. 자동 적용 불가.'
  }
];
const generated = records.map(r => {
  const turbo = r.turboBase + r.boost, manualMax = r.manualBase + r.boost;
  const summary = `ASUS 공식 사양: ${r.family} ${r.year} ${r.model} · ${r.gpu} · 최대 GPU 전력 Turbo ${turbo}W / Manual ${manualMax}W.`;
  return {
    id: `asus-${r.year}-${r.model.toLowerCase()}-gpu-spec`,
    title: `${r.family} ${r.year} ${r.gpu} · ${r.model}`,
    model: r.model, year: r.year, family: r.family, cpu: r.cpu, gpu: r.gpu,
    status: 'reference', sourceType: 'official',
    sourceTitle: `ASUS ROG · ${r.year} GPU 전력 사양표`, sourceUrl: official[r.year], sourceDate: null,
    summary,
    settingsText: r.year === 2024
      ? `공식 GPU TGP ${r.turboBase}W + Dynamic Boost ${r.boost}W = 최대 ${turbo}W. G-Helper 조용·균형·터보 모드의 CPU/팬 설정값은 이 표에 없습니다.`
      : `공식 GPU TGP Turbo ${r.turboBase}W / Manual ${r.manualBase}W + Dynamic Boost ${r.boost}W = 최대 ${turbo}W / ${manualMax}W. G-Helper CPU/팬 설정값은 이 표에 없습니다.`,
    limitations: 'ASUS 하드웨어 전력 사양입니다. G-Helper 전력 슬라이더의 권장 입력값이 아니며, 지역별 SKU·BIOS·동작 모드에 따라 다를 수 있습니다. 자동 적용 불가.'
  };
});
const catalog = { schemaVersion: 2, updatedAt: '2026-09-25', entries: [...community, ...manual.entries, ...generated] };
for (const entry of catalog.entries) {
  if (!entry.sourceUrl?.startsWith('https://') || !entry.model || entry.status === 'applyable') throw Error(`Invalid reference ${entry.id}`);
  entry.status = 'reference';
}
const ids = catalog.entries.map(x => x.id);
if (new Set(ids).size !== ids.length) throw Error('Duplicate reference ID');
const json = JSON.stringify(catalog, null, 2) + '\n';
const module = `// Generated by scripts/generate_references.mjs. Edit the source script or desktop/catalog.manual.json.\nexport const CATALOG = ${JSON.stringify(catalog)};\n`;
const targets = [[path.join(root, 'desktop/catalog.json'), json], [path.join(root, 'api/catalog-data.mjs'), module]];
if (process.argv.includes('--check')) {
  for (const [file, expected] of targets) if (readFileSync(file, 'utf8') !== expected) throw Error(`Out of date: ${file}`);
} else {
  for (const [file, contents] of targets) writeFileSync(file, contents);
}
console.log(`References: ${catalog.entries.length} (${generated.length} ASUS, ${community.length} Time Spy, ${manual.entries.length} existing)`);
