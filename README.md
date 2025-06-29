# arkit8s – Living Architecture for Kubernetes

**arkit8s** (pronounced "architects") is a living, executable architecture blueprint for Kubernetes and OpenShift environments. It replaces static diagrams with declarative, observable, and deployable definitions managed through GitOps.

## 🎯 Purpose

Architectural designs often become outdated and disconnected from what is actually deployed. `arkit8s` proposes a Git-native approach to:

- Define architecture using Kubernetes manifests organized by layers and domains
- Deploy mock or placeholder components to instantiate the architecture from day zero
- Describe dependencies and relationships via metadata and environment variables
- Observe and understand system behavior and architecture in real environments

## 🧱 Core Layers

This project models an architecture through the following logical layers:

- `ui/`: Access layer (e.g., frontends, portals)
- `api/`: Backend APIs and business logic
- `integration/`: Orchestration, workflows, event bridges
- `data-access/`: Persistence and data services (e.g., databases, cache)
- `auth/`: Authentication and authorization services

Each layer is represented by:
- A dedicated folder with Kubernetes manifests
- A namespace that scopes its resources
- Metadata to indicate dependencies and business context

## 🔧 Tech Stack

- **Kubernetes / OpenShift**
- **Kustomize** for environment-specific overlays
- **GitOps** tools like ArgoCD or Flux
- Declarative metadata and environment variable conventions

## 📦 Structure Example

```
arkit8s/
├── architecture/
│   ├── bootstrap/
│   ├── business-domain/
│   ├── shared-components/
│   └── support-domain/
└── utilities/
    ├── gitops-install.sh
    └── ...
```


## 🔁 Shared Components

Reusable building blocks shared across domains. Components like `shared-components/access-control/keycloak` provide ready-to-use manifests that can be applied directly.

### Example usage

Apply all manifests recursively from the `architecture/` directory:

```bash
oc apply -f architecture/ --recursive
```

## 📌 Example Annotation and Dependency

```yaml
metadata:
  name: auth-service
  namespace: auth
  annotations:
    business.domain: "identity"
    depends.incluster: "api-user-svc, integration-token-svc"
    depends.outcluster: "https://auth0.example.com"
spec:
  containers:
    - name: mock-auth
      image: mockserver/mockserver
      env:
        - name: API_USER_URL
          value: "http://api-user-svc:8080"
```

## 🚀 Vision

This project aims to:
- Make architecture visible from Git
- Validate service readiness via dependency metadata
- Allow deploy-by-design with real or mock components
- Enable onboarding and evolution of cloud-native platforms with clear boundaries

---

> 🗣️ Pronounced like "architects" — because architecture should be versioned, validated, and visible.

## 💻 Manual GitOps

Use the helper scripts below to deploy or reset the full stack without a GitOps operator.

### 🧱 Bootstrap (crear namespaces)

```bash
oc apply -f architecture/bootstrap/
```

### 🚀 Despliegue completo

```bash
oc apply -f architecture/ --recursive
```

### 🚀 Instalación rápida

```bash
./utilities/gitops-install.sh  # para Linux/macOS
./utilities/gitops-install.ps1 # para PowerShell
```

### 🧹 Desinstalación rápida

```bash
./utilities/gitops-uninstall.sh  # para Linux/macOS
./utilities/gitops-uninstall.ps1 # para PowerShell
```

### 👀 Observación continua

```bash
./utilities/watch-cluster.sh                # por defecto 5 minutos, detalle minimo
./utilities/watch-cluster.sh 10 detailed    # 10 minutos con detalle medio
./utilities/watch-cluster.ps1 10 all        # usar PowerShell con detalle maximo
```
En modo `detailed` o `all` se listan los namespaces, deployments, manifiestos de bootstrap
y se muestran los estados actuales de namespaces, deployments y pods en cada iteración.

### 🧹 Limpiar entorno (opcional)

```bash
oc delete -f architecture/ --recursive
oc delete -f architecture/bootstrap/
```

### ✅ Validación del entorno

```bash
./utilities/validate-cluster.sh  # para Linux/macOS
./utilities/validate-cluster.ps1 # para PowerShell
```
