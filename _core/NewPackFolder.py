# -*- coding: utf-8 -*-
"""
NewPackFolder ---- Unity 打包工作目录一键创建
================================================

输入：teambition 标题整串，例如
    [vivo-rpk]《模拟火车司机驾驶》(地铁模拟器3D) 正式包 厦门-吴伟

产出（默认根目录 D:\\UnityOutput）：
    D:\\UnityOutput\\<运营方拼音>\\<平台>\\<游戏名拼音>\\
        V1\\                    <- Unity 工程文件导出目录
        <平台批处理>.bat         <- 从 D:\\Resources\\111\\批处理 复制
        certificate.pem         <- 从 D:\\Resources\\GameSign 搜索并复制
        private.pem

规则要点：
  * 平台取自 [] 内第一段：vivo / oppo / xiaomi / honor / huawei ...
  * 游戏名取自《》
  * 原工程名取自 ()  ->  仅用于在 GameSign 里搜索签名
  * 尾部 "厦门-吴伟"  ->  "-" 前是运营方(厦门)，"-" 后是个人名(吴伟，不建目录)
  * 中文 -> 驼峰拼音：模拟火车司机驾驶 => MoNiHuoCheSiJiJiaShi
  * 签名文件放进"游戏名根目录"（与 V1 同级），不放进 V1
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time


# --------------------------------------------------------------------------
# 输出编码（Windows 控制台）
# --------------------------------------------------------------------------
def _force_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


_force_utf8()

try:
    from pypinyin import lazy_pinyin, load_phrases_dict
except Exception:
    print("[X] 未检测到 pypinyin。请先执行：  python -m pip install pypinyin")
    sys.exit(1)

# 多音字纠错：默认读音不对的地名/专名。发现新的错读就往这里加。
PHRASE_OVERRIDES = {
    "厦门": [["xià"], ["mén"]],   # 默认会给成 shà men
}
try:
    load_phrases_dict(PHRASE_OVERRIDES)
except Exception as _e:
    print("[!] 多音字短语表加载失败：%s" % _e)


# --------------------------------------------------------------------------
# 彩色输出
#   真终端下自动开（Windows 需打开 VT 处理）；重定向到文件时自动关。
#   想强制控制：环境变量 NPF_COLOR=1 / 0，或命令模式里的 color 命令。
# --------------------------------------------------------------------------
_ANSI = {
    "reset": "\033[0m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
    "gray": "\033[90m",
    "b_red": "\033[91m", "b_green": "\033[92m", "b_yellow": "\033[93m",
    "b_blue": "\033[94m", "b_magenta": "\033[95m", "b_cyan": "\033[96m",
}


def _want_color():
    v = os.environ.get("NPF_COLOR", "").strip().lower()
    if v in ("0", "off", "no", "false"):
        return False
    if v in ("1", "on", "yes", "true"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if k32.GetConsoleMode(handle, ctypes.byref(mode)):
            k32.SetConsoleMode(handle, mode.value | 0x0004)   # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return True
    except Exception:
        pass
    return False


COLOR = _want_color()


def col(tag, s):
    if not COLOR:
        return "%s" % s
    return _ANSI.get(tag, "") + ("%s" % s) + _ANSI["reset"]


def c_path(s):   return col("b_blue", s)       # 目录 / 路径
def c_game(s):   return col("b_green", s)      # 游戏名 / 游戏目录
def c_op(s):     return col("b_yellow", s)     # 运营方
def c_plat(s):   return col("b_magenta", s)    # 平台
def c_key(s):    return col("cyan", s)         # 命令 / 配置项
def c_ok(s):     return col("green", s)        # 齐全 / 成功
def c_warn(s):   return col("yellow", s)       # 提醒 / 不完整
def c_err(s):    return col("red", s)          # 缺失 / 失败
def c_dim(s):    return col("gray", s)         # 次要信息


def set_color(on):
    global COLOR
    COLOR = bool(on)


# --------------------------------------------------------------------------
# 默认配置（可用命令行参数覆盖）
# --------------------------------------------------------------------------
DEFAULTS = {
    "root": r"D:\UnityOutput",
    "sign_root": r"D:\Resources\GameSign",
    "batch_src": r"D:\Resources\111\批处理",
}

# 平台关键字 -> (目录名, 批处理文件名)  批处理为 None 表示该平台没有批处理
PLATFORM_MAP = {
    "vivo":    ("Vivo",    ".PackNewVivoRpk.bat"),
    "oppo":    ("OPPO",    ".oppopack.bat"),
    "xiaomi":  ("XiaoMi",  ".PackXiaoMi.bat"),
    "mi":      ("XiaoMi",  ".PackXiaoMi.bat"),
    "小米":    ("XiaoMi",  ".PackXiaoMi.bat"),
    "honor":   ("RongYao", ".PackRongYao.bat"),
    "honour":  ("RongYao", ".PackRongYao.bat"),
    "rongyao": ("RongYao", ".PackRongYao.bat"),
    "荣耀":    ("RongYao", ".PackRongYao.bat"),
    "huawei":  ("HuaWei",  None),
    "华为":    ("HuaWei",  None),
}

# 旧的、已废弃的批处理文件（禁止误用）
DEPRECATED_BATCH = {".packoppo.bat"}

# 各平台「成品包」(*.rpk 编译产物) 相对游戏目录的位置。
# 华为没有固定子目录，习惯直接把 rpk 放在 V1 同目录（游戏根目录）。
# 新增平台时在这里补一行即可。
DIST_PATH = {
    "Vivo":    r"V1\webgl_vivo\dist",
    "OPPO":    r"V1\quickgame\dist",
    "RongYao": r"V1\webgl_qg\dist",
    "XiaoMi":  r"V1\MiQGameBuild\MiQGame\dist",
    "HuaWei":  "",
}

# 压根没有批处理的平台（这些平台不用报「缺 批处理」）
NO_BATCH_PLATFORMS = {d for (d, b) in PLATFORM_MAP.values() if not b}


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def hr(ch="=", n=64):
    print(ch * n)


_INVISIBLE = "\ufeff\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060"


def clean_input(s):
    """去掉 BOM / 零宽字符等隐形字符，避免污染文件名。"""
    if not s:
        return ""
    for ch in _INVISIBLE:
        s = s.replace(ch, "")
    return s.strip()


def ask(prompt, default="", auto=False, allow_empty=True):
    if auto:
        return default
    try:
        s = clean_input(input(prompt))
    except EOFError:
        return default
    if not s:
        if not allow_empty and not default:
            return ask(prompt, default, auto, allow_empty)
        return default
    return s


def is_cjk(ch):
    return "\u4e00" <= ch <= "\u9fff"


def to_camel(text):
    """中文 -> 驼峰拼音；英文数字原样保留；其他符号丢弃。
    模拟火车司机驾驶 -> MoNiHuoCheSiJiJiaShi
    海上生存60s      -> HaiShangShengCun60s
    """
    if not text:
        return ""
    out = []
    buf = ""

    def flush():
        nonlocal buf
        if not buf:
            return
        # 整段连续中文一起转，才能命中 PHRASE_OVERRIDES 里的多音字短语
        for py in lazy_pinyin(buf):
            if py:
                out.append(py[0].upper() + py[1:])
        buf = ""

    for ch in text:
        if is_cjk(ch):
            buf += ch
        else:
            flush()
            if ch.isalnum():
                out.append(ch)
    flush()
    return "".join(out)


def norm(s):
    """归一化：全角括号转半角、去空白，便于解析。"""
    if not s:
        return ""
    s = clean_input(s)
    table = {"（": "(", "）": ")", "【": "[", "】": "]", "：": ":",
             "－": "-", "—": "-", "–": "-", "　": " "}
    for k, v in table.items():
        s = s.replace(k, v)
    return s.strip()


# --------------------------------------------------------------------------
# 解析 teambition 标题
# --------------------------------------------------------------------------
def parse_title(title):
    t = norm(title)
    info = {"raw": title, "platform_raw": None, "game": None,
            "project": None, "operator": None, "person": None, "pack_type": None}

    m = re.search(r"\[([^\]]*)\]", t)
    if m:
        info["platform_raw"] = m.group(1).strip()

    mg = re.search(r"《([^》]*)》", t)
    if mg:
        info["game"] = mg.group(1).strip()

    # 原工程名：优先取《》之后的第一个圆括号，没有则取全文第一个
    game_end = mg.end() if mg else 0
    mp = re.search(r"\(([^)]*)\)", t[game_end:]) or re.search(r"\(([^)]*)\)", t)
    if mp:
        info["project"] = mp.group(1).strip() or None

    # 尾部：去掉 《》 与 () 后的剩余文本
    tail = t
    tail = re.sub(r"《[^》]*》", " ", tail)
    tail = re.sub(r"\([^)]*\)", " ", tail)
    tail = re.sub(r"\[[^\]]*\]", " ", tail)
    tokens = [x for x in re.split(r"\s+", tail) if x]

    # 取最后一段作为 "运营方-人名"
    for tok in reversed(tokens):
        if "-" in tok:
            op, _, person = tok.partition("-")
            info["operator"] = op.strip() or None
            info["person"] = person.strip() or None
            break
    if info["operator"] is None and tokens:
        # 没有 "-" 时，退化为最后一个 token 当运营方
        info["operator"] = tokens[-1].strip() or None

    # 包类型：尾部里除去"运营方-人名" token 之外的中文词（正式包/测试包 ...）
    pk = [x for x in tokens if "-" not in x and x != info["operator"]]
    pk = [x for x in pk if re.search(r"[\u4e00-\u9fff]", x)]
    if pk:
        info["pack_type"] = pk[-1]

    return info


def resolve_platform(platform_raw, auto):
    """vivo-rpk / oppo / 小米 ... -> (目录名, 批处理文件名, 原始关键字)"""
    if not platform_raw:
        return None, None, None
    seg = re.split(r"[-_/]", platform_raw)[0].strip().lower()
    if seg in PLATFORM_MAP:
        d, b = PLATFORM_MAP[seg]
        return d, b, seg
    # 尝试包含匹配
    for k, (d, b) in PLATFORM_MAP.items():
        if k in platform_raw.lower():
            return d, b, k
    if auto:
        return None, None, seg
    print("  [!] 无法识别的平台：%s" % platform_raw)
    print("      可选：vivo / oppo / xiaomi(小米) / honor(荣耀) / huawei(华为)")
    d = ask("      请输入平台目录名（如 Vivo）: ", auto=auto, allow_empty=False)
    return d, None, seg


# --------------------------------------------------------------------------
# 运营方解析（优先匹配已存在目录，再别名表，再拼音）
# --------------------------------------------------------------------------
def tool_root():
    """工具根目录（_core 的上一级）"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def relify(path):
    """工具目录内部的路径存成相对路径，这样整个目录拷到别的机器也能用"""
    if not path:
        return path
    try:
        rel = os.path.relpath(path, tool_root())
    except Exception:
        return path
    return path if rel.startswith("..") else rel


