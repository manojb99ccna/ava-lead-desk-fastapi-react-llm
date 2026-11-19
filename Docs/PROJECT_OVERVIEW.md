# Ava AI Receptionist — Project Overview

> Context file for AI coding assistants. Read it before changing code.
> Product direction: this is the base of an **AI Lead Management & Follow-up SaaS**. Web chat
> exists today; WhatsApp and phone-call channels will reuse the same chat engine later.

## 1. What the project does

**Ava** is an AI receptionist for a business website (sample business: "WebeXcellence", a web
agency; all business data is editable in the admin panel). Customers chat with Ava to:

- ask about services, prices, opening hours and contact details (answers come only from verified data),
- book an appointment (date and time pickers), reschedule or cancel it (booking code + phone),
- leave their details as a lead (quote, callback),
- ask for a person (human handoff), complain, or follow up on an earlier request.

Staff use the admin dashboard (`/admin`) to manage appointments, handoffs, leads, customers,
conversations, FAQs, business info, opening hours, services and users.

**Hard constraint from the owner:** no paid AI APIs and no external AI services. The LLM runs
inside the backend process (PyTorch + Hugging Face `transformers`, open-weight Qwen2.5-Instruct).

## 2. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, React Router 6, Bootstrap 5.3 + Bootstrap Icons, plain JSX |
| Backend | Python 3.13, FastAPI, Uvicorn, Pydantic v2 |
| Database | MySQL 8, SQLAlchemy 2, Alembic migrations, PyMySQL |
| Auth | Argon2id (`argon2-cffi`), PyJWT HS256 with roles `admin` / `staff` |
| Intent model | scikit-learn: word (1-2) + char_wb (2-5) TF-IDF → LogisticRegression, 18 intents (incl. affirm/decline) |
| FAQ search | TF-IDF word + character n-grams, cosine similarity |
| LLM | `transformers` 5 + CPU PyTorch, default `Qwen/Qwen2.5-0.5B-Instruct`, tool calling via the Qwen chat template |
| Infra | Docker Compose (MySQL, phpMyAdmin, backend, frontend); `docker-compose.prod.yml` for nginx + non-reload backend |
| Tests | pytest + FastAPI TestClient, in-memory SQLite, scripted fake LLM |

Pinned versions: `backend/requirements*.txt`, `frontend/package.json`.

## 3. Folder structure

```
Ava_AI_Receptionist_LLM/
├── docker-compose.yml, docker-compose.prod.yml, README.md
├── Docs/PROJECT_OVERVIEW.md
├── backups/                       # manual DB dumps (git-ignored)
├── backend/
│   ├── Dockerfile                 # targets: dev (reload) / prod (non-root)
│   ├── requirements.txt, requirements-llm.txt, requirements-dev.txt
│   ├── .env / .env.example
│   ├── alembic.ini, migrations/versions/0001_baseline.py, 0002_receptionist_features.py
│   ├── seed/seed_data.json        # SAMPLE business data, loaded only into empty tables
│   ├── llm_models/hub/            # downloaded model weights (git-ignored, ~1-3 GB)
│   ├── logs/                      # redacted debug logs
│   ├── tests/                     # 82 tests
│   └── app/
│       ├── main.py                # app, lifespan (migrate → seed → start LLM), CORS, security headers, error handlers
│       ├── core/config.py         # all settings from env
│       ├── core/rate_limit.py     # in-memory per-IP sliding window
│       ├── database.py, models.py, auth.py, seed.py, db_migrate.py
│       ├── services/              # business logic, shared by API routes, rules engine and LLM tools
│       │   ├── appointment_service.py  # availability, book/reschedule/cancel, row lock, history, booking codes
│       │   ├── business_service.py     # settings, hours, services, local "now"
│       │   ├── chat_service.py         # handle_chat(): routing rules ↔ LLM, confirmations, persistence
│       │   ├── customer_service.py, lead_service.py (leads + handoffs), faq_service.py, validation.py
│       ├── ai/
│       │   ├── intent.py          # loads the intent model, classify() → (intent, confidence)
│       │   ├── rules_engine.py    # deterministic flows (booking, manage booking, lead, handoff) + answers
│       │   ├── agent.py           # LLM prompt (verified facts, 8-day calendar), tool loop, reply guard
│       │   ├── tools.py           # 10 tools, Pydantic-validated; action tools write the reply themselves
│       │   ├── llm_client.py      # LocalTransformersClient (background load, lock, timeout), parse <tool_call>
│       │   └── chat_types.py      # ChatTurn, ChatResult, state helpers
│       ├── ml/
│       │   ├── generate_intent_data.py   # ~63k synthetic examples (typos, Hinglish, WhatsApp style) → CSV and DB
│       │   ├── train_intent_model.py     # trains from DB table, evaluates, saves artifacts/intent_model.joblib
│       │   └── data/intent_eval.csv      # 68 hand-written evaluation messages
│       ├── routers/               # chat, public_appointments, admin (auth/users), appointments, customers,
│       │                          # leads, conversations, faqs, business, handoffs, dashboard
│       └── utils/logger.py        # redacts phones/e-mails before writing logs
└── frontend/
    ├── Dockerfile (dev / build / prod nginx), nginx.conf, vite.config.js
    └── src/
        ├── components/Chatbox.jsx + chatbox.css   # customer widget
        ├── components/admin/ui.jsx, shared.jsx    # shared admin UI + hooks (useLoader, useMutation, SlotPicker…)
        ├── layouts/AdminLayout.jsx                # responsive sidebar, role-aware menu, change password
        ├── pages/admin/                           # Dashboard, Appointments, Handoffs, Leads, Customers,
        │                                          # Conversations, Faqs, Business, Users, Login
        ├── routes/AppRoutes.jsx, ProtectedRoute.jsx
        ├── services/api.js (all API calls), auth.js
        └── utils/format.js
```

