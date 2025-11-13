# Flujo GitOps para promover cambios de 3scale a *staging* y *production*

Este flujo describe cómo administrar la configuración de **Red Hat 3scale API Management** usando GitOps para promover cambios desde un repositorio Git hacia los entornos *staging* y *production*. El objetivo es que cuando un desarrollador modifique una API/backend, el cambio se propague de forma consistente a los productos y backends correspondientes respetando los principios GitOps.

## 1. Estructura del repositorio

Organiza los manifiestos declarativos de 3scale en un repositorio dedicado con la siguiente convención:

```
3scale-gitops/
├── bootstrap/                 # Operadores y secretos compartidos.
├── shared/                    # Recursos comunes (MappingRules, ActiveDocs).
├── environments/
│   ├── staging/
│   │   ├── kustomization.yaml
│   │   ├── backends/
│   │   │   └── <backend-name>.yaml
│   │   └── products/
│   │       └── <product-name>.yaml
│   └── production/
│       └── ...
└── pipelines/                 # Pipelines Tekton/GitHub Actions.
```

- Usa `kustomize` o `helm` para derivar overlays por entorno.
- Versiona las credenciales de 3scale como `Secret` cifrado con [SealedSecrets](https://github.com/bitnami-labs/sealed-secrets) o [SOPS](https://github.com/mozilla/sops).

## 2. Bootstrap inicial

1. Declara en `bootstrap/` los recursos necesarios para instalar el **3scale Operator** y crear los tenants requerido.
2. Aplica `bootstrap/` una sola vez utilizando un servicio de automatización con credenciales mínimas (por ejemplo, `oc apply -k bootstrap/`).
3. Configura Argo CD o Flux para reconciliar los overlays `environments/staging` y `environments/production`.

## 3. Declarar productos y backends

### Backends

Cada backend se modela mediante el CRD `Backend`:

```yaml
apiVersion: capabilities.3scale.net/v1beta1
kind: Backend
metadata:
  name: payments-backend
  annotations:
    gitops.3scale.net/owner: payments
spec:
  systemName: payments
  privateBaseURL: https://payments.internal.svc
  providerAccountRef:
    name: tenant-sandbox
  mappingRules:
    - httpMethod: GET
      pattern: "/transactions"
      delta: 1
      metricMethodRef: hits
```

### Productos

Los productos consumen backends declarados y exponen Application Plans y ActiveDocs:

```yaml
apiVersion: capabilities.3scale.net/v1beta1
kind: Product
metadata:
  name: payments-product
spec:
  systemName: payments
  providerAccountRef:
    name: tenant-sandbox
  deployment:
    apicastSelfManaged: true
  backendUsages:
    payments:
      backend: payments-backend
  applicationPlans:
    default:
      name: Default
      published: true
      limits:
        - metricMethodRef: hits
          period: minute
          value: 100
```

> **Tip:** centraliza métricas personalizadas, políticas de Apicast y configuraciones de OpenID Connect como ConfigMaps referenciados por tus CRDs.

## 4. Automatizar el flujo de promoción

1. **Ramas y Pull Requests**: Los desarrolladores editan los manifiestos (por ejemplo `environments/staging/backends/payments-backend.yaml`) y abren un PR. Las revisiones de código validan la intención de negocio.
2. **Validaciones automáticas**:
   - `kustomize build environments/staging` para asegurar que los manifests renderizan correctamente.
   - `tkn` o `oc kustomize` para validar sintaxis de CRDs.
   - Tests específicos usando [`3scale_toolbox`](https://github.com/3scale/3scale_toolbox) en modo `dry-run` (por ejemplo, `3scale toolbox import openapi --publish false`).
3. **Pipeline de integración** (Tekton, GitHub Actions o GitLab CI):
   - Ejecuta linters (`yamllint`, `kubeconform`).
   - Usa el `3scale toolbox` con `--target <tenant>` para prevalidar credenciales.
   - Publica artefactos (por ejemplo, OpenAPI validado).
4. **Sincronización automática**: al fusionar el PR, Argo CD detecta el commit y aplica los cambios en el entorno `staging`.
5. **Publicar configuración en APIcast**: tras cada sincronización, declara un objeto `Promotion` para forzar que 3scale genere y
   publique la `proxy-config` hacia el Gateway correspondiente (`staging` o `production`). El CR debe referenciar al `Product`
   actualizado:

   ```yaml
   apiVersion: capabilities.3scale.net/v1beta1
   kind: Promotion
   metadata:
     name: payments-staging-promotion
   spec:
     productCR:
       name: payments-product
     environment: staging
   ```

   Argo CD/Flux tratarán el `Promotion` como cualquier otro recurso; cuando detecten cambios del `Product`, se generará un `Promotion`
   nuevo (o se actualizará el existente) y 3scale propagará la configuración de APIcast. Repite el mismo patrón para `production`.

### 4.1. Generar `Promotion` automáticamente cuando cambie un `Product` o `Backend`

Para evitar depender de que alguien actualice manualmente el manifiesto del `Promotion`, puedes automatizarlo en tu pipeline de
integración continua. La idea es detectar qué productos/backends cambiaron en el commit y actualizar un archivo declarativo por
entorno con un *trigger* único que fuerce al operador de 3scale a crear un nuevo `Promotion`.

1. Mantén los `Promotion` en `environments/<env>/promotions/` dentro del mismo repositorio GitOps y añádelos al `kustomization.yaml`:

   ```yaml
   resources:
     - ../base
     - promotions/
   ```

2. Agrega a cada `Promotion` una anotación que puedas sobrescribir automáticamente (por ejemplo, el SHA del commit):

   ```yaml
   apiVersion: capabilities.3scale.net/v1beta1
   kind: Promotion
   metadata:
     name: payments-staging-promotion
     annotations:
       gitops.3scale.net/trigger: "initial"
   spec:
     productCR:
       name: payments-product
     environment: staging
   ```

3. En la pipeline CI (Tekton/GitHub Actions), identifica qué `Product` o `Backend` cambió. Si un backend cambió, toma los
   `Product` que lo referencian (puedes mantener un mapa en un archivo `products-backends.yaml` o consultar el repo con `yq`). Por
   cada producto impactado, actualiza la anotación `gitops.3scale.net/trigger` con el SHA del commit:

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   SHA="$(git rev-parse HEAD)"
   CHANGED_PRODUCTS=$(git diff --name-only origin/main...HEAD \
     | grep 'environments/staging/products/' \
     | xargs -r -n1 basename \
     | sed 's/\.yaml$//')

   for product in ${CHANGED_PRODUCTS}; do
     for env in staging production; do
       yq -i \
         '.metadata.annotations["gitops.3scale.net/trigger"] = "'"${SHA}"'"' \
         "environments/${env}/promotions/${product}-${env}-promotion.yaml"
     done
   done
   ```

   Al modificar la anotación, Argo CD/Flux verán un cambio real en el manifiesto y recrearán el `Promotion`. El operador de 3scale
   generará la `proxy-config` actualizada automáticamente en APIcast para cada entorno.

4. Si necesitas cubrir dependencias `Product` → `Backend`, puedes complementar el script con una consulta `yq`:

   ```bash
   backend=$(basename "${changed_backend}" .yaml)
   affected=$(yq '.spec.backendUsages | to_entries[] | select(.value.backend == "'"${backend}"'") | .key' \
     environments/staging/products/*.yaml)
   ```

   Con ello, marcas los `Promotion` de los productos impactados aunque sólo haya cambiado el backend.

Esta estrategia mantiene el flujo 100 % GitOps: todo el contenido sigue versionado en Git, la pipeline sólo actualiza anotaciones
determinísticas y Argo CD/Flux se encargan de aplicar los nuevos `Promotion` sin pasos manuales.
6. **Promoción a producción**:
   - Usa *GitOps Environments* o *ApplicationSet Wavefront* para encadenar promociones. Ejemplo: crea una etiqueta `staging-ready` cuando Argo CD esté en `Synced` y la pipeline dispare un PR automático contra `environments/production` que copie los cambios aprobados.
   - Alternativamente, usa `git cherry-pick` desde la rama `staging` hacia `production` con un pipeline manual que abre el PR y exige aprobación del equipo de operaciones. Después del merge, aplica el `Promotion` apuntando al entorno `production` para que la `proxy-config` quede disponible.

## 5. Gestión de credenciales y secretos

- Usa `ExternalSecret` o `Vault` para inyectar tokens de 3scale (`THREESCALE_ACCESS_TOKEN`).
- Configura el controlador de secretos para que Argo CD/Flux sólo aplique el `ExternalSecret` y no el `Secret` plano.
- Al promover a producción, actualiza las referencias `providerAccountRef` en los overlays de producción para utilizar el tenant/credentials correctos.

## 6. Auditoría y observabilidad

- Habilita [Argo CD Application Controller notifications](https://argo-cd.readthedocs.io/en/stable/operator-manual/notifications/) o Webhooks personalizados para alertar cuando un sync de staging/production falle.
- Usa etiquetas y anotaciones (`gitops.3scale.net/owner`, `gitops.3scale.net/ticket`) para trazar qué equipo hizo cada cambio.
- Integra `3scale toolbox` en modo lectura en dashboards (Grafana, Kibana) para mostrar la versión del manifiesto aplicada en cada producto.

## 7. Ejemplo de pipeline Tekton simplificada

```yaml
apiVersion: tekton.dev/v1beta1
kind: Pipeline
metadata:
  name: promote-3scale
spec:
  params:
    - name: git-revision
    - name: environment
  tasks:
    - name: fetch-repo
      taskRef:
        name: git-clone
        kind: ClusterTask
      params:
        - name: url
          value: https://git.example.com/platform/3scale-gitops.git
        - name: revision
          value: "$(params.git-revision)"
    - name: validate
      runAfter: [fetch-repo]
      taskSpec:
        steps:
          - name: kustomize
            image: bitnami/kubectl
            script: |
              kustomize build environments/$(params.environment)
          - name: toolbox-dry-run
            image: quay.io/3scale/toolbox:master
            script: |
              3scale toolbox import openapi openapi/payment.yaml \
                --target https://$(params.environment).3scale.net \
                --provider-key $(THREESCALE_ACCESS_TOKEN) \
                --publish false
    - name: promote-apicast
      runAfter: [validate]
      taskSpec:
        steps:
          - name: apply-promotion
            image: bitnami/kubectl
            script: |
              cat <<'EOF' | kubectl apply -f -
              apiVersion: capabilities.3scale.net/v1beta1
              kind: Promotion
              metadata:
                name: payments-$(params.environment)-promotion
              spec:
                productCR:
                  name: payments-product
                environment: $(params.environment)
              EOF
    - name: open-pr-production
      runAfter: [promote-apicast]
      when:
        - input: "$(params.environment)"
          operator: In
          values: [staging]
      taskRef:
        name: create-pr
```

La pipeline se desencadena automáticamente desde Webhooks de Git. Cuando el entorno `staging` se sincroniza sin errores, un pipeline secundario genera un PR hacia `production` reutilizando los mismos manifiestos.

## 8. Operación diaria

1. Desarrollador modifica OpenAPI/Backend → abre PR a `main`.
2. CI valida sintaxis, toolbox y abre vista previa en *staging*.
3. Argo CD sincroniza `staging`, aplica el `Promotion` y APIcast expone la nueva `proxy-config`.
4. Pipeline promueve cambios a `production` mediante PR automático.
5. Equipo de operaciones aprueba/merge → Argo CD aplica en producción y publica la `proxy-config` final con un `Promotion`.

Este enfoque asegura trazabilidad completa, revisiones obligatorias y sincronización declarativa de 3scale con tus entornos gestionados.
