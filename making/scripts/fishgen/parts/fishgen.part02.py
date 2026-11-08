        # 縦のひれの付け根の近く（体から体長の 1.5% まで）は不透明に。付け根の膜が薄くて背景が透ける所（ブリの後ろの背びれ、
        # メバルの背びれ）は、体とひれの間に穴や縦の切れ目が開いて見えた
        # （骨の間の膜が抜けた切れ目は、_fins でひれの形に入れてある）
        d = self.base_fill
        base = np.zeros(self.fish.shape, bool)
        for c in self.median:
            base |= c & dilate(self.body, d)
        base_w = box_blur(base.astype(np.float32), max(1, d // 4))
        alpha = np.maximum(alpha, base_w * 0.95)
        solid = np.maximum(solid, base_w)
        if self.pect is not None:
            # 体の上は不透明に近く、体の外へ出た所（マゴチの大きな胸びれなど）は縦のひれと同じく写真の透け具合
            # 体の上かどうかは、体の写真の色ではなく体の輪郭の上下で（体の暗い斑点を背景と見て、ひれに穴が開くので）
            yy, xx = np.mgrid[0:self.H, 0:self.W]
            xc = np.clip(xx, self.XF, self.XB)
            in_outline = (yy >= self.TOP(xc)) & (yy <= self.BOT(xc)) & (xx >= self.XF) & (xx <= self.XB)
            on_body = self.pect & in_outline
            alpha = np.maximum(alpha, box_blur(on_body.astype(np.float32), 2) * 0.92)
            alpha = np.maximum(alpha, box_blur((self.pect & ~in_outline).astype(np.float32), 1) * a_bg)
            self._pect_on_body = on_body
        bgl = to_lin(self.bg)
        col = (src - bgl * (1 - a_bg[..., None])) / np.maximum(a_bg[..., None], 0.05)
        # 不透明にした所と埋めた穴は、背景を引かずに写真の色のまま（暗い斑点で背景を引くと、色が明るく跳ね上がる）
        solid = np.maximum(solid, box_blur(holes.astype(np.float32), 1))
        col = col * (1 - solid[..., None]) + src * solid[..., None]
        if self.pect is not None:
            pm = box_blur(self._pect_on_body.astype(np.float32), 2)[..., None]
            col = col * (1 - pm) + src * pm            # over the body the photo needs no un-premultiply
        self.plate = np.concatenate([np.clip(col, 0, 1), alpha[..., None]], -1).astype(np.float32)


# ---------------- geometry ----------------

def set_attr(me, name, values):
    at = me.attributes.get(name) or me.attributes.new(name, "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", np.ascontiguousarray(values, np.float32).ravel())


def mesh_from(name, verts, faces, uvs):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    uvl = me.uv_layers.new(name="UVMap")
    flat = np.array([c for f in uvs for c in f], np.float32)
    uvl.data.foreach_set("uv", flat.ravel())
    for p in me.polygons:
        p.use_smooth = True
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def body_v(vm):
    return BODY_V0 + (1.0 - BODY_V0) * vm


def build_body(F, n_st=None, n_ring=None):
    n_st = n_st or LOD_PARAMS[0]
    n_ring = n_ring or LOD_PARAMS[1]
    u = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n_st))          # denser at both ends
    xs = F.XF + 0.5 + (F.XB - F.XF - 1.0) * u
    ts = 2 * np.pi * np.arange(n_ring) / n_ring
    XX, TT = np.meshgrid(xs, ts, indexing="ij")
    yp, side = F.section(XX, TT)
    X, Z = F.to_m(XX, yp)
    verts = np.stack([X, side * F.S, Z], -1).reshape(-1, 3)
    yf = (F.TOP(xs[0]) + F.BOT(xs[0])) / 2
    yb = (F.TOP(xs[-1]) + F.BOT(xs[-1])) / 2
    Xf, Zf = F.to_m(xs[0] - 1.0, yf)
    Xb, Zb = F.to_m(xs[-1] + 1.0, yb)
    verts = np.vstack([verts, [[Xf, 0, Zf], [Xb, 0, Zb]]])
    i_f, i_b = len(verts) - 2, len(verts) - 1
    uo = (xs - F.XF) / (F.XB - F.XF)
    faces, uvs = [], []
    vm = lambda k: 2.0 * min(k / n_ring, 1 - k / n_ring)
    for i in range(n_st - 1):
        for k in range(n_ring):
            k2 = (k + 1) % n_ring
            a, b = i * n_ring + k, i * n_ring + k2
            faces.append((a, b, (i + 1) * n_ring + k2, (i + 1) * n_ring + k))
            v0, v1 = body_v(vm(k)), body_v(vm(k + 1))
            uvs.append(((uo[i], v0), (uo[i], v1), (uo[i + 1], v1), (uo[i + 1], v0)))
    o = (n_st - 1) * n_ring
    for k in range(n_ring):
        k2 = (k + 1) % n_ring
        v0, v1, vc = body_v(vm(k)), body_v(vm(k + 1)), body_v(0.5)
        faces.append((i_f, k2, k)); uvs.append(((0, vc), (uo[0], v1), (uo[0], v0)))
        faces.append((i_b, o + k, o + k2)); uvs.append(((1, vc), (uo[-1], v0), (uo[-1], v1)))
    ob = mesh_from(F.sid + "_body", verts, faces, uvs)
    n = len(verts)
    set_attr(ob.data, "_FIN", np.zeros((n, 3)))
    set_attr(ob.data, "_PIV", np.zeros((n, 3)))
    return ob


