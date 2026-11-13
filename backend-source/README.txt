CUSTOM MATERIAL EXPORT BACKEND

Upstream: https://github.com/joric/CUE4Parse.CLI
Exact upstream revision: UPSTREAM_COMMIT.txt
Changes: textured-export.patch
License: Apache-2.0; upstream LICENSE and NOTICE are in ../tools/.

Changes add multi-directory provider mounting with top-level-only scanning,
retain named slots whose FPackageIndex reports None, export exact material-slot
JSON references, and resolve null duplicate slots to their unique same-mesh base.

Build with .NET SDK 10:
git clone https://github.com/joric/CUE4Parse.CLI.git
cd CUE4Parse.CLI
git checkout <revision from UPSTREAM_COMMIT.txt>
git apply <path to textured-export.patch>
dotnet publish CUE4Parse.CLI/CUE4Parse.CLI.csproj -c Release -o publish -p:PublishTrimmed=false -p:CUE4PARSE_SKIP_NATIVE=true

Copy publish/CUE4Parse.CLI.exe to ../tools/cue4parse-materials.exe.
Untrimmed publishing preserves the reflected JSON material parameter payloads.
The Python GUI build command (Python 3.10 plus dependencies) is:
python -m PyInstaller --noconfirm --onedir --windowed --name RivalsFbxConverter converter.py
Keep the existing tools, mappings, materials.py and blender_convert.py beside the
resulting executable and its _internal directory. materials.py is also bundled.
