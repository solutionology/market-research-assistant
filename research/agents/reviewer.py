from research.quality import audit_findings


class EvidenceReviewAgent:
    def __call__(self, state):
        result = audit_findings(state['findings'], state['sources'], state['request']['news_days'], state['as_of'])
        return {'findings': result,
                'events': state['events'] + [f"Evidence reviewer · {state['competitor']['name']}: citations and news dates checked."]}
