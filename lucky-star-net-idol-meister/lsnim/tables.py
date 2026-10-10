"""Data: sorting tables, names, and tables copied from the EBOOT (ULJM05542).

Nothing here decodes a format; these tables say what each file is and where it goes.
Naming rule: what the game displays is kept in Japanese as displayed; the categories
we made up are in English.
"""
import os
import struct


# ---------------------------------------------------------------- characters

# Character numbers as used by the scripts and the voice tables.
CHARACTERS = ['こなた', 'かがみ', 'つかさ', 'みゆき', 'みさお', 'あやの', 'こう', 'やまと',
              'ゆたか', 'みなみ', 'ひより', 'パティ', 'あきら', 'ひかげ', 'ひなた', 'ゆい',
              'ななこ', 'ひかる', 'ふゆき', 'そうじろう', 'ゆかり', 'みなみの母', 'チェリー']


# ---------------------------------------------------------------- quiz

# Quiz (ローカルオーディション): 1800 questions = 9 categories of 200, in this order.
# The category of question n is n // 200 (u16 table of first questions 0, 200 ... 1600 at
# file offset 0x1428a8 of ULJM05542 EBOOT.BIN). Names as drawn by the game (pr.bin image 23).
QUIZ_CATEGORY_SIZE = 200
QUIZ_CATEGORIES = ['四択問題', '○×問題', 'ギョーカイ用語', '正しいタイトル', 'ツンデレ判断',
                   'モノマネ大会', '仲間はずれ', 'らき☆すたカルト', '画像問題']
# モノマネ大会 (category 5) plays a voice: question n (1000-1199) plays union file
# 251 + (n - 1000), computed by the game code (EBOOT.BIN file offsets 0x16348 and 0x17814).
QUIZ_VOICE_CATEGORY = 5
QUIZ_VOICES_FIRST = 251


def quiz_voice_question(file_id):
    """Question number (0-based) of a union quiz voice, or None."""
    k = file_id - QUIZ_VOICES_FIRST
    if 0 <= k < QUIZ_CATEGORY_SIZE:
        return QUIZ_VOICE_CATEGORY * QUIZ_CATEGORY_SIZE + k
    return None


# ---------------------------------------------------------------- image layout tables

FONT_IDS = {'union': {3214: (16, 16)}}   # raw 2-bit fonts stored in the CPKs: id -> glyph size



# Files where some images own several palettes (colour variants). Palettes are still
# stored in image order, but nothing in the file says how many each image owns, so the
# count is given here (checked against the game screen). The first palette of an image
# gives <file>_<image>.png, the others <file>_<image>_v<n>.png.
# {archive: {file id: {image: palette count}}}
# union 03065 (mini-games グラビア撮影 / ダンスレッスン): 24 palettes for 20 images;
#   01 HUD (numbers, notes, ring) in 3 colours (blue, pink, green),
#   03 dojo background + an almost white flash version,
#   19 dancer sheet: black suit (player) and red suit (rival).
PALETTE_COUNTS = {'union': {3065: {1: 3, 3: 2, 19: 2}}}

