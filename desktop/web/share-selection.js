/* Select a saved setting and its latest verified result for each mode. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ShareSelection = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const modes = [{id: 2, name: '조용'}, {id: 0, name: '균형'}, {id: 1, name: '터보'}];
  const stamp = row => Number.isFinite(Date.parse(row.createdAt)) ? Date.parse(row.createdAt) : 0;
  const sameHardware = (a, b) => a && b && ['manufacturer', 'model', 'cpu', 'gpu', 'ram_gb', 'bios']
    .every(key => JSON.stringify(a[key]) === JSON.stringify(b[key]));
  function defaultBase(profiles, hardware) {
    const compatible = [...(profiles || [])].filter(p => sameHardware(p.hardware, hardware))
      .sort((a, b) => stamp(b) - stamp(a));
    return compatible.find(p => p.origin === 'local') || compatible[0] || null;
  }
  function eligible(run, profile, mode) {
    return profile && run.mode === mode && ['captured', 'manual'].includes(run.binding) &&
      run.status === 'valid' && run.settingsHash && run.settingsHash === profile.settingsHash &&
      (run.binding !== 'manual' || run.profileId === profile.id) &&
      Number.isFinite(run.graphicsScore) && run.graphicsScore > 0 &&
      Number.isFinite(run.cpuScore) && run.cpuScore > 0;
  }
  function plan(profiles, runs, base, choices = {}) {
    const candidates = [...(profiles || [])].filter(p => base && sameHardware(p.hardware, base.hardware))
      .sort((a, b) => stamp(b) - stamp(a));
    const sorted = [...(runs || [])].sort((a, b) => stamp(b) - stamp(a));
    return modes.map(mode => {
      const newest = sorted.find(r => candidates.some(p => p.origin === 'local' && p.id === r.profileId && eligible(r, p, mode.id)));
      const profile = candidates.find(p => p.id === choices[mode.id]) ||
        candidates.find(p => p.id === newest?.profileId) || candidates.find(p => p.id === base?.id) || null;
      const run = sorted.find(r => eligible(r, profile, mode.id) && candidates.some(p =>
        p.id === r.profileId && p.origin === 'local' && eligible(r, p, mode.id))) || null;
      return {...mode, candidates, profile, run};
    });
  }
  return {plan, defaultBase};
});
