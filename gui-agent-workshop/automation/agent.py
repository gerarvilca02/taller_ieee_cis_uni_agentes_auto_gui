import argparse
import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright

from automation.browser_session import BrowserSession
from automation.session_log import SessionRecorder, generate_session_id


DEFAULT_GOAL = """Registra una nueva solicitud de acceso temporal para Ana Torres usando el correo ana.torres@empresa.com. Debe tener prioridad alta y las notificaciones por correo activadas. Confirma el envío y verifica en el centro de actividad que la solicitud figure como Enviada."""

INSTRUCTIONS = """Eres un agente de navegación web que controla una GUI de demostración mediante Playwright. Recibes una meta, una memoria de trabajo compacta y observaciones actualizadas. Primero presenta una planificación breve. Después deduce una sola acción por turno sin pedir una receta. Lee las etiquetas y estados visibles, evita acciones irrelevantes y no inventes referencias. Usa interacción semántica cuando esté disponible. Tras cada acción recibirás una nueva observación. Solo usa finish cuando hayas abierto la evidencia final y puedas verificar todos los datos solicitados. Si una acción falla, utiliza la observación siguiente para recuperarte. El campo reasoning_summary debe contener únicamente una justificación breve y observable de la acción, nunca una cadena de pensamiento privada."""


def function_tool(name, description, properties, required):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "strict": True,
    }


def planning_tool():
    return function_tool(
        "present_plan",
        "Confirma lo entendido y presenta el plan de navegación antes de actuar.",
        {
            "understanding": {"type": "string"},
            "plan": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 10,
            },
        },
        ["understanding", "plan"],
    )


def action_properties(properties):
    return {
        **properties,
        "reasoning_summary": {
            "type": "string",
            "description": "Justificación breve de la acción basada en la observación actual.",
        },
    }


def action_tool(name, description, properties, required):
    return function_tool(
        name,
        description,
        action_properties(properties),
        [*required, "reasoning_summary"],
    )


def tools_for(mode):
    tools = []
    if mode in {"dom", "hybrid"}:
        tools.extend([
            action_tool(
                "click_element",
                "Haz clic en un elemento visible usando su referencia semántica actual.",
                {"ref": {"type": "string"}},
                ["ref"],
            ),
            action_tool(
                "fill_element",
                "Reemplaza el contenido de un campo de texto identificado semánticamente.",
                {"ref": {"type": "string"}, "text": {"type": "string"}},
                ["ref", "text"],
            ),
            action_tool(
                "select_option",
                "Selecciona una opción de un combobox HTML por su etiqueta visible.",
                {"ref": {"type": "string"}, "label": {"type": "string"}},
                ["ref", "label"],
            ),
            action_tool(
                "set_checked",
                "Activa o desactiva un checkbox, switch o radio identificado semánticamente.",
                {"ref": {"type": "string"}, "checked": {"type": "boolean"}},
                ["ref", "checked"],
            ),
        ])
    if mode in {"screenshot", "hybrid"}:
        tools.extend([
            action_tool(
                "click_at",
                "Haz clic en coordenadas del viewport observado.",
                {
                    "x": {"type": "number", "minimum": 0, "maximum": 1440},
                    "y": {"type": "number", "minimum": 0, "maximum": 1000},
                },
                ["x", "y"],
            ),
            action_tool(
                "type_text",
                "Escribe texto en el elemento que actualmente tiene el foco.",
                {"text": {"type": "string"}},
                ["text"],
            ),
        ])
    tools.extend([
        action_tool(
            "press_key",
            "Presiona una tecla o combinación válida de Playwright.",
            {"key": {"type": "string"}},
            ["key"],
        ),
        action_tool(
            "wait",
            "Espera brevemente cuando la interfaz necesita completar una transición.",
            {"milliseconds": {"type": "integer", "minimum": 100, "maximum": 2000}},
            ["milliseconds"],
        ),
        action_tool(
            "finish",
            "Declara que la meta fue completada y solicita una verificación estricta contra el registro real.",
            {
                "summary": {"type": "string"},
                "expected": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "request_type": {"type": "string"},
                        "priority": {"type": "string"},
                        "notifications": {"type": "boolean"},
                    },
                    "required": ["name", "email", "request_type", "priority", "notifications"],
                    "additionalProperties": False,
                },
            },
            ["summary", "expected"],
        ),
    ])
    return tools


def observation_message(observation, goal, working_memory, stage):
    text = (
        f"Meta del usuario:\n{goal}\n\n"
        f"Etapa actual: {stage}\n"
        f"Memoria de trabajo verificable:\n{json.dumps(working_memory, ensure_ascii=False)}\n\n"
        "Decide la siguiente salida a partir de la observación actual."
    )
    return {
        "role": "user",
        "content": [{"type": "input_text", "text": text}, *observation["content"]],
    }


def response_usage(response):
    if response.usage is None:
        return None
    if hasattr(response.usage, "model_dump"):
        return response.usage.model_dump()
    return str(response.usage)


def first_function_call(response, expected_name=None):
    calls = [item for item in response.output if item.type == "function_call"]
    if not calls:
        raise RuntimeError(f"El modelo no solicitó una acción. Respuesta: {response.output_text}")
    call = calls[0]
    if expected_name and call.name != expected_name:
        raise RuntimeError(f"Se esperaba {expected_name}, pero el modelo solicitó {call.name}")
    return call