def default_alias_path():
    """别名表默认位置：脚本同目录 -> 上一级目录（工具根的 operator_alias.json）"""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "operator_alias.json"),
              os.path.join(os.path.dirname(here), "operator_alias.json")):
        if os.path.isfile(p):
            return p
    return os.path.join(here, "operator_alias.json")


def load_alias(path):
    """{中文运营方: 目录名}；忽略 _ 开头的元信息键"""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: v.strip() for k, v in data.items()
                    if not k.startswith("_") and isinstance(v, str) and v.strip()}
        except Exception as e:
            print("  [!] 别名表读取失败：%s" % e)
    return {}


def load_registry(path):
    """运营方目录名单（_operators）。新人电脑上本地没有目录时，靠它把名字建对。"""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            v = data.get("_operators")
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
        except Exception:
            pass
    return []


_ILLEGAL_NAME = '\\/:*?"<>|'


def sanitize_dirname(name):
    """清掉不能做目录名的字符，防止手滑把整条标题粘成目录名"""
    s = clean_input(name or "")
    for ch in _ILLEGAL_NAME + "[]【】《》()（）":
        s = s.replace(ch, "")
    return s.strip().strip(".")


def looks_like_dirname(name, max_len=24):
    """判断像不像一个自己起的目录名。
    真目录名不会带空格；粘整条 teambition 标题进来必然带空格且超长。"""
    if not name or " " in name or len(name) > max_len:
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", name))


