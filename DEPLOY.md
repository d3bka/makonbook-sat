# Student goal v32 deployment note

This build includes migration `sat.0030_student_goal_v32_qs_top_200`. Do not deploy only the static files. Apply migrations before testing the goal form:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

The migration adds QS ranking fields, allows a missing SAT average, and seeds the top-200 university catalogue.

---

# Cutover: makonbook-sat-main → production on makonbook.uz

This stack replaces `makonbook-old` as production. It ships the **complete edge** — web,
telegram-bot, nginx and certbot — and its nginx also serves **sat-makon.uz** by proxying to the
`sat-makon-site` container, exactly as the outgoing stack does.

```
                    :80/:443
Internet ──▶ makonbook-nginx ──┬─▶ web:8000            makonbook.uz, www.makonbook.uz
                   │           └─▶ sat-makon-site:80   sat-makon.uz, www.sat-makon.uz
                   │
             makonbook-certbot ── one SAN cert, 4 names, renews every 12h
```

`sat-makon-site` runs in its own Compose project and stays up throughout — only the edge in
front of it changes. The shared `db` container is likewise untouched.

Because the old edge is torn down, **both sites go down for the length of steps 6–7.** Steps 1–5
all run while the old stack is still serving, so if the image is pre-pulled the window is well
under a minute.

---

## Read this first

**`ALLOWED_HOSTS` must be added to the production `.env`.** The live
`/opt/sat-makon/makonbook-old/.env` has no such line. `.dockerignore` excludes `.env` from the
image, so the container's only env source is that file, and `settings.py:37-40` then falls back
to `127.0.0.1,localhost,makonbook.satmakon.com`. The currently running image tolerates this — it
was built from source predating this tree. **An image built from this tree will not.** Without
the line, every request to makonbook.uz returns HTTP 400 `DisallowedHost`.

```
ALLOWED_HOSTS=makonbook.uz,www.makonbook.uz,127.0.0.1,localhost
```

`CSRF_TRUSTED_ORIGINS` is already present and correct; this is its missing sibling.

Two smaller notes on the same file:

- **`DATABASE_URL` wins over every `DB_*` variable** (`settings.py:151-155`), and the live `.env`
  sets it. Editing `DB_NAME` or `DB_HOST` there has no effect unless you also change the URL.
- `sat-makon.uz` is **not** a Django host — it is served straight from the static container — so
  it does not belong in `ALLOWED_HOSTS`.

---

## Cutover

### 1. Preserve makonbook-new's image

`nazacd/makonbook:latest` is currently makonbook-new's image (it is `APP_IMAGE` in that project's
`.env`). This cutover overwrites that tag, so save it first or lose the rollback path to that
codebase:

```bash
docker pull nazacd/makonbook:latest
docker tag  nazacd/makonbook:latest nazacd/makonbook:new-rollback
docker push nazacd/makonbook:new-rollback
```

### 2. Preserve makonbook-new's bundle on the VPS

`/opt/sat-makon/makonbook/` holds makonbook-new's compose file, `.env` and nginx config. Move it
aside rather than overwriting:

```bash
mv /opt/sat-makon/makonbook /opt/sat-makon/makonbook-new-bundle
mkdir -p /opt/sat-makon/makonbook/nginx
```

### 3. Build and push

The dated tag makes this cutover itself reversible:

```bash
docker build -t nazacd/makonbook:latest -t nazacd/makonbook:sat-20260719 .
docker push nazacd/makonbook:latest
docker push nazacd/makonbook:sat-20260719
```

### 4. Copy the certificate into the new volume

The cert lives in `makonbook-old_certbot_conf`. Compose volumes are project-scoped, so the new
`makonbook` project looks for `makonbook_certbot_conf` — copy rather than re-issue, and both the
Let's Encrypt rate limit and the cold-start bootstrap are avoided entirely.

`cp -a` is required: `live/` is a tree of symlinks into `archive/`, and a plain copy flattens
them, which breaks renewal.

```bash
docker volume create makonbook_certbot_conf
docker run --rm -v makonbook-old_certbot_conf:/from:ro -v makonbook_certbot_conf:/to \
  alpine sh -c 'cd /from && cp -a . /to/'
```

**Verify the copy — do not trust its exit code.** `docker run -v name:/path` silently *creates*
an empty volume when `name` does not exist, so a mistyped source reports success and produces
nothing. nginx would then fail to start on a missing certificate, mid-cutover:

