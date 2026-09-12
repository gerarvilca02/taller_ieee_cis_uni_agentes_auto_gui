import base64
import json


SEMANTIC_SNAPSHOT_SCRIPT = r"""
() => {
  document.querySelectorAll('[data-agent-ref]').forEach(el => el.removeAttribute('data-agent-ref'))
  const isVisible = el => {
    const style = getComputedStyle(el)
    const rect = el.getBoundingClientRect()
    return style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0' && rect.width > 0 && rect.height > 0 && el.getClientRects().length > 0
  }
  const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(isVisible)
  const root = dialogs.length ? dialogs[dialogs.length - 1] : document
  const selector = 'button, a[href], input, select, textarea, [role="button"], [role="menuitem"], [role="status"], [role="dialog"], h1, h2, h3, [data-record-id]'
  const candidates = [...(root.matches?.(selector) ? [root] : []), ...root.querySelectorAll(selector)].filter(isVisible)
  const roleFor = el => {
    if (el.getAttribute('role')) return el.getAttribute('role')
    if (el.tagName === 'BUTTON') return 'button'
    if (el.tagName === 'A') return 'link'
    if (el.tagName === 'SELECT') return 'combobox'
    if (el.tagName === 'TEXTAREA') return 'textbox'
    if (el.matches('h1,h2,h3')) return 'heading'
    if (el.tagName === 'INPUT') {
      if (el.type === 'checkbox') return 'checkbox'
      if (el.type === 'radio') return 'radio'
      return 'textbox'
    }
    return el.tagName.toLowerCase()
  }
  const nameFor = el => {
    const labelledBy = el.getAttribute('aria-labelledby')
    if (labelledBy) {
      const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ').trim()
      if (text) return text
    }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim()
    if (el.labels?.length) return [...el.labels].map(label => label.innerText).join(' ').replace(/\s+/g, ' ').trim()
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`)
      if (label) return label.innerText.trim()
    }
    if (el.getAttribute('placeholder')) return el.getAttribute('placeholder').trim()
    return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 220)
  }
  const elements = candidates.map((el, index) => {
    const ref = `e${index + 1}`
    const role = roleFor(el)
    el.setAttribute('data-agent-ref', ref)
    const item = {ref, role, name: nameFor(el), tag: el.tagName.toLowerCase()}
    if (el.id) item.id = el.id
    if ('value' in el) item.value = el.value
    if ('checked' in el) item.checked = el.checked
    if ('disabled' in el) item.disabled = Boolean(el.disabled)
    if ('required' in el) item.required = Boolean(el.required)
    if (el.getAttribute('aria-expanded') !== null) item.expanded = el.getAttribute('aria-expanded') === 'true'
    if (el.tagName === 'SELECT') item.options = [...el.options].map(option => ({label: option.text, value: option.value, selected: option.selected}))
    if (el.getAttribute('data-record-id')) item.record_id = el.getAttribute('data-record-id')
    return item
  })
  const focused = document.activeElement && document.activeElement !== document.body ? {
    id: document.activeElement.id || null,
    role: roleFor(document.activeElement),
    name: nameFor(document.activeElement)
  } : null
  return {
    page: document.title,
    active_layer: dialogs.length ? 'dialog' : 'page',
    focused_element: focused,
    visible_elements: elements
  }
}
"""


