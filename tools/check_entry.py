#!/usr/bin/env python3
"""Check that a pull request adds or replaces exactly one well-formed entry in an open league.

Everything is read from git objects (the base commit and the pull request's head), never from a
checkout of the pull request, using the standard library only. That is what lets the admission
workflow, which holds a league key, run this same check on an untrusted pull request. The weights
cannot be checked here: they are encrypted; the admission workflow decrypts them and runs
tools/admit.py.

Environment: BASE_SHA (the pull request's base), HEAD_REF (its head commit or ref) and PR_AUTHOR (its
author's GitHub login). With --github-output FILE, a passing check also writes league=, bot= and
secret= (the name of the league's key secret) for the next step.
"""
import argparse
import json
import os
import re
import subprocess
import sys

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
AGE_HEADER = b"age-encryption.org/v1\n"
MAX_BYTES = 1024 * 1024
FILES = {"bot.safetensors.age", "entry.json"}
LEGAL = {"mu_front": (0.5, 1.5), "mu_back": (0.5, 1.5), "e_front": (0.82, 0.92), "e_back": (0.82, 0.92)}

errors = []


def fail(msg):
    errors.append(msg)


def git(*args, binary=False):
    out = subprocess.run(["git", *args], check=True, capture_output=True).stdout
    return out if binary else out.decode()


def blob(rev, path, binary=False):
    """A file's bytes (or text) at rev, or None if it is not there."""
    try:
        return git("show", f"{rev}:{path}", binary=binary)
    except subprocess.CalledProcessError:
        return None


def json_at(rev, path):
    text = blob(rev, path)
    try:
        return json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        return None


def tree(rev, path):
    """(mode, name) of the entries directly under path at rev; empty if path is not there."""
    try:
        out = git("ls-tree", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return []
    return [(line.split()[0], line.split("\t", 1)[1]) for line in out.splitlines()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--github-output")
    a = ap.parse_args()
    base, head, author = os.environ["BASE_SHA"], os.environ.get("HEAD_REF", "HEAD"), os.environ["PR_AUTHOR"]

    changed = [line.split("\t") for line in git("diff", "--no-renames", "--name-status", f"{base}...{head}").splitlines()]
    paths = sorted({p for _, *ps in changed for p in ps})

    # exactly one entries/<league>/<bot>/ folder, and nothing outside it
    outside = [p for p in paths if not p.startswith("entries/")]
    if outside:
        fail(f"only files under entries/ may change, not: {', '.join(outside)}")
    folders = {tuple(p.split("/")[1:3]) for p in paths if p.startswith("entries/") and p.count("/") >= 3}
    stray = [p for p in paths if p.startswith("entries/") and p.count("/") < 3]
    if stray:
        fail(f"entries go in entries/<league>/<bot-name>/, not: {', '.join(stray)}")
    if len(folders) != 1:
        fail(f"a pull request adds or replaces exactly one entry folder; this one touches {len(folders)}")
    if errors:
        return finish(a, None)

    league, name = folders.pop()
    # both names go into paths and the league's into a secret's name, so they are checked first
    if not NAME.match(league):
        fail(f"'{league}' is not a league; see leagues/ for the leagues there are")
        return finish(a, None)
    folder = f"entries/{league}/{name}"

    # the league must exist on the base branch and be open
    meta = json_at(base, f"leagues/{league}/league.json")
    if meta is None:
        fail(f"there is no league '{league}'; see leagues/ for the leagues there are")
    elif meta.get("status") != "open":
        fail(f"league '{league}' is not open for entries")

    if not NAME.match(name):
        fail(f"'{name}' is not a valid bot name: 3 to 32 of a-z, 0-9, - and _, starting with a letter or digit")
    present = tree(head, folder)
    if {n for _, n in present} != FILES:
        fail(f"{folder} must hold exactly {', '.join(sorted(FILES))}; it holds {', '.join(sorted(n for _, n in present)) or 'nothing'}")
    if any(mode not in ("100644", "100755") for mode, _ in present):
        fail(f"{folder} may hold only plain files")

    weights = blob(head, f"{folder}/bot.safetensors.age", binary=True)
    if weights is not None:
        if len(weights) > MAX_BYTES:
            fail(f"bot.safetensors.age is {len(weights)} bytes; the limit is {MAX_BYTES}")
        if not weights.startswith(AGE_HEADER):
            fail(f"bot.safetensors.age is not an age-encrypted file (encrypt it with age -R leagues/{league}/recipient.txt)")

    entry = blob(head, f"{folder}/entry.json")
    try:
        entry = json.loads(entry) if entry is not None else None
    except json.JSONDecodeError as exc:
        fail(f"entry.json is not valid JSON: {exc}")
        entry = None
    if isinstance(entry, dict):
        extra = set(entry) - {"name", "author", "website", "racketColor", "equipment"}
        if extra:
            fail(f"entry.json has unknown fields: {', '.join(sorted(extra))}")
        if entry.get("name") != name:
            fail(f"entry.json name must be '{name}', the folder's name")
        if str(entry.get("author", "")).lower() != author.lower():
            fail(f"entry.json author must be your GitHub login, '{author}'")
        website = entry.get("website")
        if website is not None and not (isinstance(website, str) and website.startswith("https://")):
            fail("website, if given, must be an https:// URL")
        color = entry.get("racketColor")
        if color is not None and not (isinstance(color, str) and COLOR.match(color)):
            fail("racketColor, if given, must look like #e34948")
        equipment = entry.get("equipment")
        if equipment is not None:
            if not isinstance(equipment, dict) or set(equipment) != set(LEGAL):
                fail(f"equipment, if given, must set exactly {', '.join(LEGAL)}")
            else:
                for key, (lo, hi) in LEGAL.items():
                    v = equipment[key]
                    if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
                        fail(f"equipment.{key} must be between {lo} and {hi}")
    elif entry is not None:
        fail("entry.json must be a JSON object")

    # one bot per account per league, and a name already taken belongs to whoever took it
    previous = json_at(base, f"{folder}/entry.json")
    if previous and str(previous.get("author", "")).lower() != author.lower():
        fail(f"'{name}' is already entered in {league} by {previous.get('author')}")
    for mode, other in tree(base, f"entries/{league}"):
        if mode != "040000" or other == name:
            continue
        e = json_at(base, f"entries/{league}/{other}/entry.json")
        if e and str(e.get("author", "")).lower() == author.lower():
            fail(f"{author} already has an entry in {league}, '{other}'; one bot per account (replace that one instead)")

    return finish(a, (league, name))


def finish(a, entry):
    if errors:
        for msg in errors:
            print(f"::error::{msg}")
        return 1
    league, name = entry
    if a.github_output:
        with open(a.github_output, "a") as f:
            f.write(f"league={league}\nbot={name}\nsecret=AGE_KEY_{league.upper().replace('-', '_')}\n")
    print(f"entry looks good: {league}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
