import json
from pathlib import Path

from app.brand_export import main as collect_brand

REGISTRY = Path('site/data/brands/registry.json')


def load_brands():
    if not REGISTRY.exists():
        return []
    try:
        data = json.loads(REGISTRY.read_text(encoding='utf-8'))
        return [str(x).strip() for x in data.get('brands', []) if str(x).strip()]
    except Exception:
        return []


def main(days=2):
    brands = load_brands()
    print(f'registered brands={len(brands)}')
    failed = []
    for brand in brands:
        try:
            print(f'\n=== {brand} ===')
            collect_brand(brand, days)
        except BaseException as exc:
            failed.append((brand, str(exc)))
            print(f'FAILED {brand}: {exc}')
    if failed:
        print('\nBrand failures:')
        for brand, error in failed:
            print(f'- {brand}: {error}')
    print(f'completed brands={len(brands)-len(failed)} failed={len(failed)}')


if __name__ == '__main__':
    main(days=2)
