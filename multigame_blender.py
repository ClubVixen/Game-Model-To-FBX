"""Background worker. Never opens or changes the interactive Blender scene."""
import bpy
import bmesh
import json
from pathlib import Path
import sys


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
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix('.blend')))
    bpy.ops.export_scene.fbx(filepath=str(out), use_selection=True,
        object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False, bake_anim=False, use_mesh_modifiers=False,
        path_mode='COPY', embed_textures=True, axis_forward='-Z', axis_up='Y')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(out), use_anim=False)
    after = snapshot()
    for key in ('vertices', 'bones', 'weighted_vertices', 'bound_meshes'):
        if after[key] != before[key]:
            raise RuntimeError(f'FBX round-trip changed {key}: {before[key]} -> {after[key]}')
    outputs.append({'fbx': str(out), 'before': before, 'after': after})
(target/'validation.json').write_text(json.dumps(outputs, indent=2))
