# Community Release Scope

## Current release posture

- Status: limited release / beta
- Source of truth for communities: `Community`, `FloorPlan`, `Unit`
- Deprecated path: `Listing.is_community` and parent-child listing communities are legacy-only and should not be used for new inventory

## In-scope

- Community creation and editing
- Floor plan and unit management under a community
- Discovery of communities in the main grid
- Community lead capture and tour requests
- Community impression, click, and tour-request event tracking

## Out of scope

- Migrating historic listing-based communities into the dedicated community model
- Full BI dashboards outside owner/community management and Django admin
- Automated abuse prevention beyond basic endpoint throttling

## Release gate

- Run migrations before deploy
- Verify `community_detail`, `create_community`, and `my_communities`
- Verify community events and leads appear in admin
- Treat this as beta until legacy listing-based community records are migrated or retired
