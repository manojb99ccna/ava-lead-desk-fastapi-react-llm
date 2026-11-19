# Ava AI Receptionist — Libraries and Flowcharts

Every library is open source and runs inside this project. No paid API or external AI service is used.
Diagrams use Mermaid: they render on GitHub, and in VS Code with a Mermaid preview extension.

---

## 1. Libraries

### Backend: web API and database (`backend/requirements.txt`)

| Library | Version | Used for |
|---|---|---|
| fastapi | 0.162.0 | REST API, routing, request validation, Swagger docs (`/docs`) |
| uvicorn[standard] | 0.54.0 | ASGI server that runs FastAPI (hot reload in development) |
| pydantic | 2.14.3 | Validating request bodies and LLM tool arguments |
| sqlalchemy | 2.1.8 | ORM: models, queries, transactions, row locking |
| alembic | 1.20.1 | Database migrations (`backend/migrations/`) |
| pymysql | 1.2.3 | MySQL driver used by SQLAlchemy |
| cryptography | 50.0.2 | Needed by PyMySQL for MySQL 8 authentication |
| python-dotenv | 1.2.4 | Loads `backend/.env` |
| pyjwt | 2.15.1 | Admin login tokens (HS256, with expiry) |
| argon2-cffi | 25.1.0 | Argon2id password hashing |
| tzdata | 2026.6 | Time-zone data (needed when running on Windows) |

### Backend: machine learning (`backend/requirements.txt`)

| Library | Version | Used for |
|---|---|---|
| scikit-learn | 1.9.1 | Intent classifier (TF-IDF + LogisticRegression) and FAQ search (TF-IDF + cosine similarity) |
| joblib | 1.6.0 | Saving and loading the trained intent model (`intent_model.joblib`) |
| numpy, scipy | (installed by scikit-learn) | Maths behind scikit-learn |

### Backend: local LLM (`backend/requirements-llm.txt`)

| Library | Version | Used for |
|---|---|---|
| torch (CPU build) | 2.15.0 | Runs the neural network (installed from the PyTorch CPU index) |
| transformers | 5.22.2 | Loads Qwen2.5-Instruct, builds the chat prompt with tools, generates replies |
| accelerate | 1.15.0 | Memory-efficient model loading |
| huggingface_hub, tokenizers, safetensors | (installed by transformers) | One-time model download, tokenizer, weight files |

Model: **Qwen/Qwen2.5-0.5B-Instruct** (Apache-2.0), stored in `backend/llm_models/hub/`.

### Backend: tests (`backend/requirements-dev.txt`)

| Library | Version | Used for |
|---|---|---|
| pytest | 9.2.0 | Test runner (82 tests) |
| httpx | 0.28.1 | HTTP client used by FastAPI's TestClient |

### Frontend (`frontend/package.json`, installed versions)

| Library | Version | Used for |
|---|---|---|
| react, react-dom | 18.3.1 | User interface |
| react-router-dom | 6.30.6 | Pages and routes (`/`, `/admin/...`) |
| bootstrap | 5.3.8 | Layout, styling, responsive design |
| bootstrap-icons | 1.13.1 | Icons |
| vite | 5.4.21 | Dev server, `/api` proxy, production build |
| @vitejs/plugin-react | 4.7.0 | JSX support in Vite |

### Infrastructure (Docker images)

| Image | Used for |
|---|---|
| python:3.13-slim | Backend container |
| node:22-alpine | Frontend dev server and build |
| nginx:1.27-alpine | Production: serves the built frontend, proxies `/api` |
| mysql:8.0 | Database |
| phpmyadmin:latest | Database admin tool (development) |

---

## 2. System overview

```mermaid
flowchart LR
    subgraph Browser
        W["Chat widget<br/>React + Bootstrap"]
        A["Admin dashboard<br/>React Router + Bootstrap"]
    end

    subgraph Frontend["Frontend container (Vite dev / nginx prod)"]
        P["/api proxy"]
    end

    subgraph Backend["Backend container: FastAPI + Uvicorn"]
        R["Routers<br/>/api/chat, /api/appointments, /api/admin/*"]
        S["Services<br/>appointments, FAQ, leads, customers, business"]
        AI["AI layer<br/>rules engine, intent model, LLM agent, tools"]
        AU["Auth<br/>PyJWT + argon2-cffi"]
        RL["Rate limiter"]
    end

    DB[("MySQL 8<br/>SQLAlchemy + PyMySQL<br/>Alembic migrations")]
    M[["Local LLM files<br/>backend/llm_models<br/>torch + transformers"]]
    J[["Intent model<br/>intent_model.joblib<br/>scikit-learn"]]

    W -->|"POST /api/chat"| R
    A -->|"/api/admin/* with Bearer token"| P --> R
    R --> RL
    R --> AU
    R --> S
    R --> AI
    AI --> S
    AI --> J
    AI --> M
    S --> DB
    AU --> DB
```

