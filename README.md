# Ahenfor Engineering and Construction — Website & CMS

A Flask application that serves the public corporate website of Ahenfor Engineering and
Construction Limited and a private admin dashboard for managing its content: projects,
construction phases, dated progress updates with photos and video, the homepage hero,
news and events, services, awards, testimonials, contact details and inquiries.

**The developer controls the design; the administrator controls the content.** Admins
work with plain forms, tables and upload controls. They never edit layout, CSS, icons or
HTML.

---

## 1. Features

**Public website**
- Homepage with an image/video hero, verified statistics, about, services, featured
  projects, upcoming projects, testimonials, awards, news and events
- Project listing filtered by status and category. Each project page shows key facts,
  a manually reported progress %, the latest update, a phase-by-phase timeline with
  dated updates, a photo gallery with a lightbox, and related projects
- News and events, with upcoming and past events classified automatically (past
  events are kept, never deleted)
- Contact and Request a Quote forms with server validation, a honeypot, rate limiting,
  private attachments and email notification
- SEO: per-page titles and descriptions, Open Graph tags, canonical URLs,
  `sitemap.xml`, `robots.txt` and schema.org Organization data built only from
  configured details
- Accessibility: semantic HTML, skip link, keyboard navigation, visible focus states,
  alt text, and support for reduced motion

**Admin dashboard (`/admin/`)**
- Dashboard with counts and recent activity, all computed from the database
- Projects: create, edit, preview, publish/unpublish/archive and feature, with search,
  filters and pagination
- Progress manager: phases (7 suggested defaults or custom; reorder with arrows or
  drag; archive and restore) and dated updates with multi-photo upload (progress bars,
  captions, alt text, reorder, choose from library) and an optional video
- Homepage hero: draft, preview, then publish. Image or video, poster image,
  headline, and buttons limited to fixed destinations
- Media library: search, metadata editing, "where is this used", archive, and
  delete-only-when-unused
- News & events, Services, Awards & certifications, Testimonials (publishing requires
  recorded client approval)
- Inquiries: private list and detail view, status, internal notes, attachment download
- Settings: company copy, contact details, social links, statistics; password change

---

## 2. Technology stack

| Layer | Choice |
|---|---|
| Web framework | Flask 3 (application factory, Blueprints), Jinja2, vanilla JavaScript |
| Database | SQLite (`instance/ahenfor.db`, WAL mode) in development and production; PostgreSQL optional via `DATABASE_URL`. Flask-SQLAlchemy 3, Flask-Migrate/Alembic |
| Auth & forms | Flask-Login, Flask-WTF (CSRF), Werkzeug scrypt hashing, Flask-Limiter |
| Media | Storage interface with local, S3/S3-compatible (boto3) and Cloudinary backends; Pillow for validation and resizing |
| Email | Built-in SMTP backend behind an abstraction (console backend in development) |
| Server | Gunicorn behind Nginx |
| Tests | pytest (114 tests), run against SQLite and PostgreSQL 16 |

No React, Vue, Vite, TypeScript or Node server is used.

---

## 3. Directory structure

```
ahenfor-website/
├── app/
│   ├── __init__.py            # create_app(): config, extensions, blueprints, headers, error pages
│   ├── config.py              # Development / Testing / Production config + startup validation
│   ├── extensions.py          # db, migrate, login_manager, csrf, limiter
│   ├── models/                # SQLAlchemy models (one file per entity) + enums.py, base.py mixins
│   ├── public/                # Public blueprint: routes.py, forms.py
│   ├── admin/                 # Admin blueprint
│   │   ├── decorators.py      # Blueprint-wide login guard (no admin route can be left public)
│   │   ├── forms.py           # All admin forms
│   │   ├── helpers.py         # Media slots, pagination, safe redirects
│   │   ├── template_helpers.py
│   │   └── routes/            # auth, dashboard, projects, progress, media, content, inquiries, settings
│   ├── services/              # Business logic (routes stay thin)
│   │   ├── media_service.py   # Upload validation, image variants, UploadBatch, reference checks
│   │   ├── project_service.py # Public queries, timeline, phase ordering, dashboard stats
│   │   ├── publishing_service.py  # The single definition of "publicly visible"
│   │   ├── content_service.py # News/events/services/awards/testimonials queries
│   │   ├── settings_service.py# Editable settings registry + hero draft/publish
│   │   └── email_service.py   # console / smtp / memory backends
│   ├── storage/               # base.py (interface), local.py, s3.py, cloudinary_backend.py
│   ├── cli/                   # flask create-admin, set-password, seed-demo, check-config
│   ├── utils/                 # helpers (slugs, safe redirects, text→paragraphs), validators, icon map
│   ├── templates/             # base.html, partials/, public/, admin/, emails/, errors/
│   └── static/                # css/main.css, css/admin.css, js/*.js, images/
├── migrations/                # Alembic migrations (never edit the schema by hand)
├── tests/                     # pytest suite
├── deploy/                    # nginx.conf, ahenfor.service (systemd), backup.sh
├── requirements.txt / requirements-dev.txt
├── .env.example
└── run.py                     # WSGI entry point (gunicorn "run:app")
```

