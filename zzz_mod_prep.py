#!/usr/bin/env python3
"""
zzz_mod_prep.py - turn a ZZZ mod folder into something XXMITools' raw importer accepts.

A ZZZ mod ships <Component>Position.buf / Blend.buf / Texcoord.buf, an .ib, .dds textures
and an .ini. XXMITools' "Import 3DMigoto Raw Buffers" instead wants, per component:

    <name>.vb0  [<name>.vb1 ...]  <name>.ib  <name>.fmt

...which is why you get "unable to find matching .vb* files for the ib".

The important part: the game does NOT use three separate vertex buffers. It uses ONE
interleaved buffer, and ZZMI splits it into three files purely so mods can override each
piece independently - a compute shader stitches them back together at draw time. You can
see this in the numbers: a dump's vb0 stride equals the sum of the mod's three strides
(40 + 32 + 24 = 96, or 40 + 32 + 20 = 92).

So this script CONCATENATES the buffers back into a single vb0 that matches the dump's
layout byte for byte. Splitting them across input slots instead produces elements whose
offsets run past the end of their stride, which is where errors like
"Unhandled TEXCOORD0 dimension: 0" come from.

Usage
-----
  python zzz_mod_prep.py inspect <mod_folder>
      Parse the .ini and report every part, its buffers, strides and vertex counts.
      Run this first - it tells you whether the numbers are self-consistent.

  python zzz_mod_prep.py prepare <mod_folder> -o <out_folder> [--ref <dump_folder>]
      Write the .vb0/.ib/.fmt set into <out_folder>.
      --ref points at the matching ORIGINAL dump (from ZZ-Model-Importer-Assets). If given,
      the real vertex layout is copied from it and used to verify the concatenation order.
      This is strongly preferred - without it the script falls back to a guessed layout.

  Extra flags: --component NAME (one part only), --variant NAME (pick .Flat etc.),
               --split (keep separate slots; almost never what you want)

Runs on plain Python 3.8+. No Blender, no dependencies.
"""

import argparse
import os
import re
import shutil
import sys
from collections import OrderedDict

SLOT_ORDER = ["Position", "Blend", "Texcoord"]

# Which vertex semantics live in which of the mod's .buf files.
SEMANTIC_FAMILY = {
    "Position": {"POSITION", "NORMAL", "TANGENT", "BITANGENT", "BINORMAL"},
    "Blend": {"BLENDWEIGHT", "BLENDWEIGHTS", "BLENDINDICES", "BLENDINDEX"},
    "Texcoord": {"TEXCOORD", "COLOR"},
}


def dxgi_size(fmt):
    """Bytes per element for a DXGI format name, e.g. R32G32B32A32_FLOAT -> 16."""
    f = fmt.replace("DXGI_FORMAT_", "").split("_")[0]
    bits = sum(int(b) for b in re.findall(r"[RGBADXES](\d+)", f))
    return bits // 8


def family_of(semantic_name):
    s = re.sub(r"\d+$", "", semantic_name.upper())
    for fam, names in SEMANTIC_FAMILY.items():
        if s in names:
            return fam
    return None

# --------------------------------------------------------------------------------------
# Fallback layouts, keyed by (slot, stride). Used ONLY when --ref is not supplied.
# These match what ZZZ character shaders commonly use, but strides vary between
# characters and game versions - always prefer --ref.
# Each entry: (SemanticName, SemanticIndex, Format, AlignedByteOffset)
# --------------------------------------------------------------------------------------
GUESSED_LAYOUTS = {
    ("Position", 40): [
        ("POSITION", 0, "R32G32B32_FLOAT", 0),
        ("NORMAL", 0, "R32G32B32_FLOAT", 12),
        ("TANGENT", 0, "R32G32B32A32_FLOAT", 24),
    ],
    ("Position", 28): [
        ("POSITION", 0, "R32G32B32_FLOAT", 0),
        ("NORMAL", 0, "R32G32B32_FLOAT", 12),
        ("TANGENT", 0, "R32G32B32A32_FLOAT", 24),  # 4 half-floats
    ],
    ("Blend", 32): [
        ("BLENDINDICES", 0, "R32G32B32A32_UINT", 0),
        ("BLENDWEIGHT", 0, "R32G32B32A32_FLOAT", 16),
    ],
    ("Blend", 16): [
        ("BLENDWEIGHT", 0, "R32G32B32A32_FLOAT", 0),
    ],
    ("Blend", 8): [
        ("BLENDINDICES", 0, "R8G8B8A8_UINT", 0),
        ("BLENDWEIGHT", 0, "R8G8B8A8_UNORM", 4),
    ],
    ("Texcoord", 8): [
        ("TEXCOORD", 0, "R32G32_FLOAT", 0),
    ],
    ("Texcoord", 12): [
        ("COLOR", 0, "R8G8B8A8_UNORM", 0),
        ("TEXCOORD", 0, "R32G32_FLOAT", 4),
    ],
    ("Texcoord", 16): [
        ("TEXCOORD", 0, "R32G32_FLOAT", 0),
        ("TEXCOORD", 1, "R32G32_FLOAT", 8),
    ],
    ("Texcoord", 20): [
        ("COLOR", 0, "R8G8B8A8_UNORM", 0),
        ("TEXCOORD", 0, "R32G32_FLOAT", 4),
        ("TEXCOORD", 1, "R32G32_FLOAT", 12),
    ],
}


