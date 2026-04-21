from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_MLS_Agent_Portal_Conversation.docx")


TRANSCRIPT = [
    (
        "User",
        "What Im thinking is to add MLS feed from NTREIS via api and also Listojo agents should have a separate portal, which provides them the list of leads [Image #1]  like in the screenshots",
    ),
    (
        "Assistant",
        """Yes, this is the right direction, but it changes Listojo from a pure classifieds product into a hybrid marketplace + agent workflow platform.

**Short answer**

Adding an NTREIS MLS feed plus a separate Listojo agent portal can materially increase product value if your goal is to serve serious renter/buyer leads and give agents a reason to stay inside Listojo. The screenshot direction makes sense: agents should not use the same UI as consumers or landlords. They need a lead desk, shortlist workflow, match quality view, status tracking, and follow-up tooling.

**Why this is valuable**

The MLS feed solves one of Listojo’s biggest business problems: inventory liquidity.

Right now, your biggest risk is limited listing volume. NTREIS data can immediately improve:
- inventory depth
- geographic coverage
- search quality
- agent usefulness
- lead conversion potential

The agent portal solves a second problem: operational monetization.

Instead of only being a listing marketplace, Listojo can become:
- a lead-generation platform for agents
- a workflow system for shortlisting and client follow-up
- a monetizable B2B layer on top of the consumer-facing experience

That is a stronger business than “just classifieds,” if executed properly.

**What the agent portal should do**

The screenshot is directionally good. I would treat that as a separate product surface with these modules:

- `Leads`
  - all leads
  - lead detail
  - status: new, working, pending, closed
  - source: organic, guided search, inquiry, chat
  - match score
  - assigned agent

- `Client profile`
  - city preferences
  - budget
  - beds/baths
  - commute / school / amenity preferences
  - timeline
  - notes
  - shortlist history

- `Shortlist workflow`
  - matched listings from MLS + native Listojo listings
  - save shortlist
  - send shortlist to client
  - mark viewed / interested / rejected
  - schedule tours

- `Communication`
  - messages
  - reminders
  - follow-up tasks
  - response tracking

- `Performance`
  - leads assigned
  - shortlists sent
  - tours scheduled
  - closings
  - revenue attribution

That gives you a real agent operating system, not just a prettier inbox.

**Strategic upside**

If you do this well, Listojo becomes a 3-sided system:

- consumers use Listojo to search and submit guided preferences
- agents use Listojo to manage and convert leads
- MLS data provides inventory depth and market credibility

That opens better monetization options:
- pay-per-lead
- monthly agent subscription
- brokerage dashboard plans
- premium lead routing
- premium CRM / shortlist tools
- referral revenue from closings or rentals

This is much stronger than relying only on featured listings.

**Important constraints**

This part matters a lot: MLS access is not just “connect an API and ship it.”

Based on current RESO guidance, MLS data access is typically provided by the MLS directly, and credentials come from the MLS or its technical provider, not from RESO itself. RESO says the modern transport standard is the `RESO Web API`, and data access is obtained from the local MLS after licensing and approval. Sources:
- RESO Web API overview: https://www.reso.org/reso-web-api/
- RESO FAQ on data/credentials: https://www.reso.org/ht-faq/new-faq-question-156/
- RESO transition guide listing common provider ecosystems: https://www.reso.org/api-guide/

Also, NTREIS historically adopted a RESO Web API solution through Remine according to this announcement:
- https://www.businesswire.com/news/home/20200211005301/en/Remine-Announces-North-Texas-Regional-Information-Systems-NTREIS-Adoption-of-API-and-AddEdit-Products

**What this means in practice**
You will likely need:
- MLS approval
- proper licensing agreement
- brokerage or vendor relationship
- compliance with display rules
- data refresh / attribution compliance
- rules on who can see what data
- auditability of lead routing and listing display

So from a business standpoint, this is viable, but operationally regulated.

**Big product decisions you need to make first**

1. Is Listojo becoming an `agent-assisted marketplace` or staying a `self-serve classifieds platform`?
If you add MLS + agent portal, your identity shifts toward agent-assisted discovery.

2. Who owns the lead?
You need a clean answer:
- Listojo-owned lead distributed to agents?
- brokerage-owned lead?
- exclusive assignment?
- round robin?
- city-based routing?

3. Are MLS listings and Listojo-native listings treated equally?
You need clear UX rules:
- native listings
- MLS listings
- sponsored listings
- shortlist source transparency

4. What is the monetization model?
Best options:
- monthly agent subscription
- pay-per-qualified-lead
- brokerage seats
- success-based referral/placement fees

**My recommendation**

I would do this in phases.

**Phase 1: Agent portal without MLS**
Use existing guided search + inquiry + chat data.
Build:
- lead inbox
- lead status pipeline
- lead detail page
- shortlist object
- manual matching workflow

Why:
- proves agent workflow value before MLS complexity
- lets you validate if agents even want this
- faster to launch

**Phase 2: NTREIS MLS integration**
Once workflow is proven:
- ingest MLS inventory
- normalize it with Listojo listing schema
- add compliance-safe display
- allow agents to build shortlists from MLS data
- log all listing-source attribution

**Phase 3: Lead monetization**
After supply + workflow + conversions exist:
- agent subscriptions
- premium lead routing
- team dashboards
- brokerage reporting

**Business verdict**

As a business move, this is much better than just adding more consumer features.

Why:
- MLS feed fixes inventory weakness
- agent portal creates a monetizable B2B layer
- the screenshot-style workflow is commercially meaningful
- it moves Listojo closer to a real revenue model

But it only works if you stay disciplined:
- define lead ownership
- handle MLS compliance correctly
- keep consumer UX simple
- give agents a truly separate portal, not a reused consumer dashboard

**Best framing**
If you pursue this, Listojo should be positioned more like:

`A lead-driven home search and agent workflow platform powered by local marketplace demand + MLS inventory.`

That is a stronger story than “classifieds site with agents.”

If you want, I can next give you one of these:
- a `product architecture plan` for MLS + agent portal
- a `business model recommendation` for how to monetize agents
- a `screen-by-screen PRD` for the agent dashboard shown in your screenshot""",
    ),
    ("User", "Give me all three"),
    (
        "Assistant",
        """**Product Architecture Plan**

The cleanest approach is to treat this as three connected layers, not one monolithic product.

**1. Consumer Layer**
This is the public-facing Listojo experience.

Purpose:
- capture intent
- generate leads
- drive discovery
- collect structured preferences

Core modules:
- search and filters
- guided search
- listing detail
- inquiry submission
- chat / contact
- saved listings
- user accounts

Key outputs from this layer:
- lead profile
- search intent
- budget / city / beds / must-haves
- engagement score
- source of lead
- shortlist interactions

**2. Listing Data Layer**
This is the inventory engine.

You should support two listing sources:
- `Listojo Native Listings`
- `MLS Listings via NTREIS`

Recommended architecture:
- `listing_sources` table or enum
  - `native`
  - `mls_ntreis`
- unified normalized listing model for search/display
- raw-source ingestion tables for MLS sync logs and compliance fields
- source attribution on every listing

Important design rule:
Do not force MLS data directly into the exact same storage path as native listings without preserving origin metadata. You need strong source traceability.

Suggested model split:
- `native_listings`
- `mls_sync_records`
- `canonical_listings`
- `listing_media`
- `listing_source_metadata`

Why:
- native listings are user-created and editable in your product
- MLS listings are licensed data and may have display/compliance constraints
- canonical search results need one unified search surface
- source-specific rules must still be preserved

**3. Agent Operations Layer**
This should be a separate portal, not an extension of the consumer UI.

Purpose:
- manage leads
- build shortlists
- communicate with clients
- track conversion
- measure agent performance

Core modules:
- lead inbox
- lead detail
- client profile
- shortlist builder
- communications
- task/reminder system
- reporting / pipeline
- agent settings / territory / routing

**Recommended System Flow**

1. Consumer searches or completes guided search.
2. Listojo creates or updates a structured lead profile.
3. Matching engine scores both native and MLS listings.
4. Lead is assigned to:
   - unassigned queue,
   - auto-routed agent,
   - or brokerage queue.
5. Agent sees the lead in portal.
6. Agent reviews preferences, shortlist candidates, and engagement history.
7. Agent sends curated shortlist.
8. Client engages, messages, tours, applies, or closes.
9. Platform records conversion and monetization events.

**Core Entities You Need**

- `Lead`
  - id
  - name
  - email / phone
  - source
  - stage
  - assigned_agent_id
  - assigned_brokerage_id
  - created_at
  - last_activity_at
  - qualification_score

- `LeadPreferences`
  - city
  - neighborhoods
  - max_budget
  - beds
  - baths
  - property type
  - move-in timeline
  - must-have amenities
  - notes

- `LeadActivity`
  - search completed
  - listing viewed
  - inquiry sent
  - shortlist opened
  - message sent
  - tour scheduled

- `Agent`
  - profile
  - territory
  - specialties
  - active status
  - brokerage
  - plan type

- `Shortlist`
  - lead_id
  - agent_id
  - status
  - sent_at
  - version

- `ShortlistItem`
  - listing_id
  - source_type
  - match_score
  - notes
  - item_status

- `Listing`
  - canonical listing record
  - source metadata
  - MLS attribution fields
  - display eligibility flags

**Search / Matching Architecture**

You should not just “show MLS feed.” You need a scoring layer.

Scoring inputs:
- location
- budget fit
- beds/baths
- property type
- amenities
- timeline
- behavioral data
- agent notes / manual boost

Outputs:
- match score
- reason tags
- shortlist eligibility
- recommended inventory count

This is where Listojo keeps a differentiated moat. MLS inventory gives you supply. Matching gives you product value.

**Security / Permissions**

Separate roles clearly:
- consumer
- landlord / native lister
- agent
- brokerage manager
- admin / compliance

Agent portal permissions should control:
- assigned leads only
- brokerage queue visibility
- listing source visibility
- notes visibility
- export permissions
- reassignment permissions

**Compliance / MLS-Specific Considerations**

Architecturally, you should plan for:
- display attribution
- refresh timestamps
- source disclaimers
- allowed fields vs restricted fields
- consumer display vs agent-only display
- listing status synchronization
- audit logs for MLS data usage

Do not hard-code MLS assumptions into the consumer flow. Keep it abstracted in the listing source layer.

**Recommended Build Phases**

**Phase 1**
- build lead object
- build agent portal
- use only native Listojo + manual shortlist logic

**Phase 2**
- add NTREIS ingestion service
- normalize MLS listings
- integrate MLS inventory into matching/search
- add source compliance handling

**Phase 3**
- routing engine
- brokerage/team support
- monetization
- analytics and conversion attribution

---

**Business Model Recommendation**

This should become a B2B2C model, not just a consumer classifieds business.

The strongest commercial model is:
- consumers use the platform free
- agents/brokerages pay for workflow and lead access
- premium monetization happens on the agent side, not just on listing boosts

**Recommended Monetization Stack**

**1. Agent Subscription**
This should be your most stable revenue layer.

What agents pay for:
- access to lead portal
- shortlist tools
- lead notes/history
- match explanations
- communication workflow
- reporting dashboard

Suggested pricing shape:
- solo agent plan
- team plan
- brokerage plan

Possible pricing logic:
- `Starter`: limited active leads, basic shortlist tools
- `Pro`: full lead management, analytics, tasks
- `Team`: multiple agents, routing, reporting
- `Brokerage`: admin controls, queues, team analytics

**2. Qualified Lead Routing**
This can become high-margin if quality is real.

Models:
- pay per lead
- pay per accepted lead
- monthly quota plan
- exclusive ZIP/city routing plan

Be careful here:
If quality is inconsistent, pay-per-lead creates churn and distrust quickly.

**3. Premium Visibility / Priority Routing**
Agents can pay for:
- priority assignment
- geography exclusivity
- category specialization
- premium placement in lead routing

This only works if you already have real demand volume.

**4. Native Listing Boosts**
This can still exist, but I would treat it as secondary.
It is simpler, but less strategic than agent monetization.

**5. Brokerage SaaS Layer**
Long term, this is the strongest business if you succeed.

Brokerages could pay for:
- team lead queues
- routing rules
- SLA tracking
- lead conversion reporting
- agent productivity analytics
- territory assignment

**Best Monetization Path by Stage**

**Stage 1: Validate Workflow**
- free or pilot access for 3-10 agents
- no complex billing
- prove that agents actually use shortlist and follow-up tools

**Stage 2: Subscription First**
- monthly agent plans
- simple pricing
- avoid per-lead complexity too early

**Stage 3: Hybrid Monetization**
- subscription + premium leads
- team plans + brokerage plans
- premium routing or exclusivity

**Stage 4: Outcome-Linked Revenue**
- referral fees
- success fees where compliant
- partnership revenue from rental/application ecosystem

**Business Risks in Monetization**

1. Charging too early before lead quality is proven.
2. Selling “leads” that are really just weak inquiries.
3. No clear distinction between free product and paid value.
4. Agents seeing the portal as just another inbox instead of a workflow advantage.
5. Brokerage conflict if routing and ownership rules are unclear.

**My strongest recommendation**
Start with `agent subscription SaaS`, not pure `pay-per-lead`.

Reason:
- more predictable revenue
- less friction
- easier trust-building
- stronger product positioning
- less immediate pressure on lead quality perfection

---

**Screen-by-Screen PRD For Agent Dashboard**

This PRD assumes the screenshot direction is the base.

**1. Agent Dashboard Home**
Purpose:
Give agents an at-a-glance lead and productivity view.

Sections:
- KPI cards
  - new leads
  - active shortlists sent
  - closings this month
  - earnings this month
- incoming leads list
- quick filters
  - all
  - new
  - working
  - pending
  - closed
- recent activity

Primary actions:
- open lead
- send shortlist
- message client
- mark status

Success metrics:
- time to first response
- shortlist sent per lead
- lead touched within SLA

**2. Leads List**
Purpose:
Main working queue for agents.

Fields:
- lead name
- city / area
- beds / budget / move timeline
- lead status
- match score
- matched listing count
- source
- last updated
- assigned date

Filters:
- status
- city
- budget band
- match score
- source
- assigned to me / team
- new today / overdue

Actions:
- open lead
- assign / reassign
- archive
- create shortlist
- add note

**3. Lead Detail**
Purpose:
Single source of truth for one client.

Panels:
- lead summary
- preferences
- timeline
- contact info
- source and qualification
- notes
- activity history
- matched listings
- shortlist status
- tasks / reminders

Actions:
- change stage
- add note
- create shortlist
- send message
- schedule tour
- mark converted / lost

Suggested stages:
- new
- contacted
- shortlist ready
- shortlist sent
- touring
- application in progress
- closed won
- closed lost

**4. Client Preferences Panel**
Purpose:
Show structured intent clearly.

Fields:
- preferred cities
- neighborhood / school / commute preferences
- budget max
- beds / baths
- property type
- amenities
- move-in window
- special notes
- cultural/community preferences if relevant

Actions:
- edit preference profile
- sync with matching engine
- rerun match results

**5. Matched Listings Screen**
Purpose:
Show AI/FMM + rules-based matched inventory.

Listing cards should include:
- photo
- address / area
- price
- beds / baths
- source
  - native
  - NTREIS MLS
- match score
- match reasons
- compliance attribution
- shortlist toggle

Filters:
- match score threshold
- source
- price
- area
- status
- newly updated

Actions:
- add to shortlist
- dismiss
- pin
- compare
- message client about listing

**6. Shortlist Builder**
Purpose:
Create curated sets of listings for the client.

Sections:
- selected listings
- ordering / ranking
- agent notes per listing
- send preview
- saved shortlist history

Actions:
- send shortlist
- edit shortlist
- resend updated shortlist
- duplicate previous shortlist

System behavior:
- track open rate
- track listing clicks
- track favorite / reject behavior
- log when client responds

**7. Messages / Communications**
Purpose:
Central communication thread.

Should support:
- lead messages
- agent notes
- shortlist delivery history
- reminder nudges
- email/SMS integration later

Actions:
- send message
- use template
- mark awaiting response
- schedule follow-up

**8. Tasks / Follow-Ups**
Purpose:
Prevent lead leakage.

Task types:
- first contact
- follow-up
- shortlist send
- tour schedule
- application check
- re-engagement

Filters:
- due today
- overdue
- completed

**9. Analytics / Performance**
Purpose:
Show agent and team value.

Metrics:
- leads assigned
- response time
- shortlist send rate
- tour rate
- conversion rate
- close rate
- revenue attribution
- city / budget segment performance

For managers:
- agent comparison
- routing efficiency
- unassigned queue health
- SLA breaches

**10. Brokerage Admin Portal**
Purpose:
Team-level management.

Functions:
- create agents
- assign territories
- set routing rules
- monitor queue
- view pipeline
- export reports
- manage subscriptions / billing

---

**Recommended MVP Scope**

If you want this to ship quickly, do not build the full screenshot ecosystem in one go.

Build this first:

**Agent MVP**
- agent login
- leads list
- lead detail
- status updates
- notes
- matched listings list
- shortlist builder
- shortlist send action

**Second wave**
- tasks/reminders
- analytics
- brokerage manager view
- routing rules
- NTREIS source blending

---

**Final Recommendation**

All three together fit very well.

- The `architecture` gives you a scalable separation between consumer search, listing supply, and agent operations.
- The `business model` gives you a stronger B2B revenue path than relying on classifieds-style monetization alone.
- The `agent dashboard PRD` gives you a product surface that agents could actually use daily.

If I were prioritizing execution, I would do it in this order:

1. Build the agent portal MVP on top of current Listojo lead flows.
2. Define lead ownership, routing, and assignment rules before anything else.
3. Add NTREIS/MLS inventory only after the workflow model is clear.
4. Monetize through subscriptions first, not pay-per-lead first.

If you want, I can next turn this into a single polished deliverable as:
- a `technical architecture document`
- a `PRD`
- or a `business plan / investor memo` for this new MLS + agent portal direction.""",
    ),
    ("User", "1"),
    (
        "Assistant",
        """**Technical Architecture Document**

**Title**
Listojo MLS + Agent Portal Architecture

**Objective**
Extend Listojo from a marketplace/classifieds platform into a lead-driven search and agent workflow platform by introducing:
- NTREIS MLS inventory ingestion
- a separate agent portal
- unified lead, shortlist, and matching workflows

**Architecture Goals**
- Keep consumer, listing-data, and agent-ops concerns separate
- Support both native Listojo listings and MLS listings in one search experience
- Preserve listing-source traceability and MLS compliance boundaries
- Create a scalable foundation for agent subscriptions, routing, and brokerage workflows
- Avoid tightly coupling MLS feed logic to consumer-facing templates

**System Overview**

The platform should be split into 4 logical layers:

1. `Experience Layer`
- Consumer web app
- Agent portal
- Admin / brokerage portal

2. `Application Layer`
- lead management
- matching engine
- shortlist service
- messaging / notifications
- routing engine
- reporting / analytics

3. `Data Integration Layer`
- NTREIS MLS connector
- normalization / mapping pipeline
- sync scheduler
- compliance metadata handling

4. `Persistence Layer`
- transactional database
- search index later if needed
- audit/event logs
- media/reference storage

**High-Level Component Model**

**A. Consumer Platform**
Purpose:
- capture leads
- collect preferences
- display listings
- drive inquiry/chat activity

Modules:
- search
- guided search
- listing detail
- saved listings
- inquiry/chat
- user profile

**B. Agent Portal**
Purpose:
- manage assigned leads
- review preference profiles
- create and send shortlists
- track pipeline status
- convert leads into tours / deals

Modules:
- lead inbox
- lead detail
- client preferences
- matched listings
- shortlist builder
- tasks/reminders
- communications
- analytics

**C. MLS Integration Service**
Purpose:
- pull NTREIS inventory via approved API access
- transform MLS schema into canonical Listojo schema
- maintain source attribution and sync freshness
- enforce display eligibility and source-specific rules

Modules:
- authentication client
- pull/sync scheduler
- field mapper
- canonical listing upsert
- sync audit logs
- source metadata processor

**D. Admin/Brokerage Layer**
Purpose:
- manage agents
- manage lead routing
- monitor compliance and sync health
- review performance

Modules:
- agent management
- brokerage queue management
- routing rules
- listing-source oversight
- reporting dashboard

**Core Domain Model**

**1. Lead**
Represents a renter/buyer inquiry or guided-search prospect.

Fields:
- `id`
- `source_type`
- `source_channel`
- `name`
- `email`
- `phone`
- `status`
- `assigned_agent_id`
- `assigned_brokerage_id`
- `qualification_score`
- `created_at`
- `last_activity_at`

Example statuses:
- `new`
- `contacted`
- `working`
- `shortlist_ready`
- `shortlist_sent`
- `touring`
- `pending`
- `closed_won`
- `closed_lost`

**2. LeadPreference**
Structured client intent.

Fields:
- `lead_id`
- `cities`
- `neighborhoods`
- `max_budget`
- `min_budget`
- `bedrooms`
- `bathrooms`
- `property_types`
- `move_in_date`
- `amenities`
- `school_preference`
- `commute_preference`
- `community_preference`
- `notes`

**3. LeadActivity**
Event trail for lead behavior.

Fields:
- `lead_id`
- `event_type`
- `listing_id`
- `metadata`
- `created_at`

Examples:
- guided search completed
- listing viewed
- inquiry submitted
- shortlist opened
- message sent
- tour scheduled

**4. ListingSource**
Defines the origin of a listing.

Values:
- `native`
- `mls_ntreis`

This must be a first-class field, not a weak tag.

**5. CanonicalListing**
Unified display/search object used by Listojo.

Fields:
- `id`
- `source_type`
- `source_record_id`
- `display_status`
- `title`
- `description`
- `city`
- `state`
- `zip_code`
- `price`
- `bedrooms`
- `bathrooms`
- `property_type`
- `listing_type`
- `photos`
- `lat`
- `lng`
- `last_synced_at`
- `display_allowed`
- `compliance_payload`

**6. NativeListing**
Existing Listojo listing model can remain source-owned for user-posted content.

**7. MlsListingRaw**
Raw imported MLS record.

Fields:
- `source_record_id`
- `payload_json`
- `ingested_at`
- `checksum`
- `status`

**8. Shortlist**
Agent-curated collection for a lead.

Fields:
- `id`
- `lead_id`
- `agent_id`
- `status`
- `sent_at`
- `created_at`
- `updated_at`

Statuses:
- `draft`
- `sent`
- `viewed`
- `updated`
- `archived`

**9. ShortlistItem**
Listing inside a shortlist.

Fields:
- `shortlist_id`
- `listing_id`
- `source_type`
- `match_score`
- `agent_note`
- `order_index`
- `client_response`

**10. Agent**
Role-specific user extension.

Fields:
- `user_id`
- `brokerage_id`
- `territories`
- `specialties`
- `subscription_plan`
- `is_active`

**11. Brokerage**
Team-level org object.

Fields:
- `id`
- `name`
- `routing_mode`
- `subscription_plan`
- `manager_user_id`

**Data Flow**

**Flow 1: Consumer Lead Creation**
1. User completes guided search or submits inquiry.
2. System creates `Lead`.
3. System creates/updates `LeadPreference`.
4. Matching engine runs against canonical inventory.
5. Lead enters unassigned queue or gets routed to agent.
6. Agent sees lead in portal.

**Flow 2: MLS Sync**
1. Scheduler calls NTREIS connector.
2. Raw MLS payload is fetched.
3. Payload stored in `MlsListingRaw`.
4. Mapper transforms source fields into canonical schema.
5. System upserts `CanonicalListing`.
6. Compliance fields and sync metadata are recorded.
7. Search surface updates.

**Flow 3: Shortlist Creation**
1. Agent opens lead detail.
2. System shows matched listings from canonical index.
3. Agent selects listings and creates `Shortlist`.
4. Client receives shortlist.
5. Client interactions become `LeadActivity`.
6. Agent follows up and moves lead stage.

**Flow 4: Conversion Tracking**
1. Lead status changes from working to touring/pending/closed.
2. Events are logged.
3. Performance metrics update per agent and brokerage.

**Recommended Service Boundaries**

For current project size, these can begin as Django app modules, not full microservices.

Suggested internal modules:
- `consumer`
- `leads`
- `agents`
- `matching`
- `shortlists`
- `mls_integration`
- `brokerages`
- `analytics`

That keeps the architecture modular without premature distributed-system complexity.

**Database Strategy**

Current SQLite setup is not appropriate for this architecture long term.

Recommended production database:
- `PostgreSQL`

Reason:
- better concurrency
- better indexing
- JSON support for MLS raw payloads
- safer transactional behavior
- easier growth path

Recommended storage additions:
- object storage for images/media
- optional Redis later for caching/jobs
- optional search engine later if listing volume grows significantly

**Search Architecture**

Short term:
- PostgreSQL-backed filtering and scoring is acceptable

Medium term:
- introduce dedicated search/index layer if MLS volume becomes large

Search should operate on `CanonicalListing`, not directly on source tables.

Search inputs:
- city
- budget
- beds/baths
- property type
- amenities
- timeline
- lead preference tags
- behavioral signals

Search outputs:
- ranked listing set
- match score
- match reasons
- shortlist recommendations

**Matching Engine Design**

Separate matching logic into an application-layer service.

Inputs:
- `LeadPreference`
- lead behavior
- listing attributes
- optional agent adjustments

Outputs:
- `match_score`
- `reason_tags`
- `fit_summary`

Important:
Do not embed complex matching directly inside templates or controller-heavy views once MLS data is introduced. It should be a reusable service.

**Routing Engine Design**

Lead routing should be explicit and configurable.

Possible routing modes:
- round robin
- city/territory based
- specialization based
- brokerage queue first
- manual assignment

Inputs:
- lead city
- price range
- property type
- language/community preferences
- brokerage territory
- agent workload

Output:
- `assigned_agent_id`
- routing audit entry

**Compliance Architecture**

MLS integration requires guardrails in the architecture.

Required concepts:
- source attribution
- refresh timestamp
- per-source display flags
- role-based field access
- sync logs
- audit trail of imported records

You should store:
- raw source payload
- mapped canonical fields
- compliance metadata
- last sync status
- display eligibility marker

That will let you handle future audits, troubleshooting, and source-specific restrictions.

**Security and Access Control**

Roles:
- `consumer`
- `native_lister`
- `agent`
- `brokerage_manager`
- `admin`

Access rules:
- consumers only see consumer-safe listing fields
- agents only see assigned or team-visible leads
- managers can view team queues and reporting
- admins can inspect sync state and source compliance

Sensitive data controls:
- contact info limited by role
- lead notes scoped by org/agent permissions
- MLS-restricted fields not exposed to unauthorized users

**Background Jobs**

You should introduce background jobs for:
- MLS sync pulls
- listing normalization
- lead scoring refresh
- reminder/task generation
- notification dispatch
- analytics aggregation

Short term options:
- Django management commands + cron
- or a lightweight queue later

**Observability**

Track these system metrics:
- MLS sync success/failure
- records ingested per run
- listing upsert counts
- stale listing count
- lead assignment latency
- shortlist send rate
- lead response SLA
- agent conversion funnel

Application logs should include:
- source sync failures
- mapping failures
- routing decisions
- shortlist delivery events

**API / Integration Boundaries**

Internal API surfaces you’ll likely need:
- `POST /leads`
- `GET /agent/leads`
- `GET /agent/leads/:id`
- `POST /agent/leads/:id/assign`
- `GET /agent/leads/:id/matches`
- `POST /agent/shortlists`
- `POST /agent/shortlists/:id/send`
- `POST /mls/sync/run` internal/admin only
- `GET /brokerage/analytics`

Even if initially implemented server-side, these boundaries help structure the system.

**Suggested Django App Evolution**

Current codebase can evolve like this:

- `listings`
  - keep native listing functionality
  - add canonical listing display adapters later or split out

- new app: `leads`
  - lead, lead preference, lead activity

- new app: `agents`
  - agent profile, inbox, lead detail, tasks

- new app: `shortlists`
  - shortlist and shortlist items

- new app: `mls_integration`
  - raw imports, mappers, sync jobs, compliance

- new app: `brokerages`
  - brokerage orgs, routing policies, manager dashboards

- new app: `analytics`
  - KPI aggregation and reporting

**Phased Implementation Plan**

**Phase 1: Agent Workflow Foundation**
- create `Lead`, `LeadPreference`, `LeadActivity`
- create `Agent`
- build agent portal
- add shortlist objects
- support native listings only

**Phase 2: Listing Canonicalization**
- introduce `CanonicalListing`
- separate source metadata
- update search/matching to use canonical layer

**Phase 3: NTREIS Integration**
- build connector
- ingest raw records
- map to canonical schema
- add sync jobs and compliance metadata

**Phase 4: Routing + Brokerage**
- add routing engine
- add team/brokerage queues
- add manager reporting

**Phase 5: Monetization + Scale**
- agent plans
- brokerage plans
- routing premium
- analytics and SLA tooling

**Architecture Risks**

1. Mixing MLS and native listing logic too early in one model.
2. Building agent UI before lead/routing ownership is defined.
3. Hard-coding matching logic into view/controller layers.
4. Ignoring source attribution and compliance metadata.
5. Scaling on SQLite while adding sync-heavy ingestion workflows.

**Recommended Technical Decisions**
- move to PostgreSQL before serious MLS work
- introduce canonical listing layer before feed ingestion
- treat agent portal as separate module with separate navigation and permissions
- implement lead/routing models before building visual dashboard polish
- make matching and routing services reusable, not template-bound

**Conclusion**

The right architecture is a modular Django-based platform with:
- a consumer lead-capture layer
- a canonical listing/search layer
- an MLS ingestion layer
- a separate agent operations layer
- a brokerage/admin oversight layer

That gives Listojo a credible path from local marketplace MVP to a lead-driven real estate operations platform.

If you want, I can next turn this into:
- a formal markdown architecture doc for your repo
- a database schema draft
- or an implementation roadmap by sprint.""",
    ),
]