# Sheets stored as 32x16 cells packed 16 per row (like the tachi-e atlas), whose cell
# positions are not in the file but in the EBOOT. Each image is rebuilt on its canvas.
# union 03065_19 (ダンスレッスン dancers, 17 poses on a 928x864 canvas): 475 cells,
# positions = u16 (x, y) pairs at file offset 0x176884 of ULJM05542 EBOOT.BIN, stored
# here as (x / 32, y / 16) bytes.
DANCER_CELLS = bytes.fromhex(
    '030009000f0014001500160017001b00020103010401080109010a010d010e010f0114011501160117011b0102020302'
    '0402080209020a020d020e020f0210021502160217021a021b021c02020303030403080309030a030d030e030f031003'
    '1503160317031a031b031c03020403040404080409040a040e040f04150416041a041b041c040305040509050a050e05'
    '0f051405150516051a051b051c05020603060406080609060a060e060f0610061406150616061a061b061c0602070307'
    '0407080709070a070e070f0710071407150716071b071c07020803080408080809080a080e080f081008140815081608'
    '1b08020903090409080909090a090e090f09100915091b09020a030a040a080a090a0a0a0e0a0f0a100a150a1b0a020b'
    '030b020c030c070c080c0d0c0e0c010d020d030d070d080d090d0d0d0e0d0f0d010e020e030e070e080e090e0c0e0d0e'
    '0e0e0f0e010f020f030f070f080f090f0c0f0d0f0e0f0f0f0210031004100710081009100e100f100211031104110811'
    '09110e110f111011021203120412081209120a120e120f121012021303130413081309130a130e130f13101302140314'
    '0414081409140a140e140f1410140115021503150415081509150a150e150f151015031603170417081709170d170e17'
    '021803180418081809180a180d180e180f18021903190419081909190a190e190f19021a031a041a081a091a0a1a0d1a'
    '0e1a0f1a021b031b041b081b091b0a1b0d1b0e1b0f1b101b021c031c041c081c091c0a1c0e1c0f1c101c021d031d041d'
    '081d091d0a1d0e1d0f1d101d021e031e041e081e091e0a1e0e1e0f1e101e021f031f041f071f081f091f0a1f0e1f0f1f'
    '101f032004200a200e200f20102011200321042109210a210e210f21102111210322042209220a220f22102211220323'
    '042309230a230f231023112303240424082409240a240b240f24102403250425082509250a250b250f25102502260326'
    '042609260a260b260f26102602270327042709270a270f27102702280328042809280a280f2810280229032904290929'
    '0a290f291029022a032a042a092a0a2a0f2a102a032b042b0a2b032c042c0a2c112c022d032d042d092d0a2d102d112d'
    '022e032e042e092e0a2e0b2e0f2e102e112e122e032f042f092f0a2f0b2f0c2f0d2f0e2f0f2f102f112f122f03300430'
    '09300a300c300d300e300f3010301130123002310331043109310a310f31103102320332043209320a320f3210320233'
    '0333043309330a330f33103302340334043409340f34103402350335043509350a350f351035'
)
CELL_LAYOUTS = {'union': {3065: {19: DANCER_CELLS}}}


# Sheets of separate pieces (texts, icons) packed into a power-of-two texture; the game
# draws each piece on its own. They are laid out again as lines: the pieces of a line
# side by side (gap px apart), the lines LINE_GAP px apart, all left-aligned.
# Rectangles (x0, y0, x1, y1) are measured on the texture.
# {archive: {file id: {image: [(gap, [pieces]), ...]}}}
# union 03065_00: 特訓開始!! is cut at x=238 and continues on the next line (the two
# halves join pixel-exactly, gap 0), then the 4 buttons ○△✕□, then 終了.
PIECE_LAYOUTS = {'union': {3065: {0: [
    (0, [(0, 0, 238, 84), (0, 84, 147, 168)]),
    (4, [(150, 86, 195, 130), (198, 86, 243, 130), (198, 134, 243, 178), (198, 182, 243, 226)]),
    (0, [(0, 168, 155, 256)]),
]}}}


# ---------------------------------------------------------------- lt.bin and pr.bin
#
# Two files of the DATA folder that are not CPK archives; the game loads each one whole.
#
# lt.bin: the game font (the glyph indices of the scripts point into it, see GLYPHS).
#   3650 glyphs back to back, no header; one glyph = 92 bytes = 18 rows of 5 bytes
#   (20 px, 2 bits per pixel, low bits first) + 2 zero bytes. Zero padding at the end.
LT_GLYPH = (20, 18, 92)                 # width, height, bytes per glyph

