from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count, Q

from portal.models import Lead


OPEN_STATUSES = [
    'new',
    'contacted',
    'shortlist_ready',
    'shortlist_sent',
    'touring',
    'application_in_progress',
]


def least_loaded_agent() -> User | None:
    return (
        User.objects.filter(is_staff=True, is_active=True)
        .annotate(open_leads=Count('assigned_leads', filter=Q(assigned_leads__status__in=OPEN_STATUSES)))
        .order_by('open_leads', 'id')
        .first()
    )


def assign_to_agent(lead: Lead, agent: User) -> None:
    lead.assigned_agent = agent
    lead.save(update_fields=['assigned_agent', 'updated_at'])


def auto_assign(lead: Lead) -> User | None:
    agent = least_loaded_agent()
    if agent:
        assign_to_agent(lead, agent)
    return agent
