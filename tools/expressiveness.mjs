/**
 * Level 3 validation: expressiveness.
 *
 * Level 0 asks "does this document conform to the schema".
 * Level 3 asks "can the schema represent reality".
 *
 * Those are different questions, and the gap between them is where the
 * expensive mistakes live. A document that validates while silently discarding
 * something real is worse than one that fails, because nothing alerts anyone -
 * the number simply comes out wrong for a reason nobody can see.
 *
 * Every case is classified:
 *   expressible  schema holds the situation fully, and it validates
 *   gap_silent   validates, but reality is lost with no signal   <- act on these
 *   gap_loud     rejected by validation, so it fails visibly
 *
 * Usage: node tools/expressiveness.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const ROOT = path.resolve(import.meta.dirname, '..');
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));

const ajv = new Ajv({ allErrors: true, strict: true });
addFormats(ajv);
const validate = ajv.compile(read('schema/representation.schema.json'));

const suite = read('fixtures/expressiveness.json');

/* Semantic layer, mirroring tools/validate.mjs. A schema cannot express these,
 * so they must be checked in code or malformed perception output gets trusted. */
function semanticErrors(rep) {
  const errs = [];
  const map = [...rep.u_map].sort((a, b) => a.u_from - b.u_from);

  for (const s of map) if (s.u_to < s.u_from) errs.push(`span ${s.u_from}-${s.u_to} inverted`);
  for (let i = 1; i < map.length; i++) {
    if (map[i].u_from <= map[i - 1].u_to) errs.push(`spans overlap at U${map[i].u_from}`);
    else if (map[i].u_from !== map[i - 1].u_to + 1) errs.push(`gap before U${map[i].u_from}`);
  }
  if (map[0].u_from !== 1) errs.push('u_map does not start at U1');

  const total = rep.scale.measured_total_u;
  if (typeof total === 'number') {
    if (map[map.length - 1].u_to !== total) errs.push(`u_map ends at U${map[map.length - 1].u_to}, expected U${total}`);
    const covered = map.reduce((n, m) => n + (m.u_to - m.u_from + 1), 0);
    if (covered !== total) errs.push(`covers ${covered} U, expected ${total}`);
  }
  for (const s of map) {
    if (s.state === 'occupied' && !s.occupied_class) errs.push(`U${s.u_from}-${s.u_to} occupied without occupied_class (OCC-1.0)`);
    if (s.state === 'occluded' && !s.occlusion_cause) errs.push(`U${s.u_from}-${s.u_to} occluded without cause`);
  }
  return errs;
}

const results = [];
console.log('\nExpressiveness test set\n' + '-'.repeat(72));

for (const c of suite.cases) {
  const structOk = validate(c.representation);
  const structErrs = structOk ? [] : ajv.errorsText(validate.errors, { separator: '; ' });
  const semErrs = structOk ? semanticErrors(c.representation) : [];
  const accepted = structOk && semErrs.length === 0;

  let outcome;
  if (c.expectation === 'expressible') outcome = accepted ? 'PASS' : 'UNEXPECTED_REJECT';
  else if (c.expectation === 'gap_loud') outcome = accepted ? 'UNEXPECTED_ACCEPT' : 'PASS';
  else outcome = accepted ? 'SILENT_GAP' : 'GAP_CAUGHT';

  results.push({ ...c, accepted, outcome, structErrs, semErrs });

  const tag = { PASS: 'ok  ', SILENT_GAP: 'GAP ', GAP_CAUGHT: 'ok  ',
                UNEXPECTED_REJECT: 'FAIL', UNEXPECTED_ACCEPT: 'FAIL' }[outcome];
  console.log(`${tag} ${c.case.padEnd(30)} expected=${c.expectation.padEnd(12)} accepted=${accepted}`);
  if (!structOk) console.log(`       structural: ${structErrs}`);
  if (semErrs.length) console.log(`       semantic:   ${semErrs.join('; ')}`);
}

const silent = results.filter((r) => r.outcome === 'SILENT_GAP');
const broken = results.filter((r) => r.outcome.startsWith('UNEXPECTED'));

if (silent.length) {
  console.log('\n' + '='.repeat(72));
  console.log(`${silent.length} SILENT GAPS - schema accepts these but loses information`);
  console.log('='.repeat(72));
  for (const s of silent) {
    console.log(`\n  ${s.case}`);
    console.log(`    situation:   ${s.description}`);
    console.log(`    lost:        ${s.lost_information}`);
    console.log(`    consequence: ${s.consequence}`);
  }
}

console.log('\n' + '-'.repeat(72));
console.log(`  expressible confirmed : ${results.filter((r) => r.expectation === 'expressible' && r.outcome === 'PASS').length}`);
console.log(`  gaps caught loudly    : ${results.filter((r) => r.outcome === 'GAP_CAUGHT' || (r.expectation === 'gap_loud' && r.outcome === 'PASS')).length}`);
console.log(`  SILENT GAPS           : ${silent.length}`);
console.log(`  test-suite errors     : ${broken.length}`);
console.log('-'.repeat(72) + '\n');

/* Silent gaps are findings to act on, not build failures. Only a fixture whose
 * behaviour contradicts its own stated expectation is a failure of the suite. */
process.exit(broken.length === 0 ? 0 : 1);