# pr.bin: 61 resources back to back, without any table inside the file. Their offsets are
# in the EBOOT (61 x u32 at file offset 0x14b498 of ULJM05542 EBOOT.BIN), copied below.
#   resources 0-29   images: pixel indices, PSP swizzled, either raw (0, 1, 5, 6) or as
#                    the gzip image blocks of union.cpk (see find_blocks)
#   resources 30-60  palettes: 256 RGBA colours, or 16 colours padded to 0x100 bytes
# As in union.cpk, no size or bit depth is stored: the depth comes from the palette size
# and the width from best_layout.
PR_OFFSETS = (
    0x00000, 0x10000, 0x18000, 0x19000, 0x1c800, 0x21800, 0x29800, 0x32000, 0x32800, 0x33000,
    0x3b000, 0x41000, 0x46800, 0x4b800, 0x52000, 0x58000, 0x5e800, 0x65000, 0x69000, 0x71000,
    0x79000, 0x86800, 0x88000, 0x8d000, 0x8e800, 0x94000, 0x9c800, 0x9f000, 0xa7000, 0xaa800,
    0xae000, 0xae400, 0xae800, 0xae900, 0xaed00, 0xaee00, 0xaef00, 0xaf000, 0xaf100, 0xaf500,
    0xaf600, 0xafa00, 0xafb00, 0xaff00, 0xb0300, 0xb0700, 0xb0800, 0xb0c00, 0xb1000, 0xb1400,
    0xb1800, 0xb1c00, 0xb2000, 0xb2400, 0xb2800, 0xb2900, 0xb2a00, 0xb2e00, 0xb3200, 0xb3600,
    0xb3a00,
)
PR_IMAGES = 30
# Palette(s) of each image. The game code loads image n then palette n + 31 for images
# 9-29; the first images are paired one by one in the code, listed here. Image 3 has two
# palettes (blue and pink versions of the same interface): 03.png and 03_v1.png.
# Images 2 and 28 are never loaded with a constant number: their palette is the one left
# (2 -> 39) / the one of the n + 31 rule (28 -> 59); result checked by eye.
PR_PALETTES = {0: [32], 1: [33], 2: [39], 3: [30, 31], 4: [38], 5: [34], 6: [35], 7: [36], 8: [37]}
# Width forced where best_layout cannot tell: image 21 is 512x48, a strip too flat for it.
# It holds the two pieces of the シンクロ率上昇中 warning animation (the text, which blinks,
# and the DANGER sign, repeated in two scrolling rows); the animation itself is game code.
PR_WIDTHS = {21: 512}
# What each image shows (descriptions are ours, for the README).
PR_CONTENTS = [
    'system messages (save, load, install) as text lines', 'save/load screen buttons',
    'small font (digits, latin, kana)', 'interface with 撮影 / ウィンドウ消去 / 終了 (2 colours)',
    'text boxes and message icons', 'rain overlay', 'cloud overlay', 'star', 'circle mask',
    'town map: こなたの街', 'town map place names', 'idol ranks, level and rank numbers',
    'character face icons', 'town map buildings: こなたの街', 'main menu entries',
    'town map buildings: アキバ', 'town map buildings: ブクロ', 'town map icons: ネット',
    'town map: アキバ', 'town map: ブクロ', 'town map: ネット (browser window)',
    'シンクロ率上昇中 warning: text and DANGER sign', 'NEW!! / GET!! labels, genre icons, オススメ',
    'quiz category names', 'costume names', 'end of day banner (営業終了)',
    'curtain (sides)', 'town map (variant loaded with the curtains)', 'curtain (full)',
    'audition stage labels and multipliers',
]


# ---------------------------------------------------------------- vo.cpk

