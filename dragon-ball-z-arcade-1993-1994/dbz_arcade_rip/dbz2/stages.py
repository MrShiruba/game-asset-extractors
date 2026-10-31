"""Stages of Dragon Ball Z 2.

* 0x44C2 + 8*base + 2*round : stage actually loaded for base stage 0-9 (+10 = 21)
  at round 0-3 (variable 0x4877C0) - some stages change between rounds.
* 0x540C + 8*stage + layout : two map/palette codes (back layer, front layer),
  layout = 4 (variable 0x487768 = 4, even rounds: the ground view) or 0 (sky view).
* 0x4C678 + 8*stage + layout : animation channels (routine 0x54BC / 0x54E6):
    word initial delay, long script ; script = (word delay, word map code)...
    then a negative word followed by the loop address. The codes are map patches
    drawn over the layer, with the layer palette.
* 0x10CD4 + 4*stage : sprite objects placed on the stage (routine 0x553C), 16 bytes:
    layout, x, y, priority, scale, colour, flip, object script (0x10F36 table).
* music = command 0x01 + base stage (routine at 0x530C).
"""
BASE_TO_STAGE = 0x44C2
STAGE_CODES = 0x540C
STAGE_ANIMS = 0x4C678
STAGE_OBJECTS = 0x10CD4
NUM_STAGES = 22
NUM_BASE = 11
LAYOUTS = {4: "ground", 0: "sky"}


class StageInfo:
    def __init__(self, maincpu):
        self.m = maincpu

    def w(self, a):
        return int.from_bytes(self.m[a:a + 2], "big")

    def l(self, a):
        return int.from_bytes(self.m[a:a + 4], "big")

    def rounds(self):
        """stage -> list of (base stage, round)"""
        out = {}
        for b in range(NUM_BASE):
            for r in range(4):
                out.setdefault(self.w(BASE_TO_STAGE + 8 * b + 2 * r), []).append((b, r))
        return out

    def codes(self, stage, layout):
        return self.w(STAGE_CODES + 8 * stage + layout), self.w(STAGE_CODES + 8 * stage + layout + 2)

    def animations(self, stage, layout):
        """-> list of channels: {"start_delay", "steps": [(delay, code)], "loop_to": index}"""
        a = self.l(STAGE_ANIMS + 8 * stage + layout)
        out = []
        while self.w(a) < 0x8000 and len(out) < 64:
            delay, p = self.w(a), self.l(a + 2)
            a += 6
            steps, pos = [], {}
            loop = None
            for _ in range(256):
                if self.w(p) & 0x8000:
                    target = self.l(p) & 0xFFFFFF
                    loop = pos.get(target)
                    if loop is None and target not in pos:
                        p = target          # jump forward/elsewhere: follow once
                        if p in pos:
                            break
                        continue
                    break
                pos[p] = len(steps)
                steps.append((self.w(p), self.w(p + 2)))
                p += 4
            out.append({"start_delay": delay, "steps": steps, "loop_to": loop})
        return out

    def objects(self, stage):
        a = self.l(STAGE_OBJECTS + 4 * stage)
        out = []
        while self.w(a) < 0x8000 and len(out) < 32:
            v = [self.w(a + 2 * k) for k in range(8)]
            out.append({"layout": v[0], "x": v[1] - 0x10000 if v[1] & 0x8000 else v[1], "y": v[2],
                        "priority": v[3], "scale": v[4], "colour": v[5], "flip": v[6], "script": v[7]})
            a += 16
        return out
