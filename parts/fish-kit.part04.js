					const span = front - mouth.joint[0];
					k = Math.max(k, THREE.MathUtils.smoothstep(x, front - .6 * span, front - .3 * span));
				}
			} else continue;
			w[i * 2] = k * THREE.MathUtils.smoothstep(x, mouth.joint[0] - .008, mouth.joint[0]);
		}
	}
	geo.setAttribute("jaw", new THREE.BufferAttribute(w, 2));
}
/**
* 目（部位 6）の回る中心を作る（マダイの lowpoly_lite.py と同じ：左右それぞれの目の頂点の平均が目玉の中心）。
* 中心があれば、シェーダーが目をきょろきょろ動かし、見ている人を目で追う。glb に中心が入っている種類は触らない。
* 片方の目の中心と半径（体の横から見た大きさ）を返す
*/
function addEyePivots(geo) {
	const fin = geo.getAttribute("_fin");
	const piv = geo.getAttribute("_piv");
	const pos = geo.getAttribute("position");
	if (!fin || !piv || !pos) return null;
	const eye = [];
	for (let i = 0; i < pos.count; i++) if (partOf(fin, i) === 6) eye.push(i);
	if (!eye.length || eye.some((i) => piv.getX(i) !== 0 || piv.getY(i) !== 0 || piv.getZ(i) !== 0)) return null;
	let out = null;
	for (const side of [1, -1]) {
		const vs = eye.filter((i) => Math.sign(pos.getZ(i)) === side);
		if (!vs.length) continue;
		const c = new THREE.Vector3();
		for (const i of vs) c.add(new THREE.Vector3(pos.getX(i), pos.getY(i), pos.getZ(i)));
		c.divideScalar(vs.length);
		for (const i of vs) piv.setXYZ(i, c.x, -c.z, c.y);
		if (!out) {
			let r = 0;
			for (const i of vs) r = Math.max(r, Math.hypot(pos.getX(i) - c.x, pos.getY(i) - c.y));
			out = new THREE.Vector3(c.x, c.y, r);
		}
	}
	piv.needsUpdate = true;
	return out;
}
/** 頂点属性の i 番目の k 成分 */
var comp = (a, i, k) => k === 0 ? a.getX(i) : k === 1 ? a.getY(i) : k === 2 ? a.getZ(i) : a.getW(i);
/**
* 体の一部を切り抜いて、別に動く板にする（えらぶた・下あご）。体の三角形を limits（横から見た模型の (x, y) で、どれも 0 以上なら中）
* で切り抜いて写し、体から lift だけ浮かせて、縁に厚み thick を付ける。写真は体と同じ所なので、動かさなければ今までと同じに見える。
* part は部位の番号、_FIN.y には weight(x, y) を入れる（シェーダーが動かすのに使う）。sidesOnly なら体の横の面だけ（頭の上や下の面は入れない）。
* 縁の厚みは、rim(x, y) が両端とも true の辺だけに付ける（体につながっている辺に付けると、そこが光って白い線に見える）
*/
function cutPlate(geo, o) {
	const index = geo.getIndex();
	const pos = geo.getAttribute("position");
	const fin = geo.getAttribute("_fin");
	if (!index || !pos || !geo.getAttribute("normal") || !fin) return;
	const names = Object.keys(geo.attributes);
	const attrs = names.map((n) => geo.getAttribute(n));
	const offsets = [];
	let stride = 0;
	for (const a of attrs) {
		offsets.push(stride);
		stride += a.itemSize;
	}
	const at = (n) => offsets[names.indexOf(n)];
	const iPos = at("position");
	const iNor = at("normal");
	const iFin = at("_fin");
	const vert = (i) => {
		const v = [];
		attrs.forEach((a) => {
			for (let k = 0; k < a.itemSize; k++) v.push(comp(a, i, k));
		});
		return v;
	};
	const limits = o.limits.map((f) => (v) => f(v[iPos], v[iPos + 1]));
	const clip = (poly, f) => {
		const out = [];
		for (let k = 0; k < poly.length; k++) {
			const a = poly[k];
			const b = poly[(k + 1) % poly.length];
			const fa = f(a);
			const fb = f(b);
			if (fa >= 0) out.push(a);
			if (fa >= 0 !== fb >= 0) {
				const t = fa / (fa - fb);
				out.push(a.map((x, j) => x + (b[j] - x) * t));
			}
		}
		return out;
	};
	const mid = (a, b) => a.map((x, j) => (x + b[j]) / 2);
	const subdivide = (tri) => {
		const s = o.subdiv;
		if (!s) return [tri];
		const [x0, x1, y0, y1] = s.box;
		const xs = tri.map((v) => v[iPos]);
		const ys = tri.map((v) => v[iPos + 1]);
		if (Math.max(...xs) < x0 || Math.min(...xs) > x1 || Math.max(...ys) < y0 || Math.min(...ys) > y1) return [tri];
		let out = [tri];
		for (let k = 0; k < s.n; k++) out = out.flatMap(([a, b, c]) => {
			const ab = mid(a, b);
			const bc = mid(b, c);
			const ca = mid(c, a);
			return [
				[
					a,
					ab,
					ca
				],
				[
					ab,
					b,
					bc
				],
				[
					ca,
					bc,
					c
				],
				[
					ab,
					bc,
					ca
				]
			];
		});
		return out;
	};
	const lift = o.lift;
	const thick = o.thick;
	const added = [];
	const keys = /* @__PURE__ */ new Map();
	const tris = [];
	const addVert = (v) => {
		const key = `${v[iPos].toFixed(6)},${v[iPos + 1].toFixed(6)},${v[iPos + 2].toFixed(6)}`;
		const found = keys.get(key);
		if (found !== void 0) return found;
		const id = pos.count + added.length;
		added.push(v);
		keys.set(key, id);
		return id;
	};
	for (let t = 0; t < index.count; t += 3) {
		const ids = [
			index.getX(t),
			index.getX(t + 1),
			index.getX(t + 2)
		];
		if (ids.some((i) => partOf(fin, i) !== 0)) continue;
		const tri = ids.map(vert);
		const nz = tri.reduce((s, v) => s + v[iNor + 2], 0) / 3;
		if (o.sidesOnly && Math.abs(nz) < .3) continue;
		for (let poly of subdivide(tri)) {
			for (const f of limits) poly = clip(poly, f);
			if (poly.length < 3) continue;
			const vs = poly.map((v) => {
				const w = v.slice();
				const n = new THREE.Vector3(w[iNor], w[iNor + 1], w[iNor + 2]).normalize();
				w[iPos] += n.x * lift;
				w[iPos + 1] += n.y * lift;
				w[iPos + 2] += n.z * lift;
				w[iNor] = n.x;
				w[iNor + 1] = n.y;
				w[iNor + 2] = n.z;
				w[iFin] = o.part;
				w[iFin + 1] = o.weight(w[iPos], w[iPos + 1]);
				w[iFin + 2] = 0;
				return addVert(w);
			});
			for (let k = 1; k + 1 < vs.length; k++) tris.push(vs[0], vs[k], vs[k + 1]);
		}
	}
	if (!tris.length) return;
	const edgeUse = /* @__PURE__ */ new Map();
	const ek = (a, b) => a < b ? `${a}_${b}` : `${b}_${a}`;
	for (let t = 0; t < tris.length; t += 3) for (let k = 0; k < 3; k++) {
		const e = ek(tris[t + k], tris[t + (k + 1) % 3]);
		edgeUse.set(e, (edgeUse.get(e) ?? 0) + 1);
	}
	const vOf = (i) => added[i - pos.count];
	const center = [
		0,
		0,
		0
	];
	for (const v of added) for (let k = 0; k < 3; k++) center[k] += v[iPos + k] / added.length;
	const flapTris = tris.length;
	for (let t = 0; t < flapTris; t += 3) for (let k = 0; k < 3; k++) {
		const a = tris[t + k];
		const b = tris[t + (k + 1) % 3];
		if (edgeUse.get(ek(a, b)) !== 1) continue;
		if (!o.rim(vOf(a)[iPos], vOf(a)[iPos + 1]) || !o.rim(vOf(b)[iPos], vOf(b)[iPos + 1])) continue;
		const rim = (i, depth) => {
			const w = vOf(i).slice();
			const n = new THREE.Vector3(w[iNor], w[iNor + 1], w[iNor + 2]);
			w[iPos] -= n.x * depth;
			w[iPos + 1] -= n.y * depth;
			w[iPos + 2] -= n.z * depth;
			const o = new THREE.Vector3(w[iPos] - center[0], w[iPos + 1] - center[1], 0).normalize();
			w[iNor] = o.x;
			w[iNor + 1] = o.y;
			w[iNor + 2] = 0;
			w[iFin + 2] = 1;
			return pos.count + added.push(w) - 1;
		};
		const [oa, ob, ia, ib] = [
			rim(a, 0),
			rim(b, 0),
			rim(a, thick),
			rim(b, thick)
		];
		tris.push(oa, ob, ib, oa, ib, ia);
	}
	const total = pos.count + added.length;
	attrs.forEach((a, n) => {
		const arr = new Float32Array(total * a.itemSize);
		for (let i = 0; i < pos.count; i++) for (let k = 0; k < a.itemSize; k++) arr[i * a.itemSize + k] = comp(a, i, k);
		added.forEach((v, j) => {
			for (let k = 0; k < a.itemSize; k++) arr[(pos.count + j) * a.itemSize + k] = v[offsets[n] + k];
		});
		geo.setAttribute(names[n], new THREE.BufferAttribute(arr, a.itemSize));
	});
	const idx = new Uint32Array(index.count + tris.length);
	for (let i = 0; i < index.count; i++) idx[i] = index.getX(i);
	idx.set(tris, index.count);
	geo.setIndex(new THREE.BufferAttribute(idx, 1));
	geo.computeBoundingSphere();
}
/**
* えらぶたを、体とは別の動く板にする（部位 7）。体の左右の、えらぶたの所の三角形を縁の曲線で切り抜いて写し、
* 体から少し浮かせて（体長の 0.2%）、縁に厚み（体長の 0.4%）を付ける。
* _FIN.y には、前の縁（ちょうつがい）からの距離（上の端ほど小さく、上の端では開かない）を入れる。シェーダーがこれで外へ開く
*/
function addGillCover(geo, g, length) {
	const edgeX = (y) => lineX(g.edge, y);
	const hingeX = (y) => lineX(g.hinge, y);
	cutPlate(geo, {
		limits: [
			(x, y) => x - edgeX(y),
			(x, y) => hingeX(y) - x,
			(_x, y) => g.top - y,
			(_x, y) => y - g.bottom
		],
		part: 7,
		lift: .002 * length,
		thick: .004 * length,
		sidesOnly: true,
		weight: (x, y) => Math.max(0, Math.min(hingeX(y), g.pivotMax) - x) * THREE.MathUtils.smoothstep(g.top - y, 0, .02 * length),
		rim: (x, y) => Math.min(hingeX(y), g.pivotMax) - x > .006 * length && g.top - y > .004 * length
	});
}
/**
* 下あごを、体とは別の動く板にする（部位 8）。唇の線 lipA（上あごの骨の縁を、口を閉じる角度だけ下へ回した線。写真の下唇とほぼ同じ）より下、
* 下あごの下側 under より上、関節より前の三角形を、左右と下の面ごと切り抜く（Codex に教えてもらったやり方）。
* 口を閉じると、板の上の縁（lipA）がちょうど上あごの骨の縁に重なる
*/
function addJawPlate(geo, m, length) {
	const lip = m.lowerLip;
	const front = Math.max(...m.under.map((p) => p[0]));
	const x0 = m.lowerLip[0][0];
	const raise = (x) => .003 * (1 - THREE.MathUtils.smoothstep(x, x0, x0 + .025));
	cutPlate(geo, {
		limits: [
			(x, y) => lineXofX(lip, x) + raise(x) - y,
			(x, y) => y - lineXofX(m.under, x),
			(x) => x - m.joint[0],
			(x) => front - x
		],
		part: 8,
		lift: .0015 * length,
		thick: .003 * length,
		sidesOnly: false,
		weight: () => 1,
		rim: (x, y) => lineXofX(lip, x) + raise(x) - y < .0015 && x > m.joint[0] + .004
	});
}
/**
* 上あご（前上顎骨と主上顎骨）を、体とは別の動く板にする（部位 9）。多角形 upper の中の三角形を、左右と上下の面ごと切り抜いて、
* 下あごの板より少し外へ浮かせる（開いた口では、写真のとおり下あごの後ろに重なる）
*/
function addUpperJawPlate(geo, m, length) {
	cutPlate(geo, {
		limits: m.close > 0 ? [(x, y) => polyInside(m.upper, x, y)] : [(x, y) => polyInside(m.upper, x, y), (x, y) => y - lipCut(m, x)],
		part: 9,
		lift: (m.close > 0 ? .0025 : .001) * length,
		thick: (m.close > 0 ? .003 : .0012) * length,
		sidesOnly: false,
		weight: () => 1,
		rim: (x, y) => Math.hypot(x - m.upperPivot[0], y - m.upperPivot[1]) > .004,
		subdiv: {
			box: [
				Math.min(...m.upper.map((p) => p[0])),
				Math.max(...m.upper.map((p) => p[0])),
				Math.min(...m.upper.map((p) => p[1])),
				Math.max(...m.upper.map((p) => p[1]))
			],
			n: m.close > 0 ? 3 : 2
		}
	});
}
/** 部位の番号（_FIN の x） */
var partOf = (fin, i) => Math.round(fin.getX(i));
/**
* ひれの縁の線を消す（どの種類も、テクスチャの上の 400 行が体、その下がひれの写真）。
* ひれの写真のいちばん上の行は体の写真のすぐ下にあるので、そのまま写すと、ひれの縁に体の色が細い線になって出る。
* ひれの頂点の v を、体の写真の下の端から 4 ピクセル離す。胴の頂点は、体の写真の下の端の 1 ピクセル内側までにする
*/
function fixFinEdges(geo, texHeight) {
	const fin = geo.getAttribute("_fin");
	const uv = geo.getAttribute("uv");
	if (!fin || !uv) return;
	let bodyV = 0;
	for (let i = 0; i < uv.count; i++) if (partOf(fin, i) === 0) bodyV = Math.max(bodyV, uv.getY(i));
	const minV = bodyV + 4 / texHeight;
	const maxV = bodyV - 1 / texHeight;
	for (let i = 0; i < uv.count; i++) {
		const p = partOf(fin, i);
		if (p !== 0 && p !== 6 && p !== 7 && uv.getY(i) < minV) uv.setY(i, minV);
		if (p === 0 && uv.getY(i) > maxV) uv.setY(i, maxV);
	}
	uv.needsUpdate = true;
}
/** 体の上下の輪郭と、ひれの板（三角形でつながった、背びれ・しりびれなど部位 1・2 の頂点のまとまり） */
function finLayout(geo) {
	const fin = geo.getAttribute("_fin");
	const pos = geo.getAttribute("position");
	const index = geo.getIndex();
	if (!fin || !pos || !index) return null;
	let x0 = Infinity;
	let x1 = -Infinity;
	for (let i = 0; i < pos.count; i++) {
		if (partOf(fin, i) !== 0) continue;
		x0 = Math.min(x0, pos.getX(i));
		x1 = Math.max(x1, pos.getX(i));
	}
	const N = 100;
	const top = new Float32Array(N).fill(-Infinity);
	const bottom = new Float32Array(N).fill(Infinity);
	const bin = (x) => THREE.MathUtils.clamp(Math.floor((x - x0) / (x1 - x0) * N), 0, 99);
	for (let i = 0; i < pos.count; i++) {
		if (partOf(fin, i) !== 0) continue;
		const b = bin(pos.getX(i));
		top[b] = Math.max(top[b], pos.getY(i));
		bottom[b] = Math.min(bottom[b], pos.getY(i));
	}
	for (const arr of [top, bottom]) {
		const filled = [...arr.keys()].filter((k) => Number.isFinite(arr[k]));
		if (!filled.length) continue;
		for (let k = 0; k < N; k++) {
			if (Number.isFinite(arr[k])) continue;
			const a = filled.filter((j) => j < k).pop();
			const b = filled.find((j) => j > k);
			arr[k] = a === void 0 ? arr[b] : b === void 0 ? arr[a] : arr[a] + (arr[b] - arr[a]) * (k - a) / (b - a);
		}
	}
	const bodyAt = (x, upper) => {
		const b = bin(x);
		let y = upper ? Infinity : -Infinity;
		for (let k = Math.max(0, b - 1); k <= Math.min(99, b + 1); k++) {
			if (upper && Number.isFinite(top[k])) y = Math.min(y, top[k]);
			if (!upper && Number.isFinite(bottom[k])) y = Math.max(y, bottom[k]);
		}
		return y;
	};
	let bodyTop = -Infinity;
	let bodyBottom = Infinity;
	for (let k = 0; k < N; k++) {
		if (Number.isFinite(top[k])) bodyTop = Math.max(bodyTop, top[k]);
		if (Number.isFinite(bottom[k])) bodyBottom = Math.min(bodyBottom, bottom[k]);
	}
	const bodyMid = (bodyTop + bodyBottom) / 2;
	const parent = new Int32Array(pos.count).map((_, i) => i);
	const root = (i) => parent[i] === i ? i : parent[i] = root(parent[i]);
	for (let t = 0; t < index.count; t += 3) {
		const a = index.getX(t);
		if (partOf(fin, a) === 0) continue;
		parent[root(index.getX(t + 1))] = root(a);
		parent[root(index.getX(t + 2))] = root(a);
	}
	const plates = /* @__PURE__ */ new Map();
	for (let i = 0; i < pos.count; i++) {
		const p = partOf(fin, i);
		if (p !== 1 && p !== 2) continue;
		const r = root(i);
		if (!plates.has(r)) plates.set(r, []);
		plates.get(r).push(i);
	}
	return {
		x0,
		x1,
		bodyAt,
		bodyMid,
		plates: [...plates.values()]
	};
}
/**
* ひれのはためきの重み（頂点属性 flutter）= (付け根 0 〜 縁 1, 前 0 〜 後ろ 1, ひれの番号)。胸びれ（部位 4）は、もとの重み（付け根 0 〜 先 1）。
* 背びれ・しりびれ・腹びれは体の表面からの高さ、尾びれは体の後ろの端からの距離で測り、板ごとにいちばん遠い所を 1 にする。
* 前後は板ごとに、いちばん前（口に近い所）を 0、いちばん後ろを 1 にする。番号は板ごとにばらばらの 0〜1（尾びれは -1：旗にしない）
*/
/** 尾びれのほかのひれは、はためかない（軽い固定版） */
function tailOnlyFlutter(geo) {
	const fin = geo.getAttribute("_fin");
	const fl = geo.getAttribute("flutter");
	if (!fin || !fl) return;
	for (let i = 0; i < fl.count; i++) if (partOf(fin, i) !== 3) fl.setX(i, 0);
	fl.needsUpdate = true;
}
function addFlutterWeights(geo) {
	const fin = geo.getAttribute("_fin");
	const pos = geo.getAttribute("position");
	if (!fin || !pos) return;
	const w = new Float32Array(pos.count * 3);
	const h = new Float32Array(pos.count);
	for (let i = 0; i < pos.count; i++) if (partOf(fin, i) === 4) w[i * 3] = fin.getY(i);
	const layout = finLayout(geo);
	if (layout) {
		const { x0, bodyAt, bodyMid, plates } = layout;
		const cx = plates.map((vs) => vs.reduce((s, i) => s + pos.getX(i), 0) / vs.length);
		const rank = cx.map((x) => cx.filter((o) => o > x).length);
		plates.forEach((vs, n) => {
			let ymin = Infinity;
			let ymax = -Infinity;
			let xmin = Infinity;
			let xmax = -Infinity;
			for (const i of vs) {
				ymin = Math.min(ymin, pos.getY(i));
				ymax = Math.max(ymax, pos.getY(i));
				xmin = Math.min(xmin, pos.getX(i));
				xmax = Math.max(xmax, pos.getX(i));
			}
			let upper = ymin > bodyMid;
			let lower = ymax < bodyMid;
			if (!upper && !lower && (xmin + xmax) / 2 > x0 + .15 * (layout.x1 - x0)) {
				upper = vs.reduce((s, i) => s + pos.getY(i), 0) / vs.length > bodyMid;
				lower = !upper;
			}
			const d = vs.map((i) => {
				const x = pos.getX(i);
				const y = pos.getY(i);
				const v = upper ? y - bodyAt(x, true) : lower ? bodyAt(x, false) - y : x0 - x;
				return Number.isFinite(v) ? Math.max(0, v) : 0;
			});
			const far = Math.max(...d);
			if (far <= 0) return;
			const id = upper || lower ? (rank[n] + 1) * .618034 % 1 : -1;
			vs.forEach((i, k) => {
				w[i * 3] = d[k] / far;
				w[i * 3 + 1] = xmax > xmin ? (xmax - pos.getX(i)) / (xmax - xmin) : 0;
				w[i * 3 + 2] = id;
				if (upper || lower) h[i] = upper ? d[k] : -d[k];
			});
		});
	}
	geo.setAttribute("flutter", new THREE.BufferAttribute(w, 3));
	geo.setAttribute("finH", new THREE.BufferAttribute(h, 1));
}
/**
* 背びれ・しりびれの付け根のすきまを埋める。ひれは縦の平らな板で、板は体の中まであるが、写真のひれは付け根が
* 体の表面より少し外で切れていて、体との間が透けて見える。写真のひれの付け根の色を、体の表面の少し内側（体長の 0.6%）まで
* 伸ばしたテクスチャを作って返す。板の上の位置と写真の位置の対応は、板ごとに頂点から求める。minV より上の行は触らない
*/
function fillFinBases(geo, map, length, minV) {
	const fin = geo.getAttribute("_fin");
	const uv = geo.getAttribute("uv");
	const pos = geo.getAttribute("position");
	const index = geo.getIndex();
	const img = map.image;
	if (!fin || !uv || !pos || !index || !img?.width) return map;
	const W = img.width;
	const H = img.height;
	const canvas = document.createElement("canvas");
	canvas.width = W;
	canvas.height = H;
	const ctx = canvas.getContext("2d", { willReadFrequently: true });
	if (!ctx) return map;
	ctx.drawImage(img, 0, 0);
	const data = ctx.getImageData(0, 0, W, H);
	const px = data.data;
	const layout = finLayout(geo);
	if (!layout) return map;
	const { x0, x1, bodyAt, bodyMid, plates } = layout;
	const inset = .006 * length;
	const maxGap = .01 * length;
	for (const vs of plates) {
		let sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0, su = 0, sxu = 0, syu = 0, sv = 0, sxv = 0, syv = 0;
		let ymin = Infinity, ymax = -Infinity, umin = Infinity, umax = -Infinity, vmin = Infinity, vmax = -Infinity;
		for (const i of vs) {
			const x = pos.getX(i), y = pos.getY(i), u = uv.getX(i) * W, v = uv.getY(i) * H;
			sx += x;
			sy += y;
			sxx += x * x;
			sxy += x * y;
			syy += y * y;
			su += u;
			sxu += x * u;
			syu += y * u;
			sv += v;
			sxv += x * v;
			syv += y * v;
			ymin = Math.min(ymin, y);
			ymax = Math.max(ymax, y);
			umin = Math.min(umin, u);
			umax = Math.max(umax, u);
			vmin = Math.min(vmin, v);
			vmax = Math.max(vmax, v);
		}
		const upper = ymin > bodyMid;
		if (!upper && ymax > bodyMid) continue;
		const m = new THREE.Matrix3().set(sxx, sxy, sx, sxy, syy, sy, sx, sy, vs.length);
		if (Math.abs(m.determinant()) < 1e-12) continue;
		m.invert();
		const cu = new THREE.Vector3(sxu, syu, su).applyMatrix3(m);
		const cv = new THREE.Vector3(sxv, syv, sv).applyMatrix3(m);
		const inv = new THREE.Matrix3().set(cu.x, cu.y, cu.z, cv.x, cv.y, cv.z, 0, 0, 1);
		if (Math.abs(inv.determinant()) < 1e-12) continue;
		inv.invert();
		const p = new THREE.Vector3();
		const v0 = Math.max(Math.ceil(vmin), Math.ceil(minV * H));
		const v1 = Math.min(Math.floor(vmax), H - 1);
		for (let u = Math.max(0, Math.ceil(umin)); u <= Math.min(W - 1, Math.floor(umax)); u++) {
			let vo = -1;
			if (upper) {
				for (let v = v1; v >= v0 && vo < 0; v--) if (px[(v * W + u) * 4 + 3] >= 128) vo = v;
			} else for (let v = v0; v <= v1 && vo < 0; v++) if (px[(v * W + u) * 4 + 3] >= 128) vo = v;
			if (vo < 0) continue;
			p.set(u, vo, 1).applyMatrix3(inv);
			if (p.x < x0 || p.x > x1) continue;
			const yIn = upper ? bodyAt(p.x, true) - inset : bodyAt(p.x, false) + inset;
			if (!Number.isFinite(yIn)) continue;
			if ((upper ? p.y - yIn : yIn - p.y) > inset + maxGap) continue;
			const vIn = Math.round(cv.x * p.x + cv.y * yIn + cv.z);
			const c = (THREE.MathUtils.clamp(upper ? vo - 3 : vo + 3, v0, v1) * W + u) * 4;
			const r = px[c];
			const g = px[c + 1];
			const b = px[c + 2];
			const a0 = upper ? vo + 1 : Math.max(vIn, v0);
			const a1 = upper ? Math.min(vIn, v1) : vo - 1;
			for (let v = a0; v <= a1; v++) {
				const k = (v * W + u) * 4;
				px[k] = r;
				px[k + 1] = g;
				px[k + 2] = b;
				px[k + 3] = 255;
			}
		}
	}
	ctx.putImageData(data, 0, 0);
	const tex = new THREE.CanvasTexture(canvas);
	tex.colorSpace = map.colorSpace;
	tex.flipY = map.flipY;
	tex.wrapS = map.wrapS;
	tex.wrapT = map.wrapT;
	tex.anisotropy = map.anisotropy;
	map.dispose();
	return tex;
}
/**
* 写真の魚を読み込んでおく（無いファイルは飛ばし、その種類は手続きで作った形のまま。?nophotofish で全部手続きの形）。
* pick.only：この種類だけ読む、pick.skip：この種類は読まない（省けば全部）。
* pick.lo = false なら遠い形（_lo.glb）を読まない（ゲーム。掛かるまでの魚は軽い固定版で描き、細かい形で描くのは掛かった 1 匹だけなので、
* 遠くでも細かい形のまま描く。ファイルは確認ページのために残してある）。
* pick.fixed = false なら軽い固定版（_lo3.glb）を読まない（配布用の魚のキット。_lo3 は入れていない）
*/
async function loadPhotoFish(base = `/fish/`, pick = {}) {
	if (new URLSearchParams(location.search).has("nophotofish")) return;
	const loader = new GLTFLoader();
	const want = Object.entries(FILES).filter(([id]) => (!pick.only || pick.only.includes(id)) && !pick.skip?.includes(id));
	const lo = pick.lo === false ? null : "_lo";
	await Promise.all(want.map(async ([id, file]) => {
		await loadOne(loader, base, id, file, lo);
		if (pick.fixed !== false) await loadOne(loader, base, id, file, FIXED_SUFFIX, id + FIXED_SUFFIX + "_fixed", true, true);
	}));
}
var urlOf = (base, name) => typeof base === "string" ? base + name : base(name);
/** 写真の魚がある種類の id と、public/fish/ のファイル名（配布用の魚のキットが一覧に使う） */
function photoFishFiles() {
	return { ...FILES };
}
/** 軽い固定版の形のファイル名の後ろ（scripts/fishgen で FISH_LOD=3。画像は入れず、細かい形の画像を使う） */
var FIXED_SUFFIX = "_lo3";
/**
* 軽い固定版でも、細かい形の画像を使わず、固定版の glb に入れた自分の画像を使う種類。シーバスは細かい形の glb を別の生成スクリプト
* （japan-scenery）で作ったので、画像の中のひれの並べ方が違い、細かい形の画像を貼るとひれの模様がずれる
*/
var OWN_FIXED_TEXTURE = /* @__PURE__ */ new Set(["seabass"]);
/**
* 1 種類を読み込んで assets に入れる。loSuffix が null なら遠い形を読まない。needLo なら遠い形のファイルが無いときは入れない。
* fixed は軽い固定版（loadPhotoFishVariant）
*/
async function loadOne(loader, base, id, file, loSuffix = "_lo", key = id, needLo = false, fixed = false) {
	try {
		const hi0 = fixed ? null : first(await loader.loadAsync(urlOf(base, `${file}.glb`)));
		if (!fixed && !hi0) return;
		const lo0 = loSuffix === null ? null : await loader.loadAsync(urlOf(base, `${file}${loSuffix}.glb`)).then(first, () => null);
		if ((needLo || fixed) && !lo0) return;
		const hi = fixed ? lo0 : hi0;
		const lo = fixed ? null : lo0;
		const fileTris = {
			hi: triCount(hi.geometry),
			lo: lo ? triCount(lo.geometry) : 0
		};
		const swim = hi.userData.swim;
		const shared = fixed && !OWN_FIXED_TEXTURE.has(id) ? assets.get(id)?.map ?? null : null;
		const photo = shared ?? hi.material.map;
		if (!photo) return;
		const texHeight = photo.image?.height ?? 640;
		let bodyV = 0;
		const fin = hi.geometry.getAttribute("_fin");
		const uvs = hi.geometry.getAttribute("uv");
		if (fin && uvs) {
			for (let i = 0; i < uvs.count; i++) if (partOf(fin, i) === 0) bodyV = Math.max(bodyV, uvs.getY(i));
		}
		const map = shared ?? fillFinBases(hi.geometry, photo, swim.length, bodyV + 4 / texHeight);
		const mouth = fixed ? null : MOUTHS[id] ?? null;
		fixFinEdges(hi.geometry, texHeight);
		addFlutterWeights(hi.geometry);
		if (fixed) tailOnlyFlutter(hi.geometry);
		if (lo) {
			fixFinEdges(lo.geometry, texHeight);
			addFlutterWeights(lo.geometry);
		}
		const gill = fixed ? null : GILLS[id] ?? null;
		if (gill) {
			addGillCover(hi.geometry, gill, swim.length);
			if (lo) addGillCover(lo.geometry, gill, swim.length);
		}
		if (mouth) {
			if (mouth.close === 0) {
				splitAtLip(hi.geometry, mouth);
				if (lo) splitAtLip(lo.geometry, mouth);
			}
			addJawPlate(hi.geometry, mouth, swim.length);
			addUpperJawPlate(hi.geometry, mouth, swim.length);
			if (lo) {
				addJawPlate(lo.geometry, mouth, swim.length);
				addUpperJawPlate(lo.geometry, mouth, swim.length);
			}
		}
		addJawWeights(hi.geometry, mouth);
		if (lo) addJawWeights(lo.geometry, mouth);
		const still = fixed || STILL.has(id);
		const eye = still ? null : addEyePivots(hi.geometry);
		if (eye && lo) addEyePivots(lo.geometry);
		map.anisotropy = 4;
		map.wrapS = map.wrapT = THREE.ClampToEdgeWrapping;
		let photos = null;
		const hf = HEAD_FILES[id];
		if (hf && gill) {
			const tl = new THREE.TextureLoader();
			const load = async (f) => {
				const t = await tl.loadAsync(urlOf(base, f));
				t.colorSpace = THREE.SRGBColorSpace;
				t.flipY = false;
				t.anisotropy = 4;
				t.needsUpdate = true;
				return t;
			};
			photos = await Promise.all([load(`${hf.file}_head.webp`), load(`${hf.file}_cover.webp`)]).then(([head, cover]) => ({
				head,
				cover
			}), () => null);
		}
		const [x0, z0, k] = swim.photo ?? [
			HEAD_PHOTO.x0,
			HEAD_PHOTO.z0,
			HEAD_PHOTO.k
		];
		const headMap = {
			x0,
			z0,
			k,
			box: hf?.box ?? [
				0,
				0,
				1,
				1
			]
		};
		const foldMax = FOLD_MAX[id] ?? 1.1;
		assets.set(key, {
			hi: hi.geometry,
			lo: lo?.geometry ?? null,
			map,
			swim,
			gill,
			mouth,
			eye,
			photos,
			headMap,
			still,
			foldMax,
			fileTris,
			tailFlutter: fixed
		});
	} catch {}
}
/** glb の中のいちばん初めの形 */
function first(gltf) {
	let mesh = null;
	gltf.scene.traverse((o) => {
		if (!mesh && o.isMesh) mesh = o;
	});
	return mesh;
}
var triCount = (g) => g ? (g.index ? g.index.count : g.attributes.position.count) / 3 : 0;
/** 確認ページ用：形の三角形の数（細かい / 粗い。file は glb のままの数）、テクスチャの大きさ、泳ぎの値 */
function photoFishInfo(id) {
	const a = assets.get(id);
	if (!a) return null;
	const img = a.map.image;
	return {
		hi: triCount(a.hi),
		lo: triCount(a.lo),
		file: a.fileTris,
		texture: `${img?.width ?? "?"}×${img?.height ?? "?"}`,
		swim: a.swim
	};
}
new THREE.Matrix4();
new THREE.Matrix4();
/** まとめて描く軽い固定版の 1 匹（操作は buildPhotoFish と同じ。目・ひれ・えらぶた・口は動かないので、その操作は何もしない） */
function buildBatchedFish(key, a, length, batches) {
	const root = new THREE.Group();
	const anchor = new THREE.Object3D();
	const s = length / a.swim.length;
	anchor.scale.setScalar(s);
	anchor.rotation.y = -Math.PI / 2;
	anchor.position.z = s * (.47 * a.swim.length - a.swim.snout);
	root.add(anchor);
	const m = {
		anchor,
		swim: new THREE.Vector4(0, 1, 0, 0),
		neck: new THREE.Vector4(0, .23, .43, 0),
		flut: new THREE.Vector4(0, 0, 0, 0),
		head: 1,
		power: 0,
		shade: 0
	};
	const batch = batches.get(key, a);
	batch.add(m);
	const env = a.swim.env ?? [
		.02,
		-.08,
		.16
	];
	const tipEnv = env[0] + env[1] + env[2];
	return {
		root,
		shadows: [batch.shadow],
		/** もう使わない（まとまりから外す） */
		dispose() {
			batch.remove(m);
		},
		detail(_on) {},
		shade(opacity) {
			m.shade = opacity;
		},
		swim(phase, amp, bend = 0) {
			m.swim.set(phase / (Math.PI * 2), amp / (a.swim.amp * tipEnv), THREE.MathUtils.clamp(bend, -4, 4) * s, 0);
		},
		lieOnFloor(_up) {},
		lookAtViewer(_amount) {},
		finMove(_clock, _tilt, _fold, _steer, _wobble = 0, _pect = 0, _whim = 0) {},
		mouth(_open) {},
		mouthMax: 0,
		gill(_open) {},
		/** 尾びれのはためき（ほかのひれは、はためかない形になっている） */
		flutter(clock, amp, flag = 0, seed = 0) {
			m.flut.set(clock, amp, flag, seed);
		},
		flex(neck, from, to, cBend, head, power = 0) {
			m.neck.set(neck, from, to, THREE.MathUtils.clamp(cBend, -6, 6) * s);
			m.head = head;
			m.power = power;
		}
	};
}
/**
* 写真の魚を 1 匹作る。+Z が頭で、口先が体長の 47% 前に来る（手続きの魚と同じ置き方）。
* swim(phase, amp, bend)：phase は尾の位相 rad、amp は尾の先の振れ / 体長、bend は体の曲がり 1/m。
* batches を渡すと、まとめて描く（軽い固定版だけ。目・ひれ・えらぶた・口は動かさない）
*/
function buildPhotoFish(id, length, batches) {