# Order of the sc.cpk script blocks inside vo.cpk. vo.cpk stores voices script by script,
# in the order of the FF65 (voiced line) commands inside each script. Recovered by
# matching voice durations against text length; it tiles all 23487 voice files exactly.
BLOCK_ORDER = """
    00000 00525 00524 00523 00001 00528 00527 00526 00002 00531 00530 00529 00003 00534 00533 00532
    00009 00552 00551 00550 00010 00555 00554 00553 00004 00537 00536 00535 00005 00540 00539 00538
    00011 00558 00557 00556 00006 00543 00542 00541 00012 00561 00560 00559 00013 00564 00563 00562
    00014 00567 00566 00565 00008 00549 00548 00547 00015 00570 00569 00568 00016 00573 00572 00571
    00017 00576 00575 00574 00018 00579 00578 00577 00007 00546 00545 00544 00027 00028 00029 00030
    00031 00032 00033 00034 00035 00036 00037 00038 00039 00040 00041 00042 00043 00019 00020 00021
    00022 00023 00024 00025 00026 00052 00053 00054 00055 00056 00057 00058 00059 00060 00061 00062
    00063 00064 00065 00066 00067 00068 00044 00045 00046 00047 00048 00049 00050 00051 00077 00078
    00079 00080 00081 00082 00083 00084 00085 00086 00087 00088 00089 00090 00091 00092 00093 00069
    00070 00071 00072 00073 00074 00075 00076 00102 00103 00104 00105 00106 00107 00108 00109 00110
    00111 00112 00113 00114 00115 00116 00117 00118 00094 00095 00096 00097 00098 00099 00100 00101
    00125 00126 00127 00128 00129 00130 00131 00132 00133 00134 00135 00136 00137 00138 00119 00120
    00121 00122 00123 00124 00145 00146 00147 00148 00149 00150 00151 00152 00153 00154 00155 00156
    00157 00158 00139 00140 00141 00142 00143 00144 00165 00166 00167 00168 00169 00170 00171 00172
    00173 00174 00175 00176 00177 00178 00159 00160 00161 00162 00163 00164 00185 00186 00187 00188
    00189 00190 00191 00192 00193 00194 00195 00196 00197 00198 00179 00180 00181 00182 00183 00184
    00207 00208 00209 00210 00211 00212 00213 00214 00215 00216 00217 00218 00219 00220 00221 00222
    00223 00199 00200 00201 00202 00203 00204 00205 00206 00232 00233 00234 00235 00236 00237 00238
    00239 00240 00241 00242 00243 00244 00245 00246 00247 00248 00224 00225 00226 00227 00228 00229
    00230 00231 00257 00258 00259 00260 00261 00262 00263 00264 00265 00266 00267 00268 00269 00249
    00250 00251 00252 00253 00254 00255 00256 00276 00277 00278 00279 00280 00281 00282 00283 00284
    00285 00286 00287 00288 00289 00270 00271 00272 00273 00274 00275 00298 00299 00300 00301 00302
    00303 00304 00305 00306 00307 00308 00309 00310 00311 00312 00313 00314 00290 00291 00292 00293
    00294 00295 00296 00297 00322 00323 00324 00325 00326 00327 00328 00329 00330 00331 00332 00333
    00334 00315 00316 00317 00318 00319 00320 00321 00342 00343 00344 00345 00346 00347 00348 00349
    00350 00351 00352 00353 00354 00335 00336 00337 00338 00339 00340 00341 00359 00360 00361 00362
    00363 00364 00365 00366 00367 00368 00369 00355 00356 00357 00358 00375 00376 00377 00378 00379
    00380 00381 00382 00383 00384 00385 00370 00371 00372 00373 00374 00390 00391 00392 00393 00394
    00395 00396 00397 00398 00399 00400 00386 00387 00388 00389 00405 00406 00407 00408 00409 00410
    00411 00412 00413 00414 00415 00401 00402 00403 00404 00420 00421 00422 00423 00424 00425 00416
    00417 00418 00419 00429 00430 00431 00432 00433 00434 00435 00426 00427 00428 00439 00440 00441
    00442 00443 00444 00445 00436 00437 00438 00450 00451 00452 00453 00454 00455 00456 00457 00458
    00459 00460 00446 00447 00448 00449 00468 00469 00470 00466 00467 00473 00474 00475 00471 00472
    00478 00479 00480 00476 00477 00483 00484 00485 00481 00482 00488 00489 00490 00486 00487 00492
    00493 00494 00495 00491 00464 00465 00461 00462 00463 00501 00502 00503 00504 00505 00506 00507
    00496 00497 00498 00499 00500 00509 00510 00511 00512 00508 00514 00515 00516 00517 00513 00519
    00520 00521 00522 00518 00580 00581 00582 00583 00584 00585 00586 00587 00588 00589 00590 00591
    00592
""".split()


# ---------------------------------------------------------------- union.cpk and sc.cpk
#
# Scripts start music and sound effects with numbered commands:
#     FF67 <n>        music n       (n = FFFF: stop, FFFC: other)
#     FF66 <n> 0000   sound effect n
# Music n is union file n (0-44) and sound effect n is union file 68 + n (0-174); the
# numbering matches the file counts exactly and was checked by ear.
# Two groups are never called by the scripts (the mini-game / map code plays them); their
# folder names are ours:
#     45-67    ボイストレーニング  singing voices of that mini-game, one per character in
#                             character order: 045-chr00_こなた.adx ... 067-chr22_チェリー.adx
#     243-250  ambient        looping ambience (car, waves, alarm...)
# Each group gets its own folder under adx/ and files keep their union index; sound
# effects also get the number the scripts use: adx/bgm/000.adx, adx/se/068-se000.adx.
SOUND_FILES = {}
SOUND_FILES.update({n: ('bgm', None) for n in range(45)})
SOUND_FILES.update({45 + n: ('ボイストレーニング', 'chr%02d_%s' % (n, CHARACTERS[n])) for n in range(23)})
SOUND_FILES.update({68 + n: ('se', 'se%03d' % n) for n in range(175)})
SOUND_FILES.update({243 + n: ('ambient', None) for n in range(8)})

