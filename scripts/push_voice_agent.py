#!/usr/bin/env python3
"""Create or update Finora's voice agent on ElevenLabs (contracts/agent_api_contract.md v1.1).

    python scripts/push_voice_agent.py            # dry run: render the bodies, show the plan
    python scripts/push_voice_agent.py --apply    # create / update (idempotent)

What it manages, all recorded in infra/voice_agent.json (config, not secrets): the agent_id
and the ids of the 5 tools it created. It talks to ElevenLabs with the el_toldo key (SSM
SecureString /toldo/prod/elevenlabs/api_key, us-east-1), read in memory and never printed.
It never touches el_toldo's agents, tools or secrets, and never starts a conversation.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "infra" / "voice_agent.json"
API = "https://api.elevenlabs.io"
BASE = "https://d1smzfxmkay9lx.cloudfront.net"
NAME = "Finora · Analista de datos (voz)"
LLM = "claude-haiku-4-5"                  # ElevenLabs-hosted (the user's choice); same model el_toldo runs here
VOICE_ES = "b2htR0pMe28pYwCY9gnP"         # a Spanish voice already in the workspace (shared, not modified)
TTS_MODEL = "eleven_v4_turbo"
FIRST_MESSAGE = "Hola, estoy cargando los números de hoy."
AUTH_HEADER = {"variable_name": "secret__agent_token"}  # value = the agent token (the API also accepts "Bearer <t>")

PROMPT = """Eres el analista de datos de Finora por voz. Hablas solo en español, con frases cortas y claras.

Reglas:
1. Al empezar la conversación llama a get_briefing antes de decir cualquier número. Luego di los 2 o 3 primeros hechos (text_es, en orden) y ofrece "¿qué más quieres ver?". Los demás hechos quedan para cuando pregunten.
2. Nunca digas un número que no venga, tal cual, del resultado de una herramienta (text_es, summary_es, reason_es, alternative_es, caveats_es). No calcules, no redondees, no conviertas monedas.
3. Para cualquier pregunta que el resumen no responda, di una frase corta como "Déjame revisarlo" y llama a ask con las palabras exactas del usuario en question. En un seguimiento ("¿y en Retail?", "¿y el año anterior?") pasa previous_result_id con el result_id de la respuesta anterior.
4. Si ask devuelve status "pending", di "Sigo trabajando en eso" y vuelve a llamar a ask con la misma question y previous_result_id igual a ese result_id.
5. Si devuelve "answered": di summary_es y después el primer elemento de caveats_es. La advertencia de moneda ("Los montos están en unidades completas…") dila solo una vez por conversación. Luego llama a show_chart con el result_id para que el usuario vea el gráfico, y si hay kpi_ids llama a highlight_kpi con el primero. Ofrece "¿quieres los detalles?" para el resto de caveats_es.
6. Si devuelve "out_of_scope": di reason_es y ofrece alternative_es como pregunta ("¿quieres que te lo muestre?"). Si acepta, llama a ask con esa alternativa en palabras.
7. Si devuelve "error": di reason_es.
8. Nombra el nivel de evidencia cuando evidence no es "observado": inferido = "es una estimación a partir de los pagos"; supuesto = "con las tasas supuestas, no observadas"; no probado = "no está probado con estos datos".
9. Si una herramienta falla con 401 o devuelve "Por favor recarga la página para continuar.", di exactamente: "Por favor recarga la página para continuar."
10. Para mostrar otra página usa go_to_page con dq, acquisition o mrr, sin terminar la conversación.
11. Nunca leas filas, identificadores ni listas largas. Nunca menciones montos de personal (equipo, nómina, freelance) ni datos de un cliente individual.

