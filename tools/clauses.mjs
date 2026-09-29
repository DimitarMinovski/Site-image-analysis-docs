/**
 * Clause catalogue: validation and rendering.
 *
 * The catalogue JSON is the single source of truth. Section 6 of the rubric
 * markdown is generated from it, so the prose and the machine-readable
 * definition cannot drift apart - which is the usual failure once a domain
 * expert edits markdown and an engineer edits code.
 *
 * The most valuable check here is closure: every representation field a clause
 * claims to read must actually exist in representation.schema.json. That
 * catches a clause referring to data the perception layer never produces,
 * which would otherwise surface as a clause that silently never fires.
 *
 *   node tools/clauses.mjs check    validate the catalogue
 *   node tools/clauses.mjs render   regenerate section 6 of the rubric
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const CAT = 'docs/rubrics/CAB-FREE-SPACE.clauses.json';
const MD = 'docs/rubrics/CAB-FREE-SPACE.md';
const SCHEMA = 'schema/representation.schema.json';

const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const cat = read(CAT);
const schema = read(SCHEMA);

let failures = 0;
const ok = (m) => console.log(`  PASS  ${m}`);
const bad = (m, d) => { failures++; console.log(`  FAIL  ${m}`); if (d) console.log(`        ${d}`); };
const warn = (m) => console.log(`  WARN  ${m}`);

/* Walk a JSON Schema by dotted path, stepping through array items. */
function resolves(dotted) {
  let node = schema;
  for (const seg of dotted.split('.')) {
    if (node.type === 'array' || (Array.isArray(node.type) && node.type.includes('array'))) node = node.items;
    if (!node?.properties?.[seg]) return false;
    node = node.properties[seg];
  }
  return true;
}

function check() {
  const clauses = cat.clauses;
  const active = clauses.filter((c) => c.status === 'active');
  const candidates = clauses.filter((c) => c.status === 'candidate');

  console.log(`\nClause catalogue ${cat.catalogue} v${cat.catalogue_version}`);
  console.log(`  ${active.length} active, ${candidates.length} candidate, ${clauses.length} total\n`);

  console.log('Structure');
  const ids = clauses.map((c) => c.id);
  new Set(ids).size === ids.length
    ? ok('clause ids are unique')
    : bad('clause ids are unique', ids.filter((id, i) => ids.indexOf(id) !== i).join(', '));

  const prefixes = Object.keys(cat.id_rules.prefixes);
  const badIds = ids.filter((id) => {
    const m = /^([A-Z]+)-(\d+)\.(\d+)$/.exec(id);
    return !m || !prefixes.includes(m[1]);
  });
  badIds.length === 0
    ? ok(`all ids match PREFIX-major.minor with a known prefix`)
    : bad('id format and prefix', badIds.join(', '));

  const required = ['id', 'status', 'title', 'requirement', 'rationale', 'authority',
                    'observable', 'evaluated_by', 'severity', 'affects_verdict', 'remedy', 'added_in'];
  const missing = [];
  for (const c of clauses) for (const f of required) if (c[f] === undefined) missing.push(`${c.id}.${f}`);
  missing.length === 0 ? ok('all clauses carry the required fields') : bad('required fields', missing.join(', '));

  console.log('\nConsistency');
  const sev = Object.keys(cat.severity_scale);
  const badSev = clauses.filter((c) => !sev.includes(c.severity)).map((c) => c.id);
  badSev.length === 0 ? ok('severities are on the declared scale') : bad('severity values', badSev.join(', '));

  const evalKinds = ['policy_engine', 'vlm_judgement', 'flag_only'];
  const badEval = clauses.filter((c) => !evalKinds.includes(c.evaluated_by)).map((c) => c.id);
  badEval.length === 0 ? ok('evaluated_by values are valid') : bad('evaluated_by values', badEval.join(', '));

  /* A clause that affects the verdict must name the decision-table row it
   * drives, otherwise a verdict cannot be traced back to a written rule. */
  const verdictMismatch = clauses.filter((c) =>
    (c.affects_verdict && (c.verdict_rule === null || c.verdict_rule === undefined)) ||
    (!c.affects_verdict && c.verdict_rule)).map((c) => c.id);
  verdictMismatch.length === 0
    ? ok('affects_verdict agrees with verdict_rule')
    : bad('affects_verdict agrees with verdict_rule', verdictMismatch.join(', '));

  /* Something unobservable cannot be deterministically evaluated. */
  const obsMismatch = clauses.filter((c) => !c.observable && c.evaluated_by !== 'flag_only').map((c) => c.id);
  obsMismatch.length === 0
    ? ok('unobservable clauses are flag_only')
    : bad('unobservable clauses are flag_only', obsMismatch.join(', '));

  const deprecated = clauses.filter((c) => c.status === 'deprecated');
  deprecated.every((c) => c.superseded_by)
    ? ok('deprecated clauses name a successor')
    : bad('deprecated clauses name a successor');

  console.log('\nClosure against representation schema');
  const unresolved = [];
  for (const c of clauses) for (const p of c.inputs ?? []) if (!resolves(p)) unresolved.push(`${c.id} -> ${p}`);
  unresolved.length === 0
    ? ok('every clause input exists in representation.schema.json')
    : bad('every clause input exists in representation.schema.json', unresolved.join('\n        '));

  const noInputs = clauses.filter((c) => !(c.inputs ?? []).length).map((c) => c.id);
  noInputs.length === 0 ? ok('every clause declares its inputs') : warn(`no inputs declared: ${noInputs.join(', ')}`);

  console.log('\nSign-off readiness');
  const unverified = active.filter((c) => c.authority?.status === 'unverified');
  if (unverified.length) {
    warn(`${unverified.length} active clause(s) have unverified authority - blocking for sign-off:`);
    for (const c of unverified) console.log(`          ${c.id.padEnd(14)} ${c.title}`);
  } else ok('every active clause cites a verified or internal authority');

  const openThresholds = active.filter((c) =>
    c.threshold && Object.entries(c.threshold).some(([k, v]) => v === null && k !== 'note'));
  if (openThresholds.length) warn(`${openThresholds.length} active clause(s) have unset thresholds: ${openThresholds.map((c) => c.id).join(', ')}`);
  else ok('no unset thresholds on active clauses');

  console.log(`\n${failures === 0 ? 'CATALOGUE VALID' : `${failures} FAILURE(S)`}`);
  console.log(`(warnings are sign-off items, not build failures)\n`);
  return failures;
}

