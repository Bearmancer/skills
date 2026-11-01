# vercel-labs/skills: reference for issues and PRs

## CI/CD contract (regenerated each run)
- `agents.yml` (Agents CI) on pull_request
  - job `validate-agents` runs-on ubuntu-latest needs -: Checkout repository: uses actions/checkout@v6 | Setup pnpm: uses pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271 | Setup Node.js: uses actions/setup-node@v6 | Install dependencies: pnpm install --frozen-lockfile | Validate agents: node scripts/validate-agents.ts
  - job `sync-agents` runs-on ubuntu-latest needs validate-agents: Checkout repository: uses actions/checkout@v6 | Setup pnpm: uses pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271 | Setup Node.js: uses actions/setup-node@v6 | Install dependencies: pnpm install --frozen-lockfile | Sync agents: pnpm exec node scripts/sync-agents.ts | Commit changes: git config --local user.email "github-actions[bot]@users.noreply.github.com" | Push changes: git push
- `ci.yml` (CI) on pull_request
  - job `checks` runs-on ${{ matrix.os }} needs -: Checkout repo: uses actions/checkout@v6 | Setup pnpm: uses pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271 | Setup Node: uses actions/setup-node@v6 | Install dependencies: pnpm install --frozen-lockfile | Build: pnpm build | Prettier: pnpm format:check | Tests: pnpm test
  - job `typecheck` runs-on ubuntu-latest needs -: Checkout repo: uses actions/checkout@v6 | Setup pnpm: uses pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271 | Setup Node: uses actions/setup-node@v6 | Install dependencies: pnpm install --frozen-lockfile | Type check: pnpm type-check
- default branch: main; merge methods: unknown
- required status checks: unknown (no access or no protection)
- recent failed PR runs: CI: Enable board collaboration for PR workflows (https://github.com/vercel-labs/skills/actions/runs/39285403844); CI: feat: preselect Grok Build with the default install agents (https://github.com/vercel-labs/skills/actions/runs/37689603231); CI: fix(update): keep path-scoped locked copies when names repeat (https://github.com/vercel-labs/skills/actions/runs/37608568730); CI: fix(update): preserve existing global skill destinations (https://github.com/vercel-labs/skills/actions/runs/37437804227); CI: Record global installs from a local path in the skill lock (https://github.com/vercel-labs/skills/actions/runs/36471377256); CI: fix: skip unchanged project skills in `skills update` (https://github.com/vercel-labs/skills/actions/runs/36471351071); CI: fix: treat Pi as a universal (.agents/skills) agent (https://github.com/vercel-labs/skills/actions/runs/36471322044); Agents CI: fix: treat Pi as a universal (.agents/skills) agent (https://github.com/vercel-labs/skills/actions/runs/36471321757); CI: Codespace fantastic space cod 6v96qqg6xprvh4jw4 (https://github.com/vercel-labs/skills/actions/runs/36268691230); CI: fix: use `~/.agents/skills` for Codex global skills (https://github.com/vercel-labs/skills/actions/runs/36117175141)
- policy file: .github\RELEASE_TEMPLATE.md
- policy file: .github\ISSUE_TEMPLATE\agent-request.yml
- policy file: .github\ISSUE_TEMPLATE\bug-report.yml
- policy file: .github\ISSUE_TEMPLATE\config.yml
- policy file: .github\ISSUE_TEMPLATE\feature-request.yml

## Learnings (append with `learn`)