class BrowserSession:
    def __init__(self, page, mode, recorder):
        self.page = page
        self.mode = mode
        self.recorder = recorder
        self.observation_index = 0

    def task_state(self):
        return self.page.evaluate(
            """
            () => ({
              task_status: document.body.dataset.taskStatus || null,
              workflow_state: document.body.dataset.workflowState || null,
              submitted_data: window.flowDeskState?.submittedData || null,
              activity_open: !document.getElementById('activityDrawer')?.hidden
            })
            """
        )

    def semantic_snapshot(self):
        snapshot = self.page.evaluate(SEMANTIC_SNAPSHOT_SCRIPT)
        snapshot["state"] = self.task_state()
        return snapshot

    def observe(self):
        self.observation_index += 1
        image = self.page.screenshot(full_page=False)
        screenshot_path = self.recorder.screenshot_path(self.observation_index)
        screenshot_path.write_bytes(image)
        content = []
        snapshot = None
        if self.mode in {"dom", "hybrid"}:
            snapshot = self.semantic_snapshot()
            content.append({
                "type": "input_text",
                "text": f"Observación semántica actual:\n{json.dumps(snapshot, ensure_ascii=False)}",
            })
        if self.mode in {"screenshot", "hybrid"}:
            encoded = base64.b64encode(image).decode("ascii")
            content.append({
                "type": "input_text",
                "text": "Captura actual del viewport 1440x1000. Interpreta visualmente las etiquetas, controles y estados.",
            })
            content.append({
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
                "detail": "high",
            })
        return {
            "content": content,
            "snapshot": snapshot,
            "screenshot_path": str(screenshot_path),
            "state": self.task_state(),
        }

    def locator_for(self, ref):
        locator = self.page.locator(f'[data-agent-ref="{ref}"]')
        if locator.count() != 1:
            raise ValueError(f"La referencia {ref} no existe en la observación actual")
        if not locator.is_visible():
            raise ValueError(f"La referencia {ref} ya no está visible")
        return locator

    def execute(self, name, arguments):
        if name == "click_element":
            locator = self.locator_for(arguments["ref"])
            locator.scroll_into_view_if_needed()
            locator.click()
            return {"ok": True, "action": name}
        if name == "fill_element":
            locator = self.locator_for(arguments["ref"])
            locator.scroll_into_view_if_needed()
            locator.fill(arguments["text"])
            return {"ok": True, "action": name}
        if name == "select_option":
            locator = self.locator_for(arguments["ref"])
            locator.select_option(label=arguments["label"])
            return {"ok": True, "action": name}
        if name == "set_checked":
            locator = self.locator_for(arguments["ref"])
            locator.set_checked(arguments["checked"])
            return {"ok": True, "action": name}
        if name == "click_at":
            self.page.mouse.click(arguments["x"], arguments["y"])
            return {"ok": True, "action": name}
        if name == "type_text":
            self.page.keyboard.insert_text(arguments["text"])
            return {"ok": True, "action": name}
        if name == "press_key":
            self.page.keyboard.press(arguments["key"])
            return {"ok": True, "action": name}
        if name == "wait":
            self.page.wait_for_timeout(arguments["milliseconds"])
            return {"ok": True, "action": name}
        if name == "finish":
            return self.verify(arguments["expected"])
        raise ValueError(f"Herramienta no soportada: {name}")

    def verify(self, expected):
        state = self.task_state()
        actual = state["submitted_data"]
        if not actual:
            return {
                "ok": False,
                "action": "finish",
                "message": "No existe una solicitud enviada para verificar",
            }
        comparisons = {
            "name": (expected["name"], actual.get("name")),
            "email": (expected["email"], actual.get("email")),
            "request_type": (expected["request_type"], actual.get("type")),
            "priority": (expected["priority"], actual.get("priority")),
            "notifications": (expected["notifications"], actual.get("notifications")),
        }
        mismatches = {}
        for field, (expected_value, actual_value) in comparisons.items():
            if isinstance(expected_value, str):
                matches = expected_value.strip().casefold() == str(actual_value).strip().casefold()
            else:
                matches = expected_value == actual_value
            if not matches:
                mismatches[field] = {"expected": expected_value, "actual": actual_value}
        completed = state["task_status"] == "completed" and state["activity_open"]
        return {
            "ok": completed and not mismatches,
            "action": "finish",
            "state": state,
            "mismatches": mismatches,
            "message": "Objetivo verificado" if completed and not mismatches else "La evidencia visible todavía no coincide con la meta",
        }
