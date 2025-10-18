# Architects Console

Aplicación web basada en Quarkus y Qute que ofrece una experiencia inspirada en Kubeland para los comandos del CLI `arkit8s.py`. El catálogo se alimenta del archivo `commands.json` generado mediante `python arkit8s.py sync-web-console`.

## Requisitos
- Java 17
- Maven 3.9+

## Compilación local
```bash
mvn -pl support-domain/architects-console -am clean package
```

La salida empaquetada se encontrará en `support-domain/architects-console/target/quarkus-app` y se puede ejecutar con:
```bash
java -jar target/quarkus-app/quarkus-run.jar
```

## Contenedor
```bash
mvn -pl support-domain/architects-console package -Dquarkus.container-image.build=true \
    -Dquarkus.container-image.image=quay.io/sergio_canales_e/arkit8s/architects-console:latest
```

El contenedor expone el puerto `8080` y espera encontrar el archivo `commands.json` en `/opt/arkit8s/commands/commands.json`.

## Despliegue en OpenShift

Desde la raíz del repositorio puedes aplicar la interfaz web en el clúster ejecutando:

```bash
python3 arkit8s.py console deploy --sync-commands
```

El indicador `--sync-commands` regenera el ConfigMap consumido por la consola antes de aplicar la
kustomization `architecture/support-domain/architects-visualization`.
