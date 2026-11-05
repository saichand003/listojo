"""
Community photo headings — the Apartments.com model.

Photos are uploaded once, together, at the community level, and each carries a
two-part heading picked from dropdowns:

    Belongs to   Community | one of the community's floor plans
    Shows        pool, gym, … for Community; kitchen, bathroom, … for a plan

The gallery is grouped by that heading automatically — "Community – Swimming
Pool", then "2 Bedroom – Kitchen" — and each floor plan card on the public page
shows its own photos, which every unit on the plan inherits.
"""
from __future__ import annotations

from dataclasses import dataclass, field

COMMUNITY = 'community'


@dataclass
class PhotoGroup:
    """Every photo sharing one heading, plus where it starts in the gallery."""
    heading: str
    floor_plan: object = None
    photos: list = field(default_factory=list)
    start: int = 0


def belongs_to_label(floor_plan, floor_plans) -> str:
    """
    "2 Bedroom" — or "2 Bedroom · The Magnolia" when the community has two
    2-bedroom plans, so their photos never merge under one heading.
    """
    if floor_plan is None:
        return 'Community'
    twins = [fp for fp in floor_plans if fp.bedrooms == floor_plan.bedrooms]
    if len(twins) > 1:
        return f'{floor_plan.bedroom_label} · {floor_plan.name}'
    return floor_plan.bedroom_label


def belongs_to_options(floor_plans) -> list[tuple[str, str]]:
    """(value, label) for the "Belongs to" dropdown."""
    floor_plans = list(floor_plans)
    return [(COMMUNITY, 'Community')] + [
        (str(fp.pk), belongs_to_label(fp, floor_plans)) for fp in floor_plans
    ]


def group_photos(images, floor_plans) -> list[PhotoGroup]:
    """
    Photos grouped by heading in display order: community groups first, then
    each floor plan in plan order; inside each, the order of the Shows
    dropdown. Within a group, upload order holds.
    """
    from listings.models import CommunityImage

    floor_plans = list(floor_plans)
    plan_rank = {fp.pk: n for n, fp in enumerate(floor_plans)}
    plans_by_pk = {fp.pk: fp for fp in floor_plans}
    community_rank = {key: n for n, (key, _label) in enumerate(CommunityImage.COMMUNITY_SHOWS)}
    room_rank = {key: n for n, (key, _label) in enumerate(CommunityImage.ROOM_SHOWS)}

    def sort_key(photo):
        if photo.floor_plan_id is None:
            # Untagged photos predate headings; they lead, as they always have.
            return (0, 0, community_rank.get(photo.shows, -1))
        return (1, plan_rank.get(photo.floor_plan_id, len(plan_rank)),
                room_rank.get(photo.shows, len(room_rank)))

    groups: list[PhotoGroup] = []
    by_heading: dict[str, PhotoGroup] = {}
    for photo in sorted((p for p in images if p.image), key=sort_key):
        plan = plans_by_pk.get(photo.floor_plan_id)
        belongs = belongs_to_label(plan, floor_plans)
        shows = photo.shows_label
        heading = f'{belongs} – {shows}' if shows else belongs
        group = by_heading.get(heading)
        if group is None:
            group = by_heading[heading] = PhotoGroup(heading=heading, floor_plan=plan)
            groups.append(group)
        group.photos.append(photo)

    index = 0
    for group in groups:
        group.start = index
        index += len(group.photos)
    return groups


def resolve_heading(community, belongs: str, shows: str, custom_label: str = ''):
    """
    Turn submitted dropdown values into (floor_plan, shows, custom_label).

    Anything the dropdowns could not have produced — another community's floor
    plan, a room tag on a community photo — falls back to the community and a
    blank tag rather than failing the whole upload.
    """
    from listings.models import CommunityImage

    floor_plan = None
    if belongs and belongs != COMMUNITY and belongs.isdigit():
        floor_plan = community.floor_plans.filter(pk=int(belongs)).first()

    allowed = {key for key, _label in CommunityImage.shows_choices_for(floor_plan)}
    shows = shows if shows in allowed else ''
    custom_label = custom_label.strip()[:100] if shows == 'other' else ''
    return floor_plan, shows, custom_label
