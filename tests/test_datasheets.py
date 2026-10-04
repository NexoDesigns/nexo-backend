"""
/datasheets against a disposable Supabase with the datasheet_extractor
schema applied (`npx supabase start` in that repo). Skipped without one:

    DATASHEETS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
    DATASHEETS_TEST_SUPABASE_URL=http://127.0.0.1:54321
    DATASHEETS_TEST_SERVICE_KEY=<service_role key>

It empties datasheets.sheets: never point it at a real project. Seeding the
rows needs psycopg (`pip install "psycopg[binary]"`), a test-only dependency.
"""

from __future__ import annotations

import json
import os

import pytest

DSN = os.environ.get("DATASHEETS_TEST_DATABASE_URL")
URL = os.environ.get("DATASHEETS_TEST_SUPABASE_URL")
KEY = os.environ.get("DATASHEETS_TEST_SERVICE_KEY")
pytestmark = pytest.mark.skipif(not (DSN and URL and KEY), reason="no disposable Supabase (DATASHEETS_TEST_*)")

API_KEY = "n8n-test-key"


def sheet_row(file_name, gpn, parts, status, description, supply, temps=(-40, 125), quals=()):
    facts = {"identity": {"part_numbers": parts, "description": description},
             "supplies": [{"name": "VIN", "min": supply[0], "max": supply[1], "units": "V"}]}
    return {
        "file_name": file_name, "gpn": gpn, "doc_sha256": gpn.lower().ljust(64, "0"), "part_numbers": parts,
        "manufacturer": "ti", "package": "DBV (SOT-23, 5)", "status": status, "valid": True,
        "data": json.dumps({"gpn": gpn, "part_numbers": parts, "facts": facts, "status": status}),
        "description": description, "temp_min": temps[0], "temp_max": temps[1], "qualifications": list(quals),
        "supply": f"[{supply[0]},{supply[1]}]", "search_text": f"{gpn} {' '.join(parts)} ti {description}",
    }


@pytest.fixture()
def client(monkeypatch):
    import psycopg

    for name, value in {
        "SUPABASE_URL": URL, "SUPABASE_SERVICE_KEY": KEY, "N8N_BASE_URL": "http://n8n", "N8N_WEBHOOK_SECRET": "x",
        "BACKEND_URL": "http://backend", "OPENAI_API_KEY": "x", "N8N_SERVICE_API_KEY": API_KEY,
        "N8N_SERVICE_USER_ID": "00000000-0000-0000-0000-000000000001",
    }.items():
        monkeypatch.setenv(name, value)
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("truncate datasheets.sheets cascade")
        for row in (
            sheet_row("TLV755P__TLV75533PDBVR__t.json", "TLV755P", ["TLV75533PDBVR", "TLV75533PDBVT"], "approved",
                      "500-mA low-dropout voltage regulator", (1.45, 5.5), quals=("AEC-Q100",)),
            sheet_row("LM5164__LM5164DDAR__l.json", "LM5164", ["LM5164DDAR"], "draft",
                      "100-V synchronous buck converter", (6, 100)),
        ):
            conn.execute(
                "insert into datasheets.sheets (file_name, gpn, doc_sha256, part_numbers, manufacturer, package, status,"
                " valid, data, description, temp_min, temp_max, qualifications, supply_ranges, search_text) values ("
                "%(file_name)s, %(gpn)s, %(doc_sha256)s, %(part_numbers)s, %(manufacturer)s, %(package)s, %(status)s,"
                " %(valid)s, %(data)s::jsonb, %(description)s, %(temp_min)s, %(temp_max)s, %(qualifications)s,"
                " array[%(supply)s::numrange], %(search_text)s)", row)

    from fastapi.testclient import TestClient

    from core import config, supabase as supabase_module

    monkeypatch.setattr(config, "settings", config.Settings())
    supabase_module.get_supabase.cache_clear()
    from main import app

    yield TestClient(app)
    supabase_module.get_supabase.cache_clear()


def test_the_design_agents_find_approved_components_only(client) -> None:
    headers = {"X-Api-Key": API_KEY}
    found = client.get("/datasheets/search", params={"q": "voltage regulator", "supply_v": 3.3}, headers=headers)
    assert found.status_code == 200, found.text
    assert [r["gpn"] for r in found.json()["results"]] == ["TLV755P"]
    assert client.get("/datasheets/search", params={"q": "buck converter"}, headers=headers).json()["count"] == 0
    filtered = client.get("/datasheets/search", params={"qualifications": ["aec-q100"], "temp_min": -40,
                                                       "temp_max": 125}, headers=headers)
    assert [r["gpn"] for r in filtered.json()["results"]] == ["TLV755P"]
    assert client.get("/datasheets/search", params={"supply_v": 12}, headers=headers).json()["count"] == 0


def test_a_part_number_finds_its_sheet_and_its_facts(client) -> None:
    headers = {"X-Api-Key": API_KEY}
    found = client.get("/datasheets/by-part/tlv75533pdbv", headers=headers)
    assert found.status_code == 200 and found.json()["gpn"] == "TLV755P"
    sheet = client.get(f"/datasheets/{found.json()['id']}", headers=headers)
    assert sheet.status_code == 200 and sheet.json()["facts"]["identity"]["description"].startswith("500-mA")
    assert client.get("/datasheets/by-part/LM5164DDAR", headers=headers).status_code == 404   # a draft


def test_the_catalog_needs_a_caller(client) -> None:
    assert client.get("/datasheets/search").status_code == 401
    assert client.get("/datasheets/search", headers={"X-Api-Key": "wrong"}).status_code == 401