---

## 4. Database relationships

```
AdminUser 1───* MediaAsset (uploaded_by)

Project 1───* ProjectPhase 1───* ProgressUpdate 1───* ProgressUpdateMedia *───1 MediaAsset
   │                                   └── video_id ──────────────────────────────▶ MediaAsset
   ├── cover_image_id ───────────────────────────────────────────────────────────▶ MediaAsset
   └── cover_video_id ───────────────────────────────────────────────────────────▶ MediaAsset

ContentPost (news + events) ── cover_image_id / video_id ──▶ MediaAsset
Service ── image_id ──▶ MediaAsset
Award ── image_id / document_id ──▶ MediaAsset
Testimonial ── portrait_id ──▶ MediaAsset ;  project_id ──▶ Project
Inquiry ── attachment_id ──▶ MediaAsset (private)
HeroConfig (rows: "draft", "published") ── image_id / video_id / poster_id ──▶ MediaAsset
SiteSetting (key/value; keys defined in settings_service.REGISTRY)
```

Key rules:
- **Publication status** (`draft` / `published` / `archived`) is a separate column from
  **project status** (`upcoming` / `ongoing` / `on_hold` / `completed`).
- Public pages show a progress update only when the update, its phase and its project
  are all published and the phase is not archived (`publishing_service`).
- Galleries live in an association table (`progress_update_media`) with position,
  caption and alt text per link. They are never comma-separated URLs.
- Media foreign keys are `RESTRICT`, and `media_service.purge()` refuses to delete an
  asset that is still referenced anywhere. Removing a photo from an update deletes only
  the link, never the file.
- Event past/upcoming status is computed from `coalesce(ends_at, starts_at)` at query
  time, so it is never stored and cannot go stale.
- All datetimes are stored as UTC (Ghana is UTC+0).

---

## 5. Prerequisites

- Python 3.11+ (developed and tested on 3.13)
- Nothing extra for the database: SQLite ships with Python. (PostgreSQL 14+ is supported if the site ever outgrows SQLite.)
- Optional: an S3-compatible bucket or a Cloudinary account, an SMTP mailbox, and Redis
  (shared rate limits across Gunicorn workers)

---

## 6–9. Local installation

```bash
git clone <repo-url> ahenfor-website && cd ahenfor-website

# Virtual environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# Dependencies (dev includes pytest)
pip install -r requirements-dev.txt

# Environment
cp .env.example .env
# Edit .env: keep FLASK_CONFIG=development and leave DATABASE_URL blank (SQLite).
```

## 10. Environment configuration

Every setting is listed with comments in `.env.example`. The important ones are:

| Variable | Purpose |
|---|---|
| `FLASK_CONFIG` | `development` or `production`. **Defaults to production**, which refuses to start with unsafe settings. |
| `SECRET_KEY` | 32+ random characters: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Leave **blank** for SQLite at `instance/ahenfor.db`. Optional: a `postgresql://...` URL |
| `SITE_URL` | Public base URL, used for canonical links, the sitemap and email links |
| `ALLOWED_HOSTS` | Comma-separated host names (Flask `TRUSTED_HOSTS`) |
| `PROXY_FIX_HOPS` | `1` behind Nginx or Render, so HTTPS and client IPs are detected correctly |
| `MEDIA_STORAGE_PROVIDER` | `local`, `s3` or `cloudinary` |
| `MAIL_BACKEND` | `console` (logs only, sends nothing) or `smtp` |
| `RATELIMIT_STORAGE_URI` | `memory://` or `redis://localhost:6379/0` |

Run `flask --app run.py check-config` to print the active configuration. Secrets are
never printed.

## 11–12. Database setup and migrations

```bash
# SQLite (default: instance/ahenfor.db when DATABASE_URL is blank)
flask --app run.py db upgrade

# Optional PostgreSQL instead: create a database and set DATABASE_URL=postgresql://... in .env, then
flask --app run.py db upgrade
```

After changing a model:

```bash
flask --app run.py db migrate -m "Describe the change"
# Review the generated file in migrations/versions/ before applying it
flask --app run.py db upgrade
```