---

## 3. Chat message flow (`POST /api/chat`)

```mermaid
flowchart TD
    U(["Customer sends a message<br/>Chatbox.jsx → services/api.js sendChat()"]) --> API["POST /api/chat<br/>FastAPI + Pydantic validation"]
    API --> RL{"Rate limit OK?<br/>30 per minute per IP"}
    RL -- no --> E429["429 Too many requests"]
    RL -- yes --> CONV["Find or create conversation<br/>server-generated session_id<br/>SQLAlchemy"]

    CONV --> STEP{"Step-by-step flow running?<br/>booking, cancel, lead, handoff"}
    STEP -- yes --> RULES["Rules engine finishes the flow<br/>rules_engine.py"]

    STEP -- no --> PEND{"Waiting for yes/no<br/>to a prepared action?"}
    PEND -- "yes" --> EXEC["Backend executes the action<br/>tools.run_pending_action()"]
    PEND -- "no" --> DROP["Drop the action"]
    PEND -- "nothing pending" --> ROUTE{"Hybrid router<br/>intent model confident<br/>and message short?<br/>scikit-learn"}

    ROUTE -- yes --> RULES
    ROUTE -- "no: unclear or many details" --> READY{"LLM loaded?"}
    READY -- no --> RULES
    READY -- yes --> AGENT["LLM agent<br/>agent.py<br/>torch + transformers"]
    AGENT -- "timeout or error" --> RULES
    AGENT --> REPLY

    RULES --> REPLY["Reply + optional date/time pickers"]
    EXEC --> REPLY
    DROP --> REPLY
    REPLY --> SAVE[("Save both messages<br/>ava_messages")]
    SAVE --> OUT(["JSON: reply, session_id, ui_action, data, engine"])
```

---

## 4. LLM agent and tools

```mermaid
flowchart TD
    IN["Customer message"] --> PROMPT["Build prompt<br/>verified business facts, opening hours,<br/>services, matching FAQs, 8-day calendar,<br/>last 10 messages"]
    PROMPT --> GEN["Generate with Qwen2.5<br/>transformers apply_chat_template + generate"]
    GEN --> PARSE{"Reply contains<br/>a tool call?"}

    PARSE -- no --> GUARD{"Guard: claims 'booked'<br/>or an unknown booking code?"}
    GUARD -- yes --> SAFE["Replace with a safe reply"]
    GUARD -- no --> TEXT["Send the LLM text"]

    PARSE -- yes --> VAL["Validate arguments<br/>Pydantic"]
    VAL --> KIND{"Tool type"}

    KIND -- "information" --> INFO["get_business_information<br/>search_faq<br/>get_services<br/>get_business_hours"]
    INFO -->|"result back to the model"| GEN

    KIND -- "action" --> ACT["check_availability<br/>book_appointment<br/>reschedule_appointment<br/>cancel_appointment<br/>create_customer_lead<br/>request_human_handoff"]
    ACT --> BACK["Backend service runs it<br/>and writes the reply itself"]
    BACK --> CONF["Book / reschedule / cancel:<br/>store pending action + summary,<br/>customer must answer yes next"]
```

---

## 5. Appointment booking (with double-booking protection)

```mermaid
sequenceDiagram
    actor C as Customer
    participant W as Chat widget (React)
    participant API as FastAPI /api/chat
    participant AS as appointment_service
    participant DB as MySQL (SQLAlchemy)

    C->>W: "Book a website design consultation"
    W->>API: POST /api/chat
    API->>AS: available_dates()
    AS->>DB: working hours + existing appointments
    API-->>W: ui_action = select_date
    C->>W: picks a date
    W->>API: POST /api/chat (action select_date)
    API->>AS: available_slots(date)
    API-->>W: ui_action = select_time
    C->>W: picks a time
    W->>API: POST /api/chat (action select_time)
    API-->>W: "Please confirm... reply yes"
    C->>W: "yes"
    W->>API: POST /api/chat
    API->>AS: book_appointment()
    AS->>DB: SELECT ... FOR UPDATE (lock that weekday)
    AS->>DB: check overlaps, insert appointment + history
    DB-->>AS: ok
    API-->>W: "Booking code: AVA-XXXXXX"
```

