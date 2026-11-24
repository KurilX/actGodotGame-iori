# 参考地图来源

这些是 **Hollow Knight 的官方区域地图剪影**，用作关卡设计对照参考。

## 来源

仓库 `SFGrenade/AdditionalMaps`（Hollow Knight 地图模组），
通过 GitHub raw 下载：

    https://raw.githubusercontent.com/SFGrenade/AdditionalMaps/master/Resources/...

| 文件 | 原路径 |
|---|---|
| `hk_white_palace_1.png` | `Resources/White_Palace/RWP01.png` |
| `hk_white_palace_2.png` | `Resources/White_Palace/RWP02.png` |
| `hk_white_palace_3.png` | `Resources/White_Palace/RWP03.png` |
| `hk_white_palace_5.png` | `Resources/White_Palace/RWP05.png` |
| `hk_godhome_1.png` | `Resources/Godhome/RGH0.png` |

`hk_maps_grid.png` 是本项目用 `docs/refs` 下的图片拼的对照表。

## 为什么用它们

这些剪影能直接看出 Hollow Knight 的空间组织手法：

- **竖直攀爬的终点总有落点**：塔顶要么接独立房间、要么接横向平台，
  从不出现"爬上去看一眼再跳回来"的死端。
- **垂直与横向交替**：竖井两侧会伸出横向支路，形成分层，而不是一根光杆。
- **房间边缘不平直**：底部有锯齿状地形，避免"方块感"。

## 怎么用

`tools/review_level.py` 会把 `docs/refs/*.png` 作为图片输入传给 LLM
（实测网关支持 image block），让它**看着真实地图**评价我们的关卡，
而不是只凭文字描述想象。

## 注意

这些图片版权属 Team Cherry / Hollow Knight，仅作**内部设计参考**，
不进入游戏发布物，不对外分发。
