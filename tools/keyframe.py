"""关键帧 + 缓动系统：把「逐帧手写参数」换成「少量关键帧 + 程序采样」。

## 为什么这么做

原来的写法是每个动作把所有帧的参数全部手写：

    specs = [dict(body_dy=1, lean=-7, hand=(-12,-20), sword_angle=-80),
             dict(body_dy=2, lean=-10, hand=(-14,-22), sword_angle=-100),
             ... 8 帧全写 ]

问题：帧数一多就难维护，而且**每帧之间是线性跳变**，动作僵硬。

新写法只写关键帧 + 缓动曲线：

    KEY = [(0.0, ease_out, dict(...)),   # 起手
           (0.45, ease_in,  dict(...)),  # 蓄力顶点
           (1.0, None,     dict(...))]   # 命中

中间帧由程序按时间采样插值出来。

## 两个关键设计

1. **角度插值走最短弧**：sword_angle 从 -100° 到 25°，线性插值会走 125°，
   但如果目标是 -170°，线性走 230° 就是反的，应该走 130°。
   `lerp_angle` 处理这个。

2. **缓动按「段」生效**：每个关键帧带一个缓动函数，
   描述的是「从上一帧到我这一帧」这段的插值方式。
   蓄力用 ease_out（快起慢停，有"顶住"的感觉），
   出手用 ease_in（慢起快落，有"甩出去"的感觉）。
"""

import math


# ─────────────────────────── 缓动函数 ───────────────────────────

def linear(t):
    return t


def ease_in(t):
    """慢起快落。用在「出手」「加速」这类需要爆发的段。"""
    return t * t


def ease_in_cubic(t):
    return t * t * t


def ease_out(t):
    """快起慢停。用在「蓄力到顶点」「收招」这类需要减速的段。"""
    return 1.0 - (1.0 - t) ** 2


def ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t):
    """平滑两端。用在循环动作（待机呼吸、跑动）。"""
    return t * t * (3.0 - 2.0 * t)


def ease_out_back(t, s=1.70158):
    """回弹。用在落地、冲击这类需要"过冲再回来"的段。"""
    t -= 1.0
    return t * t * ((s + 1.0) * t + s) + 1.0


def ease_out_elastic(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * (2.0 * math.pi) / 3.0) + 1.0


# ─────────────────────────── 插值 ───────────────────────────

def lerp(a, b, t):
    return a + (b - a) * t


def lerp_angle(a, b, t):
    """角度插值，走最短弧。

    普通 lerp 从 170° 到 -170° 会走 340°（绕一大圈），
    正确做法是走 20°（穿过 180°）。像素动作的剑经常跨越 ±180，
    不做这个处理会出现"剑突然转一整圈"的怪动作。
    """
    diff = (b - a + 180.0) % 360.0 - 180.0
    return a + diff * t


def lerp_point(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


# ─────────────────────────── 关键帧轨道 ───────────────────────────

ANGLE_KEYS = {"sword_angle"}
POINT_KEYS = {"hand", "sh", "foot_l", "foot_r"}


class Track:
    """一条关键帧轨道：给定归一化时间 t∈[0,1]，返回该时刻的参数字典。

    关键帧格式：[(t, ease_fn, {参数...}), ...]
      t        归一化时间，必须从 0.0 递增到 1.0
      ease_fn  从上一个关键帧到这一个的插值缓动（第一个关键帧的 ease 被忽略）
      params   compose() 的参数子集，缺失的键沿用上一个关键帧
    """

    def __init__(self, keys):
        if not keys:
            raise ValueError("关键帧不能为空")
        if abs(keys[0][0]) > 1e-6:
            raise ValueError("第一个关键帧的时间必须是 0.0")
        if abs(keys[-1][0] - 1.0) > 1e-6:
            raise ValueError("最后一个关键帧的时间必须是 1.0")

        # 补全缺失的键（沿用前一个关键帧的值）
        merged = []
        prev = {}
        for t, ease, params in keys:
            cur = dict(prev)
            cur.update(params)
            merged.append((t, ease, cur))
            prev = cur
        self.keys = merged

    def sample(self, t):
        t = max(0.0, min(1.0, t))
        keys = self.keys

        # 找到 t 所在的区间
        for i in range(1, len(keys)):
            t0, _, p0 = keys[i - 1]
            t1, ease, p1 = keys[i]
            if t <= t1 + 1e-9:
                span = t1 - t0
                local = 0.0 if span <= 1e-9 else (t - t0) / span
                e = (ease or linear)(local)
                return self._interp(p0, p1, e)

        return dict(keys[-1][2])

    @staticmethod
    def _interp(p0, p1, e):
        out = {}
        for k, v1 in p1.items():
            v0 = p0.get(k, v1)
            if k in ANGLE_KEYS:
                out[k] = lerp_angle(float(v0), float(v1), e)
            elif k in POINT_KEYS and isinstance(v0, (tuple, list)):
                out[k] = lerp_point(v0, v1, e)
            elif isinstance(v0, (int, float)) and isinstance(v1, (int, float)):
                out[k] = lerp(float(v0), float(v1), e)
            else:
                # 布尔或离散值：不做插值，过半切换
                out[k] = v0 if e < 0.5 else v1
        return out


def bake(track, count):
    """把轨道烘焙成 count 帧参数。

    时间采样用「均匀分布」而不是「按关键帧密度」：
    因为像素帧的时长是一致的（每帧占同样的屏幕时间），
    采样必须均匀，否则动作会忽快忽慢。
    """
    if count <= 0:
        return []
    if count == 1:
        return [track.sample(0.0)]
    return [track.sample(i / (count - 1)) for i in range(count)]
