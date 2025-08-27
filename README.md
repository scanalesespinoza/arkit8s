# RHBK on CRC

Despliega Red Hat Build of Keycloak en OpenShift Local (CRC) usando Kustomize.

## Requisitos
- CRC en ejecución y accesible
- `oc login` contra el clúster

## Instalación rápida (DEV/CRC)

```bash
make crc-dev
```

## Comandos útiles
- `make wait` – espera a que Keycloak esté listo
- `make admin` – muestra las credenciales iniciales
- `make open` – imprime la URL de acceso

## Desinstalación

```bash
make destroy
```

## Notas de producción

Para producción usa el overlay `shared-components/keycloak/overlays/prod`, una base de datos externa y configura TLS y Routes reencrypt/passthrough.
