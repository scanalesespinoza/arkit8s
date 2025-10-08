#!/usr/bin/env python3
"""Cross-platform CLI for arkit8s utilities."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import shutil
import sys
import time
from functools import wraps
from pathlib import Path

HELP_START_MARKER = "<!-- BEGIN ARKIT8S HELP -->"
HELP_END_MARKER = "<!-- END ARKIT8S HELP -->"

REPO_ROOT = Path(__file__).resolve().parent
ARCH_DIR = REPO_ROOT / "architecture"
UTIL_DIR = REPO_ROOT / "utilities"
ENV_DIR = REPO_ROOT / "environments"
SIM_TEMPLATE_PATH = UTIL_DIR / "simulator-deployment.yaml.tpl"


def _load_usage_text() -> str:
    """Return the README help block so CLI help matches documentation."""
    readme = REPO_ROOT / "README.md"
    try:
        content = readme.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "arkit8s utility CLI"

    start = content.find(HELP_START_MARKER)
    end = content.find(HELP_END_MARKER)
    if start == -1 or end == -1 or end <= start:
        return "arkit8s utility CLI"

    help_block = content[start + len(HELP_START_MARKER):end]
    return help_block.strip() or "arkit8s utility CLI"


USAGE_TEXT = _load_usage_text()


def _await_confirmation(message: str = "¿Desea finalizar? (Y/N) ") -> None:
    """Prompt the user until a Y/N confirmation is provided."""

    while True:
        resp = input(message).strip().lower()
        if resp in {"y", "n"}:
            if resp == "y":
                return
            print("Operación en espera de confirmación. Responda 'Y' para finalizar.")
        else:
            print("Respuesta inválida. Ingrese 'Y' o 'N'.")


def _confirm_command(func):
    """Wrap CLI commands so they wait for a Y/N confirmation before finishing."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        print("Tarea finalizada")
        _await_confirmation("¿Desea salir? (Y/N) ")
        return result

    return wrapper


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


def cleanup(args: argparse.Namespace) -> int:
    """Remove all arkit8s resources, including namespaces, for a fresh start."""

    env_dir = ENV_DIR / args.env
    status = 0

    if env_dir.exists():
        proc = run(["oc", "delete", "--ignore-not-found", "-k", str(env_dir)], check=False)
        if proc.returncode != 0:
            status = proc.returncode
    else:
        print(
            f"⚠️  El entorno {args.env} no existe en este repositorio; se omite su limpieza.",
            file=sys.stderr,
        )

    proc = run(["oc", "delete", "--ignore-not-found", "-k", str(ARCH_DIR)], check=False)
    if proc.returncode != 0:
        status = proc.returncode

    for namespace in _get_namespaces():
        res = subprocess.run(
            ["oc", "delete", "namespace", namespace, "--ignore-not-found"],
            check=False,
        )
        status = res.returncode if status == 0 and res.returncode != 0 else status

    return status


def _get_namespaces() -> list[str]:
    names = []
    for path in sorted((ARCH_DIR / "bootstrap").glob("00-namespace-*.yaml")):
        names.append(path.stem.replace("00-namespace-", ""))
    return names