# --------------------------------------------------------------------------------------
# ini parsing
# --------------------------------------------------------------------------------------

class Resource:
    __slots__ = ("section", "stride", "filename", "rtype", "format", "path", "size")

    def __init__(self, section):
        self.section = section
        self.stride = None
        self.filename = None
        self.rtype = None
        self.format = None
        self.path = None
        self.size = None

    def vertex_count(self):
        if self.size is None or not self.stride:
            return None
        q, r = divmod(self.size, self.stride)
        return q if r == 0 else None


def parse_ini(path):
    """Minimal 3DMigoto ini reader. Returns OrderedDict[section] -> OrderedDict[key] -> value."""
    sections = OrderedDict()
    cur = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                cur = line[1:-1]
                sections.setdefault(cur, OrderedDict())
                continue
            if cur is None or "=" not in line:
                continue
            k, v = line.split("=", 1)
            sections[cur][k.strip()] = v.strip()
    return sections


# Input-slot -> buffer family, used ONLY as a last resort. ZZZ does not bind these in
# the obvious order: Texcoord goes to vb1 and Blend to vb2. Because that ordering varies
# between games and even between mods, the buffer's own name always wins over this table.
SLOT_KEY_FAMILY = {"vb0": "Position", "vb1": "Texcoord", "vb2": "Blend",
                   "vb3": None, "ib": "IB"}


def link_overrides(sections):
    """
    3DMigoto binds resources through TextureOverride blocks:

        [TextureOverrideNicoleHairPosition]
        hash = 176bf3d7
        vb0 = ResourceNicoleHairPosition
        vb2 = ResourceNicoleHairBlend

    Use this for COMPONENT IDENTITY (which part a buffer belongs to). Do not use the
    vb index to decide which family a buffer is - see SLOT_KEY_FAMILY.

    Returns {resource_section_lower: (override_name, slot_key)}.
    """
    owner = {}
    for name, kv in sections.items():
        low_name = name.lower()
        if not low_name.startswith("textureoverride"):
            continue
        comp = name[len("TextureOverride"):].strip("_- ")
        for k, v in kv.items():
            key = k.strip().lower()
            if key not in SLOT_KEY_FAMILY:
                continue
            res = v.strip().split(";")[0].strip()
            if res:
                owner[res.lower()] = (comp, key)
    return owner


def family_from_name(resource):
    """
    Which buffer family this resource is, judged by its own file/section name.
    This is the authoritative signal - filenames say Position/Blend/Texcoord plainly.
    """
    if resource.filename and resource.filename.lower().endswith(".ib"):
        return "IB"
    hay = ((resource.filename or "") + " " + resource.section).lower()
    for fam in SLOT_ORDER:
        if fam.lower() in hay:
            return fam
    if "index" in hay:
        return "IB"
    return None


def find_inis(folder):
    out = []
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.lower().endswith(".ini") and not fn.lower().startswith("desktop"):
                out.append(os.path.join(root, fn))
    return sorted(out)


def collect_resources(sections, ini_dir):
    """Every [Resource*] block that points at a real buffer file on disk."""
    res = OrderedDict()
    for name, kv in sections.items():
        if not name.lower().startswith("resource"):
            continue
        low = {k.lower(): v for k, v in kv.items()}
        fn = low.get("filename")
        if not fn:
            continue
        if not fn.lower().endswith((".buf", ".ib")):
            continue  # textures etc.
        r = Resource(name)
        r.filename = fn
        r.rtype = low.get("type")
        r.format = low.get("format")
        try:
            r.stride = int(low["stride"]) if "stride" in low else None
        except ValueError:
            r.stride = None
        p = os.path.normpath(os.path.join(ini_dir, fn.replace("\\", os.sep).replace("/", os.sep)))
        r.path = p
        r.size = os.path.getsize(p) if os.path.isfile(p) else None
        res[name] = r
    return res


