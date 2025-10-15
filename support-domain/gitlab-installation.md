# Instalación de GitLab con arkit8s

Esta guía describe cómo desplegar **GitLab Community Edition** empleando el flujo GitOps incluido en arkit8s. Toda la configuración vive en el repositorio y se aplica mediante el CLI `arkit8s.py`, evitando configuraciones manuales en el clúster.

## Arquitectura y manifiestos relevantes

Los recursos de GitLab se declaran bajo `architecture/shared-components/gitlab-ce/`:

- `statefulset.yaml` y `service.yaml`: definen el pod Omnibus y la exposición interna.
- `route.yaml`: publica la instancia mediante una Route de OpenShift.
- `configmap-omnibus.yaml`: plantilla de `gitlab.rb` donde se fijan `external_url`, almacenamiento y ajustes adicionales.
- `secret-root-credentials.yaml`: credenciales iniciales del usuario `root`.

Las personalizaciones deben realizarse editando estos manifiestos y versionándolos en Git. Una vez fusionados, cualquier clúster sincronizado con el repositorio aplicará los mismos cambios.

## Prerrequisitos

1. Un clúster OpenShift (CRC, ROSA o equivalente) con un `StorageClass` que aprovisione volúmenes `ReadWriteOnce` de al menos 20 GiB.
2. Herramientas locales instaladas:
   - `oc` autenticado contra el clúster objetivo (`oc login ...`).
   - Python 3.10+ para ejecutar `arkit8s.py` (solo depende de la biblioteca estándar).
3. El repositorio `arkit8s` clonado y actualizado (`git pull`).

## Configuración previa

1. **URL pública**: actualiza `external_url` y `nginx['listen_port']` en `architecture/shared-components/gitlab-ce/configmap-omnibus.yaml` para reflejar el dominio que expondrá GitLab.
2. **Credenciales**: reemplaza `ChangeMe123!` y el correo por valores definitivos en `architecture/shared-components/gitlab-ce/secret-root-credentials.yaml`. Codifica la contraseña en Base64 si modificas `data.password`. Alternativamente, usa `stringData.password` para ingresar texto plano.
3. (Opcional) ajusta parámetros extra de Omnibus (SMTP, registro de contenedores, TLS) dentro del mismo ConfigMap siguiendo la sintaxis de `gitlab.rb`.

Ejecuta `./arkit8s.py validate-yaml` antes de continuar para asegurarte de que los cambios cumplen con la sintaxis declarativa.

## Despliegue mediante GitOps

1. Autentícate en el clúster: `oc login https://api.<cluster>:6443 -u <usuario>`.
2. Aplica la arquitectura declarativa en el entorno deseado. Por ejemplo, para `sandbox`:

   ```bash
   ./arkit8s.py install --env sandbox
   ```

   El comando aplica primero los manifiestos comunes (`architecture/bootstrap/`) y luego el overlay `environments/sandbox`, que incluye los recursos de `shared-components/gitlab-ce`.
3. Supervisa el despliegue con:

   ```bash
   oc get pods -n shared-components
   oc get route gitlab-ce -n shared-components -o jsonpath='{.spec.host}\n'
   ```

   Espera a que el pod `gitlab-ce-0` alcance el estado `Running` y utiliza la URL emitida por la Route para acceder a la interfaz web.

## Operaciones posteriores

- **Validación continua**: ejecuta `./arkit8s.py validate-cluster --env sandbox` para corroborar que el estado del clúster coincide con los manifiestos versionados.
- **Actualizaciones**: cualquier modificación en los manifiestos (por ejemplo, cambiar el `external_url` o habilitar características de Omnibus) se propaga volviendo a ejecutar `./arkit8s.py install --env <entorno>`.
- **Rollback o limpieza**: si necesitas retirar GitLab, edita los manifiestos (por ejemplo, comentando la entrada en `architecture/shared-components/kustomization.yaml`) y vuelve a aplicar `install`. Para eliminar todos los recursos de la arquitectura ejecuta `./arkit8s.py uninstall`.

Siguiendo este flujo garantizas instalaciones reproducibles de GitLab bajo la arquitectura y los procesos GitOps definidos por arkit8s.
