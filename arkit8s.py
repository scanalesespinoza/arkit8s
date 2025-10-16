#!/usr/bin/env python3
"""Cross-platform CLI for arkit8s utilities."""
from __future__ import annotations

import argparse
import json
import random
import shutil
import ssl
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utilities.assistant_model import (
    AssistantModelNotFoundError,
    generate_assistant_reply,
    train_assistant_knowledge_base,
)

HELP_START_MARKER = "<!-- BEGIN ARKIT8S HELP -->"
HELP_END_MARKER = "<!-- END ARKIT8S HELP -->"

REPO_ROOT = Path(__file__).resolve().parent
ARCH_DIR = REPO_ROOT / "architecture"
UTIL_DIR = REPO_ROOT / "utilities"
ENV_DIR = REPO_ROOT / "environments"
SIM_TEMPLATE_PATH = UTIL_DIR / "simulator-deployment.yaml.tpl"

DEFAULT_ENV = "sandbox"
DEFAULT_SCENARIO = "default"
DEFAULT_SIMULATOR_COUNT = 10

COMMAND_OUTPUT_FILE = REPO_ROOT / "tmp" / "command-output.out"
EXPECTED_PRODUCT_ROUTES: dict[tuple[str, str], str] = {
    ("shared-components", "gitlab-ce"): "GitLab CE",
    ("shared-components", "keycloak"): "Keycloak",
    ("support-domain", "architects-visualization"): "Architects Visualization",
}

WEB_CONSOLE_DIR = ARCH_DIR / "support-domain" / "architects-visualization"
WEB_CONSOLE_COMMANDS_CONFIGMAP = WEB_CONSOLE_DIR / "console-commands-configmap.yaml"
PIPELINES_DIR = ARCH_DIR / "shared-components" / "openshift-pipelines"


@dataclass(frozen=True)
class CommandDefinition:
    """Describe a CLI command along with its handler and parser configuration."""

    name: str
    handler: Callable[[argparse.Namespace], int]
    summary: str
    description: str | None = None
    configure: Callable[[argparse.ArgumentParser], None] | None = None


@dataclass(frozen=True)
class CommandGroup:
    """Group related commands under a shared namespace."""

    name: str
    summary: str
    description: str | None
    commands: tuple[CommandDefinition, ...]


class AssistantQueryError(Exception):
    """Raised when an invocation debe redirigirse al asistente inteligente."""


class AssistantAwareArgumentParser(argparse.ArgumentParser):
    """Custom parser que redirige errores al asistente."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise AssistantQueryError(message)


@dataclass(frozen=True)
class DefaultComponent:
    """Representa un componente principal de la arquitectura por defecto."""

    name: str
    namespace: str
    kind: str
    route_name: str | None = None
    expected_route_host: str | None = None


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


def _configure_cluster_deploy(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env",
        default=DEFAULT_ENV,
        help="Nombre del entorno en environments/ (por defecto: sandbox).",
    )


def _configure_cluster_reset(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env",
        default=DEFAULT_ENV,
        help="Entorno a limpiar por completo (por defecto: sandbox).",
    )


def _configure_cluster_watch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env",
        default=DEFAULT_ENV,
        help="Entorno a monitorear (por defecto: sandbox).",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=5,
        help="Duración del monitoreo en minutos (por defecto: 5).",
    )
    parser.add_argument(
        "--detail",
        choices=["default", "detailed", "all"],
        default="default",
        help="Nivel de detalle de la salida (default, detailed o all).",
    )


def _configure_cluster_validate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env",
        default=DEFAULT_ENV,
        help="Entorno a validar (por defecto: sandbox).",
    )


def _configure_scenarios_deploy(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--simulators",
        type=int,
        default=DEFAULT_SIMULATOR_COUNT,
        help="Cantidad de simuladores aleatorios a desplegar (por defecto: 10).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Semilla opcional para reproducir la distribución de simuladores.",
    )


def _configure_simulators_generate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Número de simuladores por componente (por defecto: 3).",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=sorted(BUSINESS_SIM_TARGETS.keys()),
        default=sorted(BUSINESS_SIM_TARGETS.keys()),
        help="Componentes de negocio a los que se agregará carga (por defecto: todos).",
    )
    parser.add_argument(
        "--branch",
        default="load-simulators",
        help="Rama local donde se guardarán los manifiestos generados.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Semilla para generar comportamientos deterministas.",
    )
    parser.add_argument(
        "--behavior",
        choices=["dynamic", "ok", "notready", "restart"],
        help="Comportamiento forzado de los simuladores (por defecto: dinámico).",
    )


def _configure_simulators_cleanup(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=sorted(BUSINESS_SIM_TARGETS.keys()),
        help="Componentes cuyas definiciones de simulador se eliminarán.",
    )
    parser.add_argument(
        "--branch",
        default="load-simulators",
        help="Rama local que contiene los manifiestos generados.",
    )
    parser.add_argument(
        "--delete-branch",
        action="store_true",
        help="Elimina la rama local indicada tras limpiar los manifiestos.",
    )


def _configure_assistant_train(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--epochs",
        type=int,
        default=6,
        help="Cantidad de épocas para entrenar la red neuronal (por defecto: 6).",
    )
    parser.add_argument(
        "--hidden-size",
        type=int,
        default=128,
        help="Dimensión del espacio latente utilizado por el asistente (por defecto: 128).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Tamaño del batch para el entrenamiento (por defecto: 16).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1200,
        help="Longitud máxima por fragmento de texto al generar el dataset (por defecto: 1200).",
    )
    parser.add_argument(
        "--min-frequency",
        type=int,
        default=2,
        help="Frecuencia mínima de un término para formar parte del vocabulario (por defecto: 2).",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        help="Límite opcional de fragmentos a indexar para acelerar entrenamientos de prueba.",
    )


def _configure_components_create(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="Nombre del componente a crear.")
    parser.add_argument("--type", required=True, help="Tipo según component_inventory.yaml.")
    parser.add_argument(
        "--domain",
        required=True,
        choices=["business", "support", "shared"],
        help="Dominio donde residirá el componente.",
    )
    parser.add_argument("--function", help="Sobrescribe la anotación architecture.function.")
    parser.add_argument(
        "--depends-incluster",
        help="Dependencias dentro del clúster separadas por comas.",
    )
    parser.add_argument(
        "--depends-outcluster",
        help="Dependencias externas separadas por comas.",
    )
    parser.add_argument(
        "--branch",
        default="component-instances",
        help="Rama local donde se almacenarán los manifiestos creados.",
    )

def train_assistant_command(args: argparse.Namespace) -> int:
    summary = train_assistant_knowledge_base(
        REPO_ROOT,
        epochs=args.epochs,
        hidden_size=args.hidden_size,
        batch_size=args.batch_size,
        max_chars=args.max_chars,
        min_frequency=args.min_frequency,
        max_chunks=args.max_chunks,
    )
    print("Asistente entrenado correctamente.")
    print(
        "Fragmentos indexados: {chunks} | Vocabulario: {vocab_size} | Épocas: {epochs}".format(
            chunks=summary["chunks"], vocab_size=summary["vocab_size"], epochs=summary["epochs"]
        )
    )
    print(f"Archivo generado en: {summary['artifacts']}")
    return 0


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


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and stream output."""
    return subprocess.run(cmd, check=check)