def slot_of(resource):
    """Which vb slot a resource belongs to, from its section/file name."""
    hay = (resource.section + " " + (resource.filename or "")).lower()
    if resource.filename and resource.filename.lower().endswith(".ib"):
        return "IB"
    for slot in SLOT_ORDER:
        if slot.lower() in hay:
            return slot
    if "index" in hay:
        return "IB"
    return None


def strip_slot(name, slot):
    """
    Remove the family word and any variant suffix from a name.

        NicoleHairPosition        + Position -> ("NicoleHair", "")
        QingyiBodyPosition.Flat   + Position -> ("QingyiBody", "Flat")
        NicoleHairA               + IB       -> ("NicoleHairA", "")
    """
    name = re.sub(r"^Resource", "", name, flags=re.I)
    name = re.sub(r"^TextureOverride", "", name, flags=re.I)
    name = re.sub(r"^Mod", "", name, flags=re.I)

    variant = ""
    if "." in name:
        name, variant = name.rsplit(".", 1)

    if slot and slot != "IB":
        # the family word may sit mid-name, and a variant is sometimes glued on
        # after it (QingyiBodyPositionFlat)
        m = re.search(slot, name, flags=re.I)
        if m:
            trailing = name[m.end():].strip("_- ")
            if trailing and not variant:
                variant = trailing
            name = name[:m.start()]
    else:
        name = re.sub(r"(Index|IB)$", "", name, flags=re.I)

    return name.strip("_- ") or "Component", variant


def strip_any_slot(name):
    """
    Component name from a TextureOverride, whichever family word it happens to carry.

    An override block is usually named after just one of the buffers it binds
    ([TextureOverrideNicoleHairPosition] binding Position, Blend AND Texcoord), so the
    word to remove is whichever one is present - not the family of the resource being
    looked up.
    """
    for fam in SLOT_ORDER:
        if re.search(fam, name, flags=re.I):
            return strip_slot(name, fam)[0]
    return strip_slot(name, "IB")[0]


def split_section(resource, slot):
    return strip_slot(resource.section, slot)


class Part:
    """One index buffer plus the vertex buffers it draws from."""

    def __init__(self, name, base):
        self.name = name        # output name, taken from the IB (QingyiBodyA)
        self.base = base        # vertex-buffer component (QingyiBody)
        self.ib = None
        self.vbs = OrderedDict()      # slot -> Resource (chosen variant)
        self.variants = OrderedDict()  # slot -> {variant: Resource}

    def vertex_counts(self):
        out = {}
        for slot, r in self.vbs.items():
            vc = r.vertex_count()
            if vc is not None:
                out[slot] = vc
        return out


def pick_variant(by_variant, preferred=""):
    """
    Choose which variant of a buffer to use.

    Multi-toggle mods declare several variants pointing into subfolders that may not
    exist (a packaged mod often ships only one of them), so variants whose file is
    actually on disk always win.
    """
    if preferred:
        for v in by_variant:
            if v.lower() == preferred.lower():
                return by_variant[v], v

    present = {k: v for k, v in by_variant.items() if v.size is not None}
    pool = present or by_variant

    for v in ("", "Base"):
        for k in pool:
            if k.lower() == v.lower():
                return pool[k], k
    k = next(iter(pool))
    return pool[k], k


