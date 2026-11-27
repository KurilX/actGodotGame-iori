// 桥接 V2：不走 spawn 命令行（ENAMETOOLONG），直接 require generate.js 内部逻辑。
// generate.js 是 CLI —— 我们用 child_process 的 stdin 传参？也不行。
// 最终方案：把参考图压到 512px（base64 ~70KB），仍超 32K。
//   → 唯一可行：临时 HTTP 服务（media-security 限制公网 URL，本地 127.0.0.1 会被拒）
//   → 或者：修改调用方式：spawn 传参时用「参数文件」？generate.js 不支持。
// 所以桥接 v2 = 把 generate.js 作为模块加载不可行（它是自执行 CLI），
// 改成：spawn 用 shell:false + 把 reference_images 写进临时文件，
// generate.js 支持 --reference_images 文件路径吗？grep 一下没有。
// 结论：桥接改为「复制 generate.js 为本地模块调用」太重。
// 最简单可靠：参考图缩到 384px JPEG（base64 ~25KB < 32K 命令行限制）。
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = "D:\\Program Files\\Projects\\personal\\actGame";
const SKILL = path.join(ROOT, ".agents", "skills", "byted-ark-seedream-skill");
// API key：环境变量 ARK_API_KEY 或 tools/ark_key.txt（gitignored），不入库
const API_KEY = process.env.ARK_API_KEY ||
  (() => {
    const kf = path.join(ROOT, "tools", "ark_key.txt");
    return fs.existsSync(kf) ? fs.readFileSync(kf, "utf-8").trim() : "";
  })();

const args = process.argv.slice(2);
const [promptFile, refList, outDir, optimize, gridPx] = args;
const prompt = fs.readFileSync(promptFile, "utf-8").trim();

// 用 Python 预处理参考图（缩到 384px jpeg）后 base64
function toSmallDataUri(p) {
  const b64 = fs.readFileSync(p).toString("base64");
  const ext = path.extname(p).toLowerCase();
  const mime = ext === ".jpeg" || ext === ".jpg" ? "jpeg" : "png";
  return `data:image/${mime};base64,${b64}`;
}

const refs = refList.split("|").filter(Boolean).map(toSmallDataUri);

const genArgs = [
  path.join(SKILL, "scripts", "generate.js"),
  "--model", "flash",
  "--prompt", prompt,
  "--reference_images", JSON.stringify(refs),
  "--size", "2K",
  "--optimize", optimize || "false",
  "--api_key", API_KEY,
];

const child = spawn(process.execPath, genArgs, { cwd: SKILL });
let out = "";
child.stdout.on("data", (d) => (out += d.toString()));
child.stderr.on("data", (d) => (out += d.toString()));
child.on("close", (code) => {
  fs.mkdirSync(outDir, { recursive: true });
  const m = out.match(/本地保存路径:\s*(\S+)/);
  if (m) {
    const dst = path.join(outDir, path.basename(m[1]));
    fs.copyFileSync(m[1], dst);
    console.log("SAVED " + dst + " " + fs.statSync(dst).size);
  } else {
    console.log("FAILED code=" + code);
    console.log(out.slice(-600));
  }
});
