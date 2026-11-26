# 音频素材来源与许可证（AUDIO-CREDITS）

本项目使用的全部音频素材均来自 OpenGameArt.org 的**可商用免费许可**（CC0 / Public Domain）。
按素材列出来源、作者与许可证，修改或替换时请同步更新本文件。

## BGM

| 文件 | 用途 | 来源页 | 作者 | 许可证 |
|---|---|---|---|---|
| `assets/audio/bgm/bgm_courtyard.mp3` | 教程庭院 BGM（循环） | https://opengameart.org/content/foreboding-pixels | Dark Primitives | CC0（页内标注 Public Domain / CC0） |
| `assets/audio/bgm/bgm_piano_a.ogg` | 菜单 BGM（忧郁钢琴主版） | https://opengameart.org/content/melancholy-piano-bgm | Maivash | CC0 |
| `assets/audio/bgm/bgm_piano_b.ogg` | 菜单 BGM 备选（变奏） | 同上 | 同上 | CC0 |
| `assets/audio/bgm/bgm_boss_ambient.ogg` | BOSS 房环境层 | https://opengameart.org/content/dark-cavern-ambient | Silvermoot | CC0 |

## SFX

| 文件 | 用途 | 来源页 | 作者 | 许可证 |
|---|---|---|---|---|
| `sfx_swing_light.wav` | 轻攻击挥砍 | https://opengameart.org/content/swishes-sound-pack | dland | CC0 |
| `sfx_swing_heavy.wav` | 重攻击挥砍 | 同上 | 同上 | CC0 |
| `sfx_dash.wav` | 闪避 | 同上 | 同上 | CC0 |
| `sfx_enemy_hurt.wav` | 敌人受击 | https://opengameart.org/content/rpg-sound-pack | North上升（hrspw） | Public Domain |
| `sfx_enemy_die.wav` | 敌人死亡 | 同上 | 同上 | Public Domain |
| `sfx_hurt_player.wav` | 玩家受伤 | 同上 | 同上 | Public Domain |
| `sfx_parry.wav` | 弹反成功 | 同上 | 同上 | Public Domain |
| `sfx_pickup.wav` | 拾取道具 | 同上 | 同上 | Public Domain |
| `sfx_pickup_coin.wav` | 拾取备选（金币） | 同上 | 同上 | Public Domain |

## 接入说明

- 播放核心：`src/systems/audio_manager.gd`（bootstrap 挂载为 `AudioMgr`）
  - BGM：`AudioMgr.set_zone("menu" / "courtyard" / "boss")`，1.2s 交叉淡入淡出
  - SFX：`AudioMgr.play_sfx(key)`，8 池轮转避免同音效互相打断
- 场景切换：bootstrap `_process` 每 0.5s 检查玩家 x（< 1560 庭院 / ≥ 1560 BOSS 房）
- 音频总线：默认 Master；BGM/SFX 各自 bus 名预留（Godot Audio 面板建 BGM/SFX 总线即可分轨调音）

## 许可证合规

CC0 与 Public Domain 素材可商用、可修改、无需署名；本文件署名是**礼节性归档**，
便于日后溯源。若未来引入 CC-BY 素材，必须在此表登记作者并在游戏内 about 页展示。
