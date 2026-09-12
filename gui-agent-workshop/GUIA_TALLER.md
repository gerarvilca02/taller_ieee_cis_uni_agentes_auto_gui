# Guía de demostración

## Objetivo pedagógico

Mostrar que una automatización clásica ejecuta una receta definida por el programador, mientras que un agente recibe una meta, observa el estado actual, elige herramientas y se adapta después de cada acción.

## Secuencia recomendada

### 1. Abrir la consola del agente

Ejecuta `python run_demo.py` y abre `http://127.0.0.1:8000`. Presenta el chat, el selector de modo, la vista de screenshots, la salida equivalente al terminal y el enlace de memoria auditable.

### 2. Explorar la GUI

Abre `http://127.0.0.1:8000/target` y recorre sus componentes:

1. Menú emergente `Operaciones`.
2. Formulario con inputs, select, radio buttons y switch.
3. Modal de confirmación.
4. Toast temporal que se desvanece.
5. Panel lateral de actividad.
6. Estado final verificable.

### 3. Ejecutar la forma clásica

Muestra `automation/classic.py` antes de ejecutarlo. Resalta que cada locator y cada acción corresponden a un paso conocido de antemano. Después cambia una etiqueta de la GUI o altera el orden conceptual del flujo para discutir qué partes habría que reprogramar.

### 4. Presentar el bucle del agente

Explica el ciclo `observar → decidir → actuar → verificar`. El modelo no controla el navegador directamente. Solicita una herramienta con argumentos estructurados y el programa valida y ejecuta esa acción con Playwright.

### 5. Comparar los tres modos

Ejecuta primero `dom`, después `screenshot` y finalmente `hybrid` desde la consola web. Usa exactamente la misma meta para que la comparación sea válida.

| Pregunta | DOM | Screenshot | Híbrido |
| --- | --- | --- | --- |
| ¿Reconoce roles accesibles? | Sí | Solo visualmente | Sí |
| ¿Usa coordenadas? | No | Sí | Solo si conviene |
| ¿Comprende distribución visual? | Limitado | Sí | Sí |
| ¿Tolera Canvas o componentes sin DOM útil? | Poco | Sí | Sí |
| ¿Consumo esperado? | Menor | Mayor | Intermedio o mayor |

### 6. Revisar la auditoría

Abre el enlace `memory.json` y muestra la meta, el plan, las acciones, los resultados y las rutas de capturas. Explica que este archivo se usa para supervisión posterior y no como memoria recuperada por el agente.

### 7. Cierre

La conclusión central es que un agente no elimina Playwright. Cambia quién construye el plan. Playwright sigue siendo la capa determinista que navega, hace clic, escribe y verifica; el modelo aporta interpretación y planificación dinámica.

## Preguntas para los participantes

- ¿Qué ocurre si el botón cambia de posición?
- ¿Qué ocurre si cambia de texto pero conserva su rol y contexto?
- ¿Cuándo es preferible un flujo clásico por costo, seguridad o repetibilidad?
- ¿Qué acciones deberían requerir confirmación humana?
- ¿Cómo registrarías evidencias para auditar cada decisión del agente?
- ¿Qué diferencia existe entre la memoria de trabajo del agente y el registro `memory.json`?

## Extensiones opcionales

- Introducir un cambio de layout y comparar la resiliencia de cada modo.
- Agregar una acción destructiva que requiera aprobación.
- Medir pasos, latencia, tokens y costo por ejecución.
- Ejecutar el mismo objetivo con distinta redacción.
- Añadir una prueba donde una acción falla y el agente debe recuperarse.
