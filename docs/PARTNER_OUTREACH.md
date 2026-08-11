# Partner & Supply Outreach — Track A

Two emails that unblock everything downstream. Both are free to send and slow to
come back, so they go out **before** the code that depends on them.

Neither blocks Track B (the CSV importer) — that path needs no permission from
anyone.

**Status**

| # | To | Sent | Reply | Blocks |
|---|----|------|-------|--------|
| 1 | Broker → NTREIS | ☐ | ☐ | MLS adapter, search-page layout |
| 2 | RealPage RPX | ☐ | ☐ | PMS integration track |

---

## Email 1 — Broker / NTREIS

**Why it matters:** the IDX agreement is the gate on all MLS rental data. Two of
these four answers are product-shaping, not paperwork — if commingling is
restricted, the search results page needs rethinking *before* an adapter is
written, not after.

**To:** your agent's sponsoring broker
**Subject:** IDX sponsorship for listojo.com — four questions before we build

> Hi [Name],
>
> I'm building Listojo, a DFW rental marketplace. [Agent name] is on our team, and
> we'd like to display NTREIS rental listings on the site under a broker-sponsored
> IDX agreement.
>
> Before we write any integration code, I want to make sure I understand what the
> license actually permits. Four questions:
>
> 1. **Sponsorship** — would you be willing to sponsor an IDX agreement for
>    listojo.com, and what does NTREIS require from us to get there?
>
> 2. **Commingling** — our search results show MLS listings alongside listings
>    posted directly by individual landlords and property managers, in one ranked
>    list. Does NTREIS permit that mixing, or must MLS listings be displayed
>    separately?
>
> 3. **Secondary data use** — we run a price-estimate model trained on listing
>    data. Does the IDX license permit using MLS data for that, or is it limited
>    to consumer display only?
>
> 4. **Approved vendors** — does NTREIS maintain a list of approved IDX vendors?
>    We're deciding between building a direct RESO Web API client and using a
>    vendor such as SimplyRETS, and being on an approved list may matter for
>    compliance review.
>
> Happy to jump on a call if that's easier.
>
> Thanks,
> [Your name] · Listojo

**How the answers change the plan**

| Answer | Consequence |
|---|---|
| Commingling restricted | Redesign search results before building the MLS adapter |
| Secondary use not permitted | Exclude MLS rows from `train_valuation_model.py` |
| SimplyRETS on approved list | Reconsider buy-vs-build; otherwise build direct |
| Broker declines | MLS track pauses; partner feeds carry supply alone |

---

## Email 2 — RealPage RPX

**Why it matters:** certification is eligibility, not customers — each PM still
authorizes Listojo individually. Worth applying early because approval runs in
the background while supply gets built elsewhere.

**To:** RealPage Exchange / partner enquiries
**Subject:** Marketplace integration — Registered Vendor vs AppPartner

> Hi,
>
> I'm with Listojo, a rental marketplace launching in Dallas–Fort Worth. We'd like
> to receive property, unit, pricing, availability and media data from RealPage
> clients who choose to syndicate to us, and I'd like to understand the right
> path in.
>
> 1. **Tier** — for an ILS/marketplace use case like ours, is Registered Vendor or
>    AppPartner the appropriate track, and what distinguishes them in practice?
>
> 2. **Certification** — what does the process involve, what does it cost, and how
>    long does it typically take end to end?
>
> 3. **Prerequisites** — do you require existing mutual customers before a vendor
>    can apply, or can we certify first and onboard clients afterward?
>
> One follow-up if it's easy to answer: where API licensing is handled on the
> client's behalf, does cost scale with the number of client properties connected?
> That affects how we plan onboarding.
>
> Thanks,
> [Your name] · Listojo

**How the answers change the plan**

| Answer | Consequence |
|---|---|
| Registered Vendor is open | Apply now; certification runs alongside Track B |
| Mutual customers required first | Park it — sign PMs via CSV, revisit with names in hand |
| Per-client licensing cost | Recalculate per-partner unit economics before scaling |

---

## Not in these emails, on purpose

**Locator referral fees.** Deferred to Phase 2 — in Texas, being paid to locate
apartments generally requires a TREC license, and the current listojo.com Terms
of Service don't describe a locator model. Raising it now would complicate both
conversations for revenue that isn't being built yet.

When Phase 2 starts, that's a third conversation with the broker — a different
question from IDX sponsorship, and it needs the Terms page updated first.