function render() {
  const rows = cat.clauses
    .filter((c) => c.status === 'active')
    .map((c) => {
      const det = c.observable ? (c.evaluated_by === 'vlm_judgement' ? 'Interpretive' : 'Yes') : 'No - flag only';
      const auth = c.authority.status === 'unverified' ? '**TBD**' : c.authority.source;
      const v = c.affects_verdict ? `rule ${c.verdict_rule}` : '-';
      return `| \`${c.id}\` | ${c.title} | ${det} | ${c.severity} | ${v} | ${auth} |`;
    });

  const cand = cat.clauses.filter((c) => c.status === 'candidate')
    .map((c) => `| \`${c.id}\` | ${c.title} | ${c.authority.source} |`);

  const body = [
    '<!-- CLAUSES:BEGIN - generated by tools/clauses.mjs, do not edit by hand -->',
    '',
    `Generated from \`CAB-FREE-SPACE.clauses.json\` v${cat.catalogue_version}.`,
    'Stable IDs. Findings cite these, and citations may reach customer-facing',
    'reports, so **never renumber a clause** - deprecate and add.',
    '',
    '| Clause | Requirement | Image-determinable | Severity | Verdict | Authority |',
    '|---|---|---|---|---|---|',
    ...rows,
    '',
    ...(cand.length ? [
      '### Candidates, not yet active',
      '',
      'Harvested from recorded field root causes. Each needs a data source and',
      'sign-off before activation.',
      '',
      '| Clause | Requirement | Derived from |',
      '|---|---|---|',
      ...cand,
      ''
    ] : []),
    `**TBD** authority means the governing specification has not yet been cited.`,
    `${cat.clauses.filter((c) => c.status === 'active' && c.authority.status === 'unverified').length} active clause(s) are in that state and must be resolved before sign-off:`,
    'a clause without an authority is an opinion with a reference number.',
    '',
    '<!-- CLAUSES:END -->'
  ].join('\n');

  const md = fs.readFileSync(path.join(ROOT, MD), 'utf8');
  const re = /<!-- CLAUSES:BEGIN[\s\S]*?<!-- CLAUSES:END -->/;
  if (!re.test(md)) { console.error(`No CLAUSES markers found in ${MD}`); process.exit(1); }
  fs.writeFileSync(path.join(ROOT, MD), md.replace(re, body));
  console.log(`rendered ${rows.length} active + ${cand.length} candidate clause(s) into ${MD}`);
}

const cmd = process.argv[2] ?? 'check';
if (cmd === 'check') process.exit(check() === 0 ? 0 : 1);
else if (cmd === 'render') render();
else { console.log('usage: node tools/clauses.mjs <check|render>'); process.exit(1); }
