"""Tests for the FastAPI web application."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from bill_processor.web.app import app
    return TestClient(app)


@pytest.fixture
def tmp_queue(tmp_path, monkeypatch):
    """Patch BILLS_INPUT_PATH to a temp file."""
    queue_file = tmp_path / "bills_to_process.txt"
    queue_file.write_text("")
    from bill_processor import config
    monkeypatch.setattr(config, "BILLS_INPUT_PATH", queue_file)
    return queue_file


def test_status_returns_ok(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "vendor_sync" in data
    assert "queued_bills" in data


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"GnuCash Bill Processor" in response.content


def test_add_bill_to_queue(client, tmp_queue):
    response = client.post("/bills/queue", data={
        "vendor_name": "Acme Electric",
        "amount": "123.45",
        "memo": "Test bill",
        "bill_date": "2026-03-01",
    })
    assert response.status_code == 200
    content = tmp_queue.read_text()
    assert "Acme Electric" in content
    assert "123.45" in content


def test_delete_bill_from_queue(client, tmp_queue):
    tmp_queue.write_text("Acme Electric, 123.45, test, 2026-03-01\n")
    response = client.delete("/bills/queue/0")
    assert response.status_code == 200
    assert tmp_queue.read_text().strip() == ""


def test_edit_bill_in_queue(client, tmp_queue):
    tmp_queue.write_text("Acme Electric, 123.45, test, 2026-03-01\n")
    response = client.patch("/bills/queue/0", data={
        "vendor_name": "Acme Electric",
        "amount": "200.00",
        "memo": "Updated",
        "bill_date": "2026-03-01",
    })
    assert response.status_code == 200
    content = tmp_queue.read_text()
    assert "200.00" in content


def test_vendor_search_returns_html(client):
    response = client.get("/vendors/search", params={"vendor_name": "acme"})
    assert response.status_code == 200
    # Returns HTML fragment (empty or with results)
    assert "text/html" in response.headers["content-type"]


def test_vendor_search_empty_query(client):
    response = client.get("/vendors/search", params={"vendor_name": ""})
    assert response.status_code == 200
    # Empty query returns empty response
    assert response.content == b""


def test_new_vendor_form_renders(client):
    response = client.get("/vendors/new-form", params={"name": "TestVendor"})
    assert response.status_code == 200
    assert b"TestVendor" in response.content


def test_address_lookup_returns_form(client):
    # With no API keys, should still return a form (possibly with error message)
    response = client.post("/vendors/lookup-address", data={"vendor_name": "Acme Electric"})
    assert response.status_code == 200
    # Should return HTML with a form, not a 500
    assert b"<form" in response.content or b"form" in response.content.lower()


def test_create_vendor_empty_name_rejected(client):
    response = client.post("/vendors/create", data={
        "vendor_name": "",
        "display_name": "",
    })
    assert response.status_code == 200
    assert b"error" in response.content.lower() or b"required" in response.content.lower()