def resolve_operator(op_cn, root, alias, auto, registry=None):
    existing = []
    if os.path.isdir(root):
        existing = sorted([d for d in os.listdir(root)
                           if os.path.isdir(os.path.join(root, d)) and re.search(r"[\u4e00-\u9fffA-Za-z]", d)])

    if not op_cn:
        return None

    op_cn = op_cn.strip()

    # 1) 别名表
    if op_cn in alias:
        return alias[op_cn]

    # 候选池 = 本地已有目录 + 运营方名单。
    # 新人电脑上本地是空的，全靠 _operators 名单才能把 Yezi 这种不规则命名建对。
    pool = list(existing)
    for r in (registry or []):
        if r not in pool:
            pool.append(r)

    def _ratio(a, b):
        return difflib.SequenceMatcher(
            None, a.lower().replace("_", ""), b.lower().replace("_", "")).ratio()

    cand = to_camel(op_cn)

    # 2) 拼音精确匹配
    for d in pool:
        if cand and d.lower() == cand.lower():
            return d

    # 3) 前缀匹配（唯一时直接采用，处理 SunBo <-> SunBo_BoHuan 这类）
    pref = [d for d in pool if cand and d.lower().startswith(cand.lower())]
    if len(pref) == 1:
        print("  %s 运营方『%s』按前缀匹配到：%s"
              % (c_dim("[i]"), c_op(op_cn), c_op(pref[0])))
        return pref[0]

    # 4) 模糊匹配（多音字 厦门->ShaMen / 不规则命名 叶子->Yezi 都靠这步）
    if cand and pool:
        best = max(pool, key=lambda d: _ratio(cand, d))
        if _ratio(cand, best) >= 0.6:
            print("  %s 运营方『%s』拼音 %s 与 %s 相近，采用后者。"
                  % (c_dim("[i]"), c_op(op_cn), c_dim(cand), c_op(best)))
            return best

    # 5) 交互选择
    if auto:
        return cand or None
    print("  %s 没找到与『%s』(拼音 %s) 对应的运营方目录。"
          % (c_warn("[!]"), c_op(op_cn), c_dim(cand)))
    if pool:
        print("       %s：" % ("已有目录" if existing else "运营方名单（_operators）"))
        for i, d in enumerate(pool, 1):
            print("        %2d) %s" % (i, d))
    tip = sanitize_dirname(ask("      输入序号选择 / 直接回车新建【%s】/ 或输入其他名称: " % cand,
                               default=cand, auto=auto))
    if tip.isdigit() and pool and 1 <= int(tip) <= len(pool):
        return pool[int(tip) - 1]
    if not looks_like_dirname(tip):
        if cand:
            print("      %s 这个名字不像运营方目录，改用【%s】" % (c_warn("[!]"), c_op(cand)))
            return cand
        return None
    return tip


# --------------------------------------------------------------------------
# 签名搜索
# --------------------------------------------------------------------------
def collect_pems(folder):
    """在 folder 内递归找 certificate.pem / private.pem（取最浅的一对）"""
    found = {}
    for cur, _dirs, files in os.walk(folder):
        lower = {f.lower(): f for f in files}
        for key in ("certificate.pem", "private.pem"):
            if key in lower and key not in found:
                found[key] = os.path.join(cur, lower[key])
        if len(found) == 2:
            break
    return found


def search_signatures(project, sign_root):
    """在 sign_root 下递归找名字含 project 的目录，返回 [{dir, pems}]"""
    hits = []
    if not project or not os.path.isdir(sign_root):
        return hits
    key = project.strip()
    for cur, dirs, _files in os.walk(sign_root):
        if cur != sign_root and key in os.path.basename(cur):
            hits.append({"dir": cur, "pems": collect_pems(cur)})
            dirs[:] = []   # 命中后不再向下，避免嵌套重复命中
    return hits


def choose_signature(hits, project, auto):
    """返回选中的 {dir, pems}，或 None 表示跳过"""
    valid = [h for h in hits if len(h["pems"]) == 2]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]
    if auto:
        return valid[0]
    print("  [!] 在 GameSign 中搜到 %d 个含『%s』的候选：" % (len(valid), project))
    for i, h in enumerate(valid, 1):
        print("        %2d) %s" % (i, h["dir"]))
    print("         0) 跳过（不复制签名）")
    while True:
        s = ask("      请选择序号: ", auto=auto)
        if s == "0":
            return None
        if s.isdigit() and 1 <= int(s) <= len(valid):
            return valid[int(s) - 1]
        print("      输入无效，请重试。")


# --------------------------------------------------------------------------
# 华为 / 荣耀：签名按「运营方」取，不走原工程名
# --------------------------------------------------------------------------
HW_PLATFORMS = ("RongYao", "HuaWei")


def load_hw_map(path):
    """{运营方目录: 华为/荣耀签名文件夹名}"""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            v = data.get("_hw_sign_folders")
            if isinstance(v, dict):
                return {str(k).strip(): str(x).strip()
                        for k, x in v.items() if str(x).strip()}
        except Exception:
            pass
    return {}


def find_hw_sign_base(sign_root):
    """定位『1.华为-rpk（各运营签名文件）』（名字可能改，按关键字找）"""
    if not os.path.isdir(sign_root):
        return None
    for d in sorted(os.listdir(sign_root)):
        full = os.path.join(sign_root, d)
        if os.path.isdir(full) and "华为" in d and "签名" in d:
            return full
    return None


def hw_sign_candidates(base):
    """{运营方文件夹名: {certificate.pem/private.pem: 路径}}"""
    out = {}
    if not base or not os.path.isdir(base):
        return out
    for d in sorted(os.listdir(base)):
        sub = os.path.join(base, d)
        if os.path.isdir(sub):
            pems = collect_pems(sub)
            if len(pems) == 2:
                out[d] = pems
    return out


def resolve_hw_signature(ctx, operator, operator_cn, hw_map):
    """按运营方给华为/荣耀找签名。返回 {dir, pems} 或 None。"""
    base = find_hw_sign_base(ctx.cfg["sign_root"])
    if not base:
        print("  %s 没找到华为/荣耀的签名目录（%s 下名字含『华为』『签名』的文件夹）"
              % (c_warn("[!]"), c_path(ctx.cfg["sign_root"])))
        return None

    cand = hw_sign_candidates(base)
    if not cand:
        print("  %s %s 下没有可用的运营方签名" % (c_warn("[!]"), c_path(base)))
        return None
    names = list(cand.keys())

    # 1) 映射表（运营方目录 -> 签名文件夹）
    want = hw_map.get(operator)
    if want and want in cand:
        return {"dir": os.path.join(base, want), "pems": cand[want]}

    # 2) 标题里的中文运营方直接对上
    if operator_cn:
        for n in names:
            if n == operator_cn.strip():
                return {"dir": os.path.join(base, n), "pems": cand[n]}

    # 3) 模糊
    if operator_cn:
        def _ratio(a, b):
            return difflib.SequenceMatcher(None, a, b).ratio()

        best = max(names, key=lambda n: _ratio(operator_cn.strip(), n))
        if _ratio(operator_cn.strip(), best) >= 0.6:
            return {"dir": os.path.join(base, best), "pems": cand[best]}

    # 4) 问
    label = operator_cn or operator
    if ctx.yes:
        print("  %s 没能确定『%s』该用哪份华为/荣耀签名（映射表里没这条），跳过。"
              % (c_warn("[!]"), label))
        print("       可选：%s" % " / ".join(names))
        return None
    print("  %s 华为/荣耀的签名按运营方分，没确定『%s』该用哪份：" % (c_warn("[!]"), label))
    for i, n in enumerate(names, 1):
        print("        %2d) %s" % (i, n))
    print("         0) 跳过")
    while True:
        s = ask("      请选择序号: ", auto=ctx.yes)
        if s == "0":
            return None
        if s.isdigit() and 1 <= int(s) <= len(names):
            n = names[int(s) - 1]
            return {"dir": os.path.join(base, n), "pems": cand[n]}
        print("      输入无效，请重试。")


