# vercel-labs/agent-skills: reference for issues and PRs

## CI/CD contract (regenerated each run)
- `agent-skills-discovery.yml` (Agent Skills Discovery) on pull_request
  - job `validate` runs-on ubuntu-latest needs -: uses actions/checkout@v4 | npm ci --ignore-scripts | node scripts/build-discovery-index.mjs https://example.com/skills
  - job `publish` runs-on ubuntu-latest needs validate: uses actions/checkout@v4 | npm ci --ignore-scripts | node scripts/build-discovery-index.mjs "https://github.com/${{ github.repository }}/releases/download/${RELEASE_TAG}" | gh release view "$RELEASE_TAG" >/dev/null 2>&1 ||
- `react-best-practices-ci.yml` (React Best Practices CI) on pull_request
  - job `validate` runs-on ubuntu-latest needs -: uses actions/checkout@v4 | uses pnpm/action-setup@v2 | uses actions/setup-node@v4 | pnpm install | pnpm validate | pnpm build
- default branch: main; merge methods: unknown
- required status checks: unknown (no access or no protection)
- recent failed PR runs: Agent Skills Discovery: Aagl react standards (https://github.com/vercel-labs/agent-skills/actions/runs/37743922658); React Best Practices CI: Aagl react standards (https://github.com/vercel-labs/agent-skills/actions/runs/37743922689); React Best Practices CI: fix: keep compiled rule links resolvable (https://github.com/vercel-labs/agent-skills/actions/runs/34842676628); Agent Skills Discovery: fix: keep compiled rule links resolvable (https://github.com/vercel-labs/agent-skills/actions/runs/34842676636); Agent Skills Discovery: react-best-practices: add a cross-process caching example to server-cache-lru (https://github.com/vercel-labs/agent-skills/actions/runs/33401459618); React Best Practices CI: react-best-practices: add a cross-process caching example to server-cache-lru (https://github.com/vercel-labs/agent-skills/actions/runs/33401459832); Agent Skills Discovery: feat: add HOL Guard Vercel command safety skill (https://github.com/vercel-labs/agent-skills/actions/runs/32954202553); Agent Skills Discovery: feat: add HOL Guard Vercel command safety skill (https://github.com/vercel-labs/agent-skills/actions/runs/32836530356); React Best Practices CI: docs: fix React skill relative links (https://github.com/vercel-labs/agent-skills/actions/runs/31995876786); React Best Practices CI: fix: rename skill dirs to match frontmatter, surface React Compiler caveat, fix listener/guidelines examples (https://github.com/vercel-labs/agent-skills/actions/runs/30542551087)

## Learnings (append with `learn`)
