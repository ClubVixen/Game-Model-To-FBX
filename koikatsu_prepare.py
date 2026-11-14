"""KKBP 6.6.3 / Blender 3.6 bridge; run with a graphics-enabled Blender process.

--python koikatsu_prepare.py -- job.json
External KKBP and mmd_tools are required, not redistributed here.
"""
import json
from pathlib import Path
import sys
import traceback
import bpy
import addon_utils

job = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text())
target = Path(job['target'])
target.mkdir(parents=True, exist_ok=True)
bpy.context.preferences.filepaths.temporary_directory = str(target)
if job.get('kkbp_addons'):
    sys.path.insert(0, job['kkbp_addons'])

def prepare():
    try:
        if bpy.app.version[:2] != (3, 6):
            raise RuntimeError('This KKBP bridge requires Blender 3.6; use a separate portable install.')
        addon_utils.enable('mmd_tools', default_set=True)
        addon_utils.enable('kkbp', default_set=True)
        import kkbp.common as common
        common.toggle_console = lambda: None
        # KKBP 6.6.3 uses removed Object.hide in its apply step. Replace only
        # that operator callback in this disposable process, not installed files.
        from kkbp.exporting import applymaterials
        def apply(self, context):
            folder = context.scene.kkbp.import_dir
            for obj in context.view_layer.objects:
                if obj.type != 'MESH' or not obj.visible_get():
                    continue
                bpy.ops.object.select_all(action='DESELECT')
                context.view_layer.objects.active = obj
                obj.select_set(True)
                applymaterials.create_atlas_helpers()
                applymaterials.replace_images(folder, 'A')
            return {'FINISHED'}
        applymaterials.apply_materials.execute = apply
        result = bpy.ops.kkbp.kkbpimport(filepath=job['source'])
        if 'FINISHED' not in result:
            raise RuntimeError('KKBP import did not finish')
        bpy.ops.wm.save_as_mainfile(filepath=str(target/'assembled.blend'))
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        baked = target/'baked'; baked.mkdir(exist_ok=True)
        settings = bpy.context.scene.kkbp
        settings.bake_light_bool = True
        settings.bake_dark_bool = settings.bake_norm_bool = False
        settings.bake_mult = 1
        if 'FINISHED' not in bpy.ops.kkbp.bakematerials(directory=str(baked) + '/'):
            raise RuntimeError('KKBP material baking did not finish')
        converted = 0
        for mat in bpy.data.materials:
            if not mat.use_nodes: continue
            nodes = mat.node_tree.nodes
            image = nodes.get('Image Texture')
            if not image or not image.image or 'light' not in image.image.name: continue
            image = image.image
            nodes.clear()
            output = nodes.new('ShaderNodeOutputMaterial')
            shader = nodes.new('ShaderNodeBsdfPrincipled')
            texture = nodes.new('ShaderNodeTexImage'); texture.image = image
            mat.node_tree.links.new(texture.outputs['Color'], shader.inputs['Base Color'])
            mat.node_tree.links.new(texture.outputs['Alpha'], shader.inputs['Alpha'])
            mat.node_tree.links.new(shader.outputs[0], output.inputs['Surface'])
            converted += 1
        if not converted: raise RuntimeError('No baked materials were created')
        for obj in bpy.data.objects:
            if obj.name in ('Tears', 'Gag Eyes'):
                obj.hide_render = True; obj.hide_set(True)
            for mod in obj.modifiers:
                if mod.type == 'SOLIDIFY' and 'outline' in mod.name.lower():
                    mod.show_render = mod.show_viewport = False
        used_images = {n.image for mat in bpy.data.materials if mat.use_nodes for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
        for image in used_images:
            if image.source == 'FILE' and image.has_data: image.pack()
        bpy.ops.wm.save_as_mainfile(filepath=str(target/'prepared.blend'))
        (target/'prepare-report.json').write_text(json.dumps({'status':'success', 'baked_materials':converted}))
    except Exception:
        (target/'prepare-report.json').write_text(json.dumps({'status':'failed','error':traceback.format_exc()}))
    finally:
        bpy.ops.wm.quit_blender()

# Wait until Blender has a window/GPU context before KKBP's LUT conversion.
bpy.app.timers.register(prepare, first_interval=1.0)
