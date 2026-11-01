Never leave an empty exception block — every catch must handle, log, or rethrow.

`rg -n '\.catch\(\s*\(\s*\)\s*=>\s*\{\s*\}\)|catch\s*\([^)]*\)\s*\{\s*\}|catch\s*\{\s*\}' <paths>`

A hit on agent-written scratch code is a finding to report, not to auto-fix.
