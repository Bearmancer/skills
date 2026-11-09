# The run gate

Safety of the script is necessary, not sufficient. Before any real `--apply`:

1. **Fresh scan, fresh manifest.** Never apply a manifest older than the last change to the tree. Scanning costs real time — on this host the reference engine scans `~\Dev` in about 1.7 s and the whole home folder (about 890k files in candidate rows) in about 2 minutes — so start the scan as its own background run and keep the manifest it writes.
2. **Compare totals.** Paths, files, dirs against the scan you reviewed. A factor-of-ten jump means the rules matched something new; re-read the diff before applying.
3. **Clear the OWNER list path by path.** Those rows are the only ones needing a human; the rest are mechanical.
4. **Check the journal location is writable and outside every target.** A journal inside a purged tree is a journal you lose.
5. **Set the budget.** `--max-minutes` and `--max-failures` must be plausible for the tree size; an unbounded run is a runaway.
6. **State the expected residue.** Normally 0. A non-zero residue after apply means the run is unfinished, not "mostly done".
7. **Re-scan afterwards** and report counts, not adjectives: deleted files/dirs, residue paths, refused rows.
8. **Run `fd -u` over every removed path** (for a gone path, `fd -u -i -g -d 1 <name> <parent>`) and require a count of 0. Any other count is residue: BLOCK the claim of done. A missing `fd` is UNPROVEN, never PASS. `purge.py` does this itself; run it by hand for any other script.
PY