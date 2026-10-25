"""Load editable prompts and search templates without caching."""
import json
from importlib.resources import files


def load_prompt(filename):
    # Imports stay local to avoid a cycle with the provider client.
    from research.clients import ResearchError
    if '/' in filename or '\\' in filename or filename.startswith('.'):
        raise ResearchError('Invalid prompt filename.')
    try:
        text = files(__package__).joinpath(filename).read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError) as exc:
        raise ResearchError(f'Cannot read prompt file: {filename}.') from exc
    if not text:
        raise ResearchError(f'Prompt file is empty: {filename}.')
    return text


def render_query(template_name, **values):
    from research.clients import ResearchError
    try:
        templates = json.loads(load_prompt('search_queries.json'))
        return templates[template_name].format_map(values)
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ResearchError(f'Invalid search query template: {template_name}. Check search_queries.json and its placeholders.') from exc