```bash
docker run --rm -v makonbook_certbot_conf:/c:ro alpine ls -l /c/live/makonbook.uz/
```

Expect four **symlinks** — `cert.pem`, `chain.pem`, `fullchain.pem`, `privkey.pem` — pointing
into `../../archive/makonbook.uz/`. Regular files instead of symlinks means `-a` did not take:
nginx will start now but renewal breaks later.

`media_files` is **not** copied — verified empty on 2026-07-19, since uploads go to Cloudflare R2
(`apps/sat/storages.py:14-16`). `static_files` is not copied either; `collectstatic` regenerates
it on start.

### 5. Stage the bundle and pre-pull

```bash
# from this repo
scp docker-compose.prod.yml root@188.245.175.83:/opt/sat-makon/makonbook/docker-compose.yml
scp nginx/default.conf      root@188.245.175.83:/opt/sat-makon/makonbook/nginx/default.conf
scp init-letsencrypt.sh     root@188.245.175.83:/opt/sat-makon/makonbook/
```

Ship the production env file. **It must land named `.env`** — the compose file's
`env_file: .env` reads that name from the deploy directory:

```bash
scp .env.production root@188.245.175.83:/opt/sat-makon/makonbook/.env
```

Do **not** copy the repo's `.env` — that is the dev template (`DEBUG=True`, `ALLOWED_HOSTS`
pointing at `makonbook.satmakon.com`, `DB_HOST` set to the VPS public IP, and a different
`SECRET_KEY` that would log out every user). `.env.production` is that file with those five
corrections applied; the reasons are marked `[CHANGED]` inline. Transfer over `scp` only.

```bash
# on the VPS — pull now so step 7 has nothing to download
cd /opt/sat-makon/makonbook && docker compose pull
```

### 6. Stop the old stack — downtime begins

```bash
cd /opt/sat-makon/makonbook-old && docker compose down
```

**Never add `-v`.** That would delete `makonbook-old_certbot_conf` and every other old volume,
destroying the rollback path and the original certificate.

### 7. Start the new stack — downtime ends

```bash
cd /opt/sat-makon/makonbook && docker compose up -d
```

`RUN_MIGRATIONS=1` on `web`, so migrations apply on boot. Watch them land:

```bash
docker logs -f makonbook-web
```

### 8. Re-point the DNS record for dev (optional housekeeping)

`dev.makonbook.uz` still has an A record pointing at this VPS but nothing serves it — it will hit
the `_` default_server block and get `444`. Harmless; remove the record if you want it tidy.

---

## Rollback

The old directory and all `makonbook-old_*` volumes are intact, so returning to the current
production state takes about as long as the cutover did:

```bash
cd /opt/sat-makon/makonbook     && docker compose down
cd /opt/sat-makon/makonbook-old && docker compose up -d
```

Keep `/opt/sat-makon/makonbook-old/` and its volumes until the new stack has run cleanly for
several days.

---

## Afterwards

**Renewals are automatic** — `makonbook-certbot` attempts renewal every 12h and no-ops until the
cert is inside its renewal window; `makonbook-nginx` reloads every 6h to pick up a renewed cert.
Nothing to schedule.

**Updating code later:**

```bash
docker build -t nazacd/makonbook:latest .
docker push nazacd/makonbook:latest
# on the VPS
cd /opt/sat-makon/makonbook && docker compose pull && docker compose up -d
```

**If the certificate ever has to be rebuilt from nothing**, `init-letsencrypt.sh` does the
self-signed bootstrap dance. It requests all four names against the `makonbook.uz` lineage with
an ECDSA key. Certbot *replaces* a lineage's name set rather than appending, so any name dropped
from `LETSENCRYPT_DOMAINS` loses its TLS — which is exactly how an earlier version of that script
would have silently broken sat-makon.uz.

## Files

| File | Role |
|---|---|
| `docker-compose.prod.yml` | full stack; `name: makonbook` pins the project so volumes resolve to `makonbook_*` |
| `nginx/default.conf` | edge config for both makonbook.uz and sat-makon.uz |
| `nginx/letsencrypt-bootstrap.conf` | temporary HTTP-only config, cold-start cert rebuild only |
| `init-letsencrypt.sh` | cold-start cert rebuild; not needed for this cutover |
