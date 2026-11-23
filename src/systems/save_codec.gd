"""存档码：把存档加密成一串可复制粘贴的文本。

## 格式

    AG1.<base64>

`AG1` 是魔数 + 版本前缀（ActGame v1），后面接 Base64。

Base64 解码后的二进制布局：

    [0..16)   IV（16 字节，AES 块大小）
    [16..48)  SHA-256 校验和（32 字节，对「明文」计算）
    [48..]    AES-256-CBC 密文（PKCS#7 padding）

## 为什么这么设计

1. **AES-256-CBC**：Godot 内置 `AESContext` 支持，跨平台（桌面/Web）一致，
   且是可逆的对称加密 —— 正是需求要的"同样的串拷进去能解出来"。

2. **IV 随数据走**：CBC 模式每次加密用随机 IV，保证**同样的存档每次导出
   得到的串都不同**（否则别人能通过字符串比对知道你存档内容）。
   IV 不是秘密，跟密文一起发就行。

3. **SHA-256 对明文算校验**：解密后先验校验和，不匹配就拒绝。
   - 防止有人改密文导致解密出乱码后**崩坏存档**
   - 也给"这不是我们的串"一个明确的失败信号
   注意这是**完整性校验**，不是防作弊：密钥在客户端，谁都能解。

4. **Base64 而不是 hex**：体积小 33%，复制粘贴也短一些。

## 关于密钥

密钥硬编码在客户端里。**这不构成真正的安全** —— 任何人反编译 pck 都能拿到。
它的作用只是：让存档串看起来是乱码，防止玩家直接改 JSON 作弊（比如把心心改成 99）。
对单机离线游戏来说这个强度是合适的；不要把它当成能防住有动机的攻击者。
"""

extends RefCounted

const MAGIC := "AG1."
const MAGIC_BYTES := "ACTGAME1"

# AES-256 密钥（32 字节）。改这个会导致旧存档码失效，需同步升 MAGIC 版本。
const KEY_HEX := "a3f1c07e5b9d2468e8b14f6c2d7a90315f8e2b4c6d1a7e93c5b02f8d4a6e1379"
const IV_LEN := 16
const HASH_LEN := 32
const BLOCK := 16


static func _key() -> PackedByteArray:
	return KEY_HEX.hex_decode()


static func _pad(data: PackedByteArray) -> PackedByteArray:
	"""PKCS#7 填充到 16 字节整数倍。"""
	var n: int = BLOCK - (data.size() % BLOCK)
	var out: PackedByteArray = data.duplicate()
	for i in n:
		out.append(n)
	return out


static func _unpad(data: PackedByteArray) -> PackedByteArray:
	"""去掉 PKCS#7 填充。填充非法则原样返回（由校验和兜底拒绝）。"""
	if data.is_empty():
		return data
	var n: int = data[data.size() - 1]
	if n < 1 or n > BLOCK or n > data.size():
		return data
	return data.slice(0, data.size() - n)


static func _sha256(data: PackedByteArray) -> PackedByteArray:
	var h := HashingContext.new()
	h.start(HashingContext.HASH_SHA256)
	h.update(data)
	return h.finish()


static func encode(plain_text: String) -> String:
	"""把 JSON 文本加密成存档码。失败返回空串。"""
	var plain: PackedByteArray = plain_text.to_utf8_buffer()
	if plain.is_empty():
		return ""

	var crypto := Crypto.new()
	var iv: PackedByteArray = crypto.generate_random_bytes(IV_LEN)
	var digest: PackedByteArray = _sha256(plain)

	var ctx := AESContext.new()
	var err: int = ctx.start(AESContext.MODE_CBC_ENCRYPT, _key(), iv)
	if err != OK:
		printerr("存档码加密失败：AESContext.start err=", err)
		return ""
	var ct: PackedByteArray = ctx.update(_pad(plain))
	ctx.finish()

	# 拼装：iv + hash + ciphertext
	var blob := PackedByteArray()
	blob.append_array(iv)
	blob.append_array(digest)
	blob.append_array(ct)

	return MAGIC + Marshalls.raw_to_base64(blob)


static func decode(code: String) -> Dictionary:
	"""把存档码解回 JSON 文本。

	返回 {"ok": bool, "text": String, "error": String}
	"""
	var s := code.strip_edges()
	# 允许玩家复制时带了换行/空格，也允许漏了前缀（宽松处理）
	if s.begins_with(MAGIC):
		s = s.substr(MAGIC.length())
	if s.is_empty():
		return {"ok": false, "text": "", "error": "存档码为空"}

	var blob: PackedByteArray = Marshalls.base64_to_raw(s)
	if blob.size() < IV_LEN + HASH_LEN + BLOCK:
		return {"ok": false, "text": "", "error": "存档码长度不足，可能复制不完整"}

	var iv: PackedByteArray = blob.slice(0, IV_LEN)
	var expect_hash: PackedByteArray = blob.slice(IV_LEN, IV_LEN + HASH_LEN)
	var ct: PackedByteArray = blob.slice(IV_LEN + HASH_LEN)
	if ct.size() % BLOCK != 0:
		return {"ok": false, "text": "", "error": "存档码已损坏（密文长度异常）"}

	var ctx := AESContext.new()
	var err: int = ctx.start(AESContext.MODE_CBC_DECRYPT, _key(), iv)
	if err != OK:
		return {"ok": false, "text": "", "error": "解密初始化失败"}
	var pt_padded: PackedByteArray = ctx.update(ct)
	ctx.finish()

	var plain: PackedByteArray = _unpad(pt_padded)
	# 完整性校验：必须在解析 JSON 之前做，避免拿着乱码去 parse
	if _sha256(plain) != expect_hash:
		return {"ok": false, "text": "", "error": "校验失败：存档码被改动过或已损坏"}

	return {"ok": true, "text": plain.get_string_from_utf8(), "error": ""}
