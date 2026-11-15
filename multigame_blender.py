"""Background worker. Never opens or changes the interactive Blender scene."""
import bpy
import bmesh
import json
from pathlib import Path
import sys
import re


def export_textures(objects, folder):
    folder.mkdir(parents=True, exist_ok=True)
    images, bindings = {}, []
    def visit(tree, seen):
        if not tree or tree.as_pointer() in seen: return
        seen.add(tree.as_pointer())
        for node in tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                yield node.image
            elif node.type == 'GROUP':
                yield from visit(node.node_tree, seen)
    for obj in objects:
        if obj.type != 'MESH': continue
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes: continue
            for image in visit(mat.node_tree, set()):
                key = image.as_pointer()
                if key not in images:
                    if image.source not in {'FILE', 'GENERATED'}:
                        raise ValueError(f'Unsupported editable texture source: {image.name} ({image.source})')
                    name = re.sub(r'[^A-Za-z0-9_.-]', '_', image.name)[:100]
                    path = folder / f'{len(images):03d}_{Path(name).stem}.png'
                    # Load external pixels before replacing their source path.
                    if not image.has_data: image.pixels[0]
                    if not image.has_data: raise ValueError(f'Texture has no pixels: {image.name}')
                    image.filepath_raw = str(path)
                    image.file_format = 'PNG'
                    image.save()
                    if not path.is_file() or path.stat().st_size == 0:
                        raise ValueError(f'Texture was not written: {image.name}')
                    if image.packed_file: image.unpack(method='REMOVE')
                    image.filepath = str(path)
                    images[key] = str(path)
                bindings.append({'object':obj.name,'material':mat.name,'image':image.name,'file':images[key]})
    return bindings


def import_asset(path):
    path = Path(path)
    if path.suffix.lower() == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False)
    else:
        bpy.ops.import_scene.gltf(filepath=str(path))


def snapshot(objects=None):
    objects = list(bpy.context.scene.objects if objects is None else objects)
    meshes = [o for o in objects if o.type == 'MESH']
    rigs = [o for o in objects if o.type == 'ARMATURE']
    weighted = 0
    for o in meshes:
        bones = {b.name for m in o.modifiers if m.type == 'ARMATURE' and m.object for b in m.object.data.bones}
        groups = {g.index for g in o.vertex_groups if g.name in bones}
        weighted += sum(any(g.group in groups and g.weight > 1e-8 for g in v.groups) for v in o.data.vertices)
    return {'meshes': len(meshes), 'vertices': sum(len(o.data.vertices) for o in meshes),
            'bones': sum(len(o.data.bones) for o in rigs), 'weighted_vertices': weighted,
            'bound_meshes': sum(any(m.type == 'ARMATURE' and m.object for m in o.modifiers) for o in meshes),
            'materials': len(bpy.data.materials)}


job = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text())
target = Path(job['target'])
outputs = []
kind = job['kind']
inputs = job.get('inputs', [job['source']])
if kind == 'zzz':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(job['base_fbx'])
    rigs = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    if len(rigs) != 1:
        raise ValueError('ZZZ base must contain exactly one skeleton')
    rig = rigs[0]
    for o in list(bpy.context.scene.objects):
        if o.type != 'ARMATURE':
            bpy.data.objects.remove(o, do_unlink=True)
    # Extracted FBXs can carry a neutral pose differing from their bind transforms.
    # The raw buffers are already in that neutral shape; bind against this pose.
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.preferences.addon_enable(module='XXMITools')
    maps = json.loads(Path(job['bone_map']).read_text())
    textures = job.get('material_map', {})
    for path in inputs:
        p = Path(path)
        before = set(bpy.data.objects)
        bpy.ops.import_mesh.migoto_raw_buffers(filepath=str(p), files=[{'name': p.name}],
            axis_forward=job.get('zzz_axis_forward', 'Y'), axis_up=job.get('zzz_axis_up', 'Z'))
        imported = [o for o in set(bpy.data.objects)-before if o.type == 'MESH']
        if not imported:
            raise RuntimeError(f'No mesh imported from {p}')
        # Rig Transfer saves maps per draw part; shared indices can mean different bones.
        mapping = maps.get('parts', {}).get(p.stem, {}).get('map')
        if mapping is None:
            mapping = maps.get(p.stem, maps.get('*', {}))
        for obj in imported:
            # Shared buffers include vertices for other draws/toggle variants.
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
            bm.to_mesh(obj.data)
            bm.free()
            weights = []
            names = {g.index: g.name for g in obj.vertex_groups}
            for vertex in obj.data.vertices:
                merged = {}
                for weight in vertex.groups:
                    if weight.weight <= 1e-8:
                        continue
                    name = names[weight.group]
                    dest = mapping.get(name) if name.isdigit() else name
                    if not dest or dest not in rig.data.bones:
                        raise ValueError(f'{p.stem}: unmapped skin index {name}')
                    merged[dest] = merged.get(dest, 0.0) + weight.weight
                weights.append(merged)
            # Renaming collisions creates .001 groups, which do not bind to the bone.
            obj.vertex_groups.clear()
            groups = {name: obj.vertex_groups.new(name=name)
                      for name in sorted({n for w in weights for n in w})}
            for index, merged in enumerate(weights):
                for name, weight in merged.items():
                    groups[name].add([index], weight, 'REPLACE')
            world = obj.matrix_world.copy()
            obj.parent = rig
            obj.matrix_world = world
            mod = obj.modifiers.new('Skin', 'ARMATURE')
            mod.object = rig
            texpath = textures.get(p.stem)
            if not texpath:
                raise ValueError(f'Missing material_map diffuse texture for {p.stem}')
            mat = bpy.data.materials.new(p.stem)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get('Principled BSDF')
            tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
            tex.image = bpy.data.images.load(texpath, check_existing=True)
            mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            mat.node_tree.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
            obj.data.materials.clear()
            obj.data.materials.append(mat)
    inputs = [None]