def _collect_component_namespaces() -> set[str]:
    """Return namespaces referenced by manifests in the architecture tree."""

    import yaml  # type: ignore

    namespaces: set[str] = set()
    for manifest in ARCH_DIR.rglob("*.yaml"):
        if manifest.name.startswith("00-namespace-"):
            continue
        try:
            docs = list(yaml.safe_load_all(manifest.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            metadata = doc.get("metadata")
            if not isinstance(metadata, dict):
                continue
            namespace = metadata.get("namespace")
            if isinstance(namespace, str) and namespace:
                namespaces.add(namespace)
    return namespaces


def _collect_serviceaccounts() -> set[tuple[str, str]]:
    """Return tuples of (namespace, name) for ServiceAccount manifests."""

    import yaml  # type: ignore

    serviceaccounts: set[tuple[str, str]] = set()
    for manifest in ARCH_DIR.rglob("*.yaml"):
        try:
            docs = list(yaml.safe_load_all(manifest.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "ServiceAccount":
                continue
            metadata = doc.get("metadata")
            if not isinstance(metadata, dict):
                continue
            name = metadata.get("name")
            namespace = metadata.get("namespace")
            if isinstance(name, str) and name and isinstance(namespace, str) and namespace:
                serviceaccounts.add((namespace, name))
    return serviceaccounts


def validate_cluster(args: argparse.Namespace, quiet: bool = False) -> int:
    env = args.env
    env_dir = ENV_DIR / env
    namespaces = _get_namespaces()
    component_namespaces = _collect_component_namespaces()
    missing_namespaces = sorted(component_namespaces - set(namespaces))
    if missing_namespaces:
        print(
            "Componentes referencian namespaces que no forman parte del bootstrap: "
            + ", ".join(missing_namespaces),
            file=sys.stderr,
        )
        return 1
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
            if len(cols) < 2:
                continue
            ready = cols[1]
            if "/" in ready:
                try:
                    current, desired = (int(x) for x in ready.split("/", 1))
                except ValueError:
                    current = desired = 0
                if current != desired:
                    print(
                        f"Deployment no listo en {ns}: {cols[0]}",
                        file=sys.stderr,
                    )
                    return 1
            elif len(cols) >= 3 and cols[1] != cols[2]:
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
    serviceaccounts = _collect_serviceaccounts()
    if serviceaccounts and not quiet:
        print("🪪 Verificando ServiceAccounts requeridas...")
    for namespace, name in sorted(serviceaccounts):
        res = subprocess.run(
            ["oc", "get", "sa", name, "-n", namespace],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode != 0:
            print(
                f"ServiceAccount {name} no existe en el namespace {namespace}",
                file=sys.stderr,
            )
            return 1
    if not quiet:
        print(f"🔄 Verificando sincronización de manifiestos para {env}...")
    if shutil.which("diff") is None:
        print("error: comando 'diff' no encontrado. Instale diffutils.", file=sys.stderr)
        return 1
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
                "file": path.relative_to(REPO_ROOT).as_posix(),
                "bootstrap": path.is_relative_to(ARCH_DIR / "bootstrap"),
            }
            components.append(comp)

    if not components:
        print("No se encontraron manifiestos para procesar", file=sys.stderr)
        return 1

    print("# Reporte de arquitectura viva\n")
    print("## Resumen de componentes\n")
    for c in components:
        if c["kind"] == "Namespace" and c.get("bootstrap"):
            print(f"- **{c['name']}** ({c['kind']})")
        else:
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


BUSINESS_SIM_TARGETS: dict[str, dict[str, str | Path]] = {
    "api": {
        "path": ARCH_DIR / "business-domain" / "api",
        "name_prefix": "api-availability-sim",
        "simulated_component": "api-app-instance",
        "function_annotation": "api-load-simulator",
    },
    "ui": {
        "path": ARCH_DIR / "business-domain" / "ui",
        "name_prefix": "ui-availability-sim",
        "simulated_component": "ui-app-instance",
        "function_annotation": "ui-load-simulator",
    },
    "company-identity": {
        "path": ARCH_DIR
        / "business-domain"
        / "company-management"
        / "identity-verification",
        "name_prefix": "company-identity-availability-sim",
        "simulated_component": "company-identity-verification-app-instance",
        "function_annotation": "company-identity-load-simulator",
    },
    "person-identity": {
        "path": ARCH_DIR
        / "business-domain"
        / "person-management"
        / "identity-verification",
        "name_prefix": "person-identity-availability-sim",
        "simulated_component": "person-identity-verification-app-instance",
        "function_annotation": "person-identity-load-simulator",
    },
}


def generate_load_simulators(args: argparse.Namespace) -> int:
    """Generate load simulator deployments for selected business functions."""

    ensure_branch(args.branch)

    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - handled at runtime
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"],
            check=False,
        )
        import yaml  # type: ignore

    if not SIM_TEMPLATE_PATH.exists():
        print(
            "Plantilla de simuladores no encontrada. Ejecuta desde la raíz del repositorio.",
            file=sys.stderr,
        )
        return 1

    template_text = SIM_TEMPLATE_PATH.read_text(encoding="utf-8")
    rng = random.Random(args.seed)
    behavior_mode = args.behavior or "dynamic"

    namespace = "business-domain"
    generated: list[Path] = []

    for target in args.targets:
        if target not in BUSINESS_SIM_TARGETS:
            print(f"Destino desconocido: {target}", file=sys.stderr)
            return 1
        info = BUSINESS_SIM_TARGETS[target]
        comp_path = info["path"]
        if not isinstance(comp_path, Path):
            comp_path = Path(comp_path)  # pragma: no cover - defensive
        if not comp_path.exists():
            print(f"Directorio de componente no encontrado: {comp_path}", file=sys.stderr)
            return 1

        output_file = comp_path / "load-simulators.yaml"
        docs: list[str] = []
        for idx in range(1, args.count + 1):
            behavior_seed = rng.randrange(1, 2**31)
            name = f"{info['name_prefix']}-{idx}"
            rendered = template_text.format(
                name=name,
                namespace=namespace,
                behavior=behavior_mode,
                behavior_seed=behavior_seed,
                simulated_component=info["simulated_component"],
                function_annotation=info["function_annotation"],
            )
            docs.append(rendered.strip())

        header = "# Generated by arkit8s generate-load-simulators\n"
        body = "\n---\n".join(docs)
        output_file.write_text(f"{header}---\n{body}\n", encoding="utf-8")
        generated.append(output_file)

        kustom_file = comp_path / "kustomization.yaml"
        if kustom_file.exists():
            with kustom_file.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        else:
            data = {}

        resources = list(data.get("resources", []) or [])
        if "load-simulators.yaml" not in resources:
            resources.append("load-simulators.yaml")
            data["resources"] = resources
            class _IndentDumper(yaml.Dumper):  # type: ignore
                def increase_indent(self, flow=False, indentless=False):  # type: ignore
                    return super().increase_indent(flow, False)

            rendered = yaml.dump(
                data,
                sort_keys=False,
                Dumper=_IndentDumper,
            )
            lines = rendered.splitlines()
            for idx, line in enumerate(lines):
                if line.strip() == "resources:":
                    j = idx + 1
                    while j < len(lines) and lines[j].startswith("-"):
                        lines[j] = f"  {lines[j]}"
                        j += 1
                    break
            kustom_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for file in generated:
        print(f"Simuladores generados: {file.relative_to(REPO_ROOT)}")
    return 0


def cleanup_load_simulators(args: argparse.Namespace) -> int:
    """Remove generated load simulators from manifests and the cluster."""

    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - handled at runtime
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"],
            check=False,
        )
        import yaml  # type: ignore

    # Attempt to delete running simulators from the cluster.
    try:
        delete_proc = subprocess.run(
            [
                "oc",
                "delete",
                "deploy",
                "-n",
                "business-domain",
                "-l",
                "arkit8s.simulator=true",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        delete_proc = None
        print(
            "⚠️  Comando 'oc' no disponible; omitiendo eliminación en el clúster.",
            file=sys.stderr,
        )
    else:
        if delete_proc.stdout.strip():
            print(delete_proc.stdout.strip())
        if delete_proc.returncode not in (0, 1):
            sys.stderr.write(delete_proc.stderr)

    targets = args.targets or sorted(BUSINESS_SIM_TARGETS.keys())
    for target in targets:
        if target not in BUSINESS_SIM_TARGETS:
            print(f"Destino desconocido: {target}", file=sys.stderr)
            return 1
        info = BUSINESS_SIM_TARGETS[target]
        comp_path = info["path"]
        if not isinstance(comp_path, Path):
            comp_path = Path(comp_path)
        if not comp_path.exists():
            continue

        manifest = comp_path / "load-simulators.yaml"
        if manifest.exists():
            content = manifest.read_text(encoding="utf-8")
            if "Generated by arkit8s generate-load-simulators" in content:
                manifest.unlink()
                print(
                    f"Archivo eliminado: {manifest.relative_to(REPO_ROOT)}",
                )
            else:
                print(
                    f"⚠️  El archivo {manifest.relative_to(REPO_ROOT)} no fue generado automáticamente; se conserva.",
                    file=sys.stderr,
                )

        kustom_file = comp_path / "kustomization.yaml"
        if not kustom_file.exists():
            continue

        with kustom_file.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        resources = [r for r in data.get("resources", []) or [] if r != "load-simulators.yaml"]
        if "load-simulators.yaml" in (data.get("resources", []) or []):
            if resources:
                data["resources"] = resources
            else:
                data.pop("resources", None)

            class _IndentDumper(yaml.Dumper):  # type: ignore
                def increase_indent(self, flow=False, indentless=False):  # type: ignore
                    return super().increase_indent(flow, False)

            rendered = yaml.dump(
                data,
                sort_keys=False,
                Dumper=_IndentDumper,
            )
            lines = rendered.splitlines()
            for idx, line in enumerate(lines):
                if line.strip() == "resources:":
                    j = idx + 1
                    while j < len(lines) and lines[j].startswith("-"):
                        lines[j] = f"  {lines[j]}"
                        j += 1
                    break
            kustom_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(
                f"Kustomization actualizado: {kustom_file.relative_to(REPO_ROOT)}",
            )

    if args.delete_branch:
        branch = args.branch
        git_env = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if git_env.returncode == 0:
            current = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            current_branch = current.stdout.strip()
            if current_branch == branch:
                print(
                    f"⚠️  Cambia de rama antes de eliminar '{branch}'.",
                    file=sys.stderr,
                )
            else:
                delete_branch = subprocess.run(
                    ["git", "branch", "-D", branch],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if delete_branch.returncode == 0:
                    print(delete_branch.stdout.strip())
                else:
                    sys.stderr.write(delete_branch.stderr)

    return 0


def list_load_simulators(_args: argparse.Namespace) -> int:
    """List simulator deployments currently applied to the cluster."""

    try:
        proc = subprocess.run(
            [
                "oc",
                "get",
                "deploy",
                "-A",
                "-l",
                "arkit8s.simulator=true",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("error: comando 'oc' no encontrado", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as err:
        sys.stderr.write(err.stderr)
        return err.returncode

    data = json.loads(proc.stdout or "{}")
    items = data.get("items", [])
    if not items:
        print("No se encontraron simuladores desplegados.")
        return 0

    print("Simuladores desplegados:\n")
    for item in items:
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        template = spec.get("template", {}).get("spec", {})
        containers = template.get("containers", [])
        behavior = "desconocido"
        for container in containers:
            for env in container.get("env", []):
                if env.get("name") == "BEHAVIOR":
                    behavior = env.get("value", behavior)
                    break
            if behavior != "desconocido":
                break
        print(
            f"- Namespace: {meta.get('namespace', 'desconocido')}\n"
            f"  Deployment: {meta.get('name', 'desconocido')}\n"
            f"  Comportamiento: {behavior}\n"
        )

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
    # Parse dependencies from CLI
    depends_incluster = getattr(args, "depends_incluster", None)
    depends_outcluster = getattr(args, "depends_outcluster", None)
    # Prepare annotation fields
    annotations = {
        "architecture.domain": args.domain,
        "architecture.function": function,
        "architecture.part_of": "arkit8s",
    }
    # Add dependency metadata as recommended in README
    if depends_incluster:
        annotations["depends.incluster"] = depends_incluster
    if depends_outcluster:
        annotations["depends.outcluster"] = depends_outcluster

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

        # Build annotation YAML block
        annotation_yaml = "\n".join([f"    {k}: {v}" for k, v in annotations.items()])
        deployment = f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
    name: {args.name}
    labels:
        app: {args.name}
    annotations:
{annotation_yaml}
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
                service_annotation_yaml = annotation_yaml
                service = f"""---
apiVersion: v1
kind: Service
metadata:
    name: {args.name}
    annotations:
{service_annotation_yaml}
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
    parser = argparse.ArgumentParser(
        description=USAGE_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="Install manifests via oc apply")
    p_install.add_argument("--env", default="sandbox", help="Target environment")
    p_install.set_defaults(func=_confirm_command(install))

    p_uninstall = sub.add_parser("uninstall", help="Delete manifests")
    p_uninstall.set_defaults(func=_confirm_command(uninstall))

    p_cleanup_all = sub.add_parser(
        "cleanup",
        help="Eliminar todos los recursos de arkit8s, incluidos los namespaces",
    )
    p_cleanup_all.add_argument("--env", default="sandbox", help="Entorno a limpiar")
    p_cleanup_all.set_defaults(func=_confirm_command(cleanup))

    p_watch = sub.add_parser("watch", help="Watch cluster status")
    p_watch.add_argument("--minutes", type=int, default=5, help="Duration in minutes")
    p_watch.add_argument("--detail", choices=["default", "detailed", "all"], default="default")
    p_watch.add_argument("--env", default="sandbox")
    p_watch.set_defaults(func=_confirm_command(watch))

    p_validate = sub.add_parser("validate-cluster", help="Validate cluster state")
    p_validate.add_argument("--env", default="sandbox")
    p_validate.set_defaults(func=_confirm_command(validate_cluster))

    p_yaml = sub.add_parser("validate-yaml", help="Validate YAML syntax")
    p_yaml.set_defaults(func=_confirm_command(validate_yaml))

    p_report = sub.add_parser("report", help="Generate architecture report")
    p_report.set_defaults(func=_confirm_command(report))

    p_meta = sub.add_parser(
        "validate-metadata",
        help="Check that calls and invoked_by annotations match and align with NetworkPolicies",
    )
    p_meta.set_defaults(func=_confirm_command(validate_metadata))

    p_gen_np = sub.add_parser(
        "generate-network-policies",
        help="Output NetworkPolicy manifests based on metadata",
    )
    p_gen_np.set_defaults(func=_confirm_command(generate_network_policies))

    p_sim = sub.add_parser(
        "generate-load-simulators",
        help="Create synthetic deployments with random availability to stress business workloads",
    )
    p_sim.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of simulator deployments per target (default: 3)",
    )
    p_sim.add_argument(
        "--targets",
        nargs="+",
        choices=sorted(BUSINESS_SIM_TARGETS.keys()),
        default=sorted(BUSINESS_SIM_TARGETS.keys()),
        help="Business components to simulate (default: all)",
    )
    p_sim.add_argument(
        "--branch",
        default="load-simulators",
        help="Local git branch to store generated manifests",
    )
    p_sim.add_argument(
        "--seed",
        type=int,
        help="Optional random seed to obtain deterministic behavior scheduling",
    )
    p_sim.add_argument(
        "--behavior",
        choices=["dynamic", "ok", "notready", "restart"],
        help="Override the runtime behavior of generated simulators (default: dynamic)",
    )
    p_sim.set_defaults(func=_confirm_command(generate_load_simulators))

    p_list_sim = sub.add_parser(
        "list-load-simulators",
        help="List simulator deployments running in the cluster",
    )
    p_list_sim.set_defaults(func=_confirm_command(list_load_simulators))

    p_cleanup_sims = sub.add_parser(
        "cleanup-load-simulators",
        help="Remove generated simulator manifests and cluster resources",
    )
    p_cleanup_sims.add_argument(
        "--targets",
        nargs="+",
        choices=sorted(BUSINESS_SIM_TARGETS.keys()),
        help="Componentes para los que se limpiarán los manifiestos",
    )
    p_cleanup_sims.add_argument(
        "--branch",
        default="load-simulators",
        help="Rama local que contiene los manifiestos generados",
    )
    p_cleanup_sims.add_argument(
        "--delete-branch",
        action="store_true",
        help="Eliminar la rama local indicada tras limpiar los manifiestos",
    )
    p_cleanup_sims.set_defaults(func=_confirm_command(cleanup_load_simulators))

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
        "--depends-incluster",
        help="Comma-separated list of in-cluster dependencies (e.g. api-user-svc, integration-token-svc)",
    )
    p_new.add_argument(
        "--depends-outcluster",
        help="Comma-separated list of out-of-cluster dependencies (e.g. https://auth0.example.com)",
    )
    p_new.add_argument(
        "--branch",
        default="component-instances",
        help="Local git branch to store generated manifests",
    )
    p_new.set_defaults(func=_confirm_command(create_component))

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    code = main()
    sys.exit(code)
