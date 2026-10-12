# Unity 打包工作目录一键创建

把 teambition 标题整串粘进来，自动把出包目录、平台批处理、签名文件一次摆好。

## 用法

双击 **`新建打包目录.bat`**，然后把标题粘进去回车：

```
[vivo-rpk]《模拟火车司机驾驶》(地铁模拟器3D) 正式包 厦门-吴伟
```

> ⚠️ **不要双击 `_core\NewPackFolder.py`**，那样 Windows 会弹「你要用什么打开这个文件」。
> 要双击的是 **`新建打包目录.bat`**。

也可以命令行直接带标题（跳过交互）：

```bat
python _core\NewPackFolder.py "[vivo-rpk]《模拟火车司机驾驶》(地铁模拟器3D) 正式包 厦门-吴伟"
python _core\NewPackFolder.py "..." --dry-run     :: 只预览，不落盘
python _core\NewPackFolder.py "..." --yes         :: 全部用默认值，不交互
```

## 命令

启动后是个命令窗口（提示符 `npf>`）。**直接把 teambition 标题粘进去回车就执行**，不用加任何参数。另外这些命令：

| 命令 | 作用 |
|---|---|
| `help` / `?` | 显示帮助 |
| `open` | 打开**上一次**建的游戏目录（建完也会自动打开） |
| `open <路径>` | 打开指定目录 / 文件 |
| `open <运营方> [平台] [游戏]` | 按名字定位后打开，支持模糊（`open XiaMen Vivo MoNi`）；也可只给游戏名，会列出所有同名的候选 |
| `open on` / `open off` | 开关「建完自动打开」 |
| `ls` | 列出所有运营方 + 各自的平台 + 游戏数量 |
| `ls <运营方>` | 列出该运营方下的平台 |
| `ls <运营方> <平台>` | 列出该平台下的游戏目录，并标注每个**缺什么**（V1 / 批处理 / 签名 / 成品包） |
| `history` | 本次会话执行过的标题（含时间、成功/失败、目标目录） |
| `history <序号>` | 重新执行第 `<序号>` 条 |
| `history -c` | 清空本次会话历史 |
| `config` | 查看当前配置，并标注每一项的来源（内置默认 / config.json / 本次会话 / 命令行） |
| `config -c <项> <值>` | 修改一项，如 `config -c root D:\UnityOutput2`；也支持 `config -c root=D:\...` |
| `config -c` | 交互式逐项修改（回车 = 跳过该项） |
| `config -s` | 保存到 `config.json`，下次启动自动读取 |
| `config -r` | 恢复内置默认值（只在内存里，要清掉文件就删 `config.json`） |
| `set <项> <值>` | `config -c` 的简写 |
| `dry` / `preview` | 切换预览开关（也可写 `dry on` / `dry off`） |
| `color` | 开关彩色输出（也可 `color on` / `color off`） |
| `cls` / `clear` | 清屏 |
| `exit` / `quit` / `q` | 退出 |

`ls` 的运营方/平台支持**不区分大小写的部分匹配**（`ls xia v` 这种），也认别名表里的中文（`ls 厦门 Vivo`）。

```
npf> ls XiaMen Vivo
D:\UnityOutput\XiaMen\Vivo  (6 个游戏)
  HaiShangShengCun60s     齐全
  JieQuGeDouWangZhe       齐全
  MoNiHuoCheSiJiJiaShi    缺 批处理 / 签名 / 成品包
  ...
```

### 「齐全 / 缺 xx」是怎么判的

