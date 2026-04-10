# Listojo Security Guide

## 1) Production security baseline

Set these env vars before running in production:

```bash
export DJANGO_DEBUG=false
export DJANGO_SECRET_KEY='a-long-random-secret'
export DJANGO_ALLOWED_HOSTS='listojo.com,www.listojo.com'
export DJANGO_CSRF_TRUSTED_ORIGINS='https://listojo.com,https://www.listojo.com'
```

When `DJANGO_DEBUG=false`, the app enables:
- HTTPS redirect
- Secure & HttpOnly cookies
- HSTS
- content-type sniff protection
- clickjacking protection (`X-Frame-Options: DENY`)

## 2) Authentication hardening

- Keep strong password validators enabled (already configured).
- Add email verification + optional 2FA for real production.
- Rate-limit login and registration endpoints (Django Axes / reverse proxy limits).

## 3) Data encryption and protection

- **In transit:** always serve via HTTPS (TLS certificates).
- **At rest:** use encrypted disks/volumes and encrypted backups.
- Use a managed production database (PostgreSQL) with encrypted storage and PITR backups.
- Never commit secrets or `.env` files to git.

## 4) Intrusion resistance

- Put app behind a reverse proxy (Nginx/Caddy) and WAF/CDN.
- Restrict admin URL access by IP and enforce strong admin passwords.
- Keep dependencies patched and run regular vulnerability scans.
- Enable centralized logs + alerts for suspicious login bursts.

## 5) Operational checklist

- [ ] `DJANGO_DEBUG=false`
- [ ] Strong unique `DJANGO_SECRET_KEY`
- [ ] HTTPS enabled
- [ ] Daily encrypted backups tested for restore
- [ ] Security updates cadence defined