# --------------------------------------------------------------------------
# 配置（优先级：内置默认 < config.json < 命令行）
# --------------------------------------------------------------------------
CONFIG_FILE_NAME = "config.json"
CONFIG_KEYS = ("root", "sign_root", "batch_src", "alias", "auto_open")
CONFIG_LABELS = {
    "root": "输出根目录",
    "sign_root": "签名库",
    "batch_src": "批处理源",
    "alias": "别名表",
    "auto_open": "建完自动打开",
}
PATH_KEYS = ("root", "sign_root", "batch_src")     # 需要校验目录是否存在的项
BOOL_KEYS = ("auto_open",)                          # 开关类配置项


def as_bool(v, default=None):
    """把 on/off/true/false/开/关 之类解析成 bool；解析不了返回 default"""
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "开", "是"):
        return True
    if s in ("0", "false", "no", "off", "关", "否"):
        return False
    return default


def fmt_val(key, v):
    """配置值的显示形式"""
    if key in BOOL_KEYS:
        return c_ok("开") if v else c_dim("关")
    return c_path(v) if (key != "alias" or os.path.isfile(v)) else c_err(v)


def config_candidates():
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(os.path.dirname(here), CONFIG_FILE_NAME),
            os.path.join(here, CONFIG_FILE_NAME)]


def find_config_file():
    for p in config_candidates():
        if os.path.isfile(p):
            return p
    return None


