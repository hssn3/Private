'use strict';

/**
 * Backup Vault - a small token-protected file manager.
 *
 * Designed to run on Railway with a Volume mounted at DATA_DIR (default /data).
 * The Windows backup app streams .zip archives here; the browser UI lets you
 * log in with the same token and download the newest archive after a disaster.
 */

const crypto = require('crypto');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const express = require('express');

const PORT = Number(process.env.PORT) || 3000;
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const MAX_BACKUPS = Math.max(1, Number(process.env.MAX_BACKUPS) || 10);
const TOKEN = process.env.BACKUP_TOKEN || '';
const COOKIE_NAME = 'vault_session';

if (!TOKEN) {
  console.error('[fatal] BACKUP_TOKEN is not set. Refusing to start an open file server.');
  process.exit(1);
}
if (TOKEN.length < 16) {
  console.warn('[warn] BACKUP_TOKEN is shorter than 16 characters. Use a long random value.');
}

fs.mkdirSync(DATA_DIR, { recursive: true });

const app = express();
app.disable('x-powered-by');
app.set('trust proxy', true);

/* ------------------------------------------------------------------ auth */

function safeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}

function readCookie(req, name) {
  const raw = req.headers.cookie;
  if (!raw) return null;
  for (const part of raw.split(';')) {
    const idx = part.indexOf('=');
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) {
      return decodeURIComponent(part.slice(idx + 1).trim());
    }
  }
  return null;
}

function presentedToken(req) {
  const header = req.get('x-auth-token');
  if (header) return header.trim();
  const auth = req.get('authorization');
  if (auth && auth.toLowerCase().startsWith('bearer ')) return auth.slice(7).trim();
  const cookie = readCookie(req, COOKIE_NAME);
  if (cookie) return cookie;
  return '';
}

function requireAuth(req, res, next) {
  if (safeEqual(presentedToken(req), TOKEN)) return next();
  res.status(401).json({ ok: false, error: 'unauthorized' });
}

/* ------------------------------------------------------------- file utils */

// Only allow a flat namespace of simple archive names - no traversal, no
// subdirectories, no surprises.
const NAME_RE = /^[A-Za-z0-9._-]{1,180}$/;

function safeName(name) {
  const raw = String(name || '').trim();
  // Reject anything that is not already a bare filename rather than silently
  // basename()-ing it - a caller sending "../../etc/passwd" has a bug or bad
  // intentions, and either way should get an error instead of a surprise.
  if (raw !== path.basename(raw)) return null;
  if (!NAME_RE.test(raw)) return null;
  if (raw === '.' || raw === '..') return null;
  return raw;
}

async function listBackups() {
  const entries = await fsp.readdir(DATA_DIR, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    if (entry.name.endsWith('.part')) continue;
    try {
      const st = await fsp.stat(path.join(DATA_DIR, entry.name));
      files.push({ name: entry.name, size: st.size, mtime: st.mtimeMs });
    } catch {
      /* file vanished between readdir and stat - ignore */
    }
  }
  files.sort((a, b) => b.mtime - a.mtime);
  return files;
}

/**
 * The "cycle rule": keep at most MAX_BACKUPS archives. Anything older than the
 * newest MAX_BACKUPS is deleted permanently so the volume never fills up.
 */
async function enforceCycleRule() {
  const files = await listBackups();
  const doomed = files.slice(MAX_BACKUPS);
  const removed = [];
  for (const file of doomed) {
    try {
      await fsp.unlink(path.join(DATA_DIR, file.name));
      removed.push(file.name);
    } catch (err) {
      console.warn('[rotate] could not delete %s: %s', file.name, err.message);
    }
  }
  if (removed.length) console.log('[rotate] removed %d old backup(s): %s', removed.length, removed.join(', '));
  return removed;
}

/* ----------------------------------------------------------------- routes */

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'backup-vault', maxBackups: MAX_BACKUPS });
});

