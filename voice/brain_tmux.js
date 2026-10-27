// A quiet pause during tool work is not completion: wait for Claude's turn-end record.
const fs = require('fs');
const { execFileSync } = require('child_process');
const { active } = require('./active.js');
const TMUX = '/data/data/com.termux/files/usr/bin/tmux';
const SOCKET = '/data/data/com.termux/files/usr/var/run/tmux-10435/vapi-line';
function tmux(args) {
  return execFileSync(TMUX, ['-S', SOCKET, ...args], {encoding:'utf8', timeout:5000, stdio:['pipe','pipe','pipe']});
}
function ask(jsonlArg, text, callbacks, timeoutMs = 0, target = active()) {
  const {onDelta, onDone} = callbacks;
  const jsonl = jsonlArg || target.jsonl;
  let cursor = 0, finished = false, iv, lastCheck = 0, seenInput = false;
  let finalText = '', lastText = '', terminalReason = '';
  const input = String(text).replace(/\s*\n\s*/g, ' ').trim();
  const started = Date.now();
  const fin = (answer, state, error) => {
    if (finished) return;
    finished = true; clearInterval(iv);
    if (state === 'completed' && onDelta) onDelta(answer);
    onDone(answer, {state, error});
  };
  try {
    if (!jsonl) throw new Error('The brain transcript is not known.');
    tmux(['has-session','-t',target.tmux]);
    if(tmux(['display-message','-p','-t',target.tmux,'#{pane_dead}']).trim()!=='0') throw new Error('The brain process stopped.');
    cursor = fs.existsSync(jsonl) ? fs.statSync(jsonl).size : 0;
    tmux(['send-keys','-t',target.tmux,'-l',input]);
    tmux(['send-keys','-t',target.tmux,'Enter']);
  } catch (e) {
    fin('The brain did not accept the request.', 'failed', e.message); return;
  }
  iv = setInterval(() => {
    try {
      if (Date.now() - lastCheck > 5000) {
        tmux(['has-session','-t',target.tmux]);
    if(tmux(['display-message','-p','-t',target.tmux,'#{pane_dead}']).trim()!=='0') throw new Error('The brain process stopped.'); lastCheck = Date.now();
      }
      if (fs.existsSync(jsonl)) {
        const size = fs.statSync(jsonl).size;
        if (size < cursor) throw new Error('The brain transcript was replaced.');
        if (size > cursor) {
          const fd = fs.openSync(jsonl, 'r');
          const buf = Buffer.alloc(size - cursor);
          try { fs.readSync(fd, buf, 0, buf.length, cursor); } finally { fs.closeSync(fd); }
          const boundary = buf.lastIndexOf(10);
          if (boundary >= 0) {
            cursor += boundary + 1;
            for (const line of buf.subarray(0,boundary+1).toString('utf8').split('\n')) {
              if (!line.trim()) continue;
              let row; try { row = JSON.parse(line); } catch (_) { continue; }
              const msg = row.message || {}, content = msg.content;
              if (row.type === 'user' && !seenInput) {
                const userText = typeof content === 'string' ? content : (content || []).filter(b=>b.type==='text').map(b=>b.text).join('\n');
                if (userText.includes(input)) seenInput = true;
              }
              if (!seenInput) continue;
              if (row.type === 'assistant' && Array.isArray(content)) {
                const reply = content.filter(b=>b.type==='text').map(b=>b.text).join('\n').trim();
                if (reply) lastText = reply;
                terminalReason = msg.stop_reason || '';
                finalText = terminalReason === 'end_turn' ? reply : '';
              }
              if (row.type === 'system' && row.subtype === 'turn_duration') {
                if (finalText) return fin(finalText, 'completed');
                return fin(lastText || 'The brain stopped without a final answer.', 'incomplete', terminalReason || 'no final answer');
              }
            }
          }
        }
      }
      if (timeoutMs > 0 && Date.now() - started > timeoutMs)
        return fin('The brain has not finished. Its work was not cancelled.', 'incomplete', 'deadline');
    } catch (e) { fin('The connection to the brain stopped. Completion is not confirmed.', 'failed', e.message); }
  }, 300);
}
module.exports = { ask, tmux };