# union ACX holding ADX: the sound effects of each mini-game, written to
# acx/ミニゲーム-sfx/<id>-<mini-game>.acx. Names as written in the game's ミニ☆ゲーム menu.
MINIGAME_SFX = {
    2964: '握手会',
    2989: 'ブログ炎上',
    3014: 'お神輿わっしょい',
    3039: 'ファン暴走',
    3064: 'メガコナタン',
    3066: 'ボイストレーニング_グラビア撮影_ダンスレッスン',   # shared by these 3 mini-games
    3215: 'ローカルオーディション',
}

# union ACX holding AHX: mini-game voices, one ACX per character, 23 in a row in the order
# of the character select screen = the character numbers of the scripts (00 こなた ...
# 22 チェリー). Written to ahx/ミニゲーム-voices/<mini-game>/chrNN_<name>/<id>_<track>.ahx;
# the first tracks of each ACX are lines shared by all characters (identical copies).
MINIGAME_VOICES = {
    2965: '握手会',
    2990: 'ブログ炎上',
    3015: 'お神輿わっしょい',
    3040: 'ファン暴走',
    3090: 'ダンスレッスン',
    3216: 'ローカルオーディション',
}


# union images, sorted by what they show (ranges checked in game); anything not listed
# stays directly in png/. Mini-game names as in the ミニ☆ゲーム menu.
IMAGE_FOLDERS = {'union': [
    (912, 1236, 'アルバム鑑賞'),         # event CGs (the album of the game)
    (1237, 1463, 'bg'),                 # backgrounds
    (1464, 2925, 'tachie'),             # character sprites
    (2926, 2962, 'ui'),                 # title screen, menus, settings, interface, save icon
    (2963, 2963, 'ミニゲーム/握手会'),
    (2988, 2988, 'ミニゲーム/ブログ炎上'),
    (3013, 3013, 'ミニゲーム/お神輿わっしょい'),
    (3038, 3038, 'ミニゲーム/ファン暴走'),
    (3063, 3063, 'ミニゲーム/メガコナタン'),
    (3065, 3065, 'ミニゲーム/ボイストレーニング_グラビア撮影_ダンスレッスン'),
    (3067, 3089, 'ミニゲーム/ボイストレーニング'),
    (3113, 3213, 'ミニゲーム/ローカルオーディション'),   # quiz screen, then close-ups and silhouettes of the questions
    (3214, 3214, 'ui'),                 # 16x16 font
    (3239, 3247, 'ui'),
    # GIM previews of the ミニ☆ゲーム menu, in menu order
    (3248, 3248, 'ミニゲーム/ボイストレーニング'),
    (3249, 3249, 'ミニゲーム/グラビア撮影'),
    (3250, 3250, 'ミニゲーム/ダンスレッスン'),
    (3251, 3251, 'ミニゲーム/お神輿わっしょい'),
    (3252, 3252, 'ミニゲーム/ブログ炎上'),
    (3253, 3253, 'ミニゲーム/握手会'),
    (3254, 3254, 'ミニゲーム/メガコナタン'),
    (3255, 3255, 'ミニゲーム/ファン暴走'),
]}


