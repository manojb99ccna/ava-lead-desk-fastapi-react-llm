from datetime import timedelta

from app.models import AvaAppointment, AvaAppointmentHistory, AvaCustomer

from .conftest import FIXED_NOW, SUNDAY, TUESDAY

BOOKING = {
    "name": "Priya Sharma",
    "phone": "+91 98765 43210",
    "service": "Website Design",
    "appointment_date": TUESDAY.isoformat(),
    "start_time": "10:00",
}


def book(client, **overrides):
    return client.post("/api/appointments", json={**BOOKING, **overrides})


def test_available_dates_respect_working_hours(client):
    dates = {d["date"]: d for d in client.get("/api/appointments/available-dates").json()["dates"]}
    assert len(dates) == 7  # booking window
    assert dates[SUNDAY.isoformat()]["is_open"] is False
    assert dates[TUESDAY.isoformat()]["available_slots"] == 9  # 09:00-18:00, 60 min


def test_available_slots_and_today_past_slots(client):
    slots = client.get(f"/api/appointments/available-slots?selected_date={TUESDAY}").json()["slots"]
    assert [s["time"] for s in slots][:2] == ["09:00", "10:00"]
    today = client.get(f"/api/appointments/available-slots?selected_date={FIXED_NOW.date()}").json()["slots"]
    # "now" is 08:00, so every slot today is still in the future
    assert all(s["available"] for s in today)


def test_book_success_creates_code_customer_and_history(client, db):
    res = book(client)
    assert res.status_code == 201, res.text
    appointment = res.json()["appointment"]
    assert appointment["booking_code"].startswith("AVA-")
    assert appointment["status"] == "pending"
    row = db.query(AvaAppointment).one()
    assert row.phone == "919876543210"  # normalized
    assert db.query(AvaCustomer).one().phone == "919876543210"
    assert db.query(AvaAppointmentHistory).one().action == "created"


def test_double_booking_rejected(client):
    assert book(client).status_code == 201
    res = book(client, name="Someone Else", phone="9123456789")
    assert res.status_code == 409
    assert "already booked" in res.json()["detail"]


def test_invalid_bookings_rejected(client):
    assert book(client, appointment_date=SUNDAY.isoformat()).status_code == 400  # closed
    assert book(client, start_time="07:00").status_code == 400  # before opening
    assert book(client, start_time="17:30").status_code == 400  # not a slot / past closing
    assert book(client, start_time="10:30").status_code == 400  # misaligned
    past = (FIXED_NOW.date() - timedelta(days=1)).isoformat()
    assert book(client, appointment_date=past).status_code == 400
    far = (FIXED_NOW.date() + timedelta(days=30)).isoformat()
    assert book(client, appointment_date=far).status_code == 400
    assert book(client, phone="123").status_code == 422
    assert book(client, name="123 456").status_code == 400
    assert book(client, email="not-an-email").status_code == 400


def test_lookup_requires_matching_phone(client):
    code = book(client).json()["appointment"]["booking_code"]
    ok = client.post("/api/appointments/lookup", json={"booking_code": code, "phone": "+91 98765 43210"})
    assert ok.status_code == 200
    wrong = client.post("/api/appointments/lookup", json={"booking_code": code, "phone": "9999999999"})
    assert wrong.status_code == 404
    unknown = client.post("/api/appointments/lookup", json={"booking_code": "AVA-ZZZZZZ", "phone": "919876543210"})
    assert unknown.status_code == 404
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no hint whether the code exists


def test_reschedule_and_cancel_free_the_slot(client, db):
    code = book(client).json()["appointment"]["booking_code"]
    creds = {"booking_code": code, "phone": "919876543210"}

    res = client.post("/api/appointments/reschedule", json={**creds, "new_date": TUESDAY.isoformat(), "new_time": "11:00"})
    assert res.status_code == 200 and res.json()["appointment"]["time"] == "11:00"
    # 10:00 is free again, 11:00 is taken
    assert book(client, phone="9123456789", name="Other Person").status_code == 201
    assert book(client, phone="9123456780", name="Third Person", start_time="11:00").status_code == 409

    assert client.post("/api/appointments/cancel", json=creds).status_code == 200
    assert book(client, phone="9123456780", name="Third Person", start_time="11:00").status_code == 201
    assert client.post("/api/appointments/cancel", json=creds).status_code == 409  # already cancelled

    actions = [h.action for h in db.query(AvaAppointmentHistory).order_by(AvaAppointmentHistory.id)]
    assert actions[:3] == ["created", "rescheduled", "created"]
    assert "cancelled" in actions


def test_reschedule_into_taken_slot_rejected(client):
    code = book(client).json()["appointment"]["booking_code"]
    book(client, phone="9123456789", name="Other Person", start_time="12:00")
    res = client.post("/api/appointments/reschedule", json={"booking_code": code, "phone": "919876543210",
                                                           "new_date": TUESDAY.isoformat(), "new_time": "12:00"})
    assert res.status_code == 409


def test_admin_appointment_management(client, admin_headers, db):
    created = client.post("/api/admin/appointments", json=BOOKING, headers=admin_headers)
    assert created.status_code == 201
    appointment_id = created.json()["id"]
    assert created.json()["source"] == "admin"

    listed = client.get(f"/api/admin/appointments?q=Priya&date_from={TUESDAY}&date_to={TUESDAY}", headers=admin_headers)
    assert [a["id"] for a in listed.json()] == [appointment_id]

    res = client.patch(f"/api/admin/appointments/{appointment_id}", json={"status": "confirmed", "notes": "VIP"},
                       headers=admin_headers)
    assert res.json()["status"] == "confirmed" and res.json()["notes"] == "VIP"
    assert client.patch(f"/api/admin/appointments/{appointment_id}", json={"status": "weird"},
                        headers=admin_headers).status_code == 400

    res = client.post(f"/api/admin/appointments/{appointment_id}/reschedule",
                      json={"new_date": TUESDAY.isoformat(), "new_time": "14:00"}, headers=admin_headers)
    assert res.status_code == 200
    detail = client.get(f"/api/admin/appointments/{appointment_id}", headers=admin_headers).json()
    assert [h["action"] for h in detail["history"]] == ["created", "status_changed", "rescheduled"]
    assert detail["history"][1]["actor"] == "admin:admin"

    assert client.post(f"/api/admin/appointments/{appointment_id}/cancel", json={"reason": "test"},
                       headers=admin_headers).json()["status"] == "cancelled"
    assert client.get("/api/admin/appointments/99999", headers=admin_headers).status_code == 404


def test_reactivating_cancelled_appointment_cannot_double_book(client, admin_headers):
    first = client.post("/api/admin/appointments", json=BOOKING, headers=admin_headers).json()
    client.post(f"/api/admin/appointments/{first['id']}/cancel", json={}, headers=admin_headers)
    assert book(client, phone="9123456789", name="Other Person").status_code == 201
    res = client.patch(f"/api/admin/appointments/{first['id']}", json={"status": "pending"}, headers=admin_headers)
    assert res.status_code == 409


def test_old_unauthenticated_routes_are_gone(client):
    assert client.get("/admin/appointments/").status_code == 404
