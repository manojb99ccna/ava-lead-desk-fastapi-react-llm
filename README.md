# Ava AI Receptionist

Ava is an AI receptionist for a business website. Customers chat with Ava to ask about services,
prices and opening hours, book, reschedule or cancel appointments, leave their contact details,
or ask for a person. Staff manage everything in an admin dashboard.

**Everything runs inside this project.** The language model runs in the backend process with
PyTorch. There is no API key, no paid AI service and no external AI server.

- Frontend: React 18, Vite 5, Bootstrap 5
- Backend: Python 3.13, FastAPI, SQLAlchemy 2, Alembic, MySQL 8
- AI: scikit-learn intent classifier, TF-IDF FAQ search, local LLM (Qwen2.5-Instruct via Hugging Face `transformers`)
- Security: Argon2id passwords, JWT with admin/staff roles, rate limiting, input validation

More detail for developers and AI tools: [Docs/PROJECT_OVERVIEW.md](Docs/PROJECT_OVERVIEW.md).

---

## 1. Quick start (Docker)

Requirements: Docker Desktop, about 4 GB free disk for images and 1–3 GB for the model.

```bash
cp backend/.env.example backend/.env      # then change the passwords and JWT_SECRET
cp frontend/.env.example frontend/.env
docker compose up -d --build
```

On first start the backend:
1. runs the database migrations (an existing database is upgraded, never recreated),
2. creates the first admin from `ADMIN_USERNAME` / `ADMIN_PASSWORD` if there are no users,
3. loads **sample** business data (settings, hours, services, FAQs, intents) into empty tables,
4. starts loading the local LLM in the background. Until it is ready, Ava answers with the rule-based engine.

| Service | URL |
|---|---|
| Website + chat widget | http://localhost:5190 |
| Admin dashboard | http://localhost:5190/admin |
| Backend API docs (Swagger) | http://localhost:8410/docs |
| phpMyAdmin | http://localhost:8420 |
| MySQL | `127.0.0.1:3335`, database `ava_ai` |

Default admin (development): `admin` / the `ADMIN_PASSWORD` in `backend/.env`.
**Edit the sample business data** in Admin → Business and Admin → FAQs.

### The local LLM

The model downloads automatically the first time (from Hugging Face, free, once) into
`backend/llm_models/`. After that it works offline. To download in advance:

```bash
docker compose exec backend python -c "from huggingface_hub import snapshot_download as d; d('Qwen/Qwen2.5-0.5B-Instruct', cache_dir='/app/llm_models/hub')"
```

| `LLM_MODEL` | RAM | Speed on 4 CPU cores | Quality |
|---|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct` (default) | ~2 GB | 10–20 s per LLM reply | basic |
| `Qwen/Qwen2.5-1.5B-Instruct` | ~6.5 GB | slower; needs more Docker RAM | better tool use |
| either, with an NVIDIA GPU (`LLM_DEVICE=cuda`) | GPU memory | 1–3 s | — |

`LLM_PROVIDER=none` turns the LLM off; Ava then uses only the rule-based engine.

---

## 2. How the AI works

```
customer message
   │
   ├─ step-by-step flow running? (booking, cancelling…) ──► rule engine finishes it
   ├─ waiting for "yes/no" to a booking/cancel/reschedule? ──► backend executes or drops it
   │
   ├─ intent model is confident and the message is short ──► rule engine (instant, verified data)
   └─ otherwise (unclear, or many details in one message) ──► local LLM with tools
                                                              └─ on timeout/error ► rule engine
