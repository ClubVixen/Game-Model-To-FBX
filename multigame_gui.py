"""Batch front end for explicit mod conversion routes."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from multigame import convert, inspect, ROOT
from tkinter import messagebox


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Game Models to FBX')
        self.geometry('900x660')
        self.kind = tk.StringVar(value='rivals')
        self.config_path = tk.StringVar(value=str(ROOT/'multigame.local.json') if (ROOT/'multigame.local.json').is_file() else '')
        self.output = tk.StringVar(value=str(Path.home()/'Documents'/'ConvertedMods'))
        self.messages = queue.Queue()
        top = ttk.Frame(self, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='Source game').pack(side='left')
        ttk.Combobox(top, textvariable=self.kind, values=['rivals', 'deadlock', 'zzz', 'koikatsu'], state='readonly').pack(side='left', padx=10)
        for label, variable, folder in [('Configuration JSON', self.config_path, False), ('Output folder', self.output, True)]:
            row = ttk.Frame(self, padding=6)
            row.pack(fill='x')
            ttk.Label(row, text=label, width=20).pack(side='left')
            ttk.Entry(row, textvariable=variable).pack(side='left', expand=True, fill='x')
            ttk.Button(row, text='Browse', command=lambda v=variable, f=folder: self.browse(v, f)).pack(side='left')
        tools = ttk.Frame(self, padding=6)
        tools.pack(fill='x')
        ttk.Button(tools, text='Create / Edit configuration', command=self.edit_config).pack(side='left')
        ttk.Button(tools, text='Game instructions', command=self.open_guide).pack(side='left', padx=10)
        self.inputs = tk.Listbox(self, selectmode='extended', height=9)
        self.inputs.pack(fill='x', padx=10)
        row = ttk.Frame(self, padding=10)
        row.pack(fill='x')
        ttk.Button(row, text='Add files', command=self.add_files).pack(side='left')
        ttk.Button(row, text='Add mod folder', command=self.add_folder).pack(side='left')
        ttk.Button(row, text='Remove selected', command=self.remove).pack(side='left')
        row = ttk.Frame(self, padding=10)
        row.pack(fill='x')
        self.buttons = []
        for label, action in [('Inspect / Read Mods', 'inspect'), ('Convert Batch to FBX', 'convert'), ('Sunshine to KK card', 'convert-card')]:
            b = ttk.Button(row, text=label, command=lambda a=action:self.start(a))
            b.pack(side='left', padx=8)
            self.buttons.append(b)
        ttk.Label(self, text='Rivals: set game Paks and mappings. Deadlock: set VRF and gameinfo. Koikatsu: convert Sunshine cards, check mods, then use Maker/KKBP PMX or Studio FBX Bridge .studio.json. FBX exports include editable PNG textures. ZZZ needs the matching rig and bone map.', wraplength=850).pack(padx=10)
        self.log = tk.Text(self, height=17, state='disabled')
        self.log.pack(fill='both', expand=True, padx=10, pady=10)
        self.after(150, self.poll)

    def open_guide(self):
        pages = {'rivals':'marvel-rivals', 'deadlock':'deadlock', 'zzz':'zzz', 'koikatsu':'koikatsu'}
        import webbrowser
        webbrowser.open('https://github.com/ClubVixen/marvel-rivals-fbx-converter/blob/main/docs/games/' + pages[self.kind.get()] + '.md')

    def edit_config(self):
        window = tk.Toplevel(self)
        window.title('Configuration — paths and advanced game options')
        window.geometry('850x600')
        ttk.Label(window, text='Edit paths for your game. Use forward slashes in JSON paths. Other game fields may be left unused.').pack(pady=8)
        editor = tk.Text(window, wrap='none')
        editor.pack(fill='both', expand=True, padx=10)
        path = Path(self.config_path.get()) if self.config_path.get() else ROOT/'multigame.example.json'
        try:
            editor.insert('1.0', path.read_text(encoding='utf-8-sig'))
        except OSError as exc:
            editor.insert('1.0', '{}')
            messagebox.showwarning('Configuration', str(exc), parent=window)
        def save():
            try:
                data = json.loads(editor.get('1.0', 'end'))
                if not isinstance(data, dict): raise ValueError('Configuration must be a JSON object')
                dest = filedialog.asksaveasfilename(parent=window, initialfile='multigame.local.json', defaultextension='.json')
                if not dest: return
                Path(dest).write_text(json.dumps(data, indent=2), encoding='utf-8')
                self.config_path.set(dest)
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror('Cannot save configuration', str(exc), parent=window)
        ttk.Button(window, text='Save configuration as…', command=save).pack(pady=10)

    def browse(self, variable, folder):
        p = filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if p: variable.set(p)

    def add_files(self):
        for p in filedialog.askopenfilenames(filetypes=[('Supported inputs', '*.pak *.utoc *.ucas *.vpk *.png *.blend *.pmx *.studio.json'), ('All files', '*.*')]):
            self.inputs.insert('end', p)

    def add_folder(self):
        p = filedialog.askdirectory()
        if p: self.inputs.insert('end', p)

    def remove(self):
        for i in reversed(self.inputs.curselection()): self.inputs.delete(i)

    def start(self, action):
        try:
            config = json.loads(Path(self.config_path.get()).read_text(encoding='utf-8-sig'))
            sources = self.inputs.get(0, 'end')
            if not sources: raise ValueError('Add at least one input')
        except Exception as exc:
            self.messages.put(str(exc)); return
        kind, output = self.kind.get(), self.output.get()
        for b in self.buttons: b.configure(state='disabled')
        def work():
            for source in sources:
                self.messages.put('Reading ' + source)
                try:
                    if action == 'convert-card':
                        if kind != 'koikatsu': raise ValueError('Choose Koikatsu for card conversion')
                        from koikatsu_card import prepare_card
                        result = prepare_card(source, output, config)
                    else:
                        result = inspect(source, kind, config) if action == 'inspect' else str(convert(source, kind, output, config, log=self.messages.put))
                    self.messages.put(json.dumps(result, indent=2))
                except Exception as exc: self.messages.put('FAILED: ' + str(exc))
            self.messages.put(None)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while not self.messages.empty():
            message = self.messages.get()
            if message is None:
                for b in self.buttons: b.configure(state='normal')
            else:
                self.log.configure(state='normal')
                self.log.insert('end', message + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
        self.after(150, self.poll)


if __name__ == '__main__': App().mainloop()
