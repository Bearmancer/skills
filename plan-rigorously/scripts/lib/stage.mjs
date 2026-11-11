// Stage derivation and edit-scope matching. Pure; knows nothing about any harness.
import {
  approvalIsValid, check1, check2, check3, intentIsSigned, lightCheck,
} from './checks.mjs';
import { hasGlob, matchesPathSpec, normRel } from './paths.mjs';

/**
 * parsed = result of parsePlan, or null when there is no plan.md.
 * Returns none | invalid | light | light-invalid | intent | drafting | build.
 */
export function deriveStage(parsed, state, ctx) {
  if (!parsed) return 'none';
  if (!parsed.ok) return 'invalid';
  const { plan } = parsed;
  if (plan.path === 'light') return lightCheck(plan, ctx).length === 0 ? 'light' : 'light-invalid';
  if (!intentIsSigned(plan, state)) return 'intent';
  if (!approvalIsValid(plan, state)) return 'drafting';
  return 'build';
}

/**
 * Is `rel` (repo-relative, any separators) an allowed edit target in this stage? A wildcard entry
 * never covers a file that matches a risk pattern (`.env.local`, a lockfile...); only an exact entry can.
 */
export function inScope(stage, plan, rel, riskPatterns = []) {
  if (stage === 'light') return plan.files.some((f) => matchesPathSpec(f, rel));
  if (stage === 'build') {
    const risky = riskPatterns.some((re) => re.test(normRel(rel)));
    const covers = (f) => matchesPathSpec(f, rel) && !(risky && hasGlob(f));
    return plan.tasks.some((t) => t.edits.some(covers) || t.creates.some(covers));
  }
  return false;
}

/** What the next checkpoint still lacks, as plain gap sentences. */
export function nextGaps(stage, parsed, ctx) {
  if (stage === 'invalid') return parsed.errors;
  const { plan } = parsed;
  switch (stage) {
    case 'light-invalid':
      return lightCheck(plan, ctx);
    case 'intent':
      return check1(plan, ctx);
    case 'drafting':
      return [...check2(plan, ctx), ...check3(plan, ctx)];
    case 'build':
      return plan.tasks.filter((t) => !t.done).map((t) => `${t.id} is not done yet.`);
    default:
      return [];
  }
}

export function nextStepText(stage, plan) {
  switch (stage) {
    case 'invalid':
      return 'repair plan.md so it parses';
    case 'light':
      return 'edit only the files listed in the plan';
    case 'light-invalid':
      return 'rewrite the plan as path: full';
    case 'intent':
      return 'settle the open questions with the user, then ask the `Sign intent` question';
    case 'drafting':
      return 'finish the spec, claims and tasks, run both reviews, then ask the `Approve plan` question';
    case 'build': {
      const left = plan.tasks.filter((t) => !t.done).length;
      return left === 0 ? 'every task is done; ask the `Close plan` question' : `carry out the remaining tasks (${left} of ${plan.tasks.length} left)`;
    }
    default:
      return 'write .rigor/plan.md';
  }
}
