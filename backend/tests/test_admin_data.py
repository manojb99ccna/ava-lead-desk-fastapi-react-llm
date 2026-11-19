"""FAQs, business settings, leads, handoffs, customers, conversations, dashboard, security basics."""
from app.models import AvaHandoffRequest
from app.services import faq_service
from app.utils.logger import redact

from .conftest import TUESDAY


def test_faq_crud_and_search(client, db, admin_headers):
    res = client.post("/api/admin/faqs", json={"intent": "parking", "question": "Is there parking near your office?",
                                               "answer": "Yes, free parking."}, headers=admin_headers)
    assert res.status_code == 201
    faq_id = res.json()["id"]
    results = client.get("/api/admin/faqs/search?q=is there parkng", headers=admin_headers).json()
    assert results[0]["id"] == faq_id and results[0]["confident"]
    assert faq_service.best_answer(db, "parking available?") == "Yes, free parking."
    assert faq_service.best_answer(db, "zzzz qqqq") is None

    res = client.put(f"/api/admin/faqs/{faq_id}", json={"intent": "parking", "question": "Parking?",
                                                         "answer": "Paid parking.", "is_active": False},
                     headers=admin_headers)
    assert res.json()["is_active"] is False
    db.expire_all()
    assert faq_service.best_answer(db, "Parking?") != "Paid parking."  # inactive FAQs are ignored
    assert client.delete(f"/api/admin/faqs/{faq_id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/admin/faqs/{faq_id}", headers=admin_headers).status_code == 404


def test_business_settings_hours_services(client, admin_headers):
    settings = {"business_name": "Acme Studio", "email": "hello@acme.test", "timezone": "Europe/London",
                "appointment_duration_minutes": 30, "booking_window_days": 14}
    assert client.put("/api/admin/business/settings", json=settings, headers=admin_headers).json()["business_name"] \
        == "Acme Studio"
    assert client.put("/api/admin/business/settings", json={**settings, "timezone": "Mars/Base"},
                      headers=admin_headers).status_code == 422
    assert client.put("/api/admin/business/settings", json={**settings, "email": "bad"},
                      headers=admin_headers).status_code == 422

    hours = [{"day_of_week": 1, "is_open": True, "opening_time": "12:00", "closing_time": "13:00"}]
    assert client.put("/api/admin/business/hours", json=hours, headers=admin_headers).status_code == 200
    slots = client.get(f"/api/appointments/available-slots?selected_date={TUESDAY}").json()["slots"]
    assert [s["time"] for s in slots] == ["12:00", "12:30"]  # new hours and 30-minute duration
    bad = [{"day_of_week": 1, "is_open": True, "opening_time": "13:00", "closing_time": "12:00"}]
    assert client.put("/api/admin/business/hours", json=bad, headers=admin_headers).status_code == 422

    res = client.post("/api/admin/business/services", json={"name": "SEO Audit", "price": "From INR 5,000"},
                      headers=admin_headers)
    assert res.status_code == 201
    assert client.post("/api/admin/business/services", json={"name": "SEO Audit"},
                       headers=admin_headers).status_code == 409
    assert "SEO Audit" in [s["name"] for s in client.get("/api/chat/info").json()["services"]]


def test_leads_customers_conversations(client, admin_headers, staff_headers):
    client.post("/api/chat", json={"message": "can you send me a quote"})
    sid = client.get("/api/admin/conversations", headers=staff_headers).json()[0]["session_id"]
    for text in ("Karan Mehta", "9876522222", "Website Design", "tomorrow at 2 pm"):
        client.post("/api/chat", json={"message": text, "session_id": sid})

    leads = client.get("/api/admin/leads", headers=staff_headers).json()
    assert len(leads) == 1 and leads[0]["status"] == "new"
    updated = client.patch(f"/api/admin/leads/{leads[0]['id']}", json={"status": "contacted", "notes": "Called"},
                           headers=staff_headers)
    assert updated.json()["status"] == "contacted"
    assert client.patch(f"/api/admin/leads/{leads[0]['id']}", json={"status": "bogus"},
                        headers=staff_headers).status_code == 422

    customers = client.get("/api/admin/customers?q=Karan", headers=staff_headers).json()
    assert customers[0]["leads"] == 1
    detail = client.get(f"/api/admin/customers/{customers[0]['id']}", headers=staff_headers).json()
    assert detail["leads"][0]["status"] == "contacted"

    conversation = client.get("/api/admin/conversations", headers=staff_headers).json()[0]
    assert conversation["message_count"] == 10
    messages = client.get(f"/api/admin/conversations/{conversation['id']}/messages", headers=staff_headers).json()
    assert messages[0]["sender"] == "user"


def test_handoff_management(client, db, staff_headers):
    client.post("/api/chat", json={"message": "I want to talk to a human"})
    handoff = client.get("/api/admin/handoffs?status=open", headers=staff_headers).json()[0]
    res = client.patch(f"/api/admin/handoffs/{handoff['id']}", json={"status": "in_progress", "assign_to_me": True},
                       headers=staff_headers)
    assert res.json()["assigned_to"] == "staff"
    res = client.patch(f"/api/admin/handoffs/{handoff['id']}", json={"status": "resolved",
                                                                     "resolution_note": "Called back"},
                       headers=staff_headers)
    assert res.json()["status"] == "resolved"
    assert client.patch(f"/api/admin/handoffs/{handoff['id']}", json={"status": "nope"},
                        headers=staff_headers).status_code == 422
    assert db.query(AvaHandoffRequest).count() == 1


def test_dashboard_stats(client, staff_headers):
    client.post("/api/appointments", json={"name": "Anita Rao", "phone": "9876500000", "service": "Website Design",
                                           "appointment_date": TUESDAY.isoformat(), "start_time": "10:00"})
    client.post("/api/chat", json={"message": "I want to talk to a human"})
    data = client.get("/api/admin/dashboard", headers=staff_headers).json()
    assert data["stats"]["appointments_upcoming"] == 1
    assert data["stats"]["appointments_pending"] == 1
    assert data["stats"]["handoffs_open"] == 1
    assert data["upcoming_appointments"][0]["name"] == "Anita Rao"
    assert data["llm"]["status"] == "disabled"


def test_security_headers_and_validation_errors(client):
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    res = client.post("/api/appointments", json={"name": "<script>", "phone": "1"})
    assert res.status_code == 422 and "<script>" not in res.text


def test_sql_injection_attempt_is_harmless(client, admin_headers):
    res = client.get("/api/admin/appointments?q=' OR 1=1; DROP TABLE ava_appointments; --", headers=admin_headers)
    assert res.status_code == 200 and res.json() == []
    assert client.get("/api/admin/appointments", headers=admin_headers).status_code == 200


def test_chat_rate_limit(client, monkeypatch):
    from dataclasses import replace

    from app.core.config import settings
    from app.routers import chat as chat_router

    monkeypatch.setattr(chat_router, "settings", replace(settings, rate_limit_chat_per_minute=2))
    codes = [client.post("/api/chat", json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_log_redaction():
    out = redact({"message": "call me on +91 98765 43210 or a.b@example.com", "phone": "9876543210"})
    assert "98765" not in str(out) and "example.com" not in str(out)
