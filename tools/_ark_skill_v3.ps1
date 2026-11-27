# 构建参考图 data URI 并调用 skill 的 generate.js（key 走 ark_key.txt）
$ErrorActionPreference = "Continue"
$root = "D:\Program Files\Projects\personal\actGame"
$skill = "$root\.agents\skills\byted-ark-seedream-skill"
$keyFile = "$root\tools\ark_key.txt"
$key = [System.IO.File]::ReadAllText($keyFile).Trim()
