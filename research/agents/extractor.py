from research.models import Findings
from research.prompts import load_prompt


class ExtractionAgent:
    def __init__(self, analyst):
        self.analyst = analyst

    def __call__(self, state):
        analyst = self.analyst
        result = analyst.ask(Findings,
            load_prompt('extraction.md'), state)
        return {'findings': result,
                'events': state['events'] + [f"Extraction agent · {state['competitor']['name']}: structured evidence."]}
