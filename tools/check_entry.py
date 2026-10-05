#!/usr/bin/env python3
"""Check that a pull request adds or replaces exactly one well-formed entry.

Reads only git and the files in the checkout, using the standard library, so it can run on an
untrusted pull request with no secrets. The weights themselves cannot be checked here: they are
encrypted, and the league's evaluator checks them after decrypting.
"""
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


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def entry_at(rev, path):
    """entry.json as committed at rev, or None if it is not there."""
    try:
        return json.loads(git("show", f"{rev}:{path}"))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


base, author = os.environ["BASE_SHA"], os.environ["PR_AUTHOR"]
changed = [line.split("\t") for line in git("diff", "--name-status", f"{base}...HEAD").splitlines()]

# exactly one folder under entries/, and nothing outside it
outside = [p for _, *ps in changed for p in ps if not p.startswith("entries/")]
if outside:
    fail(f"only files under entries/ may change, not: {', '.join(sorted(set(outside)))}")
folders = {p.split("/")[1] for _, *ps in changed for p in ps if p.startswith("entries/") and p.count("/") >= 2}
if len(folders) != 1:
    fail(f"a pull request adds or replaces exactly one entry folder; this one touches {len(folders)}")

if not errors:
    name = folders.pop()
    folder = os.path.join("entries", name)
    if not NAME.match(name):
        fail(f"'{name}' is not a valid bot name: 3 to 32 of a-z, 0-9, - and _, starting with a letter or digit")
    present = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    if present != FILES:
        fail(f"{folder} must hold exactly {', '.join(sorted(FILES))}; it holds {', '.join(sorted(present)) or 'nothing'}")

    weights = os.path.join(folder, "bot.safetensors.age")
    if os.path.isfile(weights):
        size = os.path.getsize(weights)
        if size > MAX_BYTES:
            fail(f"bot.safetensors.age is {size} bytes; the limit is {MAX_BYTES}")
        with open(weights, "rb") as f:
            if f.read(len(AGE_HEADER)) != AGE_HEADER:
                fail("bot.safetensors.age is not an age-encrypted file (encrypt it with age -R recipient.txt)")

    entry = None
    try:
        with open(os.path.join(folder, "entry.json")) as f:
            entry = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"entry.json is missing or not valid JSON: {exc}")
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
                    if not isinstance(v, (int, float)) or not lo <= v <= hi:
                        fail(f"equipment.{key} must be between {lo} and {hi}")
    elif entry is not None:
        fail("entry.json must be a JSON object")

    # one bot per account, and a name already taken belongs to whoever took it
    previous = entry_at(base, f"{folder}/entry.json")
    if previous and str(previous.get("author", "")).lower() != author.lower():
        fail(f"'{name}' is already entered by {previous.get('author')}")
    taken = git("ls-tree", "-d", "--name-only", f"{base}:entries").split()
    for other in taken:
        if other == name:
            continue
        e = entry_at(base, f"entries/{other}/entry.json")
        if e and str(e.get("author", "")).lower() == author.lower():
            fail(f"{author} already has an entry, '{other}'; one bot per account (replace that one instead)")

if errors:
    for msg in errors:
        print(f"::error::{msg}")
    sys.exit(1)
print("entry looks good")
