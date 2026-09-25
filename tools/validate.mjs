/**
 * Validates the Step 2 contract artefacts.
 *
 * Two layers of checking, because JSON Schema alone is not enough:
 *
 *   1. Structural - the examples conform to their schemas.
 *   2. Semantic   - invariants a schema cannot express: that the U map covers
 *                   every position exactly once, that the assessment's
 *                   arithmetic actually follows from the representation, and
 *                   that every cited clause exists in the rubric.
 *
 * The clause check matters more than it looks: it is what stops the rubric and
 * the code drifting apart silently, which is the usual failure mode once a
 * rubric starts being edited by a domain expert and the code by an engineer.
 *
 * Usage: node tools/validate.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
// 2020-12 entry point. Ajv's default export only knows draft-07, and our
// schemas declare $schema: draft/2020-12.
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const ROOT = path.resolve(import.meta.dirname, '..');
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const readText = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

let failures = 0;
const ok = (m) => console.log(`  PASS  ${m}`);
const bad = (m, detail) => { failures++; console.log(`  FAIL  ${m}`); if (detail) console.log(`        ${detail}`); };

const ajv = new Ajv({ allErrors: true, strict: true });
addFormats(ajv);

/* ---------- 1. structural ------------------------------------------------ */
console.log('\nStructural validation');

const repSchema = read('schema/representation.schema.json');
const assSchema = read('schema/assessment.schema.json');
const rep = read('examples/representation.example.json');
const ass = read('examples/assessment.example.json');

for (const [name, schema, doc] of [
  ['representation', repSchema, rep],
  ['assessment', assSchema, ass]
]) {
  let validate;
  try { validate = ajv.compile(schema); }
  catch (e) { bad(`${name} schema compiles`, e.message); continue; }
  ok(`${name} schema compiles`);
  if (validate(doc)) ok(`${name} example conforms`);
  else bad(`${name} example conforms`, ajv.errorsText(validate.errors, { separator: '\n        ' }));
}

/* ---------- 2. semantic: the U map ---------------------------------------- */
console.log('\nU map invariants');

const map = [...rep.u_map].sort((a, b) => a.u_from - b.u_from);
const totalU = rep.scale.measured_total_u;

let contiguous = map[0].u_from === 1;
for (let i = 1; i < map.length; i++) {
  if (map[i].u_from !== map[i - 1].u_to + 1) { contiguous = false; break; }
}
contiguous && map[map.length - 1].u_to === totalU
  ? ok(`u_map covers 1..${totalU} with no gaps or overlaps`)
  : bad('u_map covers every position exactly once');

const span = (s) => map.filter((m) => m.state === s).reduce((n, m) => n + (m.u_to - m.u_from + 1), 0);
const counts = {
  occupied: span('occupied'), blanked: span('blanked'),
  open: span('open'), occluded: span('occluded')
};
const sum = Object.values(counts).reduce((a, b) => a + b, 0);
sum === totalU
  ? ok(`state counts sum to total_u (${sum})`)
  : bad('state counts sum to total_u', `got ${sum}, expected ${totalU}`);

/* every occupied span must carry a class - fail-closed rule OCC-1.0 */
map.filter((m) => m.state === 'occupied').every((m) => m.occupied_class)
  ? ok('every occupied span carries an occupied_class (OCC-1.0)')
  : bad('every occupied span carries an occupied_class');

/* ---------- 3. semantic: assessment arithmetic ---------------------------- */
console.log('\nAssessment arithmetic');

const M = ass.measurements;
const expect = (label, actual, wanted) => actual === wanted
  ? ok(`${label} = ${actual}`)
  : bad(label, `got ${actual}, expected ${wanted}`);

expect('total_u', M.total_u, totalU);
expect('occupied_u', M.occupied_u, counts.occupied);
expect('blanked_u', M.blanked_u, counts.blanked);
expect('open_u', M.open_u, counts.open);
expect('occluded_u', M.occluded_u, counts.occluded);
expect('free_u = blanked + open', M.free_u, counts.blanked + counts.open);

/* occluded must never be counted as free - the dangerous error */
M.free_u + M.occupied_u + M.occluded_u === M.total_u
  ? ok('occluded U excluded from free_u (OCC-2.0)')
  : bad('occluded U excluded from free_u');

/* largest contiguous run of available (blanked|open) positions */
let run = 0, best = 0;
for (let u = 1; u <= totalU; u++) {
  const seg = map.find((m) => u >= m.u_from && u <= m.u_to);
  if (seg && (seg.state === 'blanked' || seg.state === 'open')) { run++; best = Math.max(best, run); }
  else run = 0;
}
expect('largest_contiguous_free_u', M.largest_contiguous_free_u, best);

const usable = M.free_runs.filter((r) => r.usable).reduce((n, r) => n + (r.u_to - r.u_from + 1), 0);
expect('usable_free_u = sum of usable runs', M.usable_free_u, usable);

M.free_runs.every((r) => r.usable === (r.excluded_reason === null))
  ? ok('every excluded run states a reason')
  : bad('every excluded run states a reason');

/* free_runs must lie within available positions */
M.free_runs.every((r) => {
  for (let u = r.u_from; u <= r.u_to; u++) {
    const seg = map.find((m) => u >= m.u_from && u <= m.u_to);
    if (!seg || (seg.state !== 'blanked' && seg.state !== 'open')) return false;
  }
  return true;
})
  ? ok('free_runs fall only on available positions')
  : bad('free_runs fall only on available positions');

/* ---------- 4. semantic: uncertainty and verdict -------------------------- */
console.log('\nUncertainty and verdict');

const U = ass.uncertainty;
U.free_u_low <= M.free_u && M.free_u <= U.free_u_high
  ? ok('free_u lies inside its uncertainty interval')
  : bad('free_u lies inside its uncertainty interval');

U.free_u_high - U.free_u_low >= M.occluded_u
  ? ok('interval width accounts for occluded U')
  : bad('interval width accounts for occluded U',
        `width ${U.free_u_high - U.free_u_low} < occluded ${M.occluded_u}`);

!U.verdict_stable_across_interval && ass.verdict.value !== 'borderline'
  ? bad('unstable verdict must be reported as borderline (rule 4)')
  : ok('verdict stability consistent with verdict value');

(ass.verdict.value === 'abstained') === (ass.verdict.abstain_reason !== null)
  ? ok('abstain_reason present exactly when abstained')
  : bad('abstain_reason present exactly when abstained');

/* ---------- 5. semantic: clauses exist in the rubric ---------------------- */
console.log('\nRubric clause integrity');

const rubric = readText('docs/rubrics/CAB-FREE-SPACE.md');
const declared = new Set([...rubric.matchAll(/`([A-Z]{3,8}-\d+\.\d+)`/g)].map((m) => m[1]));
declared.size > 0 ? ok(`rubric declares ${declared.size} clause ids`) : bad('rubric declares clause ids');

const cited = new Set([
  ...ass.findings.map((f) => f.clause_id),
  ...(ass.not_determinable ?? []).map((n) => n.clause_id)
]);
const unknown = [...cited].filter((c) => !declared.has(c));
unknown.length === 0
  ? ok(`all ${cited.size} cited clauses exist in the rubric`)
  : bad('all cited clauses exist in the rubric', `unknown: ${unknown.join(', ')}`);

/* ---------- summary ------------------------------------------------------- */
console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`}\n`);
process.exit(failures === 0 ? 0 : 1);
