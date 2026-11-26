"""Exa agent run stop and cancel. Create runs with `rr vendor exa POST /agent/runs`, poll with `GET /agent/runs/<id>`.

Docs: https://exa.ai/docs/exa-spec.yaml (`/agent/runs/{id}/stop`, `/agent/runs/{id}/cancel`)
stop: ends an `ultra` run early, keeps results so far. cancel: drops a queued or running run, no results. Both bill accrued usage.
Usage: rr vendor exa-agent-run stop|cancel <run_id>
"""

import argparse

from . import common as pc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    pc.add_id_commands(
        ap.add_subparsers(dest="cmd", required=True),
        {
            "stop": ("POST", "/agent/runs/{id}/stop"),
            "cancel": ("POST", "/agent/runs/{id}/cancel"),
        },
    )
    pc.dispatch("exa", ap.parse_args(argv))


if __name__ == "__main__":
    main()