# Tachi-e by character. The scripts show a sprite with FFC1 <n>: sprite n is face n % 2
# of union file 1464 + n // 2, and the voiced line that follows gives the character number
# (same numbers as the voices, 00 こなた ... 22 チェリー; 23+ are side characters).
# Ranges below come from those script references (gaps between two ranges of the same
# character filled in after checking the faces). After 02731 the sprite shown is often not
# the one who speaks next: those files were matched by comparing their faces with the
# sorted ones, then checked by eye. Folder: png/tachie/chr<nn>_<name>.
TACHIE_CHARACTERS = [
    (1464, 1535, 0), (1536, 1607, 1), (1608, 1675, 2), (1676, 1747, 3), (1748, 1823, 4),
    (1824, 1891, 5), (1892, 1959, 6), (1960, 2031, 7), (2032, 2095, 8), (2096, 2167, 9),
    (2168, 2251, 10), (2252, 2319, 11), (2320, 2383, 12), (2384, 2443, 13), (2444, 2507, 14),
    (2508, 2567, 15), (2568, 2619, 16), (2620, 2647, 17), (2648, 2669, 18), (2670, 2689, 19),
    (2690, 2711, 20), (2712, 2731, 21),
    # 02732-02752: side characters (not sorted, except these)
    (2732, 2732, 22), (2733, 2738, 25), (2745, 2745, 23),
    # other outfits
    (2753, 2760, 4), (2761, 2764, 5), (2765, 2768, 13), (2769, 2772, 14), (2773, 2776, 16),
    (2777, 2780, 19), (2781, 2782, 20), (2783, 2783, 21), (2784, 2784, 9), (2785, 2785, 23),
    # framed portraits, first set
    (2786, 2789, 0), (2790, 2793, 1), (2794, 2801, 2), (2802, 2805, 3), (2806, 2813, 4),
    (2814, 2821, 5), (2822, 2825, 6), (2826, 2829, 7), (2830, 2833, 8), (2834, 2837, 9),
    (2838, 2841, 10), (2842, 2845, 11), (2846, 2849, 12), (2850, 2853, 13), (2854, 2857, 14),
    (2858, 2865, 15), (2866, 2869, 16),
    (2870, 2870, 22), (2871, 2873, 3),       # 02871-02873: みゆき as a teacher
    # framed portraits, second set
    (2874, 2877, 0), (2878, 2880, 1), (2881, 2883, 2), (2884, 2886, 4), (2887, 2889, 5),
    (2890, 2891, 8), (2892, 2895, 9), (2896, 2899, 10), (2900, 2900, 11), (2901, 2903, 12),
    (2904, 2905, 13), (2906, 2906, 14), (2907, 2910, 15), (2911, 2914, 16), (2915, 2915, 3),
    (2916, 2916, 17), (2917, 2918, 18), (2919, 2920, 19), (2921, 2922, 20), (2923, 2923, 21),
    (2924, 2924, 9), (2925, 2925, 23),
]
CHARACTER_NAMES = dict(enumerate(CHARACTERS))
CHARACTER_NAMES[23] = 'かなた'           # character 23 of the scripts (こなた's mother)
CHARACTER_NAMES[25] = '兄沢'             # character 25 of the scripts


# Order of the event CGs in the アルバム☆鑑賞 album: entry k (k = 0..324) shows union file
# 912 + ALBUM_ORDER[k] (u16 table at file offset 0x14ddb0 of ULJM05542 EBOOT.BIN).
# CGs are named <album rank 001-325>-<union id>, e.g. png/アルバム鑑賞/003-01150.png.
ALBUM_ORDER = struct.unpack('<325H', bytes.fromhex(
    '00000100ee00020003000400050006000700080009000a000b000c000d000e000f001000110012001300150014001600'
    '1700180019001a001b001c001d001f001e0020002100220023002400250026002700280029002a002b002c002d002e00'
    '2f0030003100430133003400350036003700380039003a003b003c003e003f0040004100420043004400490045004600'
    '470048004a004b004c004d004e004f0050005100520053005400550056005c005d005e005f0060006100630062006400'
    '650066006700680069006a006b006c006e006d006f0070007100720073007400750076007700780079007a007b007c00'
    '7d007e007f008000810082008300ef00f000f100f200f300f400f500f600f700f800f900fa00fb00fc00870084008500'
    '8600880089008a008b008c008d008e008f0090009100920093009400950096009700980099009a009b009c009d009e00'
    '9f00a000a100a200a300a400a500a600a700a800a900aa00ab00ad00ae00af00b000b100b200b300b400b500b600b700'
    'b8005700b9005800ac00ba00bb00bc00bd00be00bf00c000c100c200c300c400c500c800c600c700c900ca00cb00cc00'
    'cd00ce00cf00d000d100d200fd00fe00ff0000010101020103010401050106010701080109010a010b010c010d010e01'
    '0f011001110112011301140115011601170118011901d300d400d500d600d700d800d900da00db00dc00dd00de00df00'
    'e000e100e200e300e400e500e600e700e800e900ea00eb00ec00ed001a01320044011b011c0136011d011e011f012001'
    '2101220123012401250126012701280129012a012b012c012d012f012e01300131013201330134013701380139013a01'
    '3b013e01350141014201400159005a005b003d003f013d013c01'
))
ALBUM_RANK = {912 + n: k + 1 for k, n in enumerate(ALBUM_ORDER)}