def body_uv_of(F, xp, yp):
    u = (xp - F.XF) / (F.XB - F.XF)
    top, bot = F.TOP(xp), F.BOT(xp)
    t = np.arccos(np.clip(2 * (yp - bot) / (top - bot) - 1, -1, 1))
    return u, body_v(t / np.pi)


def build_eyes(F):
    out = []
    for (ex, ey, r) in F.eyes:
        X, Z = F.to_m(ex, ey)
        R = r * F.S
        ys = float(F.surface_y(ex, ey))
        bm = bmesh.new()
        for side in (1, -1):
            g = bmesh.ops.create_uvsphere(bm, u_segments=LOD_PARAMS[3], v_segments=LOD_PARAMS[4], radius=1.0)
            for v in g["verts"]:
                lx, ly, lz = v.co
                v.co = (X + lx * R, side * (ys - 0.25 * R + ly * R * 0.5), Z + lz * R)
        me = bpy.data.meshes.new(F.sid + "_eye"); bm.to_mesh(me); bm.free()
        co = np.array([v.co[:] for v in me.vertices])
        xp = ex - (co[:, 0] - X) / F.S * 0.9
        yp = ey - (co[:, 2] - Z) / F.S * 0.9
        u, v = body_uv_of(F, xp, yp)
        loops = np.zeros(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", loops)
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.stack([u[loops], v[loops]], -1).ravel())
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(F.sid + "_eye", me)
        bpy.context.scene.collection.objects.link(ob)
        n = len(co)
        set_attr(me, "_FIN", np.tile([6, 1, 0], (n, 1)))
        set_attr(me, "_PIV", np.zeros((n, 3)))
        out.append(ob)
    return out


def sheet(F, mask, name, cell, place, rows=2):
    """Grid over the mask's bbox, cells without fin pixels removed. place(xp, yp) -> (X, Y, Z) metres.
    rows: the fewest rows (a long low fin needs several, or it cannot fold ray by ray)"""
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min() - 2, xs.max() + 2, ys.min() - 2, ys.max() + 2
    nx = int(np.clip(round((x1 - x0) / cell), 2, 40)); ny = int(np.clip(round((y1 - y0) / cell), rows, 24))
    gx = np.linspace(x0, x1, nx + 1); gy = np.linspace(y0, y1, ny + 1)
    cov = dilate(mask, 3)
    keep = np.zeros((ny, nx), bool)
    for j in range(ny):
        for i in range(nx):
            keep[j, i] = cov[int(gy[j]):int(gy[j + 1]) + 1, int(gx[i]):int(gx[i + 1]) + 1].any()
    used = {}
    verts, faces, pix = [], [], []

    def vid(i, j):
        if (i, j) not in used:
            used[(i, j)] = len(verts)
            verts.append(place(gx[i], gy[j])); pix.append((gx[i], gy[j]))
        return used[(i, j)]
    for j in range(ny):
        for i in range(nx):
            if keep[j, i]:
                faces.append((vid(i, j), vid(i, j + 1), vid(i + 1, j + 1), vid(i + 1, j)))
    return np.array(verts), faces, np.array(pix), (x0, y0, x1, y1)