def _ensure_yaml_module():
    """Return the PyYAML module, installing it locally if necessary."""

    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - handled at runtime
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", "pyyaml"],
            check=False,
        )
        import yaml  # type: ignore

    return yaml  # type: ignore


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
    env = getattr(args, "env", DEFAULT_ENV)
    try:
        run(["oc", "apply", "-k", str(ARCH_DIR / "bootstrap")])
        run(["oc", "apply", "-k", str(ENV_DIR / env)])
    except subprocess.CalledProcessError:
        print(
            "\u26a0\ufe0f  Verifica que la cuenta tenga permisos para crear namespaces y aplicar recursos",
            file=sys.stderr,
        )
        return 1
    status = validate_cluster(args)
    route_status, missing_routes = _record_route_summary(env)
    if missing_routes:
        print(
            "⚠️  Productos sin Route configurada: " + ", ".join(sorted(missing_routes)) + ".",
            file=sys.stderr,
        )
    elif route_status != 0:
        print(
            "⚠️  No fue posible registrar las Routes del clúster; revisa el archivo de salida.",
            file=sys.stderr,
        )
    print(f"📝 Consulta {COMMAND_OUTPUT_FILE} para los detalles de las URLs expuestas.")
    if status == 0 and route_status != 0:
        status = route_status
    return status


def uninstall(_args: argparse.Namespace) -> int:
    run(["oc", "delete", "-f", str(ARCH_DIR), "--recursive"], check=False)
    run(["oc", "delete", "-f", str(ARCH_DIR / "bootstrap")], check=False)
    return 0


