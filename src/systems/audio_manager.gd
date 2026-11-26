"""AudioManager：BGM 分场景切换 + SFX 播放。

## 设计

单例 Node（bootstrap 加入 root），两个子节点：
  · BgmPlayer   AudioStreamPlayer，bus=BGM，场景切换时 crossfade
  · SfxPool     8 个 AudioStreamPlayer 池（同一 SFX 连发不互相打断），bus=SFX

## 场景 → BGM 映射

  教程庭院（x < 1560）  → bgm_courtyard
  BOSS 房（x >= 1560）  → bgm_boss_ambient
  菜单                  → bgm_piano_a

## 用法

  AudioMgr.play_sfx("swing_light")
  AudioMgr.set_zone("boss")     # / "courtyard" / "menu"
"""

extends Node

const SFX := {
    "swing_light": "res://assets/audio/sfx/sfx_swing_light.wav",
    "swing_heavy": "res://assets/audio/sfx/sfx_swing_heavy.wav",
    "dash": "res://assets/audio/sfx/sfx_dash.wav",
    "hurt_player": "res://assets/audio/sfx/sfx_hurt_player.wav",
    "enemy_hurt": "res://assets/audio/sfx/sfx_enemy_hurt.wav",
    "enemy_die": "res://assets/audio/sfx/sfx_enemy_die.wav",
    "pickup": "res://assets/audio/sfx/sfx_pickup.wav",
    "parry": "res://assets/audio/sfx/sfx_parry.wav",
}

const BGM := {
    "courtyard": "res://assets/audio/bgm/bgm_courtyard.mp3",
    "boss": "res://assets/audio/bgm/bgm_boss_ambient.ogg",
    "menu": "res://assets/audio/bgm/bgm_piano_a.ogg",
}

const FADE := 1.2        # BGM 交叉淡入淡出秒数
const SFX_POOL := 8

var _bgm_player: AudioStreamPlayer
var _sfx_players: Array[AudioStreamPlayer] = []
var _sfx_streams := {}
var _bgm_streams := {}
var _current_zone := ""
var _fade_tween: Tween


func _ready() -> void:
	# 音频总线：BGM/SFX 必须真实存在才能赋给 player.bus。
	# 项目没有 default_bus_layout.tres，直接在运行时创建——
	# 不存在的 bus 会报 "Invalid bus index -1" 且音效整条哑掉（实测）。
	if AudioServer.get_bus_index("BGM") == -1:
		var idx := AudioServer.bus_count
		AudioServer.add_bus(idx)
		AudioServer.set_bus_name(idx, "BGM")
		AudioServer.set_bus_send(idx, "Master")
	if AudioServer.get_bus_index("SFX") == -1:
		var idx2 := AudioServer.bus_count
		AudioServer.add_bus(idx2)
		AudioServer.set_bus_name(idx2, "SFX")
		AudioServer.set_bus_send(idx2, "Master")

	_bgm_player = AudioStreamPlayer.new()
	_bgm_player.name = "Bgm"
	_bgm_player.bus = "BGM"
	add_child(_bgm_player)

	for i in SFX_POOL:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		add_child(p)
		_sfx_players.append(p)

	for key in SFX:
		if ResourceLoader.exists(SFX[key]):
			_sfx_streams[key] = load(SFX[key])
	for key in BGM:
		if ResourceLoader.exists(BGM[key]):
			_bgm_streams[key] = load(BGM[key])


func play_sfx(key: String, volume_db: float = 0.0) -> void:
	if not _sfx_streams.has(key):
		return
	# 找一个空闲播放器（最久没在响的也行，简化为第一个 !playing）
	for p in _sfx_players:
		if not p.playing:
			p.stream = _sfx_streams[key]
			p.volume_db = volume_db
			p.play()
			return
	# 池满：抢占第一个
	_sfx_players[0].stream = _sfx_streams[key]
	_sfx_players[0].volume_db = volume_db
	_sfx_players[0].play()


func set_zone(zone: String) -> void:
	if zone == _current_zone:
		return
	_current_zone = zone
	if not _bgm_streams.has(zone):
		return
	var stream: AudioStream = _bgm_streams[zone]

	# 交叉淡入淡出：旧的淡出后切流播放，新的淡入
	if _fade_tween and _fade_tween.is_valid():
		_fade_tween.kill()
	_fade_tween = create_tween()
	if _bgm_player.playing:
		_fade_tween.tween_property(_bgm_player, "volume_db", -40.0, FADE * 0.5)
	_fade_tween.tween_callback(func() -> void:
		_bgm_player.stream = stream
		_bgm_player.volume_db = -40.0
		_bgm_player.play())
	_fade_tween.tween_property(_bgm_player, "volume_db", 0.0, FADE)


func stop_bgm() -> void:
	_current_zone = ""
	if _bgm_player.playing:
		_bgm_player.stop()