def build_fins(F):
    """Returns list of (object, rect_px, kind) ; UVs filled in later by the packer."""
    parts = []
    cell = max(F.XB - F.XF, 1) / LOD_PARAMS[2]
    for k, m in enumerate(F.median):
        verts, faces, pix, rect = sheet(F, m, f"{F.sid}_fin{k}", cell,
                                        lambda x, y: (*F.to_m(x, y)[:1], 0.0, F.to_m(x, y)[1]),
                                        F.cfg.get("fin_rows", 2) if not LOD else 2)
        parts.append(dict(verts=verts, faces=faces, pix=pix, rect=rect, part=1, kind="median%d" % k, mask=m))
    if F.pect is not None:
        ys, xs = np.nonzero(F.pect)
        xa = xs.min(); xlen = max(xs.max() - xa, 1)
        x_base, y_base = xa, ys[xs < xa + 0.12 * xlen].mean()
        if F.pect_base:
            # Codex に聞いた付け根の線（いちばん前の所は、お腹の下へ張り出した先のこともある。マゴチ）
            x_base, y_base = np.mean(F.pect_base, 0)
        # 付け根の体の幅より内へは寄せない（体の表面に沿わせると、お腹の下へ出た所が体の真ん中へ巻き込む。マゴチの大きな胸びれ）
        # 胸びれの板を置く所だけを上へずらす（pect_up：体長に対する割合。絵は写真の同じ所から切り抜く）
        up = F.cfg.get("pect_up", 0.0) * (F.tail_px - F.snout_px)
        y_base = y_base - up
        w_base = float(F.surface_y(np.clip(x_base, F.XF, F.XB), y_base))
        for side in (1, -1):
            def place(x, y, side=side):
                y = y - up
                X, Z = F.to_m(x, y)
                rr = np.clip((x - xa) / xlen, 0, 1)
                w = np.maximum(F.surface_y(np.clip(x, F.XF, F.XB), y), w_base)
                Y = side * (w + 0.0015 + 0.03 * F.cfg["length"] * rr ** 1.3)
                return (X, Y, Z)
            verts, faces, pix, rect = sheet(F, F.pect, f"{F.sid}_pect", cell * 0.7, place)
            rr = np.clip((pix[:, 0] - xa) / xlen, 0, 1)
            Xp, Zp = F.to_m(x_base, y_base)
            piv = np.array([Xp, side * w_base, Zp])
            parts.append(dict(verts=verts, faces=faces, pix=pix, rect=rect, part=4, kind="pect", mask=F.pect,
                              weight=np.clip(rr / 0.25, 0, 1) ** 1.5, piv=piv))
    return parts


def pack(rects):
    keys = list(rects)

    def shelf(k):
        order = sorted(keys, key=lambda t: -(rects[t][3] - rects[t][1]))
        x = y = float(PAD); sh = 0.0
        place = {}
        for t in order:
            w = (rects[t][2] - rects[t][0]) * k + 1; h = (rects[t][3] - rects[t][1]) * k + 1
            if w > AW - 2 * PAD:
                return None, 1e9
            if x + w > AW - PAD:
                x, y, sh = float(PAD), y + sh + PAD, 0.0
            place[t] = (x, y); x += w + PAD; sh = max(sh, h)
        return place, y + sh + PAD
    lo, hi = 0.02, 3.0
    for _ in range(40):
        k = (lo + hi) / 2
        _, used = shelf(k)
        lo, hi = (k, hi) if used <= FIN_ROWS else (lo, k)
    place, _ = shelf(lo)
    return lo, place