# union UI files: one file = one screen (or part of one), named after the screen (checked
# in game, names are ours), written to png/<screen>/. Files not listed stay in png/.
UI_SCREENS = [
    (2926, 2926, 'title-screen'),
    (2928, 2928, 'options'),
    (2929, 2929, 'セーブ'),
    (2930, 2930, 'ロード'),
    (2931, 2931, '泉家'),
    (2932, 2932, 'アルバム鑑賞-thumbnails'),
    (2933, 2933, 'セーブ-icon'),
    (2934, 2934, 'インストール'),
    (2936, 2936, 'らっきーぽん'),
    (2937, 2937, 'PV配信-situation-select'),
    (2938, 2938, 'アイドル殿堂'),
    (2939, 2939, 'ワゴンセール'),
    (2940, 2959, 'characters-fade'),
    (2960, 2962, 'extend-event'),
    (3214, 3214, 'font'),
    (3239, 3239, 'PV配信-start'),
    (3240, 3241, 'iDOL☆選択'),                 # 03240 interface, 03241 portraits
    (3242, 3242, 'idol-results-status'),
    (3243, 3243, 'コスチューム'),
    (3244, 3244, 'ミニゲーム-menu'),
    (3245, 3245, 'ローカルオーディション-results'),
    (3246, 3246, 'ネットアイドルオーディション-results'),
    (3247, 3247, 'intro'),
]


def png_folder(archive_label, stem):
    """Folder for the PNG of a file: png/ or png/<category>/."""
    if stem.isdigit() and archive_label == 'union':
        for first, last, character in TACHIE_CHARACTERS:
            if first <= int(stem) <= last:
                return os.path.join('png', 'tachie', 'chr%02d_%s' % (character, CHARACTER_NAMES[character]))
    if stem.isdigit():
        for first, last, folder in IMAGE_FOLDERS.get(archive_label, []):
            if first <= int(stem) <= last:
                if folder == 'ui':                       # one folder per screen, directly in png/
                    screen = next((name for a, b, name in UI_SCREENS if a <= int(stem) <= b), None)
                    return os.path.join('png', screen) if screen else 'png'
                return os.path.join('png', *folder.split('/'))
    return 'png'


# union 00251-00450: voices of the quiz category モノマネ大会 (see QUIZ_VOICES_FIRST), one
# per question, written to ahx/ローカルオーディション/<id>-Q<nnnn>.ahx. The game only stores the
# question index; Q<nnnn> is our label, the same as in sc/txt/ローカルオーディション/00595.txt (Q1001-Q1200).
def quiz_voice_path(file_id):
    """(folder, stem) for a union quiz voice, or None."""
    question = quiz_voice_question(file_id)
    if question is None:
        return None
    return os.path.join('ahx', 'ローカルオーディション'), '%05d-Q%04d' % (file_id, question + 1)


# union 00911: one-minute narration of the game intro, played right after script 00580 when
# a new game starts (checked in game; no script command plays it and its text is in no
# script). Written to ahx/story/00911.ahx (folder name is ours).
OTHER_VOICES = {911: (os.path.join('ahx', 'story'), '00911')}


# union 00451-00910: system voices, 20 situations x 23 characters. Each situation is a
# run of 23 files in character order (00 こなた ... 22 チェリー). Situations were identified
# by ear (names are ours; day-start-1..4 / day-end-1..5 are the variants the game picks
# from at the start / end of a day). Written to
# ahx/system-voices/<situation>/<id>-chrNN_<character>.ahx
MENU_VOICES_FIRST = 451
MENU_VOICE_SITUATIONS = [
    'title-call', 'day-start-1', 'day-start-2', 'day-start-3', 'day-start-4',
    'day-end-1', 'day-end-2', 'day-end-3', 'day-end-4', 'day-end-5',
    'extend-event', 'コスチューム', 'location-welcome',
    'ローカルオーディション-1st-place', 'ローカルオーディション-lose', 'level-up', 'rank-up',
    'PV配信-ready', 'PV配信-action', 'PV配信-cut',
]


def menu_voice_path(file_id):
    """(folder, stem) for a union menu voice, or None."""
    k = file_id - MENU_VOICES_FIRST
    if not 0 <= k < len(MENU_VOICE_SITUATIONS) * len(CHARACTERS):
        return None
    situation, character = divmod(k, len(CHARACTERS))
    folder = os.path.join('ahx', 'system-voices', MENU_VOICE_SITUATIONS[situation])
    return folder, '%05d-chr%02d_%s' % (file_id, character, CHARACTERS[character])


