"""throne-artifacts CLI.

All commands use the same service and policy implementation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .service import ArtifactService


def _svc(root: str | None) -> ArtifactService:
    return ArtifactService(root=Path(root) if root else Path("runtime/artifacts"))


def _print(obj: object, as_json: bool) -> None:
    if as_json:
        if hasattr(obj, "as_dict"):
            print(json.dumps(obj.as_dict(), indent=2, sort_keys=True))
        elif isinstance(obj, list):
            print(
                json.dumps(
                    [x.as_dict() if hasattr(x, "as_dict") else x for x in obj],
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(json.dumps(obj, indent=2, sort_keys=True))
    else:
        if hasattr(obj, "as_dict"):
            d = obj.as_dict()
            for k, v in d.items():
                print(f"{k}: {v}")
        elif isinstance(obj, list):
            for item in obj:
                if hasattr(item, "as_dict"):
                    print(item.as_dict().get("run_id") or item.as_dict().get("artifact_id"))
                else:
                    print(item)
        else:
            print(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="throne-artifacts")
    parser.add_argument("--root", default=None, help="artifact store root")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="initialize store layout")

    p_create = sub.add_parser("create-run", help="create a new run")
    p_create.add_argument("--project", required=True)
    p_create.add_argument("--subsystem", default="unknown")
    p_create.add_argument("--type", dest="run_type", required=True)
    p_create.add_argument("--source-commit", default="")
    p_create.add_argument("--parent-run", default=None)

    p_ingest = sub.add_parser("ingest", help="ingest a file into a run")
    p_ingest.add_argument("--run", required=True, dest="run_id")
    p_ingest.add_argument("path", type=Path)
    p_ingest.add_argument("--role", default="output")

    p_show = sub.add_parser("show", help="show a run")
    p_show.add_argument("run_id")

    p_list = sub.add_parser("list", help="list runs")
    p_list.add_argument("--project", default=None)

    p_verify = sub.add_parser("verify", help="verify a run")
    p_verify.add_argument("run_id")

    p_promo = sub.add_parser("promote", help="promote an artifact")
    p_promo.add_argument("artifact_id")
    p_promo.add_argument("--target", required=True)
    p_promo.add_argument("--actor", default="operator")
    p_promo.add_argument("--reason", default="")
    p_promo.add_argument("--verifier-id", default="")
    p_promo.add_argument("--verifier-version", default="")
    p_promo.add_argument("--proof-target", default="")
    p_promo.add_argument("--certificate-hash", default="")
    p_promo.add_argument("--verification-result", default="")

    p_export = sub.add_parser("export", help="export a run bundle")
    p_export.add_argument("run_id")
    p_export.add_argument("--output", required=True, type=Path)

    p_audit = sub.add_parser("audit", help="show promotion audit for a run")
    p_audit.add_argument("run_id")

    args = parser.parse_args(argv)
    svc = _svc(args.root)

    try:
        if args.cmd == "init":
            root = svc.init_layout()
            print(str(root) if not args.json else json.dumps({"root": str(root)}))
            return 0

        if args.cmd == "create-run":
            m = svc.create_run(
                project=args.project,
                subsystem=args.subsystem,
                run_type=args.run_type,
                source_commit=args.source_commit,
                parent_run=args.parent_run,
            )
            _print(m, args.json)
            return 0

        if args.cmd == "ingest":
            rec = svc.ingest(run_id=args.run_id, path=args.path, role=args.role)
            _print(rec, args.json)
            return 0

        if args.cmd == "show":
            m = svc.get_run(args.run_id)
            if m is None:
                print(f"run not found: {args.run_id}", file=sys.stderr)
                return 1
            _print(m, args.json)
            return 0

        if args.cmd == "list":
            runs = svc.list_runs(project=args.project)
            _print(runs, args.json)
            return 0

        if args.cmd == "verify":
            result = svc.verify(args.run_id)
            _print(result, args.json or True)
            return 0 if result.get("ok") else 2

        if args.cmd == "promote":
            evidence = {}
            if args.verifier_id:
                evidence = {
                    "verifier_id": args.verifier_id,
                    "verifier_version": args.verifier_version,
                    "target": args.proof_target,
                    "certificate_hash": args.certificate_hash,
                    "verification_result": args.verification_result,
                }
            result = svc.promote(
                args.artifact_id,
                target=args.target,
                actor=args.actor,
                reason=args.reason,
                verifier_evidence=evidence or None,
            )
            _print(result, args.json or True)
            return 0 if result.get("decision") == "ALLOWED" else 3

        if args.cmd == "export":
            out = svc.export_run(args.run_id, args.output)
            print(str(out) if not args.json else json.dumps({"export": str(out)}))
            return 0

        if args.cmd == "audit":
            entries = svc.audit(args.run_id)
            _print(entries, args.json or True)
            return 0

    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