def load_config(cli):
    cfg = {k: DEFAULTS.get(k, "") for k in CONFIG_KEYS}
    cfg["alias"] = default_alias_path()
    cfg["auto_open"] = True          # 建完自动打开游戏目录，默认开
    src = {k: "内置默认" for k in CONFIG_KEYS}

    cf = find_config_file()
    if cf:
        try:
            with open(cf, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in CONFIG_KEYS:
                if k not in data:
                    continue
                v = data[k]
                if k in BOOL_KEYS:
                    b = as_bool(v, None)
                    if b is not None:
                        cfg[k] = b
                        src[k] = CONFIG_FILE_NAME
                elif isinstance(v, str) and v.strip():
                    cfg[k] = v.strip()
                    src[k] = CONFIG_FILE_NAME
        except Exception as e:
            print("[!] %s 读取失败：%s" % (cf, e))

    for k in PATH_KEYS + ("alias",):
        v = getattr(cli, k, None)
        if v:
            cfg[k] = v
            src[k] = "命令行"
    if getattr(cli, "no_open", False):
        cfg["auto_open"] = False
        src["auto_open"] = "命令行"

    # alias 允许写相对路径（相对工具根）；配置里的路径失效时退回工具自带的别名表
    ap = cfg["alias"]
    if ap and not os.path.isabs(ap):
        cfg["alias"] = os.path.normpath(os.path.join(tool_root(), ap))
    if not os.path.isfile(cfg["alias"]):
        fb = default_alias_path()
        if os.path.isfile(fb):
            cfg["alias"] = fb

    return cfg, src, cf


def save_config(ctx):
    p = find_config_file() or config_candidates()[0]
    data = {k: ctx.cfg[k] for k in CONFIG_KEYS}
    data["alias"] = relify(data.get("alias", ""))    # 存相对路径，换机器也能用
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("  [!] 保存失败：%s" % e)
        return None
    ctx.cfgfile = p
    return p


class Ctx:
    """一次运行的全部状态。"""

    def __init__(self, cfg, src, cfgfile):
        self.cfg = cfg
        self.src = src
        self.cfgfile = cfgfile
        self.dry = False
        self.yes = False
        self.force = False
        self.last_game_dir = None
        self.history = []      # [{"time","title","ok","dir"}]


# --------------------------------------------------------------------------
# 主流程：处理一条 teambition 标题
# --------------------------------------------------------------------------
def run_title(ctx, title):
    ctx.last_game_dir = None
    hr()
    print("  %s %s" % (c_key("输出根目录："), c_path(ctx.cfg["root"])))
    hr()

    info = parse_title(title)
    alias = load_alias(ctx.cfg["alias"])
    registry = load_registry(ctx.cfg["alias"])
    hw_map = load_hw_map(ctx.cfg["alias"])

    # ---- 解析 ----
    plat_dir, batch_file, plat_key = resolve_platform(info["platform_raw"], ctx.yes)
    if not plat_dir:
        print(c_err("[X] 平台解析失败，已放弃本次处理。"))
        return False

    print("\n%s" % c_key("解析结果："))
    print("  平台关键字 : %s" % c_plat(info["platform_raw"]))
    print("  平台目录   : %s" % c_plat(plat_dir))
    print("  游戏名     : %s" % c_game(info["game"]))
    print("  原工程名   : %s   %s" % (c_game(info["project"]), c_dim("(仅用于搜签名)")))
    print("  运营方     : %s   %s"
          % (c_op(info["operator"]), c_dim("(个人名 %s，不建目录)" % info["person"])))
    print("  包类型     : %s" % c_dim(info["pack_type"]))

    # ---- 游戏目录拼音（可编辑）----
    game_pinyin = to_camel(info["game"] or "")
    if not ctx.yes:
        print("\n%s %s" % (c_key("游戏目录拼音："), c_game(game_pinyin)))
        fixed = sanitize_dirname(ask("  回车确认，或输入修正值: ",
                                     default=game_pinyin, auto=ctx.yes))
        if fixed and looks_like_dirname(fixed, max_len=64):
            game_pinyin = fixed
        elif fixed:
            print("      %s 这个名字不像游戏目录，仍用【%s】" % (c_warn("[!]"), c_game(game_pinyin)))
    if not game_pinyin:
        print(c_err("[X] 游戏目录名为空，已放弃本次处理。"))
        return False

    # ---- 运营方 ----
    operator = resolve_operator(info["operator"], ctx.cfg["root"], alias, ctx.yes, registry)
    if not operator:
        print(c_err("[X] 运营方无法确定，已放弃本次处理。"))
        return False

    game_dir = os.path.join(ctx.cfg["root"], operator, plat_dir, game_pinyin)
    v1_dir = os.path.join(game_dir, "V1")

    # ---- 该平台下已存在的游戏目录（供核对，避免命名对不上）----
    plat_path = os.path.join(ctx.cfg["root"], operator, plat_dir)
    siblings = []
    if os.path.isdir(plat_path):
        siblings = sorted([d for d in os.listdir(plat_path)
                           if os.path.isdir(os.path.join(plat_path, d))])
    if siblings:
        print("\n  %s %s %s"
              % (c_dim("[i]"), c_plat(plat_dir),
                 c_dim("下已有 %d 个游戏目录（不会覆盖，只补齐缺失文件）：" % len(siblings))))
        for d in siblings:
            if d.lower() == game_pinyin.lower():
                print("        %s   %s" % (c_game(d), c_warn("<- 本次目标，已存在")))
            else:
                print("        %s" % c_game(d))

    # ---- 打印计划 ----
    hr("-")
    print("%s" % c_key("执行计划："))
    print("  运营方目录 : %s" % c_path(os.path.join(ctx.cfg["root"], operator)))
    print("  平台目录   : %s" % c_path(os.path.join(ctx.cfg["root"], operator, plat_dir)))
    print("  游戏目录   : %s" % c_game(game_dir))
    print("  工程目录   : %s" % c_path(v1_dir))
    if batch_file:
        src = os.path.join(ctx.cfg["batch_src"], batch_file)
        print("  批处理     : %s %s %s"
              % (c_dim(src), c_dim("->"), c_path(os.path.join(game_dir, batch_file))))
    else:
        print("  批处理     : %s" % c_warn("该平台无批处理（%s）" % plat_dir))

    # ---- 签名搜索 ----
    sign_hit = None
    if plat_dir in HW_PLATFORMS:
        # 华为 / 荣耀：签名按运营方分，不用原工程名
        print("  %s %s 的签名按【运营方】取，不走原工程名"
              % (c_dim("[i]"), c_plat(plat_dir)))
        sign_hit = resolve_hw_signature(ctx, operator, info["operator"], hw_map)
        if sign_hit:
            print("  签名来源   : %s" % c_path(sign_hit["dir"]))
        else:
            print("  签名来源   : %s" % c_warn("未取到"))
            if not ctx.yes:
                manual = ask("      可直接粘贴签名目录路径，或回车跳过: ", auto=ctx.yes)
                if manual:
                    pems = collect_pems(manual) if os.path.isdir(manual) else {}
                    if len(pems) == 2:
                        sign_hit = {"dir": manual, "pems": pems}
                    else:
                        print("      %s 该路径下未找到完整 pem 对，跳过。" % c_warn("[!]"))
    elif info["project"]:
        hits = search_signatures(info["project"], ctx.cfg["sign_root"])
        valid = [h for h in hits if len(h["pems"]) == 2]
        if hits and not valid:
            print("  %s 搜到目录但没有完整 pem 对：" % c_warn("[!]"))
            for h in hits:
                print("        %s  %s"
                      % (c_path(h["dir"]), c_dim("(找到 %s)" % (", ".join(h["pems"].keys()) or "无"))))
        if valid:
            if len(valid) > 1 and ctx.yes:
                print("  %s 有 %d 个候选，--yes 模式下自动采用第 1 个：%s"
                      % (c_warn("[!]"), len(valid), c_path(valid[0]["dir"])))
            sign_hit = choose_signature(hits, info["project"], ctx.yes)
            if sign_hit:
                print("  签名来源   : %s" % c_path(sign_hit["dir"]))
            else:
                print("  签名来源   : %s" % c_warn("用户选择跳过"))
        else:
            print("  %s 未在 %s 搜到 %s 的签名。"
                  % (c_warn("[!]"), c_path(ctx.cfg["sign_root"]), c_game(info["project"])))
            if not ctx.yes:
                manual = ask("      可粘贴签名目录路径，或回车跳过: ", auto=ctx.yes)
                if manual:
                    pems = collect_pems(manual) if os.path.isdir(manual) else {}
                    if len(pems) == 2:
                        sign_hit = {"dir": manual, "pems": pems}
                    else:
                        print("      %s 该路径下未找到完整 pem 对，跳过。" % c_warn("[!]"))
    else:
        print("  %s 标题里没有括号(原工程名)，跳过签名搜索。" % c_warn("[!]"))
    hr("-")

    if not ctx.yes:
        go = ask("确认执行？[Y/n] : ", default="Y", auto=ctx.yes).lower()
        if go not in ("y", "yes", "", "确认"):
            print(c_warn("已取消。"))
            return False

    if ctx.dry:
        print(c_warn("(dry-run 模式，未做任何改动)"))
        return True

    # ---- 落盘（root 也列上，新人机器上根目录本身可能还不存在）----
    for d in (ctx.cfg["root"], os.path.join(ctx.cfg["root"], operator),
              os.path.join(ctx.cfg["root"], operator, plat_dir), game_dir, v1_dir):
        if not os.path.isdir(d):
            os.makedirs(d)
            print("  %s %s" % (c_ok("[建]"), c_path(d)))
        else:
            print("  %s %s" % (c_dim("[有]"), c_dim(d)))

    if batch_file:
        src = os.path.join(ctx.cfg["batch_src"], batch_file)
        dst = os.path.join(game_dir, batch_file)
        if not os.path.isfile(src):
            print("  %s 源批处理不存在：%s" % (c_err("[!]"), c_path(src)))
        elif os.path.isfile(dst) and not ctx.force:
            print("  %s 批处理已存在，跳过：%s" % (c_dim("[有]"), c_dim(dst)))
        else:
            shutil.copy2(src, dst)
            print("  %s %s" % (c_ok("[拷]"), c_path(dst)))

    if sign_hit:
        for key, sp in sign_hit["pems"].items():
            dst = os.path.join(game_dir, key)
            if os.path.isfile(dst) and not ctx.force:
                print("  %s 签名已存在，跳过：%s" % (c_dim("[有]"), c_dim(dst)))
            else:
                shutil.copy2(sp, dst)
                print("  %s %s" % (c_ok("[拷]"), c_path(dst)))

    hr()
    print("%s" % c_ok("完成。游戏目录："))
    print("  %s" % c_game(game_dir))
    hr()
    ctx.last_game_dir = game_dir
    return True


# --------------------------------------------------------------------------
# 交互命令
# --------------------------------------------------------------------------
HELP_TEXT = """
可用命令
  help / ?               显示本帮助
  open                   打开上一次建的游戏目录（建完也会自动打开）
  open <路径>            打开指定目录 / 文件
  open <运营方> [平台] [游戏]   按名字定位后打开（支持模糊）
  open on / open off     开关「建完自动打开」
  ls                     列出所有运营方及游戏数量
  ls <运营方>            列出该运营方下的平台
  ls <运营方> <平台>     列出该平台下的游戏目录（并标注缺什么）
  history                本次会话执行过的标题
  history <序号>         重新执行第 <序号> 条
  history -c             清空本次会话历史
  config                 查看当前配置（等于 config -l）
  config -c <项> <值>     修改配置，如：config -c root D:\\UnityOutput2
  config -c              交互式逐项修改
  config -s              保存到 config.json（下次启动自动读取）
  config -r              恢复内置默认值（不落盘）
  dry / preview          切换「只看不改」（dry-run）开关
  color                  开关彩色输出（也可 color on / color off）
  cls / clear            清屏
  exit / quit / q        退出

直接把 teambition 标题粘进来（不用加任何参数）即执行，例如：
  [vivo-rpk]《模拟火车司机驾驶》(地铁模拟器3D) 正式包 厦门-吴伟

配置项：root（输出根目录）/ sign_root（签名库）/ batch_src（批处理源）/ alias（别名表）
命令行同名参数 --root / --sign-root / --batch-src / --alias 优先级最高。
""".strip("\n")

CONFIG_HELP = """
config                 查看当前配置
config -c <项> <值>     修改一项，例如：config -c sign_root D:\\Resources\\GameSign
config -c <项>=<值>     同上，另一种写法
config -c              交互式逐项修改
config -s              保存到 config.json
config -r              恢复内置默认值
配置项：root / sign_root / batch_src / alias
""".strip("\n")


def print_banner(ctx):
    hr()
    print("  %s" % c_key("Unity 打包工作目录一键创建"))
    print("  直接粘贴 teambition 标题即可执行；输入 %s 看命令。" % c_key("help"))
    print("  输出根目录：%s" % c_path(ctx.cfg["root"]))
    print("  预览模式：%s      彩色输出：%s"
          % (c_warn("开") if ctx.dry else c_dim("关"),
             c_ok("开") if COLOR else c_dim("关")))
    hr()


def show_config(ctx):
    print("%s" % c_key("当前配置："))
    for k in CONFIG_KEYS:
        print("  %s = %s" % (c_key("%-9s" % k), fmt_val(k, ctx.cfg[k])))
        print("  %s   %s  %s"
              % (" " * 9, c_dim(CONFIG_LABELS.get(k, "")), c_dim("[来自 %s]" % ctx.src.get(k, ""))))
    print("  %s = %s" % (c_key("dry-run  "), c_warn("开") if ctx.dry else c_dim("关")))
    print("  %s = %s"
          % (c_key("配置文件 "),
             c_path(ctx.cfgfile) if ctx.cfgfile else c_dim("(尚未生成，用 config -s 生成)")))


def set_config(ctx, key, value):
    if key in BOOL_KEYS:
        b = as_bool(value, None)
        if b is None:
            print("  %s %s 只接受 on / off（或 开 / 关）" % (c_warn("[!]"), c_key(key)))
            return
        ctx.cfg[key] = b
    elif key in PATH_KEYS:
        if not os.path.isdir(value):
            print("  %s 目录不存在：%s  %s" % (c_warn("[!]"), c_err(value), c_dim("（已记下）")))
        ctx.cfg[key] = value
    elif key == "alias":
        if not os.path.isfile(value):
            print("  %s 文件不存在：%s  %s" % (c_warn("[!]"), c_err(value), c_dim("（已记下）")))
        ctx.cfg[key] = value
    else:
        print("  %s 未知配置项：%s" % (c_warn("[!]"), c_key(key)))
        return
    ctx.src[key] = "本次会话"
    print("  %s = %s" % (c_key(key), fmt_val(key, ctx.cfg[key])))


def edit_config_interactive(ctx):
    print("逐项修改（直接回车 = 保持原值）：")
    for k in CONFIG_KEYS:
        cur = ctx.cfg[k]
        shown = ("开" if cur else "关") if k in BOOL_KEYS else cur
        v = ask("  %s [%s]: " % (k, shown), default="")
        if v:
            set_config(ctx, k, v)
    print("改完记得 config -s 保存。")


def handle_config(ctx, rest):
    arg = rest.strip()

    if arg == "" or arg in ("-l", "--list", "list"):
        show_config(ctx)
        return
    if arg in ("-h", "--help", "help"):
        print(CONFIG_HELP)
        return
    if arg in ("-s", "--save", "save"):
        p = save_config(ctx)
        if p:
            print("  已保存到 %s" % p)
        return
    if arg in ("-r", "--reset", "reset"):
        for k in CONFIG_KEYS:
            ctx.cfg[k] = DEFAULTS.get(k, "")
            ctx.src[k] = "内置默认"
        ctx.cfg["alias"] = default_alias_path()
        print("  已恢复内置默认值（未落盘，用 config -s 保存）")
        show_config(ctx)
        return

    if arg.startswith("-c"):
        arg = arg[2:].strip()
        if not arg:
            edit_config_interactive(ctx)
            return
    elif arg.startswith("-"):
        print("  [!] 未知的 config 参数：%s" % arg)
        print(CONFIG_HELP)
        return

    if "=" in arg:
        k, _, v = arg.partition("=")
    else:
        k, _, v = arg.partition(" ")
    k = k.strip().lower()
    v = clean_input(v)

    if k not in CONFIG_KEYS:
        print("  [!] 未知配置项：%s（可选：%s）" % (k, " / ".join(CONFIG_KEYS)))
        return
    if not v:
        print("  [!] 缺少值。用法：config -c %s <值>" % k)
        return
    set_config(ctx, k, v)


def handle_dry(ctx, rest):
    arg = rest.strip().lower()
    if arg in ("on", "1", "true", "开"):
        ctx.dry = True
    elif arg in ("off", "0", "false", "关"):
        ctx.dry = False
    else:
        ctx.dry = not ctx.dry
    print("  预览模式（dry-run）：%s"
          % (c_warn("开 —— 只显示计划，不落盘") if ctx.dry else c_dim("关")))


def handle_color(ctx, rest):
    arg = rest.strip().lower()
    if arg in ("on", "1", "true", "开"):
        set_color(True)
    elif arg in ("off", "0", "false", "关"):
        set_color(False)
    else:
        set_color(not COLOR)
    print("  彩色输出：%s" % (c_ok("开") if COLOR else c_dim("关")))


# --------------------------------------------------------------------------
# ls：翻目录，看已有游戏 / 缺什么
# --------------------------------------------------------------------------
def _pick(name, candidates):
    """按名字挑候选：先精确（不分大小写），再唯一子串。返回 (命中, 所有命中)"""
    n = name.strip().lower()
    if not n:
        return None, []
    for d in candidates:
        if d.lower() == n:
            return d, [d]
    hits = [d for d in candidates if n in d.lower()]
    if len(hits) == 1:
        return hits[0], hits
    return None, hits


def _find_rpk(game_dir, plat, max_depth=4):
    """找成品包 *.rpk，返回相对路径；没找到返回 None。

    - 平台有固定位置(DIST_PATH)：只看那个目录。位置对但里面没有 = 真的没编译产物。
    - 平台没固定位置(华为) 或固定位置压根不存在：限深递归找，因为布局五花八门
      （build/ output/dist/ formal/ 正式包/ 测试包/ 中文文件夹 都出现过）。
    """
    rel = DIST_PATH.get(plat)
    if rel:
        d = os.path.join(game_dir, rel)
        if os.path.isdir(d):
            try:
                for n in os.listdir(d):
                    if n.lower().endswith(".rpk"):
                        return os.path.join(rel, n)
            except Exception:
                pass
            return None

    base = game_dir.rstrip("\\/")
    for cur, dirs, files in os.walk(base):
        r = os.path.relpath(cur, base)
        depth = 0 if r == "." else r.count(os.sep) + 1
        if depth >= max_depth:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(".rpk"):
                return f if r == "." else os.path.join(r, f)
    return None


def _has_output(game_dir, plat):
    """成品包 (*.rpk) 是否已生成。平台不在 DIST_PATH 里时返回 None（不下结论）。"""
    if plat not in DIST_PATH:
        return None
    return _find_rpk(game_dir, plat) is not None


def _has_signature(game_dir):
    """根目录、或某个直接子目录里，是否有完整的一对 pem。
    （有的项目按版本/渠道分子目录放，如 1059\\ / 1724\\）"""
    try:
        names = os.listdir(game_dir)
    except Exception:
        return False
    if sum(1 for n in names if n.lower() in ("certificate.pem", "private.pem")) >= 2:
        return True
    for n in names:
        sub = os.path.join(game_dir, n)
        if not os.path.isdir(sub):
            continue
        try:
            sn = [x.lower() for x in os.listdir(sub)]
        except Exception:
            continue
        if sum(1 for x in sn if x in ("certificate.pem", "private.pem")) >= 2:
            return True
    return False


def _game_missing(game_dir, plat):
    """看游戏目录里缺什么：V1 / 批处理 / 签名 / 成品包"""
    try:
        names = os.listdir(game_dir)
    except Exception:
        return ["无法读取"]
    lower = [n.lower() for n in names]
    missing = []
    if not os.path.isdir(os.path.join(game_dir, "V1")):
        missing.append("V1")
    if plat not in NO_BATCH_PLATFORMS and not any(n.endswith(".bat") for n in lower):
        missing.append("批处理")
    if not _has_signature(game_dir):
        missing.append("签名")
    if _has_output(game_dir, plat) is False:
        missing.append("成品包")
    return missing


def _status_text(game_dir, plat):
    missing = _game_missing(game_dir, plat)
    return c_ok("齐全") if not missing else c_warn("缺 " + " / ".join(missing))


def cmd_ls(ctx, rest):
    root = ctx.cfg["root"]
    if not os.path.isdir(root):
        print("  %s 输出根目录不存在：%s" % (c_err("[!]"), c_path(root)))
        return

    args = rest.split()
    if args:
        amap = load_alias(ctx.cfg["alias"])
        if args[0] in amap:
            args[0] = amap[args[0]]

    ops = sorted([d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))])

    # ls —— 所有运营方
    if not args:
        print("%s  %s" % (c_path(root), c_dim("(%d 个运营方)" % len(ops))))
        for op in ops:
            opdir = os.path.join(root, op)
            plats = sorted([d for d in os.listdir(opdir) if os.path.isdir(os.path.join(opdir, d))])
            total = 0
            for p in plats:
                pdir = os.path.join(opdir, p)
                total += sum(1 for d in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, d)))
            print("  %s  %s  %s"
                  % (c_op("%-18s" % op),
                     c_plat(" ".join(plats)) if plats else c_dim("(无平台)"),
                     c_dim("%d 个游戏" % total)))
        print(c_dim("  用法：ls <运营方> [平台]"))
        return

    op, hits = _pick(args[0], ops)
    if not op:
        if hits:
            print("  %s 匹配到多个运营方：%s" % (c_warn("[!]"), c_op(" / ".join(hits))))
        else:
            print("  %s 找不到运营方：%s" % (c_err("[!]"), c_err(args[0])))
        print(c_dim("       现有：%s" % ", ".join(ops)))
        return

    opdir = os.path.join(root, op)
    plats = sorted([d for d in os.listdir(opdir) if os.path.isdir(os.path.join(opdir, d))])

    # ls <运营方>
    if len(args) < 2:
        print("%s" % c_path(opdir))
        if not plats:
            print(c_dim("  (没有平台目录)"))
        for p in plats:
            pdir = os.path.join(opdir, p)
            games = [d for d in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, d))]
            print("  %s  %s" % (c_plat("%-8s" % p), c_dim("%d 个游戏" % len(games))))
        return

    plat, phits = _pick(args[1], plats)
    if not plat:
        if phits:
            print("  %s 匹配到多个平台：%s" % (c_warn("[!]"), c_plat(" / ".join(phits))))
        else:
            print("  %s 找不到平台：%s" % (c_err("[!]"), c_err(args[1])))
        print(c_dim("       现有：%s" % (", ".join(plats) or "无")))
        return

    pdir = os.path.join(opdir, plat)
    games = sorted([d for d in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, d))])
    print("%s  %s" % (c_path(pdir), c_dim("(%d 个游戏)" % len(games))))
    if not games:
        print(c_dim("  (还没有游戏目录)"))
        return
    width = max(len(g) for g in games)
    for g in games:
        print("  %s  %s" % (c_game(g.ljust(width)), _status_text(os.path.join(pdir, g), plat)))


