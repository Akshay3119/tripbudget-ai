import asyncio
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Header, Request

from .errors import DomainError
from .schemas import utcnow

HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash("constant-time-dummy-account-no-login")


async def login(store, username, password):
    key = hashlib.sha256(username.lower().encode()).hexdigest()
    attempt = await store.one(
        "INSERT INTO auth_attempts(key,attempts,window_start) VALUES(%s,1,now()) "
        "ON CONFLICT(key) DO UPDATE SET attempts=CASE WHEN auth_attempts.window_start<now()-interval '15 minutes' "
        "THEN 1 ELSE auth_attempts.attempts+1 END, window_start=CASE WHEN auth_attempts.window_start<now()-interval '15 minutes' "
        "THEN now() ELSE auth_attempts.window_start END RETURNING attempts",
        (key,),
    )
    if attempt["attempts"] > 20:
        raise DomainError("RATE_LIMIT", "Too many sign-in attempts; try later", 429)
    user = await store.one("SELECT * FROM app_users WHERE username=%s", (username,))
    try:
        await asyncio.to_thread(HASHER.verify, user["password_hash"] if user else DUMMY_HASH, password)
    except VerificationError:
        raise DomainError("UNAUTHENTICATED", "Invalid username or password", 401) from None
    if not user:
        raise DomainError("UNAUTHENTICATED", "Invalid username or password", 401)
    await store.execute("DELETE FROM auth_attempts WHERE key=%s", (key,))
    return {"token": await store.new_session(user["uid"]), "uid": user["uid"], "role": user["role"]}


async def principal(request: Request, authorization: str = Header(default="")):
    if not authorization.startswith("Bearer ") or len(authorization) > 8192:
        raise DomainError("UNAUTHENTICATED", "Sign in to continue", 401)
    token = authorization[7:]
    settings, store = request.app.state.settings, request.app.state.store
    if settings.auth_mode == "firebase":
        import firebase_admin
        from firebase_admin import auth

        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id})
            identity = await asyncio.to_thread(auth.verify_id_token, token, check_revoked=True)
        except Exception:
            raise DomainError("UNAUTHENTICATED", "Invalid Firebase ID token", 401) from None
        if identity["uid"] not in settings.firebase_allowed_uids:
            raise DomainError("FORBIDDEN", "Account is not on the organizer allowlist", 403)
        return {"uid": identity["uid"], "role": "organizer"}
    user = await store.one(
        "SELECT u.uid,u.role,s.expires_at FROM app_sessions s JOIN app_users u ON u.uid=s.uid WHERE token_hash=%s",
        (hashlib.sha256(token.encode()).hexdigest(),),
    )
    if not user or user["expires_at"] <= utcnow():
        raise DomainError("UNAUTHENTICATED", "Session expired; sign in again", 401)
    return {"uid": user["uid"], "role": user["role"]}