def group_parts(resources, preferred_variant="", owner=None):
    """
    Reconcile vertex-buffer components with index buffers.

    ZZZ mods name the two differently - buffers are <Comp><Slot>.buf while the index
    buffer is <Comp><Letter>.ib - so IBs are matched to the longest component name
    that prefixes them. One component may own several IBs (drawn as separate parts).
    """
    vb_comps = OrderedDict()   # base -> {slot: {variant: Resource}}
    ib_entries = OrderedDict()  # base -> {variant: Resource}
    orphan_vbs = []

    owner = owner or {}
    for r in resources.values():
        link = owner.get(r.section.lower())

        # 1. the buffer's own name is the authoritative signal
        slot = family_from_name(r)
        # 2. only if the name says nothing, fall back to which input slot it binds to
        if slot is None and link:
            slot = SLOT_KEY_FAMILY.get(link[1])
        if slot is None:
            continue

        # component identity: the TextureOverride name is more reliable than the
        # resource name, but strip the family word off either way
        _b, variant = split_section(r, slot)
        base = strip_any_slot(link[0]) if link else _b
        if slot == "IB":
            ib_entries.setdefault(base, OrderedDict())[variant or r.filename] = r
        else:
            vb_comps.setdefault(base, OrderedDict()).setdefault(slot, OrderedDict())[variant] = r

    # A multi-toggle mod declares the same index buffer once per variant folder. Collapse
    # them to whichever copy is actually present on disk.
    parts, claimed = [], set()
    for ibname, by_variant in ib_entries.items():
        ibres = pick_variant(by_variant, preferred_variant)[0]
        cands = [b for b in vb_comps if ibname.lower().startswith(b.lower())]
        if not cands:
            cands = [b for b in vb_comps if b.lower().startswith(ibname.lower())]
        if not cands:
            p = Part(ibname, None)
            p.ib = ibres
            parts.append(p)
            continue
        base = max(cands, key=len)
        claimed.add(base)
        p = Part(ibname, base)
        p.ib = ibres
        for slot in SLOT_ORDER:
            by_variant = vb_comps[base].get(slot)
            if not by_variant:
                continue
            p.variants[slot] = by_variant
            p.vbs[slot] = pick_variant(by_variant, preferred_variant)[0]
        parts.append(p)

    # Components with no index buffer of their own still become parts - many mods only
    # replace vertex data and leave the game's original topology in place. prepare() can
    # borrow the .ib from the reference dump for these.
    for base in vb_comps:
        if base in claimed:
            continue
        orphan_vbs.append(base)
        p = Part(base, base)
        for slot in SLOT_ORDER:
            by_variant = vb_comps[base].get(slot)
            if not by_variant:
                continue
            p.variants[slot] = by_variant
            p.vbs[slot] = pick_variant(by_variant, preferred_variant)[0]
        if p.vbs:
            parts.append(p)

    return parts, orphan_vbs, vb_comps


# --------------------------------------------------------------------------------------
# .fmt handling
# --------------------------------------------------------------------------------------

def parse_reference_fmt(text):
    """Read strides + elements out of a .fmt or a frame-analysis vb .txt."""
    strides = {}
    elements = []
    topology = "trianglelist"
    ib_format = None
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^vb(\d+) stride:\s*(\d+)$", line)
        if m:
            strides[int(m.group(1))] = int(m.group(2))
            continue
        m = re.match(r"^stride:\s*(\d+)$", line)
        if m:
            strides.setdefault(0, int(m.group(1)))
            continue
        if line.startswith("topology:"):
            topology = line[len("topology:"):].strip()
            continue
        if line.startswith("format:"):
            ib_format = line[len("format:"):].strip()
            continue
        if line.startswith("element["):
            cur = {}
            elements.append(cur)
            continue
        if cur is not None and ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip()
    return strides, elements, topology, ib_format


def find_reference_fmt(ref_dir, component_hint=""):
    """
    Pick the best .fmt / vb0 .txt in a reference dump folder for a given component.

    Frame-analysis dumps look like 'QingyiBodyA-vb0=ac54012f.txt' and each vb txt carries
    the FULL input layout (elements tagged with their InputSlot), so vb0 alone is enough
    for the element list. Per-slot strides come from the vb1/vb2 siblings.
    """
    cands = []
    for root, _d, files in os.walk(ref_dir):
        for fn in files:
            low = fn.lower()
            if low.endswith(".fmt") or (low.endswith(".txt") and "vb0" in low):
                cands.append(os.path.join(root, fn))
    if not cands:
        return None

    hint = (component_hint or "").lower()
    if hint:
        exact = [c for c in cands
                 if os.path.basename(c).lower().split("-vb0")[0].split(".fmt")[0] == hint]
        if exact:
            return exact[0]
        partial = [c for c in cands if hint in os.path.basename(c).lower()]
        if partial:
            return min(partial, key=lambda p: len(os.path.basename(p)))
        # try progressively shorter prefixes of the hint (QingyiBodyA -> QingyiBody -> ...)
        for cut in range(len(hint) - 1, 3, -1):
            sub = hint[:cut]
            partial = [c for c in cands if sub in os.path.basename(c).lower()]
            if partial:
                return min(partial, key=lambda p: len(os.path.basename(p)))

    cands.sort(key=lambda p: (0 if p.lower().endswith(".fmt") else 1, len(p)))
    return cands[0]


