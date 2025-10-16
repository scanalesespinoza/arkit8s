# Applied Architecture Resume

This document summarizes the current arkit8s deployment, the components delivered per domain, and the recommended entry points (URLs or CLI checks) for quick validation.

## Domain Overview

| Domain | Namespace | Purpose | Principal Entry Points |
| --- | --- | --- | --- |
| Business | `business-domain` | Hosts customer-facing UI, API façade, and verification services that orchestrate the business workflow. | Deployments `ui-app-instance`, `api-app-instance`; Services `company-identity-verification-app-instance`, `person-identity-verification-app-instance`. |
| Support | `support-domain` | Provides shared backend capabilities (data access, orchestration, notifications) plus operational tooling. | Route `architects-visualization-support-domain.apps-crc.testing`; Services `address-validator-app-instance`, `user-profile-app-instance`, `sentik`; CronJob `sentik-send-not-ready`. |
| Shared Components | `shared-components` (plus cluster-scoped namespaces) | Supplies platform-wide services such as access control, source control, and CI/CD. | Routes `gitlab-ce-shared-components.apps-crc.testing`, `keycloak-shared-components.apps-crc.testing`; Tekton `Subscription/TektonConfig`. |

## Business Domain (`business-domain`)

| Component | Workloads & Resources | Access / Quick Check | Notes |
| --- | --- | --- | --- |
| UI | Deployment `ui-app-instance`; simulator deployments `ui-availability-sim-1…3`. | `oc -n business-domain get deployment/ui-app-instance` | Invoked by end users and drives API calls.【F:architecture/business-domain/ui/deployment.yaml†L1-L27】【F:architecture/business-domain/ui/load-simulators.yaml†L1-L210】 |
| API | Deployment `api-app-instance`; simulator deployments `api-availability-sim-1…3`. | `oc -n business-domain get deployment/api-app-instance` | Receives UI traffic and fans out to support services (`data-access`, `orchestrator`, `access-control`).【F:architecture/business-domain/api/deployment.yaml†L1-L33】【F:architecture/business-domain/api/load-simulators.yaml†L1-L240】 |
| Company Identity Verification | Deployment & Service `company-identity-verification-app-instance`. | `oc -n business-domain get svc/company-identity-verification-app-instance` | Called by API to validate organizations; exposes port 80 → 8080 inside the cluster.【F:architecture/business-domain/company-management/identity-verification/deployment.yaml†L1-L30】【F:architecture/business-domain/company-management/identity-verification/service.yaml†L1-L18】 |
| Person Identity Verification | Deployment & Service `person-identity-verification-app-instance`. | `oc -n business-domain get svc/person-identity-verification-app-instance` | Mirrors the company flow for individual users, exposing port 80 → 8080.【F:architecture/business-domain/person-management/identity-verification/deployment.yaml†L1-L30】【F:architecture/business-domain/person-management/identity-verification/service.yaml†L1-L18】 |

## Support Domain (`support-domain`)