def _wait_for_crd(crd: str, timeout: int = 600, interval: int = 10) -> bool:
    """Poll the cluster until the requested CRD is available or timeout expires."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        proc = subprocess.run(
            ["oc", "get", "crd", crd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode == 0:
            return True
        time.sleep(interval)

    return False


def install_openshift_pipelines(_args: argparse.Namespace) -> int:
    """Install OpenShift Pipelines using the GitOps manifests tracked in the repo."""

    subscription_path = PIPELINES_DIR / "subscription.yaml"
    tektonconfig_path = PIPELINES_DIR / "tektonconfig.yaml"

    proc = run(["oc", "apply", "-f", str(subscription_path)], check=False)
    if proc.returncode != 0:
        print(
            "⚠️  No se pudieron aplicar los manifiestos de OpenShift Pipelines; revisa permisos y el estado del clúster.",
            file=sys.stderr,
        )
        return proc.returncode or 1

    if not _wait_for_crd("tektonconfigs.operator.tekton.dev"):
        print(
            "⚠️  La CRD tektonconfigs.operator.tekton.dev no estuvo disponible en 10 minutos; revisa el estado del operador.",
            file=sys.stderr,
        )
        return 1

    proc = run(["oc", "apply", "-f", str(tektonconfig_path)], check=False)
    if proc.returncode != 0:
        print(
            "⚠️  No se pudieron aplicar los manifiestos de OpenShift Pipelines; revisa permisos y el estado del clúster.",
            file=sys.stderr,
        )
        return proc.returncode or 1

    wait_proc = run(
        ["oc", "wait", "--for=condition=Ready", "tektonconfig/config", "--timeout=600s"],
        check=False,
    )
    if wait_proc.returncode != 0:
        print(
            "⚠️  Los recursos se aplicaron, pero TektonConfig/config no alcanzó la condición Ready en 10 minutos.",
            file=sys.stderr,
        )
        return wait_proc.returncode or 1

    print("✅ OpenShift Pipelines quedó listo para sincronizar pipelines declarativos.")
    return 0


def cleanup_openshift_pipelines(_args: argparse.Namespace) -> int:
    """Remove the GitOps-managed OpenShift Pipelines subscription and payload."""

    status = 0

    proc = run(["oc", "delete", "-k", str(PIPELINES_DIR)], check=False)
    if proc.returncode != 0:
        status = proc.returncode

    ns_proc = run(
        ["oc", "delete", "project", "openshift-pipelines", "--ignore-not-found"],
        check=False,
    )
    if status == 0 and ns_proc.returncode != 0:
        status = ns_proc.returncode

    return status


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


def sync_web_console(_args: argparse.Namespace) -> int:
    """Export CLI command metadata for the Quarkus web control plane."""

    yaml = _ensure_yaml_module()
    parser = build_parser()
    commands: list[dict[str, str]] = []

    summary_lookup = {
        f"{group.name} {cmd.name}": cmd.summary
        for group in COMMAND_GROUPS
        for cmd in group.commands
    }

    top_level = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if not top_level:
        return 1

    for group_name, group_parser in sorted(top_level[0].choices.items()):
        nested = [
            action
            for action in group_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        if not nested:
            continue
        for command_name, command_parser in sorted(nested[0].choices.items()):
            full_name = f"{group_name} {command_name}"
            usage = " ".join(command_parser.format_usage().split())
            summary = summary_lookup.get(full_name, usage)
            commands.append(
                {
                    "name": full_name,
                    "summary": summary,
                    "usage": usage,
                }
            )

    payload = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "architects-console-commands",
            "namespace": "support-domain",
            "labels": {
                "app.kubernetes.io/name": "architects-visualization",
                "app.kubernetes.io/component": "control-plane",
                "app.kubernetes.io/part-of": "arkit8s",
            },
            "annotations": {
                "architecture.domain": "support",
                "architecture.function": "architecture-visualization",
                "architecture.part_of": "arkit8s",
            },
        },
        "data": {
            "commands.json": json.dumps(
                {
                    "commands": commands,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    }

    WEB_CONSOLE_DIR.mkdir(parents=True, exist_ok=True)
    WEB_CONSOLE_COMMANDS_CONFIGMAP.write_text(
        yaml.dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    print(f"📦 ConfigMap de comandos actualizada en {WEB_CONSOLE_COMMANDS_CONFIGMAP}")
    return 0


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


def _record_route_summary(env: str) -> tuple[int, list[str]]:
    """Store the list of available Routes and highlight missing products."""

    output_path = COMMAND_OUTPUT_FILE
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# Routes disponibles para el entorno {env}",
        f"# Generado: {timestamp}",
        "",
    ]

    try:
        proc = subprocess.run(
            ["oc", "get", "route", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        lines.append("⚠️  El comando 'oc' no está disponible; no se pueden listar Routes.")
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1, []
    except subprocess.CalledProcessError as err:
        lines.append("⚠️  Error al ejecutar 'oc get route -A -o json'.")
        stderr = (err.stderr or "").strip()
        if stderr:
            lines.append(stderr)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return err.returncode or 1, []

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        lines.append("⚠️  No fue posible interpretar la salida JSON de 'oc get route'.")
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1, []

    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        lines.append("No se encontraron Routes en el clúster.")
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1, list(EXPECTED_PRODUCT_ROUTES.values())

    header = "\t".join(["NAMESPACE", "NAME", "HOST", "SERVICE"])
    lines.append(header)
    found: set[tuple[str, str]] = set()
    entries: list[tuple[str, str, str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        namespace = meta.get("namespace", "") if isinstance(meta, dict) else ""
        name = meta.get("name", "") if isinstance(meta, dict) else ""
        host = spec.get("host", "") if isinstance(spec, dict) else ""
        service = ""
        if isinstance(spec, dict):
            to = spec.get("to", {})
            if isinstance(to, dict):
                service = to.get("name", "") or ""
        if namespace and name:
            found.add((namespace, name))
        entries.append((namespace, name, host or "-", service or "-"))

    for namespace, name, host, service in sorted(entries):
        lines.append("\t".join([namespace or "-", name or "-", host, service]))

    missing = [
        product
        for key, product in EXPECTED_PRODUCT_ROUTES.items()
        if key not in found
    ]

    lines.append("")
    if missing:
        lines.append("⚠️  Productos sin Route detectada: " + ", ".join(sorted(missing)) + ".")
    else:
        lines.append("✅ Todos los productos esperados cuentan con Route.")

    lines.append("")
    lines.append("Comando ejecutado: oc get route -A -o json")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (0 if not missing else 1), missing


def _load_default_components() -> list[DefaultComponent]:
    """Descubre los componentes base y sus rutas asociadas dentro de architecture/."""

    yaml = _ensure_yaml_module()
    components: dict[tuple[str, str], dict[str, str]] = {}
    route_targets: dict[tuple[str, str], dict[str, str | None]] = {}

    for path in sorted(ARCH_DIR.rglob("*.yaml")):
        if path.name == "kustomization.yaml":
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                docs = list(yaml.safe_load_all(fh))
        except FileNotFoundError:
            continue
        except yaml.YAMLError:
            continue

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            kind = doc.get("kind")
            metadata = doc.get("metadata")
            if not isinstance(metadata, dict):
                continue
            name = metadata.get("name")
            namespace = metadata.get("namespace")
            if not isinstance(name, str) or not name:
                continue
            if not isinstance(namespace, str) or not namespace:
                continue

            if kind in {"Deployment", "StatefulSet"}:
                labels = metadata.get("labels")
                if isinstance(labels, dict):
                    label_value = labels.get("arkit8s.simulator")
                    if isinstance(label_value, str) and label_value.lower() == "true":
                        continue
                components[(namespace, name)] = {
                    "name": name,
                    "namespace": namespace,
                    "kind": kind or "Deployment",
                }
            elif kind == "Route":
                spec = doc.get("spec")
                if not isinstance(spec, dict):
                    continue
                to = spec.get("to")
                if not isinstance(to, dict):
                    continue
                target = to.get("name")
                host = spec.get("host")
                if (
                    isinstance(target, str)
                    and target
                    and isinstance(host, str)
                    and host
                ):
                    route_targets[(namespace, target)] = {
                        "route_name": name,
                        "expected_host": host,
                    }

    result: list[DefaultComponent] = []
    for key, info in sorted(components.items()):
        route_info = route_targets.get(key, {})
        result.append(
            DefaultComponent(
                name=info["name"],
                namespace=info["namespace"],
                kind=info["kind"],
                route_name=route_info.get("route_name"),
                expected_route_host=route_info.get("expected_host"),
            )
        )
    return result


def _fetch_cluster_routes() -> tuple[dict[tuple[str, str], str], str | None]:
    """Recupera las Routes disponibles en el clúster indexadas por namespace/nombre."""

    try:
        proc = subprocess.run(
            ["oc", "get", "route", "-A", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        return {}, "El comando 'oc' no está disponible en el PATH."
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or err.stdout or str(err)).strip()
        return {}, detail or "Error al ejecutar 'oc get route -A -o json'."

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}, "No se pudo interpretar la salida JSON de 'oc get route'."

    mapping: dict[tuple[str, str], str] = {}
    items = data.get("items", []) if isinstance(data, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        namespace = meta.get("namespace") if isinstance(meta, dict) else None
        name = meta.get("name") if isinstance(meta, dict) else None
        host = spec.get("host") if isinstance(spec, dict) else None
        if (
            isinstance(namespace, str)
            and namespace
            and isinstance(name, str)
            and name
            and isinstance(host, str)
            and host
        ):
            mapping[(namespace, name)] = host
    return mapping, None


def _check_workload_status(component: DefaultComponent) -> tuple[bool, str]:
    """Valida el estado de un Deployment/StatefulSet reportando réplicas listas."""

    resource_map = {
        "Deployment": "deployment",
        "StatefulSet": "statefulset",
    }
    resource = resource_map.get(component.kind, component.kind.lower())
    try:
        proc = subprocess.run(
            [
                "oc",
                "get",
                resource,
                component.name,
                "-n",
                component.namespace,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        return False, "El comando 'oc' no está disponible en el PATH."
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or err.stdout or str(err)).strip()
        return False, detail or f"'oc get {resource} {component.name}' no tuvo éxito."

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False, "No se pudo interpretar la salida JSON del recurso."

    spec = data.get("spec", {}) if isinstance(data, dict) else {}
    status = data.get("status", {}) if isinstance(data, dict) else {}

    def _as_int(value: object, default: int) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    desired = _as_int(spec.get("replicas"), 1)
    ready = _as_int(status.get("readyReplicas"), 0)
    available = _as_int(status.get("availableReplicas"), ready)

    if component.kind == "StatefulSet":
        effective_ready = ready
    else:
        effective_ready = max(ready, available)

    message = f"réplicas listas {effective_ready}/{desired}"
    is_ready = desired == 0 or effective_ready >= desired

    if not is_ready:
        conditions = status.get("conditions") if isinstance(status, dict) else None
        details: list[str] = []
        if isinstance(conditions, list):
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                cond_type = cond.get("type")
                cond_status = cond.get("status")
                if cond_type in {"Available", "Ready", "Progressing", "Degraded"}:
                    reason = cond.get("reason")
                    cond_message = cond.get("message")
                    parts = [p for p in (cond_type, reason, cond_message) if isinstance(p, str) and p]
                    if parts:
                        details.append(" - ".join(parts))
        if details:
            message += " | " + "; ".join(details)

    return is_ready, message


def _probe_route(host: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Realiza peticiones HTTP/HTTPS a la ruta indicada y devuelve el resultado."""

    context = ssl._create_unverified_context()
    attempts: list[str] = []

    for scheme in ("https", "http"):
        url = f"{scheme}://{host}"
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                status_code = getattr(response, "status", None)
                if status_code is None:
                    status_code = response.getcode()
                if 200 <= status_code < 400:
                    return True, f"{url} → HTTP {status_code}"
                attempts.append(f"{url}: HTTP {status_code}")
        except urllib.error.HTTPError as err:
            attempts.append(f"{url}: HTTP {err.code}")
        except urllib.error.URLError as err:
            reason = getattr(err, "reason", None)
            attempts.append(f"{url}: {reason if reason else err}")
        except Exception as exc:  # pragma: no cover - fallback defensivo
            attempts.append(f"{url}: {exc}")

    return False, "; ".join(attempts) if attempts else "No se pudo contactar la ruta."


