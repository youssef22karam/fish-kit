	const a = assets.get(id);
	if (!a) return null;
	if (batches) return buildBatchedFish(id, a, length, batches);
	const { material, uniforms } = swimMaterial(a);
	const root = new THREE.Group();
	const lod = new THREE.LOD();
	const s = length / a.swim.length;
	lod.scale.setScalar(s);
	lod.rotation.y = -Math.PI / 2;
	lod.position.z = s * (.47 * a.swim.length - a.swim.snout);
	const shadeU = {
		...uniforms,
		uShade: { value: 0 },
		uShadeColor: { value: new THREE.Color(397332) }
	};
	const shadowMat = shadowMaterial(a.map, shadeU);
	const shadows = [];
	const level = (geo) => {
		const mesh = new THREE.Mesh(geo, material);
		const sh = new THREE.Mesh(geo, shadowMat);
		sh.renderOrder = 3;
		sh.visible = false;
		mesh.add(sh);
		shadows.push(sh);
		return mesh;
	};
	lod.addLevel(level(a.hi), 0);
	const loDist = 2.5 + length * 8;
	if (a.lo) lod.addLevel(level(a.lo), loDist, .1);
	root.add(lod);
	const env = a.swim.env ?? [
		.02,
		-.08,
		.16
	];
	const tipEnv = env[0] + env[1] + env[2];
	let lastPhase = 0;
	let flap = Math.random();
	return {
		root,
		shadows,
		/** 細かい形を使うか。false なら粗い形に切り替わる距離を 0 にして、近くでも粗い形で描く */
		detail(on) {
			const l = lod.levels[1];
			if (l) l.distance = on ? loDist : 0;
		},
		/** 水の上から見える影の濃さ 0〜1（0 で出さない） */
		shade(opacity) {
			shadeU.uShade.value = opacity;
			for (const s of shadows) s.visible = opacity > .005;
		},
		/** time：目を動かす時計 秒（省けばいまの時刻。配布用の魚のキットはスローにするとき自分の時計を渡す） */
		swim(phase, amp, bend = 0, time = performance.now() / 1e3) {
			const cyc = phase / (Math.PI * 2);
			const slow = THREE.MathUtils.clamp(1 - (amp - .04) / .06, 0, 1);
			flap += Math.max(0, cyc - lastPhase) * .8;
			lastPhase = cyc;
			uniforms.uTime.value = time;
			uniforms.uSwim.value.set(cyc, amp / (a.swim.amp * tipEnv), THREE.MathUtils.clamp(bend, -4, 4) * s, a.still ? 0 : .03 + slow * .08);
			if (a.still) uniforms.uFin.value.set(0, 0, 1, 0);
			else uniforms.uFin.value.set(flap, slow * .3, .15 + slow * .6, slow * .5);
		},
		/** 床に横たわっている：模型の横（+Z）が上を向いている度合い -1〜1（0 は床なし）。体を床へは曲げない */
		lieOnFloor(up) {
			uniforms.uFloor.value = up;
		},
		/** 見ている人を目で追う度合い 0〜1（釣り上げられた魚） */
		lookAtViewer(amount) {
			uniforms.uLookAt.value = amount;
		},
		/**
		* ひれを根元から動かす：時計 秒、横へ傾ける振れ rad、後ろへ畳む度合い 0〜1、舵の角度 rad、
		* ひれごとにゆっくり開け閉めする振れ 0〜1、胸びれを開く角度 rad、ひれごとに気まぐれに閉じたり広げたりする大きさ 0〜1
		*/
		finMove(clock, tilt, fold, steer, wobble = 0, pect = 0, whim = 0) {
			if (a.still) return;
			uniforms.uFinMove.value.set(clock, tilt, fold, steer);
			uniforms.uFinMove2.value.set(wobble, pect, whim, a.foldMax);
		},
		/** 下あごを開く角度 rad（口の形を決めてある種類だけ） */
		mouth(open) {
			uniforms.uMouth.value = a.mouth ? open : 0;
		},
		mouthMax: a.mouth ? a.mouth.close + .35 : 0,
		/** えらぶたを開く角度 rad（えらぶたを作ってある種類だけ） */
		gill(open) {
			uniforms.uGill.value = a.gill ? open : 0;
		},
		/** ひれのはためき：ひれの時計 秒、縁の細かい揺れと旗のような振れ（体長に対して）、1 匹ごとの乱数 0〜1 */
		flutter(clock, amp, flag = 0, seed = 0) {
			if (a.still && !a.tailFlutter) return;
			uniforms.uFlut.value.set(clock, amp, flag, seed);
		},
		/** 首で曲げる角度 rad（from〜to で）、首振りの C 字の曲がり 1/m、泳ぐときの頭の振れの倍率、体全体を使って泳ぐ度合い 0〜1 */
		flex(neck, from, to, cBend, head, power = 0) {
			uniforms.uNeck.value.set(neck, from, to, THREE.MathUtils.clamp(cBend, -6, 6) * s);
			uniforms.uHead.value = head;
			uniforms.uPower.value = power;
		}
	};
}
// fish-species.js
var ALL_SPECIES = [
	{
		"name": "アジ",
		"id": "aji",
		"en": "Horse Mackerel",
		"lengthCm": [16, 48],
		"bodyHeight": .25,
		"cruise": .4,
		"burst": 2,
		"glide": .35,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "メバル",
		"id": "mebaru",
		"en": "Rockfish",
		"lengthCm": [17, 33],
		"bodyHeight": .32,
		"cruise": .25,
		"burst": 1.5,
		"glide": .5,
		"hoverPitch": .35,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "カサゴ",
		"id": "kasago",
		"en": "Scorpionfish",
		"lengthCm": [15, 33],
		"bodyHeight": .3,
		"cruise": .15,
		"burst": 1.2,
		"glide": .9,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "シーバス",
		"id": "seabass",
		"en": "Seabass",
		"lengthCm": [50, 95],
		"bodyHeight": .24,
		"cruise": .6,
		"burst": 3.5,
		"glide": .3,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "サバ",
		"id": "saba",
		"en": "Mackerel",
		"lengthCm": [20, 40],
		"bodyHeight": .2,
		"cruise": .6,
		"burst": 4,
		"glide": .25,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "タチウオ",
		"id": "tachiuo",
		"en": "Cutlassfish",
		"lengthCm": [65, 145],
		"bodyHeight": .07,
		"cruise": .3,
		"burst": 2.5,
		"glide": .6,
		"hoverPitch": 0,
		"upright": 1.31,
		"maxBend": .08,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "サワラ",
		"id": "sawara",
		"en": "Spanish Mackerel",
		"lengthCm": [50, 100],
		"bodyHeight": .16,
		"cruise": .8,
		"burst": 4.5,
		"glide": .25,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "カマス",
		"id": "kamasu",
		"en": "Barracuda",
		"lengthCm": [22, 46],
		"bodyHeight": .13,
		"cruise": .5,
		"burst": 3,
		"glide": .3,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "ブリ",
		"id": "buri",
		"en": "Yellowtail",
		"lengthCm": [40, 100],
		"bodyHeight": .22,
		"cruise": .9,
		"burst": 5,
		"glide": .25,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "ヒラマサ",
		"id": "hiramasa",
		"en": "Kingfish",
		"lengthCm": [50, 110],
		"bodyHeight": .21,
		"cruise": 1,
		"burst": 5.5,
		"glide": .25,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "マゴチ",
		"id": "magochi",
		"en": "Flathead",
		"lengthCm": [35, 65],
		"bodyHeight": .12,
		"cruise": .15,
		"burst": 2.5,
		"glide": .85,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "クロダイ",
		"id": "kurodai",
		"en": "Black Sea Bream",
		"lengthCm": [28, 65],
		"bodyHeight": .38,
		"cruise": .35,
		"burst": 2.5,
		"glide": .5,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "マダイ",
		"id": "madai",
		"en": "Red Sea Bream",
		"lengthCm": [28, 90],
		"bodyHeight": .38,
		"cruise": .4,
		"burst": 3,
		"glide": .5,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "キハダ",
		"id": "kihada",
		"en": "Yellowfin Tuna",
		"lengthCm": [126, 150],
		"bodyHeight": .25,
		"cruise": 1.3,
		"burst": 7,
		"glide": .15,
		"hoverPitch": 0,
		"finFlutter": .006,
		"finFlag": .025,
		"finMove": 1
	},
	{
		"name": "イサキ",
		"id": "isaki",
		"en": "Chicken Grunt",
		"lengthCm": [22, 45],
		"bodyHeight": .27,
		"cruise": .4,
		"burst": 2.2,
		"glide": .4,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "尾長グレ",
		"id": "onagagure",
		"en": "Largescale Blackfish",
		"lengthCm": [30, 62],
		"bodyHeight": .36,
		"cruise": .4,
		"burst": 3.2,
		"glide": .4,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "口太グレ",
		"id": "kuchibuto",
		"en": "Opaleye",
		"lengthCm": [25, 52],
		"bodyHeight": .38,
		"cruise": .35,
		"burst": 2.6,
		"glide": .45,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "シブダイ",
		"id": "shibudai",
		"en": "Star Snapper",
		"lengthCm": [40, 60],
		"bodyHeight": .33,
		"cruise": .35,
		"burst": 2.8,
		"glide": .5,
		"hoverPitch": 0,
		"finFlutter": .008,
		"finFlag": .035,
		"finMove": 1
	},
	{
		"name": "カタクチイワシ",
		"id": "katakuchi",
		"en": "Anchovy",
		"lengthCm": [8, 15],
		"bodyHeight": .17,
		"cruise": .4,
		"burst": 1.8,
		"glide": .2,
		"hoverPitch": 0
	}
];
var RESERVE_SPECIES = [];
var recordKey = (sp) => sp.name;
// src/game/fish/swim-style.ts
/** えらぶたをいちばん開く角度 rad（Codex に教えてもらった目安の、大きく開くときの上の 20°） */
var GILL_MAX = .35;
/** 呼吸の速さ 回/秒（どの場面でも同じ間で、えらと口を開け閉めし続ける） */
var BREATH_HZ = .8;
/**
* ゲームのしなり方（fish.html でシーバスを見比べて決めた）。首振りは頭のすぐ後ろ（口先から 4 割）でよく曲げ、
* 体全体も C 字に大きくしならせる。尾は首振りに合わせない。泳ぐときの頭の左右の揺れは小さく（写真の値の 2 割）
*/
var GAME_STYLE = {
	neckFlex: .65,
	neckAt: .4,
	bodyBend: 1.5,
	tailLock: 0,
	tailOffset: 0,
	recoil: .2,
	flutter: 1,
	flag: 1,
	finMove: 1,
	finWhim: .55,
	gill: 1,
	mouth: 1,
	burst: 1,
	airAmp: .35,
	airFreq: .5,
	airGill: 1.5,
	airMouth: 1.5
};
// src/kit/fish-kit.ts
var MOTIONS = [
	{
		id: "swim",
		ja: "ゆったり泳ぐ",
		en: "Cruise",
		noteJa: "ふだんの速さ。ゆっくりの魚は尾を数回振っては体をまっすぐにして滑るのをくり返す",
		noteEn: "Everyday cruising speed. Slow species beat the tail a few times, then glide with a straight body.",
		onLine: false
	},
	{
		id: "power",
		ja: "全速で泳ぐ",
		en: "Full speed",
		noteJa: "その魚のいちばん速い泳ぎ。頭から尾まで体全体を大きくうねらせ、ひれを畳む",
		noteEn: "Top speed. The whole body undulates from head to tail and the fins fold back.",
		onLine: false
	},
	{
		id: "turn",
		ja: "曲がる",
		en: "Turning",
		noteJa: "左右へゆっくり向きを変えながら泳ぐ。体が曲がる側へ弧になり、ひれを舵のように傾ける",
		noteEn: "Swims while slowly turning left and right. The body arcs into the turn and the fins steer.",
		onLine: false
	},
	{
		id: "hover",
		ja: "止まる",
		en: "Hover",
		noteJa: "その場に止まって呼吸する。胸びれで漕ぎ、目がきょろきょろ動く（メバルは頭を上げ、タチウオは立ち泳ぎ）",
		noteEn: "Holds still and breathes, sculling with the pectoral fins while the eyes dart around (some species tilt up or stand vertical).",
		onLine: false
	},
	{
		id: "range",
		ja: "口・えら・ひれを開く",
		en: "Full range",
		noteJa: "4 秒に 1 回、口とえらぶたをいっぱいに開け、ひれを大きく広げてから体にぴったり畳む（動かせる範囲の見本）",
		noteEn: "Every 4 s the mouth and gill covers open fully and the fins spread wide, then everything closes and folds flat (range-of-motion demo).",
		onLine: false
	},
	{
		id: "bite",
		ja: "くわえて首を振る",
		en: "Bite & shake",
		noteJa: "ルアーをくわえて小さく首を振る。首で曲げ、体も C 字にしなる",
		noteEn: "Holds a lure and shakes its head gently, bending at the neck with a C-shaped body.",
		onLine: true
	},
	{
		id: "hooked",
		ja: "掛かって暴れる",
		en: "Hooked fight",
		noteJa: "針に掛かり、大きく首を振って粘る。ひれをいっぱいに広げる",
		noteEn: "Hooked and fighting with big head shakes, fins spread wide.",
		onLine: true
	},
	{
		id: "tired",
		ja: "弱って横倒し",
		en: "Exhausted",
		noteJa: "力が抜けて横に倒れ、尾をゆっくり小さく振る",
		noteEn: "Worn out, rolls onto its side and beats the tail slowly.",
		onLine: true
	},
	{
		id: "air",
		ja: "空中で暴れる",
		en: "Out of water",
		noteJa: "抜き上げられて糸にぶら下がり、尾を振ってねじれる。えらと口を大きくあえがせ、目がこちらを見る",
		noteEn: "Lifted out on the line: hangs head-up, twists and kicks, gasps with mouth and gills, and looks at you.",
		onLine: true
	},
	{
		id: "landed",
		ja: "床で跳ねる",
		en: "Flopping",
		noteJa: "床に横たわってピチピチ跳ねる。はじめは強く、だんだん弱く（2.4 秒ごとにくり返す）",
		noteEn: "Lies on its side on the deck and flops, strong at first then weaker (repeats every 2.4 s).",
		onLine: false
	}
];
var ON_LINE = /* @__PURE__ */ new Set([
	"bite",
	"hooked",
	"tired",
	"air"
]);
/** イサキの幼魚は種類ではなく、イサキの小さい個体の姿（species.ts の young） */
var YOUNG = { isaki_young: {
	of: "isaki",
	ja: "イサキ（幼魚）",
	en: "Grunt (juvenile)",
	lengthCm: [15, 28]
} };
var speciesById = (id) => [...ALL_SPECIES, ...RESERVE_SPECIES].find((s) => s.id === id);
function paramsOf(id) {
	const sp = speciesById(YOUNG[id]?.of ?? id);
	return {
		cruise: sp.cruise,
		burst: sp.burst,
		glide: sp.glide,
		hoverPitch: sp.hoverPitch,
		upright: sp.upright ?? 0,
		maxBend: sp.maxBend ?? .15,
		finFlutter: sp.finFlutter ?? 0,
		finFlag: sp.finFlag ?? 0,
		finMove: sp.finMove ?? 0,
		bodyHeight: sp.bodyHeight
	};
}
/** 写真の魚がある種類の一覧 */
var FISH = Object.entries(photoFishFiles()).flatMap(([id, file]) => {
	const y = YOUNG[id];
	if (y) return [{
		id,
		file,
		ja: y.ja,
		en: y.en,
		lengthCm: y.lengthCm,
		typicalCm: (y.lengthCm[0] + y.lengthCm[1]) / 2
	}];
	const sp = speciesById(id);
	if (!sp) return [];
	const lengthCm = [sp.lengthCm[0], sp.lengthCm[1]];
	return [{
		id,
		file,
		ja: recordKey(sp, false),
		en: sp.en,
		lengthCm,
		typicalCm: Math.round((lengthCm[0] + lengthCm[1]) / 2 * 10) / 10
	}];
});
/**
* 魚の形を読み込む。baseUrl は glb と webp の置き場所（末尾の / まで。例 './fish/'）か、
* ファイル名（'aji.glb'、'aji_head.webp' など）から URL を返す関数（data: URL や blob: URL を返してもよい）。
* ids を省けば全部。読み込めなかった種類は createFish が null を返す
*/
async function loadFish(baseUrl, ids) {
	await loadPhotoFish(baseUrl, {
		only: ids,
		fixed: false
	});
}
/**
* glb ファイルの三角形の数とテクスチャの大きさ（読み込んでいなければ null）。
* 描くときは、読み込むときに切り出すえらぶた・あごの板と、ひれの付け根の分が足されて 2〜3 倍になる
*/
function fishStats(id) {
	const i = photoFishInfo(id);
	return i ? {
		hiTris: i.file.hi,
		loTris: i.file.lo,
		texture: i.texture
	} : null;
}
var rand = (a, b) => a + (b - a) * Math.random();
var clamp = THREE.MathUtils.clamp;
var smooth = THREE.MathUtils.smoothstep;
var AXIS_X = new THREE.Vector3(1, 0, 0);
var AXIS_Y = new THREE.Vector3(0, 1, 0);
var AXIS_Z = new THREE.Vector3(0, 0, 1);
/** 口先は体の真ん中から体長の 47% 前 */
var MOUTH = .47;
/** 水の外で、こちらを見ている間（2〜4 秒）と、きょろきょろ見回す間（0.8〜2 秒）をくり返す（fish-mesh.ts の ViewerGaze） */
var Gaze = class {
	on = true;
	left = 1 + Math.random() * 2;
	amount = 0;
	update(dt) {
		this.left -= dt;
		if (this.left <= 0) {
			this.on = !this.on;
			this.left = this.on ? 2 + Math.random() * 2 : .8 + Math.random() * 1.2;
		}
		this.amount += ((this.on ? 1 : 0) - this.amount) * Math.min(1, dt * 6);
		return this.amount;
	}
};
/** 首振りの大きさ rad（ゲームでは、くわえている 9°、掛かって粘る 14〜31°） */
var SHAKE = {
	bite: THREE.MathUtils.degToRad(9),
	hooked: THREE.MathUtils.degToRad(25),
	tired: .04
};
/**
* 1 匹の魚。object を scene に足し、毎フレーム update(dt) を呼ぶ。
* 向き：口が +Z、背中が +Y、体の真ん中が原点。大きさは実寸（m）
*/
var FishActor = class {
	/** scene に足すもの */
	object = new THREE.Group();
	info;
	/** 体長 m */
	length;
	/** 床で跳ねる（landed）ときの床の高さ（object の中の y） */
	floorY;
	motion = "swim";
	/** 体のしなり方（ゲームの値。変えると動きが変わる） */
	style = { ...GAME_STYLE };
	/**
	* 自分で泳がせるとき：泳ぐ速さ m/s と曲がる速さ rad/s（+ で左へ）。泳ぐ動き（swim・power・turn・hover）の間、
	* 決まった見本の速さの代わりに使い、尾の振り方・体の曲がり・ひれをそれに合わせる。null なら見本の速さ。
	* 動かすのは使う人：毎フレーム object を口の向き（+Z）へ currentSpeed × dt 進め、turnRate × dt だけ Y 軸まわりに回す
	*/
	drive = null;
	body = new THREE.Group();
	mesh;
	p;
	gaze = new Gaze();
	seed = Math.random() * 100;
	base = new THREE.Quaternion();
	time = Math.random() * 100;
	phase = Math.random() * 10;
	finClock = Math.random() * 100;
	finFold = 0;
	gillPhase = Math.random() * 10;
	mouthOpen = 0;
	shakePhase = Math.random() * 10;
	shakeAmp = 0;
	shakeAngle = 0;
	shakeShown = 0;
	roll = 0;
	pitch = 0;
	yaw = 0;
	exert = 0;
	speed = 0;
	prevSpeed = 0;
	decel = 0;
	intent = 0;
	turn = 0;
	thrust = 1;
	bursting = true;
	gaitT = Math.random();
	flop = 2.4;
	constructor(id, lengthCm) {
		const info = FISH.find((f) => f.id === id);
		if (!info) throw new Error(`unknown fish: ${id}`);
		this.info = info;
		this.length = (lengthCm ?? info.typicalCm) / 100;
		const mesh = buildPhotoFish(id, this.length);
		if (!mesh) throw new Error(`fish not loaded: ${id} (call loadFish first)`);
		this.mesh = mesh;
		this.p = paramsOf(id);
		this.floorY = -this.length * this.p.bodyHeight * .2;
		this.body.add(mesh.root);
		this.object.add(this.body);
	}
	/** 動きを変える（体の状態はなめらかにつながる） */
	setMotion(m) {
		if (m === this.motion) return;
		this.motion = m;
		this.flop = 2.4;
	}
	/** 'auto'：カメラから遠いと軽い形、'high'：いつも細かい形、'low'：いつも軽い形 */
	setDetail(d) {
		const lod = this.mesh.root.children[0];
		lod.autoUpdate = d === "auto";
		if (d !== "auto") lod.levels.forEach((l, i) => l.object.visible = d === "low" ? i === lod.levels.length - 1 : i === 0);
		else this.mesh.detail(true);
	}
	/** いま泳いでいる速さ m/s（ゆっくりの魚は尾を振っては滑るので、drive.speed のまわりで上下する） */
	get currentSpeed() {
		return this.speed;
	}
	/** 口先の位置（object の中の座標）。口から糸を描くのに使う */
	getMouth(out = new THREE.Vector3()) {
		return out.set(0, 0, this.length * MOUTH).applyQuaternion(this.body.quaternion);
	}
	/** dt 秒すすめる */
	update(dt) {
		const L = this.length;
		const m = this.motion;
		const p = this.p;
		const st = this.style;
		const lure = ON_LINE.has(m) || m === "landed";
		this.time += dt;
		const drive = this.drive;
		if (!lure) {
			const want = drive ? Math.max(0, drive.speed) : m === "swim" || m === "turn" ? p.cruise : m === "power" ? p.burst : 0;
			const bl = want / Math.max(L, .05);
			const inter = p.glide * (1 - smooth(bl, 1, 2.5));
			let target = want;
			let accel = 1.5;
			if (inter < .05) {
				this.thrust += (1 - this.thrust) * Math.min(1, dt * 4);
				this.intent = want;
			} else {
				this.gaitT -= dt;
				if (this.gaitT <= 0) {
					this.bursting = !this.bursting;
					this.gaitT = this.bursting ? rand(.3, .7) : rand(.3, 1.4) * inter * 2.5;
				}
				if (this.bursting) {
					this.thrust += (1 - this.thrust) * Math.min(1, dt * 8);
					target = want * (1 + inter * 1.5);
					accel = 3;
					this.intent = target;
				} else {
					this.thrust += (.12 - this.thrust) * Math.min(1, dt * 5);
					target = 0;
					accel = .8;
					this.intent = want;
				}
			}
			this.speed += (target - this.speed) * Math.min(1, dt * accel);
			let yawRate = 0;
			if (drive) yawRate = drive.turnRate;
			else if (m === "turn") {
				const k = this.bursting || inter < .05 ? 1 : .15;
				yawRate = .9 * Math.cos(this.time * .45) * k - .3 * this.yaw;
			}
			this.yaw = m === "turn" && !drive ? this.yaw + yawRate * dt : this.yaw * (1 - Math.min(1, dt * 2));
			this.turn += (yawRate - this.turn) * Math.min(1, dt * 5);
		} else {
			this.speed += (0 - this.speed) * Math.min(1, dt * 3);
			this.intent = 0;
			this.yaw *= 1 - Math.min(1, dt * 2);
			this.turn -= this.turn * Math.min(1, dt * 5);
		}
		this.shakeShown = this.shakeAngle;
		this.shakeAmp += ((SHAKE[m] ?? 0) - this.shakeAmp) * Math.min(1, dt * 4);
		const shakeHz = 1.3 / Math.sqrt(Math.max(L, .1));
		this.shakePhase += dt * Math.PI * 2 * shakeHz;
		this.shakeAngle = this.shakeAmp * Math.sin(this.shakePhase);
		let freq;
		let amp;
		let roll = clamp(-this.turn * .35, -.6, .6);
		let exert = 0;
		if (m === "landed") {
			this.flop -= dt;
			if (this.flop <= 0) this.flop = 2.4;
			const vigor = Math.max(.25, this.flop / 2.4);
			freq = 4 + 4 * vigor;
			amp = .12 + .25 * vigor;
			roll = -Math.PI / 2;
		} else if (m === "air") {
			freq = 7 * st.airFreq;
			amp = .3 * st.airAmp;
			roll = Math.sin(this.time * 9) * .7;
		} else if (m === "tired") {
			freq = 1.8;
			amp = .05;
			roll = -1.3;
		} else if (m === "hooked") {
			freq = 4.5;
			amp = .18;
		} else if (m === "bite") {
			freq = 4;
			amp = .11;
		} else {
			const bl = this.speed / Math.max(L, .05);
			freq = (4 * bl + 4) / 3 * (.35 + .65 * this.thrust);
			amp = (.035 + Math.min(bl / 6, 1) * .09) * (.2 + .8 * this.thrust);
			exert = smooth(bl, 3, 6);
		}
		exert *= st.burst;
		this.exert += (exert - this.exert) * Math.min(1, dt * 3);
		freq /= 1 + .8 * this.exert;
		amp *= 1 + .5 * this.exert;
		const lock = m === "bite" || m === "hooked" ? st.tailLock : 0;
		if (lock > 0) {
			freq = THREE.MathUtils.lerp(freq, shakeHz, lock);
			amp *= 1 + .6 * lock;
		}
		this.phase += dt * Math.PI * 2 * freq;
		if (lock > 0) {
			const d = this.shakePhase + st.tailOffset - this.phase;
			this.phase += Math.atan2(Math.sin(d), Math.cos(d)) * lock * Math.min(1, dt * 6);
		}
		const shaking = ON_LINE.has(m);
		const neck = shaking ? this.shakeShown * st.neckFlex : 0;
		const cBend = shaking ? -st.bodyBend * this.shakeShown / Math.max(L, .05) : 0;
		this.mesh.flex(neck, st.neckAt - .1, st.neckAt + .1, cBend, st.recoil, this.exert);
		const flow = lure ? 1 : Math.min(1, this.speed / Math.max(L, .05) / 3);
		this.finClock += dt * (1 + .6 * flow);
		const flag = p.finFlag * st.flag * (.6 + .7 * flow);
		this.mesh.flutter(this.finClock, p.finFlutter * st.flutter * (1 + .4 * flow), flag, this.seed % 1);
		const muscle = p.finMove * st.finMove;
		if (dt > 0) {
			const d = lure ? 0 : Math.max(0, (this.prevSpeed - this.speed) / dt) / Math.max(L, .05);
			this.decel += (d - this.decel) * Math.min(1, dt * 6);
			this.prevSpeed = this.speed;
		}
		const plan = this.finPlan(m);
		this.finFold += (plan.fold - this.finFold) * Math.min(1, dt * 3);
		const steer = lure ? 0 : clamp(this.turn * .3, -.35, .35);
		const pect = .6 * (.25 - .15 * this.finFold + Math.min(.3, this.decel * .1));
		const m1 = Math.min(1, muscle);
		if (m === "range") {
			const s = .5 - .5 * Math.cos(this.time * Math.PI * .5);
			this.mesh.finMove(this.finClock, .4 * s, 1 - s, 0, 0, -.6 + 1.02 * s, 0);
			this.mesh.gill(GILL_MAX * s);
			this.mesh.mouth(this.mesh.mouthMax * s);
		} else {
			this.mesh.finMove(this.finClock, plan.sway * muscle, this.finFold * m1, steer * muscle, plan.wobble * m1, pect * muscle, st.finWhim * m1);
			this.gillPhase += dt * Math.PI * 2 * BREATH_HZ;
			const gill = GILL_MAX * (.5 - .5 * Math.cos(this.gillPhase));
			const mouth = .6 * (this.mesh.mouthMax || .35) * (.5 - .5 * Math.cos(this.gillPhase + 1.4));
			this.mouthOpen += (mouth - this.mouthOpen) * Math.min(1, dt * 12);
			const aloft = m === "air";
			this.mesh.gill(gill * st.gill * (aloft ? st.airGill : 1));
			this.mesh.mouth(this.mouthOpen * st.mouth * (aloft ? st.airMouth : 1));
		}
		this.mesh.lookAtViewer(m === "air" || m === "landed" ? this.gaze.update(dt) : 0);
		let bend = -this.turn / Math.max(this.speed, .15, .5 * L);
		const most = p.maxBend / (.325 * .65 * L);
		bend = clamp(bend, -most, most);
		this.mesh.swim(this.phase, amp, bend, this.time);
		this.roll += (roll - this.roll) * Math.min(1, dt * 4);
		this.mesh.lieOnFloor(m === "landed" ? -Math.sin(this.roll) : 0);
		const bl = Math.max(this.speed, this.intent) / Math.max(L, .05);
		let pitch = lure ? 0 : p.hoverPitch * (1 - smooth(bl, .5, 2));
		if (!lure && p.upright) pitch = Math.max(pitch, p.upright * (1 - smooth(bl, .1, .35)));
		this.pitch += (pitch - this.pitch) * Math.min(1, dt * 1.5);
		const up = m === "air" ? -Math.PI / 2 : 0;
		this.base.slerp(new THREE.Quaternion().setFromAxisAngle(AXIS_X, up), Math.min(1, dt * 6));
		const q = this.body.quaternion;
		q.setFromAxisAngle(AXIS_Y, this.yaw + (shaking ? this.shakeShown : 0)).multiply(this.base);
		q.multiply(new THREE.Quaternion().setFromAxisAngle(AXIS_X, -this.pitch));
		q.multiply(new THREE.Quaternion().setFromAxisAngle(AXIS_Z, this.roll));
	}
	/** ひれの開き具合（fold：0 いっぱいに開く〜1 畳む）、横へ傾ける振れ、ひれごとにばらばらに開け閉めする振れ */
	finPlan(m) {
		let r;
		if (m === "landed" || m === "air") r = [
			.3,
			.4,
			.6
		];
		else if (m === "tired") r = [
			.55,
			.08,
			.5
		];
		else if (m === "hooked") r = [
			.3,
			.35,
			.6
		];
		else if (m === "bite") r = [
			.35,
			.25,
			.6
		];
		else {
			const fast = smooth(this.speed / Math.max(this.length, .05), 1.5, 4);
			r = [
				.4 + .35 * fast,
				.2 - .14 * fast,
				.6 - .2 * fast
			];
			r[0] -= Math.min(.4, this.decel * .12) + Math.min(.2, Math.abs(this.turn) * .1);
		}
		return {
			fold: clamp(r[0], 0, 1),
			sway: r[1],
			wobble: r[2]
		};
	}
	/** scene から外して、この魚の材質を捨てる（形とテクスチャは読み込んだまま、ほかの魚と共有） */
	dispose() {
		this.object.removeFromParent();
		this.object.traverse((o) => {
			const mesh = o;
			if (mesh.isMesh) mesh.material.dispose();
		});
	}
};
/** 魚を 1 匹作る（loadFish で読み込んだあと）。lengthCm を省けばふつうの大きさ */
function createFish(id, lengthCm) {
	return new FishActor(id, lengthCm);
}
export { FISH, FishActor, MOTIONS, createFish, fishStats, loadFish };
