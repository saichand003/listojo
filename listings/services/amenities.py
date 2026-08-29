"""
The amenity vocabulary and the shared/private split it hangs off.

One definition, three consumers: the create-listing picker renders its groups
from here, the backfill command classifies legacy `tags` with it, and the
detail page reads the two columns those two write.

The split is shared-versus-private, not indoor-versus-outdoor — see
AmenityDisplayMixin for why. A third bucket exists because the picker's
vocabulary was never purely about facilities: "pet-friendly" and "no deposit"
are terms of the lease, not things in the building, and putting them in a
catalogue of amenities makes that catalogue mean less. They stay searchable via
`tags` and are simply not catalogued.
"""

#: Shared with other residents, or reached outside the tenant's own front door.
SHARED_AMENITY_TAGS = (
    'parking',
    'gym',
    'pool',
    'near transit',
    'EV charging',
    'storage',
    'rooftop access',
)

#: Behind the tenant's own door, theirs alone.
PRIVATE_AMENITY_TAGS = (
    'furnished',
    'washer/dryer',
    'balcony',
    'AC',
    'heating',
    'wifi',
    'dishwasher',
    'hardwood floors',
)

#: Terms of the lease. Searchable, deliberately not catalogued.
POLICY_TAGS = (
    'pet-friendly',
    'utilities included',
    'no deposit',
)

#: The picker's full vocabulary, in display order.
PICKER_GROUPS = (
    ('Shared & building', SHARED_AMENITY_TAGS),
    ('In-unit & private', PRIVATE_AMENITY_TAGS),
    ('Lease terms',       POLICY_TAGS),
)

_SHARED_LOOKUP  = {t.lower(): t for t in SHARED_AMENITY_TAGS}
_PRIVATE_LOOKUP = {t.lower(): t for t in PRIVATE_AMENITY_TAGS}


def classify_tags(tags):
    """
    Split an iterable of tags into (shared, private), dropping the rest.

    Matching is case-insensitive because `tags` is free text — the picker
    writes 'AC' but a hand-typed row may say 'ac'. Anything unrecognised is
    dropped rather than guessed at: a tag the vocabulary has never heard of is
    as likely to be 'no smoking' as it is to be an amenity, and a wrong card is
    worse than a missing one. Order follows the vocabulary, not the input, so
    two listings with the same amenities render the same chip order.
    """
    seen = {t.strip().lower() for t in tags if t and t.strip()}
    shared  = [orig for low, orig in _SHARED_LOOKUP.items() if low in seen]
    private = [orig for low, orig in _PRIVATE_LOOKUP.items() if low in seen]
    return shared, private
