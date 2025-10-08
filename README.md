# RHBK on CRC

Este repositorio despliega Red Hat Build of Keycloak sobre OpenShift Local (CRC) usando Kustomize y aporta un conjunto de utilidades operativas agrupadas en el CLI `arkit8s.py`.

## Requisitos generales

- CRC u otro clúster OpenShift en ejecución y accesible.
- Autenticarse con `oc login` contra el clúster objetivo.
- Contar con `diffutils`, `jq` y `curl` en el `PATH` para las tareas auxiliares de validación y monitoreo.
- Python 3.9+ para ejecutar `arkit8s.py`.

## Instalación rápida (DEV/CRC)

```bash
make crc-dev
```

## Comandos útiles de Makefile

- `make wait` – espera a que Keycloak esté listo.
- `make admin` – muestra las credenciales iniciales.
- `make open` – imprime la URL de acceso.

## Desinstalación completa

```bash
make destroy
```

## Notas para entornos productivos

Para producción usa el overlay `shared-components/keycloak/overlays/prod`, una base de datos externa y configura TLS y Routes reencrypt/passthrough.

## Uso del CLI `arkit8s`

<!-- BEGIN ARKIT8S HELP -->
El script `arkit8s.py` centraliza las tareas operativas de la plataforma. Todos los comandos deben ejecutarse desde la raíz del repositorio.

### Prerrequisitos del CLI

1. Ejecuta `oc login` contra el clúster de destino con un usuario con permisos para crear namespaces y aplicar manifiestos.
2. Verifica que `diff`, `jq` y `curl` estén disponibles; se utilizan para validaciones y recopilación de métricas.
3. Si trabajas con varios entornos, revisa el directorio `environments/` y selecciona el overlay adecuado (por defecto `sandbox`).

### Flujo sugerido

1. **Instala** los manifiestos del entorno: `./arkit8s.py install --env sandbox`.
2. **Valida** que el clúster quedó en sincronía: `./arkit8s.py validate-cluster --env sandbox`.
3. **Monitorea** durante unos minutos para detectar desincronizaciones: `./arkit8s.py watch --env sandbox --minutes 5`.
4. **Genera reportes** o valida metadatos según sea necesario.

### Subcomandos disponibles

> Todos los subcomandos aceptan `--help` para mostrar su resumen puntual.

- `install [--env <nombre>]` – aplica los manifiestos base (`architecture/bootstrap`) y los del entorno indicado en `environments/`, verificando que existan los namespaces esperados y las ServiceAccounts que habilitan componentes como Sentik.
- `uninstall` – elimina los recursos definidos en `architecture/` (incluyendo bootstrap). No falla si los recursos ya no existen.
- `cleanup [--env <nombre>]` – borra todos los recursos del entorno indicado, incluidos los namespaces creados por `bootstrap`, dejando el clúster listo para una instalación desde cero.
- `validate-cluster [--env <nombre>]` – revisa namespaces, deployments, pods y sincronización (`oc diff`) para asegurar que el estado del clúster coincide con los manifiestos.
- `watch [--env <nombre>] [--minutes <n>] [--detail <default|detailed|all>]` – ejecuta validaciones continuas cada 30 segundos durante el tiempo indicado. Con `--detail` distinto de `default` imprime el inventario de recursos monitoreados.
- `validate-yaml` – recorre el repositorio y verifica que todos los YAML (excepto `kustomization.yaml`) sean sintácticamente válidos.
- `report` – genera un reporte Markdown con trazabilidad de componentes y relaciones usando las anotaciones `architecture.*`.
- `validate-metadata` – comprueba coherencia entre los campos `calls`/`invoked_by` y que las NetworkPolicies permitan el tráfico declarado.
- `generate-network-policies` – produce manifiestos de NetworkPolicy derivados de las anotaciones de dependencias (útil para revisiones o generación automatizada).
- `generate-load-simulators [--count <n>] [--targets <componentes>] [--seed <n>]` – crea Deployments sintéticos con comportamientos aleatorios (`ok`, `notready`, `restart`) tomando como referencia el repositorio [`quarkus-txt-report-frontend`](https://github.com/scanalesespinoza/quarkus-txt-report-frontend). Útil para ejercitar dominios de negocio y validar el flujo de reportes.
- `list-load-simulators` – consulta en el clúster todos los Deployments etiquetados como simuladores (`arkit8s.simulator=true`) e imprime el namespace, nombre y comportamiento (`BEHAVIOR`) asignado a cada uno.
- `cleanup-load-simulators [--branch <nombre>] [--targets <componentes>]` – elimina los simuladores del clúster, borra los manifiestos `load-simulators.yaml` generados por el comando y retira su referencia de los `kustomization.yaml`.  Después de ejecutar la limpieza, cambia a tu rama principal (`git switch main`) y elimina la rama temporal (`git branch -D <nombre>`).
- `create-component --type <tipo> --domain <business|support|shared> --branch <rama>` – crea una instancia de componente a partir del inventario (`component_inventory.yaml`), generando Deployment/Service/Kustomization y actualizando el `kustomization.yaml` del dominio.

### Ejemplo práctico: instalar **Sentik**

1. **Configura credenciales**: edita `architecture/support-domain/sentik/secret.yaml` para colocar la URL real del webhook de Microsoft Teams (`stringData.url`).
2. **Ajusta la URL del frontend** si corresponde: en `architecture/support-domain/sentik/cronjob.yaml` o mediante variables de entorno modifica el valor de `FRONTEND_URL` para apuntar al servicio que consumirá los reportes (por defecto `http://sentik:8080`).
3. **Aplica el entorno** deseado: `./arkit8s.py install --env sandbox`. Esto creará el namespace `support-domain`, desplegará el Deployment, Service, CronJob y ConfigMap asociados a Sentik.
4. **Verifica el estado**: 
   - `./arkit8s.py validate-cluster --env sandbox` para asegurar sincronización.
   - `oc get pods -n support-domain` para confirmar que el Deployment `sentik` está `Running`.
   - `oc get cronjob -n support-domain sentik-send-not-ready` para revisar el agendamiento.
5. **Monitorea ejecuciones**: usa `./arkit8s.py watch --env sandbox --minutes 10 --detail detailed` para observar reinicios o fallas en los pods disparados por el CronJob.

### Buenas prácticas y solución de problemas

- Ejecuta `./arkit8s.py validate-yaml` antes de aplicar cambios para detectar errores de formato.
- Usa `./arkit8s.py validate-metadata` después de editar anotaciones de arquitectura para mantener la trazabilidad consistente.
- Si necesitas revisar o compartir el estado de la arquitectura, ejecuta `./arkit8s.py report > reporte.md` y distribuye el archivo generado.
- Ante diferencias entre manifiestos y clúster, vuelve a ejecutar `install` o revisa `oc diff -k environments/<env>` para entender los cambios pendientes.
<!-- END ARKIT8S HELP -->
