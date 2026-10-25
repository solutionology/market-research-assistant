import argparse
import os
from dotenv import load_dotenv
from research.models import Request
from research.runner import run_research, ROOT
from research.storage import list_saved_searches, load_saved_search
from research.formatting import briefing_markdown


def main():
    load_dotenv(ROOT / '.env')
    p = argparse.ArgumentParser(description='Live multi-agent competitor research')
    p.add_argument('--company')
    p.add_argument('--competitors', nargs=3, metavar='NAME')
    p.add_argument('--competitor-urls', nargs=3, metavar='URL')
    p.add_argument('--context', default='')
    p.add_argument('--feature-focus', default='', help='Capabilities or workflows to investigate')
    p.add_argument('--geography', default='Global')
    p.add_argument('--news-days', type=int, default=30)
    p.add_argument('--list', action='store_true', help='List completed saved searches')
    p.add_argument('--show', metavar='RUN_ID', help='Read a saved briefing without API calls')
    args = p.parse_args()
    if args.list:
        for row in list_saved_searches():
            print(f"{row['run_id']}  {row['generated_at']}  {row['company']}  {', '.join(row['competitors'])}")
        return
    if args.show:
        print(briefing_markdown(load_saved_search(args.show)))
        return
    if not args.company or not args.competitors:
        p.error('--company and exactly three --competitors are required')
    req = Request(company=args.company.strip(), competitor_names=args.competitors,
                  competitor_urls=args.competitor_urls or [None] * 3,
                  context=args.context, feature_focus=args.feature_focus, geography=args.geography, news_days=args.news_days)
    result = run_research(req, tavily_key=os.getenv('TAVILY_API_KEY', ''),
        openrouter_key=os.getenv('OPENROUTER_API_KEY', ''),
        model=os.getenv('OPENROUTER_MODEL', 'openai/gpt-4.1-mini'), on_event=print)
    print(f"\nSaved briefing: {ROOT / 'runs' / result['run_id'] / 'briefing.md'}")


if __name__ == '__main__':
    main()