The app never creates, drops or resets tables at startup, and `db.create_all()` is
used only inside tests. `tests/test_migrations.py` checks that the migrations produce
exactly the schema the models describe.

## 13. Creating the first administrator

There is no public sign-up and there are no default credentials.

```bash
flask --app run.py create-admin            # prompts for email, name, password (min 12 chars)
flask --app run.py set-password            # reset a forgotten password (signs out existing sessions)
```

## 14. Running the application

```bash
flask --app run.py run --debug             # http://127.0.0.1:5000  — admin at /admin/login

# Optional: clearly labelled sample content for development
flask --app run.py seed-demo               # 5 sample projects with phases, updates and placeholder photos
flask --app run.py seed-demo --clear       # remove all sample content and its files
```

While any sample record is published, the site shows a "Sample content" notice. The
seed never creates awards, testimonials, client names or statistics, because those
must be real.

## 15. Running tests

```bash
pytest                                      # SQLite in a temp folder
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/ahenfor_test pytest   # PostgreSQL
```

`TEST_DATABASE_URL` must point to a **throwaway** database, because every test drops
and recreates all tables. Never point it at production.

The suite covers authentication, rate limiting, CSRF, authorization, project
workflows A–G from the specification, phases and updates, upload validation (spoofed
types, SVG, PHP, oversize files, path traversal), storage and database failure
cleanup, shared-media protection, hero draft/publish, event classification, private
inquiries, XSS escaping, security headers and migrations.

## 16. Media storage configuration

Every backend stores objects under generated keys of the form
`public|private/<kind>/<yyyy>/<mm>/<uuid>.<ext>`. The browser's filename is never used
as a path. Images are verified with Pillow, auto-rotated, stripped of EXIF data
(including GPS), capped at 2400 px, and given an 800 px thumbnail. Videos and PDFs are
checked by their file signature. Default limits are 10 MB per image, 100 MB per video
and 15 MB per document (see `.env`).

**Local (`MEDIA_STORAGE_PROVIDER=local`)** writes to `LOCAL_MEDIA_ROOT` (default
`instance/uploads`). Local storage is **not durable** on platforms with ephemeral
disks such as Render or Heroku. On a VPS it is acceptable only with backups: set
make sure the upload folder is in your backups, and let Nginx serve `/media/public/`
(see `deploy/nginx.conf`). Never expose the `private/` folder.

**S3 or S3-compatible (`s3`)**:
1. Create a bucket and an access key limited to that bucket.
2. Allow public `GET` on the `public/*` prefix only (bucket policy or a public custom
   domain), and keep `private/*` private.
3. Set `AWS_S3_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.
   For Cloudflare R2 or DigitalOcean Spaces, also set `S3_ENDPOINT_URL` and
   `MEDIA_PUBLIC_BASE_URL` (the public URL that serves the bucket).

Private files such as inquiry attachments are served through `/admin/media/<id>/file`,
which redirects to a 5-minute presigned URL.

**Cloudinary (`cloudinary`)**: run `pip install cloudinary` and set the three
`CLOUDINARY_*` variables. Private assets use Cloudinary's `authenticated` delivery
type with signed URLs.

> The S3 and Cloudinary adapters are implemented against the providers' SDKs but have
> **not yet been exercised against live accounts**. Upload one image, one video and
> one PDF on staging before launch.

## 17. Email configuration

```
MAIL_BACKEND=smtp
MAIL_SERVER=smtp.zoho.com          # or smtp.gmail.com (needs an app password), Brevo, etc.
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=website@ahenfor.com
MAIL_PASSWORD=...
MAIL_DEFAULT_SENDER=website@ahenfor.com
```

Set the recipient in **Admin › Company & contact › Contact details › Send new inquiries
to**, or with `INQUIRY_NOTIFY_EMAIL` as a fallback. An inquiry is always saved first.
The admin inquiry page shows whether a notification was actually delivered, and
`notified_at` is set only when the SMTP server accepts the message. With
`MAIL_BACKEND=console`, nothing is sent and a warning is logged.

## 18. Production deployment (Ubuntu VPS)

```bash
# 1. System packages
sudo apt install python3-venv nginx certbot python3-certbot-nginx
sudo adduser --system --group --home /srv/ahenfor ahenfor

# 2. Code and environment
sudo -u ahenfor git clone <repo-url> /srv/ahenfor/app && cd /srv/ahenfor/app
sudo -u ahenfor python3 -m venv .venv && sudo -u ahenfor .venv/bin/pip install -r requirements.txt
sudo -u ahenfor cp .env.example .env     # FLASK_CONFIG=production, SECRET_KEY, DATABASE_URL blank (SQLite),
                                         # SITE_URL=https://ahenfor.com, ALLOWED_HOSTS, PROXY_FIX_HOPS=1, ...
