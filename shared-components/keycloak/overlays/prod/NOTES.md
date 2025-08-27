# Production Notes

- Provide a TLS secret via `spec.http.tlsSecret` for HTTPS.
- Configure the external PostgreSQL database and ensure the secret `kc-db-credentials` exists.
- Routes should use reencrypt or passthrough termination as appropriate.
