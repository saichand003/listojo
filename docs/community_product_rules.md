# Community Product Rules

## Entity rules

- A `Community` is a multi-unit property or building marketed as one destination.
- A `FloorPlan` belongs to exactly one `Community`.
- A `Unit` belongs to exactly one `FloorPlan`.
- A plain `Listing` is not a community.

## Discovery rules

- Community cards can appear in the discovery grid.
- Units do not appear as standalone discovery cards through the community model.
- Listing-based child units are legacy records and are not part of the supported community workflow.

## Creation rules

- Owners create communities from `create_community`.
- Owners add floor plans and units from `edit_community`.
- Owners create ordinary listings from `create_listing`.
- Owners must not create new communities through `Listing.is_community`.

## Reporting rules

- Community tour requests must link back to `Lead.community`.
- Community engagement is measured via `UserListingEvent.community`.
- BI questions should be answerable from this model:
  - Which community generated a lead?
  - Which communities are most viewed?
  - Which communities receive the most tour requests?
