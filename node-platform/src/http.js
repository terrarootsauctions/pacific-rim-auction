// MINIMAL HTTP ROUTER - Node built-ins only, so the only npm dependency is `pg`.
const http = require('http');
const fs = require('fs');
const path = require('path');

const MAX_BODY = 1024 * 1024;
const SEC = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'Cache-Control': 'no-store',
};

function createApp() {
  const routes = [];
  const add = (method) => (pattern, ...handlers) => {
    const keys = [];
    const re = new RegExp('^' + pattern.replace(/:([A-Za-z]+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '/?$');
    routes.push({ method, re, keys, handlers });
  };

  function send(res, status, body, type = 'application/json; charset=utf-8') {
    const payload = typeof body === 'string' ? body : JSON.stringify(body);
    res.writeHead(status, { ...SEC, 'Content-Type': type, 'Content-Length': Buffer.byteLength(payload) });
    res.end(payload);
  }

  function readBody(req) {
    return new Promise((resolve, reject) => {
      let size = 0; const chunks = [];
      req.on('data', (c) => { size += c.length; if (size > MAX_BODY) { reject(Object.assign(new Error('BODY_TOO_LARGE'), { status: 413 })); req.destroy(); } else chunks.push(c); });
      req.on('end', () => {
        if (!chunks.length) return resolve({});
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
        catch (_) { reject(Object.assign(new Error('INVALID_JSON'), { status: 400 })); }
      });
      req.on('error', reject);
    });
  }

  const handler = async (req, res) => {
    try {
      const url = new URL(req.url, 'http://x');
      req.path = url.pathname; req.query = Object.fromEntries(url.searchParams);
      res.json = (status, body) => send(res, status, body);
      if (req.method === 'GET' || req.method === 'HEAD') {
        const pub = staticFile(req.path);
        if (pub) return send(res, 200, pub.body, pub.type);
      }
      for (const r of routes) {
        if (r.method !== req.method) continue;
        const m = r.re.exec(req.path); if (!m) continue;
        req.params = {}; r.keys.forEach((k, i) => (req.params[k] = decodeURIComponent(m[i + 1])));
        if (req.method === 'POST') req.body = await readBody(req); else req.body = {};
        for (const h of r.handlers) { let nextCalled = false; await h(req, res, () => { nextCalled = true; }); if (!nextCalled) return; }
        return;
      }
      send(res, 404, { ok: false, reason: 'NOT_FOUND' });
    } catch (e) {
      const status = e.status || 500;
      if (status === 500) console.error('REQUEST_ERROR', req.method, req.url, e.message);
      if (!res.headersSent) send(res, status, { ok: false, reason: status === 500 ? 'INTERNAL_ERROR_ACTION_NOT_PERFORMED' : e.message });
    }
  };

  return { get: add('GET'), post: add('POST'), handler, listen: (port, cb) => { const s = http.createServer(handler); s.listen(port, '0.0.0.0', cb); return s; } };
}

const PUBLIC = path.join(__dirname, '..', 'public');
const PAGES = { '/': 'index.html', '/index.html': 'index.html', '/admin': 'admin.html', '/admin.html': 'admin.html' };
function staticFile(p) {
  const f = PAGES[p]; if (!f) return null;
  try { return { body: fs.readFileSync(path.join(PUBLIC, f), 'utf8'), type: 'text/html; charset=utf-8' }; } catch (_) { return null; }
}

module.exports = { createApp };