for index, path in enumerate(inputs):
    if kind != 'zzz':
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if kind == 'koikatsu':
            if job.get('studio_manifest'):
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from studio_import import import_studio
                import_studio(job['studio_manifest'])
            else:
                bpy.ops.wm.open_mainfile(filepath=str(Path(job['source']).resolve()))
        else:
            import_asset(path)
    # Remove glTF bone display meshes, never real character geometry.
    custom = {b.custom_shape for o in bpy.context.scene.objects if o.type == 'ARMATURE'
              for b in o.pose.bones if b.custom_shape}
    for obj in custom:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.context.scene.objects:
        if obj.type in {'MESH', 'ARMATURE'} and not obj.hide_render and obj.visible_get():
            obj.select_set(True)
    before = snapshot(bpy.context.selected_objects)
    if not before['vertices'] or not before['bones'] or not before['weighted_vertices']:
        raise ValueError('Expected a rigged mesh; empty or unskinned result rejected')
    name = Path(path).stem if path else Path(job['source']).stem
    out = target / f'{index:02d}_{name}.fbx'
    mesh_inventory = [{'name':o.name,'vertices':len(o.data.vertices),'materials':[m.name for m in o.data.materials if m]}
                      for o in bpy.context.selected_objects if o.type == 'MESH']
    for required in job.get('required_mesh_names', []):
        if not any(required.casefold() in o['name'].casefold() for o in mesh_inventory):
            raise ValueError(f'Required accessory/mesh absent from export: {required}')
    for required in job.get('required_material_names', []):
        if not any(required.casefold() in m.casefold() for o in mesh_inventory for m in o['materials']):
            raise ValueError(f'Required accessory material absent from export: {required}')
    texture_bindings = export_textures(list(bpy.context.selected_objects), target/'textures'/out.stem)
    (target / f'{index:02d}_materials.json').write_text(json.dumps(texture_bindings, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix('.blend')))
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix('.blend')))
    bpy.ops.export_scene.fbx(filepath=str(out), use_selection=True,
        object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False, bake_anim=False, use_mesh_modifiers=False,
        path_mode='RELATIVE', embed_textures=False, axis_forward='-Z', axis_up='Y')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(out), use_anim=False)
    after = snapshot()
    for img in bpy.data.images:
        if img.source == 'FILE' and img.filepath and not Path(bpy.path.abspath(img.filepath)).is_file():
            raise RuntimeError(f'FBX texture reference is missing: {img.filepath}')
    for key in ('vertices', 'bones', 'weighted_vertices', 'bound_meshes'):
        if after[key] != before[key]:
            raise RuntimeError(f'FBX round-trip changed {key}: {before[key]} -> {after[key]}')
    outputs.append({'fbx': str(out), 'before': before, 'after': after,
                    'meshes':mesh_inventory,'textures':texture_bindings})
(target/'validation.json').write_text(json.dumps(outputs, indent=2))
