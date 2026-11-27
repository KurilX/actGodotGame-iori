"""放大攻击动作幅度：躯干大幅前倾 + 蹬地 + 剑加长。"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = "tools/make_animation_v4.py"
s = open(p, encoding="utf-8").read()

old = """def make_attack(p, seg):
    \"\"\"四段轻攻击，每段 6 帧。\"\"\"
    angles = [(100, 40), (40, -30), (-30, 30), (30, 100)][seg]
    track = K.Track([
        (0.00, None, dict(hand=(4, -13), sword_angle=angles[0] + 20,
                          body_dy=0, lean=0.5)),
        (0.25, K.ease_in_out, dict(hand=(7, -15), sword_angle=angles[0],
                                   body_dy=-1, lean=1.0)),
        (0.45, K.ease_in_out, dict(hand=(10, -13), sword_angle=angles[1],
                                   body_dy=-1, lean=2.0)),
        (0.65, K.ease_in_out, dict(hand=(9, -12), sword_angle=angles[1] + 10,
                                   body_dy=0, lean=1.5)),
        (0.85, K.ease_in_out, dict(hand=(6, -13), sword_angle=angles[0],
                                   body_dy=0, lean=0.5)),
        (1.00, K.ease_in_out, dict(hand=(6, -14), sword_angle=angles[0],
                                   body_dy=0, lean=0.0)),
    ])
    return [compose(p, **params) for params in K.bake(track, 6)]"""

new = """def make_attack(p, seg):
    \"\"\"四段轻攻击，每段 6 帧——大幅躯干前倾 + 蹬地 + 剑弧线。\"\"\"
    angles = [(110, 20), (30, -50), (-60, 40), (20, 120)][seg]
    track = K.Track([
        (0.00, None, dict(hand=(3, -17), sword_angle=angles[0] + 30,
                          body_dy=1, lean=-2.0, torso_dx=-1.0,
                          foot_l=(-3, 0), foot_r=(3, 0))),
        (0.22, K.ease_in_out, dict(hand=(8, -20), sword_angle=angles[0],
                                   body_dy=0, lean=-3.0, torso_dx=-1.5,
                                   foot_l=(-4, 0), foot_r=(4, 0))),
        (0.42, K.ease_in_out, dict(hand=(13, -15), sword_angle=angles[1],
                                   body_dy=-2, lean=4.0, torso_dx=2.5,
                                   foot_l=(4, 0), foot_r=(-3, 0))),
        (0.60, K.ease_in_out, dict(hand=(12, -13), sword_angle=angles[1] + 15,
                                   body_dy=-1, lean=5.0, torso_dx=3.0,
                                   foot_l=(5, 0), foot_r=(-4, 0))),
        (0.80, K.ease_in_out, dict(hand=(8, -15), sword_angle=angles[0] + 10,
                                   body_dy=0, lean=2.0, torso_dx=1.0,
                                   foot_l=(2, 0), foot_r=(-2, 0))),
        (1.00, K.ease_in_out, dict(hand=(9, -18), sword_angle=angles[0],
                                   body_dy=0, lean=0.0, torso_dx=0.0,
                                   foot_l=(0, 0), foot_r=(0, 0))),
    ])
    return [compose(p, **params) for params in K.bake(track, 6)]"""

assert old in s, "attack block not found"
s = s.replace(old, new)
s = s.replace("for i in range(2, 22):", "for i in range(2, 30):")
open(p, "w", encoding="utf-8").write(s)
print("attack keyframes amplified, sword lengthened 22->30")
