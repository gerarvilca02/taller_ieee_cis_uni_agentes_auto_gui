import argparse
import os

from dotenv import load_dotenv
from playwright.sync_api import expect, sync_playwright

from automation.session_log import SessionRecorder, generate_session_id


GOAL = "Registra una solicitud de acceso temporal para Ana Torres, con prioridad alta, notificaciones activadas y verifica que figure como Enviada."


def run(url, headless, delay, session_id=None):
    session_id = session_id or generate_session_id("classic")
    recorder = SessionRecorder(session_id, "classic", "dom", GOAL)
    recorder.emit("session_started", message="Automatización clásica iniciada")
    browser = None
    step = 0

    def execute(description, action, page):
        nonlocal step
        step += 1
        recorder.emit("step_started", step=step, action="playwright", description=description, arguments={})
        print(f"Paso {step:02d} | {description}")
        try:
            action()
            page.wait_for_timeout(180)
            screenshot_path = recorder.screenshot_path(step)
            page.screenshot(path=str(screenshot_path), full_page=False)
            recorder.emit(
                "step_result",
                step=step,
                action="playwright",
                ok=True,
                result={"message": description, "screenshot": str(screenshot_path)},
            )
        except Exception as error:
            screenshot_path = recorder.screenshot_path(step)
            page.screenshot(path=str(screenshot_path), full_page=False)
            recorder.emit(
                "step_result",
                step=step,
                action="playwright",
                ok=False,
                result={"error": str(error), "screenshot": str(screenshot_path)},
            )
            raise

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless, slow_mo=delay)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")

            execute("Abrir el menú Operaciones", lambda: page.get_by_role("button", name="Operaciones", exact=True).click(), page)
            execute("Seleccionar Nueva solicitud", lambda: page.get_by_role("menuitem", name="Nueva solicitud", exact=True).click(), page)
            execute("Completar el nombre Ana Torres", lambda: page.get_by_label("Nombre completo", exact=True).fill("Ana Torres"), page)
            execute("Completar el correo corporativo", lambda: page.get_by_label("Correo corporativo", exact=True).fill("ana.torres@empresa.com"), page)
            execute("Seleccionar Acceso temporal", lambda: page.get_by_label("Tipo de solicitud", exact=True).select_option(label="Acceso temporal"), page)
            execute("Seleccionar prioridad Alta", lambda: page.get_by_role("radio", name="Alta", exact=True).check(), page)
            execute("Activar las notificaciones por correo", lambda: page.get_by_role("switch", name="Notificaciones por correo", exact=True).check(), page)
            execute("Continuar al resumen", lambda: page.get_by_role("button", name="Continuar", exact=True).click(), page)

            dialog = page.get_by_role("dialog", name="Confirmar solicitud")

            def verify_summary():
                for value in ["Ana Torres", "ana.torres@empresa.com", "Acceso temporal", "Alta", "Activadas"]:
                    expect(dialog.get_by_text(value, exact=True)).to_be_visible()

            execute("Verificar que el modal de confirmación esté visible", lambda: expect(dialog).to_be_visible(), page)
            execute("Verificar los datos del resumen", verify_summary, page)
            execute("Confirmar y enviar la solicitud", lambda: dialog.get_by_role("button", name="Confirmar y enviar", exact=True).click(), page)
            execute("Abrir el centro de actividad", lambda: page.get_by_role("button", name="Ver actividad", exact=True).click(), page)

            record = page.get_by_role("article", name="Solicitud SOL-1043")

            def verify_record_data():
                for value in ["Ana Torres", "ana.torres@empresa.com", "Prioridad Alta", "Notificaciones activadas"]:
                    expect(record).to_contain_text(value)

            execute("Verificar el registro SOL-1043", lambda: expect(record).to_be_visible(), page)
            execute("Verificar el estado Enviada", lambda: expect(record.get_by_text("Enviada", exact=True)).to_be_visible(), page)
            execute("Verificar todos los datos de la solicitud", verify_record_data, page)
            execute("Verificar el estado final de la GUI", lambda: expect(page.locator("body")).to_have_attribute("data-task-status", "completed"), page)

            recorder.emit(
                "session_completed",
                step=step,
                summary="SOL-1043 figura como Enviada con todos los datos esperados",
                memory_file=str(recorder.memory_path),
                screenshots_directory=str(recorder.screenshots_dir),
            )
            print(f"Automatización clásica completada en {step} pasos | Sesión: {session_id}")
            page.wait_for_timeout(800)
            browser.close()
            browser = None
            return {"ok": True, "session_id": session_id, "steps": step}
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
    parser = argparse.ArgumentParser(description="Automatización clásica con pasos explícitos")
    parser.add_argument("--url", default=os.getenv("GUI_URL", "http://127.0.0.1:8000/target"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=int, default=260)
    args = parser.parse_args()
    run(args.url, args.headless, args.delay)


if __name__ == "__main__":
    main()