# --------------------------------------------------------------------------
# open：打开目录
# --------------------------------------------------------------------------
def _open_path(path):
    """用系统默认方式打开目录 / 文件"""
    try:
        if os.name == "nt":
            os.startfile(path)                       # 目录 -> 资源管理器
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, path])
        return True
    except Exception as e:
        print("  %s 打开失败：%s" % (c_err("[!]"), e))
        print(c_dim("       路径：%s" % path))
        return False


def _do_open(ctx, path):
    if not os.path.exists(path):
        print("  %s 路径不存在：%s" % (c_err("[!]"), c_err(path)))
        return False
    print("  打开：%s" % c_path(path))
    return _open_path(path)


def _find_game_dirs(root, name, game_depth=3):
    """按名字模糊找「游戏」目录，返回绝对路径列表。
    只认 <运营方>\\<平台>\\<游戏> 里最底下那一层，避免把运营方/平台目录也算进来。"""
    n = name.strip().lower()
    if not n:
        return []
    base = root.rstrip("\\/")
    hits = []
    for cur, dirs, _files in os.walk(base):
        rel = os.path.relpath(cur, base)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth + 1 < game_depth:
            continue                          # 还在运营方 / 平台层，继续下探
        if depth + 1 == game_depth:           # 下一层正好是「游戏」层 -> 匹配
            for d in dirs:
                if n in d.lower():
                    hits.append(os.path.join(cur, d))
        dirs[:] = []                          # 到游戏层或更深，不再往下
    return sorted(set(hits))


