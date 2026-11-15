using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using BepInEx;
using KKAPI.Studio;
using UnityEngine;

// Independent Studio-only exporter. Does not replace or patch KKBP's Maker exporter.
[BepInPlugin("clubvixen.studiofbxbridge", "Studio FBX Bridge", "1.0.0")]
[BepInDependency("marco.kkapi", BepInDependency.DependencyFlags.HardDependency)]
[BepInProcess("CharaStudio")]
public class StudioFbxBridge : BaseUnityPlugin
{
    Rect window = new Rect(20, 220, 410, 190);
    string status = "Select one character in Workspace. Use a neutral pose for retargeting.";
    bool visible = true;
    void Update() { if (Input.GetKeyDown(KeyCode.F8)) visible = !visible; }
    void OnGUI()
    {
        if (visible && StudioAPI.InsideStudio)
            window = GUI.Window(174039, window, Draw, "Studio FBX Bridge (F8 to hide)");
    }
    void Draw(int id)
    {
        GUILayout.Label("Current pose becomes the exported rig's rest pose.");
        GUILayout.Label("Visible outfit/accessories only. Scene is not modified.");
        if (GUILayout.Button("Export selected character + textures"))
        {
            try
            {
                var selected = StudioAPI.GetSelectedCharacters().ToArray();
                if (selected.Length != 1) throw new Exception("Select exactly one character in Workspace.");
                status = Export(selected[0].charInfo);
                Logger.LogInfo(status);
            }
            catch (Exception ex) { status = "Export failed: " + ex.Message; Logger.LogError(ex); }
        }
        GUILayout.Label(status);
        GUI.DragWindow();
    }

    [Serializable] public class Document
    {
        public string format = "clubvixen.studio-character.v1";
        public string character;
        public string pose = "current-pose-as-rest";
        public List<Bone> bones = new List<Bone>();
        public List<Geometry> meshes = new List<Geometry>();
        public List<Surface> materials = new List<Surface>();
        public List<string> skipped = new List<string>();
        public string warning = "PBR approximation, not Unity shader parity. Physics simulation and facial morph animation are not transferred.";
    }
    [Serializable] public class Bone { public string name; public int parent; public Vector3 position; public Vector3 up; public Vector3 forward; }
    [Serializable] public class FaceSet { public int material; public int[] indices; }
    [Serializable] public class Influence { public int[] bones; public float[] weights; }
    [Serializable] public class Geometry
    {
        public string name;
        public Vector3[] vertices;
        public Vector2[] uv;
        public Vector2[] uv2;
        public Influence[] skin;
        public List<FaceSet> parts = new List<FaceSet>();
    }
    [Serializable] public class TextureSlot
    {
        public string property; public string file; public Vector2 scale; public Vector2 offset;
    }
    [Serializable] public class Surface
    {
        public string name; public string shader; public Color color;
        public List<TextureSlot> textures = new List<TextureSlot>();
    }

