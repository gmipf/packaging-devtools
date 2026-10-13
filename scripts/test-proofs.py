#!/usr/bin/env python3
"""proofs/ledger.tsv -- what only the real services can show, and whether it
still holds.

Everything this repository can check offline is checked on every commit
(lint.sh, the test suites, selftest.py). A few things cannot: how Packit
routes a push, what Copr runs, what the reconciler does on GitHub. Those are
observed at the real service and written down here, with a fingerprint of the
files whose content they rest on. Change such a file and the entry is stale:
this is red until the same commit sets it back to not-yet -- a changed
mechanism does not inherit the observation of the old one.

States, and nothing in between:
  not-yet    an open obligation. Listed, never red.
  observed   seen at the real service. The red half cannot be produced there
             without shipping a broken package to the people who install it;
             the evidence says where it was measured instead. The evidence
             file must carry OBSERVED and VERDICT lines.
  proven     red and green both measured in one setup: RED, GREEN, VERDICT.

The fingerprint follows the mechanism, not the text around it: YAML is read
as YAML (path#a.b picks a subtree), a Python function as its syntax tree
without docstring (path#name), so comments and formatting do not count; any
other file counts byte for byte.

    scripts/test-proofs.py            check (lint.sh runs it)
    scripts/test-proofs.py --refresh  fill in mech_hash where it says AUTO --
                                      only right after observing that entry
"""
import ast
import hashlib
import json
import pathlib
import re
import sys

import yaml

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "proofs/ledger.tsv"
FIELDS = ("claim", "state", "date", "mech_hash", "evidence", "mech")
MARKERS = {"observed": ("OBSERVED", "VERDICT"), "proven": ("RED", "GREEN", "VERDICT")}


class Missing(Exception):
    pass


def canonical(node):
    # YAML 1.1 reads a workflow's `on:` as the boolean True; keys must sort.
    if isinstance(node, dict):
        return {str(k): canonical(v) for k, v in node.items()}
    if isinstance(node, list):
        return [canonical(v) for v in node]
    return node


def fragment(spec):
    path, _, sel = spec.partition("#")
    f = ROOT / path
    if not f.is_file():
        raise Missing(f"{path} does not exist")
    if path.endswith((".yml", ".yaml")):
        node = yaml.safe_load(f.read_text())
        for key in filter(None, sel.split(".")):
            if not isinstance(node, dict) or key not in node:
                raise Missing(f"{spec}: no key {key!r}")
            node = node[key]
        return json.dumps(canonical(node), sort_keys=True)
    if path.endswith(".py") and sel:
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == sel:
                if ast.get_docstring(n) is not None:
                    n.body = n.body[1:]
                return ast.dump(n)
        raise Missing(f"{spec}: no function or class {sel!r}")
    if sel:
        raise Missing(f"{spec}: only YAML and Python files take a #selector")
    return f.read_bytes().decode(errors="surrogateescape")


def mech_hash(mech):
    h = hashlib.sha256()
    for spec in mech.split(","):
        h.update(f"{spec}\n{fragment(spec)}\0".encode(errors="surrogateescape"))
    return h.hexdigest()[:16]


def rows():
    for n, line in enumerate(LEDGER.read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#") or line.startswith("claim|"):
            continue
        yield n, line.split("|")


def check(n, f):
    """-> (state for the report, detail or None if it holds)."""
    if len(f) != len(FIELDS):
        return "FAIL", f"line {n}: want {len(FIELDS)} fields ({'|'.join(FIELDS)}), have {len(f)}"
    claim, state, date, h, evidence, mech = f
    try:
        live = mech_hash(mech)
    except Missing as e:
        return "FAIL", f"mechanism file gone or moved: {e}"
    if state == "not-yet":
        if (date, h, evidence) != ("-", "-", "-"):
            return "FAIL", "not-yet takes '-' for date, mech_hash and evidence"
        return "OPEN", None
    if state not in MARKERS:
        return "FAIL", f"unknown state {state!r} (not-yet | observed | proven)"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return "FAIL", f"date {date!r} is not YYYY-MM-DD"
    ev = ROOT / evidence
    if not ev.is_file():
        return "FAIL", f"evidence {evidence} does not exist"
    text = ev.read_text()
    for marker in MARKERS[state]:
        if not re.search(rf"^{marker}\b", text, re.M):
            return "FAIL", f"evidence {evidence} has no {marker} line -- {state} needs {', '.join(MARKERS[state])}"
    if h == "AUTO":
        return "FAIL", "mech_hash is AUTO -- run scripts/test-proofs.py --refresh"
    if h != live:
        return "FAIL", (f"DRIFT: {mech} changed since {date} ({h} -> {live}). What was {state} there is not "
                        "known for the new state: set this entry to not-yet in the same commit, observe again")
    return "PASS", None


def refresh():
    out = []
    for line in LEDGER.read_text().splitlines():
        f = line.split("|")
        if len(f) == len(FIELDS) and f[3] == "AUTO" and not line.startswith("#"):
            f[3] = mech_hash(f[5])
            line = "|".join(f)
        out.append(line)
    LEDGER.write_text("\n".join(out) + "\n")


def main():
    if sys.argv[1:] == ["--refresh"]:
        refresh()
        print("mech_hash filled in for every AUTO entry")
        return
    if sys.argv[1:]:
        sys.exit(__doc__)
    fails = total = opened = 0
    for n, f in rows():
        state, detail = check(n, f)
        claim = f[0]
        if state == "OPEN":
            opened += 1
            print(f"OPEN  {claim}: not yet observed")
            continue
        total += 1
        fails += state == "FAIL"
        print(f"{state}  {claim}" + (f": {f[1]} {f[2]}, still holds" if detail is None else f"\n      {detail}"))
    if not total + opened:
        print("FAIL  the ledger has no entries -- this would pass on nothing")
        fails += 1
    print(f"\n{total - fails}/{total} passed, {opened} open")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
