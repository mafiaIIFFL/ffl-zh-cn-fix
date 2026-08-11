# FFL中文翻译及修复补丁

适用于 **《Mafia II: Definitive Edition / 黑手党2：最终版》+ Friends for Life 1.1** 的简体中文兼容、文本修复与汉化项目。

> 当前状态：**v1.0.0，实机验证成功**  
> 实测平台：**Epic Games 版《黑手党2：最终版》**  
> 游戏语言：**简体中文（Chinesesimp）**

## 解决什么问题

原版 Friends for Life 1.1 在英文环境下可以正常进入，且自定义文本 ID `77010001~77010018` 正常显示；切换简体中文后会出现两类问题：

- “附加内容”里能看到“一生挚友”，但点击后无法正常进入；
- 修复进入问题后，圆形菜单中 FFL 自定义文本仍显示 `Undefined text id: 770100xx`。

本项目同时处理这两部分，并为 18 条 FFL 自定义文本提供简体中文翻译。

## 最终修复结论

实机排查确认：

- 单纯增加 `sds_sc` 挂载不能解决 `770100xx`；
- 单纯复制 FFL 英文 `TextDatabase_MainMenu_ZFL.dat` 不能解决；
- 单独增加 `MainMenuTdbFile` 不能解决；
- 单独修正 ZFL SDS 的 `ResourceInfo` 顺序不能解决；
- **真正解决 `77010001~77010018` 的关键，是把这些 ID 合并进简中实际使用的主文本库 `pc/sds_sc/text/text_default.sds`。**

安装器会自动完成所需修改，并在修改前创建完整备份。

## 安装条件

1. 已安装《Mafia II: Definitive Edition》。
2. 已安装 **Friends for Life 1.1 原版 MOD**。
3. 游戏准备使用**简体中文**。
4. 安装补丁前完全退出游戏。

项目**不包含** 2K、Hangar 13 或 Friends for Life MOD 的原始游戏资源；所有 SDS 修改均基于用户本机已有文件生成。

## 最简单的安装方法

### 源码版

1. 下载本仓库并解压。
2. Windows 双击：

```text
install.bat
```

3. 按提示输入游戏根目录，例如：

```text
D:\Epic Games\MafiaIIIDE
```

正确目录内应该能看到 `pc` 文件夹。

4. 安装完成后，将游戏语言设为**简体中文**。
5. 启动游戏：

```text
附加内容 → 一生挚友
```

### 命令行

```powershell
python patcher.py install --game-dir "D:\Games\MafiaIIIDE"
```

检查安装状态：

```powershell
python patcher.py status --game-dir "D:\Games\MafiaIIIDE"
```

## 自动备份与卸载

安装前，补丁会自动在游戏根目录创建：

```text
FFL_ZH_CN_BACKUP\时间戳\
```

其中保存被修改文件的原始版本和 `manifest.json`。

恢复最近一次备份：

```text
uninstall.bat
```

或：

```powershell
python patcher.py uninstall --game-dir "D:\Games\MafiaIIIDE"
```

## 补丁会修改什么

安装器只处理以下路径：

```text
pc\dlcs\cnt_friendsforlife\content
pc\dlcs\cnt_friendsforlife\sds_sc\gui\gui-main_dlc_zfl.sds
pc\sds_sc\text\text_default.sds
```

主要动作：

1. 为 FFL 增加 `Chinesesimp` / `GameLine_3_Chinesesimp` 挂载；
2. 从用户本机 `sds_en` 复制 ZFL GUI SDS 到 FFL 的 `sds_sc` 语言目录；
3. 将 `77010001~77010018` 的简中翻译安全合并进简中主 TextDatabase；
4. 重算 SDS FNV1 安全校验和资源大小；
5. 修改完成后再次解析并执行 round-trip 校验；失败则自动回滚。

## 18 条中文翻译

翻译表位于：

```text
translations/zh-CN.json
```

例如：

| ID | English | 简体中文 |
|---|---|---|
| 77010001 | Change weather/time | 更改天气/时间 |
| 77010002 | Change character model | 更改角色模型 |
| 77010007 | Open garage | 打开车库 |
| 77010012 | Exit from menu and save game | 退出菜单并保存游戏 |
| 77010014 | Animation menu | 动画菜单 |
| 77010016 | Cheat: Add all weapons | 作弊：获得全部武器 |
| 77010017 | Cheats menu | 作弊菜单 |

完整 18 条请直接查看 JSON。

## 兼容性

目前正式实测：

- ✅ Epic Games 版《Mafia II: Definitive Edition》
- ✅ Friends for Life 1.1
- ✅ 简体中文

Steam / 其他发行渠道可能具有相同资源结构，但目前**没有宣称已经实机验证**。安装器会先解析 SDS 并执行结构校验；如果检测到不兼容结构，会中止并回滚，而不是强行覆盖。

## 为什么不直接提供修改后的 `text_default.sds`？

因为它属于游戏原始资源的修改版本。这个仓库采用**本地补丁器**：只保存代码和翻译表，由用户自己的正版游戏文件生成修改结果。这样也更容易兼容不同安装位置和后续版本。

## 项目结构

```text
FFL中文翻译及修复补丁/
├─ patcher.py                 # 自动补丁器
├─ install.bat                # Windows 安装入口
├─ uninstall.bat              # 恢复备份
├─ status.bat                 # 状态检查
├─ translations/
│  └─ zh-CN.json              # 18 条翻译
├─ docs/
│  └─ TECHNICAL_NOTES.md      # 排查过程与技术结论
├─ tests/
├─ .github/
├─ CHANGELOG.md
├─ LICENSE
└─ README.md
```

## 说明

- 本项目不是 Friends for Life 原作者发布的官方中文版本。
- 本项目不包含《Mafia II: Definitive Edition》的原始游戏文件。
- Friends for Life、Mafia、2K、Hangar 13 及相关名称/商标归各自权利人所有。
- 请在拥有合法游戏副本的前提下使用。

## 致谢

感谢 Friends for Life 原作者及 Mafia MOD 社区。这个补丁来自对 English / Chinesesimp 语言加载、官方 DLC TextDatabase 与 FFL 自定义文本注册差异的逐项实机排查。
