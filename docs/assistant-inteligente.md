# Asistente inteligente de arkit8s

El CLI `arkit8s.py` incluye un modo asistente que responde preguntas usando un modelo ligero
entrenado localmente con el contenido del repositorio. Esta sección resume cómo aprovecharlo y
qué estrategia conviene seguir cuando surgen dudas sobre el alcance del modelo.

## Cómo entrenar el asistente

1. Agrega o actualiza documentación relevante dentro del repositorio (por ejemplo Markdown,
   YAML o scripts) con las respuestas que quieras que el asistente conozca.
2. Ejecuta `python3 arkit8s.py assistant train` para reconstruir el modelo.
   - El comando tokeniza los archivos admitidos, genera fragmentos de texto de hasta 1 200
     caracteres y ajusta un codificador neural pequeño almacenado en `tmp/assistant_model.pkl`.
   - El entrenamiento tarda segundos y no requiere GPU ni dependencias externas.
3. Vuelve a lanzar tus consultas libres (sin grupo ni comando) para obtener la respuesta
   enriquecida con la información recién incorporada.

Si prefieres un alias más corto puedes invocar `python3 arkit8s.py train-assistant`, que
redirige al subcomando anterior.

## ¿Modelo opensource o más fragmentos?

Para preguntas como *"¿es conveniente usar un modelo opensource que sea capaz de responder este
tipo de pregunta o es mejor simplemente agregar más fragmentos y entrenar para las necesidades
específicas del CLI?"* la recomendación es seguir ampliando los fragmentos locales y volver a
entrenar el asistente incluido.

- **Costo y simplicidad**: el modelo integrado es pequeño (se entrena en segundos) y evita
  administrar dependencias externas o credenciales para servicios de inferencia.
- **Contexto alineado**: al nutrirse solo con archivos del repositorio, las respuestas se
  mantienen enfocadas en la arquitectura y comandos de arkit8s.
- **Privacidad**: no se envían datos a terceros; toda la lógica se ejecuta en tu máquina.

Un modelo opensource genérico puede ser útil si necesitas lenguaje natural avanzado o
razonamiento fuera del dominio de arkit8s. Sin embargo, para el CLI resulta más ligero y
rentable mantener el modelo local e iterar sobre la documentación con fragmentos específicos del
proyecto.

## Consejos para redactar fragmentos

- Escribe la información en español claro, reutilizando términos ya presentes en el repositorio.
- Incluye las palabras clave que esperas en las preguntas para que el tokenizador las aprenda.
- Agrupa las ideas en párrafos concisos; cada párrafo debería responder una duda concreta.
- Tras modificar los archivos, recuerda versionarlos con `git` y repetir el entrenamiento del
  asistente.

Siguiendo este flujo, el asistente responderá de forma consistente y alineada a las necesidades
del CLI sin incurrir en los costos de modelos de mayor tamaño.
