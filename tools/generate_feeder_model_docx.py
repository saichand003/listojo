from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_Feeder_App_Referral_Model.docx")


CONTENT = """**Feeder-App Business Model Blueprint**

**1. Core Positioning**
Listojo should first position itself as a **lead capture and matching platform** for renters, with agent-assisted conversion layered on top.

Best near-term positioning:
- `Find the right apartment faster, then get matched with a real expert who helps you close.`

This is stronger than trying to market Listojo immediately as:
- a full locator company
- a pure MLS portal
- or a Craigslist/Zillow replacement

**2. What Listojo Does in the Feeder Model**
Listojo’s job in this model is to generate and qualify demand.

That means:
- capture renter intent through guided search
- structure budget, area, move date, beds, amenities, and preferences
- show relevant inventory
- identify serious leads
- route those leads to agents or locator partners
- track downstream conversion

So Listojo becomes:
- acquisition engine
- qualification engine
- shortlist/matching engine
- lead routing layer

**3. Who the Customers Are**
There are really 3 customer groups:

- `Renters`
  - want speed
  - want relevant matches
  - want less spam / less manual search

- `Agents / Locators`
  - want qualified renter leads
  - want workflow tools
  - want conversion visibility

- `Brokerages / Partners`
  - want scalable lead flow
  - want routing and reporting
  - want accountability on conversions

**4. Revenue Options in the Feeder Model**
Most realistic early monetization options:

- lead referral split with locator partners
- monthly subscription for agents using the portal
- premium lead routing / exclusivity
- brokerage plans for team access
- success-based payout on closed leases where contractually allowed

**5. Best Early Operating Model**
Start with a hybrid approach:

- Listojo captures and qualifies renter demand
- small number of trusted locator partners or agents receive leads
- Listojo tracks shortlist, tours, applications, and lease outcomes
- commission/revenue is shared on successful conversions

This reduces your initial operational burden while still proving the model.

**6. Why this works**
This model fits Listojo’s current strengths:
- guided search
- lead structuring
- match logic
- emerging agent portal concept

It avoids the hardest part too early:
- becoming a full concierge locator business from day one

**Referral Revenue Workflow Design**

This is the minimum viable referral-money workflow.

**Stage 1: Lead Capture**
Trigger sources:
- guided search completion
- inquiry on listing
- saved-search request
- chat/contact request
- “get help from an agent” CTA

System creates:
- `Lead`
- `LeadPreferences`
- source attribution record

Key fields:
- name
- phone/email
- city preference
- budget
- beds/baths
- move timeline
- property type
- must-haves
- source channel

**Stage 2: Lead Qualification**
System scores lead quality.

Example qualification factors:
- complete preferences
- realistic budget
- timeline within 30-90 days
- active engagement with listings
- response readiness
- repeated visits / shortlist clicks

Output:
- low / medium / high intent
- qualification score
- routing priority

**Stage 3: Routing**
Lead is routed to:
- partner locator
- in-house Listojo agent
- brokerage queue
- unassigned queue if manual review needed

Routing rules can use:
- city
- price range
- specialty
- language/community fit
- agent capacity
- lead score

System logs:
- who got the lead
- when
- routing basis
- ownership status

**Stage 4: Shortlist / Agent Engagement**
Assigned agent:
- reviews lead profile
- builds shortlist
- contacts renter
- schedules tours
- updates status

Lead stages:
- new
- contacted
- shortlist sent
- touring
- applied
- approved
- signed
- lost

**Stage 5: Attribution**
This is the most important part if you want referral money.

You need to track:
- which agent worked the lead
- which listings were recommended
- whether the renter applied through the referred path
- whether the renter listed the agent/company on the application
- whether a lease was signed
- payout amount
- payout status

Without this, you have activity but not reliable revenue.

**Stage 6: Commission Capture**
Once the lease closes:
- property/brokerage pays locator commission
- split is calculated
- Listojo records:
  - gross referral amount
  - partner share
  - platform share
  - payment date
  - payment status

**Suggested Revenue Event Model**
You should track milestone events like this:

- `lead_created`
- `lead_assigned`
- `shortlist_sent`
- `tour_booked`
- `application_started`
- `application_submitted`
- `lease_signed`
- `commission_confirmed`
- `commission_received`
- `revenue_distributed`

That gives you a full revenue pipeline, not just raw lead counts.

**Key Risks in Referral Workflow**
1. Lead attribution is not enforced.
2. Agents work leads outside the platform and you lose visibility.
3. Renters apply without naming the correct referring party.
4. No contract/payout structure exists with partner agents or brokerages.
5. “Leads” are low quality and never progress far enough to monetize.

**Best Design Principle**
Treat referral revenue as a **tracked conversion pipeline**, not an informal side effect.

**Comparison Table: Listojo vs Smart City vs What Listojo Must Build**

| Area | Listojo Today | Smart City-Style Model | What Listojo Must Build |
|------|---------------|------------------------|--------------------------|
| Lead capture | Partial, promising | Strong, concierge-driven | Better intent capture and “get agent help” conversion |
| Inventory depth | Limited today | Broad apartment inventory access | NTREIS/MLS and/or partner inventory normalization |
| Human assistance | Minimal today | Core part of product | In-house agents or strong partner network |
| Workflow for agents | Not mature yet | Central to business | Separate agent portal with lead stages, shortlist, tasks |
| Revenue model | Early / unclear | Referral/locator commission-driven | Attribution, payout tracking, referral agreements |
| Brand trust | Early-stage | Established in category | Consistent experience, verified support, conversion proof |
| Ops maturity | Low | High service-operating model | Lead routing, SLAs, concierge operations |
| Conversion tracking | Limited | Likely operationally mature | Application-to-lease attribution pipeline |
| Monetization | Mostly conceptual | Proven referral business | Commission capture + agent SaaS + brokerage plans |
| Replaceability | Not ready | Existing benchmark | Would require software + service business execution |

**Interpretation of the Table**

**Where Listojo is already useful**
- structured search intent
- potential matching layer
- local-market product flexibility
- possibility of agent workflow integration

**Where Smart City is ahead**
- operational service model
- human-assisted conversion
- referral monetization maturity
- trust and process

**What Listojo must build to replace Smart City**
- robust agent portal
- lead assignment and ownership rules
- end-to-end shortlist and follow-up workflow
- referral attribution infrastructure
- property/partner payout relationships
- concierge operations, not just software

**Strategic Recommendation**

If the goal is revenue soon, the smartest path is:

**Step 1**
Build Listojo as a **feeder app + agent portal**

**Step 2**
Prove:
- qualified leads are generated
- agents use the workflow
- shortlists get sent
- leases can be attributed

**Step 3**
Layer in referral revenue and agent subscriptions

**Step 4**
Only after that, decide whether to evolve into a full Smart City replacement

That sequence is lower risk, faster to validate, and much more realistic than trying to become a full locator platform immediately.

**Bottom Line**
- `Feeder app`: highly realistic
- `Referral money`: realistic if attribution and partner ops are built
- `Full replacement of Smart City`: possible long term, but only if Listojo becomes both a software platform and a real service business"""