def cmd_open(ctx, rest):
    arg = rest.strip()

    # open on / open off —— 切换「建完自动打开」
    if arg.lower() in ("on", "off", "1", "0", "true", "false", "开", "关"):
        b = as_bool(arg, None)
        if b is not None:
            ctx.cfg["auto_open"] = b
            ctx.src["auto_open"] = "本次会话"
            print("  建完自动打开：%s   %s"
                  % (c_ok("开") if b else c_dim("关"),
                     c_dim("（想长期生效用 config -s）")))
            return

    # open —— 打开上一次建的目录
    if not arg:
        if ctx.last_game_dir:
            _do_open(ctx, ctx.last_game_dir)
        else:
            print(c_dim("  本次会话还没建过目录。可以：open <路径> / open <运营方> [平台] [游戏]"))
        return

    # 看着像路径就直接当路径
    if any(ch in arg for ch in "\\/:") or os.path.exists(arg):
        _do_open(ctx, os.path.normpath(arg))
        return

    # 否则按名字定位：open <运营方> [平台] [游戏]
    root = ctx.cfg["root"]
    if not os.path.isdir(root):
        print("  %s 输出根目录不存在：%s" % (c_err("[!]"), c_path(root)))
        return

    parts = arg.split()
    amap = load_alias(ctx.cfg["alias"])
    if parts[0] in amap:
        parts[0] = amap[parts[0]]

    ops = sorted([d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))])
    op, ohits = _pick(parts[0], ops)

    if not op:
        if len(ohits) > 1:
            print("  %s 运营方匹配到多个：%s" % (c_warn("[!]"), c_op(" / ".join(ohits))))
            print(c_dim("       写全一点，例如：open XiaMen Vivo"))
            return
        # 也许用户直接给的是游戏目录名
        found = _find_game_dirs(root, parts[0])
        if len(found) == 1:
            _do_open(ctx, found[0])
            return
        if len(found) > 1:
            print("  %s 匹配到多个游戏目录：" % c_warn("[!]"))
            for f in found:
                print("        %s" % c_path(f))
            print(c_dim("       带上运营方和平台更准：open <运营方> <平台> <游戏>"))
            return
        print("  %s 找不到：%s" % (c_err("[!]"), c_err(parts[0])))
        print(c_dim("       现有运营方：%s" % ", ".join(ops)))
        return

    target = os.path.join(root, op)

    if len(parts) >= 2:
        plats = sorted([d for d in os.listdir(target) if os.path.isdir(os.path.join(target, d))])
        plat, phits = _pick(parts[1], plats)
        if not plat:
            if len(phits) > 1:
                print("  %s 平台匹配到多个：%s" % (c_warn("[!]"), c_plat(" / ".join(phits))))
            else:
                print("  %s 找不到平台：%s" % (c_err("[!]"), c_err(parts[1])))
            print(c_dim("       现有：%s" % (", ".join(plats) or "无")))
            return
        target = os.path.join(target, plat)

    if len(parts) >= 3:
        games = sorted([d for d in os.listdir(target) if os.path.isdir(os.path.join(target, d))])
        want = " ".join(parts[2:])
        game, ghits = _pick(want, games)
        if not game:
            print("  %s 找不到游戏目录：%s" % (c_err("[!]"), c_err(want)))
            if ghits:
                print(c_dim("       命中多个，写全一点：%s" % " / ".join(ghits)))
            return
        target = os.path.join(target, game)

    _do_open(ctx, target)


