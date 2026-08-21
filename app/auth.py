import os
from functools import wraps

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import connect


def init_auth():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'viewer',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        admin_user = os.getenv("ADMIN_USER", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "change-me-now")
        existing = con.execute("SELECT id FROM users WHERE username=?", (admin_user,)).fetchone()
        if not existing:
            con.execute(
                "INSERT INTO users(username,password_hash,role) VALUES(?,?, 'admin')",
                (admin_user, generate_password_hash(admin_password)),
            )
        con.commit()


def authenticate(username: str, password: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT id,username,password_hash,role FROM users WHERE username=?", (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def create_user(username: str, password: str, role: str = "viewer"):
    if role not in {"admin", "manager", "viewer"}:
        raise ValueError("invalid role")
    if len(username.strip()) < 2 or len(password) < 8:
        raise ValueError("아이디는 2자 이상, 비밀번호는 8자 이상이어야 합니다")
    with connect() as con:
        con.execute(
            "INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
            (username.strip(), generate_password_hash(password), role),
        )
        con.commit()


def list_users():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT id,username,role,created_at FROM users ORDER BY id").fetchall()]


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify(error="로그인이 필요합니다"), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = session.get("user") or {}
        if user.get("role") != "admin":
            return jsonify(error="관리자 권한이 필요합니다"), 403
        return fn(*args, **kwargs)
    return wrapper