def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def content_types_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
            '</Types>',
        ]
    )


def root_rels_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>',
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>',
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>',
            '</Relationships>',
        ]
    )


def app_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" ',
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">',
            '<Application>Microsoft Office Word</Application>',
            '<DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>',
            '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Title</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>',
            '<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>Document</vt:lpstr></vt:vector></TitlesOfParts>',
            '<Company>OpenAI Codex</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion>',
            '</Properties>',
        ]
    )


def core_xml() -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "".join(
        [
            xml_header(),
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" ',
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" ',
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
            '<dc:title>Listojo MLS Agent Portal Conversation</dc:title>',
            '<dc:creator>OpenAI Codex</dc:creator>',
            '<cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>',
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>',
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>',
            '</cp:coreProperties>',
        ]
    )


def word_rels_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
            '</Relationships>',
        ]
    )


def styles_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:rPr><w:sz w:val="22"/></w:rPr></w:style>',
            '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>',
            '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>',
            '</w:styles>',
        ]
    )


def paragraph_xml(text: str, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def blank_paragraph() -> str:
    return "<w:p/>"


def document_xml() -> str:
    parts = [
        paragraph_xml("Listojo MLS + Agent Portal Conversation", style="Title"),
        paragraph_xml("Transcript starting from the MLS feed and separate agent portal discussion.", style="Normal"),
        blank_paragraph(),
    ]
    for speaker, message in TRANSCRIPT:
        parts.append(paragraph_xml(f"{speaker}:", style="Heading1"))
        for line in message.splitlines():
            if line == "":
                parts.append(blank_paragraph())
            else:
                parts.append(paragraph_xml(line))
        parts.append(blank_paragraph())
    parts.append(
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    return "".join(
        [
            xml_header(),
            '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" ',
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" ',
            'xmlns:o="urn:schemas-microsoft-com:office:office" ',
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
            'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" ',
            'xmlns:v="urn:schemas-microsoft-com:vml" ',
            'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" ',
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" ',
            'xmlns:w10="urn:schemas-microsoft-com:office:word" ',
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ',
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" ',
            'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" ',
            'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" ',
            'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" ',
            'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">',
            "<w:body>",
            "".join(parts),
            "</w:body></w:document>",
        ]
    )


def build_docx(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml())
        zf.writestr("_rels/.rels", root_rels_xml())
        zf.writestr("docProps/app.xml", app_xml())
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("word/document.xml", document_xml())
        zf.writestr("word/styles.xml", styles_xml())
        zf.writestr("word/_rels/document.xml.rels", word_rels_xml())


if __name__ == "__main__":
    build_docx(OUT_PATH)
    print(OUT_PATH)