app.post('/api/login', express.json({ limit: '8kb' }), (req, res) => {
  const token = (req.body && req.body.token) || '';
  if (!safeEqual(token, TOKEN)) {
    return res.status(401).json({ ok: false, error: 'invalid token' });
  }
  const secure = req.protocol === 'https' ? '; Secure' : '';
  res.setHeader(
    'Set-Cookie',
    `${COOKIE_NAME}=${encodeURIComponent(TOKEN)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000${secure}`
  );
  res.json({ ok: true });
});

app.post('/api/logout', (_req, res) => {
  res.setHeader('Set-Cookie', `${COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`);
  res.json({ ok: true });
});

app.get('/api/session', (req, res) => {
  res.json({ ok: safeEqual(presentedToken(req), TOKEN) });
});

app.get('/api/files', requireAuth, async (_req, res) => {
  try {
    const files = await listBackups();
    const total = files.reduce((sum, f) => sum + f.size, 0);
    res.json({ ok: true, files, totalSize: total, maxBackups: MAX_BACKUPS });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

/**
 * Streaming upload. The client POSTs the raw archive bytes with the target
 * name in the query string:  POST /api/upload?name=backup_0_20260826.zip
 * Written to <name>.part first, then renamed, so a half-finished transfer can
 * never be mistaken for a good backup.
 */
app.post('/api/upload', requireAuth, async (req, res) => {
  const name = safeName(req.query.name);
  if (!name) {
    return res.status(400).json({ ok: false, error: 'invalid or missing ?name=' });
  }

  const finalPath = path.join(DATA_DIR, name);
  const tempPath = `${finalPath}.part`;
  const expected = Number(req.get('content-length')) || 0;
  let written = 0;

  const out = fs.createWriteStream(tempPath);
  let failed = false;

  const abort = async (code, message) => {
    if (failed) return;
    failed = true;
    out.destroy();
    try { await fsp.unlink(tempPath); } catch { /* nothing to clean */ }
    if (!res.headersSent) res.status(code).json({ ok: false, error: message });
  };

  req.on('data', (chunk) => { written += chunk.length; });
  req.on('aborted', () => abort(400, 'upload aborted by client'));
  req.on('error', (err) => abort(400, `request error: ${err.message}`));
  out.on('error', (err) => abort(500, `write error: ${err.message}`));

  req.pipe(out);

  out.on('close', async () => {
    if (failed) return;
    if (expected && written !== expected) {
      return abort(400, `size mismatch: expected ${expected}, received ${written}`);
    }
    if (written === 0) {
      return abort(400, 'empty upload');
    }
    try {
      await fsp.rename(tempPath, finalPath);
      const removed = await enforceCycleRule();
      console.log('[upload] stored %s (%d bytes)', name, written);
      res.json({ ok: true, name, size: written, removed });
    } catch (err) {
      await abort(500, err.message);
    }
  });
});

app.get('/api/download/:name', requireAuth, (req, res) => {
  const name = safeName(req.params.name);
  if (!name) return res.status(400).json({ ok: false, error: 'invalid name' });
  const target = path.join(DATA_DIR, name);
  if (!fs.existsSync(target)) return res.status(404).json({ ok: false, error: 'not found' });
  res.download(target, name);
});

app.delete('/api/files/:name', requireAuth, async (req, res) => {
  const name = safeName(req.params.name);
  if (!name) return res.status(400).json({ ok: false, error: 'invalid name' });
  try {
    await fsp.unlink(path.join(DATA_DIR, name));
    res.json({ ok: true });
  } catch (err) {
    const code = err.code === 'ENOENT' ? 404 : 500;
    res.status(code).json({ ok: false, error: err.message });
  }
});

app.use(express.static(path.join(__dirname, 'public'), { maxAge: '1h' }));

app.use((_req, res) => res.status(404).json({ ok: false, error: 'not found' }));

app.listen(PORT, '0.0.0.0', () => {
  console.log('[boot] backup vault listening on :%d', PORT);
  console.log('[boot] data dir: %s (keeping %d backups)', DATA_DIR, MAX_BACKUPS);
  if (!path.isAbsolute(DATA_DIR) || DATA_DIR === path.join(__dirname, 'data')) {
    console.warn('[boot] DATA_DIR is local to the container. On Railway, mount a Volume and set DATA_DIR to it.');
  }
});
