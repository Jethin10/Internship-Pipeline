"""Outreach — find hiring contacts and draft personalized messages.

Email discovery + draft generation live here. Actual sending (Gmail/SMTP) is a
later, gated milestone (M8); for now drafts are queued for human approval.
"""
from piperline.outreach.discovery import Contact, best_contact, discover_contacts

__all__ = ["Contact", "discover_contacts", "best_contact"]
