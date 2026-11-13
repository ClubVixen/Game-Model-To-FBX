import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import struct
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from materials import prepare_materials

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DEFAULT_GAME = str(Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))/'Steam/steamapps/common/MarvelRivals/MarvelGame/Marvel/Content/Paks')
DEFAULT_BLENDER = r'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe'
GAME_KEY = '0x0C263D8C22DCB085894899C3A3796383E9BF9DE0CBFB08C9BF2DEF2E84F29D74'
SAMPLES = ['LoonaSwimSuit_1.12_Thicc', 'Twilight_Sparkle_Scarlet_Witch_Swimsuit_Thicc_v0.91',
           'Chrysalis_LadyLoki_ver1.02_Thicc', 'Fluttershy_Manits_ESU_ver0.91']

class Cancelled(Exception):
    pass

def discover(path):
    path = Path(path)
    if path.is_file() and path.suffix.lower() in ('.pak', '.ucas', '.utoc'):
        return [path.with_suffix('.utoc')]
    return sorted(p for p in path.rglob('*.utoc') if p.stem.lower() != 'global')

def normalize_plaintext_flag(path):
    data = bytearray(path.read_bytes())
    if len(data) < 144 or data[:16] != b'-==--==--==--==-':
        return False
    # Only the observed v5 layout with no signing, no key GUID, and an
    # unequivocally plaintext Unreal mount point. Never guess on encrypted data.
    if data[16] != 5 or not data[80] & 2 or data[80] & 4 or any(data[64:80]):
        return False
    header, entries, blocks, block_size, methods, method_size = struct.unpack_from('<6I', data, 20)
    seeds = struct.unpack_from('<I', data, 84)[0]
    overflow = struct.unpack_from('<I', data, 96)[0]
    block_start = header + entries * 22 + seeds * 4 + overflow * 4
    index = block_start + blocks * block_size + methods * method_size
    if data[index:index+14] != b'\x0a\x00\x00\x00../../../\x00':
        return False
    # This mod layout encrypts payload blocks but leaves the index plaintext.
    # Decode payloads using the published Marvel Rivals key, into private copies.
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = bytes.fromhex('0C263D8C22DCB085894899C3A3796383E9BF9DE0CBFB08C9BF2DEF2E84F29D74')
    partition_size = struct.unpack_from('<Q', data, 88)[0]
    payloads = {}
    for i in range(blocks):
        entry = data[block_start+i*block_size:block_start+(i+1)*block_size]
        offset = int.from_bytes(entry[:5], 'little')
        size = int.from_bytes(entry[5:8], 'little')
        partition, offset = divmod(offset, partition_size)
        filename = path.with_suffix('.ucas') if partition == 0 else path.with_name(path.stem+f'_s{partition}.ucas')
        if filename not in payloads:
            payloads[filename] = bytearray(filename.read_bytes())
        payload = payloads[filename]
        aligned = (size + 15) & ~15
        if offset + aligned > len(payload):
            raise RuntimeError('Encrypted compression block exceeds its UCAS partition.')
        decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
        decoded = decryptor.update(bytes(payload[offset:offset+aligned])) + decryptor.finalize()
        if i == 0 and entry[11] == 1 and decoded[:2] != b'\x8c\x06':
            raise RuntimeError('Mixed encrypted/plaintext container uses an unsupported key or compression. Original files unchanged.')
        payload[offset:offset+aligned] = decoded
    for filename, payload in payloads.items():
        replacement = filename.with_suffix('.decoded')
        replacement.write_bytes(payload)
        os.replace(replacement, filename)  # replaces staged hard link, never writes through it
    data[80] &= ~2
    path.write_bytes(data)
    return True

