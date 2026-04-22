"""
Agent routing service.

All lead-assignment decisions must go through this module.
No view should implement its own agent-selection logic.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Count, Q

from portal.models import Lead


_OPEN_STATUSES = [
    'new', 'contacted', 'shortlist_ready', 'shortlist_sent',
    'touring', 'application_in_progress',
]


def least_loaded_agent() -> User | None:
    """
    Return the active staff agent with the fewest open leads.
    Returns None if no staff agents exist.
    """
    return (
        User.objects.filter(is_staff=True, is_active=True)
        .annotate(
            open_leads=Count(
                'assigned_leads',
                filter=Q(assigned_leads__status__in=_OPEN_STATUSES),
            )
        )
        .order_by('open_leads', 'id')
        .first()
    )


def assign_to_agent(lead: Lead, agent: User) -> None:
    """Assign a lead to a specific agent and save."""
    lead.assigned_agent = agent
    lead.save(update_fields=['assigned_agent', 'updated_at'])


def auto_assign(lead: Lead) -> User | None:
    """
    Assign a lead to the least-loaded agent automatically.
    Returns the assigned agent, or None if no agents are available.
    """
    agent = least_loaded_agent()
    if agent:
        assign_to_agent(lead, agent)
    return agent


def unassign(lead: Lead) -> None:
    """Remove agent assignment from a lead."""
    lead.assigned_agent = None
    lead.save(update_fields=['assigned_agent', 'updated_at'])