sudo chmod 600 .env

# 3. Database and first admin
sudo -u ahenfor .venv/bin/flask --app run.py db upgrade
sudo -u ahenfor .venv/bin/flask --app run.py create-admin

# 4. Gunicorn service and Nginx
sudo cp deploy/ahenfor.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now ahenfor
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ahenfor     # edit the domain first
sudo ln -s /etc/nginx/sites-available/ahenfor /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx

# 5. HTTPS
sudo certbot --nginx -d ahenfor.com -d www.ahenfor.com
```

Never run `flask run` in production. The service runs **one Gunicorn worker with 8
threads**, which suits SQLite (one writer) and keeps login rate limits in a single
process. If you later add workers, set `RATELIMIT_STORAGE_URI=redis://localhost:6379/0`
(and `pip install redis`).

**Render**: use the start command `gunicorn "run:app" --workers 2 --timeout 300` and the
build command `pip install -r requirements.txt && flask --app run.py db upgrade`. Attach
a Render PostgreSQL database and use **S3/R2 or Cloudinary** for media, because Render
disks are ephemeral.

**Updating safely**

```bash
cd /srv/ahenfor/app && ./deploy/backup.sh          # back up first
sudo -u ahenfor git pull
sudo -u ahenfor .venv/bin/pip install -r requirements.txt
sudo -u ahenfor .venv/bin/flask --app run.py db upgrade
sudo systemctl restart ahenfor
```

## 19. Backup and recovery

`deploy/backup.sh` takes a consistent online copy of the SQLite database (or `pg_dump` for PostgreSQL) and, for local storage, archives the
upload folder. It keeps 14 days of backups. Schedule it with cron, and **copy the
backups off the server**.

```bash
# Restore the database
sudo systemctl stop ahenfor
cp /srv/ahenfor/backups/db-YYYYMMDD-HHMMSS.sqlite3 /srv/ahenfor/app/instance/ahenfor.db
rm -f /srv/ahenfor/app/instance/ahenfor.db-wal /srv/ahenfor/app/instance/ahenfor.db-shm
sudo systemctl start ahenfor
# (PostgreSQL installs: pg_restore --clean --no-owner --dbname="$DATABASE_URL" db-....dump)
# Restore local media
tar -xzf /srv/ahenfor/backups/media-YYYYMMDD-HHMMSS.tar.gz -C /srv/ahenfor/
```

For S3 or R2, enable bucket versioning (or replication). For Cloudinary, enable its
backup option. The database stores only metadata and keys, so restore the database
and the media from backups taken at the same time.

## 20. Troubleshooting

| Symptom | Fix |
|---|---|
| `Production configuration is incomplete` on start | Read the listed items. Set `FLASK_CONFIG=development` for local work. |
| `Unknown FLASK_CONFIG` | Use `development` or `production`. |
| "Session expired" when submitting a form | The CSRF token expired with the session. Reload the page and resubmit. |
| Uploads fail with 413 | Raise `MAX_REQUEST_MB` **and** Nginx `client_max_body_size`. |
| Large video uploads time out | Raise Gunicorn `--timeout` and Nginx `proxy_read_timeout`, or use shorter clips. |
| Images 404 in production with local storage | Check that `LOCAL_MEDIA_ROOT` matches the Nginx `/media/public/` alias. |
| Inquiry saved but no email | `MAIL_BACKEND` is `console`, or the recipient isn't set (Settings › Contact details). Check the logs. |
| Too many login attempts | Wait a few minutes (5 per minute and 20 per hour per IP). |
| HTTPS links or client IPs wrong behind a proxy | Set `PROXY_FIX_HOPS=1`. |
| A model change isn't applied | Run `flask db migrate`, review the file, then `flask db upgrade`. |

---

## Notes for maintainers

- **Adding an editable setting**: add a `SettingDef` to
  `app/services/settings_service.py`. It appears in Admin › Settings automatically.
  Read it in templates with `site.<key>`.
- **Adding a service icon**: add a `<symbol>` to `templates/partials/icons.html` and a
  keyword rule to `app/utils/icons.py`.
- **Logo**: drop `logo.svg` (or `logo.png`) into `app/static/images/`. The header,
  footer and structured data use it automatically instead of the text wordmark.
- **Content that must be confirmed before launch**: the privacy policy text, the
  proposed services list, the default homepage copy, and all sample content.
- **Not yet implemented**: direct-to-bucket uploads for very large videos (uploads
  currently pass through Gunicorn), video duration extraction (needs ffprobe), and
  multiple admin roles (the decorator structure is ready for an "editor" role).
