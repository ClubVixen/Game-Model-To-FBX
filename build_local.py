import argparse, pathlib, shutil, subprocess, sys, zipfile, hashlib
p=argparse.ArgumentParser();p.add_argument('--assets',required=True,help='Existing locally built Rivals bundle with tools/, mappings/ and licenses/');p.add_argument('--output',required=True);a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent;assets=pathlib.Path(a.assets).resolve();output=pathlib.Path(a.output).resolve();output.mkdir(parents=True,exist_ok=True)
for f in ['tools/cue4parse-materials.exe','mappings/Marvel.usmap']:
 if not (assets/f).is_file():raise SystemExit('Missing local build input: '+str(assets/f))
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','GameModelsToFBX','--distpath',str(output/'dist'),'--workpath',str(output/'build'),'--specpath',str(output),'--collect-all','kkloader','--hidden-import','zzz_mod_prep',str(r/'app.py')],cwd=r,check=True)
bundle=output/'dist/GameModelsToFBX'
for f in r.glob('*.py'):
 if not f.name.startswith('test_'):shutil.copy2(f,bundle/f.name)
for name in ['README.md','README.txt','MULTIGAME.md','KOIKATSU_STUDIO.md','multigame.example.json','requirements.txt']:
 shutil.copy2(r/name,bundle/name)
for name in ['docs','for-llms','studio-exporter','backend-source']:
 shutil.copytree(r/name,bundle/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.dll','bin','obj'))
for name in ['tools','mappings','licenses']:
 if (assets/name).exists():shutil.copytree(assets/name,bundle/name,dirs_exist_ok=True)
archive=output/'GameModelsToFBX-v4.0.0-Windows.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for f in bundle.rglob('*'):
  if f.is_file():z.write(f,pathlib.Path('GameModelsToFBX')/f.relative_to(bundle))
archive.with_suffix('.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print(archive)
