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


def ensure_branch(name: str) -> None:
    """Create and checkout a local git branch if possible."""
    res = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if res.returncode != 0:
        return

    exists = (
        subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{name}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )

    if exists:
        subprocess.run(["git", "checkout", name], check=True)
    else:
        subprocess.run(["git", "checkout", "-b", name], check=True)


def install(args: argparse.Namespace) -> int:
    env = args.env
    try:
        run(["oc", "apply", "-k", str(ARCH_DIR / "bootstrap")])
        run(["oc", "apply", "-k", str(ENV_DIR / env)])
    except subprocess.CalledProcessError:
        print(
            "\u26a0\ufe0f  Verifica que la cuenta tenga permisos para crear namespaces y aplicar recursos",
            file=sys.stderr,
        )
        return 1
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


def generate_network_policies(_args: argparse.Namespace) -> int:
    """Output NetworkPolicy manifests based on component metadata."""
    try:
        import yaml  # type: ignore
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"], check=False)
        import yaml  # type: ignore

    components = []
    for path in sorted(ARCH_DIR.rglob("*.yaml")):
        with open(path, "r") as fh:
            docs = list(yaml.safe_load_all(fh))
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if doc.get("kind") == "NetworkPolicy":
                continue
            meta = doc.get("metadata", {})
            name = meta.get("name")
            if not name:
                continue
            annotations = meta.get("annotations", {})
            if "architecture.part_of" not in annotations:
                continue
            components.append(
                {
                    "name": name,
                    "namespace": meta.get("namespace"),
                    "invoked_by": [
                        s.strip()
                        for s in annotations.get("architecture.invoked_by", "").split(",")
                        if s.strip()
                    ],
                    "calls": [
                        s.strip()
                        for s in annotations.get("architecture.calls", "").split(",")
                        if s.strip()
                    ],
                }
            )

    if not components:
        print("No se encontraron componentes para procesar", file=sys.stderr)
        return 1

    names = {c["name"] for c in components}
    first = True
    for comp in components:
        ingress = [
            {"podSelector": {"matchLabels": {"app": src}}}
            for src in comp["invoked_by"]
            if src in names
        ]
        egress = [
            {"podSelector": {"matchLabels": {"app": dest}}}
            for dest in comp["calls"]
            if dest in names
        ]

        policy = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": comp["name"], "namespace": comp["namespace"]},
            "spec": {"podSelector": {"matchLabels": {"app": comp["name"]}}},
        }
        if ingress:
            policy["spec"]["ingress"] = [{"from": ingress}]
        if egress:
            policy["spec"]["egress"] = [{"to": egress}]

        if not first:
            print("---")
        first = False
        print(yaml.dump(policy, sort_keys=False).strip())
    return 0


def create_component(args: argparse.Namespace) -> int:
    """Create a new component instance from the inventory."""
    ensure_branch(args.branch)
    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - handled at runtime
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"],
            check=False,
        )
        import yaml  # type: ignore

    inventory_file = REPO_ROOT / "component_inventory.yaml"
    if not inventory_file.exists():
        print("Inventario de componentes no encontrado", file=sys.stderr)
        return 1

    with inventory_file.open() as fh:
        inventory = yaml.safe_load(fh) or {}

    comp_defs = inventory.get("components", {})
    if args.type not in comp_defs:
        print(f"Tipo de componente desconocido: {args.type}", file=sys.stderr)
        print(f"Tipos disponibles: {', '.join(comp_defs)}", file=sys.stderr)
        return 1

    definition = comp_defs[args.type]
    with_service = bool(definition.get("with_service", False))
    function = args.function or definition.get("function", args.type)

    domain_map = {
        "business": "business-domain",
        "support": "support-domain",
        "shared": "shared-components",
    }
    if args.domain not in domain_map:
        print(f"Dominio desconocido: {args.domain}", file=sys.stderr)
        return 1
    domain_dir = ARCH_DIR / domain_map[args.domain]
    if not domain_dir.exists():
        print(f"Directorio de dominio no existe: {domain_dir}", file=sys.stderr)
        return 1

    comp_dir = domain_dir / args.name
    if comp_dir.exists():
        print(f"El componente {args.name} ya existe", file=sys.stderr)
        return 1
    comp_dir.mkdir(parents=True)

    deployment = f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {args.name}
  labels:
    app: {args.name}
  annotations:
    architecture.domain: {args.domain}
    architecture.function: {function}
    architecture.part_of: arkit8s
  namespace: {domain_map[args.domain]}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {args.name}
  template:
    metadata:
      labels:
        app: {args.name}
    spec:
      containers:
        - name: {args.name}
          image: registry.redhat.io/openshift4/ose-tools-rhel9
          command:
            - /bin/bash
            - -c
            - sleep infinity
"""

    (comp_dir / "deployment.yaml").write_text(deployment)

    resources = ["deployment.yaml"]
    if with_service:
        service = f"""---
apiVersion: v1
kind: Service
metadata:
  name: {args.name}
  annotations:
    architecture.domain: {args.domain}
    architecture.function: {function}
    architecture.part_of: arkit8s
  namespace: {domain_map[args.domain]}
spec:
  selector:
    app: {args.name}
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
"""
        (comp_dir / "service.yaml").write_text(service)
        resources.append("service.yaml")

    kustom = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "commonLabels": {"arkit8s.component": args.name},
        "resources": resources,
    }
    (comp_dir / "kustomization.yaml").write_text(yaml.dump(kustom, sort_keys=False))

    # update domain kustomization
    domain_k_file = domain_dir / "kustomization.yaml"
    with domain_k_file.open() as fh:
        domain_k = yaml.safe_load(fh) or {}
    res_list = domain_k.get("resources", [])
    if args.name not in res_list:
        res_list.append(args.name)
        domain_k["resources"] = res_list
        domain_k_file.write_text(yaml.dump(domain_k, sort_keys=False))

    print(f"Componente {args.name} creado en {comp_dir}")
    return 0


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

    p_gen_np = sub.add_parser(
        "generate-network-policies",
        help="Output NetworkPolicy manifests based on metadata",
    )
    p_gen_np.set_defaults(func=generate_network_policies)

    p_new = sub.add_parser(
        "create-component",
        help="Create a new component instance from the inventory",
    )
    p_new.add_argument("name", help="Component instance name")
    p_new.add_argument("--type", required=True, help="Component type from inventory")
    p_new.add_argument(
        "--domain",
        required=True,
        choices=["business", "support", "shared"],
        help="Target domain short name",
    )
    p_new.add_argument("--function", help="Override function annotation")
    p_new.add_argument(
        "--branch",
        default="component-instances",
        help="Local git branch to store generated manifests",
    )
    p_new.set_defaults(func=create_component)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