# --------------------------------------------------------------------------
# history：本次会话执行过的标题
# --------------------------------------------------------------------------
def _run_and_open(ctx, title):
    """执行一条标题：记历史；成功、非 dry-run、且开了自动打开 -> 打开目录"""
    ok = run_title(ctx, title)
    _record(ctx, title, ok)
    if ok and not ctx.dry and ctx.cfg.get("auto_open") and ctx.last_game_dir:
        _do_open(ctx, ctx.last_game_dir)
    return ok


def _record(ctx, title, ok):
    ctx.history.append({
        "time": time.strftime("%H:%M:%S"),
        "title": title,
        "ok": bool(ok),
        "dir": ctx.last_game_dir,
    })


def show_history(ctx, rest):
    arg = rest.strip().lower()

    if arg in ("-c", "--clear", "clear"):
        ctx.history.clear()
        print("  已清空本次会话历史。")
        return

    if not ctx.history:
        print(c_dim("  (本次会话还没有执行过标题)"))
        return

    if arg.isdigit():
        i = int(arg)
        if not (1 <= i <= len(ctx.history)):
            print("  %s 序号超出范围（1 - %d）" % (c_warn("[!]"), len(ctx.history)))
            return
        title = ctx.history[i - 1]["title"]
        print("  重新执行 #%d：%s" % (i, c_game(title)))
        _run_and_open(ctx, title)
        return

    print("%s  %s" % (c_key("本次会话历史："), c_dim("(共 %d 条)" % len(ctx.history))))
    for i, h in enumerate(ctx.history, 1):
        print("  %s  %s  %s"
              % (c_key("#%-3d" % i), c_dim(h["time"]),
                 c_ok("成功") if h["ok"] else c_err("失败")))
        print("        %s" % c_game(h["title"]))
        if h["dir"]:
            print("        %s" % c_path(h["dir"]))
    print(c_dim("  history <序号> 重新执行；history -c 清空"))


def clear_screen():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        print("\n" * 40)


def shell(ctx):
    print_banner(ctx)
    while True:
        try:
            line = clean_input(input(c_key("npf> ")))
        except EOFError:
            print("\n再见。")
            return 0
        except KeyboardInterrupt:
            print("\n(输入 exit 退出)")
            continue

        if not line:
            continue

        parts = line.split(None, 1)
        cmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit", "quit", "q"):
            print("再见。")
            return 0
        if cmd in ("help", "?", "h"):
            print(HELP_TEXT)
            continue
        if cmd in ("cls", "clear"):
            clear_screen()
            print_banner(ctx)
            continue
        if cmd == "config" or cmd == "cfg":
            handle_config(ctx, rest)
            continue
        if cmd == "set":
            handle_config(ctx, "-c " + rest)
            continue
        if cmd in ("dry", "preview", "dryrun"):
            handle_dry(ctx, rest)
            continue
        if cmd in ("color", "colour"):
            handle_color(ctx, rest)
            continue
        if cmd in ("ls", "list", "dir"):
            cmd_ls(ctx, rest)
            continue
        if cmd in ("open", "explorer"):
            cmd_open(ctx, rest)
            continue
        if cmd in ("history", "hist"):
            show_history(ctx, rest)
            continue
        if cmd.startswith("-"):
            print("  %s 未知命令：%s（输入 %s 看可用命令）"
                  % (c_warn("[!]"), c_key(cmd), c_key("help")))
            continue

        # 其它输入一律当作 teambition 标题
        _run_and_open(ctx, line)


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(add_help=True, description="Unity 打包工作目录一键创建")
    ap.add_argument("title", nargs="?", help="teambition 标题整串；不给则进入命令交互模式")
    ap.add_argument("--root", default=None, help="输出根目录")
    ap.add_argument("--sign-root", default=None, help="签名库根目录")
    ap.add_argument("--batch-src", default=None, help="批处理来源目录")
    ap.add_argument("--alias", default=None, help="运营方别名表")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不落盘")
    ap.add_argument("--yes", action="store_true", help="全部使用默认值，不交互")
    ap.add_argument("--force", action="store_true", help="已存在的文件也覆盖")
    ap.add_argument("--no-open", action="store_true", help="建完不自动打开目录")
    return ap


def main():
    args = build_parser().parse_args()
    cfg, src, cfgfile = load_config(args)
    ctx = Ctx(cfg, src, cfgfile)
    ctx.dry = args.dry_run
    ctx.yes = args.yes
    ctx.force = args.force

    if args.title:
        print_banner(ctx)
        return 0 if run_title(ctx, clean_input(args.title)) else 2

    return shell(ctx)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断。")
        sys.exit(130)
