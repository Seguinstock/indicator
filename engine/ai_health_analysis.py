import json, os, re
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
BODY = os.environ.get('ISSUE_BODY', '')
MODEL = os.environ.get('OPENAI_MODEL', 'gpt-5.6-luna')


def extract_request():
    m = re.search(r'```json\s*(\{.*?\})\s*```', BODY, re.S)
    if not m:
        raise SystemExit('No AI analysis JSON found in issue body')
    req = json.loads(m.group(1))
    if req.get('action') != 'analyze_buy_health':
        raise SystemExit('Unsupported AI analysis action')
    request_id = str(req.get('request_id', '')).strip()
    stocks = req.get('stocks') or []
    if not request_id or not isinstance(stocks, list) or not stocks:
        raise SystemExit('Missing request_id or stocks')
    clean = []
    seen = set()
    for x in stocks[:30]:
        symbol = str(x.get('symbol', '')).strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        clean.append({
            'symbol': symbol,
            'name': str(x.get('name') or '').strip()[:120],
            'market': str(x.get('market') or '').strip()[:20],
            'country': str(x.get('country') or '').strip()[:10],
            'potential': x.get('potential'),
            'timing': x.get('timing'),
            'risk': x.get('risk'),
        })
    if not clean:
        raise SystemExit('No valid stocks')
    return request_id, clean


def parse_json_text(text):
    text = (text or '').strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.S | re.I)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    a, b = text.find('{'), text.rfind('}')
    if a >= 0 and b > a:
        return json.loads(text[a:b+1])
    raise ValueError('Model did not return valid JSON')


def analyze_batch(client, batch):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    compact = json.dumps(batch, ensure_ascii=False)
    prompt = f'''Nous sommes le {today}. Analyse les entreprises cotées ci-dessous à partir d'informations Web récentes et fiables.

Objectif: évaluer la SANTÉ DE L'ENTREPRISE et l'ACTUALITÉ RÉCENTE, indépendamment du score technique Stock Indicator. Ne donne pas une recommandation personnalisée d'achat/vente.

Pour chaque titre:
- vérifie l'identité de l'entreprise malgré les symboles ambigus;
- cherche les nouvelles récentes, derniers résultats, guidance, croissance/recul des revenus et bénéfices, marges, dette/liquidité, émissions d'actions si pertinentes, problèmes réglementaires/judiciaires, changements de direction, contrats majeurs, acquisitions et risques sectoriels;
- attribue health_status parmi EXACTEMENT: "très_sain", "sain", "à_surveille", "préoccupant", "données_insuffisantes";
- attribue health_score de 0 à 100, où 100 = santé financière/opérationnelle très forte;
- news_sentiment parmi EXACTEMENT: "très_positif", "positif", "neutre", "négatif", "très_négatif";
- résume en français en 1-2 phrases;
- donne au maximum 3 points clés et 2 risques;
- indique le principal catalyseur récent ou à surveiller;
- indique confidence de 0 à 100;
- donne 1 à 3 sources Web récentes sous forme title + url. N'invente aucune URL.

Retourne UNIQUEMENT du JSON valide, sans markdown, avec cette forme:
{{"stocks":[{{"symbol":"ABC","health_status":"sain","health_score":75,"news_sentiment":"positif","summary":"...","key_points":["..."],"risks":["..."],"catalyst":"...","confidence":85,"sources":[{{"title":"...","url":"https://..."}}]}}]}}

Titres à analyser:
{compact}'''
    response = client.responses.create(
        model=MODEL,
        tools=[{'type': 'web_search'}],
        input=prompt,
    )
    data = parse_json_text(response.output_text)
    rows = data.get('stocks') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('Missing stocks array')
    return rows


def main():
    request_id, stocks = extract_request()
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise SystemExit('OPENAI_API_KEY GitHub secret is not configured')
    client = OpenAI(api_key=api_key)
    analyses = []
    errors = []
    for i in range(0, len(stocks), 10):
        batch = stocks[i:i+10]
        try:
            analyses.extend(analyze_batch(client, batch))
        except Exception as e:
            errors.append(f"Batch {i//10+1}: {type(e).__name__}: {e}")

    by_symbol = {str(x.get('symbol', '')).upper(): x for x in analyses if isinstance(x, dict)}
    ordered = []
    for source in stocks:
        symbol = source['symbol']
        x = by_symbol.get(symbol)
        if not x:
            x = {
                'symbol': symbol,
                'health_status': 'données_insuffisantes',
                'health_score': None,
                'news_sentiment': 'neutre',
                'summary': 'Analyse indisponible pour ce titre lors de cette exécution.',
                'key_points': [], 'risks': [], 'catalyst': '', 'confidence': 0, 'sources': []
            }
        x['input'] = source
        ordered.append(x)

    out = {
        'request_id': request_id,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'model': MODEL,
        'count': len(ordered),
        'errors': errors,
        'stocks': ordered,
    }
    path = ROOT / 'data' / 'ai-health.json'
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"AI health analysis complete: {len(ordered)} stocks, {len(errors)} batch errors")


if __name__ == '__main__':
    main()