    string Export(ChaControl character)
    {
        var root = character.transform;
        var doc = new Document { character = character.chaFile.parameter.fullname };
        string safe = new string(doc.character.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c).ToArray());
        string folder = Path.GetFullPath(Path.Combine(Application.dataPath, "../Export_StudioFBX/" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + "_" + safe));
        Directory.CreateDirectory(Path.Combine(folder, "textures"));
        var boneIds = new Dictionary<Transform, int>();
        var materialIds = new Dictionary<Material, int>();
        var textureFiles = new Dictionary<Texture, string>();
        foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
        {
            if (!renderer.enabled || !renderer.gameObject.activeInHierarchy)
            { doc.skipped.Add(renderer.name + ": hidden"); continue; }
            var skinned = renderer as SkinnedMeshRenderer;
            var filter = renderer.GetComponent<MeshFilter>();
            Mesh original = skinned != null ? skinned.sharedMesh : (filter != null ? filter.sharedMesh : null);
            if (original == null) { doc.skipped.Add(renderer.name + ": not a mesh"); continue; }
            Mesh baked = null;
            try
            {
                Mesh mesh = original;
                if (skinned != null) { baked = new Mesh(); skinned.BakeMesh(baked); mesh = baked; }
                var geometry = new Geometry { name = renderer.name, uv = original.uv, uv2 = original.uv2 };
                // Unity 5 BakeMesh includes renderer scale; applying it again explodes scaled accessories.
                Matrix4x4 toWorld = skinned != null
                    ? Matrix4x4.TRS(renderer.transform.position, renderer.transform.rotation, Vector3.one)
                    : renderer.transform.localToWorldMatrix;
                geometry.vertices = mesh.vertices.Select(v => root.InverseTransformPoint(toWorld.MultiplyPoint3x4(v))).ToArray();
                var weights = original.boneWeights;
                var rig = skinned != null ? skinned.bones : new Transform[0];
                geometry.skin = new Influence[geometry.vertices.Length];
                int rigidBone = AddBone(renderer.transform, root, boneIds, doc);
                for (int i = 0; i < geometry.skin.Length; i++)
                {
                    var ids = new List<int>(); var values = new List<float>();
                    if (skinned != null && weights.Length == geometry.skin.Length)
                    {
                        BoneWeight w = weights[i];
                        int[] local = { w.boneIndex0, w.boneIndex1, w.boneIndex2, w.boneIndex3 };
                        float[] amounts = { w.weight0, w.weight1, w.weight2, w.weight3 };
                        for (int j = 0; j < 4; j++)
                            if (amounts[j] > 0)
                            {
                                if (local[j] < 0 || local[j] >= rig.Length || rig[local[j]] == null)
                                    throw new Exception(renderer.name + ": missing weighted bone");
                                ids.Add(AddBone(rig[local[j]], root, boneIds, doc)); values.Add(amounts[j]);
                            }
                    }
                    if (ids.Count == 0) { ids.Add(rigidBone); values.Add(1); }
                    geometry.skin[i] = new Influence { bones = ids.ToArray(), weights = values.ToArray() };
                }
                var materials = renderer.sharedMaterials;
                for (int sub = 0; sub < original.subMeshCount; sub++)
                {
                    if (sub >= materials.Length || materials[sub] == null) throw new Exception(renderer.name + ": missing material");
                    Material material = materials[sub]; int materialId;
                    if (!materialIds.TryGetValue(material, out materialId))
                    {
                        materialId = doc.materials.Count; materialIds.Add(material, materialId);
                        doc.materials.Add(ExportMaterial(material, folder, textureFiles));
                    }
                    geometry.parts.Add(new FaceSet { material = materialId, indices = original.GetTriangles(sub) });
                }
                doc.meshes.Add(geometry);
            }
            finally { if (baked != null) Destroy(baked); }
        }
        if (doc.meshes.Count == 0) throw new Exception("No visible meshes found.");
        // Write the manifest last: a partial texture dump is never a completed export.
        using (var writer = new StreamWriter(Path.Combine(folder, "character.studio.json"))) WriteJson(writer, doc);
        return "Exported " + doc.meshes.Count + " meshes, " + textureFiles.Count + " textures to " + folder;
    }
    int AddBone(Transform bone, Transform root, Dictionary<Transform,int> ids, Document doc)
    {
        int id; if (ids.TryGetValue(bone, out id)) return id;
        int parent = bone == root || bone.parent == null ? -1 : AddBone(bone.parent, root, ids, doc);
        id = doc.bones.Count; ids.Add(bone,id);
        doc.bones.Add(new Bone { name = bone.name, parent = parent,
            position = root.InverseTransformPoint(bone.position),
            up = root.InverseTransformDirection(bone.up), forward = root.InverseTransformDirection(bone.forward) });
        return id;
    }
    Surface ExportMaterial(Material material, string folder, Dictionary<Texture,string> files)
    {
        var result = new Surface { name = material.name, shader = material.shader.name,
            color = material.HasProperty("_Color") ? material.GetColor("_Color") : Color.white };
        var properties = new HashSet<string>(new [] { "_MainTex", "_ColorMask", "_DetailMainTex", "_NormalMap", "_BumpMap", "_AlphaMask", "_overtex1", "_overtex2", "_overtex3", "_tex1", "_tex2", "_tex3" });
        var method = typeof(Material).GetMethod("GetTexturePropertyNames", Type.EmptyTypes);
        if (method != null) foreach (var p in (string[])method.Invoke(material, null)) properties.Add(p);
        foreach (string property in properties.OrderBy(p => p))
        {
            if (!material.HasProperty(property)) continue;
            Texture texture = material.GetTexture(property);
            if (texture == null || texture.dimension != UnityEngine.Rendering.TextureDimension.Tex2D) continue;
            string file;
            if (!files.TryGetValue(texture, out file))
            {
                file = "textures/" + files.Count.ToString("D4") + ".png";
                SaveTexture(texture, Path.Combine(folder, file)); files.Add(texture, file);
            }
            result.textures.Add(new TextureSlot { property = property, file = file,
                scale = material.GetTextureScale(property), offset = material.GetTextureOffset(property) });
        }
        return result;
    }
    void SaveTexture(Texture texture, string file)
    {
        var previous = RenderTexture.active;
        var buffer = RenderTexture.GetTemporary(texture.width, texture.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear);
        Texture2D copy = null;
        try
        {
            Graphics.Blit(texture, buffer); RenderTexture.active = buffer;
            copy = new Texture2D(texture.width, texture.height, TextureFormat.RGBA32, false, true);
            copy.ReadPixels(new Rect(0,0,texture.width,texture.height),0,0); copy.Apply();
            File.WriteAllBytes(file, copy.EncodeToPNG());
        }
        finally { RenderTexture.active = previous; RenderTexture.ReleaseTemporary(buffer); if(copy != null) Destroy(copy); }
    }

    // Unity 5 JsonUtility can omit plugin-defined nested types. Serialize fields
    // explicitly; never inspect Unity properties (Vector3.normalized recurses).
    static void WriteJson(TextWriter writer, object value)
    {
        if (value == null) { writer.Write("null"); return; }
        if (value is string)
        {
            writer.Write('"');
            foreach (char c in (string)value)
            {
                if (c == '"' || c == '\\') { writer.Write('\\'); writer.Write(c); }
                else if (c < 32) writer.Write("\\u" + ((int)c).ToString("x4"));
                else writer.Write(c);
            }
            writer.Write('"'); return;
        }
        if (value is bool) { writer.Write((bool)value ? "true" : "false"); return; }
        if (value.GetType().IsPrimitive)
        {
            double number = Convert.ToDouble(value);
            if (double.IsNaN(number) || double.IsInfinity(number)) throw new Exception("Non-finite geometry value");
            writer.Write(Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture)); return;
        }
        var sequence = value as System.Collections.IEnumerable;
        bool first = true;
        if (sequence != null)
        {
            writer.Write('[');
            foreach (object item in sequence) { if (!first) writer.Write(','); first = false; WriteJson(writer,item); }
            writer.Write(']'); return;
        }
        writer.Write('{');
        foreach (var field in value.GetType().GetFields(System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public))
        {
            if (!first) writer.Write(','); first = false;
            WriteJson(writer,field.Name); writer.Write(':'); WriteJson(writer,field.GetValue(value));
        }
        writer.Write('}');
    }
}
