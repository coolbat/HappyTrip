import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from PIL import Image, ImageDraw, ImageFont

skill = Path(__file__).resolve().parents[1] / 'happytrip'
cli = skill / 'scripts/happytrip.py'
font = Path('/System/Library/Fonts/STHeiti Medium.ttc')
root = Path(tempfile.mkdtemp(prefix='happytrip-b22-docs-'))
assert font.is_file()
log = []
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
def run(*args):
    cmd = [sys.executable, str(cli), *map(str, args)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    log.append({'command': cmd, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    write(root / 'commands.json', log)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)

photos = []
for i, color in enumerate(['#9eb5aa', '#9caebc', '#bba58f'], 1):
    path = root / f'fixture-{i}.png'
    im = Image.new('RGB', (720, 480), color)
    d = ImageDraw.Draw(im)
    d.rectangle((50, 45, 670, 435), outline='#fffcf4', width=6)
    d.ellipse((150 + i * 25, 110, 420 + i * 25, 360), fill='#fff9e5')
    d.text((70, 60), f'DEV FIXTURE {i}', font=ImageFont.truetype(str(font), 26), fill='#243b35')
    im.save(path)
    photos.append(path)
initial = {str(p): sha(p) for p in photos}
example = json.loads((skill / 'examples/b22-travel-poster.request.json').read_text())
example.pop('example_only')
example.pop('note')
example['user_goal'] = '本地 B22 文档验证，使用合成测试图片，不是真实旅程。'
example['mode_options']['title'] = '开发样例'
example['mode_options']['subtitle'] = '合成图片与数据 · 非真实旅程'
for photo, path in zip(example['photos'], photos):
    photo['ref'] = str(path)
for i, stop in enumerate(example['mode_options']['stops']):
    stop['name'] = '样例' + 'ABC'[i]
assert example['capabilities']['image_generation'] is False
reference = (skill / 'references/route-photo-map.md').read_text()
recipe_code = re.search(r'<<\'PY\'\n(.*?)\nPY\npython3', reference, re.S).group(1)
recipe_script = root / 'documented-recipe.py'
recipe_script.write_text(recipe_code, encoding='utf-8')
summary = []

def validate_flow(name, request):
    request_path = root / f'{name}.request.json'
    job = root / name
    write(request_path, request)
    result = run('prepare', '--request', request_path, '--job-dir', job)
    plan = json.loads((job / 'plan.json').read_text())
    assert result['status'] == plan['status'] == 'ready', result
    assert plan['estimated_image_calls'] == 0
    assert 'image_generation' not in plan['required_capabilities']
    result = subprocess.run([sys.executable, str(recipe_script), str(job), str(font)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = run('compose', '--recipe', job / 'recipe.json', '--output', job / 'poster.png')
    actual = json.loads((job / 'poster.png.json').read_text())
    assert actual == manifest
    with Image.open(job / 'poster.png') as im:
        assert im.size == (1500, 2000)
    sources = [p for p in manifest['provenance'] if p['kind'] == 'source_photo']
    assert {p['photo_id'] for p in sources} == {'p01', 'p02', 'p03'}
    assert manifest['route']['template'] == 'travel_poster'
    assert manifest['route']['ordered_stop_ids'] == ['s01', 's02', 's03']
    summary.append({'case': name, 'plan': plan['status'], 'image_calls': plan['estimated_image_calls'],
        'photo_ids': sorted({p['photo_id'] for p in sources}), 'size': [1500,2000],
        'map_mode': manifest['route']['map_mode'], 'label': manifest['route']['label'],
        'output': str(job / 'poster.png'), 'manifest': str(job / 'poster.png.json')})
    return manifest

validate_flow('schematic', example)
geojson = {'type': 'FeatureCollection', 'features': [
    {'type': 'Feature', 'properties': {'kind': 'water'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[0.033,0.025],[0.06,0.025],[0.06,0.04],[0.033,0.04],[0.033,0.025]]]}},
    {'type': 'Feature', 'properties': {'kind': 'park'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[0.002,0.002],[0.018,0.002],[0.018,0.025],[0.002,0.025],[0.002,0.002]]]}},
    {'type': 'Feature', 'properties': {'kind': 'road'}, 'geometry': {'type': 'LineString', 'coordinates': [[0.01,0.01],[0.02,0.014],[0.025,0.02],[0.05,0.03]]}},
    {'type': 'Feature', 'properties': {'kind': 'boundary', 'name': '测试区域'}, 'geometry': {'type': 'Point', 'coordinates': [0.028,0.033]}}
]}
geo_path = root / 'fixture-map.geojson'
write(geo_path, geojson)
# As documented, basemap metadata is prepared in the job folder before prepare.
basemap = run('map-basemap', '--geojson', geo_path, '--bounds', 0, 0, .06, .04, '--size', 1400, 1400,
    '--font-path', font, '--source', 'synthetic development fixture; not a real map',
    '--attribution', '开发测试数据 · 非真实地图', '--output', root / 'geographic' / 'basemap.json')
assert basemap == json.loads((root / 'geographic' / 'basemap.json').read_text())
assert sha(basemap['path']) == basemap['sha256']
request = copy.deepcopy(example)
request['capabilities']['geographic_rendering'] = True
request['mode_options']['map_mode'] = 'geographic'
request['mode_options']['basemap'] = basemap
for stop, coord in zip(request['mode_options']['stops'], [(0.01,0.01),(.025,.02),(.05,.03)]):
    stop['coordinates'] = {'lon': coord[0], 'lat': coord[1], 'source': 'user', 'confirmed': True, 'source_reference': 'synthetic test positions'}
request['mode_options']['route_segments'] = [{
    'from': 's01', 'to': 's02', 'coordinates': [[0.01,0.01],[0.02,0.014],[0.025,0.02]],
    'kind': 'planned_route', 'source': 'user', 'confirmed': True, 'source_reference': 'synthetic test route'
}]
request['mode_options']['footer'] = [{'label':'用途', 'value':'开发测试', 'source':'user', 'confirmed': True}]
manifest = validate_flow('geographic', request)
assert manifest['route']['attribution'] == '开发测试数据 · 非真实地图'
assert len(manifest['route']['pins']) == 3
assert [s['kind'] for s in manifest['route']['route_segments']] == ['planned_route', 'station_connection']
# Round-trip documented local raster registration using actual expanded bounds.
raster = run('map-basemap', '--image', basemap['path'], '--bounds', *basemap['bounds'],
    '--source', basemap['source'], '--attribution', basemap['attribution'], '--output', root / 'raster-basemap.json')
assert raster['sha256'] == basemap['sha256']
assert all(sha(path) == digest for path, digest in initial.items())
write(root / 'summary.json', {'cases': summary, 'raster_registration': 'pass', 'input_hashes_unchanged': True, 'commands': str(root / 'commands.json')})
print(json.dumps({'root': str(root), 'summary': summary, 'raster_registration':'pass', 'input_hashes_unchanged': True}, ensure_ascii=False, indent=2))
