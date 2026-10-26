import fs from 'node:fs';
const p = 'C:/Users/Leandro/.pi/agent/settings.json';
const MODEL = 'openrouter/deepseek/deepseek-v4.1-flash';
try {
  // 1. backup
  const bak = p + '.bak-20261023-betatester-v41';
  if (!fs.existsSync(bak)) fs.copyFileSync(p, bak);
  // 2. load
  const raw = fs.readFileSync(p, 'utf8');
  let s;
  try { s = JSON.parse(raw); } catch (e) { throw new Error('settings.json is not valid JSON: ' + e.message); }
  s.subagents = s.subagents || {};
  s.subagents.modelScope = s.subagents.modelScope || {};
  // 3. global allow list
  s.subagents.modelScope.allow = s.subagents.modelScope.allow || [];
  if (!s.subagents.modelScope.allow.includes(MODEL)) s.subagents.modelScope.allow.push(MODEL);
  // 4. agent-specific entry
  s.subagents.modelScope.agents = s.subagents.modelScope.agents || {};
  const rule = s.subagents.modelScope.agents['deepseek-v4.1-flash-betatester'] || { allow: [] };
  for (const m of [MODEL, 'openrouter/deepseek/deepseek-v4-flash']) {
    if (!rule.allow.includes(m)) rule.allow.push(m);
  }
  s.subagents.modelScope.agents['deepseek-v4.1-flash-betatester'] = rule;
  fs.writeFileSync(p, JSON.stringify(s, null, 2) + '\n');
  console.log('PATCHED (idempotent). backup at', bak);
  console.log('global allow count:', s.subagents.modelScope.allow.length, '| v4.1 present:', s.subagents.modelScope.allow.includes(MODEL));
  console.log('agent rule:', JSON.stringify(rule));
} catch (err) {
  console.error('FAILED:', err.message);
  process.exit(1);
}
