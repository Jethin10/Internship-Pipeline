"""Part A — Job Board Aggregator.

Discovers openings and normalizes them into our shared JobPost schema. v1 is a
thin, faithful wrapper around JobSpy (MIT); career-page (ATS) crawlers plug in
here later behind the same `discover()` interface.
"""
from piperline.aggregator.service import DiscoverQuery, discover

__all__ = ["discover", "DiscoverQuery"]