def bake(F, fin_parts, k, place):
    atlas = np.zeros((AH, AW, 4), np.float32)          # row 0 = V 0 (bottom)
    rows = np.arange(FIN_ROWS, AH)
    vm = ((rows + 0.5) / AH - BODY_V0) / (1 - BODY_V0)
    U = (np.arange(AW) + 0.5) / AW
    uu, vv = np.meshgrid(U, vm)
    xp = F.XF + uu * (F.XB - F.XF)
    t = vv * np.pi
    yp, side = F.section(xp, t)
    hw = np.abs(side)
    # how squarely each texel faces the camera that took the photo (projection stretch)
    dYt, dZt = np.gradient(hw, axis=0), np.gradient(-yp, axis=0)
    dx = (F.XB - F.XF) / AW
    dYx, dZx = np.gradient(hw, axis=1) / dx, np.gradient(-yp, axis=1) / dx
    nx = dYt * dZx - dZt * dYx; ny = dZt; nz = -dYt
    facing = np.abs(ny) / np.maximum(np.sqrt(nx * nx + ny * ny + nz * nz), 1e-9)
    p_in = bilinear(F.inside, xp, yp)
    w = (ss(0.15, 0.45, facing) * ss(0.2, 0.9, p_in))[..., None]
    col = bilinear(F.skin, xp, yp) * w + bilinear(F.skin_blur, xp, yp) * (1 - w)
    atlas[FIN_ROWS:, :, :3] = lin_to_srgb(col)
    atlas[FIN_ROWS:, :, 3] = 1.0
    # 背中の真ん中の線（体の輪の上の端）は、体の所の端の行（FIN_ROWS）をちょうど読む。その外はひれとの間の PAD で透明なので、
    # 読む色が半分透けて背中の真ん中が細く抜け、背びれと体の間のすき間に見えた。端の行を PAD の半分まで伸ばす
    atlas[FIN_ROWS - PAD // 2:FIN_ROWS] = atlas[FIN_ROWS]
    # 縦のひれの板は、体の輪郭の中（3 画素より内）を透明に。ひれの付け根と体の輪郭の間は「ひれに囲まれた穴」として体の色で
    # 埋まっていて、体の中に隠れるはずが、ひれの前後の端では体の下にのぞき、縦の線に見えた
    yy, xx = np.mgrid[0:F.H, 0:F.W]
    xc = np.clip(xx, F.XF, F.XB)
    inside = erode((yy >= F.TOP(xc)) & (yy <= F.BOT(xc)) & (xx >= F.XF) & (xx <= F.XB), 3)
    for p in fin_parts:
        key = p["kind"]
        x0, y0, x1, y1 = p["rect"]
        ox, oy = place[key]
        pw = int(math.ceil((x1 - x0) * k)); ph = int(math.ceil((y1 - y0) * k))
        PX, PY = np.meshgrid(np.arange(int(ox), min(AW, int(ox) + pw + 1)), np.arange(int(oy), min(FIN_ROWS, int(oy) + ph + 1)))
        sx = x0 + (PX + 0.5 - ox) / k; sy = y0 + (PY + 0.5 - oy) / k
        c = bilinear(F.plate, sx, sy)
        # そのひれの所だけ（写真のひれは全部 1 枚にあるので、四角の中のほかのひれ、尾びれの横のしりびれや腹びれの前の胸びれが、
        # 板の端のます目に細い縦の帯として出る）
        own = dilate(p["mask"], 2) & (~inside if p["part"] == 1 else True)
        c[..., 3] *= np.clip(bilinear(box_blur(own.astype(np.float32), 1)[..., None], sx, sy)[..., 0], 0, 1)
        rr = FIN_ROWS - 1 - PY
        atlas[rr, PX, :3] = lin_to_srgb(c[..., :3])
        atlas[rr, PX, 3] = c[..., 3]
    img = bpy.data.images.new(F.sid + "_atlas", AW, AH, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(atlas, np.float32).ravel())
    img.filepath_raw = ROOT + "scripts/fishgen/logs/" + F.sid + "_atlas.png"
    img.file_format = "PNG"
    img.save()
    return img


def make(sid):
    bpy.ops.wm.read_homefile(use_empty=True)
    F = Fish(sid)
    F.layers()
    body = build_body(F)
    eyes = build_eyes(F)
    fins = build_fins(F)
    rects = {}
    for p in fins:
        rects[p["kind"]] = p["rect"]
    k, place = pack(rects)
    fin_objs = []
    for p in fins:
        x0, y0 = p["rect"][:2]
        ox, oy = place[p["kind"]]
        uv_pt = np.stack([(ox + (p["pix"][:, 0] - x0) * k) / AW, (FIN_ROWS - (oy + (p["pix"][:, 1] - y0) * k)) / AH], -1)
        uvs = [tuple(tuple(uv_pt[i]) for i in f) for f in p["faces"]]
        ob = mesh_from(F.sid + "_" + p["kind"], p["verts"], p["faces"], uvs)
        n = len(p["verts"])
        fin = np.zeros((n, 3)); fin[:, 0] = p["part"]
        fin[:, 1] = p.get("weight", np.ones(n))
        piv = np.tile(p.get("piv", np.zeros(3)), (n, 1))
        set_attr(ob.data, "_FIN", fin)
        set_attr(ob.data, "_PIV", piv)
        fin_objs.append(ob)
    img = bake(F, fins, k, place)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in [body] + eyes + fin_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    me = body.data
    mat = bpy.data.materials.new(sid)
    mat.use_nodes = True
    Nn, L = mat.node_tree.nodes, mat.node_tree.links
    b = next(n for n in Nn if n.type == "BSDF_PRINCIPLED")
    tn = Nn.new("ShaderNodeTexImage"); tn.image = img
    L.new(tn.outputs["Color"], b.inputs["Base Color"]); L.new(tn.outputs["Alpha"], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.4
    b.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = False
    me.materials.clear(); me.materials.append(mat)
    body.name = sid
    sw = F.cfg["swim"]
    snout = float(F.to_m(F.snout_px, 0)[0])
    body["swim"] = {"snout": snout, "length": F.cfg["length"], "lambda": sw["lam"], "freq": sw["freq"], "amp": sw["amp"],
                    "env": sw["env"], "flat": F.flat, "name": F.cfg["name"],
                    # 写真の画素と模型の対応：模型 x = (x0 − 画素 x) / k、模型 y = (z0 − 画素 y) / k
                    "photo": [round(F.X0, 2), round(F.Z0, 2), round(1 / F.S, 3)]}
    me.calc_loop_triangles()
    stats = dict(id=sid, tris=len(me.loop_triangles), verts=len(me.vertices), fins=len(F.median), photo=list(body["swim"]["photo"]),
                 pect=F.pect is not None, eyes=len(F.eyes), pack_scale=round(k, 3))
    for o in bpy.context.selected_objects:
        o.select_set(False)
    body.select_set(True)
    # the light fixed version (_lo3) uses the full glb's texture in the game, so it is exported without the image
    # (FISH_LOD_TEX=1 keeps it: for a fish whose full glb was made elsewhere with a different atlas, e.g. suzuki)
    image_format = "NONE" if LOD_LEVEL == 3 and os.environ.get("FISH_LOD_TEX") != "1" else "WEBP"
    kw = dict(filepath=OUT + sid + LOD_SUFFIX + ".glb", export_format="GLB", use_selection=True, export_animations=False,
              export_skins=False, export_yup=True, export_apply=False, export_image_format=image_format,
              export_image_quality=88, export_texcoords=True, export_normals=True, export_tangents=False,
              export_attributes=True, export_extras=True, export_materials="EXPORT")
    bpy.ops.export_scene.gltf(**kw)
    stats["glb_kb"] = round(os.path.getsize(OUT + sid + LOD_SUFFIX + ".glb") / 1024)
    if LOD:
        print("FISHSTATS " + json.dumps(stats, ensure_ascii=False))
        return
    print("FISHSTATS " + json.dumps(stats, ensure_ascii=False))
    # debug overlay of the analysis
    dbg = F.src.copy()
    dbg[F.body & ~erode(F.body, 2)] = (0, 1, 1)
    for m in F.median:
        dbg[m & ~erode(m, 2)] = (1, 0, 1)
    if F.pect is not None:
        dbg[F.pect & ~erode(F.pect, 2)] = (1, 1, 0)
    for (ex, ey, r) in F.eyes:
        yy, xx = np.ogrid[0:F.H, 0:F.W]
        ring = np.abs(np.hypot(xx - ex, yy - ey) - r) < 1.5
        dbg[ring] = (0, 1, 0)
    im = bpy.data.images.new(sid + "_dbg", F.W, F.H)
    im.pixels.foreach_set(np.concatenate([dbg[::-1], np.ones((F.H, F.W, 1), np.float32)], -1).ravel())
    im.filepath_raw = ROOT + "scripts/fishgen/logs/" + sid + "_analysis.png"
    im.file_format = "PNG"
    im.save()


if __name__ == "__main__":
    ids = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(SPECIES)
    for sid in ids:
        try:
            make(sid)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("FISHFAIL", sid, e)
