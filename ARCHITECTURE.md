# T3 — Triathlon Training Agent: Architecture Document

## Overview

An AI agent that acts as a personal triathlon coach and training plan orchestrator. It builds periodized training plans from an automated knowledge base, manages scheduling across Google Calendar and Intervals.icu, adapts to real-life disruptions, tracks performance, and communicates with you via Telegram.

---

## Design Decisions

### Interface
- **Telegram bot** (python-telegram-bot)
- Primary interaction channel for all commands, confirmations, notifications, and analytics
- WhatsApp and CLI were considered and rejected in favour of Telegram's free, official, no-approval-required Bot API

### LLM
- **Gemini 2.0 Flash** (bare SDK, function calling)
- Chosen for: generous free tier, native function calling (required for tool dispatch), large context window
- Bare SDK chosen over ADK/LangChain for: simplicity, low vendor lock-in, full control, educational value
- LlamaIndex used exclusively for the RAG pipeline (document ingestion, chunking, embedding, retrieval)

### Knowledge Base
- **Automated ingestion** — no manual curation, no copyrighted books
- Sources:
  - TrainingPeaks blog
  - Joe Friel's blog
  - PubMed API (open-access endurance sports science)
  - British Triathlon / USAT publicly available coaching resources
- Pipeline: crawl4ai scraper → LlamaIndex ingestion → chunking → embedding → Chroma vector store
- Crawls run on a weekly schedule via APScheduler

### Hosting
- **Fly.io** (free tier)
- Chosen over Railway because: genuinely free forever (not credit-based), includes 3GB persistent volume (needed for SQLite + Chroma), supports always-on services
- Persistent volume mounted for SQLite database and Chroma vector store

### Calendar Sync Strategy
- **Polling every 5 minutes** (not webhooks)
- Rationale: simpler to implement, no public URL required during development, 5-minute lag is acceptable for training schedule management
- State tracked via `last_synced_at` timestamp in SQLite
- Upgrade path to Google Calendar webhooks available if lag becomes unacceptable

### Conflict Resolution
- When a calendar event is moved and creates a scheduling conflict, the **agent always asks before acting**
- Agent presents options via Telegram; user confirms before any changes are made
- Training plan changes compound — silent auto-resolution is too risky

### Weather
- **Open-Meteo** (fully free, no API key required)
- **Passive warnings only** — agent notifies 48h before an outdoor session if significant weather is expected
- If forecast clears before the session, agent sends a follow-up "all clear" message
- No automatic rescheduling based on weather — user decides

### Disruption Reporting
- **Telegram-first**: user reports disruptions in natural language ("I'm in Paris June 15–29, no pool access but I can run")
- Agent extracts dates and constraints, presents 2–3 re-planning options with tradeoffs, waits for user confirmation before acting
- **Proactive GCal scanning**: APScheduler scans Google Calendar for multi-day blocks and asks proactively ("I see Paris Trip June 15–29 — should I adjust your training plan?")
- No naming conventions required on either calendar

### Re-planning Philosophy
- Agent always asks first and presents options with tradeoffs
- Example options for a 2-week travel disruption: "Option A: compress missed swims into weeks 9–12 (risk: fatigue spike). Option B: deprioritize swim leg, focus on bike/run."
- User picks — agent never restructures the plan silently

### Performance Analytics
- Intervals.icu API used for both **writing** (planned workouts) and **reading** (completed activities, CTL/ATL/TSB fitness metrics)
- **Configurable notifications**, defaulting to **digest mode**
- Digest mode: one weekly summary (default Sunday 8pm) bundling the week's sessions, planned vs actual, load trend
- Full proactive mode available: post-session summary, weekly recap, block summary, overtraining flag, race countdown
- Post-session analytics include: TSS, HR zones, pace/power vs target, one-line assessment

### Authentication
- **Guided OAuth flow via Telegram on first run**
- Google Calendar: standard OAuth 2.0, tokens stored in SQLite
- Intervals.icu: API key (user retrieves from their account settings, agent prompts them step-by-step)

### Athlete Profile
- Built during **onboarding conversation** (first run, ~10–12 questions via Telegram)
- Fields: name, age, sex, experience level, weekly hours available, swim/bike/run baseline, upcoming races + dates, injury history, notification preferences
- Stored in SQLite, referenced and updated by the agent over time

---

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Interface | Telegram (python-telegram-bot) |
| LLM | Gemini 2.0 Flash (bare SDK, function calling) |
| RAG | LlamaIndex + Chroma |
| Database | SQLite |
| Scheduler | APScheduler |
| Hosting | Fly.io (free tier) |
| Weather | Open-Meteo (no API key) |
| Calendar | Google Calendar API (OAuth) |
| Training platform | Intervals.icu REST API |
| Web scraping | crawl4ai |

---

## Component Map

