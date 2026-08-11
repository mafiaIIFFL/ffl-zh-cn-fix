# 技术记录：Friends for Life 1.1 简中修复

## 已实机确认的三个初始状态

1. 原版 FFL + English：可正常进入，`77010001~77010018` 正常显示。
2. 原版 FFL + Chinesesimp：附加内容可见“一生挚友”，点击后无法进入。
3. 早期简中兼容方案 + Chinesesimp：可进入，但 `77010001~77010018` 全部 `Undefined text id`；游戏原有文本 ID 正常中文。

## 关键静态发现

- FFL `gui-main_dlc_zfl.sds` 内确实存在 `/tables/TextDatabase_MainMenu_ZFL.dat`。
- 其中 18 条键值为 `00_77_01_0001` ~ `00_77_01_0018`，对应显示 ID `77010001` ~ `77010018`。
- DAT 本体是 UTF-8 文本键值表，不含单独的“English locale header”。
- English `info` 为 `default=true / full=true`；Chinesesimp 为非默认、非 full 的覆盖层。
- 官方 Joe / Jimmy DLC 的相关文本 ID 已经存在于简中主 `text_default.sds` 中。
- FFL 的 18 个新增 ID 不存在于原版简中主文本库中。

## 已排除的单独原因

以下修改分别做过单变量实机验证，均不能单独解决 770100xx：

- 仅增加 Chinesesimp 正式 Mount；
- 仅把英文 ZFL SDS 放入 `sds_sc`；
- 仅增加 `MainMenuTdbFile`；
- 仅修正 ZFL SDS 末尾 ResourceInfo 顺序；
- 把 ZFL TDB 放入其他官方 DLC 的简中 SDS。

## 最终成功点

将 `77010001~77010018` 合并到：

```text
pc/sds_sc/text/text_default.sds
```

随后在简体中文环境中，圆形菜单的 FFL 自定义文本成功显示中文。

因此 v1.0 的核心修复是：

> 在 Chinesesimp 当前活动的主 TextDatabase 中正式加入 FFL 的 18 个新 ID。

## SDS 写入注意事项

`text_default.sds` 不能简单修改压缩数据后保存。M2DE SDS v19 中存在：

- 顶层 Safe block；
- FileHeader Safe block；
- ResourceHeader Safe block；
- FNV1 32-bit 校验；
- UEzl/zlib block；
- ResourceInfo XML 中的 RAM 大小元数据。

早期一次手工重建由于校验/封装不完整，导致游戏主菜单整个文本库失效。最终写入器先完成：

```text
原版 SDS → parse → serialize → 与原版逐字节完全一致
```

之后才进行 18 条文本插入。当前 `patcher.py` 在写回前后都执行结构校验，并在失败时自动恢复备份。

## v1.0 为什么还保留 MainMenuTdbFile / ResourceInfo 规范化

它们已经被证明**不是 770100xx 的根因**。但最终成功的实机环境中同时存在这两项修改，所以 v1.0 默认保留，以最大程度复现已经验证成功的组合。

未来若完成一次“仅 Chinesesimp Mount + 主文本库合并”的回归测试，可在后续版本进一步精简。
