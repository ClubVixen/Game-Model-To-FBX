"""Resolve exported Unreal material references and make FBX-compatible texture maps.

Every image is selected through material parameters, never nearest-name guessing.
Unreal runtime lighting/FX graphs are intentionally represented as portable PBR.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

def package_path(reference):
    path = reference.split('.')[0]
    if path.startswith('/Game/'):
        return 'Marvel/Content/' + path[6:]
    if path.startswith('/Engine/'):
        return 'Engine/Content/' + path[8:]
    return path.lstrip('/')

def prepare_materials(extracted, mod_packages):
    extracted = Path(extracted)
    generated = extracted/'FBX_Textures'
    generated.mkdir(exist_ok=True)
    mod_packages = {p.casefold().removesuffix('.uasset') for p in mod_packages}
    recipes = {}
    missing = []
    def image_path(ref):
        path = extracted/(package_path(ref) + '.png')
        if not path.is_file():
            missing.append({'texture': ref, 'expected': str(path)})
            return None
        return path

    for sidecar in extracted.rglob('*.materials.json'):
        for slot in json.loads(sidecar.read_text(encoding='utf-8')):
            identity = slot.get('json')
            if not identity or identity in recipes:
                continue
            material_file = extracted/identity
            if not material_file.is_file():
                missing.append({'material': slot.get('material'), 'expected': str(material_file)})
                continue
            data = json.loads(material_file.read_text(encoding='utf-8'))
            params = data.get('Parameters', {})
            textures = data.get('Textures', {})
            scalars, colors = params.get('Scalars', {}), params.get('Colors', {})
            blend = params.get('BlendMode', 0)
            recipe = {'name': material_file.stem, 'source': slot['material'], 'textures': {},
                      'references': {}, 'approximations': [], 'blend_mode': blend,
                      'base_color': [0.8, 0.8, 0.8, 1], 'roughness': 0.5, 'metallic': 0.0,
                      'alpha': 1.0, 'emission_strength': 0.0}
            recipes[identity] = recipe
            prefix = material_file.stem + '_' + hashlib.sha256(identity.encode()).hexdigest()[:8]
            def choose(*keys):
                for key in keys:
                    if key in textures:
                        return key, textures[key]
                return None, None
            def load(channel, *keys):
                key, ref = choose(*keys)
                if not ref:
                    return None
                path = image_path(ref)
                recipe['references'][channel] = {'parameter': key, 'asset': ref,
                    'origin': 'mod' if package_path(ref).casefold() in mod_packages else 'installed_game'}
                if not path:
                    return None
                return Image.open(path).convert('RGBA')
            def save(channel, img):
                target = generated/(prefix + '_' + channel + '.png')
                img.save(target)
                recipe['textures'][channel] = str(target.relative_to(extracted))
            def color(name, default):
                c = colors.get(name)
                return [float(c.get(x, default[i])) for i,x in enumerate('RGBA')] if c else default

            diffuse = load('base_color', 'BaseColor', 'Base Color', 'Diffuse', 'DiffuseTexture')
            tint_key = next((k for k in ('BaseTint','BaseColorTint') if k in colors), None)
            recipe['tint'] = {'parameter': tint_key, 'linear_rgba': color(tint_key,[1,1,1,1])}
            recipe['unreal_parameters'] = params
            shadow = load('hair_shadow', 'ShadowColor(UV1)')
            if shadow is not None:
                save('hair_shadow', shadow)
            # Iris/sclera are separate textures sampled by Unreal's eye shader.
            if diffuse is None and 'IrisBaseColor' in textures:
                iris = load('iris', 'IrisBaseColor')
                sclera = load('sclera', 'ScleraBaseColor')
                if iris is not None:
                    size = max(1024, min(2048, iris.width))
                    base = sclera.resize((size,size), Image.Resampling.BILINEAR) if sclera else Image.new('RGBA',(size,size),'white')
                    radius = max(0.03, min(0.49, scalars.get('IrisUVRadius', 0.15)))
                    diameter = max(2, round(size*radius*2))
                    patch = iris.resize((diameter,diameter), Image.Resampling.LANCZOS)
                    y,x=np.ogrid[:diameter,:diameter]
                    dist=np.sqrt(((x+.5)/diameter-.5)**2+((y+.5)/diameter-.5)**2)*2
                    mask=Image.fromarray(np.uint8(np.clip((1-dist)*40,0,1)*255))
                    base.paste(patch,((size-diameter)//2,(size-diameter)//2),mask)
                    diffuse=base
                    recipe['approximations'].append('Baked iris/sclera composite; eye refraction and parallax are approximated.')
                    recipe['roughness']=0.18
            if diffuse is None and 'BaseColor' not in colors:
                # CUE4Parse's PM fallback may be an unrelated texture inherited
                # from an inactive VFX branch. Accept only character surfaces.
                ref=textures.get('PM_Diffuse','')
                if '/Characters/' in ref and '/Common/Textures/T_Common_' not in ref:
                    diffuse=load('base_color','PM_Diffuse')
            if diffuse is None:
                recipe['base_color']=color('BaseColor',color('BaseColorTint',[0.8,0.8,0.8,1]))
                recipe['approximations'].append('Solid-color/FX material represented by its base color and opacity.')
            effect_only = diffuse is None and not any(k in colors for k in ('BaseColor','BaseColorTint')) and blend in (2,3,4,5,6,7)
            opacity = load('opacity','OpacityMask') if blend in (1,2,4,5,6,7) else None
            if blend in (2,4,5,6,7):
                recipe['alpha']=max(0.0,min(1.0,scalars.get('Opacity',1.0)))
                recipe['approximations'].append('Unreal translucent/additive shader approximated with alpha blending.')
            if effect_only:
                recipe['alpha']=0.0
                recipe['approximations'].append('Runtime-only effect overlay has no base surface; represented as transparent in the static export.')
            if diffuse is not None:
                if tint_key:
                    rgba = np.array(diffuse)
                    rgb = rgba[:,:,:3].astype(np.float32)/255
                    linear = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
                    linear *= np.array(recipe['tint']['linear_rgba'][:3])
                    rgb = np.where(linear <= .0031308, linear*12.92, 1.055*np.maximum(linear,0)**(1/2.4)-.055)
                    rgba[:,:,:3] = np.uint8(np.clip(rgb*255+.5,0,255))
                    diffuse = Image.fromarray(rgba)
                # Unreal commonly stores masks in R; bake them into diffuse alpha
                # so FBX consumers do not need arbitrary Blender node graphs.
                if opacity is not None:
                    alpha=opacity.getchannel('R').resize(diffuse.size,Image.Resampling.BILINEAR)
                    diffuse.putalpha(alpha)
                else:
                    diffuse.putalpha(255)
                if recipe['alpha'] < 1:
                    alpha=np.asarray(diffuse.getchannel('A'),dtype=np.float32)*recipe['alpha']
                    diffuse.putalpha(Image.fromarray(np.uint8(alpha)))
                save('base_color',diffuse)
            elif opacity is not None:
                # Constant albedo with an opacity mask still needs an RGBA map.
                rgb=[round(255*(max(0,min(1,v))**(1/2.2))) for v in recipe['base_color'][:3]]
                diffuse=Image.new('RGBA',opacity.size,tuple(rgb)+(255,))
                diffuse.putalpha(opacity.getchannel('R'))
                save('base_color',diffuse)

            normal=None if effect_only else load('normal','Normal','NormalMap','Normals','PM_Normals')
            if normal is not None:
                a=np.array(normal)
                a[:,:,1]=255-a[:,:,1]  # Unreal DirectX -> Blender/OpenGL tangents
                save('normal',Image.fromarray(a[:,:,:3]))
            orm=load('orm','ORM','OcclusionRoughnessMetallic','OcclusionRoughnessMetallicTexture')
            if 'ShadowColor(UV1)' in textures and 'T_Common_LinearBlack' in recipe.get('references',{}).get('orm',{}).get('asset',''):
                orm=None
                recipe['roughness']=max(.05,min(1,scalars.get('RoughnessPower',.5)))
                recipe['approximations'].append('Inactive black ORM placeholder excluded from stylized hair; RoughnessPower used as portable roughness.')
            if orm is not None:
                save('occlusion',orm.getchannel('R'))
                save('roughness',orm.getchannel('G'))
                save('metallic',orm.getchannel('B'))
            recipe['roughness']=max(0,min(1,scalars.get('Roughness',recipe['roughness'])))
            recipe['metallic']=max(0,min(1,scalars.get('Metallic',recipe['metallic'])))
            emission=load('emission','Emissive','EmissiveTexture','EmissiveColorTexture')
            if emission is not None:
                strength=scalars.get('EmissiveStrength',scalars.get('EmissiveIntensity',0.0))
                if strength > 0:
                    save('emission',emission)
                    recipe['emission_strength']=strength
            recipe['resolved']=True
    from hair_bake import bake_hair_layers
    bake_hair_layers(extracted, recipes)
    report={'materials':recipes,'missing':missing,
            'note':'Portable PBR conversion; Unreal runtime FX, refraction, anisotropy and layered shader behavior are approximated.'}
    (extracted/'material_recipes.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if missing:
        raise RuntimeError(f'{len(missing)} material/texture references could not be resolved; see material_recipes.json')
    return report
