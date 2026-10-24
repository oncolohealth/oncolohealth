"""Offline archive/evidence review; never acquires, extracts, splits or trains."""

import argparse
import csv
import json
import sys

from .release_audit import audit_btxrd_release, prepare_btxrd_evidence_template, EVIDENCE_COLUMNS
from .evidence import check_btxrd_evidence


def _read_evidence(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Evidence CSV requires unique column names")
        return list(reader)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m cancer_workbench btxrd-review", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="Audit a local release ZIP and optional split lists")
    template = sub.add_parser("template", help="Print source flags/hashes and blank evidence fields as CSV")
    check = sub.add_parser("check", help="Compare a returned evidence CSV with the local source archive")
    for command in (audit, template, check):
        command.add_argument("archive")
        command.add_argument("--expected-md5", help="Reference digest from the chosen release record")
    audit.add_argument("--train-list")
    audit.add_argument("--validation-list")
    audit.add_argument("--inspect-exif", action="store_true", help="Optional Pillow; tag counts only, never values")
    check.add_argument("evidence")
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            result = audit_btxrd_release(args.archive, expected_md5=args.expected_md5,
                                         train_list=args.train_list, validation_list=args.validation_list,
                                         inspect_exif=args.inspect_exif)
        elif args.command == "template":
            result = prepare_btxrd_evidence_template(args.archive, expected_md5=args.expected_md5)
        else:
            result = check_btxrd_evidence(args.archive, _read_evidence(args.evidence), expected_md5=args.expected_md5)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, "Input rejected: " + str(error) + "\n")
    if args.command == "template":
        writer = csv.DictWriter(sys.stdout, fieldnames=EVIDENCE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result)
    else:
        print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
