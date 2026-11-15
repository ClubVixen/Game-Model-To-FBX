"""Non-destructive Sunshine card compatibility and installed Sideloader audit.

Version conversion follows astralash/ConvertKKS-CC-to-KK-CC (both Parameter
versions 0.0.6 -> 0.0.5), using kkloader. Original cards are never overwritten.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
import msgpack
from kkloader import KoikatuCharaData
from card_reader import inspect_card


def convert_sunshine(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError('Choose a new destination; existing cards are never overwritten')
    inspect_card(source)
    card = KoikatuCharaData.load(str(source))
    versions = [card['Parameter']['version'], card.Parameter.version]
    if any(v not in ('0.0.5', '0.0.6') for v in versions):
        raise ValueError(f'Unsupported Parameter versions: {versions}')
    before = {n: getattr(card, n).serialize() for n in card.blockdata if n != 'Parameter'}
    card['Parameter']['version'] = card.Parameter.version = '0.0.5'
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = bytes(card)
    check = KoikatuCharaData.load(payload)
    if (check.Parameter.version != '0.0.5' or check['Parameter']['version'] != '0.0.5'
            or any(getattr(check, n).serialize() != data for n, data in before.items())
            or check.image != card.image):
        raise ValueError('Card round-trip changed data outside the compatibility fields')
    with destination.open('xb') as f: f.write(payload)
    return {'card':str(destination),'changed': '0.0.6' in versions,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256(payload).hexdigest(),
            'preserved_blocks':sorted(before)}


def audit_dependencies(source, mods_folder, outfit=0):
    card = KoikatuCharaData.load(str(source))
    extension = getattr(card, 'KKEx', None)
    resolver = extension.data.get('com.bepis.sideloader.universalautoresolver') if extension else None
    if not resolver:
        return {'status':'unknown','reason':'Card has no Sideloader resolver metadata','dependencies':[]}
    required = []
    for blob in resolver[1].get('info', []):
        entry = msgpack.unpackb(blob, raw=False, strict_map_key=False)
        prop = entry.get('Property','')
        match = re.match(r'outfit(\d+)\.',prop)
        if match and int(match[1]) != outfit: continue
        required.append({k:entry.get(k) for k in ('ModID','Name','Property','Slot','CategoryNo')})
    root = Path(mods_folder)
    if not root.is_dir(): raise ValueError('Koikatsu mods folder does not exist')
    installed, errors = {}, []
    for path in sorted(root.rglob('*')):
        if path.suffix.lower() not in ('.zipmod','.zip'): continue
        try:
            with zipfile.ZipFile(path) as z:
                names=[n for n in z.namelist() if n.lower().endswith('manifest.xml')]
                if not names: continue
                document=ET.fromstring(z.read(names[0]))
                guid=next((e.text.strip() for e in document.iter() if e.tag.split('}')[-1].lower()=='guid' and e.text),'')
                if guid: installed.setdefault(guid,[]).append(str(path))
        except (OSError,zipfile.BadZipFile,ET.ParseError) as exc:
            errors.append({'file':str(path),'error':str(exc)})
    for item in required: item['installed_packages']=installed.get(item['ModID'],[])
    missing=sorted({i['ModID'] for i in required if not i['installed_packages']})
    return {'status':'missing' if missing else 'packages_found','outfit':outfit,
            'dependencies':required,'missing':missing,'archive_errors':errors,
            'note':'GUID presence is not proof of asset compatibility or inclusion in PMX. Load the card in the game, select this outfit, enable accessories, then export with KKBP.'}


def prepare_card(source, output, config):
    import datetime
    target=Path(output)/(Path(source).stem+'_KK_'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    target.mkdir(parents=True)
    result=convert_sunshine(source,target/(Path(source).stem+'_KK.png'))
    if config.get('koikatsu_mods'):
        result['dependencies']=audit_dependencies(result['card'],config['koikatsu_mods'],config.get('koikatsu_outfit',0))
    (target/'card-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