def elements_from_reference(ref_path):
    """Parse a reference layout, pulling per-slot strides from vb1/vb2 siblings if present."""
    with open(ref_path, "r", encoding="utf-8", errors="replace") as f:
        strides, elements, topo, ibfmt = parse_reference_fmt(f.read())

    base = os.path.basename(ref_path)
    if "-vb0" in base.lower():
        prefix = ref_path[:ref_path.lower().index("-vb0")]
        for slot in (1, 2, 3):
            for sib in _glob_slot(prefix, slot):
                with open(sib, "r", encoding="utf-8", errors="replace") as f:
                    s2, e2, _t, _i = parse_reference_fmt(f.read())
                for k, v in s2.items():
                    strides.setdefault(slot if k == 0 else k, v)
                if not elements:
                    elements = e2
                break

    # the vb0 txt reports its stride under the bare "stride:" key -> that's slot 0
    if 0 not in strides and strides:
        pass
    return strides, elements, topo, ibfmt


def _glob_slot(prefix, slot):
    import glob as _g
    return sorted(_g.glob(_g.escape(prefix) + "-vb%d=*.txt" % slot))


def find_reference_ib(ref_dir, component_hint=""):
    """
    Locate an index buffer in the reference dump.

    Many mods only override vertex data and leave topology alone, so they ship no .ib
    at all. In that case the original dump's index buffer is the correct one to use.
    Returns (ib_path, ib_fmt_path_or_None) or None.
    """
    cands = []
    for root, _d, files in os.walk(ref_dir):
        for fn in files:
            if fn.lower().endswith(".ib") or "-ib=" in fn.lower():
                cands.append(os.path.join(root, fn))
    bins = [c for c in cands if not c.lower().endswith(".txt")]
    if not bins:
        return None

    hint = (component_hint or "").lower()
    pick = None
    if hint:
        exact = [c for c in bins
                 if os.path.basename(c).lower().split("-ib")[0].split(".ib")[0] == hint]
        pick = exact[0] if exact else None
        if pick is None:
            part = [c for c in bins if hint in os.path.basename(c).lower()]
            if part:
                pick = min(part, key=lambda p: len(os.path.basename(p)))
        if pick is None:
            for cut in range(len(hint) - 1, 3, -1):
                part = [c for c in bins if hint[:cut] in os.path.basename(c).lower()]
                if part:
                    pick = min(part, key=lambda p: len(os.path.basename(p)))
                    break
    if pick is None:
        pick = min(bins, key=lambda p: len(os.path.basename(p)))

    txt = None
    for c in cands:
        if c.lower().endswith(".txt") and os.path.basename(c).startswith(
                os.path.splitext(os.path.basename(pick))[0]):
            txt = c
            break
    return pick, txt


def build_fmt(strides, elements, topology="trianglelist", ib_format="DXGI_FORMAT_R32_UINT"):
    """Render a .fmt in exactly the shape XXMITools' parser expects."""
    lines = []
    for slot in sorted(strides):
        lines.append("vb%d stride: %d" % (slot, strides[slot]))
    lines.append("topology: %s" % topology)
    lines.append("format: %s" % ib_format)
    for i, e in enumerate(elements):
        lines.append("element[%d]:" % i)
        lines.append("  SemanticName: %s" % e["SemanticName"])
        lines.append("  SemanticIndex: %s" % e.get("SemanticIndex", 0))
        lines.append("  Format: %s" % e["Format"])
        lines.append("  InputSlot: %s" % e.get("InputSlot", 0))
        lines.append("  AlignedByteOffset: %s" % e["AlignedByteOffset"])
        lines.append("  InputSlotClass: %s" % e.get("InputSlotClass", "per-vertex"))
        lines.append("  InstanceDataStepRate: %s" % e.get("InstanceDataStepRate", 0))
    return "\n".join(lines) + "\n"


def reference_spans(elements):
    """
    Work out where each mod .buf lands inside the dump's single interleaved vertex.

    Returns [(family, start, span), ...] ordered by byte offset, or None if the
    reference doesn't cleanly partition into Position/Blend/Texcoord regions.
    """
    groups = {}
    for e in elements:
        fam = family_of(e["SemanticName"])
        if fam is None:
            return None
        try:
            off = int(e["AlignedByteOffset"])
        except (KeyError, ValueError):
            return None
        end = off + dxgi_size(e["Format"])
        lo, hi = groups.get(fam, (off, end))
        groups[fam] = (min(lo, off), max(hi, end))

    ordered = sorted(((f, lo, hi) for f, (lo, hi) in groups.items()), key=lambda t: t[1])
    spans, cursor = [], 0
    for fam, lo, hi in ordered:
        if lo != cursor:
            return None  # gap or overlap - not a clean concatenation
        spans.append((fam, lo, hi - lo))
        cursor = hi
    return spans


