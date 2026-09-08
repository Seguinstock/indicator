import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    params_path = ROOT / 'config/parameters.json'
    results_path = ROOT / 'data/results.json'

    params = json.loads(params_path.read_text(encoding='utf-8'))
    results = json.loads(results_path.read_text(encoding='utf-8'))

    results['parameter_snapshot'] = params
    results['scored_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')

    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Stamped results with exact parameter snapshot')


if __name__ == '__main__':
    main()