```
┌─────────────────────────────────────────────────────┐
│                   Telegram Bot                       │
│           (python-telegram-bot)                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 Agent Core                           │
│         (Gemini 2.0 Flash bare SDK)                  │
│         function calling dispatcher                  │
└──┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
GCal      Intervals   Weather    RAG
Client    .icu Client  Client    Query
   │          │          │          │
   │          │      Open-Meteo  LlamaIndex
   │          │                     │
   └──────────┴──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │       SQLite        │
              │  athlete_profile    │
              │  training_plan      │
              │  calendar_events    │
              │  notification_prefs │
              │  oauth_tokens       │
              └─────────────────────┘

┌─────────────────────────────────────────────────────┐
│              Background Scheduler (APScheduler)      │
│  - Poll GCal every 5min → detect moves/vacations    │
│  - Poll Intervals.icu → detect completed workouts   │
│  - Weather check 48h before each session            │
│  - Weekly digest Sunday 8pm                         │
│  - Knowledge crawler (weekly)                       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              Knowledge Pipeline                      │
│  Sources: TrainingPeaks blog, Joe Friel's blog,     │
│           PubMed API, British Triathlon/USAT         │
│  → crawl4ai scraper → LlamaIndex ingestion          │
│  → chunking → embedding → Chroma vector store       │
└─────────────────────────────────────────────────────┘
```

---

## Key Data Flows

### Plan Generation
User asks for plan → Gemini queries RAG (training literature) → generates periodized year plan → writes workouts to Intervals.icu + GCal → confirms via Telegram

### Calendar Sync
APScheduler polls GCal every 5min → detects moved event → agent reasons about conflict → asks user via Telegram → on confirm, updates Intervals.icu

### Disruption Reporting
User tells Telegram "vacation June 15–29, no pool" → agent extracts dates + constraints → presents 2–3 re-planning options with tradeoffs → user picks → plan updated on both calendars

### Proactive Vacation Detection
APScheduler scans GCal → finds multi-day block → agent asks "I see Paris Trip June 15–29, adjust plan?"

### Post-session Analytics (digest mode)
Intervals.icu poll detects new completed activity → queued → Sunday digest bundles week's sessions + metrics → sent via Telegram

### Weather Warning
48h before outdoor session → Open-Meteo check → if significant weather, Telegram warning sent → if forecast clears before session, follow-up sent

---

## SQLite Schema (core tables)

```sql
athlete_profile     -- name, age, experience, zones, goals, race dates
training_plan       -- blocks, weeks, sessions (JSON), phase (base/build/peak/race)
calendar_events     -- gcal_id, intervals_id, scheduled_at, type, last_synced_at
notification_prefs  -- digest_mode, post_session, weather_warnings, digest_day, digest_time
oauth_tokens        -- service, access_token, refresh_token, expires_at
```

---

## Onboarding Flow (first run)

1. Bot starts → guided Google OAuth via Telegram link
2. Guided Intervals.icu API key setup (step-by-step instructions)
3. Athlete profile questionnaire (~10–12 questions):
   - Name, age, sex
   - Triathlon experience level
   - Weekly hours available (by day)
   - Swim / bike / run baseline (current fitness)
   - Upcoming races + target dates + priority (A/B/C)
   - Injury history
   - Notification preferences (digest vs full proactive)
4. Agent generates year plan → previews it → user confirms → schedules everything on GCal and Intervals.icu

---

## Build Order

### Phase 1 — Skeleton (week 1–2)
- Telegram bot + Gemini bare SDK with function calling skeleton
- Athlete profile onboarding conversation + SQLite schema
- Google Calendar OAuth + basic read/write
- Intervals.icu API client + basic read/write

### Phase 2 — Core Loop (week 3–4)
- Training plan generation (Gemini + hardcoded periodization knowledge, no RAG yet)
- GCal ↔ Intervals.icu polling sync (5-minute interval)
- Conflict detection + Telegram confirmation flow
- Disruption reporting via natural language

### Phase 3 — Intelligence (week 5–6)
- LlamaIndex + Chroma setup with persistent Fly.io volume
- crawl4ai knowledge crawler (TrainingPeaks, Friel, PubMed, British Triathlon/USAT)
- Plan generation migrated to RAG-backed knowledge retrieval
- Re-planning logic with options presentation

### Phase 4 — Analytics + Polish (week 7–8)
- Post-session analytics (TSS, HR zones, pace/power vs target)
- Weekly/block digest notifications
- Open-Meteo weather integration with 48h checks
- Proactive GCal vacation scanning
- Configurable notification preferences

### Phase 5 — Deploy
- Fly.io deployment with persistent volume
- SQLite + Chroma on mounted volume
- APScheduler as background process
- Environment variable management for secrets

---

## Open Questions (revisit at build time)

- Intervals.icu API rate limits — undocumented, test early in Phase 1
- Google Calendar webhook upgrade path — if 5-minute polling lag becomes unacceptable
- Chroma persistence on Fly.io — requires explicit volume mount path configuration
- PubMed search term strategy — sports science is broad, need curated query terms for relevance
