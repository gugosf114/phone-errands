// The ACTIVE phone room. tmux name from active.txt; transcript resolved LIVE from the
// running claude process in that room (so the pointer can never go stale).
const fs = require('fs');
const { execFileSync } = require('child_process');
const ACTIVE = '/root/.vapi/bridge/active.txt';
function active() {
  let tmux = 'brain';
  try { tmux = (fs.readFileSync(ACTIVE, 'utf8').split('\n')[0] || 'brain').trim(); } catch (e) {}
  let jsonl = '';
  try { jsonl=(fs.readFileSync(ACTIVE,'utf8').split('\n')[1]||'').trim(); } catch(e) {}
  if(jsonl) return {tmux,jsonl};
  try {
    const out = execFileSync('bash', ['-lc',
      `for p in $(pgrep -f ' -n ${tmux}$' 2>/dev/null; pgrep -f ' -n ${tmux} ' 2>/dev/null); do tr '\\0' ' ' </proc/$p/cmdline 2>/dev/null; echo; done`],
      { encoding: 'utf8' });
    const m = out.match(/--session-id ([0-9a-f-]{36})/);
    if (m) jsonl = '/root/.claude/projects/-root/' + m[1] + '.jsonl';
  } catch (e) {}
  return { tmux, jsonl };
}
module.exports = { active };
