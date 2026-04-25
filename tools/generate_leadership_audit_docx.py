from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_Leadership_Audit_And_90_Day_Roadmap.docx")


CONTENT = """Listojo Leadership Audit And 90-Day Roadmap

Red / Yellow / Green Leadership Audit

Business Analyst
- Green
  - Clear move toward a monetizable lead + agent workflow model
  - Product now has a visible path from consumer inquiry to agent action
  - DFW wedge still makes sense
- Yellow
  - Monetization logic is still more implied than operationalized
  - Native marketplace, agent workflow, and future MLS strategy are not yet fully unified
- Red
  - Lead ownership and assignment are not fully productized
  - Referral attribution model does not yet exist in code

CEO
- Green
  - Strategy is stronger than before
  - The new agent portal direction is commercially more serious than a generic marketplace play
- Yellow
  - Product scope is expanding quickly
  - Strong risk of building adjacent systems before finishing one profitable loop
- Red
  - If the company adds MLS, routing, subscriptions, and referral logic before hardening the core workflow, execution risk rises sharply

CTO
- Green
  - New domain models (Lead, LeadPreference, Shortlist) are a good sign
  - Platform direction is now more architecture-worthy
- Yellow
  - Logic is still concentrated in views
  - Matching logic is duplicated between user and agent surfaces
  - Model validation is still weak
- Red
  - No shared service boundaries yet for matching, routing, lifecycle rules, or shortlist orchestration
  - Complexity is increasing faster than architecture maturity

Security Director
- Green
  - Some security awareness exists
  - Security hardening flags are present for non-debug mode
  - File upload type validation improved
- Yellow
  - Inquiry email flow exists but without broader abuse controls
  - Guest interactions remain open surfaces
- Red
  - Insecure fallback SECRET_KEY
  - No rate limiting
  - No anti-abuse layer
  - No audit trail for lead/agent actions
  - Not suitable yet for serious production handling of lead/contact data

Infrastructure Architect
- Green
  - Current app is still simple enough to evolve without a massive migration effort
- Yellow
  - Email, lead creation, and portal workflows are now stressing the limits of the current single-node setup
- Red
  - SQLite remains a major blocker
  - No queue/job layer
  - No object storage
  - No observability or deployment-grade operational story

Product Manager
- Green
  - Product shape is much stronger now
  - Agent portal makes the roadmap more coherent
  - The lead model is a real step toward assisted conversion
- Yellow
  - UX and system behavior are not fully aligned
  - User curation and agent curation are inconsistent
- Red
  - Lead-routing and assignment are not complete enough to support the value proposition shown by the UI

QA Manager
- Green
  - Core workflows are now concrete enough to define a real QA strategy
- Yellow
  - Current state likely depends heavily on manual testing
- Red
  - No meaningful test suite
  - High regression risk across listings, leads, shortlists, permissions, and portal behavior

Overall Audit
- Business / strategy: Yellow-Green
- Product direction: Yellow-Green
- Engineering: Yellow
- Security: Red
- Infrastructure: Red
- QA: Red

The product direction is stronger than the platform discipline underneath it.

Prioritized Action Plan By Role

1. CEO Priorities
Highest priority:
- Pick the primary business loop for the next phase:
  - consumer inquiry -> lead -> agent action -> shortlist -> conversion
- Freeze major adjacent expansion until that loop works consistently
- Define operating model clearly:
  - self-serve only
  - hybrid self-serve + agent assist
  - referral/locator business
- Define ownership rules:
  - who owns leads
  - who can claim leads
  - how success/revenue gets attributed

CEO recommendation:
- Do not start MLS integration until internal lead workflow and assignment logic are reliable.

2. Business Analyst Priorities
Highest priority:
- Document the target funnel explicitly:
  - visitor
  - search user
  - inquiry lead
  - assigned lead
  - shortlist sent
  - tour/application
  - closed
- Define monetization points:
  - subscription
  - referral fee
  - listing boost
  - brokerage plans
- Define KPI framework:
  - lead creation rate
  - assignment rate
  - response time
  - shortlist send rate
  - lead-to-tour rate
  - close / referral revenue rate

BA recommendation:
- Build the measurement framework before adding more channel complexity.

3. CTO Priorities
Highest priority:
- Extract shared services from views:
  - matching_service
  - lead_routing_service
  - listing_visibility_service
  - shortlist_service
- Add model-level or form-level validation rules for listing lifecycle and category-specific fields
- Remove duplication between consumer match logic and agent-side recommendation logic
- Introduce clearer domain boundaries:
  - listings
  - leads
  - shortlists
  - routing

CTO recommendation:
- Next technical milestone should be architecture cleanup, not feature volume.

4. Security Director Priorities
Highest priority:
- Remove insecure default secret fallback in production path
- Add rate limiting on:
  - login
  - register
  - inquiry submit
  - guest chat
- Add abuse controls:
  - bot protection / CAPTCHA where needed
  - basic throttling
  - anomaly logging
- Add audit logging for:
  - lead assignment
  - shortlist creation/sending
  - status changes
- Review PII handling for leads and inquiry/contact data

Security recommendation:
- No serious production rollout of agent lead workflows until abuse and audit basics exist.

5. Infrastructure Architect Priorities
Highest priority:
- Migrate from SQLite to PostgreSQL
- Move media off local disk to object storage
- Introduce background jobs for:
  - emails
  - future MLS sync
  - future reminders/tasks
- Add logging and monitoring baseline
- Separate dev/staging/prod configuration more formally

Infrastructure recommendation:
- This is the minimum platform upgrade required before scaling leads or adding MLS.

6. Product Manager Priorities
Highest priority:
- Finish one workflow end to end:
  - inquiry creates lead
  - lead gets assigned
  - agent sees it
  - shortlist gets created/sent
  - status is updated coherently
- Align terminology and states across:
  - backend logic
  - templates
  - filters
  - analytics
- Define “working” consistently
- Make agent portal behavior match actual system capability

PM recommendation:
- Next sprint should be coherence and completion, not new concepts.

7. QA Manager Priorities
Highest priority:
- Introduce core test coverage immediately for:
  - listing creation
  - listing approval / visibility
  - expiry behavior
  - inquiry -> lead creation
  - agent permission/access rules
  - shortlist creation and send
  - lead status updates
- Create manual regression checklist for release candidates
- Add permission-focused tests for:
  - agent vs admin visibility
  - lead detail access
  - assignment flows

QA recommendation:
- Treat lead/agent workflow as a critical path and test it like a product, not a prototype.

Recommended Execution Order
1. Define business loop and ownership model
2. Fix lead assignment / workflow completeness
3. Add tests around current critical flows
4. Upgrade infrastructure baseline
5. Add security controls and audit logging
6. Refactor shared services
7. Only then add MLS / referral expansion

90-Day Action Roadmap

Days 1-30: Stabilize the Current Core Loop

Objectives
- Make the existing inquiry -> lead -> agent workflow real and measurable
- Remove the biggest trust and execution gaps
- Put basic QA and security controls in place

CEO / BA
- Finalize the primary business loop and freeze adjacent scope
- Define lead ownership rules
- Define lead statuses and business definitions for each
- Define success metrics and weekly dashboard KPIs

Product / Engineering
- Implement automatic or queue-based lead assignment
- Fix inconsistent “working” states across views/templates
- Align agent-side and user-side matching logic at a functional level
- Enforce listing visibility rules consistently, including expiry
- Add model/form validation for listing lifecycle and category-specific fields

Security / QA
- Add rate limiting to login, inquiry, registration, and guest chat
- Remove unsafe production fallbacks and tighten env requirements
- Add core tests for inquiry, lead creation, assignment, and permissions
- Create a manual regression checklist

Infrastructure
- Prepare PostgreSQL migration plan
- Decide target hosting/storage pattern for media and email

Deliverables by Day 30
- Assigned leads actually visible to the right agents
- Basic automated tests on critical flows
- Security hardening for public input endpoints
- Single agreed business funnel

Days 31-60: Harden Platform and Workflow Reliability

Objectives
- Improve architecture quality
- Reduce regression risk
- Make the portal operationally dependable

CEO / PM
- Review KPI trends from the first stabilized loop
- Confirm whether the hybrid self-serve + agent-assisted model remains primary
- Define qualification rules for high-intent leads

Engineering / CTO
- Extract shared services:
  - matching_service
  - lead_routing_service
  - shortlist_service
  - listing_visibility_service
- Refactor duplicated logic out of templates/views where feasible
- Improve shortlist lifecycle handling
- Add event logging for assignment, status changes, and shortlist actions

Infrastructure / Security
- Migrate to PostgreSQL in staging or target environment
- Add structured logging and basic monitoring
- Plan object storage for media
- Add audit trail for agent actions

QA
- Expand automated coverage to shortlist flows, expiry logic, status transitions, and access control
- Introduce role-based regression testing

Deliverables by Day 60
- Cleaner service boundaries for critical logic
- PostgreSQL-ready or migrated environment
- Audit/event trail for lead operations
- Higher confidence release process

Days 61-90: Prepare for Scale and Next-Phase Expansion

Objectives
- Make the platform ready for MLS, referral monetization, or agent subscriptions
- Finish the foundation before major expansion

CEO / BA / PM
- Decide go/no-go criteria for MLS integration
- Decide initial monetization path:
  - agent subscription
  - referral fee tracking
  - brokerage/team plan
- Finalize attribution requirements for future referral revenue

CTO / Engineering
- Complete production-grade data and workflow baseline
- Implement lead qualification scoring if still needed
- Improve agent portal reporting and operational visibility
- Standardize internal APIs/boundaries for future integrations

Infrastructure / Security
- Move media to object storage if not already done
- Add background jobs for email and future syncs
- Finalize backup/recovery and environment separation
- Review compliance posture for lead/contact data and future MLS onboarding

QA
- Run full regression on consumer + agent + admin surfaces
- Define acceptance criteria for MLS or referral expansion
- Add release sign-off checklist

Deliverables by Day 90
- Stable lead-and-agent platform foundation
- Production-ready baseline for data, logging, and security
- Decision-ready state for MLS and referral expansion
- Leadership visibility into actual conversion performance

Bottom Line
The next 90 days should not be about adding as many new features as possible. They should be about converting Listojo from a promising MVP into a reliable lead-and-agent platform with enough discipline to support future MLS, referral, and subscription models."""


