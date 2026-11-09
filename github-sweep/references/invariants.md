# Non-negotiable directives and safety invariants

1. **Strict Personal Repository Exclusion:**
   - Identity is resolved dynamically: `CURRENT_USER=$(gh api user --jq .login)`.
   - Never touch personal, non-fork repositories (`owner == CURRENT_USER and
     isFork == false`).
   - Only third-party upstream repos and user forks of third-party repos
     (`isFork == true`) are swept.
2. **Comprehensive Census ("Check All"):**
   - Sweeps all authored PRs, all authored/assigned issues, all review
     requests, and all fork branches.
3. **No Questions, No Stops:**
   - No confirmation dialogs, no question tool, no pause for a decision. Purge
     merged, closed, and stale branches maximally.
4. **CodeGraph First for Changes:**
   - When any PR or issue requires code evaluation, rebase, or changes:
     establish ground truth on upstream default-branch HEAD with CodeGraph
     (`codegraph init -y`) before touching branches or editing files.
5. **Latest Upstream Alignment:**
   - Always pull and align against latest upstream base (`dev` or `main`)
     before applying changes.
6. **Isolated Branch per Work Item:**
   - Every fix, rebase, or asset update runs in an isolated task branch and
     temporary scratch workspace.
7. **Clean Teardown:**
   - Workspaces and merged/closed branches are deleted upon completion; final
     status table printed post-updates.
   - A scratch datedir that outlives its run is a leak: delete the whole
     datedir when the run completes. Exception: a conflict-retained workspace
     (unpushed commits or a dirty working tree) is first resolved: commit,
     rebase and push with `--force-with-lease`. If that still fails after 3
     attempts, quarantine it (never auto-delete) and list its path and reason
     in the final report as `BLOCKED`.
PY