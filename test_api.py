"""
test_api.py — Script de pruebas manuales para Nexo Designs API
Ejecutar desde VSCode: python test_api.py

Requisitos:
  pip install requests

Instrucciones:
  1. Arranca el backend: uvicorn main:app --reload
  2. Pon tu JWT de Supabase en la variable JWT_TOKEN (ver cómo obtenerlo abajo)
  3. Ejecuta el script completo o comenta las secciones que no quieras probar

Cómo obtener el JWT de Supabase Auth:
  - Ve a tu proyecto Supabase → Table Editor → SQL Editor
  - O desde el frontend: console.log((await supabase.auth.getSession()).data.session.access_token)
  - O llama directamente: POST https://<project>.supabase.co/auth/v1/token?grant_type=password
    Body: { "email": "tu@email.com", "password": "tupassword" }
    Copia el campo "access_token" de la respuesta
"""

import json
import os
import requests

# ── Configuración ─────────────────────────────────────────────────────────────
# BASE_URL = "http://localhost:8000"          # Cambiar si el backend está en Render
BASE_URL = "https://nexo-backend-p5p4.onrender.com"
JWT_TOKEN = "eyJhbGciOiJFUzI1NiIsImtpZCI6ImEyYTE0MzdiLWUxNWEtNDkxNy1hN2U4LTczNzI1YzkyZjVlZCIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2hhZXVva3NnaXVlZGtneWRsc3JlLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0ZDNmNWQ1ZC1iNmE0LTQ4OWMtYWYyMS02NWQ0MTNkMTU1Y2YiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzc0NTczMDEzLCJpYXQiOjE3NzQ1Njk0MTMsImVtYWlsIjoibmV4b2Rlc2lnbm1zQGdtYWlsLmNvbSIsInBob25lIjoiIiwiYXBwX21ldGFkYXRhIjp7InByb3ZpZGVyIjoiZW1haWwiLCJwcm92aWRlcnMiOlsiZW1haWwiXX0sInVzZXJfbWV0YWRhdGEiOnsiZW1haWxfdmVyaWZpZWQiOnRydWV9LCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImFhbCI6ImFhbDEiLCJhbXIiOlt7Im1ldGhvZCI6InBhc3N3b3JkIiwidGltZXN0YW1wIjoxNzc0NTY5NDEzfV0sInNlc3Npb25faWQiOiI5ZmY4YmNkOS03YjRiLTQwMjQtYWJjMi0wM2Y5MzhkZGU4YzYiLCJpc19hbm9ueW1vdXMiOmZhbHNlfQ.lRi42078E2cQOwjPZJ51kcpCO7tZKOQWCLsS5gdmxKPBr8ZhRST0znfLOKUG042PW8dA6R92kv7_CNaR8LGDzQ"             # JWT de Supabase Auth

HEADERS = {"Authorization": f"Bearer {JWT_TOKEN}"}

# Archivo de test para subir (pon la ruta a cualquier PDF que tengas)
TEST_PDF_PATH = "lt1173.pdf"        # Cambia a la ruta de tu PDF real


# ── Helpers ───────────────────────────────────────────────────────────────────
def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def print_result(resp: requests.Response):
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        print(resp.text)
    return resp


# ── 1. Health check ───────────────────────────────────────────────────────────
print_section("1. HEALTH CHECK")
r = requests.get(f"{BASE_URL}/health")
print_result(r)


# ── 2. Crear proyecto ─────────────────────────────────────────────────────────
print_section("2. CREAR PROYECTO")
r = requests.post(
    f"{BASE_URL}/projects",
    headers=HEADERS,
    json={
        "name": "DC-DC Converter 12V→5V Test",
        "client_name": "Test electronics",
        "description": "Test project created from test_api.py",
    },
)
result = print_result(r)
PROJECT_ID = result.json().get("id") if result.status_code == 201 else None
print(f"\n>>> PROJECT_ID guardado: {PROJECT_ID}")


# ── 3. Listar proyectos ───────────────────────────────────────────────────────
print_section("3. LISTAR PROYECTOS")
r = requests.get(f"{BASE_URL}/projects", headers=HEADERS)
print_result(r)