| 检查项 | 判定依据 |
|---|---|
| `V1` | 游戏目录下有 `V1\` |
| `批处理` | 游戏目录下有任意 `.bat`（**华为这类本来就没批处理的平台不查这项**） |
| `签名` | 游戏根目录（或某个直接子目录）里有成对的 `certificate.pem` + `private.pem` |
| `成品包` | 平台对应的编译产物 `*.rpk` 已生成，位置见下表 |

成品包 `*.rpk` 各平台的位置：

| 平台 | 位置（相对游戏目录） |
|---|---|
| Vivo | `V1\webgl_vivo\dist\` |
| OPPO | `V1\quickgame\dist\` |
| RongYao | `V1\webgl_qg\dist\` |
| XiaoMi | `V1\MiQGameBuild\MiQGame\dist\` |
| HuaWei | **不固定**：`output\dist` / `build\` / `formal\` / `正式包\` / `测试包\` 都出现过，所以在游戏目录内限 4 层递归找 |

> ⚠️ 游戏根目录下那些 `.zip / .rar` 是**归档压缩包**，不是编译产物——大部分游戏本来就没有（XiaoMi 20 个里只有 9 个有），所以**不参与判定**。
>
> 要接新平台，在 `_core\NewPackFolder.py` 的 `DIST_PATH` 字典里补一行即可。

配置项共 5 个：`root`（输出根目录）/ `sign_root`（签名库）/ `batch_src`（批处理源）/ `alias`（别名表）/ `auto_open`（建完自动打开，`on` / `off`）。

**建完自动打开**默认是开的。关掉有几种方式：`open off`（只本次会话）、`config -c auto_open off` + `config -s`（长期）、或启动时加 `--no-open`。

`open` 定位时的几个细节：带了 `\ / :` 的参数一律当路径；只有游戏名有歧义时会**列出所有同名候选**（同一个游戏往往 OPPO/Vivo/XiaoMi 各有一份）让你挑；运营方匹配到多个（比如 `xia` 同时命中 `LongXiangYou`/`XiaMen`/`ZhiDianTianXia`）会明确报歧义而不是瞎猜。

优先级：**命令行参数 > `config.json` > 内置默认值**。改配置时如果目录/文件不存在，只会提醒一句，仍旧记下。

## 颜色

为了人工翻屏时好找，输出按含义分了色：

| 颜色 | 表示 |
|---|---|
| 亮蓝 | 目录 / 路径 |
| 亮绿 | 游戏名 / 游戏目录 |
| 亮黄 | 运营方 |
| 亮紫 | 平台 |
| 青色 | 命令 / 配置项 / 标题行 |
| 绿 | 齐全 / 成功 |
| 黄 | 不完整（缺 xx）/ 提醒 |
| 红 | 缺失 / 失败 |
| 灰 | 次要信息 |

**自动判断**：真终端里自动开（Windows 会顺手打开 VT 处理）；输出被重定向到文件时自动关，不会往日志里塞乱码。想手动控制就用 `color` 命令，或设环境变量 `NPF_COLOR=1` / `NPF_COLOR=0`（`NO_COLOR=1` 也认）。

只跑一条、不进命令模式：把标题当参数传进去就行（可配合 `--yes` 无人值守）。

## 它会做什么

以标题 `[vivo-rpk]《模拟火车司机驾驶》(地铁模拟器3D) 正式包 厦门-吴伟` 为例：

1. 解析出：平台 `vivo` / 游戏名 `模拟火车司机驾驶` / 原工程名 `地铁模拟器3D` / 运营方 `厦门`（`-` 后面的 `吴伟` 是人名，不建目录）
2. 建目录：`D:\UnityOutput\XiaMen\Vivo\MoNiHuoCheSiJiJiaShi\`，里面再建 `V1\`（放 Unity 导出的工程文件）
3. 从 `D:\Resources\111\批处理` 复制对应平台的批处理到**游戏根目录**（与 `V1` 同级）
4. 找签名，把 `certificate.pem` + `private.pem` 复制到**游戏根目录**：一般平台按**原工程名**在 `D:\Resources\GameSign` 里递归搜；**华为 / 荣耀按运营方**取（详见下面「签名从哪来」）

结果：

```
D:\UnityOutput\XiaMen\Vivo\MoNiHuoCheSiJiJiaShi\
├─ V1\                       ← Unity 工程文件
├─ .PackNewVivoRpk.bat       ← 平台批处理
├─ certificate.pem           ← 签名
└─ private.pem
```

## 命名规则

| 来源 | 用途 |
|---|---|
| `[]` 内第一段 | 平台（`vivo` / `oppo` / `xiaomi` / `honor` / `huawei`） |
| `《》` 内 | **游戏名** → 游戏文件夹 = 它的驼峰拼音 |
| `()` 内 | **原工程名** → 只在 GameSign 里搜签名用 |
| 末尾 `运营方-人名` | `-` 前是运营方（建目录），`-` 后是人名（忽略） |

- 拼音规则：逐字转、首字母大写、拼起来（`模拟火车司机驾驶` → `MoNiHuoCheSiJiJiaShi`），英文数字原样保留（`海上生存60s` → `HaiShangShengCun60s`）
- 运营方目录**优先复用 `D:\UnityOutput` 下已存在的目录**，匹配不上再按拼音；再匹配不上会列出现有目录让你选
- 多音字（如 `厦门` 默认读 shà）已在脚本内置纠错；`孙波` / `博恒` 这类别名写在 `operator_alias.json`

## 平台对应表

| 标题关键字 | 平台目录 | 批处理 |
|---|---|---|
| `vivo` | `Vivo` | `.PackNewVivoRpk.bat` |
| `oppo` | `OPPO` | `.oppopack.bat` |
| `xiaomi` / `小米` | `XiaoMi` | `.PackXiaoMi.bat` |
| `honor` / `荣耀` | `RongYao` | `.PackRongYao.bat` |
| `huawei` / `华为` | `HuaWei` | 无（只建目录 + 签名） |

> `.packOppo.bat` 是旧版，**脚本不会用它**。

## 签名从哪来

### 一般平台（Vivo / OPPO / XiaoMi）

在 `D:\Resources\GameSign` 下**递归**搜名字含**原工程名**（括号里那个）的目录，往里再递归找两个 `.pem`。

- 搜到多个候选会停下来让你选（例如 `t1010_模拟城市大巴` 与 `真实山地越野车模拟器(模拟城市大巴签名)`），可选 `0` 跳过
- 一个都没搜到时，会给你手动粘贴路径的机会（回车即跳过）

### 华为 / 荣耀（规则不同）

这两个平台的签名**不按工程名，按运营方**，统一放在：

```
D:\Resources\GameSign\1.华为-rpk（各运营签名文件）\<运营方>\{certificate.pem, private.pem}
```

定位顺序：

1. `operator_alias.json` 的 `_hw_sign_folders` 映射（运营方目录 → 签名文件夹）
2. 标题里的中文运营方名直接对上
3. 模糊匹配（相似度 ≥ 0.6）
4. 仍然定不下来 → **把全部可选运营方列出来让你选**，绝不瞎猜

现成的对应关系（**12 个运营方已全部对上**，照实际目录核对过）：

| UnityOutput 运营方 | 签名文件夹 |
|---|---|
| XiaMen | 厦门 |
| SunBo_BoHuan | 博恒 |
| ZhiDianTianXia | 指点天下 |
| BiaoYue | 标越 |
| Yezi | 深圳烨子 |
| WanBan | 玩伴 |
| WanBianTi | 玩变体 |
| LuZong | 路总 |
| ChenZhiWen | 陈志文 |
| ChenZhiQing | 陈志晴 |
| LongXiangYou | 龙翔游 |
| WanShiRong | 冰天 |

> 目录名没写死：脚本按「名字里同时含**华为**和**签名**」自动找那个文件夹，改名也能认出来。

## 其他细节

- **可重复运行**：目录已存在不会报错，只补齐缺失的文件；已存在的文件默认跳过，加 `--force` 才覆盖
- 脚本会把该平台下已有的游戏目录列出来供你核对，避免拼音对不上建错
- 参数：`--root`（默认 `D:\UnityOutput`）、`--sign-root`、`--batch-src`、`--alias`、`--dry-run`、`--yes`、`--force`

## 文件

```
批处理工具\
├─ 新建打包目录.bat        ← 双击这个
├─ operator_alias.json     ← 运营方别名表（要改就改这个）
├─ README.md
└─ _core\
   └─ NewPackFolder.py     ← 实现，别双击
