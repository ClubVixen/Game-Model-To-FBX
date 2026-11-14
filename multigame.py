"""Explicit, report-producing conversion routes for the hero-swap pipeline."""
import argparse
import datetime
import json
import re
from pathlib import Path
import subprocess
import sys
from card_reader import inspect_card

ROOT = Path(__file__).resolve().parent


def run(args, log):
    with Path(log).open('w', encoding='utf-8') as stream:
        proc = subprocess.run([str(a) for a in args], stdout=stream,
                              stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if proc.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed ({proc.returncode}); see {log}')


def inspect(source, kind, config):
    source = Path(source).resolve()
    if kind == 'koikatsu' and source.suffix.lower() == '.png':
        return inspect_card(source)
    if kind == 'deadlock':
        proc = subprocess.run([config['vrf'], '-i', str(source), '-l', '-e', 'vmdl_c'],
                              capture_output=True, text=True, errors='replace')
        if proc.returncode:
            raise RuntimeError(proc.stderr or proc.stdout)
        return {'type': kind, 'models': re.findall(r'(?m)^(.+?\.vmdl_c)(?:\s+CRC:.*)?$', proc.stdout)}
    if kind == 'zzz':
        proc = subprocess.run([sys.executable, config.get('zzz_reader', str(ROOT/'zzz_mod_prep.py')), 'inspect', str(source)],
                              capture_output=True, text=True, errors='replace')
        if proc.returncode:
            raise RuntimeError(proc.stderr or proc.stdout)
        return {'type': kind, 'inventory': proc.stdout}
    return {'type': kind, 'source': str(source)}


def convert(source, kind, output, config):
    source = Path(source).resolve()
    target = Path(output).resolve() / (source.stem + '_' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    target.mkdir(parents=True)
    report = {'source': str(source), 'route': kind, 'status': 'running', 'warnings': []}
    try:
        job = dict(config, kind=kind, source=str(source), target=str(target))
        if kind == 'deadlock':
            models = inspect(source, kind, config)['models']
            selected = config.get('model')
            if selected:
                if selected not in models:
                    raise ValueError('Selected model is not in this VPK')
                models = [selected]
            if not models:
                raise ValueError('No compiled models found in the VPK')
            (target/'extracted').mkdir()
            job['inputs'] = []
            for i, model in enumerate(models):
                glb = target/'extracted'/f'{i:02d}_{Path(model).stem}.glb'
                run([config['vrf'], '-i', source, '-f', model, '-o', glb, '-d',
                     '--gltf_export_format', 'glb', '--gltf_export_materials',
                     '--gltf_export_animations', '--gltf_animation_list', '__bind_pose_only__',
                     '--game', config['gameinfo']], target/f'extract-{i}.log')
                if glb.is_file():
                    job['inputs'].append(str(glb))
            if not job['inputs']:
                raise RuntimeError('Model extraction produced no GLB files')
        elif kind == 'zzz':
            for key in ('reference', 'base_fbx', 'bone_map'):
                if not config.get(key):
                    raise ValueError(f'ZZZ requires {key}: numeric skin indices alone do not define a skeleton')
            run([sys.executable, config.get('zzz_reader', str(ROOT/'zzz_mod_prep.py')), 'prepare', source, '-o', target/'prepared',
                 '--ref', config['reference']], target/'prepare.log')
            job['inputs'] = [str(p) for p in (target/'prepared').glob('*.ib')]
            if not job['inputs']:
                raise RuntimeError('Reader produced no importable index buffers')
            report['warnings'].append('Uses an explicit per-part bone map and material map; source shaders/physics are not portable.')
        elif kind == 'koikatsu':
            if source.suffix.lower() == '.pmx':
                if not config.get('kkbp_blender'):
                    raise ValueError('PMX preparation requires kkbp_blender (Blender 3.6) with KKBP 6.6.3 and mmd_tools 2.9.2')
                prep = dict(config, source=str(source), target=str(target/'kkbp'))
                prepfile = target/'prepare-job.json'
                prepfile.write_text(json.dumps(prep), encoding='utf-8')
                run([config['kkbp_blender'], '--factory-startup', '--python', ROOT/'koikatsu_prepare.py', '--', prepfile], target/'kkbp.log')
                state = json.loads((target/'kkbp'/'prepare-report.json').read_text())
                if state['status'] != 'success': raise RuntimeError(state['error'])
                job['source'] = str(target/'kkbp'/'prepared.blend')
            elif source.suffix.lower() == '.png':
                report['card'] = inspect_card(source)
                assembly = config.get('assemblies', {}).get(report['card']['sha256'])
                if not assembly and config.get('card_sha256') == report['card']['sha256']:
                    assembly = config.get('assembled_blend')
                if not assembly:
                    raise ValueError('Card verified. Load it in Koikatsu with its required mods, export with KKBP and bake materials. Map this card SHA256 to its .blend in assemblies, or convert the prepared .blend directly. A card alone cannot reconstruct meshes.')
                job['source'] = assembly
            elif source.suffix.lower() != '.blend':
                raise ValueError('Koikatsu accepts a KKBP model.pmx, prepared .blend, or card mapped to its prepared .blend')
        else:
            raise ValueError(f'Unsupported route: {kind}')
        jobpath = target/'job.json'
        jobpath.write_text(json.dumps(job, indent=2), encoding='utf-8')
        run([config['blender'], '--background', '--factory-startup', '--python-exit-code', '1', '--python',
             ROOT/'multigame_blender.py', '--', jobpath], target/'blender.log')
        report['validation'] = json.loads((target/'validation.json').read_text())
        report['status'] = 'success'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        (target/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['inspect', 'convert'])
    p.add_argument('kind', choices=['deadlock', 'zzz', 'koikatsu'])
    p.add_argument('source', nargs='+')
    p.add_argument('--config', required=True)
    p.add_argument('--output', default='Converted')
    args = p.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    failures = 0
    for source in args.source:
        try:
            result = inspect(source, args.kind, config) if args.action == 'inspect' else str(convert(source, args.kind, args.output, config))
            print(json.dumps(result, indent=2))
        except Exception as exc:
            failures += 1
            print(f'FAILED {source}: {exc}', file=sys.stderr)
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
