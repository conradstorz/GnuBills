"""Tests for the FastAPI web application."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from bill_processor.web.app import app
    return TestClient(app)


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