| Component | Workloads & Resources | Access / Quick Check | Notes |
| --- | --- | --- | --- |
| Data Access | Deployment `data-access-app-instance`. | `oc -n support-domain get deployment/data-access-app-instance` | Back-end adapter that the business API uses to reach external databases.【F:architecture/support-domain/data-access/deployment.yaml†L1-L30】 |
| Orchestrator | Deployment `orchestrator-app-instance`. | `oc -n support-domain get deployment/orchestrator-app-instance` | Handles cross-service workflows and delegates to notification services.【F:architecture/support-domain/orchestrator/deployment.yaml†L1-L30】 |
| Notification External Services | Deployment `notification-external-services-app-instance`. | `oc -n support-domain get deployment/notification-external-services-app-instance` | Sends email/third-party notifications on behalf of the orchestrator.【F:architecture/support-domain/notification-external-services/deployment.yaml†L1-L30】 |
| Address Validator | Deployment & Service `address-validator-app-instance`. | `oc -n support-domain get svc/address-validator-app-instance` | Validates addresses for the business API, exposing port 80 → 8080.【F:architecture/support-domain/address-validator/deployment.yaml†L1-L30】【F:architecture/support-domain/address-validator/service.yaml†L1-L18】 |
| User Profile | Deployment & Service `user-profile-app-instance`. | `oc -n support-domain get svc/user-profile-app-instance` | Maintains user data; responds on port 80 → 8080 inside the namespace.【F:architecture/support-domain/user-profile/deployment.yaml†L1-L30】【F:architecture/support-domain/user-profile/service.yaml†L1-L18】 |
| Architects Visualization | Deployment `architects-visualization`; Service `architects-visualization` on port 8080; Route `architects-visualization-support-domain.apps-crc.testing`. | `oc -n support-domain get route/architects-visualization` | Provides visual architecture console backed by ConfigMaps and CLI helpers.【F:architecture/support-domain/architects-visualization/deployment.yaml†L1-L40】【F:architecture/support-domain/architects-visualization/service.yaml†L1-L20】【F:architecture/support-domain/architects-visualization/route.yaml†L1-L20】 |
| Sentik | Deployment `sentik`; Service `sentik` (ClusterIP, port 8080); CronJob `sentik-send-not-ready`; RBAC & secrets for Teams notifications. | `oc -n support-domain get all -l app=sentik` | Observability tool that watches platform readiness and pings Microsoft Teams via webhook.【F:architecture/support-domain/sentik/deployment.yaml†L1-L47】【F:architecture/support-domain/sentik/service.yaml†L1-L17】【F:architecture/support-domain/sentik/cronjob.yaml†L1-L32】 |

## Shared Components

| Component | Workloads & Resources | Access / Quick Check | Notes |
| --- | --- | --- | --- |
| Access Control | Deployment `access-control-app-instance`; Keycloak deployment, service `keycloak` y Route `keycloak-shared-components.apps-crc.testing`. | `oc -n shared-components get deployment/access-control-app-instance`; `oc -n shared-components get route/keycloak` | Central auth provider; `access-control` calls Keycloak (exposed via the Route on port 80 → 8080).【F:architecture/shared-components/access-control/access-control-app-instance/deployment.yaml†L1-L29】【F:architecture/shared-components/access-control/keycloak/deployment.yaml†L1-L36】【F:architecture/shared-components/access-control/keycloak/service.yaml†L1-L18】【F:architecture/shared-components/access-control/keycloak/route.yaml†L1-L19】 |
| GitLab CE | StatefulSet & Service `gitlab-ce`; Route `gitlab-ce-shared-components.apps-crc.testing`; supporting ConfigMap, Secret, PVCs. | Web: `https://gitlab-ce-shared-components.apps-crc.testing`; CLI: `oc -n shared-components get statefulset/gitlab-ce` | Provides source code management and CI runner integration; service exposes HTTP/HTTPS/SSH ports for in-cluster use.【F:architecture/shared-components/gitlab-ce/statefulset.yaml†L1-L55】【F:architecture/shared-components/gitlab-ce/service.yaml†L1-L18】【F:architecture/shared-components/gitlab-ce/route.yaml†L1-L15】 |
| OpenShift Pipelines | Operator `Subscription` in `openshift-operators`; `TektonConfig` targeting `openshift-pipelines`. | `oc get subscription/openshift-pipelines-operator-rh -n openshift-operators`; `oc get tektonconfig/config` | Enables cluster-wide CI/CD via Tekton with the "all" profile and default pipeline service account.【F:architecture/shared-components/openshift-pipelines/subscription.yaml†L1-L15】【F:architecture/shared-components/openshift-pipelines/tektonconfig.yaml†L1-L16】 |

## Bootstrap Namespaces

Before applying component overlays, the bootstrap kustomization provisions the three domain namespaces so resources land in the correct scope: `business-domain`, `support-domain`, and `shared-components`. Use `oc get namespace <name>` to verify the foundational layout.【F:architecture/bootstrap/00-namespace-business-domain.yaml†L1-L6】【F:architecture/bootstrap/00-namespace-support-domain.yaml†L1-L6】【F:architecture/bootstrap/00-namespace-shared-components.yaml†L1-L6】

