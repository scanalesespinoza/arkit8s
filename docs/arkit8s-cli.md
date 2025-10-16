# arkit8s CLI

## Nombre
`arkit8s` — interfaz de línea de comandos para operar la arquitectura de referencia arkit8s sobre OpenShift.

## Sinopsis
```
./arkit8s.py <grupo> <comando> [opciones]
```

Cada acción del CLI se organiza en grupos temáticos para descubrir rápidamente sus funciones.

## Descripción
El script `arkit8s.py` encapsula tareas frecuentes para instalar manifiestos Kustomize, validar estados del clúster y generar artefactos auxiliares como reportes o simuladores de carga. Las acciones devuelven `0` en caso de éxito y códigos diferentes de cero cuando detectan errores operativos. Todas las rutas y archivos se resuelven desde la raíz del repositorio.

## Prerrequisitos
- `oc` autenticado contra el clúster objetivo (`oc login`).
- Utilidades locales: `diff`, `jq`, `curl` y `git`.
- Python 3.9 o superior con capacidad para instalar dependencias vía `pip` en modo usuario.

## Grupos de comandos

### 1. `cluster`
Gestiona la instalación declarativa y el estado de los entornos definidos en `environments/`.

| Comando | Descripción | Opciones clave |
| --- | --- | --- |
| `deploy` | Aplica los manifiestos base y del entorno indicado. | `--env <nombre>` (predeterminado: `sandbox`). |
| `remove` | Elimina los recursos declarados sin fallar si ya no existen. | — |
| `reset` | Borra recursos y namespaces del entorno para reinstalar desde cero. | `--env <nombre>`. |
| `validate` | Verifica namespaces, deployments, pods y diferencias con `oc diff`. | `--env <nombre>`. |
| `watch` | Ejecuta validaciones continuas cada 30 s y opcionalmente imprime inventarios detallados. | `--env`, `--minutes`, `--detail`. |

### 2. `pipelines`
Orquesta la instalación GitOps de OpenShift Pipelines.

| Comando | Descripción |
| --- | --- |
| `install` | Aplica la `Subscription` y el `TektonConfig` declarados, esperando a que `TektonConfig/config` quede en estado `Ready`.
| `cleanup` | Elimina la suscripción, el `TektonConfig` y solicita borrar el proyecto `openshift-pipelines`.

### 3. `scenarios`
Empaqueta flujos preconfigurados para acelerar demos o pruebas.

| Comando | Descripción | Opciones |
| --- | --- | --- |
| `deploy-default` | Instala el entorno `sandbox` y distribuye simuladores de carga aleatorios. | `--simulators`, `--seed`. |
| `cleanup-default` | Retira los simuladores y limpia el entorno `sandbox`. | — |

### 4. `simulators`
Genera y mantiene despliegues sintéticos que ejercitan la arquitectura viva.

| Comando | Descripción | Opciones |
| --- | --- | --- |
| `generate` | Produce manifiestos y Deployments etiquetados como simuladores por componente. | `--count`, `--targets`, `--seed`, `--behavior`, `--branch`. |
| `list` | Consulta el clúster para mostrar comportamiento y namespace de cada simulador. | — |
| `cleanup` | Elimina Deployments simulados y limpia `load-simulators.yaml` y kustomizations. | `--targets`, `--branch`, `--delete-branch`. |

### 5. `metadata`
Mantiene la trazabilidad y consistencia de anotaciones.

| Comando | Descripción |
| --- | --- |
| `lint-yaml` | Valida sintaxis YAML (excluye `kustomization.yaml`). |
| `report` | Genera reporte Markdown con dominios, relaciones y archivos fuente. |
| `audit` | Comprueba coherencia de `calls`/`invoked_by` y cobertura de NetworkPolicies. |
| `network-policies` | Deriva manifestaciones de NetworkPolicy a partir de anotaciones `architecture.*`. |

### 6. `components`
Automatiza la creación de instancias a partir del inventario `component_inventory.yaml`.

| Comando | Descripción |
| --- | --- |
| `create` | Genera Deployment, Service opcional y actualiza el `kustomization.yaml` del dominio. |

### 7. `console`
Sincroniza el CLI con la consola web Architects Visualization.

| Comando | Descripción |
| --- | --- |
| `sync` | Emite el ConfigMap `console-commands-configmap.yaml` con nombre, resumen y uso de cada comando. |

## Escenarios de uso

### Instalación completa en `sandbox`
```
./arkit8s.py cluster deploy --env sandbox
./arkit8s.py cluster validate --env sandbox
./arkit8s.py cluster watch --env sandbox --minutes 5
```

### ¿Cómo instalo la arquitectura por defecto?

La arquitectura por defecto corresponde al entorno `sandbox`. Para instalarla desde cero:

1. Asegúrate de haber ejecutado `oc login` contra el clúster de destino y de tener permisos de
   administrador del proyecto.
2. Desde la raíz del repositorio, ejecuta `python3 arkit8s.py cluster deploy --env sandbox`. El
   comando aplica los manifiestos base y el overlay `sandbox` ubicados en `environments/`.
3. Cuando el despliegue termine, valida el estado con `python3 arkit8s.py cluster validate --env
   sandbox` o monitorea los componentes con `python3 arkit8s.py cluster watch --env sandbox`.

Si necesitas reinstalarla, primero puedes limpiar recursos con `python3 arkit8s.py cluster reset
--env sandbox` y volver a ejecutar el despliegue.

### Generación de simuladores deterministas
```
./arkit8s.py simulators generate --behavior notready --seed 42
./arkit8s.py simulators list
```

### Limpieza total
```
./arkit8s.py simulators cleanup --delete-branch
./arkit8s.py cluster reset --env sandbox
```

## Archivos generados
- `tmp/command-output.out`: Resumen de Routes y productos expuestos tras `cluster deploy`.
- `architecture/support-domain/architects-visualization/console-commands-configmap.yaml`: ConfigMap consumido por la consola web tras `console sync`.
- `load-simulators.yaml`: Manifiestos generados en cada componente de negocio por `simulators generate`.

## Códigos de salida
- `0`: operación exitosa.
- `>0`: error en la operación (permisos, diferencias detectadas, validaciones fallidas).

## Véase también
- [`README.md`](../README.md) — guía introductoria y flujo paso a paso.
- `architecture/APPLIED_ARCHITECTURE_RESUME.md` — resumen de componentes desplegados.
