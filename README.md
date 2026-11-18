# 《缀》actGodotGame-iori

可爱二次元风格的 **Q 版像素横版类银河恶魔城**动作游戏，Godot 4.7 实现。

主角「织」是一名少女缝补匠，用线与针战斗。每一次变强都是学会一种新的「缝法」，而每一种缝法都在改写地图本身——**能力既是战斗词汇，也是地图词汇**。

## 当前进度

已完成一个可跑通的垂直切片骨架：

- **移动手感**：跑、跳（大跳 / 小跳）、Coyote Time、跳跃输入缓冲、急转向加成
- **轻攻击四连连段树**：砍 → 回斩 → 下劈 → 终结，每段有独立的时长、判定框、伤害与刀光
- **闪避**：冲刺位移 + 无敌帧 + 完美闪避判定（可触发子弹时间）
- **动画**：待机 / 跑 / 跳 / 落地 / 四段攻击 / 闪避，共 45 帧，全部程序化生成
- **战斗反馈**：命中判定、受击闪白、击退、落地阴影

验证：19 项自动化测试全部通过（10 项移动 + 9 项战斗）。

## 运行

需要 [Godot 4.7+](https://godotengine.org/download)。

```bash
# 用编辑器打开
godot --path .

# 直接运行（进入灰盒测试房）
godot --path .
```

仓库里不含 Godot 的导入缓存（`.godot/`），首次打开会自动重新导入资源，稍等片刻即可。

## 在线试玩（浏览器）

推送到 `main` 后，GitHub Actions 会自动导出 Web 版并发布到 GitHub Pages：

**https://kurilx.github.io/actGodotGame-iori/** ← 点击即玩

- 工作流在 [.github/workflows/deploy-web.yml](.github/workflows/deploy-web.yml)，每次推送自动构建，也可在 Actions 页手动触发
- 首次启用需在仓库 **Settings → Pages → Source** 选择 **GitHub Actions**
- 导出用官方 Web 模板，**单线程模式**（`variant/thread_support=false`），因此不需要服务器配置 `SharedArrayBuffer` 交叉源隔离头，GitHub Pages 直接可跑
- 渲染器必须是 `gl_compatibility`（WebGL 2.0）；本项目一开始就用的兼容渲染器，无需改动

构建产物不进仓库，由 CI 每次现构建，仓库体积保持在 ~10MB。

## 操作

| 动作 | 键盘 | 手柄 |
|---|---|---|
| 左右移动 | `A` / `D` | 十字键 / 左摇杆 |
| 跳跃 | `空格` | A |
| 攻击（连按出连段） | `J` | X |
| 闪避 | `K` | B |

出生点右侧有两个训练木桩，可以试连段和闪避。

## 技术规格

| 项目 | 值 |
|---|---|
| 内部分辨率 | 480 × 270 |
| 窗口 | 1440 × 810（整数 3× 缩放） |
| 主角身高 | 48 px（Q 版 2.5 头身） |
| 瓦片 | 12 × 12 |
| 色板 | 28 色硬上限 |
| 物理帧率 | 120 Hz |

**像素游戏的三个必开设置**（已在 `project.godot` 配好）：

```
display/window/stretch/scale_mode = integer
rendering/2d/snap/snap_2d_transforms_to_pixel = true
rendering/2d/snap/snap_2d_vertices_to_pixel = true
```

不开会怎样：非整数缩放导致像素大小不均、角色落在半像素位置抖动、观感直接崩。

## 动画与美术是程序化生成的

本项目的所有美术资源**不是手绘也不是 AI 直接产出**，而是由脚本从一张 48px 概念图派生：

```bash
python tools/make_placeholder_art.py   # 概念图 → 48px 占位精灵（去背景、量化到 28 色）
python tools/make_animation.py         # 单帧 → 四套基础动画 + 四段攻击 + 闪避
python tools/split_frames.py           # 横排图集 → 单帧 PNG（Godot 读的是这个）
python tools/add_contact_shadow.py     # 给脚底压暗，强化"踩在地上"的观感
python tools/make_slash_fx.py          # 生成四段刀光贴图
godot --headless --path . --import     # 让 Godot 重新导入
```

**顺序不能乱**：游戏引用的是 `art/characters/ori/frames/` 下的单帧，横排图集只是中间产物。只跑 `make_animation.py` 不生效。

## 自动化测试

```bash
godot --headless --path . --script tools/verify_headless.gd   # 移动手感 10 项
godot --headless --path . --script tools/verify_combat.gd     # 战斗系统 9 项
```

两个脚本都不需要窗口，退出码 0 表示全通过，适合接 CI。

## 目录结构

```
.
├── project.godot              # 480x270 / 整数缩放 / 像素吸附 / 120Hz
├── scenes/
│   ├── bootstrap.tscn         # 启动场景
│   ├── player/player.tscn     # CharacterBody2D + 45 帧 SpriteFrames + 判定框 + 阴影
│   └── rooms/room_greybox.tscn
├── src/
│   ├── bootstrap.gd
│   ├── player/
│   │   ├── player.gd          # 状态机 + 连段树 + 闪避（核心）
│   │   ├── attack_hitbox.gd   # 攻击判定框
│   │   └── shadow.gd          # 落地阴影
│   └── world/
│       ├── room_greybox.gd    # 数据驱动地形 + 相机
│       ├── training_dummy.gd  # 训练木桩
│       └── slash_sprite.gd    # 刀光播放器
├── art/
│   ├── palette.gpl/.gd/.hex.txt    # 28 色板（Aseprite 可直接导入）
│   ├── characters/ori/frames/      # 45 张单帧（游戏实际读取）
│   ├── fx/slash/                   # 12 张刀光贴图
│   └── concept/                    # 概念稿（生成占位素材的输入）
├── tools/                     # 素材生成 + 测试脚本
└── docs/
    ├── 01-游戏规划.md          # 玩法、BOSS、里程碑
    ├── 02-像素美术规范.md      # 尺度、色板、Q 版比例、动画帧预算
    └── 03-工程骨架说明.md      # 实现细节 + 13 条踩坑记录
```

## 设计文档

三份文档在 `docs/` 下：

- **[01-游戏规划.md](docs/01-游戏规划.md)** — 核心循环、主角设定、动作数值、BOSS 三阶段设计、4 周里程碑
- **[02-像素美术规范.md](docs/02-像素美术规范.md)** — 为什么是 480×270、28 色板、Q 版比例与动作辨识度补偿
- **[03-工程骨架说明.md](docs/03-工程骨架说明.md)** — 动画管线、测试说明、**13 条实打实的实现坑**

第 13 条坑值得单独提：`SpriteFrames` 里写 `region` 字段**不会裁剪贴图**，整条图集会被当成一整张画出来（表现为画面里并排出现多个角色，间隔正好等于帧宽）。我一开始误判成窗口残影，花了很多时间查交换链，全查错了。

## 下一步

- 敌人 AI 与首个 BOSS「瓷面的守夜人」（三阶段，P2 考弹反、P3 考缝缀）
- 「缝缀」能力：缝合出的平台是真实物理体，能站、能挡弹道、能被 BOSS 撞碎
- 房间切换与存档点
- 音乐与音效

## 授权

代码与美术资源均为本项目原创。Godot Engine 遵循其自身的 MIT 协议。
