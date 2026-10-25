"""Shared evidence utilities."""


def unique_sources(sources):
    # Preserve the first observation/category when a URL appears in several searches.
    return list({s['id']: s for s in reversed(sources)}.values())
