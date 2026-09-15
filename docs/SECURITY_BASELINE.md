# Security baseline

- Telegram authentication rejects missing, stale, or future-dated `auth_date` values.
- Authentication bypass is available only when `APP_ENV=dev`; production ignores the development bypass payload.
- JWT access/share decoding rejects non-canonical encodings and requires the expected token type and expiry.
- `TRUSTED_PROXY_HOSTS` controls which peers may supply forwarded headers. Keep it limited to the actual reverse-proxy addresses.
- `JWT_SECRET_KEY`, `SHARE_LINK_SECRET`, and Telegram credentials must be kept outside Git and never printed.

The frontend origins and trusted proxy list are environment configuration, not hard-coded production assumptions.
