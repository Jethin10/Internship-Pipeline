"""M9 — funnel analytics over the application store.

Pure read-side: turns the raw Application rows into an ordered funnel, conversion
ratios, and recent activity. No LLM, no network — just the SQLite store.

The funnel is ordered by how far an application has progressed. Note that a job
can be BOTH applied and emailed; status holds the latest stage, but history holds
the full trail, so 'emailed' is counted from history to avoid undercounting.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from piperline.store import Store

# Canonical funnel order — earliest stage first. 'skipped'/'error' are terminal
# side-branches shown separately, not part of the forward funnel.
FUNNEL_ORDER = [
    "discovered",
    "scored",
    "tailored",
    "ready",
    "applied",
    "emailed",
    "replied",
]
_SIDE = ["skipped", "error"]


@dataclass
class Funnel:
    # count of apps whose furthest-reached stage is at least this stage
    reached: dict[str, int] = field(default_factory=dict)
    side: dict[str, int] = field(default_factory=dict)  # skipped/error
    total: int = 0

    def conversion(self, frm: str, to: str) -> float | None:
        """Ratio of apps that reached `to` among those that reached `frm`."""
        base = self.reached.get(frm, 0)
        if not base:
            return None
        return self.reached.get(to, 0) / base


def _furthest_stage(app) -> str:
    """The deepest funnel stage this app ever reached (via current status + history).

    Using history (not just current status) means an application that was applied
    AND emailed counts toward both, and a 'ready' app that later got bumped back to
    'ready' after an apply escalation still counts its real high-water mark.
    """
    seen = {e.status for e in app.history} | {app.status}
    best = -1
    for s in seen:
        if s in FUNNEL_ORDER:
            best = max(best, FUNNEL_ORDER.index(s))
    return FUNNEL_ORDER[best] if best >= 0 else "discovered"


def build_funnel(store: Store) -> Funnel:
    apps = store.list_applications()
    f = Funnel(total=len(apps))
    # cumulative: reaching stage N implies having passed every earlier stage
    for stage in FUNNEL_ORDER:
        f.reached[stage] = 0
    for s in _SIDE:
        f.side[s] = 0

    for app in apps:
        # side-branch tallies use current status (terminal)
        if app.status in _SIDE:
            f.side[app.status] += 1
        # forward funnel: credit every stage up to the furthest reached
        idx = FUNNEL_ORDER.index(_furthest_stage(app))
        for i in range(idx + 1):
            f.reached[FUNNEL_ORDER[i]] += 1
    return f


@dataclass
class Activity:
    when: str
    status: str
    job: str
    note: str


def recent_activity(store: Store, limit: int = 15) -> list[Activity]:
    """Most recent status transitions across all applications, newest first."""
    events: list[tuple] = []
    for app in store.list_applications():
        job = store.get_job(app.job_id)
        label = f"{job.title} @ {job.company}" if job else app.job_id
        for e in app.history:
            events.append((e.at, e.status, label, e.note))
    events.sort(key=lambda t: t[0], reverse=True)
    return [
        Activity(when=at.strftime("%m-%d %H:%M"), status=st, job=lbl[:46], note=(nt or "")[:50])
        for at, st, lbl, nt in events[:limit]
    ]
