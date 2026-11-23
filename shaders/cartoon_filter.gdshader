shader_type canvas_item;

// 卡通滤镜：把整个画面往"动画赛璐璐"的方向推。
//
// ## 为什么用 canvas_item + BackBufferCopy 而不是屏幕后处理
//
// 项目跑的是 `gl_compatibility` 渲染器（为了 Web 导出兼容性），
// 它**不支持** Forward+ 的屏幕后处理（WorldEnvironment / 后处理材质）。
// 可行的替代是一条 CanvasLayer + ColorRect 全屏着色器，
// 用 SCREEN_TEXTURE 读当前画面再重新着色。
//
// ## 四层处理
//
// 1. **饱和度提升**：让颜色更"纯"，卡通片喜欢高饱和
// 2. **对比度提升 + 轻微提亮**：强化明暗分界，去掉灰调
// 3. **边缘压暗（vignette）**：四周轻微变暗，把视线收进画面中心
// 4. **色阶量化**：把每种通道压到较少的台阶数 —— 这是"卡通感"的核心，
//    它让渐变色块化，模拟赛璐璐的平涂
//
// **不做**：模糊、发光（bloom）。两者在像素画上会糊掉硬边，
// 是这个项目明确禁止的（docs/02 规范：不做抗锯齿，边缘必须硬切）。

// **Godot 4 不再提供内置 SCREEN_TEXTURE**，必须显式声明这个 uniform。
// 用错会编译失败（报 "add 'uniform sampler2D SCREEN_TEXTURE'"），
// 而且节点看起来"正常"，只有画面不变 —— 很难发现。
uniform sampler2D SCREEN_TEXTURE : hint_screen_texture,
	filter_linear_mipmap;

uniform float saturation : hint_range(0.8, 2.0) = 1.16;
uniform float contrast : hint_range(0.8, 2.0) = 1.10;
uniform float brightness : hint_range(-0.2, 0.3) = 0.055;
// 色阶：每通道的台阶数。越大越接近原图，越小越"海报化"。
uniform float color_steps : hint_range(4.0, 32.0) = 14.0;
// 边缘压暗强度
uniform float vignette : hint_range(0.0, 1.0) = 0.0;
// 暖色偏置：卡通片常用暖调，让画面更"软"
uniform vec3 warm_tint : source_color = vec3(0.998, 1.0, 1.004);
uniform float mix_amount : hint_range(0.0, 1.0) = 1.0;

void fragment() {
	vec3 src = texture(SCREEN_TEXTURE, SCREEN_UV).rgb;

	// ── 1. 饱和度 ──
	float lum = dot(src, vec3(0.299, 0.587, 0.114));
	vec3 c = mix(vec3(lum), src, saturation);

	// ── 2. 对比度 + 提亮 ──
	//
	// **必须提亮**：只加对比度会让整体变暗（暗部压得更低），
	// 实测中心亮度从 64 掉到 57，画面显得发闷。
	// 卡通风格要"明亮通透"，所以先提亮再拉对比。
	c = (c - 0.45) * contrast + 0.45 + brightness;

	// ── 3. 暖色调 ──
	c *= warm_tint;

	// ── 4. 边缘压暗 ──
	vec2 d = SCREEN_UV - vec2(0.5);
	float r = length(d) * 1.42;
	float v = smoothstep(0.55, 1.05, r);
	c *= (1.0 - v * vignette);

	// ── 5. 色阶量化（**必须是最后一步**）──
	//
	// 这条链上原始色是 49 色。只要有任何**连续运算**放在量化之后，
	// 每个像素就会得到略微不同的值，整屏色数会暴涨。
	// 实测把 warm_tint / vignette 放在量化后面，色数从 49 涨到 439。
	//
	// 所以：所有连续运算（饱和度、对比、暖调、压暗）全部先算完，
	// **最后一次性量化**，这样输出色数才收敛。
	float steps = max(4.0, color_steps);
	c = clamp(c, 0.0, 1.0);
	c = floor(c * steps + 0.5) / steps;

	// ── 6. 和原图混合 ──
	// mix_amount 是连续值，但它只用于"关闭/调节强度"，
	// 正常游玩时恒为 1.0，不会引入额外颜色。
	vec3 out_c = mix(src, c, mix_amount);

	COLOR = vec4(out_c, 1.0);
}