def interleave(sources, count, out_path):
    """sources: [(path, stride), ...] in byte order. Writes one interleaved buffer."""
    total = sum(s for _, s in sources)
    out = bytearray(total * count)
    off = 0
    for path, stride in sources:
        with open(path, "rb") as f:
            data = f.read()
        for i in range(count):
            base = i * total + off
            out[base:base + stride] = data[i * stride:(i + 1) * stride]
        off += stride
    with open(out_path, "wb") as f:
        f.write(out)
    return total


def remap_to_slots(elements, order, strides):
    """Convert absolute-offset, slot-0 elements into per-slot offsets for --split output."""
    bounds, cursor = [], 0
    for stride in strides:
        bounds.append((cursor, cursor + stride))
        cursor += stride
    out = []
    for e in elements:
        off = int(e["AlignedByteOffset"])
        slot = 0
        for i, (lo, hi) in enumerate(bounds):
            if lo <= off < hi:
                slot, off = i, off - lo
                break
        e2 = dict(e)
        e2["InputSlot"] = slot
        e2["AlignedByteOffset"] = off
        out.append(e2)
    return out


def guessed_merged_elements(order_strides):
    """order_strides: [(family, stride), ...] -> elements with absolute offsets, slot 0."""
    elements, warnings, base = [], [], 0
    for fam, stride in order_strides:
        layout = GUESSED_LAYOUTS.get((fam, stride))
        if layout is None:
            warnings.append("no known layout for %s at stride %d" % (fam, stride))
            return [], warnings
        for sem, idx, fmt, off in layout:
            elements.append({
                "SemanticName": sem, "SemanticIndex": idx, "Format": fmt,
                "InputSlot": 0, "AlignedByteOffset": base + off,
                "InputSlotClass": "per-vertex", "InstanceDataStepRate": 0,
            })
        base += stride
    return elements, warnings


def ib_dxgi_format(res, vertex_count_hint=None):
    if res.format:
        f = res.format
        return f if f.startswith("DXGI_FORMAT_") else "DXGI_FORMAT_" + f
    if res.size is not None:
        if vertex_count_hint and vertex_count_hint > 65535:
            return "DXGI_FORMAT_R32_UINT"
        if res.size % 4 == 0:
            return "DXGI_FORMAT_R32_UINT"
        return "DXGI_FORMAT_R16_UINT"
    return "DXGI_FORMAT_R32_UINT"


# --------------------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------------------

def cmd_inspect(args):
    folder = args.mod_folder
    inis = find_inis(folder)
    if not inis:
        print("No .ini found under %s" % folder)
        return 1

    print("Mod folder: %s" % os.path.abspath(folder))

    if args.raw:
        for ini in inis:
            print("\n########## RAW: %s ##########" % os.path.relpath(ini, folder))
            for name, kv in parse_ini(ini).items():
                print("[%s]" % name)
                for k, v in kv.items():
                    print("  %s = %s" % (k, v))
        print("\n########## files on disk ##########")
        for root, _d, files in os.walk(folder):
            for fn in sorted(files):
                p = os.path.join(root, fn)
                print("  %-44s %d bytes" % (os.path.relpath(p, folder), os.path.getsize(p)))
        return 0

    for ini in inis:
        print("\n=== %s ===" % os.path.relpath(ini, folder))
        sections = parse_ini(ini)
        res = collect_resources(sections, os.path.dirname(ini))
        if not res:
            print("  (no buffer resources - probably a namespace/toggle ini)")
            continue

        overrides = [s for s in sections if s.lower().startswith("textureoverride")]
        hashes = sorted({v for s in overrides for k, v in sections[s].items()
                         if k.lower() == "hash"})
        if hashes:
            print("  hashes: %s" % ", ".join(hashes))
            print("  (look these up in ZZ-Model-Importer-Assets to identify the character)")

        parts, orphans, _vb = group_parts(res, args.variant or "", link_overrides(sections))
        for p in parts:
            print("\n  part '%s'%s" % (p.name, "  (buffers: %s)" % p.base if p.base else ""))
            if p.ib is not None:
                r = p.ib
                print("    %-9s %-30s %-12s size=%-10s %s" % (
                    "IB", r.filename, r.format or "format=?",
                    r.size if r.size is not None else "-",
                    "ok" if r.size is not None else "MISSING FILE"))
            else:
                print("    %-9s %s" % ("IB", "- none in the mod; will be borrowed from --ref -"))
            for slot in SLOT_ORDER:
                r = p.vbs.get(slot)
                if r is None:
                    print("    %-9s %s" % (slot, "- absent -"))
                    continue
                vc = r.vertex_count()
                print("    %-9s %-30s stride=%-5s size=%-10s verts=%-8s %s" % (
                    slot, r.filename, r.stride if r.stride else "-",
                    r.size if r.size is not None else "-",
                    vc if vc is not None else "-",
                    "ok" if r.size is not None else "MISSING FILE"))
                if r.size is not None and r.stride and r.size % r.stride:
                    print("      ^ size not divisible by stride - the ini's stride is wrong")
                others = [v for v in p.variants.get(slot, {}) if p.variants[slot][v] is not r]
                if others:
                    print("      variants available: %s   (use --variant NAME)" % ", ".join(
                        v or "<base>" for v in others))
            counts = p.vertex_counts()
            distinct = set(counts.values())
            if len(distinct) > 1:
                print("    !! vertex counts disagree across buffers: %s" % counts)
            elif distinct:
                print("    vertex count: %d (consistent)" % distinct.pop())

        if orphans:
            print("\n  parts with no index buffer of their own: %s" % ", ".join(orphans))
            print("  (normal for vertex-only mods - 'prepare --ref ...' will borrow the")
            print("   original index buffer from the reference dump)")
    return 0