CONTENT += """

**Hybrid Self-Serve + Agent-Assisted Model**

Yes. That is actually the strongest model.

What you are describing is a **dual-path product**:

- user gets curated results directly
- agent gets the same lead context and curated shortlist potential
- user can continue self-serve
- or opt into agent help when they want support

That is better than forcing agent involvement too early.

**Why this model is strong**

It gives Listojo two value propositions at the same time:

**For users**
- fast, smart, self-serve discovery
- less friction
- no pressure to talk to an agent immediately
- trust builds before human handoff

**For agents**
- pre-qualified leads
- structured preference data
- shortlist-ready context
- better conversion opportunities than cold inbound leads

So Listojo becomes:
- a consumer-facing smart search product
- plus an agent-assist conversion layer
- plus a referral/revenue engine when users choose help

That is much more scalable than a pure concierge-only model.

**Best product structure**

You should think of it as:

**Layer 1: Self-serve curation**
User completes guided search and gets:
- ranked listings
- match scores
- explanation tags
- shortlist suggestions

**Layer 2: Optional assisted curation**
User sees CTA like:
- `Want expert help with better matches?`
- `Talk to a Listojo agent`
- `Get a curated shortlist from a local expert`

If the user opts in:
- lead is routed to agent
- agent sees the same profile and preferences
- agent refines shortlist
- agent handles tours / follow-up / conversion

**Why this is better than immediate agent routing**
If every user is forced into agent flow:
- low-intent users create noise
- agents waste time
- users may bounce if they just wanted to browse
- your CAC-to-conversion efficiency gets worse

If users first self-serve and then escalate:
- only stronger-intent users request help
- agents get warmer leads
- users feel more in control
- conversion quality should improve

**Best business implication**
This gives you 3 possible monetization paths from one product:

1. **Self-serve search product**
Potential future monetization:
- sponsored listings
- premium visibility
- premium search placement

2. **Agent-assisted conversion**
Monetization:
- referral fees
- agent subscriptions
- brokerage plans
- premium routing

3. **Hybrid conversion funnel**
Users browse alone first, then request help later.
This is probably your highest-quality revenue path.

**What this means architecturally**
You need one shared matching system feeding two surfaces:

**User surface**
- curated search results
- match explanations
- save / compare / inquire
- “get agent help” CTA

**Agent surface**
- lead profile
- same preferences
- same or improved matched listings
- shortlist creation
- communication and pipeline tracking

So the matching engine should not be duplicated.
It should generate:
- consumer-facing recommendations
- agent-facing shortlist candidates

Same engine, different UI and permissions.

**Important design rule**
Do not make agent curation feel like a completely different product logic.
It should feel like:

- user sees smart recommendations
- agent sees those recommendations plus extra tools, notes, and workflow controls

That consistency is important for trust and explainability.

**Best funnel design**

1. User lands on Listojo.
2. User completes search / guided search.
3. Listojo shows curated results.
4. User can:
   - save listings
   - message lister
   - continue browsing
   - request agent help
5. If user requests help:
   - lead becomes high-priority routed lead
   - agent gets profile + activity + current shortlist context
6. Agent sends curated shortlist / schedules next steps.
7. If lease closes, referral revenue can be captured.

**What to call this model**
This is best described as:

- `self-serve first, agent-assisted when needed`
- or
- `hybrid curated search + assisted conversion model`

That is a very strong product concept.

**Why this may outperform Smart City-style forced concierge**
Smart City-style models are strong for high-touch conversion, but they are less product-native.
Your version can be stronger because:
- self-serve users are not blocked
- agents only engage when there is real intent
- software handles first-pass curation
- humans handle high-value conversion moments

That is usually a better technology business.

**Main thing you must get right**
You need a clear lead-state split:

- `anonymous browsing`
- `registered self-serve`
- `high-intent but no agent requested`
- `agent requested`
- `agent assigned`
- `conversion tracked`

If you don’t structure those states clearly, agent workflows will become noisy.

**Bottom line**
Yes, this is the right model.

It makes Listojo:
- useful even without agents
- more scalable than pure concierge
- more monetizable than pure classifieds
- and better suited to referral revenue because agent help becomes an opt-in escalation point, not a forced first step"""


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
            '<dc:title>Listojo Feeder App Referral Model</dc:title>',
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
            '</w:styles>',
        ]
    )


def paragraph_xml(text: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def document_xml() -> str:
    lines = CONTENT.splitlines()
    parts = [paragraph_xml("Listojo Feeder App Referral Model")]
    parts.append(paragraph_xml(""))
    for line in lines:
        parts.append(paragraph_xml(line))
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