---

## 6. API map

```mermaid
flowchart LR
    subgraph Public["Public (no login, rate limited)"]
        H["GET /api/health"]
        C1["POST /api/chat"]
        C2["GET /api/chat/history"]
        C3["POST /api/chat/end"]
        C4["GET /api/chat/info"]
        P1["GET /api/appointments/available-dates"]
        P2["GET /api/appointments/available-slots"]
        P3["POST /api/appointments"]
        P4["POST /api/appointments/lookup<br/>reschedule / cancel<br/>(booking code + phone)"]
    end

    subgraph Auth["Login"]
        L1["POST /api/admin/login"]
        L2["GET /api/admin/me"]
        L3["POST /api/admin/me/password"]
    end

    subgraph Staff["Staff and admin (Bearer token)"]
        D["GET /api/admin/dashboard"]
        AP["/api/admin/appointments<br/>list, create, update, reschedule, cancel"]
        CU["/api/admin/customers"]
        LE["/api/admin/leads"]
        CO["/api/admin/conversations"]
        HO["/api/admin/handoffs"]
        FQ["GET /api/admin/faqs (+ search)"]
        BI["GET /api/admin/business/*"]
    end

    subgraph AdminOnly["Admin only"]
        U["/api/admin/users"]
        FW["POST/PUT/DELETE /api/admin/faqs"]
        BW["PUT/POST/DELETE /api/admin/business/*"]
        LD["DELETE /api/admin/leads/{id}"]
    end

    L1 -->|"JWT (PyJWT)"| Staff
    L1 -->|"role = admin"| AdminOnly
```

---

## 7. Intent model training

```mermaid
flowchart LR
    G["generate_intent_data.py<br/>templates + typos + Hinglish<br/>63,000 examples, 18 intents"] -->|"--to-db"| T[("ava_sys_intent_training_examples<br/>source = generated")]
    MAN["Admin / manual examples<br/>source = manual (weight x3)"] --> T
    T --> TR["train_intent_model.py<br/>TfidfVectorizer word + char<br/>LogisticRegression<br/>scikit-learn"]
    EV["intent_eval.csv<br/>74 hand-written messages"] --> TR
    TR -->|"accuracy report"| REP["95.9% on eval set"]
    TR -->|"joblib"| F[["app/ml/artifacts/intent_model.joblib"]]
    F --> RT["Used at runtime by intent.py<br/>classify() → intent + confidence"]
```

---

## 8. Startup sequence

```mermaid
flowchart TD
    S(["Backend container starts<br/>uvicorn app.main:app"]) --> W["Wait for MySQL"]
    W --> MIG["Alembic: stamp old databases,<br/>upgrade to latest migration"]
    MIG --> SEED["Seed empty tables only:<br/>first admin (argon2), sample business data"]
    SEED --> LLM["Start loading the local LLM<br/>in a background thread"]
    LLM --> READY(["API ready<br/>(rules engine answers until the LLM is loaded)"])
```

---

## 9. Code flowchart: one chat message through the backend files

File → function. Arrows mean "calls".

