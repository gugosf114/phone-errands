// Authenticated Vapi custom speech endpoint. Model settings stay unchanged.
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
let starting;
let child;
function health() {
  return new Promise((resolve) => {
    const request = http.get('http://127.0.0.1:8793/health', response => {
      let body = '';
      response.on('data', data => body += data);
      response.on('end', () => {
        try { const data = JSON.parse(body); resolve(data.ready && data.voice === 'majestic-george'); }
        catch (_) { resolve(false); }
      });
    });
    request.setTimeout(1000, () => request.destroy());
    request.on('error', () => resolve(false));
  });
}
async function ready() {
  if (await health()) return;
  if (!starting) starting = (async () => {
    child = spawn('/root/.local/share/phone-errands-voices/venv/bin/python',
      ['-u', path.join(__dirname, 'majestic_tts.py')], {stdio: ['ignore', 'pipe', 'pipe']});
    let failure;
    child.on('error', error => { failure = error; });
    child.stdout.on('data', data => console.log('MAJESTIC ' + data.toString().trim()));
    child.stderr.on('data', data => console.error('MAJESTIC ' + data.toString().slice(-800).trim()));
    for (let i = 0; i < 100; i++) {
      if (failure) throw failure;
      if (await health()) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('Majestic model did not become ready');
  })().catch(error => { starting = undefined; throw error; });
  return starting;
}
async function handle(req, res, key) {
  if (!key || req.headers['x-line-key'] !== key) {
    res.writeHead(401); res.end('no'); return;
  }
  try {
    if (req.method === 'GET') {
      await ready();
      const upstream = http.get('http://127.0.0.1:8793/health', response => {
        res.writeHead(response.statusCode, {'Content-Type': 'application/json'});
        response.pipe(res);
      });
      upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end(); });
      return;
    }
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 65536) { res.writeHead(413); res.end('too big'); return; }
      chunks.push(chunk);
    }
    const body = Buffer.concat(chunks);
    await ready();
    const upstream = http.request({hostname: '127.0.0.1', port: 8793, path: '/tts', method: 'POST',
      headers: {'Content-Type': 'application/json', 'Content-Length': body.length}}, response => {
      res.writeHead(response.statusCode, {'Content-Type': response.headers['content-type'] || 'application/octet-stream',
        'Cache-Control': 'no-store'});
      response.pipe(res);
    });
    upstream.setTimeout(20000, () => upstream.destroy());
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end(); });
    res.on('close', () => upstream.destroy());
    upstream.end(body);
  } catch (error) {
    console.error('MAJESTIC endpoint: ' + error.message);
    if (!res.headersSent) res.writeHead(503);
    res.end('Majestic speech unavailable');
  }
}
process.on('exit', () => { if (child) child.kill(); });
module.exports = {handle};
