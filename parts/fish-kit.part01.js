import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
// src/game/fish/photo-fish.ts
/** 写真の魚がある種類（species.ts の id → public/fish/ のファイル名） */
var FILES = {
	aji: "aji",
	seabass: "suzuki",
	mebaru: "mebaru",
	kasago: "kasago",
	saba: "saba",
	tachiuo: "tachiuo",
	sawara: "sawara",
	kamasu: "kamasu",
	buri: "buri",
	hiramasa: "hiramasa",
	kihada: "kihada",
	magochi: "magochi",
	kurodai: "kurodai",
	madai: "madai",
	katakuchi: "katakuchi",
	isaki: "isaki",
	isaki_young: "isaki_young",
	onagagure: "onagagure",
	kuchibuto: "kuchibuto",
	shibudai: "shibudai"
};
/** ひれ・口・えら・目を動かさない、のっぺりした種類 */
var STILL = /* @__PURE__ */ new Set(["katakuchi"]);
/** 背びれ・しりびれを、ふつう（1.1 rad）より深く、背中にしまうように畳める種類 */
var FOLD_MAX = { tachiuo: 1.52 };
/** えらぶたの後ろの縁・前の縁の折れ線の点の数（シェーダーに渡す数） */
var GILL_EDGE_N = 40;
var GILL_HINGE_N = 40;
/** 口の折れ線の点の数・上あごの多角形の点の数（シェーダーに渡す数） */
var MOUTH_N = 8;
var UPPER_N = 20;
var SWIM_HEAD = `
uniform float uTime, uSnout, uLen, uLam, uBreath, uSwimAmp, uPectRest, uLookAt, uGill, uMouth, uFloor;
uniform vec2 uEyeBulge;
uniform vec4 uMouthShape, uMouthUpper;
uniform vec4 uMouthUpper2;
uniform float uMouthClose;
attribute vec2 jaw;
// えら・口の中・目の周りの色を付けるため、動かす前の模型の位置と部位、切り抜いた板の縁の印をフラグメントへ渡す
varying vec3 vModel;
varying float vPart;
varying float vRim;
uniform vec3 uEnv;
uniform vec4 uFin, uFinMove, uFinMove2;
#ifdef FISH_INSTANCED
// まとめて描くとき（軽い固定版。FishBatches）：1 匹ごとに違う値は、1 匹ずつの属性で受け取る（SWIM_BODY の初めで写す）。
// iMisc = (泳ぐときの頭の振れの倍率, 体全体を使って泳ぐ度合い, 影の濃さ)
attribute vec4 iSwim, iNeck, iFlut;
attribute vec3 iMisc;
vec4 uSwim, uNeck, uFlut;
float uHead, uPower;
#else
uniform vec4 uSwim, uNeck, uFlut;
uniform float uHead, uPower;
#endif
attribute vec3 _fin;
attribute vec3 _piv;
attribute vec3 flutter;
attribute float finH;
// 頭から尾へ伝わる体のうねり。包絡 A(s) = c0 + c1 s + c2 s^2（s = 0 口先〜1 尾の先）、cyc は尾を振った回数
// 全身で泳ぐときは、尾の先の振れは同じまま、頭（尾の 25%）から体の真ん中まで大きくうねる
float fishH(float s, float cyc, float amp) {
  float A0 = uEnv.x * uHead + uEnv.y * s + uEnv.z * s * s;
  float A1 = (uEnv.x + uEnv.y + uEnv.z) * (0.25 + 0.75 * pow(max(s, 0.0), 1.6));
  float A = mix(A0, A1, clamp(uPower, 0.0, 1.0));
  return uLen * amp * A * sin(6.2831853 * (s / uLam - cyc));
}
// 床に横たわっているとき（uFloor：模型の横 +Z が上を向いている度合い -1〜1。0 は床なし）は、横のうねりを上へだけ曲げる
// （横倒しなので横のうねりが上下になり、下へ曲げた所が床に入る。体の長いタチウオは尾が大きく沈んだ）。0 の所でなめらかに折り返す
float lieH(float s, float cyc, float amp) {
  float h = fishH(s, cyc, amp);
  if (uFloor == 0.0) return h;
  float k = sign(uFloor), e = 0.004 * uLen;
  float up = 0.5 * (h * k + sqrt(h * h + e * e)) - 0.5 * e;
  return mix(h, k * up, abs(uFloor));
}
mat3 rotAxis(vec3 a, float t) {
  float c = cos(t), s = sin(t), k = 1.0 - c;
  return mat3(c + a.x * a.x * k, a.y * a.x * k + a.z * s, a.z * a.x * k - a.y * s,
              a.x * a.y * k - a.z * s, c + a.y * a.y * k, a.z * a.y * k + a.x * s,
              a.x * a.z * k + a.y * s, a.y * a.z * k - a.x * s, c + a.z * a.z * k);
}
// 0 から s までの smoothstep(a, b, t) の積分（首で曲げたとき、頭より後ろが横へずれる量）
float neckInt(float s, float a, float b) {
  if (s <= a) return 0.0;
  float w = b - a;
  if (s >= b) return 0.5 * w + (s - b);
  float u = (s - a) / w;
  return w * (u * u * u - 0.5 * u * u * u * u);
}
float fishHash(float n) { return fract(sin(n * 12.9898 + 4.1414) * 43758.5453); }
// ひれの気まぐれ：ひれごとに、よく分からない間隔で閉じたり広げたりする（-0.6 広げる 〜 +1 閉じる、半分ほどは何もしない）。
// しばらくそのままでいて、0.2〜0.9 秒ほどで次の開き具合へ動く（目の動きと同じ作り）。場面とは関係なく、ひれどうしもそろわない
float whimValue(float id, float seg) {
  if (fishHash(seg * 3.7 + id * 11.0) < 0.45) return 0.0;
  return mix(-0.6, 1.0, fishHash(seg * 1.3 + id * 23.0 + 5.0));
}
float finWhim(float id, float t) {
  float T = 1.4 + 2.6 * fishHash(id * 17.0 + 0.3);
  float k = t / T + fishHash(id * 5.0 + 1.7) * 9.0;
  float seg = floor(k);
  float move = mix(0.12, 0.3, fishHash(id + seg * 0.37));
  return mix(whimValue(id, seg - 1.0), whimValue(id, seg), smoothstep(0.0, move, fract(k)));
}
// 目の 1 つの動き：T 秒ごとに次の所へ、80ms ほどでさっと動く（-0.5〜0.5）
vec2 eyeJump(float id, float T) {
  float k = uTime / T + fishHash(id + 1.0) * 7.0, seg = floor(k);
  vec2 g0 = vec2(fishHash(seg * 1.7 + id), fishHash(seg * 2.3 + id + 11.0));
  vec2 g1 = vec2(fishHash(seg * 1.7 - 1.7 + id), fishHash(seg * 2.3 - 2.3 + id + 11.0));
  return mix(g1, g0, smoothstep(0.0, 0.08 / T, fract(k))) - 0.5;
}
// 目：大きく見る所を 0.35〜1.2 秒ごとに変え、その間にも 0.2〜0.5 秒ごとに小さくちらっと動き、いつも少しずつ揺れている
// （目玉がよく動くほど生きて見える）。左右の目はばらばら
vec2 eyeGaze(float id) {
  vec2 g = eyeJump(id, 0.35 + 0.85 * fishHash(id));
  g += 0.3 * eyeJump(id + 5.3, 0.2 + 0.3 * fishHash(id + 2.0));
  g += 0.06 * vec2(sin(uTime * 1.7 + id * 5.0), sin(uTime * 2.3 + id * 3.0));
  return g;
}
`;
var SWIM_BODY = `
#ifdef FISH_INSTANCED
uSwim = iSwim; uNeck = iNeck; uFlut = iFlut; uHead = iMisc.x; uPower = iMisc.y;
#endif
vec4 sw = uSwim, fs4 = uFin;
float seed = uSnout * 17.0;
float cyc = sw.x, amp = sw.y * uSwimAmp, bend = sw.z;
vec3 fishP = position;
vec3 objectNormal = normal;
float part = floor(_fin.x + 0.5);
float fw = _fin.y;
vModel = position;
vPart = part;
vRim = part > 6.5 ? _fin.z : 0.0;
vec3 piv = vec3(_piv.x, _piv.z, -_piv.y);
bool hasPiv = dot(_piv, _piv) > 1e-10;
mat3 R = mat3(1.0);
if (part == 4.0) {
  // 胸びれ：付け根を軸に開いて羽ばたく。先のほうが少し遅れてしなる
  float sd = sign(piv.z);
  float ang = uPectRest + sw.w + fs4.y * (0.5 - 0.5 * cos(6.2831853 * fs4.x - fw * 0.9));
  // 場面に合わせて開き（uFinMove2.y）、左右ばらばらにゆっくり開いたり閉じたりする
  float phz = mix(0.2, 0.5, fishHash(sd * 3.1 + uFlut.w * 7.0));
  ang += uFinMove2.y + uFinMove2.x * 0.36 * sin(6.2831853 * (phz * uFinMove.x + (sd > 0.0 ? 0.2 : 0.7)));
  // 左右ばらばらに、気まぐれに閉じたり（体に寄せる）広げたり
  ang -= uFinMove2.z * 0.45 * finWhim((sd > 0.0 ? 0.13 : 0.57) + uFlut.w * 3.1, uFinMove.x);
  ang = max(ang, 0.0);
  R = rotAxis(normalize(vec3(0.2, 1.0, 0.0)), sd * fw * ang);
} else if (part == 5.0) {
  // 腹びれ：閉じるとお腹に沿い、止まるときは前へ広げる
  float sd = sign(piv.z);
  float ang = mix(-0.12, 0.55, fs4.w) + 0.04 * sin(4.4 * uTime + seed);
  R = rotAxis(vec3(1.0, 0.0, 0.0), -sd * fw * ang);
} else if ((part == 1.0 || part == 2.0) && hasPiv) {
  // 背びれ・しりびれ：扇のように 1 本ずつ根元で後ろへ畳む
  R = rotAxis(vec3(0.0, 0.0, 1.0), _fin.z * (1.0 - fs4.z));
} else if (part == 3.0 && hasPiv) {
  // 尾びれ：振っていないときは少し閉じる
  R = rotAxis(vec3(0.0, 0.0, 1.0), _fin.z * 0.22 * (1.0 - clamp(amp * 1.5, 0.0, 1.0)));
} else if (part == 6.0 && hasPiv) {
  // 目：ばらばらに動き、曲がるときはそちらを見る。uLookAt なら、見ている人のほうの目が人を見る
  float sd = sign(piv.z);
  vec2 g = eyeGaze(seed * 7.13 + (sd > 0.0 ? 0.0 : 3.7));
  // 前後へ ±26°、上下へ ±14° まで
  float fwd = g.x * 0.9, up = g.y * 0.5, lw = 0.0;
  if (uLookAt > 0.0) {
    vec3 d = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz - piv;
    float side = d.z * sd, hz = length(vec2(d.x, side));
    lw = uLookAt * smoothstep(0.0, 0.35, side / max(length(d), 1e-4));
    fwd = mix(fwd, clamp(atan(d.x, side), -0.65, 0.65) + g.x * 0.2, lw);
    up = mix(up, clamp(atan(d.y, hz), -0.45, 0.45) + g.y * 0.1, lw);
  }
  float yaw = sd * fwd + clamp(bend * uLen, -1.0, 1.0) * 0.3 * (1.0 - lw);
  R = rotAxis(vec3(0.0, 1.0, 0.0), yaw) * rotAxis(vec3(1.0, 0.0, 0.0), -sd * up);
} else if (part == 7.0) {
  // えらぶた：前の縁（ちょうつがい）を軸に、後ろの縁ほど外へ開く（fw は前の縁からの距離。上の端は開かない）
  float sd = sign(fishP.z);
  fishP.z += sd * fw * sin(uGill);
  fishP.x += fw * (1.0 - cos(uGill));
  float ga = sd * uGill * clamp(fw / (0.05 * uLen), 0.0, 1.0);
  float gc = cos(ga), gs = sin(ga);
  objectNormal = vec3(objectNormal.x * gc + objectNormal.z * gs, objectNormal.y, -objectNormal.x * gs + objectNormal.z * gc);
}
// 目玉は uEyeBulge.x 倍の大きさにして、外へ uEyeBulge.y 押し出す（ぎょろっと出た目）
if (part == 6.0 && hasPiv) fishP = piv + (fishP - piv) * uEyeBulge.x + vec3(0.0, 0.0, sign(piv.z) * uEyeBulge.y);
if (part >= 1.0 && part <= 6.0) { fishP = piv + R * (fishP - piv); objectNormal = R * objectNormal; }
// 背びれ・しりびれ・腹びれを、胸びれのように筋肉で根元から動かす。付け根の線（体の表面）を軸に、
// 1 本ずつの骨を後ろへ倒して畳み（uFinMove.z）、ひれ全体を横へ傾ける（ひれごとにゆっくり、ばらばらに。舵の分 uFinMove.w も足す）
if (finH != 0.0 && part != 4.0 && flutter.z >= 0.0) {
  float mid = flutter.z;
  float mhz = mix(0.35, 0.8, fishHash(mid * 5.0 + uFlut.w * 11.0));
  float mph = 6.2831853 * (mhz * uFinMove.x + fishHash(mid * 3.0 + uFlut.w * 5.0));
  // 上のひれと下のひれで、舵は同じ側へ倒れるように向きをそろえる
  float side = finH > 0.0 ? 1.0 : -1.0;
  float tilt = side * (uFinMove.y * (sin(mph) + 0.5 * sin(2.3 * mph + 1.1)) + uFinMove.w);
  // 畳み具合：場面のねらい（uFinMove.z）に、ひれごとのゆっくりした開け閉め（uFinMove2.x）を重ねる
  float fhz = mix(0.2, 0.6, fishHash(mid * 9.0 + uFlut.w * 13.0));
  float fph = 6.2831853 * (fhz * uFinMove.x + fishHash(mid * 4.0 + uFlut.w * 3.0));
  float fold = uFinMove.z + uFinMove2.x * (0.7 * sin(fph) + 0.3 * sin(2.6 * fph + 0.8));
  // ひれごとの気まぐれな閉じ・広げ（場面とは関係なく）
  fold += uFinMove2.z * finWhim(mid + uFlut.w * 3.1, uFinMove.x);
  fold = clamp(fold, 0.0, 1.0) * uFinMove2.w;
  float h = abs(finH);
  vec3 base = vec3(fishP.x, fishP.y - finH, fishP.z);
  vec2 ray = vec2(-h * sin(fold), finH * cos(fold));
  fishP = base + vec3(ray.x, ray.y * cos(tilt), ray.y * sin(tilt));
  float tc = cos(tilt), ts = sin(tilt);
  objectNormal = vec3(objectNormal.x, objectNormal.y * tc - objectNormal.z * ts, objectNormal.y * ts + objectNormal.z * tc);
}
// ひれのはためき。どのひれも、付け根から縁へ大きくなる細かい波が前から後ろへ、上から下へ流れる。
// そのうえ旗のように、ひれごとに自分の速さとタイミングで、前から後ろへ波が流れて大きく振れる
// （体のうねりとも、ほかのひれともそろわない。縁と後ろほど大きく、前の縁はとげがあって硬い）。
// 胸びれはひれの面に垂直に、縦のひれは横（模型の Z）に揺らす
if (flutter.x > 0.0 && (uFlut.y > 0.0 || uFlut.z > 0.0)) {
  float fsF = (uSnout - fishP.x) / uLen;
  float arg = 6.2831853 * (2.5 * uFlut.x - fsF * 2.5 - fishP.y / uLen * 1.5);
  // 胸びれの縁の細かい揺れは、ほかのひれの 0.1 倍
  float fa = uLen * uFlut.y * pow(flutter.x, 1.5) * (part == 4.0 ? 0.1 : 1.0);
  float fz = fa * (sin(arg) + 0.35 * sin(1.7 * arg + 1.3));
  float dz = fa * (cos(arg) + 0.6 * cos(1.7 * arg + 1.3)) * 6.2831853 * 2.5 / uLen;
  // ひれの番号（胸びれは左右で別）。尾びれ（-1）は体のうねりで動くので旗にしない
  float fid = part == 4.0 ? (piv.z > 0.0 ? 0.31 : 0.77) : flutter.z;
  if (fid >= 0.0 && uFlut.z > 0.0) {
    float hz = mix(1.1, 2.3, fishHash(fid * 13.0 + uFlut.w * 31.0));
    float ph = 6.2831853 * (hz * uFlut.x + fishHash(fid * 7.0 + uFlut.w * 17.0 + 3.0) - flutter.y * 0.8 - flutter.x * 0.3);
    float W = flutter.x * (0.35 + 0.65 * flutter.y);
    float fl = uLen * uFlut.z * W * W * (part == 4.0 ? 0.6 : 1.0);
    // 速さの違う 2 つの波を重ねて、同じ振れを繰り返さないように
    fz += fl * (sin(ph) + 0.45 * sin(1.73 * ph + 2.1 + 6.2831853 * 0.37 * uFlut.x));
  }
  if (part == 4.0) fishP += objectNormal * fz;
  else {
    fishP.z += fz;
    objectNormal = normalize(vec3(objectNormal.x - dz * objectNormal.z, objectNormal.y, objectNormal.z));
  }
}
// 口：下あご（部位 8 の板と、jaw.x の重みの体）は、口の角の後ろ下の関節（uMouthShape.xy）を軸に回る。写真は口が開いているので、
// ふだんは uMouthClose だけ上へ回して閉じ、uMouth だけ開く（いちばん開いて写真の形）
float jw = part == 8.0 ? 1.0 : part == 0.0 ? jaw.x : 0.0;
if (jw > 0.0) {
  float ja = (uMouthClose - min(uMouth, uMouthClose + 0.35)) * jw;
  if (ja != 0.0) {
    vec2 hp = fishP.xy - uMouthShape.xy;
    float jc = cos(ja), js = sin(ja);
    fishP.xy = uMouthShape.xy + vec2(hp.x * jc - hp.y * js, hp.x * js + hp.y * jc);
    objectNormal.xy = vec2(objectNormal.x * jc - objectNormal.y * js, objectNormal.x * js + objectNormal.y * jc);
  }
}
// 上あご（部位 9 の板）は、口先の付け根（uMouthUpper.xy）を軸に、ふだんは uMouthUpper.z だけ後ろ上へ回して頬に沿わせる
// （口を閉じた写真の種類は 0 で写真のまま）。口を開くほど前下へ出て、uMouthUpper2.y まで開くと uMouthUpper2.x だけ回る
// （シーバスは写真の形。少し開くだけのときはほとんど動かない）。口を閉じた写真の種類は回さずに、uMouthUpper2.w だけ前下へすべり出る
if (part == 9.0) {
  float uo = clamp(uMouth / uMouthUpper2.y, 0.0, 1.0);
  float ua = uMouthUpper2.x * uo * uo - uMouthUpper.z;
  fishP.xy += vec2(0.94, -0.34) * uMouthUpper2.w * uo * uo;
  vec2 hp = fishP.xy - uMouthUpper.xy;
  float uc = cos(ua), us = sin(ua);
  fishP.xy = uMouthUpper.xy + vec2(hp.x * uc - hp.y * us, hp.x * us + hp.y * uc);
  objectNormal.xy = vec2(objectNormal.x * uc - objectNormal.y * us, objectNormal.x * us + objectNormal.y * uc);
}
float fs = (uSnout - fishP.x) / uLen;
// 首：頭のすぐ後ろ（uNeck.y〜z）でなめらかに曲げ、それより後ろを頭に対して uNeck.x rad 戻す（口先は動かさない）
if (uNeck.x != 0.0) {
  float psi = -uNeck.x * smoothstep(uNeck.y, uNeck.z, fs);
  float S = neckInt(fs, uNeck.y, uNeck.z);
  float nc = cos(psi), ns = sin(psi);
  fishP.x += uLen * 0.5 * uNeck.x * uNeck.x * S + fishP.z * ns;
  fishP.z = -uLen * uNeck.x * S + fishP.z * nc;
  objectNormal = vec3(objectNormal.x * nc + objectNormal.z * ns, objectNormal.y, -objectNormal.x * ns + objectNormal.z * nc);
}
float fd = (lieH(fs + 0.002, cyc, amp) - lieH(fs - 0.002, cyc, amp)) / 0.004 * (-1.0 / uLen);
// 曲がるときは、重心（口先から 35%）のまわりで体全体が弧になる
float bx = (fs - 0.35) * uLen;
fishP.z += lieH(fs, cyc, amp) + 0.5 * bend * bx * bx;
fd += bend * bx * (-1.0);
// 首振りの C 字：同じ弧で、口先の所は動かさない
float sx = 0.35 * uLen;
fishP.z += 0.5 * uNeck.w * (bx * bx - sx * sx);
fd -= uNeck.w * bx;
objectNormal = normalize(vec3(objectNormal.x - fd * objectNormal.z, objectNormal.y, objectNormal.z));
`;
/**
* 細かい形の魚（掛かった魚・図鑑・釣れたときの見本）のつや。昼と夜で別の値（夜はヘッドライトが近くから当たる）。
* fish.html の「モデル」の「つや」で、昼・夜の明かりの下で試せる。
* - rough：体のつやの広がり（0 でつるつる、1 でつやなし。目はいつもつやがある）
* - spec：光（太陽・月・ヘッドライト・街灯）の照り返しの強さの倍率
* - env：まわりの景色（空）の映り込みの強さの倍率
*/
var FISH_LOOK = {
	day: {
		rough: .6,
		spec: 1,
		env: 0
	},
	night: {
		rough: .6,
		spec: 1,
		env: 0
	}
};
/** すべての細かい形の魚の材質で同じものを使う（値を変えると、どの魚にもすぐ効く） */
var lookU = {
	uRough: { value: FISH_LOOK.day.rough },
	uSpecK: { value: FISH_LOOK.day.spec },
	uEnvK: { value: FISH_LOOK.day.env },
	/** 開いた口の中の暗さ（光の明るさに掛ける。奥まっていて光が入りにくい分） */
	uMouthIn: { value: .4 }
};
/** instanced：まとめて描く軽い固定版（FishBatches）のシェーダーにする */
function swimMaterial(a, instanced = false) {
	const { map, swim, gill, mouth, eye, photos, headMap } = a;
	const env = swim.env ?? [
		.02,
		-.08,
		.16
	];
	const u = {
		uTime: { value: 0 },
		uSnout: { value: swim.snout },
		uLen: { value: swim.length },
		uLam: { value: swim.lambda },
		uSwimAmp: { value: swim.amp },
		uEnv: { value: new THREE.Vector3(...env) },
		uBreath: { value: .004 * swim.length },
		uPectRest: { value: swim.pect_rest ?? 0 },
		uLookAt: { value: 0 },
		uFloor: { value: 0 },
		uHead: { value: 1 },
		uPower: { value: 0 },
		uNeck: { value: new THREE.Vector4(0, .23, .43, 0) },
		uFlut: { value: new THREE.Vector4(0, 0, 0, 0) },
		uFinMove: { value: new THREE.Vector4(0, 0, 0, 0) },
		uFinMove2: { value: new THREE.Vector4(0, 0, 0, a.foldMax) },
		uSwim: { value: new THREE.Vector4(0, 1, 0, .1) },
		uFin: { value: new THREE.Vector4(0, 0, .3, .2) },
		uGill: { value: 0 },
		uGillEdge: { value: padLine(gill?.edge, GILL_EDGE_N) },
		uGillHinge: { value: padLine(gill?.hinge, GILL_HINGE_N) },
		uGillShape2: { value: gill ? new THREE.Vector4(gill.top, gill.bottom, 1, 0) : new THREE.Vector4() },
		uGillBox: { value: gill ? new THREE.Vector2(Math.min(...gill.edge.map((p) => p[1])) - .006, Math.max(...gill.hinge.map((p) => p[1]))) : new THREE.Vector2() },
		uMouth: { value: 0 },
		uMouthShape: { value: mouth ? new THREE.Vector4(mouth.joint[0], mouth.joint[1], ...mouthCutX(mouth)) : new THREE.Vector4() },
		uMouthEdge: { value: padXY(mouth && mouth.close === 0 ? mouth.lowerLip : mouth?.jawEdge, MOUTH_N) },
		uMouthUpper: { value: mouth ? new THREE.Vector4(mouth.upperPivot[0], mouth.upperPivot[1], mouth.upperClose, mouth.photoClose) : new THREE.Vector4() },
		uMouthUpper2: { value: mouth ? mouth.close > 0 ? new THREE.Vector4(mouth.upperOpen ?? mouth.upperClose, mouth.close, 1, 0) : new THREE.Vector4(0, .4, 0, .6 * (mouth.upperOpen ?? 0) * Math.hypot(mouth.upperPivot[0] - mouth.lowerLip[0][0], mouth.upperPivot[1] - mouth.lowerLip[0][1])) : new THREE.Vector4(0, 1, 0, 0) },
		uMouthUpperPoly: { value: padXY(mouth?.upper, UPPER_N) },
		uMouthLip: { value: padXY(mouth?.lowerLip, MOUTH_N) },
		uMouthOn: { value: mouth ? 1 : 0 },
		uMouthClose: { value: mouth?.close ?? 0 },
		uEye: { value: eye ? new THREE.Vector4(eye.x, eye.y, eye.z, 1) : new THREE.Vector4() },
		uEyeBulge: { value: eye ? new THREE.Vector2(1.1, .0012) : new THREE.Vector2(1, 0) },
		uHeadOn: { value: photos ? 1 : 0 },
		uHeadTex: { value: photos?.head ?? blankTexture() },
		uCoverTex: { value: photos?.cover ?? blankTexture() },
		uHeadMap: { value: new THREE.Vector4(headMap.x0, headMap.z0, headMap.k, swim.photo ? 1 : 0) },
		uHeadBox: { value: new THREE.Vector4(...headMap.box) }
	};
	if (instanced) return {
		material: lightSwimMaterial(map, u),
		uniforms: u
	};
	const m = new THREE.MeshStandardMaterial({
		map,
		roughness: .4,
		metalness: 0,
		side: THREE.DoubleSide,
		alphaTest: .5
	});
	m.onBeforeCompile = (sh) => {
		Object.assign(sh.uniforms, u, lookU);
		sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\n" + SWIM_HEAD).replace("#include <beginnormal_vertex>", SWIM_BODY).replace("#include <begin_vertex>", "vec3 transformed = fishP;");
		sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\n" + GILL_FRAG_HEAD + "\nuniform float uRough, uSpecK, uEnvK, uMouthIn;").replace("#include <map_fragment>", "#include <map_fragment>\n" + PHOTO_FRAG + GILL_FRAG + FACE_FRAG).replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = uRough;\nif (vPart > 5.5 && vPart < 6.5) roughnessFactor = 0.07;\nif (vRim > 0.5 || (!gl_FrontFacing && (vPart < 0.5 || vPart > 7.5))) roughnessFactor = 0.9;").replace("#include <normal_fragment_maps>", "#include <normal_fragment_maps>\nif (vPart < 0.5) roughnessFactor = mix(1.0, roughnessFactor, smoothstep(0.1, 0.6, abs(dot(normal, normalize(vViewPosition)))));").replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\nif (vPart < 0.5) { float graze = smoothstep(0.05, 0.45, abs(dot(normal, normalize(vViewPosition)))); reflectedLight.indirectSpecular *= graze; reflectedLight.directSpecular *= graze; }\nreflectedLight.directSpecular *= uSpecK; reflectedLight.indirectSpecular *= uEnvK;").replace("#include <opaque_fragment>", "if (uMouthOn > 0.5 && !gl_FrontFacing && (vPart < 0.5 || vPart > 7.5)) outgoingLight = (reflectedLight.directDiffuse + reflectedLight.indirectDiffuse) * uMouthIn;\n#include <opaque_fragment>");
	};
	if (instanced) m.defines = { FISH_INSTANCED: "" };
	m.customProgramCacheKey = () => instanced ? "photo-fish-instanced" : "photo-fish";
	return {
		material: m,
		uniforms: u
	};
}
/**
* 群れの魚（掛かっていない魚。種類ごとにまとめて描く）の材質。魚が集まって画面を広く覆うと、1 画素ごとの計算が効くので軽くする：
* - 光は明るさだけの安い計算（Lambert）。照り返し（つや）とまわりの景色の映り込み（環境マップ）はなし
*   （掛かった魚も、つやは広く弱く、映り込みなし：FISH_LOOK）
* - 目のまわりの陰は省く（FACE_FRAG）。泳ぎ・頭の写真・えらと口（止めてある）は、ふつうの魚と同じ
* 掛かった魚・図鑑・釣れたときの見本は、ふつうの材質（swimMaterial の MeshStandardMaterial）のまま
*/
var LIGHT_LOOK = { 
/** 掛かった魚と同じくらいの明るさになるよう、空と地面からの明るさ（半球の光）を何倍にするか */
ambient: .97 };
function lightSwimMaterial(map, u) {
	const lu = {
		...u,
		uAmbL: { value: LIGHT_LOOK.ambient }
	};
	const m = new THREE.MeshLambertMaterial({
		map,
		side: THREE.DoubleSide,
		alphaTest: .5
	});
	m.onBeforeCompile = (sh) => {
		Object.assign(sh.uniforms, lu);
		sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\n" + SWIM_HEAD).replace("#include <beginnormal_vertex>", SWIM_BODY).replace("#include <begin_vertex>", "vec3 transformed = fishP;");
		sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\n" + GILL_FRAG_HEAD + "\nuniform float uAmbL;").replace("#include <map_fragment>", "#include <map_fragment>\n" + PHOTO_FRAG + GILL_FRAG + FACE_FRAG).replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\nreflectedLight.indirectDiffuse *= uAmbL;");
	};
	m.defines = { FISH_INSTANCED: "" };
	m.customProgramCacheKey = () => "photo-fish-instanced-light";
	return m;
}
/**
* 水の上から見ても魚の形と動きが分かる影。体と同じ形・同じ泳ぎ（同じ uniform）で、水面より後に暗く平らに塗る。
* 深さを比べて、魚のいちばん手前の面だけに塗る（体の裏やひれが重なって濃くならない。手前に岩や岸壁があれば隠れる）。
* 明るさを足すと、空を映した白い水面の上で見えなくなるので、暗い色で上から塗る
*/
function shadowMaterial(map, u, instanced = false) {
	const m = new THREE.MeshBasicMaterial({
		map,
		side: THREE.DoubleSide,
		alphaTest: .5,
		transparent: true,
		depthWrite: false,
		polygonOffset: true,
		polygonOffsetFactor: -2,
		polygonOffsetUnits: -4
	});
	m.onBeforeCompile = (sh) => {
		Object.assign(sh.uniforms, u);
		sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\n" + SWIM_HEAD + "\nvarying float vShadeI;").replace("#include <begin_vertex>", SWIM_BODY + "\nvec3 transformed = fishP;\n#ifdef FISH_INSTANCED\nvShadeI = iMisc.z;\n#else\nvShadeI = 1.0;\n#endif");
		sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nuniform float uShade;\nuniform vec3 uShadeColor;\nvarying float vShadeI;").replace("#include <opaque_fragment>", "if (vShadeI < 0.005) discard;\ngl_FragColor = vec4(uShadeColor, uShade * vShadeI);");
	};
	if (instanced) m.defines = { FISH_INSTANCED: "" };
	m.customProgramCacheKey = () => instanced ? "photo-fish-shadow-instanced" : "photo-fish-shadow";
	return m;
}
var GILL_FRAG_HEAD = `
uniform vec4 uGillShape2, uEye;
uniform vec2 uGillBox;
uniform vec2 uGillEdge[${GILL_EDGE_N}];
uniform vec2 uGillHinge[${GILL_HINGE_N}];
// 折れ線 (y, x) の、高さ y での x（下から順に並んだ点を直線でつなぐ。端より外は端の x）
float gillEdgeX(float y) {
  float x = uGillEdge[0].y;
  for (int i = 0; i < 39; i++) {
    vec2 a = uGillEdge[i], b = uGillEdge[i + 1];
    if (y >= a.x && y <= b.x && b.x > a.x) x = mix(a.y, b.y, (y - a.x) / (b.x - a.x));
  }
  return y > uGillEdge[39].x ? uGillEdge[39].y : x;
}
float gillHingeX(float y) {
  float x = uGillHinge[0].y;
  for (int i = 0; i < 39; i++) {
    vec2 a = uGillHinge[i], b = uGillHinge[i + 1];
    if (y >= a.x && y <= b.x && b.x > a.x) x = mix(a.y, b.y, (y - a.x) / (b.x - a.x));
  }
  return y > uGillHinge[39].x ? uGillHinge[39].y : x;
}
uniform float uGill, uMouth, uMouthOn, uMouthClose, uHeadOn;
uniform vec4 uMouthShape, uMouthUpper, uHeadMap, uHeadBox;
uniform vec4 uMouthUpper2;
uniform sampler2D uHeadTex, uCoverTex;
// 模型の (x, y)［m］→ 頭の写真の uv（写真の画素 = (x0 − x·k, z0 − y·k)、そこから切り出した範囲の中の割合）
vec2 headUv(vec2 p) { return (vec2(uHeadMap.x - p.x * uHeadMap.z, uHeadMap.y - p.y * uHeadMap.z) - uHeadBox.xy) / uHeadBox.zw; }
float headIn(vec2 uv) { return step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0); }
uniform vec2 uMouthEdge[${MOUTH_N}];
uniform vec2 uMouthLip[${MOUTH_N}];
uniform vec2 uMouthUpperPoly[${UPPER_N}];
// 上あごの多角形の中か
bool inUpperJaw(vec2 p) {
  bool inside = false;
  for (int i = 0; i < ${UPPER_N}; i++) {
    vec2 a = uMouthUpperPoly[i], b = uMouthUpperPoly[i == 0 ? 19 : i - 1];
    if ((a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
// 折れ線 (x, y) の、x での y（端より外は端の y）
float mouthLineY(vec2 l[${MOUTH_N}], float x) {
  float y = l[0].y;
  for (int i = 0; i < 7; i++) if (x >= l[i].x && x <= l[i + 1].x && l[i + 1].x > l[i].x) y = mix(l[i].y, l[i + 1].y, (x - l[i].x) / (l[i + 1].x - l[i].x));
  return x > l[7].x ? l[7].y : y;
}
varying vec3 vModel;
varying float vPart;
varying float vRim;
`;
var PHOTO_FRAG = `
if (uHeadOn > 0.5) {
  if (vPart < 0.5 && gl_FrontFacing) {
    vec2 hp = headUv(vModel.xy);
    vec4 hd = texture2D(uHeadTex, hp);
    // えらぶたの板があるのは前の縁のいちばん前（uGillBox.y）より後ろ（前へのびた細い所は板にしていないので、えらの写真を出さない）
    float under = step(0.5, texture2D(uCoverTex, hp).a) * step(vModel.x, uGillBox.y);
    diffuseColor.rgb = mix(diffuseColor.rgb, hd.rgb, under * hd.a * headIn(hp));
  }
  if (uHeadMap.w > 0.5 && vPart > 5.5 && vPart < 6.5) {
    // 目玉：もとの写真の目を、横からまっすぐ写す（動かす前の位置で読むので、目玉と一緒に回る）
    vec2 hp = headUv(vModel.xy);
    vec4 hd = texture2D(uHeadTex, hp);
    diffuseColor.rgb = mix(diffuseColor.rgb, hd.rgb, hd.a * headIn(hp));
  }
  if (vPart > 6.5 && vPart < 7.5 && gl_FrontFacing && vRim < 0.5) {
    vec2 hp = headUv(vModel.xy);
    vec4 cv = texture2D(uCoverTex, hp);
    diffuseColor.rgb = mix(diffuseColor.rgb, cv.rgb, cv.a * headIn(hp));
  }
  if (vPart > 7.5 && vPart < 8.5 && gl_FrontFacing && vRim < 0.5) {
    vec2 d = vModel.xy - uMouthShape.xy;
    float c = cos(uMouthUpper.w), s = sin(uMouthUpper.w);
    vec2 hp = headUv(uMouthShape.xy + vec2(d.x * c - d.y * s, d.x * s + d.y * c));
    vec4 hd = texture2D(uHeadTex, hp);
    // 関節の近く（8mm）は元の写真へなじませる（後ろの体と板の境目を見せない）
    diffuseColor.rgb = mix(diffuseColor.rgb, hd.rgb, hd.a * headIn(hp) * smoothstep(uMouthShape.x, uMouthShape.x + 0.008, vModel.x));
  }
}
`;
var FACE_FRAG = `
if (uMouthOn > 0.5) {
  float mx = vModel.x;
  // 口の中（下唇の線と上あごの骨の縁の間）と、上あごの板を切り抜いた所は抜く。下唇の線より 3mm 下まで（そこは下あごの板の裏で、