# ── 4. Guardar requisitos del proyecto ────────────────────────────────────────
print_section("4. GUARDAR REQUISITOS")
if PROJECT_ID:
    r = requests.post(
        f"{BASE_URL}/projects/{PROJECT_ID}/requirements",
        headers=HEADERS,
        json={
            "input_voltage_min": 10.0,
            "input_voltage_max": 14.0,
            "output_voltage": 5.0,
            "max_current": 1.0,
            "max_ripple_percent": 10.0,
            "temperature_range": "-40°C to +85°C",
            "main_function": "Step down DC voltage efficiently",
            "constraints": "1A maximum output current, industrial temperature range",
            "kpis": "Size, Efficiency",
            "notes": "Provide input and output connectors and protection elements",
        },
    )
    print_result(r)
else:
    print("SKIP — no hay PROJECT_ID disponible")


# ── 5. Leer requisitos ────────────────────────────────────────────────────────
print_section("5. LEER REQUISITOS")
if PROJECT_ID:
    r = requests.get(
        f"{BASE_URL}/projects/{PROJECT_ID}/requirements",
        headers=HEADERS,
    )
    print_result(r)


# ── 6. Subir documento PDF ────────────────────────────────────────────────────
print_section("6. SUBIR DOCUMENTO PDF")
DOCUMENT_ID = None

if os.path.exists(TEST_PDF_PATH):
    with open(TEST_PDF_PATH, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/documents",
            headers=HEADERS,
            files={"file": (os.path.basename(TEST_PDF_PATH), f, "application/pdf")},
            data={
                "document_type": "datasheet",
                "project_id": PROJECT_ID or "",
            },
        )
    result = print_result(r)
    DOCUMENT_ID = result.json().get("id") if r.status_code == 201 else None
    print(f"\n>>> DOCUMENT_ID guardado: {DOCUMENT_ID}")
else:
    print(f"SKIP — archivo '{TEST_PDF_PATH}' no encontrado.")
    print("Cambia TEST_PDF_PATH a la ruta de un PDF real para probar este bloque.")


# ── 7. Polling del estado de embedding ───────────────────────────────────────
print_section("7. ESTADO DEL EMBEDDING (polling manual)")
if DOCUMENT_ID:
    import time
    print("Esperando a que el embedding se complete (máx 60s)...")
    for attempt in range(12):
        r = requests.get(f"{BASE_URL}/documents/{DOCUMENT_ID}", headers=HEADERS)
        data = r.json()
        status = data.get("embedding_status")
        print(f"  Intento {attempt+1}/12: embedding_status = {status}")
        if status in ("done", "error"):
            print_result(r)
            break
        time.sleep(5)
else:
    print("SKIP — no hay DOCUMENT_ID disponible")


# ── 8. Listar documentos ──────────────────────────────────────────────────────
print_section("8. LISTAR DOCUMENTOS")
r = requests.get(
    f"{BASE_URL}/documents",
    headers=HEADERS,
    params={"project_id": PROJECT_ID} if PROJECT_ID else {},
)
print_result(r)


# ── 9. Búsqueda semántica RAG ─────────────────────────────────────────────────
print_section("9. BÚSQUEDA RAG")
r = requests.post(
    f"{BASE_URL}/rag/search",
    headers=HEADERS,
    json={
        "query": "buck converter step down 12V 5V efficiency",
        "project_id": PROJECT_ID,
        "top_k": 3,
    },
)
result = print_result(r)
if r.status_code == 200:
    chunks = result.json().get("results", [])
    print(f"\n>>> {len(chunks)} chunks recuperados")
    for i, chunk in enumerate(chunks):
        sim = chunk.get("similarity", 0)
        preview = chunk.get("content", "")[:120].replace("\n", " ")
        print(f"  [{i+1}] similarity={sim:.3f} | {preview}...")


# ── 10. Ejecutar fase Research (dispara n8n) ──────────────────────────────────
print_section("10. EJECUTAR FASE RESEARCH")
RUN_ID = None
if PROJECT_ID:
    r = requests.post(
        f"{BASE_URL}/projects/{PROJECT_ID}/phases/research/run",
        headers=HEADERS,
        json={"custom_inputs": {"notes": "Test run from test_api.py"}},
    )
    result = print_result(r)
    if r.status_code == 202:
        RUN_ID = result.json().get("run_id")
        print(f"\n>>> RUN_ID guardado: {RUN_ID}")
        print(">>> n8n ejecutando en background. Usa el bloque 11 para ver el estado.")
