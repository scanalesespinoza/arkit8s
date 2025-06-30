#!/usr/bin/env python3
"""Cross-platform CLI for arkit8s utilities."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
ARCH_DIR = REPO_ROOT / "architecture"
UTIL_DIR = REPO_ROOT / "utilities"
ENV_DIR = REPO_ROOT / "environments"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and stream output."""
    return subprocess.run(cmd, check=check)


def install(args: argparse.Namespace) -> int:
    env = args.env
    run(["oc", "apply", "-k", str(ARCH_DIR / "bootstrap")])
    run(["oc", "apply", "-k", str(ENV_DIR / env)])
    return validate_cluster(args)


def uninstall(_args: argparse.Namespace) -> int:
    run(["oc", "delete", "-f", str(ARCH_DIR), "--recursive"], check=False)
    run(["oc", "delete", "-f", str(ARCH_DIR / "bootstrap")], check=False)
    return 0


def _get_namespaces() -> list[str]:
    names = []
    for path in sorted((ARCH_DIR / "bootstrap").glob("00-namespace-*.yaml")):
        names.append(path.stem.replace("00-namespace-", ""))
    return names


def validate_cluster(args: argparse.Namespace, quiet: bool = False) -> int:
    env = args.env
    env_dir = ENV_DIR / env
    namespaces = _get_namespaces()
    if not quiet:
        print("🔍 Verificando namespaces...")
    for ns in namespaces:
        res = subprocess.run(["oc", "get", "ns", ns], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            print(f"Namespace {ns} no existe", file=sys.stderr)
            return 1
    if not quiet:
        print("📦 Verificando deployments en estado Running...")
    for ns in namespaces:
        proc = subprocess.run(["oc", "get", "deploy", "-n", ns, "--no-headers"], capture_output=True, text=True)
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            cols = line.split()
            if len(cols) < 5:
                continue
            if cols[1] != cols[2]:
                print(f"Deployment no listo en {ns}: {cols[0]}", file=sys.stderr)
                return 1
    if not quiet:
        print("🚨 Verificando pods sin errores ni reinicios...")
    for ns in namespaces:
        proc = subprocess.run(["oc", "get", "pods", "-n", ns, "--no-headers"], capture_output=True, text=True)
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            cols = line.split()
            status = cols[2] if len(cols) > 2 else ""
            restarts = int(cols[3]) if len(cols) > 3 and cols[3].isdigit() else 0
            if status not in {"Running", "Completed"} or restarts > 0:
                print(f"Pod con problemas en {ns}: {line}", file=sys.stderr)
                return 1
    if not quiet:
        print(f"🔄 Verificando sincronización de manifiestos para {env}...")
    proc = subprocess.run(["oc", "diff", "-k", str(env_dir)], capture_output=True, text=True)
    if proc.returncode == 1:
        print("Manifiestos desincronizados:", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        return 1
    if proc.returncode not in (0, 1):
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    if not quiet:
        print("✅ Validación completada exitosamente.")
    return 0


def watch(args: argparse.Namespace) -> int:
    end = time.time() + args.minutes * 60
    result = 0

    def show_details():
        namespaces = _get_namespaces()
        print("Namespaces (bootstrap):")
        for ns in namespaces:
            print(f"  - {ns}")
        print("Deployments:")
        for ns in namespaces:
            proc = subprocess.run(["oc", "get", "deploy", "-n", ns, "--no-headers"], capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                name = line.split()[0]
                print(f"  {ns}/{name}")
        print("Namespace status:")
        for ns in namespaces:
            subprocess.run(["oc", "get", "ns", ns, "--no-headers"])
        print("Deployment status:")
        for ns in namespaces:
            subprocess.run(["oc", "get", "deploy", "-n", ns, "--no-headers"])
        print("Pod status:")
        for ns in namespaces:
            subprocess.run(["oc", "get", "pods", "-n", ns, "--no-headers"])
        print("Bootstrap manifests:")
        for f in (ARCH_DIR / "bootstrap").glob("*.yaml"):
            print(f"  - {f.name}")

    while time.time() < end:
        status = 0
        if args.detail != "default":
            show_details()
        status = validate_cluster(args, quiet=args.detail == "default")
        if status == 0:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: ✅ cluster in sync")
        else:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: ❌ cluster out of sync")
            result = 1
        time.sleep(30)

    if result == 0:
        print("✅ Cluster remained in sync during watch period.")
    else:
        print("⚠️  Issues detected while watching cluster.")
    return result


def validate_yaml(_args: argparse.Namespace) -> int:
    print("🔍 Validando manifiestos YAML...")
    try:
        import yaml  # type: ignore
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"], check=False)
        import yaml  # type: ignore

    yaml_files = sorted(p for p in REPO_ROOT.rglob("*.yaml") if p.name != "kustomization.yaml")
    status = 0
    for file in yaml_files:
        try:
            with open(file, 'r') as fh:
                list(yaml.safe_load_all(fh))
            print(f"✅ {file}")
        except yaml.YAMLError:
            print(f"❌ Error al validar {file}", file=sys.stderr)
            status = 1
    if status == 0:
        print("🎉 Todos los manifiestos YAML son válidos.")
    else:
        print("⚠️  Se encontraron errores de validación.", file=sys.stderr)
    return status


def report(_args: argparse.Namespace) -> int:
    try:
        import yaml  # type: ignore
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"], check=False)
        import yaml  # type: ignore

    components = []
    for path in sorted(ARCH_DIR.rglob("*.yaml")):
        with open(path, 'r') as fh:
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
                "invoked_by": [s.strip() for s in annotations.get("architecture.invoked_by", "").split(',') if s.strip()],
                "calls": [s.strip() for s in annotations.get("architecture.calls", "").split(',') if s.strip()],
                "file": path.relative_to(REPO_ROOT).as_posix(),
            }
            components.append(comp)

    if not components:
        print("No se encontraron manifiestos para procesar", file=sys.stderr)
        return 1

    print("# Reporte de arquitectura viva\n")
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

    print("## Flujo de llamadas\n")
    any_calls = False
    for c in components:
        for target in c.get("calls", []):
            print(f"- {c['name']} ➡ {target}")
            any_calls = True
    if not any_calls:
        print("(sin relaciones registradas)")
    print()

    print("## Trazabilidad\n")
    for c in components:
        print(f"- {c['name']} -> {c['file']}")
    print()
    return 0


def validate_metadata(_args: argparse.Namespace) -> int:
    """Ensure calls and invoked_by metadata are consistent with manifests and NetworkPolicies."""
    try:
        import yaml  # type: ignore
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"], check=False)
        import yaml  # type: ignore

    components: dict[str, dict[str, object]] = {}
    network_policies: list[dict[str, object]] = []

    for path in sorted(ARCH_DIR.rglob("*.yaml")):
        with open(path, 'r') as fh:
            docs = list(yaml.safe_load_all(fh))
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            kind = doc.get("kind")
            meta = doc.get("metadata", {})
            name = meta.get("name")
            if not name:
                continue
            annotations = meta.get("annotations", {})
            record = {
                "name": name,
                "kind": kind,
                "namespace": meta.get("namespace"),
                "invoked_by": {s.strip() for s in annotations.get("architecture.invoked_by", "").split(',') if s.strip()},
                "calls": {s.strip() for s in annotations.get("architecture.calls", "").split(',') if s.strip()},
                "file": path.relative_to(REPO_ROOT).as_posix(),
            }
            if kind == "NetworkPolicy":
                network_policies.append(record | {"spec": doc.get("spec", {})})
            else:
                components[name] = record

    status = 0
    for comp in components.values():
        for call in comp["calls"]:
            if call not in components:
                print(f"❌ {comp['name']} calls unknown component {call}", file=sys.stderr)
                status = 1
            elif comp["name"] not in components[call]["invoked_by"]:
                print(f"❌ {call} missing invoked_by reference to {comp['name']}", file=sys.stderr)
                status = 1
    for comp in components.values():
        for inv in comp["invoked_by"]:
            if inv not in components:
                print(f"❌ {comp['name']} invoked_by unknown component {inv}", file=sys.stderr)
                status = 1
            elif comp["name"] not in components[inv]["calls"]:
                print(f"❌ {inv} missing calls reference to {comp['name']}", file=sys.stderr)
                status = 1

    if network_policies:
        for policy in network_policies:
            pname = policy["name"]
            component = components.get(pname)
            if not component:
                continue
            spec = policy.get("spec", {})
            ingress = spec.get("ingress", [])
            allow_from = {
                r.get("podSelector", {}).get("matchLabels", {}).get("app")
                for rule in ingress for r in rule.get("from", [])
            }
            egress = spec.get("egress", [])
            allow_to = {
                r.get("podSelector", {}).get("matchLabels", {}).get("app")
                for rule in egress for r in rule.get("to", [])
            }
            for src in component["invoked_by"]:
                if src not in allow_from:
                    print(f"❌ NetworkPolicy {pname} does not allow from {src}", file=sys.stderr)
                    status = 1
            for dest in component["calls"]:
                if dest not in allow_to:
                    print(f"❌ NetworkPolicy {pname} does not allow to {dest}", file=sys.stderr)
                    status = 1
    else:
        print("⚠️  No se encontraron NetworkPolicies. Se omitió la validación de red.")

    if status == 0:
        print("✅ Metadatos coherentes.")
    else:
        print("⚠️  Se encontraron inconsistencias de metadatos.", file=sys.stderr)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="arkit8s utility CLI")
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="Install manifests via oc apply")
    p_install.add_argument("--env", default="sandbox", help="Target environment")
    p_install.set_defaults(func=install)

    p_uninstall = sub.add_parser("uninstall", help="Delete manifests")
    p_uninstall.set_defaults(func=uninstall)

    p_watch = sub.add_parser("watch", help="Watch cluster status")
    p_watch.add_argument("--minutes", type=int, default=5, help="Duration in minutes")
    p_watch.add_argument("--detail", choices=["default", "detailed", "all"], default="default")
    p_watch.add_argument("--env", default="sandbox")
    p_watch.set_defaults(func=watch)

    p_validate = sub.add_parser("validate-cluster", help="Validate cluster state")
    p_validate.add_argument("--env", default="sandbox")
    p_validate.set_defaults(func=validate_cluster)

    p_yaml = sub.add_parser("validate-yaml", help="Validate YAML syntax")
    p_yaml.set_defaults(func=validate_yaml)

    p_report = sub.add_parser("report", help="Generate architecture report")
    p_report.set_defaults(func=report)

    p_meta = sub.add_parser(
        "validate-metadata",
        help="Check that calls and invoked_by annotations match and align with NetworkPolicies",
    )
    p_meta.set_defaults(func=validate_metadata)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
