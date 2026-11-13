"""Bake the hair UV0 albedo/opacity and UV1 shadow color into portable UV1 RGBA."""
import json,struct,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter

def linear(a):
 return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
def srgb(a):
 return np.where(a<=.0031308,a*12.92,1.055*np.maximum(a,0)**(1/2.4)-.055)
def sample(a,uv):
 h,w=a.shape[:2];xy=(uv%1)*[w,h]-.5
 x=np.floor(xy[:,0]).astype(int);y=np.floor(xy[:,1]).astype(int);f=xy-np.stack([x,y],1)
 return (a[y%h,x%w]*(1-f[:,0,None])+a[y%h,(x+1)%w]*f[:,0,None])*(1-f[:,1,None])+(a[(y+1)%h,x%w]*(1-f[:,0,None])+a[(y+1)%h,(x+1)%w]*f[:,0,None])*f[:,1,None]
def bake_hair_layers(root,recipes):
 for side in root.rglob('*.materials.json'):
  glb=side.with_name(side.name.replace('.materials.json','.glb'))
  if not glb.exists():continue
  blob=glb.read_bytes();n=struct.unpack_from('<I',blob,12)[0];g=json.loads(blob[20:20+n]);buf=blob[28+n:]
  def accessor(i):
   a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];dt=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]);c={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
   return np.ndarray((a['count'],c),dt,buf,v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dt.itemsize*c),dt.itemsize)).copy()
  slots={s['slot']:s for s in json.loads(side.read_text())};groups={}
  for mesh in g['meshes']:
   for p in mesh['primitives']:
    name=g['materials'][p['material']]['name'];identity=slots[name].get('json');r=recipes.get(identity,{})
    if 'hair_shadow' in r.get('textures',{}):groups.setdefault(identity,[]).append(p)
  for identity,prims in groups.items():
   r=recipes[identity];base=np.asarray(Image.open(root/r['textures']['base_color']).convert('RGBA'),dtype=np.float32)/255
   shadow=np.asarray(Image.open(root/r['textures']['hair_shadow']).convert('RGB'),dtype=np.float32)/255
   # A constant white UV1 map contributes no color; do not bake degenerate UVs.
   if np.min(shadow)>.999:continue
   extras={k:np.asarray(Image.open(root/v).convert('RGBA'),dtype=np.float32)/255 for k,v in r['textures'].items() if k in ('roughness','metallic','emission')}
   extra_out={k:np.zeros((2048,2048,4),np.float32) for k in extras}
   size=2048;out=np.zeros((size,size,4),np.float32);covered=np.zeros((size,size),bool);triangles=0
   for p in prims:
    uv0=accessor(p['attributes']['TEXCOORD_0']);uv1=accessor(p['attributes']['TEXCOORD_1']);indices=accessor(p['indices']).reshape(-1,3)
    for ids in indices:
     t=uv1[ids]*size-.5;lo=np.maximum(np.ceil(t.min(0)).astype(int),0);hi=np.minimum(np.floor(t.max(0)).astype(int),size-1)
     if np.any(hi<lo):continue
     a,b,c=t;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
     if abs(den)<1e-8:continue
     yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];x=xx.ravel();y=yy.ravel()
     u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den;v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den;w=1-u-v
     mask=(u>=-1e-5)&(v>=-1e-5)&(w>=-1e-5)
     x=x[mask];y=y[mask];weights=np.stack([u[mask],v[mask],w[mask]],1)
     if not len(x):continue
     col=sample(base,weights@uv0[ids]);shade=sample(shadow,weights@uv1[ids]);col[:,:3]=srgb(linear(col[:,:3])*linear(shade));out[y,x]=col;covered[y,x]=True;triangles+=1
     for k,a in extras.items():extra_out[k][y,x]=sample(a,weights@uv0[ids])
   if not covered.any():
    r['approximations'].append('UV1 shadow layer has no rasterizable UV area; retained tinted UV0 albedo.');continue
   # Dilate RGB and alpha together into empty texels for filtered atlas borders.
   for _ in range(8):
    old=covered.copy();total=np.zeros_like(out);count=np.zeros((size,size),np.float32)
    for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
     mask=np.roll(old,(dy,dx),(0,1));
     if dy: mask[0 if dy==1 else -1,:]=False
     if dx: mask[:,0 if dx==1 else -1]=False
     total+=np.roll(out,(dy,dx),(0,1))*mask[:,:,None];count+=mask
    fill=(~old)&(count>0);out[fill]=total[fill]/count[fill,None];covered|=fill
   name=glb.stem+'_'+hashlib.sha256(identity.encode()).hexdigest()[:8]+'_hair_color.png';dest=root/'FBX_Textures'/name
   Image.fromarray(np.uint8(np.clip(out*255+.5,0,255))).save(dest)
   extra_files={}
   for k,a in extra_out.items():
    path=dest.with_name(dest.stem+'_'+k+'.png');Image.fromarray(np.uint8(np.clip(a*255+.5,0,255))).save(path);extra_files[k]=str(path.relative_to(root))
   r.setdefault('mesh_base_color',{})[str(glb.relative_to(root))]={'texture':str(dest.relative_to(root)),'uv_index':1,'triangles':triangles,'extra_textures':extra_files}
   r['approximations'].append('UV0 albedo/opacity × inherited BaseTint × UV1 ShadowColor baked in linear light. Portable hair shading approximates the Unreal lighting model.')
