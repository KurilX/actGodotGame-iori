"""临时接入 V2：正确的帧名映射。

帧名清单：atk1-4, dash, gain, hurt, idle, jump, walk（ fall 用 jump 尾帧？）
先列出全部动画名再映射。
"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
ARK = ROOT / "art" / "characters" / "ori" / "frames_ark_poses"
FRAMES = ROOT / "art" / "characters" / "ori" / "frames"

names = sorted({p.name for p in FRAMES.glob("ori_*.png")})
anims = {}
for n in names:
    stem = n[len("ori_"):-len(".png")]
    anim = stem.rsplit("_", 1)[0]
    idx = int(stem.rsplit("_", 1)[1])
    anims.setdefault(anim, []).append(idx)

print("动画清单:", {k: max(v) + 1 for k, v in anims.items()})

# 映射：Ark 姿态 → (动画名, 帧号)
MAP = [
    ("pose_stand_0.png", "idle", 0),
    ("pose_walk_0.png", "walk", 0),
    ("pose_jump_0.png", "jump", 0),
    ("pose_slash_0.png", "atk1", 3),
    ("pose_heavy_0.png", "atk3", 0),
    ("pose_hurt_0.png", "hurt", 0),
    ("pose_dash_0.png", "dash", 1),
]

for ark, anim, idx in MAP:
    src = ARK / ark
    dst = FRAMES / f"ori_{anim}_{idx}.png"
    if not dst.exists():
        print("skip", dst.name, "(不存在)")
        continue
    backup = ROOT / "art/characters/ori/backup_pre_ark" / dst.name
    backup.parent.mkdir(exist_ok=True)
    if not backup.exists():
        shutil.copy(dst, backup)
    shutil.copy(src, dst)
    print(f"replaced {dst.name} <- {ark}")
print("done")
