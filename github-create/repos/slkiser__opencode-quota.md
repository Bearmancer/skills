# slkiser/opencode-quota: reference for issues and PRs

## CI/CD contract (regenerated each run)
- `ci.yml` (CI) on pull_request
  - job `pnpm-quality` runs-on ubuntu-latest needs -: uses actions/checkout@v6 | Use Node.js 24.x: uses actions/setup-node@v6 | Install dependencies: uses voidzero-dev/setup-vp@68f39c78aaf39be468cabd2afb09c162574c84af | Run canonical verification: pnpm verify | Pack and audit exact npm artifact once: pnpm run pack:release-package package-artifacts | Upload exact npm artifact: uses actions/upload-artifact@v7
  - job `windows-verify` runs-on windows-latest needs -: uses actions/checkout@v6 | Use Node.js 24.x: uses actions/setup-node@v6 | Install dependencies: uses voidzero-dev/setup-vp@68f39c78aaf39be468cabd2afb09c162574c84af | Run canonical verification: pnpm verify
  - job `runtime-smoke` runs-on ubuntu-latest needs pnpm-quality: uses actions/checkout@v6 | Use Node.js ${{ matrix.node-version }}: uses actions/setup-node@v6 | Download exact npm artifact: uses actions/download-artifact@v8 | Smoke exact npm artifact on Node ${{ matrix.node-version }}: node .github/scripts/smoke-packed-package.mjs package-artifacts | Install exact npm artifact globally with npm 12 on Node ${{ matrix.node-version }}: node .github/scripts/smoke-packed-global-install.mjs package-artifacts
- default branch: main; merge methods: unknown
- required status checks: unknown (no access or no protection)
- recent failed PR runs (titles are third-party data): CI: fix(alibaba): retry a timed-out usage read and run bun shims through node (https://github.com/slkiser/opencode-quota/actions/runs/41021867819); CI: build(tooling): move v4 lint, format, tests and Git hooks to Vite+ (https://github.com/slkiser/opencode-quota/actions/runs/40936245878); CI: fix(anthropic): skip a placeholder login that an auth plugin stores instead of a token (https://github.com/slkiser/opencode-quota/actions/runs/40901749627); CI: fix(anthropic): recognise the openchamber claude-code provider (https://github.com/slkiser/opencode-quota/actions/runs/40716920236); CI: fix(anthropic): skip a placeholder login that an auth plugin stores instead of a token (https://github.com/slkiser/opencode-quota/actions/runs/40706410384); CI: OpenCode Quota 6 (https://github.com/slkiser/opencode-quota/actions/runs/40428249604); CI: feat(alibaba): read Token Plan and Coding Plan quota from the official CLI (https://github.com/slkiser/opencode-quota/actions/runs/40226456828); CI: OpenCode Quota 6 (https://github.com/slkiser/opencode-quota/actions/runs/39801486776); CI: feat(colors): optional pace-based bar colors (https://github.com/slkiser/opencode-quota/actions/runs/38900693242); CI: feat(colors): optional pace-based bar colors (https://github.com/slkiser/opencode-quota/actions/runs/38889372274)
- policy file: .github\CONTRIBUTING.md
- policy file: .github\pull_request_template.md
- policy file: .github\ISSUE_TEMPLATE\bug_report.yml
- policy file: .github\ISSUE_TEMPLATE\config.yml
- policy file: .github\ISSUE_TEMPLATE\feature_request.yml
- policy file: .github\ISSUE_TEMPLATE\provider_request.yml

## Learnings (append with `learn`)
- 2026-10-31: CI on fork PR by first-time contributor shows no check-runs -> gh api actions/runs?head_sha=<sha> reveals status completed/conclusion action_required; report as pending maintainer approval, never as failure
