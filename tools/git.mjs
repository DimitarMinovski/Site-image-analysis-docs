/**
 * Version control without Apple's git.
 *
 * /usr/bin/git on this machine refuses to run until the Xcode licence is
 * accepted (`sudo xcodebuild -license`), and there is no Homebrew git. Rather
 * than block on a sudo prompt, this uses isomorphic-git - a pure JavaScript
 * git implementation - so commits work today and pushes work as soon as a
 * token is present.
 *
 * Everything it writes is a standard .git directory. Once the licence is
 * accepted, ordinary `git` commands operate on the same repository with no
 * conversion.
 *
 * Commands
 *   node tools/git.mjs init                 initialise repo + set remote
 *   node tools/git.mjs status               list changed / untracked files
 *   node tools/git.mjs commit "<message>"   stage everything and commit
 *   node tools/git.mjs push                 push main to origin
 *   node tools/git.mjs log [n]              recent history
 *   node tools/git.mjs save "<message>"     commit then push
 *
 * Auth: a GitHub token read from
 *   ~/.config/site-image-analysis/github-token
 * or the GITHUB_TOKEN environment variable. The file is outside the repository
 * on purpose, so it cannot be committed. It is never printed by this tool.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import git from 'isomorphic-git';
import http from 'isomorphic-git/http/node/index.js';

const dir = path.resolve(import.meta.dirname, '..');
const REMOTE = 'https://github.com/DimitarMinovski/Site-image-analysis-docs.git';
const BRANCH = 'main';
const TOKEN_FILE = path.join(os.homedir(), '.config', 'site-image-analysis', 'github-token');

/* Commits are attributed to the agent rather than to a human, so the history
 * plainly shows which changes were machine-authored. Override with
 * GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL if you prefer. */
const author = {
  name: process.env.GIT_AUTHOR_NAME || 'Kiro CLI',
  email: process.env.GIT_AUTHOR_EMAIL || 'kiro-cli@localhost'
};

function readToken() {
  if (process.env.GITHUB_TOKEN) return process.env.GITHUB_TOKEN.trim();
  if (fs.existsSync(TOKEN_FILE)) {
    const t = fs.readFileSync(TOKEN_FILE, 'utf8').trim();
    if (t) return t;
  }
  return null;
}

const onAuth = () => {
  const token = readToken();
  if (!token) {
    console.error(
      '\nNo GitHub token found.\n\n' +
      '  mkdir -p ~/.config/site-image-analysis\n' +
      '  printf %s "<your-token>" > ~/.config/site-image-analysis/github-token\n' +
      '  chmod 600 ~/.config/site-image-analysis/github-token\n\n' +
      'Needs a fine-grained token with Contents: read and write on\n' +
      'DimitarMinovski/Site-image-analysis-docs (or a classic token with repo scope).\n'
    );
    process.exit(2);
  }
  return { username: token, password: 'x-oauth-basic' };
};

/* Files tracked in the repo, honouring .gitignore. isomorphic-git has no
 * "add everything" primitive, so walk the tree ourselves. */
const IGNORE_DIRS = new Set(['.git', 'node_modules', 'tmp', 'out', '.vscode', '.idea']);
function listFiles(base = dir, rel = '') {
  const out = [];
  for (const entry of fs.readdirSync(path.join(base, rel), { withFileTypes: true })) {
    const r = rel ? path.join(rel, entry.name) : entry.name;
    if (entry.isDirectory()) {
      if (IGNORE_DIRS.has(entry.name)) continue;
      out.push(...listFiles(base, r));
    } else {
      if (entry.name === '.DS_Store' || entry.name.startsWith('._')) continue;
      if (entry.name.endsWith('.token') || entry.name.endsWith('.log')) continue;
      if (entry.name === '.env' || entry.name.startsWith('.env.')) continue;
      out.push(r);
    }
  }
  return out.sort();
}

async function cmdInit() {
  if (!fs.existsSync(path.join(dir, '.git'))) {
    await git.init({ fs, dir, defaultBranch: BRANCH });
    console.log(`initialised empty repository on ${BRANCH}`);
  } else {
    console.log('repository already initialised');
  }
  const remotes = await git.listRemotes({ fs, dir });
  if (!remotes.find((r) => r.remote === 'origin')) {
    await git.addRemote({ fs, dir, remote: 'origin', url: REMOTE });
    console.log(`remote origin -> ${REMOTE}`);
  } else {
    console.log(`remote origin already set -> ${remotes.find((r) => r.remote === 'origin').url}`);
  }
}

async function cmdStatus() {
  const files = listFiles();
  const rows = [];
  for (const f of files) {
    const s = await git.status({ fs, dir, filepath: f });
    if (s !== 'unmodified') rows.push([s, f]);
  }
  if (!rows.length) { console.log('clean - nothing to commit'); return rows; }
  for (const [s, f] of rows) console.log(`  ${s.padEnd(22)} ${f}`);
  console.log(`\n  ${rows.length} file(s) changed`);
  return rows;
}

async function cmdCommit(message) {
  if (!message) { console.error('commit needs a message'); process.exit(1); }

  // "@path" reads the message from a file, avoiding shell quoting problems
  // with long multi-line messages.
  if (message.startsWith('@')) {
    const p = message.slice(1);
    if (!fs.existsSync(p)) { console.error(`message file not found: ${p}`); process.exit(1); }
    message = fs.readFileSync(p, 'utf8').trim();
    if (!message) { console.error(`message file is empty: ${p}`); process.exit(1); }
  }

  const files = listFiles();
  for (const f of files) await git.add({ fs, dir, filepath: f });

  // stage deletions of files git knows about but that no longer exist
  const tracked = await git.listFiles({ fs, dir });
  for (const f of tracked) {
    if (!fs.existsSync(path.join(dir, f))) {
      await git.remove({ fs, dir, filepath: f });
      console.log(`  removed  ${f}`);
    }
  }

  const sha = await git.commit({ fs, dir, message, author });
  console.log(`committed ${sha.slice(0, 8)}  ${message.split('\n')[0]}`);
  console.log(`  ${files.length} file(s) tracked`);
  return sha;
}

async function cmdPush() {
  const res = await git.push({
    fs, http, dir, remote: 'origin', ref: BRANCH, onAuth
  });
  if (res.ok) console.log(`pushed ${BRANCH} -> origin`);
  else console.error('push rejected:', JSON.stringify(res.errors ?? res));
  if (!res.ok) process.exit(1);
}

async function cmdLog(n = 10) {
  const commits = await git.log({ fs, dir, depth: Number(n) });
  for (const c of commits) {
    const d = new Date(c.commit.author.timestamp * 1000).toISOString().slice(0, 16).replace('T', ' ');
    console.log(`  ${c.oid.slice(0, 8)}  ${d}  ${c.commit.message.split('\n')[0]}`);
  }
}

const [cmd, arg] = process.argv.slice(2);
try {
  if (cmd === 'init') await cmdInit();
  else if (cmd === 'status') await cmdStatus();
  else if (cmd === 'commit') await cmdCommit(arg);
  else if (cmd === 'push') await cmdPush();
  else if (cmd === 'log') await cmdLog(arg ?? 10);
  else if (cmd === 'save') { await cmdCommit(arg); await cmdPush(); }
  else {
    console.log('usage: node tools/git.mjs <init|status|commit|push|log|save> ["message"]');
    process.exit(1);
  }
} catch (e) {
  console.error(`\n${cmd} failed: ${e.message}`);
  if (e.data) console.error(JSON.stringify(e.data, null, 2));
  process.exit(1);
}
