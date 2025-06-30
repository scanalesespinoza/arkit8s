#!/usr/bin/env python3
"""Generate a living architecture report from Kubernetes manifests."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    sys.exit(
        "Missing PyYAML. Install it with 'pip install pyyaml' and rerun the script."
    )


def load_components(arch_dir: Path) -> list[dict[str, object]]:
    components = []
    for path in sorted(arch_dir.rglob("*.yaml")):
        with path.open() as fh:
            docs = list(yaml.safe_load_all(fh))
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            meta = doc.get("metadata", {})
            if not meta:
                continue
            annotations = meta.get("annotations", {})
            comp = {
                "name": meta.get("name"),
                "kind": doc.get("kind"),
                "namespace": meta.get("namespace"),
                "domain": annotations.get("architecture.domain"),
                "function": annotations.get("architecture.function"),
                "invoked_by": [s.strip() for s in annotations.get("architecture.invoked_by", "").split(",") if s.strip()],
                "calls": [s.strip() for s in annotations.get("architecture.calls", "").split(",") if s.strip()],
                "file": path.relative_to(arch_dir.parent).as_posix(),
            }
            components.append(comp)
    return components


def print_summary(components: list[dict[str, object]]) -> None:
    print("## Resumen de componentes\n")
    for c in components:
        print(f"- **{c['name']}** ({c['kind']} en {c['namespace']})")
        if c.get("domain"):
            print(f"  - Dominio: {c['domain']}")
        if c.get("function"):
            print(f"  - Función: {c['function']}")
        if c.get("invoked_by"):
            print(f"  - Invocado por: {', '.join(c['invoked_by'])}")
        if c.get("calls"):
            print(f"  - Llama a: {', '.join(c['calls'])}")
        print(f"  - Archivo: {c['file']}\n")


def print_flows(components: list[dict[str, object]]) -> None:
    print("## Flujo de llamadas\n")
    for c in components:
        for target in c.get("calls", []):
            print(f"- {c['name']} ➡ {target}")
    if not any(c.get("calls") for c in components):
        print("(sin relaciones registradas)")
    print()


def print_traceability(components: list[dict[str, object]]) -> None:
    print("## Trazabilidad\n")
    for c in components:
        print(f"- {c['name']} -> {c['file']}")
    print()


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    arch_dir = repo_root / "architecture"

    if not arch_dir.exists():
        sys.exit("No se encontró el directorio 'architecture'")

    comps = load_components(arch_dir)
    if not comps:
        sys.exit("No se encontraron manifiestos para procesar")

    print("# Reporte de arquitectura viva\n")
    print_summary(comps)
    print_flows(comps)
    print_traceability(comps)


if __name__ == "__main__":
    main()