```mermaid
flowchart TD
    subgraph R["routers/chat.py"]
        R1["chat()<br/>POST /api/chat"]
    end
    subgraph CORE["core/"]
        RL["rate_limit.rate_limit('chat')"]
    end
    subgraph CS["services/chat_service.py"]
        H["handle_chat(db, session_id, turn, channel)"]
        GC["get_conversation()"]
        NL["needs_llm()"]
        CP["_confirm_pending()"]
    end
    subgraph AI["ai/"]
        RE["rules_engine.handle()"]
        IC["intent.classify()<br/>intent.predict_intent()"]
        AG["agent.run()"]
        BP["agent.build_system_prompt()"]
        GD["agent._guard()"]
        LC["llm_client.get_llm_client()<br/>LocalTransformersClient.complete()"]
        PO["llm_client.parse_model_output()"]
        ET["tools.execute_tool()"]
        RP["tools.run_pending_action()"]
    end
    subgraph SV["services/"]
        AP["appointment_service<br/>available_dates() · available_slots()<br/>validate_slot() · book_appointment()<br/>find_customer_appointment()<br/>reschedule_appointment() · cancel_appointment()"]
        FQ["faq_service<br/>search_faq() · best_answer()"]
        LS["lead_service<br/>create_lead() · request_handoff()"]
        BS["business_service<br/>get_settings() · local_now()<br/>get_business_hours() · get_services()"]
        CU["customer_service<br/>find_or_create_customer()"]
        VA["validation<br/>is_valid_phone() · is_valid_name()<br/>normalize_booking_code()"]
    end
    DB[("models.py → MySQL<br/>AvaConversation · AvaMessage · AvaAppointment<br/>AvaLead · AvaHandoffRequest · AvaCustomer ...")]

    R1 --> RL
    R1 --> H
    H --> GC
    H --> BS
    H -->|"flow step active"| RE
    H -->|"pending action"| CP --> RP
    H --> NL --> IC
    H -->|"LLM needed"| AG
    H -->|"LLM failed"| RE
    H -->|"save messages, commit"| DB

    AG --> BP --> BS
    BP --> FQ
    AG --> LC --> PO
    AG --> ET
    AG --> GD

    RE --> IC
    RE --> AP
    RE --> FQ
    RE --> LS
    RE --> BS

    ET --> AP
    ET --> FQ
    ET --> LS
    ET --> BS
    RP --> AP

    AP --> CU
    LS --> CU
    AP --> VA
    LS --> VA
    AP --> DB
    LS --> DB
    CU --> DB
    FQ --> DB
    BS --> DB
```

---

## 10. Code flowchart: an admin request (example: reschedule an appointment)

```mermaid
flowchart TD
    UI["pages/admin/Appointments.jsx<br/>Reschedule modal + SlotPicker"] --> API1["services/api.js<br/>getAvailability() · rescheduleAppointment()"]
    API1 -->|"fetch /api/... + Bearer token"| VP["Vite proxy (dev) / nginx (prod)"]
    VP --> RT["routers/appointments.py<br/>availability() · reschedule()"]
    RT --> DEP["auth.require_staff<br/>→ require_roles() → current_admin()<br/>PyJWT decode + Admin lookup"]
    DEP -->|"401 / 403"| ERR["ApiError shown by ErrorAlert"]
    RT --> SVC["appointment_service.reschedule_appointment()"]
    SVC --> CHK["_ensure_changeable()<br/>validate_slot(lock=True)"]
    CHK --> LOCK[("SELECT ... FOR UPDATE<br/>ava_business_working_hours")]
    CHK --> OV["_blocking_appointments()<br/>_overlaps()"]
    SVC --> HIS["_history('rescheduled', actor='admin:username')"]
    SVC --> CM[("_commit() → MySQL")]
    CM --> OUT["appointment_out() → JSON"]
    OUT --> UI2["Table refreshes, SuccessAlert"]
```

---

## 11. Code flowchart: frontend structure

```mermaid
flowchart TD
    MAIN["main.jsx<br/>BrowserRouter + Bootstrap CSS/JS"] --> APP["App.jsx"] --> ROUTES["routes/AppRoutes.jsx"]

    ROUTES -->|"/"| ML["layouts/MainLayout.jsx"]
    ML --> NAV["components/Navbar.jsx"]
    ML --> HOME["pages/Home.jsx"]
    ML --> FOOT["components/Footer.jsx"]
    ML --> CHAT["components/Chatbox.jsx<br/>+ chatbox.css"]

    ROUTES -->|"/admin/login"| LOGIN["pages/admin/Login.jsx"]
    ROUTES -->|"/admin/*"| PR["routes/ProtectedRoute.jsx<br/>checks token via getAdminMe()"]
    PR --> AL["layouts/AdminLayout.jsx<br/>sidebar, role badge, change password"]
    AL --> PAGES["pages/admin/<br/>Dashboard · Appointments · Handoffs · Leads<br/>Customers · Conversations · Faqs · Business<br/>Users (admin only via AdminOnly)"]

    PAGES --> SH["components/admin/shared.jsx<br/>useLoader · useMutation · useFlash · useDebounced<br/>SlotPicker · Transcript · SuccessAlert"]
    PAGES --> UIK["components/admin/ui.jsx<br/>PageHeader · StatusBadge · Modal · ErrorAlert · Loading"]
    PAGES --> FMT["utils/format.js<br/>formatDateTime · badgeClass"]

    CHAT --> API["services/api.js"]
    PAGES --> API
    LOGIN --> API
    PR --> API
    API --> AUTHJS["services/auth.js<br/>token in localStorage"]
    API --> CFG["config.js<br/>VITE_API_URL"]
    API -->|"fetch"| BE(["Backend /api/*"])
```
