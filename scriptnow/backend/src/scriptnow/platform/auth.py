import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.identity import TenantContext
from scriptnow.platform.models import (
    LoginThrottleModel,
    RefreshTokenModel,
    RefreshTokenStatus,
    SessionModel,
    SessionStatus,
    TenantModel,
    TenantStatus,
    UserModel,
)


class AuthenticationFailed(RuntimeError):
    pass


class CsrfFailed(RuntimeError):
    pass


class RefreshTokenReuseDetected(AuthenticationFailed):
    pass


class LoginRateLimited(AuthenticationFailed):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PasswordHasher:
    n = 2**14
    r = 8
    p = 1

    def hash(self, password: str) -> str:
        if len(password) < 12:
            raise ValueError("password must be at least 12 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self.n,
            r=self.r,
            p=self.p,
        )
        return "$".join(
            [
                "scrypt",
                str(self.n),
                str(self.r),
                str(self.p),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(digest).decode("ascii"),
            ],
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded.split("$")
            if algorithm != "scrypt":
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=base64.urlsafe_b64decode(salt),
                n=int(n),
                r=int(r),
                p=int(p),
            )
            return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
        except (ValueError, TypeError):
            return False


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.passwords = PasswordHasher()
        self._dummy_password_hash = self.passwords.hash("scriptnow dummy password")

    async def create_tenant_owner(
        self,
        *,
        tenant_name: str,
        email: str,
        password: str,
    ) -> tuple[TenantModel, UserModel]:
        async with self.database.session() as session:
            tenant = TenantModel(name=tenant_name)
            session.add(tenant)
            await session.flush()
            user = UserModel(
                tenant_id=tenant.id,
                email=email.strip().casefold(),
                password_hash=self.passwords.hash(password),
            )
            session.add(user)
            await session.flush()
            return tenant, user

    async def login(self, email: str, password: str, *, client_key: str = "unknown") -> AuthTokens:
        throttle_key = token_hash(f"{client_key}|{email.strip().casefold()}")
        result: AuthTokens | None = None
        async with self.database.session() as session:
            throttle = await session.get(LoginThrottleModel, throttle_key)
            if throttle and throttle.blocked_until and not self._expired(throttle.blocked_until):
                raise LoginRateLimited("login temporarily blocked")
            row = (
                await session.execute(
                    select(UserModel, TenantModel)
                    .join(TenantModel, TenantModel.id == UserModel.tenant_id)
                    .where(UserModel.email == email.strip().casefold()),
                )
            ).one_or_none()
            if row is None:
                self.passwords.verify(password, self._dummy_password_hash)
                await self._record_login_failure(session, throttle_key, throttle)
            elif row[1].status != TenantStatus.ACTIVE:
                await self._record_login_failure(session, throttle_key, throttle)
            else:
                user, tenant = row
                if not self.passwords.verify(password, user.password_hash):
                    await self._record_login_failure(session, throttle_key, throttle)
                else:
                    if throttle is not None:
                        await session.delete(throttle)
                    result = await self._issue_session(session, tenant, user)
        if result is None:
            raise AuthenticationFailed("invalid credentials")
        return result

    async def _record_login_failure(
        self,
        session: AsyncSession,
        throttle_key: str,
        throttle: LoginThrottleModel | None,
    ) -> None:
        if throttle is None:
            throttle = LoginThrottleModel(key_hash=throttle_key, failures=0)
            session.add(throttle)
        throttle.failures += 1
        if throttle.failures >= self.settings.login_max_failures:
            throttle.blocked_until = datetime.now(UTC) + timedelta(
                minutes=self.settings.login_block_minutes
            )

    async def _issue_session(
        self,
        session: AsyncSession,
        tenant: TenantModel,
        user: UserModel,
    ) -> AuthTokens:
        now = datetime.now(UTC)
        refresh = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        record = SessionModel(
            tenant_id=tenant.id,
            user_id=user.id,
            csrf_token_hash=token_hash(csrf),
            expires_at=now + timedelta(days=self.settings.refresh_token_days),
        )
        session.add(record)
        await session.flush()
        session.add(
            RefreshTokenModel(
                session_id=record.id,
                token_hash=token_hash(refresh),
                expires_at=record.expires_at,
            ),
        )
        return self._tokens(record, refresh, csrf, now)

    def _tokens(
        self,
        session: SessionModel,
        refresh_token: str,
        csrf_token: str,
        now: datetime,
    ) -> AuthTokens:
        access_expires = now + timedelta(minutes=self.settings.access_token_minutes)
        payload = {
            "sub": session.user_id,
            "tid": session.tenant_id,
            "sid": session.id,
            "jti": str(uuid4()),
            "iss": self.settings.access_token_issuer,
            "aud": self.settings.creator_audience,
            "iat": now,
            "exp": access_expires,
        }
        return AuthTokens(
            access_token=jwt.encode(payload, self.settings.access_token_secret, algorithm="HS256"),
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            access_expires_at=access_expires,
        )

    async def validate_access(self, access_token: str) -> TenantContext:
        try:
            claims = jwt.decode(
                access_token,
                self.settings.access_token_secret,
                algorithms=["HS256"],
                audience=self.settings.creator_audience,
                issuer=self.settings.access_token_issuer,
                options={"require": ["sub", "tid", "sid", "jti", "exp", "iat"]},
            )
        except jwt.PyJWTError as error:
            raise AuthenticationFailed("invalid access token") from error
        async with self.database.session() as session:
            record = await session.get(SessionModel, claims["sid"])
            user = await session.get(UserModel, claims["sub"])
            tenant = await session.get(TenantModel, claims["tid"])
            if (
                record is None
                or user is None
                or tenant is None
                or tenant.status != TenantStatus.ACTIVE
                or record.status != SessionStatus.ACTIVE
                or record.user_id != claims["sub"]
                or record.tenant_id != claims["tid"]
                or self._expired(record.expires_at)
            ):
                raise AuthenticationFailed("session is not active")
        return TenantContext(
            tenant_id=UUID(claims["tid"]),
            user_id=UUID(claims["sub"]),
            is_admin=user.is_admin,
        )

    async def refresh(self, refresh_token: str, csrf_token: str) -> AuthTokens:
        reused = False
        result: AuthTokens | None = None
        async with self.database.session() as session:
            token = (
                await session.scalars(
                    select(RefreshTokenModel).where(
                        RefreshTokenModel.token_hash == token_hash(refresh_token),
                    ),
                )
            ).one_or_none()
            if token is None:
                raise AuthenticationFailed("invalid refresh token")
            record = await session.get(SessionModel, token.session_id)
            if record is None or record.status != SessionStatus.ACTIVE:
                raise AuthenticationFailed("session is not active")
            if token.status == RefreshTokenStatus.USED:
                record.status = SessionStatus.REVOKED
                reused = True
            elif self._expired(token.expires_at) or self._expired(record.expires_at):
                record.status = SessionStatus.REVOKED
            elif not hmac.compare_digest(record.csrf_token_hash, token_hash(csrf_token)):
                raise CsrfFailed("csrf token mismatch")
            else:
                token.status = RefreshTokenStatus.USED
                now = datetime.now(UTC)
                new_refresh = secrets.token_urlsafe(32)
                new_csrf = secrets.token_urlsafe(32)
                record.csrf_token_hash = token_hash(new_csrf)
                session.add(
                    RefreshTokenModel(
                        session_id=record.id,
                        token_hash=token_hash(new_refresh),
                        expires_at=record.expires_at,
                    ),
                )
                result = self._tokens(record, new_refresh, new_csrf, now)
        if reused:
            raise RefreshTokenReuseDetected("refresh token reuse revoked the session")
        if result is None:
            raise AuthenticationFailed("refresh token expired")
        return result

    async def logout(self, access_token: str, csrf_token: str) -> None:
        claims = self._unsafe_decode_verified(access_token)
        async with self.database.session() as session:
            record = await session.get(SessionModel, claims["sid"])
            if record is None or record.status != SessionStatus.ACTIVE:
                raise AuthenticationFailed("session is not active")
            if not hmac.compare_digest(record.csrf_token_hash, token_hash(csrf_token)):
                raise CsrfFailed("csrf token mismatch")
            record.status = SessionStatus.REVOKED

    async def authorize_action(self, access_token: str, csrf_token: str) -> TenantContext:
        context = await self.validate_access(access_token)
        claims = self._unsafe_decode_verified(access_token)
        async with self.database.session() as session:
            record = await session.get(SessionModel, claims["sid"])
            if record is None or record.status != SessionStatus.ACTIVE:
                raise AuthenticationFailed("session is not active")
            if not hmac.compare_digest(record.csrf_token_hash, token_hash(csrf_token)):
                raise CsrfFailed("csrf token mismatch")
        return context

    def _unsafe_decode_verified(self, token: str) -> dict[str, str]:
        try:
            return jwt.decode(
                token,
                self.settings.access_token_secret,
                algorithms=["HS256"],
                audience=self.settings.creator_audience,
                issuer=self.settings.access_token_issuer,
            )
        except jwt.PyJWTError as error:
            raise AuthenticationFailed("invalid access token") from error

    @staticmethod
    def _expired(value: datetime) -> bool:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value <= datetime.now(UTC)
