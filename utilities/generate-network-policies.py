#!/usr/bin/env python3
"""Generate basic NetworkPolicies from component metadata."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("Missing PyYAML. Install it with 'pip install pyyaml' and rerun the script.")


def load_components(arch_dir: Path) -> list[dict[str, object]]:
    comps = []
    for path in sorted(arch_dir.rglob("*.yaml")):
        with path.open() as fh:
            docs = list(yaml.safe_load_all(fh))
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if doc.get("kind") == "NetworkPolicy":
                continue
            meta = doc.get("metadata", {})
            if not meta:
                continue
            annotations = meta.get("annotations", {})
            if "architecture.part_of" not in annotations:
                continue
            comps.append(
                {
                    "name": meta.get("name"),
                    "namespace": meta.get("namespace"),
                    "kind": doc.get("kind"),
                    "invoked_by": [s.strip() for s in annotations.get("architecture.invoked_by", "").split(",") if s.strip()],
                    "calls": [s.strip() for s in annotations.get("architecture.calls", "").split(",") if s.strip()],
                }
            )
    return comps


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    arch_dir = repo_root / "architecture"
    if not arch_dir.exists():
        sys.exit("No se encontró el directorio 'architecture'")

    comps = load_components(arch_dir)
    comps = [c for c in comps if c["kind"]]
    if not comps:
        sys.exit("No se encontraron manifiestos para procesar")

    names = {c["name"] for c in comps}
    first = True
    for c in comps:
        ingress = [
            {"podSelector": {"matchLabels": {"app": src}}}
            for src in c["invoked_by"]
            if src in names
        ]
        egress = [
            {"podSelector": {"matchLabels": {"app": dest}}}
            for dest in c["calls"]
            if dest in names
        ]
        pol = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": c["name"], "namespace": c["namespace"]},
            "spec": {"podSelector": {"matchLabels": {"app": c["name"]}}},
        }
        if ingress:
            pol["spec"]["ingress"] = [{"from": ingress}]
        if egress:
            pol["spec"]["egress"] = [{"to": egress}]
        if not first:
            print("---")
        first = False
        print(yaml.dump(pol, sort_keys=False).strip())


if __name__ == "__main__":
    main()
