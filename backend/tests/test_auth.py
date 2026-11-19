import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import jwt

from app.auth import hash_password, verify_password
from app.core.config import settings
from app.models import Admin
from app.routers import admin as admin_router

from .conftest import login


def test_login_success_returns_token_and_role(client):
    res = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    body = res.json()
    assert body["token"] and body["admin"]["role"] == "admin"


def test_login_wrong_password(client):
    res = client.post("/api/admin/login", json={"username": "admin", "password": "nope"})
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post("/api/admin/login", json={"username": "ghost", "password": "x"})
    assert res.status_code == 401


def test_passwords_are_argon2(db):
    stored = db.query(Admin).filter_by(username="admin").one().password
    assert stored.startswith("$argon2id$")
    assert verify_password("admin123", stored)
    assert not verify_password("wrong", stored)


def test_legacy_md5_password_is_upgraded_on_login(client, db):
    db.add(Admin(username="old", password=hashlib.md5(b"oldpass1").hexdigest(), role="staff"))
    db.commit()
    login(client, "old", "oldpass1")
    db.expire_all()
    assert db.query(Admin).filter_by(username="old").one().password.startswith("$argon2id$")
    login(client, "old", "oldpass1")  # still works after the upgrade


def test_admin_endpoints_need_token(client):
    for path in ("/api/admin/me", "/api/admin/leads", "/api/admin/appointments", "/api/admin/faqs",
                 "/api/admin/handoffs", "/api/admin/dashboard", "/api/admin/customers",
                 "/api/admin/business/settings", "/api/admin/conversations"):
        assert client.get(path).status_code == 401, path


def test_invalid_and_expired_tokens_rejected(client, db):
    admin = db.query(Admin).filter_by(username="admin").one()
    expired = jwt.encode({"sub": str(admin.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         settings.jwt_secret, algorithm="HS256")
    forged = jwt.encode({"sub": str(admin.id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "another-secret-that-is-long-enough-123456", algorithm="HS256")
    no_exp = jwt.encode({"sub": str(admin.id)}, settings.jwt_secret, algorithm="HS256")
    for token in (expired, forged, no_exp, "garbage"):
        assert client.get("/api/admin/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_deactivated_user_is_locked_out(client, db, admin_headers):
    staff_headers = login(client, "staff", "staff12345")
    staff = db.query(Admin).filter_by(username="staff").one()
    assert client.patch(f"/api/admin/users/{staff.id}", json={"is_active": False},
                        headers=admin_headers).status_code == 200
    assert client.get("/api/admin/me", headers=staff_headers).status_code == 401
    assert client.post("/api/admin/login", json={"username": "staff", "password": "staff12345"}).status_code == 401


def test_staff_role_restrictions(client, staff_headers):
    assert client.get("/api/admin/faqs", headers=staff_headers).status_code == 200
    assert client.get("/api/admin/appointments", headers=staff_headers).status_code == 200
    faq = {"intent": "test", "question": "Q?", "answer": "A"}
    assert client.post("/api/admin/faqs", json=faq, headers=staff_headers).status_code == 403
    assert client.get("/api/admin/users", headers=staff_headers).status_code == 403
    assert client.put("/api/admin/business/settings", json={"business_name": "X"},
                      headers=staff_headers).status_code == 403
    assert client.delete("/api/admin/leads/1", headers=staff_headers).status_code == 403


def test_user_management(client, admin_headers):
    res = client.post("/api/admin/users", json={"username": "newbie", "password": "longpassword", "role": "staff"},
                      headers=admin_headers)
    assert res.status_code == 201
    assert client.post("/api/admin/users", json={"username": "newbie", "password": "longpassword"},
                       headers=admin_headers).status_code == 409
    assert client.post("/api/admin/users", json={"username": "short", "password": "123"},
                       headers=admin_headers).status_code == 422
    login(client, "newbie", "longpassword")


def test_cannot_demote_or_deactivate_self(client, db, admin_headers):
    me = db.query(Admin).filter_by(username="admin").one()
    assert client.patch(f"/api/admin/users/{me.id}", json={"role": "staff"}, headers=admin_headers).status_code == 400


def test_change_own_password(client, admin_headers):
    assert client.post("/api/admin/me/password", json={"current_password": "wrong", "new_password": "newpassword1"},
                       headers=admin_headers).status_code == 400
    assert client.post("/api/admin/me/password", json={"current_password": "admin123", "new_password": "newpassword1"},
                       headers=admin_headers).status_code == 200
    login(client, "admin", "newpassword1")


def test_login_rate_limit(client, monkeypatch):
    monkeypatch.setattr(admin_router, "settings", replace(settings, rate_limit_login_per_minute=3))
    codes = [client.post("/api/admin/login", json={"username": "admin", "password": "bad"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


def test_hash_password_is_salted():
    assert hash_password("same") != hash_password("same")
