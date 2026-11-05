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
#: The first seven are the original vocabulary and keep their spelling, because
#: `tags` is searched with icontains and saved searches already hold them.
SHARED_AMENITY_TAGS = (
    'parking',
    'gym',
    'pool',
    'near transit',
    'EV charging',
    'storage',
    'rooftop access',
    # Building / complex
    'elevator',
    'on-site laundry',
    'package lockers',
    'gated entry',
    'security',
    'concierge',
    'coworking space',
    'clubhouse',
    'bike storage',
    'dog park',
    'BBQ area',
    'playground',
    # A house's own grounds — outside the door, so not "in-unit"
    'garage',
    'driveway',
    'yard',
    'fenced yard',
    # A room in a shared home
    'shared kitchen',
    'shared living room',
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
    'walk-in closet',
    'stainless appliances',
    'granite counters',
    'ceiling fans',
    'fireplace',
    'smart thermostat',
    'high ceilings',
    'natural light',
    'patio',
    # A room in a shared home
    'private bathroom',
    'private entrance',
    'lock on door',
    'furnished room',
)

#: Terms of the lease. Searchable, deliberately not catalogued.
POLICY_TAGS = (
    'pet-friendly',
    'utilities included',
    'no deposit',
    'month-to-month',
    'short-term OK',
    'sublease',
    'lease takeover',
    'flexible move-in',
    'smoke-free',
)

#: The picker's full vocabulary, in display order.
PICKER_GROUPS = (
    ('Shared & building', SHARED_AMENITY_TAGS),
    ('In-unit & private', PRIVATE_AMENITY_TAGS),
    ('Lease terms',       POLICY_TAGS),
)

#: Which kinds of listing a chip makes sense for. A single-family house has no
#: elevator and a private room's renter does not get the garage, so the picker
#: hides chips that do not fit what the seller chose. A tag not listed here is
#: shown for every kind. Contexts:
#:   building — apartment, condo, loft, studio, townhouse (whole unit)
#:   house    — house, single-family, basement, trailer, ranch (whole property)
#:   room     — a private room in a shared home (accommodation_type = room)
#: Hiding is presentational only: a chip already selected stays visible, so
#: switching the property type never silently drops a pick.
TAG_CONTEXTS = {
    'rooftop access':     ('building',),
    'elevator':           ('building', 'room'),
    'on-site laundry':    ('building', 'room'),
    'package lockers':    ('building', 'room'),
    'gated entry':        ('building', 'house'),
    'concierge':          ('building',),
    'coworking space':    ('building',),
    'clubhouse':          ('building',),
    'dog park':           ('building',),
    'BBQ area':           ('building',),
    'playground':         ('building',),
    'garage':             ('house', 'room'),
    'driveway':           ('house', 'room'),
    'yard':               ('house', 'room'),
    'fenced yard':        ('house',),
    'patio':              ('house', 'building'),
    'shared kitchen':     ('room',),
    'shared living room': ('room',),
    'private bathroom':   ('room',),
    'private entrance':   ('room', 'house'),
    'lock on door':       ('room',),
    'furnished room':     ('room',),
    'lease takeover':     ('building', 'house'),
}


def picker_groups():
    """
    PICKER_GROUPS with each tag paired to its contexts, for the template.

    Yields (label, [(tag, 'ctx ctx'), ...]); an empty context string means the
    chip shows for every kind of listing.
    """
    return [
        (label, [(t, ' '.join(TAG_CONTEXTS.get(t, ()))) for t in tags])
        for label, tags in PICKER_GROUPS
    ]


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
