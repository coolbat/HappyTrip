"""Offline document/configuration checks; does NOT run an image model."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
IDS = [f'A{i:02d}' for i in range(1, 13)] + ['B01', 'B03', 'B04', 'B14', 'B16', 'B22']
P0 = {'A01', 'A05', 'A06', 'A07', 'A08', 'A12', 'B01', 'B22'}

def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    required = ['README.md', 'happytrip/SKILL.md',
                'happytrip/references/catalog.json',
                'happytrip/references/routing.md',
                'happytrip/references/execution-and-quality.md',
                'docs/01-PRD.md', 'docs/02-TECHNICAL-DESIGN.md',
                'docs/03-IMPLEMENTATION-PLAN.md', 'docs/04-ACCEPTANCE.md',
                'docs/05-SOURCE-NOTES.md']
    for rel in required:
        check((ROOT / rel).is_file(), f'Missing: {rel}')
    catalog = json.loads((ROOT / 'happytrip/references/catalog.json').read_text())
    modes = catalog['modes']
    check([m['id'] for m in modes] == IDS, 'Mode IDs/order differ from approved scope')
    check({m['id'] for m in modes if m['validation_priority'] == 'P0'} == P0, 'Wrong P0 set')
    check(len({m['slug'] for m in modes}) == 18, 'Duplicate slugs')
    skill = (ROOT / 'happytrip/SKILL.md').read_text()
    check(skill.startswith('---\nname: happytrip\n'), 'Bad skill frontmatter')
    check('description: Use when' in skill, 'Missing trigger description')
    for m in modes:
        path = ROOT / 'happytrip' / m['mode_file']
        check(path.is_file(), f'Missing mode card: {path.name}')
        text = path.read_text()
        for section in ['输入与默认值', '执行与边界', '提示词模板', '验收与回退', '来源说明']:
            check(section in text, f'{m["id"]}: Missing section {section}')
        placeholders = set(re.findall(r'\{\{([a-z_]+)\}\}', text))
        check(placeholders <= set(catalog['template_variables']), f'{m["id"]}: Unknown variable')
        check(m['input_min'] <= m['input_max'], f'{m["id"]}: Bad input range')
        if m['id'].startswith('A'):
            check(m['source']['kind'] == 'article_adaptation', f'{m["id"]}: Missing source')
        else:
            check(m['source']['kind'] == 'approved_extension', f'{m["id"]}: Wrong source kind')
    by_id = {m['id']: m for m in modes}
    check(by_id['B01']['strict_original_requires_compositor'], 'B01 must use compositor')
    check(by_id['B22']['needs_confirmed_order'], 'B22 must require order for a route')
    check(by_id['A07']['flat_stickers_only'], 'A07 must not become 3D')
    check(by_id['A02']['default_optional_retouch'] is False, 'A02 must not auto retouch')
    check(by_id['B04']['default_snow'] is False, 'B04 must not force snow')
    examples = list((ROOT / 'examples').glob('*.json'))
    check(len(examples) >= 5, 'Not enough request examples')
    for p in examples:
        x = json.loads(p.read_text())
        check(x['mode'] in IDS or x['mode'] == 'auto', f'{p.name}: Invalid mode')
        check(x['example_only'] is True, f'{p.name}: Not marked illustrative')
    for path in ROOT.rglob('*.md'):
        text = path.read_text()
        check(text.count('```') % 2 == 0, f'Unclosed code fence: {path}')
        for dest in re.findall(r'\]\(([^)]+)\)', text):
            if '://' in dest or dest.startswith('#'):
                continue
            local = (path.parent / dest.split('#')[0]).resolve()
            check(local.exists(), f'Broken relative link in {path}: {dest}')
    print(f'PASS: {len(required)} core files, 18 modes, 8 P0 priorities, {len(examples)} examples, source and link checks.')
    print('SCOPE: static documentation/configuration checks only; no image-generation or runtime integration tests.')

if __name__ == '__main__':
    try:
        main()
    except (AssertionError, KeyError, ValueError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        raise SystemExit(1)