def validate_default_architecture(_args: argparse.Namespace) -> int:
    """Valida periódicamente que la arquitectura base esté disponible funcionalmente."""

    components = _load_default_components()
    if not components:
        print(
            "No se encontraron componentes base en architecture/.",
            file=sys.stderr,
        )
        return 1

    interval_seconds = 10
    per_component_estimate = 20
    max_wait = max(interval_seconds, per_component_estimate * len(components), 120)
    deadline = time.time() + max_wait

    print(
        "🔁 Iniciando validación funcional de la arquitectura por defecto "
        f"({len(components)} componentes detectados)."
    )
    print(
        "⏳ Tiempo máximo estimado: "
        f"{max_wait} segundos (≈{per_component_estimate}s por componente)."
    )

    attempt = 0
    while True:
        attempt += 1
        route_map, route_error = _fetch_cluster_routes()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] Iteración {attempt}")

        all_ok = True
        for component in components:
            workload_ok, workload_msg = _check_workload_status(component)
            line = (
                f" - {component.namespace}/{component.name} "
                f"({component.kind}): "
            )
            if workload_ok:
                line += f"✅ {workload_msg}"
            else:
                line += f"❌ {workload_msg}"
                all_ok = False

            if component.route_name:
                if route_error:
                    line += f" | URL ❌ {route_error}"
                    all_ok = False
                else:
                    host = route_map.get((component.namespace, component.route_name))
                    if not host:
                        expected = component.expected_route_host or "desconocido"
                        line += (
                            " | URL ❌ Route no encontrada en el clúster "
                            f"(esperada {component.route_name} → {expected})."
                        )
                        all_ok = False
                    else:
                        route_ok, route_msg = _probe_route(host)
                        if route_ok:
                            line += f" | URL ✅ {route_msg}"
                        else:
                            line += f" | URL ❌ {route_msg}"
                            all_ok = False
            else:
                line += " | Sin URL expuesta"

            print(line)

        if all_ok:
            print(
                "\n🎉 Todos los componentes respondieron correctamente. "
                "La arquitectura por defecto está operativa."
            )
            return 0

        if time.time() >= deadline:
            print(
                "\n❌ No se ha logrado validar en el tiempo máximo estimado. "
                "Revisa la instalación y vuelve a ejecutar el comando de validación.",
                file=sys.stderr,
            )
            return 1

        time.sleep(interval_seconds)


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