else:
    print("SKIP — no hay PROJECT_ID disponible")


# ── 11. Polling del estado del run ────────────────────────────────────────────
print_section("11. ESTADO DEL RUN (polling manual)")
if RUN_ID and PROJECT_ID:
    import time
    print("Esperando resultado de n8n (máx 5 minutos, polling cada 10s)...")
    for attempt in range(30):
        r = requests.get(
            f"{BASE_URL}/projects/{PROJECT_ID}/phases/research/runs/{RUN_ID}",
            headers=HEADERS,
        )
        data = r.json()
        run_status = data.get("status")
        print(f"  Intento {attempt+1}/30: status = {run_status}")
        if run_status in ("completed", "failed"):
            print_result(r)
            break
        time.sleep(10)
else:
    print("SKIP — no hay RUN_ID disponible")


# ── 12. Listar runs de una fase ───────────────────────────────────────────────
print_section("12. LISTAR RUNS DE FASE RESEARCH")
if PROJECT_ID:
    r = requests.get(
        f"{BASE_URL}/projects/{PROJECT_ID}/phases/research/runs",
        headers=HEADERS,
    )
    print_result(r)


# ── 13. Activar un run manualmente ────────────────────────────────────────────
print_section("13. ACTIVAR RUN")
if PROJECT_ID and RUN_ID:
    r = requests.post(
        f"{BASE_URL}/projects/{PROJECT_ID}/phases/research/runs/{RUN_ID}/activate",
        headers=HEADERS,
    )
    print_result(r)
else:
    print("SKIP — necesitas un RUN_ID de un run completado")


# ── 14. Simular callback de n8n (sin n8n real) ────────────────────────────────
print_section("14. SIMULAR CALLBACK DE N8N")
print("Para simular que n8n completó un run sin tener n8n configurado,")
print("necesitas el N8N_WEBHOOK_SECRET de tu .env y un RUN_ID existente.")
print()
print("Descomenta y ajusta el bloque siguiente:")
print()
"""
FAKE_RUN_ID = "PEGA_AQUI_UN_RUN_ID_EN_STATUS_RUNNING"
N8N_SECRET  = "PEGA_AQUI_TU_N8N_WEBHOOK_SECRET"

r = requests.post(
    f"{BASE_URL}/webhooks/n8n/callback",
    headers={"X-N8N-Secret": N8N_SECRET},
    json={
        "run_id": FAKE_RUN_ID,
        "status": "completed",
        "output_payload": {
            "solutions": [
                {
                    "id": "A",
                    "title": "Synchronous Buck Converter",
                    "description": "High efficiency step-down using LM5148",
                    "key_references": ["LM5148 datasheet", "TI SLVA559"]
                }
            ],
            "query_summary": "12V to 5V 1A buck converter"
        },
        "n8n_execution_id": "fake-exec-001",
        "duration_seconds": 45,
        "tokens_used": 12000,
    },
)
print_result(r)
"""


# ── 15. Re-ingestar documento (si falló) ──────────────────────────────────────
print_section("15. RE-INGESTAR DOCUMENTO (si falló)")
if DOCUMENT_ID:
    r = requests.get(f"{BASE_URL}/documents/{DOCUMENT_ID}", headers=HEADERS)
    current_status = r.json().get("embedding_status")
    print(f"Estado actual del documento: {current_status}")
    if current_status == "error":
        r = requests.post(
            f"{BASE_URL}/documents/{DOCUMENT_ID}/reingest",
            headers=HEADERS,
        )
        print_result(r)
    else:
        print(f"No es necesario re-ingestar (status={current_status})")
else:
    print("SKIP — no hay DOCUMENT_ID disponible")


print("\n" + "="*60)
print("  TESTS COMPLETADOS")
print("="*60)
print(f"\nResumen de IDs creados en esta sesión:")
print(f"  PROJECT_ID:  {PROJECT_ID}")
print(f"  DOCUMENT_ID: {DOCUMENT_ID}")
print(f"  RUN_ID:      {RUN_ID}")
print("\nPuedes usar estos IDs para pruebas adicionales en Swagger:")
print(f"  http://localhost:8000/docs")