"""A fake `gh` that answers `gh api` REST calls and logs them, for tests."""
import json, os, stat

SCRIPT = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
log = open("%(log)s", "a")
log.write("gh " + " ".join(args) + "\n")
if args[:1] != ["api"]:
    sys.exit(0)
method = "GET"
if "-X" in args:
    method = args[args.index("-X") + 1]
path = [a for a in args[1:] if not a.startswith("-") and a not in ("GET", "POST", "PUT", "PATCH", "DELETE")][0]
payload = None
if "--input" in args:
    payload = json.load(open(args[args.index("--input") + 1]))
    log.write("payload " + json.dumps(payload) + "\n")
body = %(issue_body)s
if method == "GET" and "/issues/" in path:
    print(json.dumps({"body": body}))
elif method == "GET" and "/pulls" in path:
    print("[]")
elif method == "GET" and "/issues" in path:
    import os
    f = "%(dir)s/issues.json"
    print(open(f).read() if os.path.exists(f) else "[]")
elif method == "POST" and path.endswith("/issues"):
    import os
    cf = "%(dir)s/counter"
    n = int(open(cf).read()) + 1 if os.path.exists(cf) else 7
    open(cf, "w").write(str(n))
    print(json.dumps({"number": n, "id": n * 100}))
elif method == "POST" and path.endswith("/pulls"):
    print(json.dumps({"number": 3}))
elif method == "PUT" and path.endswith("/merge"):
    print(json.dumps({"merged": True}))
else:
    print("{}")
'''


def install(bindir, issue_body='""'):
    gh = os.path.join(str(bindir), "gh")
    with open(gh, "w") as f:
        f.write(SCRIPT % {"log": os.path.join(str(bindir), "gh.log"), "issue_body": issue_body, "dir": str(bindir)})
    os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
    return gh
