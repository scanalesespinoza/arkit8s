# arkit8s – Living Architecture for Kubernetes

> ⚠️ Este archivo es editado automáticamente por el CLI arkit8s.py tras la creación de componentes. No edites manualmente las secciones de ejemplo.

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

### Example: Crear un componente con dependencias

```bash
./arkit8s.py create-component my-comp --type service --domain support \
    --depends-incluster api-user-svc,integration-token-svc \
    --depends-outcluster https://auth0.example.com \
    --branch component-instances
```

Esto generará un manifiesto con metadata curada como:

```yaml
metadata:
  name: my-comp
  annotations:
    architecture.domain: support
    architecture.function: microservice
    architecture.part_of: arkit8s
    depends.incluster: api-user-svc,integration-token-svc
    depends.outcluster: https://auth0.example.com
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

## 👩‍💻 Developer Experience Benefits

Living architecture closes the gap between business program design and actual implementation. By versioning manifests in Git, teams collaborate continuously from design through deployment. Declared dependencies and standardized layers enable early validation of business flows and help catch inconsistencies. Thanks to the provided scripts and CLI, deploying the solution across environments becomes straightforward, delivering value to end users faster.


## 💻 Manual GitOps

Use the helper scripts below to deploy or reset the full stack without a GitOps operator.

> ⚠️ **Warning**: make sure to run the commands with an account that has permissions to create namespaces and apply resources. The `developer` account usually lacks these privileges, so you may receive *Forbidden* errors. Log in with a privileged user (for example `oc login -u kubeadmin`) or request the necessary permissions.

### 🧱 Bootstrap (create namespaces)

```bash
oc apply -k architecture/bootstrap/
```

### 🚀 Full deployment

```bash
oc apply -k environments/sandbox
```

### 🚀 Quick installation

```bash
./utilities/gitops-install.sh            # uses 'sandbox' by default
./utilities/gitops-install.sh prod       # specify environment
./utilities/gitops-install.ps1           # for PowerShell, 'sandbox' by default
./utilities/gitops-install.ps1 prod
```

### 🧹 Quick uninstall

```bash
./utilities/gitops-uninstall.sh  # for Linux/macOS
./utilities/gitops-uninstall.ps1 # for PowerShell
```

### 👀 Continuous watch

```bash
./utilities/watch-cluster.sh                # defaults to 5 minutes in 'sandbox'
./utilities/watch-cluster.sh 10 detailed prod
./utilities/watch-cluster.ps1 10 all prod
```
In `detailed` or `all` mode the namespaces, deployments and bootstrap manifests are listed
and the current state of namespaces, deployments and pods is shown in each iteration.

### 🧹 Clean environment (optional)

```bash
oc delete -f architecture/ --recursive
oc delete -f architecture/bootstrap/
```

### ✅ Environment validation

```bash
./utilities/validate-cluster.sh  # for Linux/macOS
./utilities/validate-cluster.ps1 # for PowerShell
```

### 🔍 YAML manifest validation

```bash
./utilities/validate-yaml.sh
```
The script parses each file with **PyYAML** to detect syntax errors without requiring
`oc` or an available cluster. If the library is not installed it will be downloaded automatically.
In GitHub Actions the validation runs autonomously as well and does not depend on `oc login`.

### 📊 Architecture report

```bash
python3 utilities/generate-architecture-report.py
```
This command extracts the metadata from all manifests in `architecture/` and
prints a report summarizing components, their call flow and the traceability of each file.

### 🛡️ Generate NetworkPolicies

```bash
python3 utilities/generate-network-policies.py > networkpolicies.yaml
```
The script analyses the annotations of each component and generates network policies
that allow only the traffic declared in the metadata.

### 🛠️ `arkit8s` CLI

All the above utilities can now be executed through a single CLI written in Python
that works on both Linux and Windows:

```bash
# Install manifests to the default environment
./arkit8s.py install

# Uninstall manifests
./arkit8s.py uninstall

# Validate cluster state
./arkit8s.py validate-cluster --env sandbox

# Watch the cluster for 10 minutes with details
./arkit8s.py watch --minutes 10 --detail detailed

# Validate YAML syntax
./arkit8s.py validate-yaml

# Validate metadata coherence
./arkit8s.py validate-metadata

# Generate base NetworkPolicies
./arkit8s.py generate-network-policies > networkpolicies.yaml

# Generate architecture report
./arkit8s.py report

# Create a new component instance
./arkit8s.py create-component my-comp --type service --domain support \
    --branch component-instances
```

This command switches to the specified branch (creating it if needed) before
generating the manifests so that local changes stay separate from `main`.

On Windows you can invoke it with `python arkit8s.py <command>`. The project
keeps the scripts in `utilities/` as a reference, but using the CLI is recommended
for a simplified experience.