def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def content_types_xml() -> str:
    return "".join([
        xml_header(),
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
        '</Types>',
    ])


def root_rels_xml() -> str:
    return "".join([
        xml_header(),
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>',
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>',
        '</Relationships>',
    ])


def app_xml() -> str:
    return "".join([
        xml_header(),
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" ',
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">',
        '<Application>Microsoft Office Word</Application>',
        '<DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>',
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Title</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>',
        '<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>Document</vt:lpstr></vt:vector></TitlesOfParts>',
        '<Company>OpenAI Codex</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion>',
        '</Properties>',
    ])


def core_xml() -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "".join([
        xml_header(),
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" ',
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" ',
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        '<dc:title>Listojo Leadership Audit And 90-Day Roadmap</dc:title>',
        '<dc:creator>OpenAI Codex</dc:creator>',
        '<cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>',
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>',
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>',
        '</cp:coreProperties>',
    ])


def word_rels_xml() -> str:
    return "".join([
        xml_header(),
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
        '</Relationships>',
    ])


def styles_xml() -> str:
    return "".join([
        xml_header(),
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:rPr><w:sz w:val="22"/></w:rPr></w:style>',
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>',
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>',
        '</w:styles>',
    ])


def paragraph_xml(text: str, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def document_xml() -> str:
    parts = [paragraph_xml("Listojo Leadership Audit And 90-Day Roadmap", style="Title"), paragraph_xml("")]
    for line in CONTENT.splitlines():
        parts.append(paragraph_xml(line))
    parts.append('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    return "".join([
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
        "<w:body>", "".join(parts), "</w:body></w:document>",
    ])


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
