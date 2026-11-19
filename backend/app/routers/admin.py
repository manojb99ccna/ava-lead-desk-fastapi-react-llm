"""Admin authentication and user management."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import create_token, current_admin, hash_password, password_needs_rehash, require_admin, verify_password
from ..core.config import settings
from ..core.rate_limit import rate_limit
from ..database import get_db
from ..models import ROLES, Admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

login_limit = rate_limit("login", lambda: settings.rate_limit_login_per_minute)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=100)
    role: str = Field(default="staff", pattern="^(admin|staff)$")


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, pattern="^(admin|staff)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


def admin_out(admin: Admin) -> dict:
    return {
        "id": admin.id, "username": admin.username, "name": admin.name, "role": admin.role,
        "is_active": admin.is_active, "last_login_at": admin.last_login_at, "created_at": admin.created_at,
    }


@router.post("/login", dependencies=[Depends(login_limit)])
def login(data: LoginIn, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == data.username).first()
    if not admin or not admin.is_active or not verify_password(data.password, admin.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if password_needs_rehash(admin.password):
        admin.password = hash_password(data.password)  # upgrades legacy MD5 hashes on login
    admin.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"token": create_token(admin), "admin": admin_out(admin)}


@router.get("/me")
def me(admin: Admin = Depends(current_admin)):
    return admin_out(admin)


@router.post("/me/password")
def change_password(data: PasswordChange, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, admin.password):
        raise HTTPException(400, "Current password is incorrect")
    admin.password = hash_password(data.new_password)
    db.commit()
    return {"success": True}


@router.get("/users")
def list_users(_: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    return [admin_out(a) for a in db.query(Admin).order_by(Admin.id.asc()).all()]


@router.post("/users", status_code=201)
def create_user(data: UserCreate, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(Admin).filter(Admin.username == data.username).first():
        raise HTTPException(409, "Username already exists")
    user = Admin(username=data.username, password=hash_password(data.password), name=data.name, role=data.role,
                 is_active=True)
    db.add(user)
    db.commit()
    return admin_out(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, actor: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(Admin, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == actor.id and (data.is_active is False or (data.role and data.role != user.role)):
        raise HTTPException(400, "You cannot deactivate yourself or change your own role")
    if data.role and data.role not in ROLES:
        raise HTTPException(422, "Invalid role")
    for field in ("name", "role", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(user, field, value)
    if data.password:
        user.password = hash_password(data.password)
    db.commit()
    return admin_out(user)
