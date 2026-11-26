// TEST-ONLY database driver. This workspace cannot install the `pg` package, so tests talk to a
// real local PostgreSQL through the `psql` command. Same SQL, same locking, same transactions.
// Production never loads this file - it uses `pg` (see src/db.js).
const { spawn } = require('child_process');
let counter = 0;

function lit(v) {
  if (v === null || v === undefined) return 'NULL';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
  return "'" + String(v).replace(/'/g, "''") + "'";
}
function bind(sql, params = []) { return sql.replace(/\$(\d+)/g, (_, n) => lit(params[Number(n) - 1])); }
function wrap(sql) {
  const t = sql.trim().replace(/;$/, '');
  if (/^(insert|update|delete)/i.test(t) && /returning/i.test(t)) return `WITH q AS (${t}) SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) FROM q`;
  if (/^select/i.test(t) && !/pg_advisory/i.test(t)) return `SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) FROM (${t}) t`;
  return t;
}

class Client {
  constructor(conn) {
    this.p = spawn('sh', ['-c', `psql -X -q -A -t -h ${conn.host} -p ${conn.port} -U ${conn.user} -d ${conn.db} 2>&1`]);
    this.buf = ''; this.waiting = null; this.queue = Promise.resolve();
    this.p.stdout.on('data', (d) => { this.buf += d.toString(); this._drain(); });
  }
  _drain() {
    if (!this.waiting) return;
    const m = this.buf.indexOf(`@@END${this.waiting.id}@@`);
    if (m < 0) return;
    const out = this.buf.slice(0, m); this.buf = this.buf.slice(m).replace(/^@@END\d+@@\n?/, '');
    const w = this.waiting; this.waiting = null;
    if (/^(ERROR|FATAL):/m.test(out)) return w.reject(new Error(out.trim()));
    let rows = [];
    const line = out.trim().split('\n').filter(Boolean).pop();
    if (line && (line.startsWith('[') || line.startsWith('{'))) { try { rows = JSON.parse(line); } catch (_) {} }
    w.resolve({ rows, rowCount: rows.length });
  }
  query(text, params) {
    const run = () => new Promise((resolve, reject) => {
      const id = ++counter; this.waiting = { id, resolve, reject };
      this.p.stdin.write(wrap(bind(text, params)) + ';\n\\echo @@END' + id + '@@\n');
    });
    this.queue = this.queue.then(run, run);
    return this.queue;
  }
  release() { this.free = true; }
  end() { try { this.p.stdin.end(); } catch (_) {} }
}

class Pool {
  constructor(conn) { this.conn = conn; this.clients = []; }
  async connect() { const c = this.clients.find((x) => x.free); if (c) { c.free = false; return c; } const n = new Client(this.conn); this.clients.push(n); return n; }
  async query(text, params) { const c = await this.connect(); try { return await c.query(text, params); } finally { c.release(); } }
  async end() { this.clients.forEach((c) => c.end()); }
}
module.exports = { Pool };
