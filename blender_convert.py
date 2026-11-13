"""Run with Blender --background --python this_file -- extracted_dir output_dir."""
import bpy
import sys
import json
import tempfile
import shutil
from pathlib import Path

source, destination = map(Path, sys.argv[sys.argv.index('--') + 1:])
destination.mkdir(parents=True, exist_ok=True)
report = []
material_report = json.loads((source/'material_recipes.json').read_text()) if (source/'material_recipes.json').exists() else None

def apply_materials(asset, meshes):
    if material_report is None:
        raise RuntimeError('Material recipes missing; refusing an untextured export.')
    slots = json.loads(asset.with_suffix('.materials.json').read_text())
    by_slot = {s['slot']: s for s in slots}
    assigned = []
    for mat in {m for obj in meshes for m in obj.data.materials if m}:
        slot = by_slot.get(mat.name)
        if slot is None or slot.get('json') not in material_report['materials']:
            raise RuntimeError(f'Material unresolved: {mat.name} in {asset}')
        recipe = material_report['materials'][slot['json']]
        mat.use_nodes = True
        mat.node_tree.nodes.clear()
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        output = nodes.new('ShaderNodeOutputMaterial')
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        bsdf.inputs['Base Color'].default_value = recipe['base_color']
        bsdf.inputs['Roughness'].default_value = recipe['roughness']
        bsdf.inputs['Metallic'].default_value = recipe['metallic']
        bsdf.inputs['Alpha'].default_value = recipe['alpha']
        bsdf.inputs['Emission Strength'].default_value = recipe['emission_strength']
        if recipe['blend_mode'] != 0:
            mat.surface_render_method = 'DITHERED'
        baked_material = recipe.get('mesh_base_color',{}).get(str(asset.relative_to(source)))
        if baked_material:
            for obj in meshes:
                if mat.name not in obj.data.materials: continue
                index = obj.data.materials.find(mat.name)
                if not obj.data.uv_layers.get('Original_UV0'):
                    if len(obj.data.uv_layers) >= 8:
                        unused = next((layer for layer in reversed(list(obj.data.uv_layers)[2:])
                                       if all((v.uv-layer.data[0].uv).length<1e-6 for v in layer.data)), None)
                        if unused is None:
                            raise RuntimeError('Hair bake needs a spare UV channel; all eight source channels contain data.')
                        obj.data.uv_layers.remove(unused)
                    original = obj.data.uv_layers.new(name='Original_UV0')
                    for a,b in zip(original.data,obj.data.uv_layers[0].data): a.uv=b.uv
                for face in obj.data.polygons:
                    if face.material_index == index:
                        for li in face.loop_indices: obj.data.uv_layers[0].data[li].uv = obj.data.uv_layers[1].data[li].uv
            recipe['approximations'].append('Hair color atlas uses the first export UV channel; original UV0 preserved as Original_UV0. Hair tangent normal map omitted because UV1 uses a different tangent frame.')
        used = {}
        uv_sets = {}
        for channel, filename in recipe['textures'].items():
            if channel in ('occlusion','hair_shadow'):
                continue  # FBX has no dedicated AO socket; PNG remains available.
            if baked_material and channel == 'normal': continue
            filename = baked_material.get('extra_textures',{}).get(channel,filename) if baked_material else filename
            baked = recipe.get('mesh_base_color',{}).get(str(asset.relative_to(source))) if channel == 'base_color' else None
            if baked:
                filename = baked['texture']
            image = bpy.data.images.load(str(source/filename), check_existing=True)
            image.colorspace_settings.name = 'sRGB' if channel in ('base_color','emission') else 'Non-Color'
            tex = nodes.new('ShaderNodeTexImage')
            tex.image = image
            tex.label = channel
            used[channel] = image.name
            if channel == 'normal':
                normal = nodes.new('ShaderNodeNormalMap')
                links.new(tex.outputs['Color'],normal.inputs['Color'])
                links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
            else:
                socket = {'base_color':'Base Color','roughness':'Roughness','metallic':'Metallic','emission':'Emission Color'}[channel]
                links.new(tex.outputs['Color'],bsdf.inputs[socket])
                if channel == 'base_color' and recipe['blend_mode'] != 0:
                    links.new(tex.outputs['Alpha'],bsdf.inputs['Alpha'])
        mat['unreal_material'] = recipe['source']
        assigned.append({'name':mat.name,'textures':used,'uv_sets':uv_sets,'solid_color':not bool(used.get('base_color')),
                         'approximations':recipe['approximations'] + ([slot['fallback']] if slot.get('fallback') else [])})
    return assigned