def run_agent(
    url,
    mode,
    goal,
    model,
    max_steps=30,
    headless=False,
    delay=180,
    session_id=None,
    event_callback=None,
    artifacts_root="artifacts",
):
    session_id = session_id or generate_session_id("agent")
    recorder = SessionRecorder(
        session_id=session_id,
        kind="agent",
        mode=mode,
        goal=goal,
        model=model,
        artifacts_root=artifacts_root,
        callback=event_callback,
    )
    recorder.emit(
        "session_started",
        message="Entendí la solicitud. Analizaré la interfaz y prepararé un plan antes de actuar.",
        max_steps=max_steps,
    )
    client = OpenAI()
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless, slow_mo=delay)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            session = BrowserSession(page, mode, recorder)
            working_memory = {
                "goal": goal,
                "plan": [],
                "completed_actions": [],
                "failures": 0,
            }
            previous_response_id = None

            observation = session.observe()
            recorder.emit(
                "observation",
                step=0,
                stage="planning",
                screenshot=observation["screenshot_path"],
                semantic_snapshot=observation["snapshot"],
                state=observation["state"],
            )
            response = client.responses.create(
                model=model,
                instructions=INSTRUCTIONS,
                input=[observation_message(observation, goal, working_memory, "planificación")],
                tools=[planning_tool()],
                tool_choice="required",
                parallel_tool_calls=False,
                reasoning={"effort": "low"},
                text={"verbosity": "low"},
                store=True,
            )
            recorder.emit("response", response_id=response.id, usage=response_usage(response))
            previous_response_id = response.id
            plan_call = first_function_call(response, "present_plan")
            plan_arguments = json.loads(plan_call.arguments)
            working_memory["plan"] = plan_arguments["plan"]
            recorder.emit(
                "plan",
                understanding=plan_arguments["understanding"],
                items=plan_arguments["plan"],
            )
            print(f"Plan | {plan_arguments['understanding']}")
            for index, item in enumerate(plan_arguments["plan"], 1):
                print(f"  {index}. {item}")
            pending_output = {
                "type": "function_call_output",
                "call_id": plan_call.call_id,
                "output": json.dumps({"ok": True, "message": "Plan presentado al usuario"}, ensure_ascii=False),
            }

            for step in range(1, max_steps + 1):
                observation = session.observe()
                recorder.emit(
                    "observation",
                    step=step,
                    stage="execution",
                    screenshot=observation["screenshot_path"],
                    semantic_snapshot=observation["snapshot"],
                    state=observation["state"],
                )
                response = client.responses.create(
                    model=model,
                    instructions=INSTRUCTIONS,
                    input=[
                        pending_output,
                        observation_message(observation, goal, working_memory, f"ejecución, paso {step} de {max_steps}"),
                    ],
                    tools=tools_for(mode),
                    tool_choice="required",
                    parallel_tool_calls=False,
                    previous_response_id=previous_response_id,
                    reasoning={"effort": "low"},
                    text={"verbosity": "low"},
                    store=True,
                )
                recorder.emit("response", response_id=response.id, usage=response_usage(response))
                previous_response_id = response.id
                call = first_function_call(response)
                arguments = json.loads(call.arguments)
                reasoning_summary = arguments.get("reasoning_summary", "")
                public_arguments = {key: value for key, value in arguments.items() if key != "reasoning_summary"}
                recorder.emit(
                    "step_started",
                    step=step,
                    action=call.name,
                    description=reasoning_summary,
                    arguments=public_arguments,
                )
                print(f"Paso {step:02d} | {call.name} | {reasoning_summary} | {json.dumps(public_arguments, ensure_ascii=False)}")
                try:
                    result = session.execute(call.name, arguments)
                except Exception as error:
                    result = {"ok": False, "action": call.name, "error": str(error)}
                if call.name != "wait":
                    page.wait_for_timeout(250)
                state_after = session.task_state()
                recorder.emit(
                    "step_result",
                    step=step,
                    action=call.name,
                    ok=result.get("ok", False),
                    result=result,
                    state=state_after,
                )
                print(f"Resultado {step:02d} | {'OK' if result.get('ok') else 'ERROR'} | {json.dumps(result, ensure_ascii=False)}")
                working_memory["completed_actions"].append({
                    "step": step,
                    "action": call.name,
                    "description": reasoning_summary,
                    "ok": result.get("ok", False),
                })
                working_memory["completed_actions"] = working_memory["completed_actions"][-12:]
                if not result.get("ok", False):
                    working_memory["failures"] += 1
                pending_output = {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
                if call.name == "finish" and result.get("ok"):
                    summary = arguments["summary"]
                    recorder.emit(
                        "session_completed",
                        step=step,
                        summary=summary,
                        memory_file=str(recorder.memory_path),
                        screenshots_directory=str(recorder.screenshots_dir),
                    )
                    print(f"Agente completado en {step} pasos: {summary}")
                    page.wait_for_timeout(800)
                    return {
                        "ok": True,
                        "session_id": session_id,
                        "steps": step,
                        "summary": summary,
                        "memory_file": str(recorder.memory_path),
                    }

            raise RuntimeError(f"El agente agotó el límite de {max_steps} pasos sin verificar la meta")
    except Exception as error:
        recorder.emit(
            "session_error",
            error=str(error),
            memory_file=str(recorder.memory_path),
            screenshots_directory=str(recorder.screenshots_dir),
        )
        raise
    finally:
        if browser and browser.is_connected():
            browser.close()


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Agente multimodal para navegación GUI")
    parser.add_argument("--mode", choices=["dom", "screenshot", "hybrid"], default="hybrid")
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"))
    parser.add_argument("--url", default=os.getenv("GUI_URL", "http://127.0.0.1:8000/target"))
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=int, default=180)
    args = parser.parse_args()
    run_agent(args.url, args.mode, args.goal, args.model, args.max_steps, args.headless, args.delay)


if __name__ == "__main__":
    main()