```

- **Intent model** (`app/ml/`): word + character TF-IDF and logistic regression,
  trained on ~63,000 generated examples plus your own examples (18 intents, incl. yes/no). Handles typos and Hinglish.
- **FAQ search** (`services/faq_service.py`): word and character TF-IDF with cosine similarity.
- **LLM agent** (`app/ai/agent.py`): gets verified facts (business info, hours, services,
  matching FAQs) in its prompt and can call 10 tools. It never touches the database directly.
- **Tools** (`app/ai/tools.py`): `get_business_information`, `search_faq`, `get_services`,
  `get_business_hours`, `check_availability`, `book_appointment`, `reschedule_appointment`,
  `cancel_appointment`, `create_customer_lead`, `request_human_handoff`. Every argument is
  validated with Pydantic.
- **Safety rules:**
  - Booking, rescheduling and cancelling first store a pending action and show a summary. Only the
    customer's "yes" in the next message runs it, and the backend checks availability again.
  - Replies for actions are written by the backend, so Ava cannot claim a booking that failed.
  - A guard replaces LLM replies that claim "booked/cancelled" or mention unknown booking codes.
  - Reschedule and cancel need the **booking code and the phone number** of the booking.
  - Double booking is prevented with a row lock per weekday plus an overlap check.

Settings: `LLM_MODE=hybrid|always`, `LLM_ROUTE_CONFIDENCE`, `LLM_ROUTE_MAX_WORDS` in `backend/.env`.

### Retraining the intent model

Training examples live in the table `ava_sys_intent_training_examples`
(`source = 'generated'` or `'manual'`; manual examples count 3×).

```bash
docker compose exec backend python -m app.ml.generate_intent_data --per-intent 3500 --to-db
docker compose exec backend python -m app.ml.train_intent_model
```

Generating replaces only the `generated` rows. Training prints the accuracy on a hand-written
test set (`app/ml/data/intent_eval.csv`) and saves `app/ml/artifacts/intent_model.joblib`.
The backend picks up the new model after a restart.

---

## 3. Admin dashboard

Login at `/admin`. Roles:

| | admin | staff |
|---|---|---|
| Dashboard, appointments, customers, leads, conversations, handoffs | ✔ | ✔ |
| Change appointments, leads, handoffs | ✔ | ✔ |
| FAQs, business info, opening hours, services (edit) | ✔ | read only |
| Users, delete leads | ✔ | – |

Passwords are Argon2id hashes. Old MD5 hashes still work once and are upgraded at login.

---

## 4. API overview

Full, interactive documentation: http://localhost:8410/docs

| Area | Endpoints | Auth |
|---|---|---|
| Health | `GET /api/health` | – |
| Chat | `POST /api/chat`, `GET /api/chat/history?session_id=`, `POST /api/chat/end`, `GET /api/chat/info` | – (rate limited) |
| Public appointments | `GET /api/appointments/available-dates`, `GET /api/appointments/available-slots?selected_date=`, `POST /api/appointments`, `POST /api/appointments/lookup`, `POST /api/appointments/reschedule`, `POST /api/appointments/cancel` | booking code + phone |
| Auth & users | `POST /api/admin/login`, `GET /api/admin/me`, `POST /api/admin/me/password`, `GET/POST /api/admin/users`, `PATCH /api/admin/users/{id}` | Bearer |
| Dashboard | `GET /api/admin/dashboard` | staff |
| Appointments | `GET/POST /api/admin/appointments`, `GET/PATCH /api/admin/appointments/{id}`, `POST …/{id}/reschedule`, `POST …/{id}/cancel`, `GET …/availability` | staff |
| Customers | `GET /api/admin/customers`, `GET /api/admin/customers/{id}` | staff |
| Leads | `GET /api/admin/leads`, `PATCH /api/admin/leads/{id}`, `DELETE` (admin) | staff |
| Conversations | `GET /api/admin/conversations`, `GET …/{id}/messages` | staff |
| Handoffs | `GET /api/admin/handoffs`, `PATCH /api/admin/handoffs/{id}` | staff |
| FAQs | `GET /api/admin/faqs`, `GET /api/admin/faqs/search?q=`, `POST/PUT/DELETE` (admin) | staff |
| Business | `GET/PUT /api/admin/business/settings`, `GET/PUT …/hours`, `GET/POST/PUT/DELETE …/services` | staff / admin |

Chat request: `{"message": "...", "session_id": "...", "action": "select_date|select_time", "selected_date": "YYYY-MM-DD", "selected_time": "HH:MM"}`.
Chat response: `{"reply", "session_id", "ui_action", "data", "engine": "llm|rules"}`.

---

## 5. Tests

```bash
docker compose exec backend python -m pytest -q
docker compose exec frontend npm run build
```

The backend tests use an in-memory SQLite database and a scripted fake LLM, so they are fast
and need no model. They cover authentication and roles, appointments (availability, booking,
double booking, invalid input, reschedule, cancel, history), the rule-based chat flows, the
LLM tool loop (confirmation, guards, fallback when the LLM fails), FAQs, leads, handoffs,
business settings, the dashboard, rate limits and log redaction.

---

## 6. Database

- Migrations: Alembic (`backend/migrations/`). They run automatically on startup
  (`RUN_MIGRATIONS_ON_STARTUP=true`). Manually: `docker compose exec backend alembic upgrade head`.
- New migration after changing `app/models.py`:
  `docker compose exec backend alembic revision --autogenerate -m "describe change"`.
- Backup: `docker exec ava-llm-db mysqldump -uroot -p<root password> ava_ai > backup.sql`

---

## 7. Running without Docker

```bash
# MySQL 8 must be running; set DB_HOST=127.0.0.1 and the port in backend/.env
cd backend
python -m venv venv && venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0
pip install -r requirements-llm.txt
set LLM_CACHE_DIR=llm_models\hub
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npm run dev        # set VITE_API_URL=http://localhost:8000 in frontend/.env
```

---

## 8. Deployment

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production override builds the frontend as static files served by nginx on port 80 (nginx
also proxies `/api` to the backend), runs the backend without hot reload as a non-root user, and
stops publishing MySQL and phpMyAdmin.

Before going live:
- set strong `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD` (in `docker-compose.yml`), `JWT_SECRET` and `ADMIN_PASSWORD`;
- set `CORS_ORIGINS` to your real domain and put HTTPS in front (for example Caddy, Traefik or a cloud load balancer);
- replace the sample business data and FAQs;
- the rate limiter is in-memory per process; with several backend instances use a shared store.

---

## 9. Future channels (WhatsApp, phone)

`services/chat_service.handle_chat(db, session_id, turn, channel)` does not depend on the web
widget. Conversations have a `channel` column (`web`, `whatsapp`, `voice`).

- **WhatsApp:** requires Meta's WhatsApp Business Platform (Cloud API). A webhook route would map
  the sender's number to a session, call `handle_chat(..., channel="whatsapp")` and send the reply.
  Replies to customers who write first are free within 24 hours; outgoing follow-up templates are paid by Meta.
- **Phone calls:** need a telephony provider or SIP trunk to receive calls. Speech-to-text
  (e.g. Whisper) and text-to-speech (e.g. Piper) can run locally like the LLM.