Rol del usuario: {{user_role}}. Los datos llegan hasta {{as_of_month}}."""

WEBHOOKS = {
    "get_briefing": {"method": "GET", "path": "/api/agent/briefing", "timeout": 10,
                     "description": "Trae el resumen precalculado de la última actualización: hechos clave (text_es), "
                                    "definiciones y advertencias. Llámala al inicio, antes de decir cualquier número."},
    "ask": {"method": "POST", "path": "/api/agent/ask", "timeout": 25,
            "description": "Responde una pregunta nueva sobre calidad de datos, adquisición o MRR. Devuelve status, "
                           "summary_es, caveats_es, evidence, kpi_ids y result_id (nunca filas).",
            "body": {"type": "object", "description": "La pregunta del usuario.", "required": ["question"],
                     "properties": {
                         "question": {"type": "string", "description": "Las palabras exactas del usuario, en español."},
                         "previous_result_id": {"type": "string", "description": "El result_id de la respuesta anterior "
                                                "si es un seguimiento o si ask devolvió pending; vacío si no."}}}},
}
CLIENT = {
    "show_chart": ("Muestra en la pantalla el gráfico de un resultado de ask.", {
        "result_id": {"type": "string", "description": "El result_id que devolvió ask."}}, ["result_id"]),
    "highlight_kpi": ("Resalta en la página la tarjeta del KPI del que estás hablando.", {
        "kpi_id": {"type": "string", "description": "Un kpi_id de kpi_ids o del resumen."}}, ["kpi_id"]),
    "go_to_page": ("Lleva al usuario a otra página del tablero sin terminar la conversación.", {
        "page": {"type": "string", "enum": ["dq", "acquisition", "mrr"],
                 "description": "dq, acquisition o mrr."}}, ["page"]),
}


def webhook_tool(name: str) -> dict:
    w = WEBHOOKS[name]
    schema = {"url": BASE + w["path"], "method": w["method"], "request_headers": {"Authorization": AUTH_HEADER}}
    if w.get("body"):
        schema.update({"content_type": "application/json", "request_body_schema": w["body"]})
    return {"tool_config": {"type": "webhook", "name": name, "description": w["description"],
                            "response_timeout_secs": w["timeout"], "api_schema": schema}}


def client_tool(name: str) -> dict:
    desc, props, req = CLIENT[name]
    return {"tool_config": {"type": "client", "name": name, "description": desc, "expects_response": False,
                            "parameters": {"type": "object", "properties": props, "required": req}}}


def agent_body(tool_ids: list[str], max_s: int, daily: int, retention_days: int) -> dict:
    return {
        "name": NAME, "tags": ["finora", "voice", "analytics"],
        "conversation_config": {
            "agent": {"first_message": FIRST_MESSAGE, "language": "es",
                      "dynamic_variables": {"dynamic_variable_placeholders": {
                          "user_role": "data", "as_of_month": "2024-10", "secret__agent_token": "unset"}},
                      "prompt": {"prompt": PROMPT, "llm": LLM, "temperature": 0.2, "tool_ids": tool_ids,
                                 "ignore_default_personality": True,
                                 "built_in_tools": {"end_call": {"type": "system", "name": "end_call", "description": "",
                                                                 "params": {"system_tool_type": "end_call"}}}}},
            "tts": {"model_id": TTS_MODEL, "voice_id": VOICE_ES},
            "conversation": {"max_duration_seconds": max_s},
        },
        "platform_settings": {
            "auth": {"enable_auth": True},
            "privacy": {"record_voice": False, "retention_days": retention_days, "delete_transcript_and_pii": True,
                        "delete_audio": True, "apply_to_existing_conversations": False},
            "overrides": {"conversation_config_override": {
                "agent": {"language": False, "first_message": False,
                          "prompt": {"prompt": False, "llm": False}},
                "tts": {"voice_id": False}, "conversation": {"text_only": False}}},
            "call_limits": {"agent_concurrency_limit": 2, "daily_limit": daily},
        },
    }


class El:
    def __init__(self):
        ssm = boto3.Session(profile_name="alegra-test", region_name="us-east-1").client("ssm")
        self.key = ssm.get_parameter(Name="/toldo/prod/elevenlabs/api_key", WithDecryption=True)["Parameter"]["Value"]

    def call(self, method: str, path: str, body=None) -> tuple[int, object]:
        req = urllib.request.Request(API + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"xi-api-key": self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read()
                return r.status, (json.loads(text) if text else {})
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")[:800]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    tools = dict(state.get("tool_ids") or {})
    bodies = {n: webhook_tool(n) for n in WEBHOOKS} | {n: client_tool(n) for n in CLIENT}
    out = Path("/tmp/finora-voice-agent")
    out.mkdir(exist_ok=True)
    for n, b in bodies.items():
        (out / f"tool.{n}.json").write_text(json.dumps(b, indent=2, ensure_ascii=False))
    if not a.apply:
        print("DRY RUN:", {n: ("update " + tools[n]) if n in tools else "create" for n in bodies},
              "agent:", "update " + state["agent_id"] if state.get("agent_id") else "create", f"(bodies in {out})")
        return
    el = El()
    for n, b in bodies.items():
        if n in tools:
            st, got = el.call("PATCH", f"/v1/convai/tools/{tools[n]}", b)
        else:
            st, got = el.call("POST", "/v1/convai/tools", b)
            if st < 300:
                tools[n] = got["id"]
        print(f"tool {n}: {st}" + ("" if st < 300 else f" {got}"))
        if st >= 300:
            sys.exit(1)
        state["tool_ids"] = tools
        STATE.write_text(json.dumps(state, indent=2) + "\n")
    max_s, daily = int(state.get("max_conversation_s", 300)), int(state.get("sessions_per_day", 5))
    for retention in (0, 1):  # the plan minimum: 0 if allowed, else 1 day
        body = agent_body([tools[n] for n in bodies], max_s, daily, retention)
        (out / "agent.json").write_text(json.dumps(body, indent=2, ensure_ascii=False))
        if state.get("agent_id"):
            st, got = el.call("PATCH", f"/v1/convai/agents/{state['agent_id']}", body)
        else:
            st, got = el.call("POST", "/v1/convai/agents/create", body)
            if st < 300:
                state["agent_id"] = got["agent_id"]
        if st < 300:
            state["retention_days"] = retention
            break
        print(f"agent with retention_days={retention}: {st} {got}")
    print(f"agent {'updated' if st < 300 else 'FAILED'}: {st} {state.get('agent_id', '')}")
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    if st >= 300:
        sys.exit(1)
    st, got = el.call("GET", f"/v1/convai/agents/{state['agent_id']}")
    cfg = got if isinstance(got, dict) else {}
    ps = cfg.get("platform_settings") or {}
    print("verify:", json.dumps({"language": (cfg.get("conversation_config") or {}).get("agent", {}).get("language"),
                                 "enable_auth": (ps.get("auth") or {}).get("enable_auth"), "privacy": ps.get("privacy"),
                                 "tools": len(((cfg.get("conversation_config") or {}).get("agent", {}).get("prompt") or {})
                                              .get("tool_ids") or [])}))


if __name__ == "__main__":
    main()