def minigame_voice_folder(file_id):
    for first, game in MINIGAME_VOICES.items():
        if first <= file_id < first + len(CHARACTERS):
            n = file_id - first
            return os.path.join('ahx', 'ミニゲーム-voices', game, 'chr%02d_%s' % (n, CHARACTERS[n]))
    return None


# Scripts of sc.cpk sorted by what they are; the same folders are used for the voices of
# vo.cpk. Folder names are ours. The ranges were found from the order of the scripts in
# vo.cpk (each prologue is followed by its 3 endings, see BLOCK_ORDER) and from who speaks
# in them, then checked in game.
# The 19 units of the iDOL☆選択 screen (7 SOLO, 6 DUO, 6 SPECIAL) are numbered here by
# their prologue script, 00000-00018; unit k has the endings 00523 + 3k to 00525 + 3k.
#   prologue/<unit>/        00000-00018  first scene of each unit
#   PV配信/chrNN_<name>/      00019-00460  PV配信 scenes of one character, in character order
#   PV配信/unitNN_<name>/     00461-00522  PV配信 scenes of a DUO / SPECIAL unit; NN (ours)
#                                           = 01-11 in file order
#   endings/<unit>/         00523-00579  3 endings per unit
# <unit> = chrNN_<name> (SOLO) or unitNN_<name>, the same folder names as in PV配信/.
#   story/                  00580-00592  story told by 鳥工作 (00580 = intro of a new game)
#   ミニゲーム/             00593-00594  texts shown after the ファン暴走 mini-game
#   ローカルオーディション/  00595        quiz database
# Unit names are the ones drawn by the game on the iDOL☆選択 screen (union 03240), checked
# in game: "U-18" is the 15 young characters (prologue 00018), "Adult Only" is そうじろう,
# ゆかり and みなみの母 (prologue 00008).
CHARACTER_EVENTS_FIRST = (19, 44, 69, 94, 119, 139, 159, 179, 199, 224, 249, 270, 290, 315, 335,
                          355, 370, 386, 401, 416, 426, 436, 446, 461)   # one start per character
UNIT_EVENTS = [(461, 465, 'Adult Only'), (466, 470, 'みさお & あやの'), (471, 475, 'こう & やまと'),
               (476, 480, 'ひより & パティ'), (481, 485, 'ひなた & ひかげ'), (486, 490, 'ゆい & ななこ'),
               (491, 495, 'ひかる & ふゆき'), (496, 507, 'メインキャラは4人'), (508, 512, 'ゆたか & みなみ'),
               (513, 517, 'ひかる & あきら'), (518, 522, 'U-18')]


# Unit of each prologue 00000-00018 (and of its endings): a character number for the SOLO
# units, a unit name for the others. Found from who speaks in the prologue and its endings,
# then checked in game.
PROLOGUE_UNITS = [0, 1, 2, 3, 8, 9, 12, 22, 'Adult Only', 'みさお & あやの', 'こう & やまと',
                  'ひより & パティ', 'ひなた & ひかげ', 'ゆい & ななこ', 'ひかる & ふゆき', 'メインキャラは4人',
                  'ゆたか & みなみ', 'ひかる & あきら', 'U-18']


def unit_folder(unit):
    """chrNN_<name> for a character number, unitNN_<name> for a unit name."""
    if isinstance(unit, int):
        return 'chr%02d_%s' % (unit, CHARACTERS[unit])
    number = [name for _, _, name in UNIT_EVENTS].index(unit) + 1
    return 'unit%02d_%s' % (number, unit)


def script_folder(script_id):
    """Folder (ours) of a script of sc.cpk, also used for its voices."""
    if script_id <= 18:
        return os.path.join('prologue', unit_folder(PROLOGUE_UNITS[script_id]))
    if script_id < CHARACTER_EVENTS_FIRST[-1]:
        character = max(k for k, first in enumerate(CHARACTER_EVENTS_FIRST) if first <= script_id)
        return os.path.join('PV配信', 'chr%02d_%s' % (character, CHARACTERS[character]))
    for first, last, unit in UNIT_EVENTS:
        if first <= script_id <= last:
            return os.path.join('PV配信', unit_folder(unit))
    if script_id <= 579:
        return os.path.join('endings', unit_folder(PROLOGUE_UNITS[(script_id - 523) // 3]))
    if script_id <= 592:
        return 'story'
    if script_id <= 594:
        return 'ミニゲーム'
    return 'ローカルオーディション' if script_id == 595 else ''