def run(command, log, cancel, logfile):
    log('Running ' + Path(command[0]).name)
    with open(logfile, 'w', encoding='utf-8') as out:
        proc = subprocess.Popen([str(x) for x in command], stdout=out, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        while proc.poll() is None:
            if cancel.wait(0.2):
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise Cancelled('Cancelled; partial output retained for inspection.')
        if proc.returncode:
            raise RuntimeError(f'{Path(command[0]).name} exited {proc.returncode}. See {logfile}')

def convert(utoc, output, game, blender, mappings, log, cancel):
    utoc = Path(utoc).resolve()
    for p in [utoc, utoc.with_suffix('.ucas'), Path(game)/'global.utoc', Path(game)/'global.ucas',
              Path(blender), Path(mappings), ROOT/'tools/cue4parse-materials.exe']:
        if not p.is_file():
            raise FileNotFoundError(f'Required file not found: {p}')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    target = Path(output).resolve() / (utoc.stem + '_' + stamp)
    target.mkdir(parents=True)
    manifest = {'input': str(utoc), 'status': 'running', 'warnings': [], 'output': str(target),
                'game_directory': str(Path(game).resolve()),
                'mapping_sha256': hashlib.sha256(Path(mappings).read_bytes()).hexdigest(),
                'global_utoc_sha256': hashlib.sha256((Path(game)/'global.utoc').read_bytes()).hexdigest()}
    try:
        with tempfile.TemporaryDirectory(prefix='rivals-fbx-') as temporary:
            stage = Path(temporary)
            # Isolate every container so overlapping replacement asset paths never collide.
            sources = list(utoc.parent.glob(utoc.stem + '.*'))
            sources += list(utoc.parent.glob(utoc.stem + '_s*.ucas'))
            for src in sources:
                if src.suffix.lower() not in ('.pak', '.utoc', '.ucas'):
                    continue
                dst = stage/src.name
                if src.suffix.lower() == '.utoc':
                    shutil.copy2(src, dst)
                    continue
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
            if normalize_plaintext_flag(stage/utoc.name):
                manifest['warnings'].append('Decoded mixed plaintext-index/encrypted-payload IoStore layout in temporary copies with the published Marvel Rivals key. Original files unchanged.')
            extracted = target/'extracted'
            backend = ROOT/'tools/cue4parse-materials.exe'
            common = ['-g', 'GAME_MarvelRivals', '-m', mappings, '-k', GAME_KEY]
            log('Reading mod asset inventoryâ€¦')
            run([backend, '-i', stage, *common, '-l'], log, cancel, target/'inventory.log')
            packages = [line.strip() for line in (target/'inventory.log').read_text(encoding='utf-8',errors='replace').splitlines()
                        if line.strip().lower().endswith('.uasset') and not line.startswith('[')]
            if not packages:
                raise RuntimeError('No asset packages found in mod; see inventory.log')
            config_file = target/'mod_packages.txt'
            config_file.write_text('\n'.join(packages), encoding='utf-8')
            log('Resolving mod materials and missing textures from installed gameâ€¦')
            run([backend, '-i', stage, '-i', game, *common, '-c', config_file,
                 '-o', extracted, '--mesh-format', 'Gltf2', '--material-depth', 'AllLayers', '-y', '-v'],
                 log, cancel, target/'extraction.log')
            if not list(extracted.rglob('*.glb')):
                raise RuntimeError('No mesh extracted. Check extraction.log; mappings may not match this mod.')
            text = (target/'extraction.log').read_text(encoding='utf-8', errors='replace')
            if 'Could not load standard asset' in text or ' ERR]' in text:
                manifest['warnings'].append('Some assets could not be extracted. See extraction.log for details.')
            log('Assigning materials and preparing portable texture mapsâ€¦')
            material_report = prepare_materials(extracted, packages)
            manifest['material_count'] = len(material_report['materials'])
            manifest['missing_textures'] = len(material_report['missing'])
            manifest['warnings'].append(material_report['note'])
            run([blender, '--background', '--factory-startup', '--python-exit-code', '1', '--python',
                 ROOT/'blender_convert.py', '--', extracted, target/'FBX'], log, cancel, target/'blender.log')
            manifest['meshes'] = json.loads((target/'FBX/rig_validation.json').read_text())
            manifest['status'] = 'success'
            log(f"DONE: {len(manifest['meshes'])} verified FBX meshes -> {target}")
            for warning in manifest['warnings']:
                log('WARNING: ' + warning)
    except Exception as exc:
        manifest['status'] = 'cancelled' if isinstance(exc, Cancelled) else 'failed'
        manifest['error'] = str(exc)
        raise
    finally:
        (target/'conversion_report.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return target

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Marvel Rivals â†’ Rigged FBX')
        self.geometry('1000x760')
        self.minsize(800, 600)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.jobs = []
        self.settings = ROOT/'settings.json'
        try:
            saved = json.loads(self.settings.read_text())
        except (OSError, ValueError):
            saved = {}
        self.vars = {}
        header = ttk.Frame(self, padding=16)
        header.pack(fill='x')
        ttk.Label(header, text='Marvel Rivals â†’ Rigged FBX', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(header, text='Textured batch conversion â€¢ installed-game material lookup â€¢ rig and texture verification').pack(anchor='w', pady=5)
        config = ttk.Frame(self, padding=(16, 0))
        config.pack(fill='x')
        defaults = {'Game Paks folder': DEFAULT_GAME, 'Blender executable': DEFAULT_BLENDER,
                    'Mappings (.usmap)': str(ROOT/'mappings/Marvel.usmap'), 'Output folder': str(ROOT/'Converted')}
        for row, (name, default) in enumerate(defaults.items()):
            var = tk.StringVar(value=saved.get(name, default))
            self.vars[name] = var
            ttk.Label(config, text=name).grid(row=row, column=0, sticky='w', pady=4)
            ttk.Entry(config, textvariable=var).grid(row=row, column=1, sticky='ew', padx=10)
            ttk.Button(config, text='Browseâ€¦', command=lambda n=name: self.browse(n)).grid(row=row, column=2)
        config.columnconfigure(1, weight=1)
        actions = ttk.Frame(self, padding=16)
        actions.pack(fill='x')
        for title, fn in [('Add filesâ€¦', self.add_files), ('Add folder recursivelyâ€¦', self.add_folder),
                          ('Load four samples', self.samples), ('Remove selected', self.remove)]:
            ttk.Button(actions, text=title, command=fn).pack(side='left', padx=(0, 8))
        self.tree = ttk.Treeview(self, columns=('file', 'status'), show='headings', height=8)
        self.tree.heading('file', text='Container (one job per .utoc + .ucas set)')
        self.tree.heading('status', text='Status')
        self.tree.column('file', width=750)
        self.tree.column('status', width=160)
        self.tree.pack(fill='both', expand=True, padx=16)
        controls = ttk.Frame(self, padding=16)
        controls.pack(fill='x')
        self.start_button = ttk.Button(controls, text='Convert batch', command=self.start)
        self.start_button.pack(side='left')
        ttk.Button(controls, text='Cancel', command=self.cancel.set).pack(side='left', padx=8)
        ttk.Button(controls, text='Open output', command=self.open_output).pack(side='right')
        self.progress = ttk.Label(controls, text='Ready')
        self.progress.pack(side='left', padx=16)
        self.logbox = tk.Text(self, height=10, wrap='word', state='disabled', font=('Consolas', 9))
        self.logbox.pack(fill='both', padx=16, pady=(0, 8))
        ttk.Label(self, text='Textures are assigned and embedded automatically. Unreal-specific shader effects are approximated as portable PBR.').pack(pady=(0, 12))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def browse(self, name):
        value = filedialog.askdirectory() if 'folder' in name else filedialog.askopenfilename()
        if value:
            self.vars[name].set(value)

    def add(self, paths):
        if self.busy:
            return
        for path in paths:
            for item in discover(path):
                item = str(item.resolve())
                if item not in self.jobs:
                    self.jobs.append(item)
                    self.tree.insert('', 'end', iid=item, values=(item, 'Queued'))

    def add_files(self):
        self.add(filedialog.askopenfilenames(filetypes=[('Unreal containers', '*.utoc *.pak *.ucas')]))

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.add([folder])

    def samples(self):
        self.add([Path.home()/'Downloads/marvel rivals mods'/name for name in SAMPLES])

    def remove(self):
        if self.busy:
            return
        for item in self.tree.selection():
            self.jobs.remove(item)
            self.tree.delete(item)

    def open_output(self):
        path = Path(self.vars['Output folder'].get())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def start(self):
        if self.busy or not self.jobs:
            return
        config = {k: v.get() for k, v in self.vars.items()}
        self.settings.write_text(json.dumps(config, indent=2))
        self.busy = True
        self.cancel.clear()
        self.start_button.config(state='disabled')
        threading.Thread(target=self.worker, args=(list(self.jobs), config), daemon=True).start()

    def worker(self, jobs, config):
        succeeded = failed = 0
        for index, job in enumerate(jobs):
            if self.cancel.is_set():
                break
            self.events.put(('status', job, f'Running {index+1}/{len(jobs)}'))
            try:
                convert(job, config['Output folder'], config['Game Paks folder'], config['Blender executable'],
                        config['Mappings (.usmap)'], lambda msg: self.events.put(('log', msg)), self.cancel)
                succeeded += 1
                self.events.put(('status', job, 'Verified'))
            except Exception as exc:
                failed += 1
                self.events.put(('log', str(exc)))
                self.events.put(('status', job, 'Cancelled' if isinstance(exc, Cancelled) else 'Failed'))
        self.events.put(('done', f'{succeeded} succeeded, {failed} failed/cancelled'))

    def poll(self):
        while not self.events.empty():
            event = self.events.get()
            if event[0] == 'log':
                self.logbox.config(state='normal')
                self.logbox.insert('end', event[1] + '\n')
                self.logbox.see('end')
                self.logbox.config(state='disabled')
            elif event[0] == 'status':
                self.tree.set(event[1], 'status', event[2])
                self.progress.config(text=event[2])
            else:
                self.busy = False
                self.start_button.config(state='normal')
                self.progress.config(text=event[1])
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            self.cancel.set()
            self.progress.config(text='Cancellingâ€¦ close again when finished')
        else:
            self.destroy()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Batch Unreal IoStore mods to verified rigged FBX')
    parser.add_argument('inputs', nargs='*')
    parser.add_argument('--game', default=DEFAULT_GAME)
    parser.add_argument('--blender', default=DEFAULT_BLENDER)
    parser.add_argument('--mappings', default=str(ROOT/'mappings/Marvel.usmap'))
    parser.add_argument('--output', default=str(ROOT/'Converted'))
    args = parser.parse_args()
    if args.inputs:
        failures = 0
        jobs = sorted({p.resolve() for item in args.inputs for p in discover(item)})
        if not jobs:
            parser.error('No .utoc containers found.')
        for job in jobs:
            try:
                convert(job, args.output, args.game, args.blender, args.mappings, print, threading.Event())
            except Exception as exc:
                failures += 1
                print(f'FAILED {job}: {exc}', file=sys.stderr)
        sys.exit(1 if failures else 0)
    else:
        App().mainloop()
