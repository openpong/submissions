#!/usr/bin/env python3
"""Would this weights file be let into the league? The evaluator's admission step, standalone.

    python3 tools/admit.py mybot.safetensors --league ittf-std

Run it on your unencrypted file before you encrypt it; the league runs the same check on the
decrypted file when you open a pull request. It needs only numpy, and it never runs code from the
file: safetensors is read by hand and only the published network shape is accepted.

The three checks below are copied from the league evaluator (genesis-world
arm/evaluate_submission.py: read_safetensors, the regime stamp check, recognize). The evaluator stays
authoritative and runs them again on league day.
"""
import argparse
import json
import os
import sys

import numpy as np

NF, NOUT = 12, 2                                   # the published return-map contract


class Refused(Exception):
    """The file would not be let in."""


def read_safetensors(path):
    """Parse safetensors without a dependency: 8-byte LE header length, JSON header, raw tensors."""
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 8:
        raise Refused("file is too short to be safetensors")
    hlen = int.from_bytes(raw[:8], "little")
    if hlen <= 0 or 8 + hlen > len(raw):
        raise Refused("safetensors header length is out of range")
    try:
        header = json.loads(raw[8:8 + hlen])
    except Exception as exc:
        raise Refused(f"safetensors header is not JSON: {exc}") from exc
    body = raw[8 + hlen:]
    meta = header.pop("__metadata__", {}) or {}
    tensors = {}
    for name, spec in header.items():
        if spec.get("dtype") not in ("F32", "F64"):
            raise Refused(f"{name}: only F32/F64 tensors are accepted, got {spec.get('dtype')}")
        lo, hi = spec["data_offsets"]
        if lo < 0 or hi > len(body) or hi < lo:
            raise Refused(f"{name}: tensor offsets fall outside the file")
        dt = np.float32 if spec["dtype"] == "F32" else np.float64
        arr = np.frombuffer(body[lo:hi], dtype=dt).reshape(spec["shape"])
        tensors[name] = np.ascontiguousarray(arr, np.float32)
    return meta, tensors


def recognize(tensors):
    """Accept only the published return-map family: one or more members, each a Linear/SiLU chain
    under `net.<2j>.weight|bias` with xm/xs/ym/ys normalizers."""
    prefixes = sorted({name.split("net.")[0] for name in tensors if ".net." in name or name.startswith("net.")})
    if not prefixes:
        raise Refused("no `net.` layers found: this is not a published return map")
    members = []
    for p in prefixes:
        layers = []
        li = 0
        while f"{p}net.{li}.weight" in tensors:
            w, b = tensors[f"{p}net.{li}.weight"], tensors.get(f"{p}net.{li}.bias")
            if b is None:
                raise Refused(f"{p}net.{li} has a weight but no bias")
            if w.ndim != 2 or b.ndim != 1 or w.shape[0] != b.shape[0]:
                raise Refused(f"{p}net.{li} weight/bias shapes do not agree")
            layers.append((w, b))
            li += 2
        if len(layers) < 2:
            raise Refused(f"member {p or 'net'} has fewer than two layers")
        if layers[0][0].shape[1] != NF:
            raise Refused(f"member {p or 'net'} takes {layers[0][0].shape[1]} features, the contract is {NF}")
        if layers[-1][0].shape[0] != NOUT:
            raise Refused(f"member {p or 'net'} returns {layers[-1][0].shape[0]} values, the contract is {NOUT}")
        stats = {}
        for k, want in (("xm", NF), ("xs", NF), ("ym", NOUT), ("ys", NOUT)):
            v = tensors.get(f"{p}{k}")
            if v is None:
                raise Refused(f"member {p or 'net'} is missing the {k} normalizer")
            if v.shape != (want,):
                raise Refused(f"member {p or 'net'} {k} has shape {v.shape}, expected ({want},)")
            stats[k] = v
        if float(np.min(np.abs(stats["xs"]))) == 0.0 or float(np.min(np.abs(stats["ys"]))) == 0.0:
            raise Refused("a normalizer scale is zero, which would divide by zero at predict time")
        for w, b in layers:
            if not (np.isfinite(w).all() and np.isfinite(b).all()):
                raise Refused("weights contain NaN or infinity")
        members.append({"layers": layers, **stats})
    return members


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("weights", help="the unencrypted .safetensors file")
    ap.add_argument("--league", default="ittf-std", help="league id (a folder under leagues/)")
    ap.add_argument("--brief", action="store_true", help="print only the verdict, nothing about the network")
    a = ap.parse_args()

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "leagues", a.league, "league.json")) as f:
        regime = json.load(f)["regime"]
    try:
        meta, tensors = read_safetensors(a.weights)
        stamped = meta.get("regime")
        if stamped and stamped != regime:
            raise Refused(f"the file is stamped for physics {stamped}; {a.league} plays {regime}")
        members = recognize(tensors)
    except Refused as exc:
        # in GitHub Actions the refusal becomes an annotation on the pull request
        prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") == "true" else ""
        print(f"{prefix}refused: {exc}")
        return 2
    if a.brief:
        print("admitted")
    else:
        hidden = [int(w.shape[0]) for w, _ in members[0]["layers"][:-1]]
        note = "" if stamped else " (no physics stamp in the metadata; admitted on the league's own)"
        print(f"admitted: {len(members)} member(s), hidden layers {hidden}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
