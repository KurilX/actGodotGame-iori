# 构建 base64 参考图 JSON 并调用 skill 的 generate.js
$ErrorActionPreference = "Continue"
$root = "D:\Program Files\Projects\personal\actGame"
$skill = "$root\.agents\skills\byted-ark-seedream-skill"
$key = "ARK_KEY_REDACTED"

function To-DataUri($path) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $b64 = [System.Convert]::ToBase64String($bytes)
    return 'data:image/png;base64,' + $b64
}

$node = "D:\tools\nodejs\node-v24.19.0-win-x64\node.exe"

# ── 1. 基底立绘 ──
$ref = To-DataUri "$root\docs\refs\ai\参考风格.png"
$refJson = '["' + $ref + '"]'
$basePrompt = '以这张参考图的像素画风格与可爱程度为基准：完全保留它的大色块画法、简约五官（黑方眼、小嘴）、头身比例、像素颗粒密度和干净程度。只替换：蓝紫发改为绿色短发头顶丸子发髻，服装改为深蓝色小斗篷加白色内衬，背景改为纯黑色。正面全身站姿立绘，像素风，无渐变无抗锯齿'
& $node "$skill\scripts\generate.js" --model flash --prompt $basePrompt --reference_images $refJson --size 2K --optimize false --api_key $key > "$env:TEMP\ark_base_out.txt" 2>&1
Get-ChildItem "C:\Users\zepeng.huang\Desktop\Seedream-Images\2026-11-27" -Filter *.jpg | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object {
    Copy-Item $_.FullName "$root\docs\refs\ai\ori_cachiu_v2_raw.jpeg" -Force
    Write-Output ("base saved: " + $_.Name + " " + $_.Length)
}
