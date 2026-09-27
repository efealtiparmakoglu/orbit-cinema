#!/usr/bin/env python3
# Blender icinde: blender --background --python firlatma.py -- --scene scenes/gece_firlatma.json [--gif 48]
"""orbit-cinema — uclemenin finali: pad-cinema kompleksinde rocket-cinema
roketi GERCEK yukselis simulasyonuyla havaya kalkar.

Fizik: roket_fizik.ucus_sim() — itki/kutle/gravite entegrasyonu.
z(t) interpolasyonla kareye tasiniyor; alev + yer dumanı kadehle buyur.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys

import bpy
from mathutils import Vector

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
sys.path.insert(0, os.path.join(BURASI, "..", "pad-cinema"))
sys.path.insert(0, os.path.join(BURASI, "..", "rocket-cinema"))

import geometri as g  # noqa: E402
import pad_render  # noqa: E402
import roket  # noqa: E402
import roket_fizik as rf  # noqa: E402

KX = g.KULE_YUKSEKLIK and -8.0  # padRender kule ofsetiyle ayni


def temiz():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def kamera_kur(konum, hedef, lens=40):
    cam = bpy.data.cameras.new("Cam")
    cam.lens = lens
    co = bpy.data.objects.new("kamera", cam)
    bpy.context.collection.objects.link(co)
    co.location = konum
    yon = Vector(hedef) - Vector(konum)
    co.rotation_euler = yon.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = co
    return co


def sahne_kur(cfg):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = True
        sc.cycles.device = "GPU"
    except Exception as e:
        print("  [uyari] GPU:", e)
    sc.cycles.samples = cfg["render"].get("samples", 128)
    sc.cycles.use_denoising = True
    sc.render.resolution_x = cfg["render"].get("width", 1600)
    sc.render.resolution_y = cfg["render"].get("height", 900)
    sc.view_settings.view_transform = "Filmic"
    sc.view_settings.exposure = cfg["render"].get("exposure", 0.0)
    look = cfg["render"].get("look")
    if look:
        try:
            sc.view_settings.look = look
        except Exception:
            pass

    dunya = bpy.data.worlds.new("Gokyuzu")
    sc.world = dunya
    dunya.use_nodes = True
    nt = dunya.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "HOSEK_WILKIE"
    sun_cfg = cfg["sun"]
    el = math.radians(sun_cfg["elevation_deg"])
    az = math.radians(sun_cfg["azimuth_deg"])
    sky.sun_elevation = max(el, math.radians(-8))
    sky.sun_rotation = az
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = cfg.get("sky", {}).get("strength", 0.12)
    outn = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], outn.inputs["Surface"])

    sd = bpy.data.lights.new("gunes", "SUN")
    sd.energy = sun_cfg.get("strength", 0.4)
    sd.color = tuple(sun_cfg.get("color", (0.5, 0.6, 0.9)))
    so = bpy.data.objects.new("gunes", sd)
    bpy.context.collection.objects.link(so)
    yon = Vector((math.cos(el) * math.sin(az),
                  -math.cos(el) * math.cos(az),
                  math.sin(el)))
    so.rotation_euler = yon.to_track_quat("Z", "Y").to_euler()

    for i, lc in enumerate(cfg.get("floodlights", [])):
        ld = bpy.data.lights.new(f"Flood{i}", "AREA")
        ld.energy = lc.get("guc", 8000)
        ld.size = 6.0
        lo = bpy.data.objects.new(f"Flood{i}", ld)
        bpy.context.collection.objects.link(lo)
        lo.location = lc["position"]
        lo.rotation_euler = (Vector(lc.get("hedef", (0, 0, 0))) - Vector(lo.location)
                             ).to_track_quat("-Z", "Y").to_euler()

    m = bpy.data.materials.new("Zemin")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    z = cfg.get("zemin", {})
    b.inputs["Base Color"].default_value = (*z.get("color", (0.03, 0.032, 0.028)), 1)
    b.inputs["Roughness"].default_value = z.get("roughness", 0.95)
    bpy.ops.mesh.primitive_plane_add(size=z.get("boyut", 2400))
    zo = bpy.context.active_object
    zo.name = "Zemin"
    zo.data.materials.append(m)
    return sc


def roket_fizik_ornekle():
    """ucus_sim sonucundan z(t) ve kademe(t) interp fonksiyonlari uret."""
    T, Z, V, M, K, DV = rf.ucus_sim(dt=0.05)

    def z_of(t):
        tt = max(0.0, min(T[-1], t))
        i = min(range(len(T)), key=lambda k: abs(T[k] - tt))
        return max(0.0, Z[i])
    return z_of


def duman_havuzu_kur(adet=14):
    """Yer duman bulutu: pad kanalindan yana yayilan hacimsel kureler."""
    m = bpy.data.materials.new("YerDumani")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (0.75, 0.74, 0.72, 1)
    vol.inputs["Density"].default_value = 0.32
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(vol.outputs["Volume"], outn.inputs["Volume"])
    havuz = []
    for i in range(adet):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.6, segments=14,
                                             ring_count=10, location=(0, 0, -80))
        p = bpy.context.active_object
        p.name = f"YerDuman{i}"
        bpy.ops.object.shade_smooth()
        p.data.materials.append(m)
        p.visible_shadow = False
        havuz.append({"obj": p, "mat": m, "faz": i / adet})
    return havuz


def yer_dumani_guncelle(havuz, t, kaynak=(3.0, 0, 0.4)):
    """Firlatis anindan itibaren kanaldan iki yana sizan buhar."""
    for i, h in enumerate(havuz):
        yas = max(0.0, t - h["faz"] * 0.5) * 3.2
        if t < 0.35:
            yas = 0.0
        yon = -1 if i % 2 == 0 else 1
        x = kaynak[0] + yon * (2.0 + 5.5 * yas) + 0.5 * math.sin(yas * 2 + i)
        y = kaynak[1] + (i % 5 - 2) * (1.1 + 1.9 * yas * 0.4)
        z = kaynak[2] + 0.35 * yas
        h["obj"].location = (x, y, z)
        olcek = min(4.2, 1.4 + 1.6 * yas)
        h["obj"].scale = (olcek * 1.4, olcek, olcek * 0.75)
        for dugum in h["mat"].node_tree.nodes:
            if dugum.type == "VOLUME_PRINCIPLED":
                yog = 0.55 if yas > 0.05 else 0.0
                dugum.inputs["Density"].default_value = \
                    yog * max(0.05, 1.0 - min(1.0, yas / 3.4))


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    ap.add_argument("--gif", type=int, default=0)
    ap.add_argument("--fps", type=int, default=12)
    a = ap.parse_args(args)

    cfg = json.load(open(a.scene, encoding="utf-8"))
    if os.environ.get("HIZLI") == "1":
        cfg["render"] = {**cfg.get("render", {}), "width": 800, "height": 450,
                         "samples": 32}
        cfg["output"] = "/tmp/onizleme_orbit_" + os.path.basename(a.scene).replace(".json", ".png")
        print("  [HIZLI] onizleme ->", cfg["output"])

    temiz()
    sc = sahne_kur(cfg)

    kok_hat = bpy.data.objects.new("Pad", None)
    bpy.context.collection.objects.link(kok_hat)
    pad_render.kule_kur(kok_hat)
    pad_render.pad_kur(kok_hat)

    refs = roket.kur()
    RKX = -13.5   # kule kollarinin uzandigi tarafa (kule -8'de)
    refs["kok"].location = (RKX, 0, -0.011)

    z_of = roket_fizik_ornekle()
    havuz = duman_havuzu_kur()

    cam_cfg = cfg["camera"]
    cam_obj = kamera_kur(cam_cfg["position"], cam_cfg["look_at"],
                         cam_cfg.get("lens", 35))

    if a.gif:
        cfg["render"] = {**cfg.get("render", {}), "width": 1280, "height": 720,
                         "samples": 48}
        out = os.path.splitext(cfg["output"])[0] + ".gif"
    else:
        out = cfg["output"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    t0_havada = cfg["sefer"].get("kalkis_t", 0.9)   # klepeler acilir
    donme_hizi = cfg["sefer"].get("cikis_hiz", 9.0)  # GIF sonunda ileri hiz

    def yerles(t):
        """t sn'deki durumu kur: sim z'si + alev + duman."""
        if t < t0_havada:
            z = 0.0
        else:
            z = z_of((t - t0_havada) * 1.35)  # sim'i hafif hizlandir
        refs["kok"].location.z = -0.011 + z
        itki_var = t > 0.12
        refs["isik"].data.energy = 3200 if itki_var else 0
        for ad, kat in (("AlevKoni", 1.0), ("AlevIc", 1.0)):
            o = bpy.data.objects.get(ad)
            if o:
                o.scale = (1, 1, kat if itki_var else 0.001)
        yer_dumani_guncelle(havuz, t, kaynak=(RKX + 2.0, 0, 0.4))
        return z

    if not a.gif:
        z = yerles(cfg["sefer"].get("duman_t", 2.6))
        print(f"  [durum] z={z:.1f} m")
        sc.render.filepath = out
        bpy.ops.render.render(write_still=True)
        print(f"== BİTTİ -> {out}")
        return

    tmp = out + ".frames"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    donme = cfg["sefer"].get("girisdur", 0)
    for f in range(a.gif):
        t = f / a.fps
        z = yerles(t)
        kamera_takip_z = cam_cfg["look_at"][2] + z * cam_cfg.get("takip_oran", 0.9)
        hedef = Vector((cam_cfg["look_at"][0], cam_cfg["look_at"][1],
                        cam_cfg["look_at"][2] + z * 0.75))
        yon = hedef - cam_obj.location
        cam_obj.rotation_euler = yon.to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{tmp}/f{f:05d}.png"
        bpy.ops.render.render(write_still=True)
        print(f"  kare {f + 1}/{a.gif} z={z:.1f}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps),
                    "-i", f"{tmp}/f%05d.png",
                    "-vf", "palettegen=max_colors=256:stats_mode=diff",
                    f"{tmp}/pal.png"], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps),
                    "-i", f"{tmp}/f%05d.png", "-i", f"{tmp}/pal.png",
                    "-lavfi", "paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
                    "-loop", "0", out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"== BİTTİ -> {out}")


if __name__ == "__main__":
    main()
