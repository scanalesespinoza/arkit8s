# RHBK on CRC

Este repositorio despliega Red Hat Build of Keycloak sobre OpenShift Local (CRC) usando Kustomize y aporta un conjunto de utilidades operativas agrupadas en el CLI `arkit8s.py`.

Inspirados por el proyecto [Kubeland Desktop Client](https://github.com/scanalesespinoza/kubeland), evolucionamos la experiencia hacia una visualización web nativa llamada **Architects Visualization**. El plano de control se construye con Quarkus, Qute y compilaciones *native image* para ofrecer un panel ligero que sincroniza en tiempo real las capacidades del CLI con una consola web accesible desde OpenShift.

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

1. **Instala** los manifiestos del entorno: `./arkit8s.py cluster deploy --env sandbox`.
   Al finalizar se genera `tmp/command-output.out` con un resumen de las Routes detectadas.
   Consulta ese archivo para verificar rápidamente los puntos de entrada expuestos.
2. **Valida** que el clúster quedó en sincronía: `./arkit8s.py cluster validate --env sandbox`.
   El comando confirma que Deployments, StatefulSets (por ejemplo GitLab CE) y Routes críticas como Keycloak estén disponibles y accesibles antes de continuar.
3. **Monitorea** durante unos minutos: `./arkit8s.py cluster watch --env sandbox --minutes 5`.
4. **Genera reportes** o valida metadatos según sea necesario (`metadata report`, `metadata audit`).

### Instalar OpenShift Pipelines con GitOps

1. Ejecuta `./arkit8s.py pipelines install` para aplicar la suscripción del operador en `openshift-operators` y el `TektonConfig` declarado en `architecture/shared-components/openshift-pipelines`. El manifiesto usa el canal `latest` según la guía oficial de OpenShift Pipelines.
2. El comando espera hasta 10 minutos a que `TektonConfig/config` quede en condición `Ready`. Si necesitas monitorear el progreso, abre otra terminal y ejecuta `oc get tektonconfig.config -w`.
3. Una vez disponible, sincroniza tus pipelines declarativos en el repositorio GitOps correspondiente.
4. Para desinstalar, ejecuta `./arkit8s.py pipelines cleanup`. Este comando elimina la suscripción, borra el `TektonConfig` y solicita la eliminación del proyecto `openshift-pipelines` generado por el operador (se ignora si ya no existe).

### Estructura del CLI

`arkit8s` agrupa los comandos en espacios de nombres que facilitan descubrir sus parámetros. Todos aceptan `--help` para mostrar detalles adicionales.

#### Grupo `cluster`
- `deploy --env <nombre>` – aplica los manifiestos base (`architecture/bootstrap`) y los del entorno indicado en `environments/`, verificando que existan los namespaces esperados.
- `remove` – elimina los recursos definidos en `architecture/` (incluido bootstrap) sin fallar si ya no existen.
- `reset --env <nombre>` – borra todos los recursos del entorno indicado, incluidos los namespaces creados por bootstrap.
- `validate --env <nombre>` – revisa namespaces, deployments, StatefulSets, pods, componentes declarados en `architecture/` (incluidas sus Routes) y sincronización (`oc diff`) para asegurar que el estado del clúster coincide con los manifiestos y que los productos expuestos responden correctamente.
- `watch --env <nombre> [--minutes <n>] [--detail <default|detailed|all>]` – ejecuta validaciones continuas cada 30 segundos durante el tiempo indicado. Con `--detail` distinto de `default` imprime el inventario de recursos monitoreados.

#### Grupo `pipelines`
- `install` – aplica la suscripción del operador y el `TektonConfig` gestionados por GitOps en `architecture/shared-components/openshift-pipelines`.
- `cleanup` – elimina la suscripción y el `TektonConfig` gestionados por GitOps y borra el proyecto `openshift-pipelines` creado por el operador.

#### Grupo `scenarios`
- `deploy-default [--simulators <n>] [--seed <n>]` – despliega el entorno `sandbox` y genera simuladores de carga aleatorios etiquetados como parte del escenario por defecto.
- `cleanup-default` – elimina los simuladores del escenario por defecto y limpia por completo el entorno `sandbox`.

#### Grupo `simulators`
- `generate [--count <n>] [--targets <componentes>] [--seed <n>] [--behavior <dynamic|ok|notready|restart>]` – crea Deployments sintéticos que, por omisión, alternan aleatoriamente entre estados para simular incidentes realistas. Con `--behavior` puedes fijar un estado específico.
- `list` – consulta en el clúster los Deployments etiquetados como simuladores (`arkit8s.simulator=true`) e imprime el namespace, nombre y comportamiento (`BEHAVIOR`).
- `cleanup [--branch <nombre>] [--targets <componentes>] [--delete-branch]` – elimina los simuladores del clúster, borra los manifiestos `load-simulators.yaml` generados por el comando y retira su referencia de los `kustomization.yaml`.

#### Grupo `metadata`
- `lint-yaml` – recorre el repositorio y verifica que todos los YAML (excepto `kustomization.yaml`) sean sintácticamente válidos.
- `report` – genera un reporte Markdown con trazabilidad de componentes y relaciones usando las anotaciones `architecture.*`.
- `audit` – comprueba coherencia entre los campos `calls`/`invoked_by` y que las NetworkPolicies permitan el tráfico declarado.
- `network-policies` – produce manifiestos de NetworkPolicy derivados de las anotaciones de dependencias.

#### Grupo `components`
- `create <nombre> --type <tipo> --domain <business|support|shared> [opciones]` – crea una instancia de componente a partir del inventario (`component_inventory.yaml`), generando Deployment/Service/Kustomization y actualizando el `kustomization.yaml` del dominio.

#### Grupo `console`
- `sync` – sincroniza la metadata del CLI con la consola web de Architects Visualization generando el `ConfigMap` consumido por Quarkus/Qute.

### Asistente inteligente del CLI

Cuando ejecutas `python3 arkit8s.py` sin argumentos el CLI intenta responder preguntas libres
usando un modelo ligero entrenado con el contenido del repositorio. Para añadir nuevos
conocimientos documenta la respuesta deseada, ejecuta `python3 arkit8s.py assistant train` y
vuelve a formular la consulta.

Consulta [docs/assistant-inteligente.md](docs/assistant-inteligente.md) para recomendaciones
detalladas sobre cómo preparar fragmentos, cuándo conviene entrenar y por qué resulta más
ligero que depender de un modelo opensource genérico.

### Visualización Architects

1. Ejecuta `python arkit8s.py console sync` tras añadir o modificar comandos del CLI. Este paso genera `architecture/support-domain/architects-visualization/console-commands-configmap.yaml` con la descripción y el `usage` de cada comando.
2. Construye la nueva imagen Quarkus/Qute si deseas publicarla en tu propio registro: `mvn -pl support-domain/architects-console package -Dquarkus.container-image.build=true -Dquarkus.container-image.image=quay.io/arkit8s/architects-console:latest`.
3. Aplica los manifiestos (`./arkit8s.py cluster deploy --env sandbox`) para desplegar el `Deployment` que usa directamente la imagen `quay.io/arkit8s/architects-console:latest`, montando tanto la configuración Qute como los comandos generados sin necesidad de compilar en el clúster.
4. El manifiesto ya declara la `Route` `architects-visualization-support-domain.apps-crc.testing`, por lo que basta con ejecutar `./arkit8s.py cluster deploy --env sandbox` y consultar la URL registrada en `tmp/command-output.out`. Alternativamente, puedes hacer `oc port-forward svc/architects-visualization 8080` para una sesión temporal.
5. Utiliza la consola web para invocar acciones del CLI desde el navegador, manteniendo sincronía entre operaciones declarativas y observabilidad del plano de control.

#### Ejemplos de uso de simuladores de carga

- `./arkit8s.py simulators generate` – genera simuladores con comportamiento dinámico.
- `./arkit8s.py simulators generate --behavior notready` – todos los simuladores permanecen permanentemente en estado `notready`.
- `./arkit8s.py simulators generate --behavior ok` – los simuladores se mantienen estables y siempre listos.
- `./arkit8s.py simulators generate --behavior restart` – los simuladores reinician periódicamente tras 60 segundos.
- `./arkit8s.py scenarios deploy-default --simulators 15` – despliega el escenario por defecto con 15 simuladores distribuidos aleatoriamente.
- `./arkit8s.py scenarios cleanup-default` – limpia por completo el escenario por defecto junto al entorno `sandbox`.

### GitLab CE en OpenShift

Este repositorio incluye un despliegue de referencia de **GitLab Community Edition** para acelerar la provisión de herramientas DevSecOps sobre OpenShift Local (CRC) u otros clústeres OpenShift compatibles.

1. **Dependencias**: se declara un `StatefulSet` con tres `PersistentVolumeClaim` (configuración, datos y bitácoras). Asegúrate de que el clúster cuente con un *StorageClass* por omisión capaz de aprovisionar volúmenes `ReadWriteOnce` de al menos 20 GiB.
2. **Credenciales iniciales**: el `Secret` `gitlab-initial-admin` crea el usuario `root` con el correo `root@gitlab.local` y la contraseña `ChangeMe123!`. Personaliza estos valores antes de aplicar los manifiestos para evitar reutilizar credenciales por defecto (`kubectl edit secret/gitlab-initial-admin -n shared-components`).
3. **URL de acceso**: la `Route` expone la instancia vía `http://gitlab-ce-shared-components.apps-crc.testing`. Tras instalar, la URL queda registrada en `tmp/command-output.out`. Si tu dominio de aplicaciones difiere, actualiza `architecture/shared-components/gitlab-ce/configmap-omnibus.yaml` para ajustar la variable `external_url` y el `host` de la `Route`.
4. **Aplicación de manifiestos**: ejecuta `./arkit8s.py cluster deploy --env sandbox` (o el entorno de tu preferencia). El `StatefulSet` tardará varios minutos en descargar la imagen `gitlab/gitlab-ce:16.9.1-ce.0` y configurar los servicios internos de PostgreSQL y Redis incluidos en la distribución Omnibus.
5. **Verificación**: consulta el estado con `oc get pods -n shared-components` y espera a que el pod `gitlab-ce-0` se encuentre en `Running`. Recupera la URL desde la `Route` (`oc get route gitlab-ce -n shared-components -o jsonpath='{.spec.host}'`) y accede con las credenciales iniciales.
6. **Personalización avanzada**: modifica `architecture/shared-components/gitlab-ce/configmap-omnibus.yaml` para añadir parámetros de `gitlab.rb` (por ejemplo SMTP, repositorio de contenedores o certificados TLS). Tras editar el ConfigMap, ejecuta `./arkit8s.py cluster deploy --env <entorno>` para reconciliar los cambios.

### Ejemplo práctico: instalar **Sentik**

1. **Configura credenciales**: edita `architecture/support-domain/sentik/secret.yaml` para colocar la URL real del webhook de Microsoft Teams (`stringData.url`).
2. **Ajusta la URL del frontend** si corresponde: en `architecture/support-domain/sentik/cronjob.yaml` o mediante variables de entorno modifica el valor de `FRONTEND_URL` para apuntar al servicio que consumirá los reportes (por defecto `http://sentik:8080`).
3. **Aplica el entorno** deseado: `./arkit8s.py cluster deploy --env sandbox`. Esto creará el namespace `support-domain`, desplegará el Deployment, Service, CronJob y ConfigMap asociados a Sentik.
4. **Verifica el estado**:
   - `./arkit8s.py cluster validate --env sandbox` para asegurar sincronización.
   - `oc get pods -n support-domain` para confirmar que el Deployment `sentik` está `Running`.
   - `oc get cronjob -n support-domain sentik-send-not-ready` para revisar el agendamiento.
5. **Monitorea ejecuciones**: usa `./arkit8s.py cluster watch --env sandbox --minutes 10 --detail detailed` para observar reinicios o fallas en los pods disparados por el CronJob.

### Buenas prácticas y solución de problemas

- Ejecuta `./arkit8s.py metadata lint-yaml` antes de aplicar cambios para detectar errores de formato.
- Usa `./arkit8s.py metadata audit` después de editar anotaciones de arquitectura para mantener la trazabilidad consistente.
- Si necesitas revisar o compartir el estado de la arquitectura, ejecuta `./arkit8s.py metadata report > reporte.md` y distribuye el archivo generado.
- Ante diferencias entre manifiestos y clúster, vuelve a ejecutar `cluster deploy` o revisa `oc diff -k environments/<env>` para entender los cambios pendientes.
<!-- END ARKIT8S HELP -->