```

| 文件 | 作用 |
|---|---|
| `新建打包目录.bat` | 双击入口，自动找 Python 并检查依赖（纯 ASCII，不会有中文乱码） |
| `_core\NewPackFolder.py` | 主逻辑 |
| `operator_alias.json` | 运营方中文 → 实际目录名的别名表（多音字/旧错名都往这加） |

依赖：Python 3 + `pypinyin`（首次运行 bat 会自动装）。

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 弹出「你要用什么打开这个文件」 | 双击到 `_core\NewPackFolder.py` 了，改双击 `新建打包目录.bat` |
| 窗口一闪就没 | 用 `新建打包目录.bat` 启动（它结束时有 `pause` 会停住）；或看下是不是 Python 没装 |
| 提示 `[X] Python 3 not found` | 装 Python 3 并勾选 "Add python.exe to PATH" |
| 运营方目录建错了 | 往 `operator_alias.json` 加一条 `"中文": "实际目录名"` |

## 新机器 / 新人第一次用

**目录会自己建**：运营方目录不存在、连 `D:\UnityOutput` 本身都不存在，脚本也会一级级建出来。平台目录名（Vivo / OPPO / XiaoMi / RongYao / HuaWei）是写死的，不会错。

**坑在运营方目录名**：本地一个目录都没有时，名字只能靠拼音推，遇到不规则写法就会错——

| 中文 | 拼音推出来 | 实际应该是 |
|---|---|---|
| 叶子 | ~~YeZi~~ | `Yezi` |
| 孙波 / 博恒 | ~~SunBo~~ / ~~BoHeng~~ | `SunBo_BoHuan` |

所以 `operator_alias.json` 里放两样东西：`_operators`（运营方目录名单，标准写法）+ 别名（多音字 / 旧错名）。

查名字顺序：**别名表 → 本地已有目录 → `_operators` 名单 → 拼音**。

> ⚠️ **新增运营方时一定往 `_operators` 里补一条**，否则新人的机器上会建出一个拼错的目录名。

另外两样是**共享资源，拷不过去**，得单独同步：`D:\Resources\111\批处理`（批处理源）、`D:\Resources\GameSign`（签名库）。对不上不会崩，但会明确提示「源批处理不存在」「未搜到签名」。

顺带做了个防手滑：把整条 teambition 标题粘到「运营方」或「游戏目录」的输入框里时会被拒绝，回退到自动推导的名字，不会建出个怪目录。

## 发给别人

**不用整个目录都发。** 这 4 个就够：

```
NewPackFolder\
├─ 新建打包目录.bat        ← 必须
├─ operator_alias.json     ← 必须（别名表：多音字 / 旧错名）
├─ README.md               ← 建议带
└─ _core\
   └─ NewPackFolder.py     ← 必须
```

下面两样**别带**：

| 别带 | 原因 |
|---|---|
| `config.json` | 装的是本机配置。不发就用内置默认值，而内置默认恰好就是 `D:\UnityOutput` + `D:\Resources\...` 这几个——所以通常根本不需要它 |
| `.workbuddy\` | 开发笔记，和用工具无关 |

（顺带做了个保险：`config.json` 里工具目录内部的路径会存成**相对路径**，所以万一带上了，换机器也还能读到别名表。）

对方那边需要：

- **Python 3**（首次运行 bat 会自动 `pip install pypinyin`，需要联网）
- `D:\UnityOutput` / `D:\Resources\GameSign` / `D:\Resources\111\批处理` 这套目录。位置不一样就 `config -c root <路径>`，再 `config -s` 存下来。

现成的包：**`NewPackFolder-dist.zip`**，解压即用。