def cmd_prepare(args):
    folder = args.mod_folder
    out = args.out
    inis = find_inis(folder)
    if not inis:
        print("No .ini found under %s" % folder)
        return 1
    os.makedirs(out, exist_ok=True)

    if args.ref:
        ra, oa = os.path.abspath(args.ref), os.path.abspath(out)
        if oa == ra or oa.startswith(ra + os.sep):
            print("REFUSING: the output folder is inside the reference dump.")
            print("  -o must be a fresh folder, otherwise you overwrite your reference assets.")
            return 1

    written, used_names = 0, {}
    for ini in inis:
        if args.ini and args.ini.lower() not in os.path.basename(ini).lower():
            continue
        sections = parse_ini(ini)
        res = collect_resources(sections, os.path.dirname(ini))
        parts, _orphans, _vb = group_parts(res, args.variant or "", link_overrides(sections))

        for p in parts:
            if args.component and args.component.lower() not in p.name.lower():
                continue
            if not p.vbs:
                print("skip '%s': no vertex buffers" % p.name)
                continue

            missing = [f for f, r in p.vbs.items() if r.size is None]
            if missing:
                print("skip '%s': buffer file(s) not on disk: %s"
                      % (p.name, ", ".join("%s=%s" % (f, p.vbs[f].filename) for f in missing)))
                continue

            # Three cases, and they need different handling:
            #   IB present            -> use it
            #   no IB declared at all  -> vertex-only mod, borrow the game's original
            #   IB declared but absent -> a disabled/unshipped variant, skip it
            ib_path = None
            if p.ib is not None and p.ib.size is not None:
                ib_path = p.ib.path
            elif p.ib is not None:
                print("skip '%s': its index buffer %s is declared but not on disk "
                      "(unshipped toggle variant)" % (p.name, p.ib.filename))
                continue
            elif args.ref:
                found = find_reference_ib(args.ref, p.name)
                if found:
                    ib_path, _ibtxt = found
                    print("note '%s': mod has no index buffer, borrowing %s from the reference"
                          % (p.name, os.path.basename(ib_path)))
            if ib_path is None:
                print("skip '%s': no index buffer, and none found in --ref "
                      "(pass --ref, or the part is vertex-only)" % p.name)
                continue

            # resolve the reference layout per part - Hair and Body differ
            ref_strides, ref_elements = {}, []
            ref_topo, ref_ibfmt, ref_path = "trianglelist", None, None
            if args.ref:
                ref_path = find_reference_fmt(args.ref, p.name)
                if ref_path is None:
                    print("!! '%s': no .fmt or vb0 .txt under %s" % (p.name, args.ref))
                else:
                    ref_strides, ref_elements, ref_topo, ref_ibfmt = \
                        elements_from_reference(ref_path)

            # several inis can define the same part name - keep both rather than clobber
            outname = p.name
            if outname in used_names:
                used_names[outname] += 1
                outname = "%s_%d" % (p.name, used_names[p.name])
            else:
                used_names[outname] = 1
            base = os.path.join(out, outname)

            # Vertex counts must agree or interleaving is meaningless
            counts = p.vertex_counts()
            if not counts:
                print("skip '%s': vertex buffers have no stride in the ini" % p.name)
                continue
            if len(set(counts.values())) > 1:
                print("skip '%s': vertex counts disagree across buffers: %s" % (p.name, counts))
                continue
            count = next(iter(counts.values()))

            # Decide the concatenation order. The reference tells us authoritatively;
            # otherwise fall back to the ZZMI convention.
            spans = reference_spans(ref_elements) if ref_elements else None
            if spans:
                order = [fam for fam, _lo, _span in spans]
                for fam, _lo, span in spans:
                    r = p.vbs.get(fam)
                    if r is None:
                        print("!! '%s': reference expects a %s buffer, mod has none" % (p.name, fam))
                    elif r.stride != span:
                        print("!! '%s': %s stride is %d, reference region is %d bytes"
                              % (p.name, fam, r.stride, span))
            else:
                order = [s for s in SLOT_ORDER if s in p.vbs]

            sources = [(p.vbs[f].path, p.vbs[f].stride) for f in order
                       if f in p.vbs and p.vbs[f].size is not None and p.vbs[f].stride]
            if not sources:
                print("skip '%s': no usable vertex buffers" % p.name)
                continue

            merged_stride = sum(s for _, s in sources)
            if ref_elements and 0 in ref_strides and merged_stride != ref_strides[0]:
                print("!! '%s': merged stride %d != reference vb0 stride %d"
                      % (p.name, merged_stride, ref_strides[0]))
                print("     the mod uses a different vertex format than this reference dump")

            if ref_elements:
                elements = ref_elements
                layout_src = "ref:" + os.path.basename(ref_path)
            else:
                elements, warnings = guessed_merged_elements(
                    [(f, p.vbs[f].stride) for f in order if f in p.vbs])
                for w in warnings:
                    print("!! '%s': %s" % (p.name, w))
                if not elements:
                    print("skip '%s': could not determine a vertex layout" % p.name)
                    continue
                layout_src = "GUESSED - verify"

            if args.split:
                copied = []
                for slot_i, fam in enumerate(order):
                    shutil.copyfile(p.vbs[fam].path, "%s.vb%d" % (base, slot_i))
                    copied.append(slot_i)
                numbered = {i: p.vbs[f].stride for i, f in enumerate(order)}
                elements = remap_to_slots(elements, order, [p.vbs[f].stride for f in order])
                written_desc = ",".join("vb%d" % i for i in copied)
            else:
                interleave(sources, count, base + ".vb0")
                numbered = {0: merged_stride}
                written_desc = "vb0"

            shutil.copyfile(ib_path, base + ".ib")
            fmt = build_fmt(numbered, elements, ref_topo,
                            ref_ibfmt or (ib_dxgi_format(p.ib, count) if p.ib
                                          else "DXGI_FORMAT_R32_UINT"))
            with open(base + ".fmt", "w", encoding="utf-8") as f:
                f.write(fmt)

            print("wrote %s.{%s,ib,fmt}  %s  stride=%d  verts=%d  layout=%s" % (
                outname, written_desc,
                " + ".join("%s:%d" % (f, p.vbs[f].stride) for f in order if f in p.vbs),
                merged_stride, count, layout_src))
            written += 1

    if written:
        print("\n%d part(s) -> %s" % (written, os.path.abspath(out)))
        print("In Blender: File > Import > 3DMigoto Raw Buffers, select the .ib files.")
    else:
        print("\nNothing written. Run 'inspect' to see what the ini actually contains.")
    return 0 if written else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect", help="report parts, strides and vertex counts")
    p.add_argument("mod_folder")
    p.add_argument("--variant", help="prefer this buffer variant (e.g. Flat)")
    p.add_argument("--raw", action="store_true",
                   help="dump every ini section and every file on disk, unprocessed. "
                        "Use this when a mod won't parse and you need to see why")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("prepare", help="write .vb0/.vb1/.vb2/.ib/.fmt for raw import")
    p.add_argument("mod_folder")
    p.add_argument("-o", "--out", required=True, help="output folder")
    p.add_argument("--ref", help="matching original dump folder (strongly recommended)")
    p.add_argument("--component", help="only this part, substring match")
    p.add_argument("--variant", help="prefer this buffer variant (e.g. Flat)")
    p.add_argument("--ini", help="only process inis whose filename contains this")
    p.add_argument("--split", action="store_true",
                   help="keep the buffers in separate vb0/vb1/vb2 slots instead of "
                        "interleaving them into one vb0 (rarely what you want)")
    p.set_defaults(func=cmd_prepare)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
