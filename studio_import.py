"""Import Studio FBX Bridge manifests in Blender, without a KKBP dependency."""
import json
from pathlib import Path


def read_manifest(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if data.get('format') != 'clubvixen.studio-character.v1':
        raise ValueError('Not a Studio FBX Bridge v1 manifest')
    bones = data.get('bones', [])
    if not bones or not data.get('meshes'):
        raise ValueError('Studio export has no rig or meshes')
    for i, bone in enumerate(bones):
        if bone['parent'] < -1 or bone['parent'] >= i:
            raise ValueError('Studio bone hierarchy must be parent-first and acyclic')
    for mesh in data['meshes']:
        count = len(mesh['vertices'])
        if len(mesh['skin']) != count:
            raise ValueError('Studio skin/vertex count mismatch')
        for influence in mesh['skin']:
            if len(influence['bones']) != len(influence['weights']) or not influence['bones']:
                raise ValueError('Invalid Studio skin weights')
            if any(b < 0 or b >= len(bones) for b in influence['bones']):
                raise ValueError('Studio skin references missing bone')
        for part in mesh['parts']:
            if len(part['indices']) % 3 or any(i < 0 or i >= count for i in part['indices']):
                raise ValueError('Invalid Studio triangle index')
            if not 0 <= part['material'] < len(data['materials']):
                raise ValueError('Studio mesh references missing material')
    for material in data['materials']:
        for texture in material['textures']:
            resolved = (path.parent / texture['file']).resolve()
            if not resolved.is_relative_to(path.parent) or not resolved.is_file():
                raise ValueError('Studio texture missing or outside export folder: ' + texture['file'])
    return data


def import_studio(path):
    import bpy
    from mathutils import Vector
    path = Path(path).resolve()
    data = read_manifest(path)
    def vec(v): return Vector((v['x'], -v['z'], v['y']))
    arm = bpy.data.armatures.new('StudioRig')
    rig = bpy.data.objects.new(data['character'] + '_Rig', arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    names = []
    for i, entry in enumerate(data['bones']):
        bone = arm.edit_bones.new(entry['name'])
        names.append(bone.name)
        bone.head = vec(entry['position'])
        direction = vec(entry['up']).normalized()
        if direction.length < .5: direction = Vector((0,0,1))
        bone.tail = bone.head + direction * .025
        bone.align_roll(vec(entry['forward']))
        if entry['parent'] >= 0: bone.parent = arm.edit_bones[names[entry['parent']]]
    bpy.ops.object.mode_set(mode='OBJECT')
    surfaces = []
    for entry in data['materials']:
        mat = bpy.data.materials.new(entry['name']); mat.use_nodes = True
        shader = mat.node_tree.nodes.get('Principled BSDF')
        color = entry['color']
        shader.inputs['Base Color'].default_value = tuple(color[k] for k in ('r','g','b','a'))
        shader.inputs['Roughness'].default_value = .65
        for slot in entry['textures']:
            node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            node.label = slot['property']; node.name = slot['property']
            node.image = bpy.data.images.load(str(path.parent/slot['file']), check_existing=True)
            if slot['property'] == '_MainTex':
                # The game often generates a fully colored main texture. Other shader
                # masks remain available as editable, unconnected image nodes.
                mat.node_tree.links.new(node.outputs['Color'], shader.inputs['Base Color'])
                mat.node_tree.links.new(node.outputs['Alpha'], shader.inputs['Alpha'])
                uv = mat.node_tree.nodes.new('ShaderNodeTexCoord')
                mapping = mat.node_tree.nodes.new('ShaderNodeMapping')
                mapping.inputs['Scale'].default_value = (slot['scale']['x'],slot['scale']['y'],1)
                mapping.inputs['Location'].default_value = (slot['offset']['x'],slot['offset']['y'],0)
                mat.node_tree.links.new(uv.outputs['UV'],mapping.inputs['Vector'])
                mat.node_tree.links.new(mapping.outputs['Vector'],node.inputs['Vector'])
        mat['studio_shader'] = entry['shader']
        surfaces.append(mat)
    for entry in data['meshes']:
        # Unity shadow and view-dependent nose-line helpers have no PBR surface.
        if all(data['materials'][part['material']]['shader'].lower().rsplit('/', 1)[-1]
               in {'shadowcast', 'toon_nose_lod0'} for part in entry['parts']):
            continue
        faces, indices = [], []
        for part in entry['parts']:
            flat = part['indices']
            faces.extend(tuple(flat[i:i+3][::-1]) for i in range(0,len(flat),3))
            indices.extend([part['material']] * (len(flat)//3))
        mesh = bpy.data.meshes.new(entry['name'])
        mesh.from_pydata([vec(v) for v in entry['vertices']], [], faces); mesh.update()
        obj = bpy.data.objects.new(entry['name'],mesh); bpy.context.collection.objects.link(obj)
        used = sorted(set(indices))
        local_material = {index: slot for slot, index in enumerate(used)}
        for index in used: mesh.materials.append(surfaces[index])
        for face, material in zip(mesh.polygons,indices): face.material_index = local_material[material]; face.use_smooth = True
        for key in ('uv','uv2'):
            coords=entry.get(key,[])
            if len(coords) == len(mesh.vertices):
                layer=mesh.uv_layers.new(name=key)
                for loop in mesh.loops:
                    uv=coords[loop.vertex_index]; layer.data[loop.index].uv=(uv['x'],uv['y'])
        groups={}
        for index, influence in enumerate(entry['skin']):
            combined={}
            for bone, weight in zip(influence['bones'],influence['weights']):
                combined[bone]=combined.get(bone,0)+weight
            total=sum(combined.values())
            if total <= 0: raise ValueError('Studio vertex has zero weight')
            for bone,weight in combined.items():
                if bone not in groups: groups[bone]=obj.vertex_groups.new(name=names[bone])
                groups[bone].add([index],weight/total,'REPLACE')
        mod=obj.modifiers.new('Studio Skin','ARMATURE'); mod.object=rig
        obj.parent=rig
    rig['studio_pose']=data['pose']
    return data