def _build_default_simulator_manifest(
    total: int, seed: int | None = None
) -> tuple[str, dict[str, int]]:
    """Return a multi-document YAML string with randomly distributed simulators."""

    if total <= 0:
        return "", {key: 0 for key in BUSINESS_SIM_TARGETS}

    if not SIM_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            "Plantilla de simuladores no encontrada. Ejecuta desde la raíz del repositorio.",
        )

    yaml = _ensure_yaml_module()
    template_text = SIM_TEMPLATE_PATH.read_text(encoding="utf-8")
    rng = random.Random(seed)
    choices = list(BUSINESS_SIM_TARGETS.items())

    counts: dict[str, int] = {key: 0 for key in BUSINESS_SIM_TARGETS}
    manifests: list[str] = []

    for _ in range(total):
        target, info = rng.choice(choices)
        counts[target] += 1
        ordinal = counts[target]
        suffix = rng.randrange(1000, 9999)
        name = f"{info['name_prefix']}-{ordinal:02d}-{suffix}"
        behavior_seed = rng.randrange(1, 2**31)

        rendered = template_text.format(
            name=name,
            namespace="business-domain",
            behavior="dynamic",
            behavior_seed=behavior_seed,
            simulated_component=info["simulated_component"],
            function_annotation=info["function_annotation"],
        )

        doc = yaml.safe_load(rendered)
        if not isinstance(doc, dict):
            continue

        metadata = doc.setdefault("metadata", {})
        labels = metadata.setdefault("labels", {})
        labels["arkit8s.scenario"] = DEFAULT_SCENARIO
        annotations = metadata.setdefault("annotations", {})
        annotations["arkit8s.scenario"] = DEFAULT_SCENARIO

        template_metadata = (
            doc.setdefault("spec", {})
            .setdefault("template", {})
            .setdefault("metadata", {})
        )
        template_labels = template_metadata.setdefault("labels", {})
        template_labels["arkit8s.scenario"] = DEFAULT_SCENARIO

        manifest_text = yaml.safe_dump(doc, sort_keys=False)
        manifests.append(manifest_text.strip())

    combined = "\n---\n".join(manifests)
    if combined:
        combined += "\n"

    return combined, counts


