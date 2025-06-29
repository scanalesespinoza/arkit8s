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
├── ui/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── api/
├── integration/
├── data-access/
├── auth/
└── base/
```


## 🔁 Shared Components

Reusable building blocks shared across domains. Components like `shared-components/access-control/keycloak` provide ready-to-use manifests that can be applied directly.

### Example usage

Apply all manifests recursively from the repository root:

```bash
oc apply -f . --recursive
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
oc apply -f bootstrap/
```

### 🚀 Despliegue completo

```bash
oc apply -f . --recursive
```

### 🚀 Instalación rápida

```bash
./gitops-install.sh  # para Linux/macOS
./gitops-install.ps1 # para PowerShell
```

### 🧹 Desinstalación rápida

```bash
./gitops-uninstall.sh  # para Linux/macOS
./gitops-uninstall.ps1 # para PowerShell
```

### 👀 Observación continua

```bash
./watch-cluster.sh      # por defecto 5 minutos
./watch-cluster.ps1 10  # observar por 10 minutos
```

### 🧹 Limpiar entorno (opcional)

```bash
oc delete -f . --recursive
oc delete -f bootstrap/
```

### ✅ Validación del entorno

```bash
./validate-cluster.sh  # para Linux/macOS
./validate-cluster.ps1 # para PowerShell
```