def verify_materials(expected, meshes, isolated_dir):
    from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
    actual={m.name:m for obj in meshes for m in obj.data.materials if m}
    checked=[]
    for item in expected:
        if item['name'] not in actual:
            raise RuntimeError('FBX material missing: '+item['name'])
        wrapper=PrincipledBSDFWrapper(actual[item['name']],is_readonly=True)
        channels={'base_color':wrapper.base_color_texture,'normal':wrapper.normalmap_texture,
                  'roughness':wrapper.roughness_texture,'metallic':wrapper.metallic_texture,
                  'emission':wrapper.emission_color_texture}
        for name in item['textures']:
            tex=channels[name]
            if tex is None or tex.image is None or tex.image.size[0] == 0:
                raise RuntimeError(f'FBX texture missing: {item["name"]}/{name}')
            if not tex.image.packed_file and not Path(bpy.path.abspath(tex.image.filepath)).is_file():
                raise RuntimeError(f'FBX texture file unavailable: {tex.image.filepath}')
            if not tex.image.packed_file and not Path(bpy.path.abspath(tex.image.filepath)).resolve().is_relative_to(isolated_dir):
                raise RuntimeError(f'FBX depends on an external texture instead of embedding it: {tex.image.filepath}')
        checked.append(item)
    return checked
for asset in sorted(source.rglob('*.glb')):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(asset), bone_heuristic='BLENDER')
    rigs = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    # Blender's glTF importer creates an Icosphere for bone display. It is not
    # source geometry and must not appear as a floating object in the FBX.
    shapes = {bone.custom_shape for rig in rigs for bone in rig.pose.bones if bone.custom_shape}
    for rig in rigs:
        for bone in rig.pose.bones:
            bone.custom_shape = None
    for shape in shapes:
        bpy.data.objects.remove(shape, do_unlink=True)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not rigs:
        continue
    assigned_materials = apply_materials(asset, meshes)
    before = {'bones': sum(len(o.data.bones) for o in rigs),
              'vertices': sum(len(o.data.vertices) for o in meshes),
              'weighted_vertices': sum(sum(any(g.weight > 0 for g in v.groups) for v in o.data.vertices) for o in meshes)}
    if not before['weighted_vertices']:
        raise RuntimeError(f'No skin weights: {asset}')
    relative = asset.relative_to(source).with_suffix('.fbx')
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=str(target), object_types={'ARMATURE', 'MESH'},
        add_leaf_bones=False, use_armature_deform_only=False, bake_anim=False,
        apply_scale_options='FBX_SCALE_UNITS', path_mode='COPY', embed_textures=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    validation_temp = tempfile.TemporaryDirectory(prefix='rivals-fbx-validation-')
    isolated_dir = Path(validation_temp.name).resolve()
    isolated_fbx = isolated_dir/target.name
    shutil.copy2(target, isolated_fbx)
    bpy.ops.import_scene.fbx(filepath=str(isolated_fbx))
    rigs = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    checked_materials = verify_materials(assigned_materials, meshes, isolated_dir)
    after = {'bones': sum(len(o.data.bones) for o in rigs),
             'vertices': sum(len(o.data.vertices) for o in meshes),
             'weighted_vertices': sum(sum(any(g.weight > 0 for g in v.groups) for v in o.data.vertices) for o in meshes)}
    weighted_meshes = [o for o in meshes if any(g.weight > 0 for v in o.data.vertices for g in v.groups)]
    bound = bool(weighted_meshes) and all(any(m.type == 'ARMATURE' and m.object in rigs for m in o.modifiers) for o in weighted_meshes)
    if before != after or not bound:
        target.unlink(missing_ok=True)
        raise RuntimeError(f'FBX round-trip failed: {asset}: {before} -> {after}, bound={bound}')
    # Verify that the exported skin actually deforms under a bone pose.
    mesh = max(weighted_meshes, key=lambda o: len(o.data.vertices))
    rig = next(m.object for m in mesh.modifiers if m.type == 'ARMATURE')
    group_names = {g.index: g.name for g in mesh.vertex_groups}
    candidates = [(g.weight, group_names[g.group]) for v in mesh.data.vertices for g in v.groups
                  if group_names[g.group] in rig.pose.bones and rig.pose.bones[group_names[g.group]].parent]
    pose_test = False
    if candidates:
        bone = rig.pose.bones[max(candidates)[1]]
        deps = bpy.context.evaluated_depsgraph_get()
        baseline = [v.co.copy() for v in mesh.evaluated_get(deps).data.vertices]
        bone.location.x += 0.025
        bpy.context.view_layer.update()
        posed = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        pose_test = any((v.co - base).length > 1e-6 for v, base in zip(posed.data.vertices, baseline))
    if not pose_test:
        target.unlink(missing_ok=True)
        raise RuntimeError(f'Skin deformation check failed: {asset}')
    entry = dict(file=str(relative), **after, armature_binding=True, pose_deformation=True,
                 materials=checked_materials, materials_verified=True, embedded_textures_verified=True)
    report.append(entry)
    print('VERIFIED ' + json.dumps(entry), flush=True)
    validation_temp.cleanup()
if not report:
    raise RuntimeError('No rigged meshes found in extracted assets.')
(destination / 'rig_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
