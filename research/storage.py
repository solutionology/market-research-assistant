"""Only completed live briefings belong in the saved-search library."""
import re
from pathlib import Path
from research.models import Briefing

DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[1] / 'runs'


def load_saved_search(run_id, runs_dir=None):
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Invalid saved-search ID.')
    path = Path(runs_dir or DEFAULT_RUNS_DIR) / run_id / 'briefing.json'
    brief = Briefing.model_validate_json(path.read_text()).model_dump(mode='json')
    if brief['mode'] != 'live' or brief['run_id'] != run_id or len(brief['competitors']) != 3:
        raise ValueError('This is not a completed live search.')
    return brief


def list_saved_searches(runs_dir=None):
    root = Path(runs_dir or DEFAULT_RUNS_DIR)
    searches = []
    for path in root.glob('*/briefing.json'):
        try:
            brief = load_saved_search(path.parent.name, root)
        except (OSError, ValueError):
            continue
        searches.append(dict(run_id=brief['run_id'], generated_at=brief['generated_at'],
                             company=brief['request']['company'],
                             competitors=brief['request']['competitor_names']))
    return sorted(searches, key=lambda row: row['generated_at'], reverse=True)


def load_review(run_id, runs_dir=None):
    """Reviews belong only to existing completed live searches."""
    from research.models import HumanReview
    load_saved_search(run_id, runs_dir)
    path = Path(runs_dir or DEFAULT_RUNS_DIR) / run_id / 'review.json'
    if not path.exists():
        return None
    return HumanReview.model_validate_json(path.read_text()).model_dump(mode='json')


def save_review(run_id, review, runs_dir=None):
    from research.models import HumanReview
    from research.clients import utcnow
    import json
    import uuid
    load_saved_search(run_id, runs_dir)
    result = HumanReview.model_validate({**review, 'reviewed_at': utcnow()}).model_dump(mode='json')
    folder = Path(runs_dir or DEFAULT_RUNS_DIR) / run_id
    temporary = folder / f'.review-{uuid.uuid4().hex}.tmp'
    try:
        temporary.write_text(json.dumps(result, indent=2))
        temporary.replace(folder / 'review.json')
    finally:
        temporary.unlink(missing_ok=True)
    return result