## 4. Runtime

| Service | Container | URL |
|---|---|---|
| Frontend (Vite dev) | `ava-llm-frontend` | http://localhost:5190 |
| Backend | `ava-llm-backend` | http://localhost:8410 (`/docs`) |
| phpMyAdmin | `ava-llm-phpmyadmin` | http://localhost:8420 |
| MySQL 8 | `ava-llm-db` | 127.0.0.1:3335, db `ava_ai` |

Separate from the original project (`DEMOS/Ava_AI_Receptionist`, containers `ava-ai-*`).
Compose project `ava-ai-llm`, network `ava-llm-net`, volume `ava-llm-db-data`.
Backend hot reload watches only `app/` and `migrations/`.

## 5. Chat pipeline (`services/chat_service.handle_chat`)

1. Conversation by `session_id` (server-generated UUID; unknown ids get a new conversation).
2. If `current_step` is set → `rules_engine` finishes the flow.
3. If a `pending_action` exists (LLM-prepared book/reschedule/cancel) → "yes" executes it in the
   backend, "no" drops it, anything else drops it and goes on.
4. Date picker click in LLM mode → slots returned directly; time click → turned into text for the LLM.
5. **Hybrid routing** (`LLM_MODE=hybrid`): the intent model answers when confident
   (≥ `LLM_ROUTE_CONFIDENCE`, ≤ `LLM_ROUTE_MAX_WORDS` words); otherwise the LLM. The LLM also
   continues when its previous reply was a question. `LLM_MODE=always` sends everything to the LLM.
6. LLM failure (not loaded, busy, timeout, empty, too many tool rounds) → rules engine.
7. Messages saved to `ava_messages`; `conversation.engine` = `llm` or `rules`.

Safety: action tools never let the LLM write the outcome; `_guard` replaces replies that claim
booked/cancelled or contain unknown `AVA-XXXXXX` codes; customer ownership = booking code + phone.

## 6. Database tables

`admins` (users: role, is_active, Argon2 hash), `ava_customers` (unique normalized phone),
`ava_conversations` (session_id, current_step, lead_data JSON state, status active/handoff/closed,
engine, channel web/whatsapp/voice, customer_id), `ava_messages`, `ava_leads` (+message, notes,
customer_id, conversation_id), `ava_appointments` (+booking_code unique, customer_id,
conversation_id, cancelled_at; statuses pending/confirmed/completed/cancelled/no_show),
`ava_appointment_history`, `ava_handoff_requests` (open/in_progress/resolved), `ava_business_faqs`,
`ava_services`, `ava_business_settings` (+name, description, contact, timezone, duration, window),
`ava_business_working_hours` (0 = Monday), `ava_sys_intents`, `ava_sys_intent_training_examples`
(+source manual/generated). Record timestamps (created_at/updated_at) are UTC via `db_types.UTCDateTime`; appointment times are business-local.

Migration 0002 is idempotent (checks before each change) because MySQL DDL is not transactional.

## 7. Configuration (`backend/.env`, see `.env.example`)

DB_*, JWT_SECRET (≥ 32 chars), JWT_EXPIRE_MINUTES, CORS_ORIGINS, ADMIN_USERNAME/PASSWORD (first user),
RATE_LIMIT_*_PER_MINUTE, LLM_PROVIDER (local|none), LLM_MODEL, LLM_DEVICE (auto|cpu|cuda),
LLM_CACHE_DIR, LLM_THREADS, LLM_MAX_NEW_TOKENS, LLM_TIMEOUT_SECONDS, LLM_TEMPERATURE,
LLM_HISTORY_MESSAGES, LLM_MODE, LLM_ROUTE_CONFIDENCE, LLM_ROUTE_MAX_WORDS, CHAT_DEBUG_LOGS,
RUN_MIGRATIONS_ON_STARTUP, SEED_ON_STARTUP. Frontend: VITE_API_URL (empty = same origin).

## 8. Measured performance (this dev machine: Docker 4 CPUs / 7.7 GB RAM, no GPU in Docker)

- Intent model: 95.9% on the 74 hand-written eval messages (templates were tuned after seeing
  misses, so expect ~90-95% on new real traffic); <10 ms per message.
- Qwen2.5-0.5B on CPU float32: 6-20 s per LLM call; bfloat16 on this CPU is ~0.5 tok/s (unusable).
  Qwen2.5-1.5B float32 needs ~6.5 GB RAM (did not fit next to other containers).
- 0.5B quality: good at extracting booking details; weak at choosing tools for simple questions
  (that is why hybrid routing exists).

## 9. Known limitations / next steps

- Small CPU model: slow and sometimes unhelpful; more Docker RAM/CPUs or the RTX GPU would allow 1.5B-3B.
- Rate limiter is per process (in memory).
- No automated e-mail/SMS/WhatsApp notifications yet; follow-ups are manual via the dashboard.
- WhatsApp needs Meta's WhatsApp Business Platform; phone calls need a telephony provider/SIP
  (speech-to-text and text-to-speech can run locally).
- No frontend unit tests; frontend is verified by `npm run build` and manual use.
