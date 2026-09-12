# Automatización de Interfaces Gráficas con Agentes de IA

Proyecto demostrativo para comparar una automatización clásica de Playwright con un agente multimodal guiado únicamente por una meta. Incluye una consola web tipo chat para iniciar y supervisar al agente en tiempo real.

## Qué incluye

- GUI objetivo `FlowDesk Lab` con menú, formulario, selector, radios, switch, modal, toast temporal, panel lateral y estado verificable.
- Automatización clásica con una receta explícita y validaciones semánticas.
- Agente con modos `dom`, `screenshot` e `hybrid`.
- Chat para enviar la meta y ver la comprensión, planificación, acciones y resultados.
- Justificación breve y auditable de cada acción.
- Capturas automáticas en todos los modos.
- Memoria de trabajo compacta durante la ejecución.
- Registro persistente `memory.json` para supervisión posterior.
- Verificación estricta de los datos antes de aceptar que la meta terminó.

## Preparación en VS Code

Abre la carpeta del proyecto en VS Code. Después abre `Terminal > New Terminal` y ejecuta:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

En macOS o Linux, la activación es:

```bash
source .venv/bin/activate
```

Copia `.env.example` como `.env`:

```powershell
Copy-Item .env.example .env
```

En macOS o Linux:

```bash
cp .env.example .env
```

Abre `.env` y coloca tu API key:

```dotenv
OPENAI_API_KEY=tu_api_key_real
OPENAI_MODEL=gpt-5.6-luna
GUI_URL=http://127.0.0.1:8000/target
```

No publiques ni compartas el archivo `.env`.

## Iniciar la consola web

Ejecuta:

```powershell
python run_demo.py
```

Luego abre:

```text
http://127.0.0.1:8000
```

La GUI que el agente debe controlar está disponible en:

```text
http://127.0.0.1:8000/target
```

## Usar el chat del agente

1. Escribe una meta en lenguaje natural.
2. Selecciona `Solo DOM semántico`, `Solo screenshot` o `DOM + screenshot`.
3. Decide si quieres ver la ventana controlada por Playwright.
4. Presiona `Ejecutar meta`.
5. Revisa la confirmación de entendimiento y el plan.
6. Observa cada acción, su justificación breve, argumentos y resultado.
7. Descarga `memory.json` desde el panel de sesión cuando quieras auditar la ejecución.

La interfaz no muestra la cadena de pensamiento privada del modelo. Muestra una explicación breve que el propio agente entrega para justificar cada acción observada.

## Modos del agente

| Modo | Entrada del modelo | Interacción | Capturas guardadas |
| --- | --- | --- | --- |
| `dom` | Snapshot semántico accesible | Referencias de elementos | Sí |
| `screenshot` | Imagen del viewport | Coordenadas y teclado | Sí |
| `hybrid` | DOM semántico e imagen | Referencias o coordenadas | Sí |

En el modo DOM, el snapshot prioriza la capa activa. Si existe un modal o panel lateral abierto, no presenta controles bloqueados que están detrás. También incluye nombres accesibles, roles, valores, opciones, selección y estado de los controles.

## Ejecutar desde terminal

Con el servidor activo, puedes ejecutar el agente directamente.

Modo DOM:

```powershell
python -m automation.agent --mode dom
```

Modo screenshot:

```powershell
python -m automation.agent --mode screenshot
```

Modo híbrido:

```powershell
python -m automation.agent --mode hybrid
```

Meta personalizada:

```powershell
python -m automation.agent --mode hybrid --goal "Registra una solicitud de acceso permanente para Luis Rojas con el correo luis.rojas@empresa.com, prioridad media, sin notificaciones, y verifica su envío"
```

El límite predeterminado es de 30 acciones:

```powershell
python -m automation.agent --mode dom --max-steps 30
```

## Demostración clásica

Con el servidor activo, abre otra terminal y ejecuta:

```powershell
python -m automation.classic
```

La automatización clásica utiliza locators semánticos de Playwright, valida el resumen antes de enviar y comprueba todos los datos del registro final.

## Capturas y memoria

Cada ejecución crea una carpeta independiente:

```text
artifacts/
└── agent-AAAAMMDD-HHMMSS-identificador/
    ├── memory.json
    └── screenshots/
        ├── observacion_01.png
        ├── observacion_02.png
        └── ...
```

Las sesiones clásicas usan el prefijo `classic-`. Las sesiones del agente usan `agent-`.

`memory.json` contiene:

- Meta, modo, modelo y marcas de tiempo.
- Plan presentado por el agente.
- Identificadores de Responses API.
- Observaciones y estados verificables.
- Acciones, argumentos, justificaciones breves y resultados.
- Rutas de las capturas.
- Estado final o error de la sesión.

Este JSON es un registro de auditoría. El agente no lo relee para decidir. Durante la ejecución utiliza el encadenamiento de Responses API mediante `previous_response_id` y una memoria de trabajo compacta con el plan y las últimas acciones.

## Parámetros del agente

```text
--mode dom|screenshot|hybrid
--model gpt-5.6-luna
--url http://127.0.0.1:8000/target
--max-steps 30
--delay 180
--headless
```

## Archivos principales

| Archivo | Propósito |
| --- | --- |
| `dist/agent.html` | Chat y consola de supervisión |
| `dist/index.html` | GUI objetivo FlowDesk Lab |
| `automation/classic.py` | Flujo clásico y validaciones explícitas |
| `automation/agent.py` | Planificación, Responses API y bucle de acciones |
| `automation/browser_session.py` | Observaciones, interacción y verificación estricta |
| `automation/session_log.py` | Sesiones, capturas y memoria JSON |
| `run_demo.py` | Servidor web, API local y eventos en tiempo real |
| `requirements.txt` | Dependencias del proyecto |

## Consideraciones para el taller

- `dom` suele ser el modo más económico y estable.
- `screenshot` demuestra multimodalidad, pero normalmente consume más tokens.
- `hybrid` combina estructura accesible con contexto visual.
- Playwright sigue ejecutando y validando las acciones. El modelo interpreta la meta y construye el plan.
- El agente solo termina cuando la GUI está en estado completado, el panel de actividad está abierto y los datos reales coinciden con lo solicitado.