def _deploy_default_simulators(
    total: int, seed: int | None = None
) -> tuple[int, dict[str, int]]:
    """Apply simulator manifests to the cluster and return their distribution."""

    try:
        manifest, counts = _build_default_simulator_manifest(total, seed=seed)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 1, {key: 0 for key in BUSINESS_SIM_TARGETS}

    if not manifest:
        return 0, counts

    try:
        proc = subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=manifest,
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        print("error: comando 'oc' no encontrado", file=sys.stderr)
        return 1, counts
    except subprocess.CalledProcessError as err:
        if err.stdout:
            print(err.stdout, end="")
        if err.stderr:
            sys.stderr.write(err.stderr)
        return err.returncode, counts

    if proc.stdout.strip():
        print(proc.stdout.strip())

    return 0, counts


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


def _delete_default_simulators() -> int:
    """Delete simulator deployments tagged with the default scenario label."""

    try:
        proc = subprocess.run(
            [
                "oc",
                "delete",
                "deploy",
                "-A",
                "-l",
                f"arkit8s.scenario={DEFAULT_SCENARIO}",
                "--ignore-not-found",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("error: comando 'oc' no encontrado", file=sys.stderr)
        return 1

    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0 and proc.stderr:
        sys.stderr.write(proc.stderr)

    return 0 if proc.returncode == 0 else proc.returncode


def install_default(args: argparse.Namespace) -> int:
    """Install the sandbox environment and provision the default scenario."""

    env_args = argparse.Namespace(env=DEFAULT_ENV)
    print(f"🚀 Instalando escenario '{DEFAULT_SCENARIO}' en el entorno {DEFAULT_ENV}...")
    status = install(env_args)
    if status != 0:
        return status

    total = getattr(args, "simulators", DEFAULT_SIMULATOR_COUNT)
    seed = getattr(args, "seed", None)

    sim_status, counts = _deploy_default_simulators(total, seed=seed)
    if sim_status != 0:
        return sim_status

    if total > 0:
        print("📊 Distribución de simuladores por componente:")
        for target, count in sorted(counts.items()):
            if count:
                print(f"  - {target}: {count}")

    return 0


def cleanup_default(_args: argparse.Namespace) -> int:
    """Remove the default scenario and clean up the sandbox environment."""

    print(f"🧹 Eliminando simuladores del escenario '{DEFAULT_SCENARIO}'...")
    sim_status = _delete_default_simulators()
    env_args = argparse.Namespace(env=DEFAULT_ENV)
    print(f"🧼 Limpiando recursos del entorno {DEFAULT_ENV}...")
    cleanup_status = cleanup(env_args)

    if sim_status != 0:
        return sim_status
    return cleanup_status


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


COMMAND_GROUPS: tuple[CommandGroup, ...] = (
    CommandGroup(
        name="cluster",
        summary="Instala, valida y monitorea entornos declarativos de arkit8s.",
        description=(
            "Acciones principales para reconciliar los manifiestos y revisar que el "
            "clúster permanezca en sincronía con el repositorio."
        ),
        commands=(
            CommandDefinition(
                name="deploy",
                handler=install,
                summary="Aplica bootstrap y el overlay del entorno seleccionado.",
                description="Aplica los manifiestos base y del entorno definido en environments/.",
                configure=_configure_cluster_deploy,
            ),
            CommandDefinition(
                name="remove",
                handler=uninstall,
                summary="Elimina los manifiestos aplicados sin fallar si ya no existen.",
                description="Ejecuta oc delete sobre la arquitectura completa para limpiar recursos declarados.",
            ),
            CommandDefinition(
                name="reset",
                handler=cleanup,
                summary="Borra recursos y namespaces del entorno indicado.",
                description="Elimina el overlay del entorno y los namespaces bootstrap para iniciar desde cero.",
                configure=_configure_cluster_reset,
            ),
            CommandDefinition(
                name="validate",
                handler=validate_cluster,
                summary="Revisa namespaces, deployments, pods y diferencias declarativas.",
                description="Valida que el estado del clúster coincida con los manifiestos del entorno seleccionado.",
                configure=_configure_cluster_validate,
            ),
            CommandDefinition(
                name="validate-default",
                handler=validate_default_architecture,
                summary="Verifica periódicamente los componentes y Routes de la arquitectura por defecto.",
                description=(
                    "Ejecuta comprobaciones de despliegues y peticiones HTTP cada 10 segundos hasta que todos los "
                    "componentes estén listos o se alcance el tiempo máximo estimado."
                ),
            ),
            CommandDefinition(
                name="watch",
                handler=watch,
                summary="Ejecuta validaciones periódicas para detectar desincronizaciones.",
                description="Monitorea cada 30 segundos el estado del clúster mostrando diferencias y recursos relevantes.",
                configure=_configure_cluster_watch,
            ),
        ),
    ),
    CommandGroup(
        name="pipelines",
        summary="Administra la instalación GitOps de OpenShift Pipelines.",
        description="Comandos dedicados a habilitar o retirar Tekton gestionado por manifiestos declarativos.",
        commands=(
            CommandDefinition(
                name="install",
                handler=install_openshift_pipelines,
                summary="Aplica la suscripción y TektonConfig gestionados por GitOps.",
                description="Instala OpenShift Pipelines esperando hasta que TektonConfig/config quede en condición Ready.",
            ),
            CommandDefinition(
                name="cleanup",
                handler=cleanup_openshift_pipelines,
                summary="Elimina la suscripción y limpia el proyecto openshift-pipelines.",
                description="Retira los recursos gestionados por GitOps y solicita la eliminación del namespace generado.",
            ),
        ),
    ),
    CommandGroup(
        name="scenarios",
        summary="Gestiona escenarios de simulación preconfigurados.",
        description="Acciones empaquetadas que combinan despliegues y simuladores listos para probar arkit8s.",
        commands=(
            CommandDefinition(
                name="deploy-default",
                handler=install_default,
                summary="Instala el entorno sandbox y distribuye simuladores aleatorios.",
                description="Despliega el escenario default generando simuladores distribuidos entre los componentes disponibles.",
                configure=_configure_scenarios_deploy,
            ),
            CommandDefinition(
                name="cleanup-default",
                handler=cleanup_default,
                summary="Elimina simuladores y limpia el entorno sandbox.",
                description="Retira el escenario por defecto y deja el entorno listo para una reinstalación limpia.",
            ),
        ),
    ),
    CommandGroup(
        name="simulators",
        summary="Orquesta simuladores de carga para componentes de negocio.",
        description="Herramientas para generar, listar y limpiar despliegues sintéticos que ejercitan la arquitectura.",
        commands=(
            CommandDefinition(
                name="generate",
                handler=generate_load_simulators,
                summary="Crea manifiestos y despliegues de simuladores por componente.",
                description="Genera Deployments etiquetados como simuladores y actualiza los kustomization.yaml correspondientes.",
                configure=_configure_simulators_generate,
            ),
            CommandDefinition(
                name="list",
                handler=list_load_simulators,
                summary="Enumera los simuladores desplegados en el clúster.",
                description="Consulta Deployments etiquetados con arkit8s.simulator=true y muestra su comportamiento actual.",
            ),
            CommandDefinition(
                name="cleanup",
                handler=cleanup_load_simulators,
                summary="Elimina simuladores y limpia los manifiestos generados.",
                description="Borra los Deployments sintéticos, elimina load-simulators.yaml y actualiza kustomization.yaml.",
                configure=_configure_simulators_cleanup,
            ),
        ),
    ),
    CommandGroup(
        name="metadata",
        summary="Genera reportes y valida anotaciones de arquitectura.",
        description="Validaciones y utilidades para mantener trazabilidad y dependencias coherentes.",
        commands=(
            CommandDefinition(
                name="lint-yaml",
                handler=validate_yaml,
                summary="Verifica la validez sintáctica de los manifiestos YAML.",
                description="Recorre el repositorio validando todos los archivos YAML excepto kustomization.yaml.",
            ),
            CommandDefinition(
                name="report",
                handler=report,
                summary="Genera un reporte Markdown con la trazabilidad de componentes.",
                description="Produce un resumen de componentes, relaciones y archivos fuente basados en anotaciones architecture.*.",
            ),
            CommandDefinition(
                name="audit",
                handler=validate_metadata,
                summary="Comprueba coherencia entre llamadas declaradas y NetworkPolicies.",
                description="Valida que los campos calls/invoked_by sean recíprocos y que las políticas de red permitan el tráfico.",
            ),
            CommandDefinition(
                name="network-policies",
                handler=generate_network_policies,
                summary="Genera NetworkPolicies derivadas de las anotaciones architecture.*.",
                description="Construye manifiestos de NetworkPolicy en memoria a partir de dependencias declaradas en los componentes.",
            ),
        ),
    ),
    CommandGroup(
        name="components",
        summary="Crea instancias declarativas basadas en el inventario de componentes.",
        description="Automatiza la generación de carpetas, manifiestos y kustomization por dominio.",
        commands=(
            CommandDefinition(
                name="create",
                handler=create_component,
                summary="Genera deployment/service y actualiza el kustomization del dominio.",
                description="Crea una instancia de componente siguiendo component_inventory.yaml y prepara la rama de trabajo.",
                configure=_configure_components_create,
            ),
        ),
    ),
    CommandGroup(
        name="console",
        summary="Sincroniza la metadata del CLI con la consola web Architects Visualization.",
        description="Genera el ConfigMap consumido por la aplicación Quarkus para mostrar los comandos disponibles.",
        commands=(
            CommandDefinition(
                name="sync",
                handler=sync_web_console,
                summary="Actualiza el ConfigMap de comandos consumido por la consola web.",
                description="Exporta nombre, resumen y uso de cada comando para mantener la interfaz web alineada con el CLI.",
            ),
        ),
    ),
    CommandGroup(
        name="assistant",
        summary="Gestiona el asistente inteligente basado en deep learning.",
        description=(
            "Herramientas para entrenar el modelo neuronal que responde preguntas sobre el repositorio y recomienda"
            " comandos cuando el CLI se utiliza incorrectamente."
        ),
        commands=(
            CommandDefinition(
                name="train",
                handler=train_assistant_command,
                summary="Genera el modelo del asistente procesando el repositorio actual.",
                description=(
                    "Construye un modelo de aprendizaje profundo que indexa el contenido del repositorio para responder"
                    " preguntas y sugerir comandos alternativos."
                ),
                configure=_configure_assistant_train,
            ),
        ),
    ),
)


def _command_documents() -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for group in COMMAND_GROUPS:
        for command in group.commands:
            name = f"{group.name} {command.name}"
            description = f"{command.summary}. {(command.description or '').strip()}".strip()
            docs.append((name, description))
    docs.append(
        (
            "train-assistant",
            "Alias del comando assistant train que genera el modelo del asistente de arkit8s.",
        )
    )
    return docs


def _build_assistant_command_corpus() -> list[tuple[str, str]]:
    return _command_documents()


def _default_command_suggestions(limit: int = 3) -> list[tuple[str, str]]:
    docs = _command_documents()
    return docs[:limit]


def _handle_assistant_question(question: str, *, reason: str) -> int:
    print("🤖  Asistente arkit8s")
    print(f"Motivo de la asistencia: {reason}.")
    try:
        reply = generate_assistant_reply(question, _build_assistant_command_corpus())
    except AssistantModelNotFoundError:
        print(
            "No se encontró un modelo entrenado. Ejecuta './arkit8s.py train-assistant' para generar las respuestas."
        )
        return 1
    except ValueError as exc:
        print(f"No se pudo interpretar la pregunta: {exc}")
        print(
            "Intenta reformularla con palabras clave presentes en el repositorio o vuelve a entrenar el asistente"
            " con más fragmentos."
        )
        print("\nComandos frecuentes:")
        for name, description in _default_command_suggestions():
            print(f"- {name}: {description}")
        return 1

    print()
    print(textwrap.fill(reply.answer, width=100))

    if reply.supporting_chunks:
        print("\nFragmentos relacionados:")
        for source, snippet in reply.supporting_chunks:
            print(f"- {source}")
            print(textwrap.indent(textwrap.fill(snippet, width=100), "  "))

    if reply.command_suggestions:
        print("\nComandos sugeridos:")
        for name, score in reply.command_suggestions:
            print(f"- {name}: {score}")

    return 0


def build_parser(
    parser_class: type[argparse.ArgumentParser] = argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    parser = parser_class(
        description=USAGE_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    top_level = parser.add_subparsers(dest="group", metavar="<grupo>", required=True)

    for group in COMMAND_GROUPS:
        group_parser = top_level.add_parser(
            group.name,
            help=group.summary,
            description=group.description or group.summary,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        sub = group_parser.add_subparsers(dest="command", metavar="<comando>", required=True)
        for command in group.commands:
            cmd_parser = sub.add_parser(
                command.name,
                help=command.summary,
                description=command.description or command.summary,
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            if command.configure:
                command.configure(cmd_parser)
            cmd_parser.set_defaults(func=command.handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)

    if not args_list:
        parser = build_parser()
        parser.print_help()
        return 1

    if args_list[0] == "train-assistant":
        args_list = ["assistant", "train", *args_list[1:]]

    if len(args_list) == 1 and not args_list[0].startswith("-"):
        token = args_list[0]
        known_groups = {group.name for group in COMMAND_GROUPS}
        if token in known_groups:
            reason = "comando incompleto"
        elif " " in token or token.endswith("?"):
            reason = "consulta directa"
        else:
            reason = "comando no reconocido"
        return _handle_assistant_question(token, reason=reason)

    parser = build_parser(AssistantAwareArgumentParser)
    try:
        args = parser.parse_args(args_list)
    except AssistantQueryError:
        question = " ".join(args_list)
        return _handle_assistant_question(question, reason="comando no reconocido")

    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    code = main()
    sys.exit(code)
