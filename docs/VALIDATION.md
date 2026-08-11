# v1.0.0 验证记录

## 实机验证

2026-08-11，在 Epic Games 版《Mafia II: Definitive Edition》+ Friends for Life 1.1 + Chinesesimp 环境完成实机验证：

- Friends for Life 可以正常进入；
- 游戏原有简中 UI 文本正常；
- `77010001~77010018` 不再显示 `Undefined text id`；
- 18 条 FFL 自定义文本正常显示简体中文。

## 补丁器离线回归验证

使用同一组干净实测文件执行：

```text
patcher.py install
```

生成的主简中文本 SDS SHA256：

```text
4260635d00c95ca9c12195f3b0e8a32b7275c4c09ded3ec65c3912ab96477543
```

与当天实机成功版本逐字节一致。

生成的 ZFL `sds_sc` GUI SDS SHA256：

```text
49f7f8f4b85147c0241bf48df66548b55ca38d71de2eba71119c577cc772172f
```

与当天最终测试环境逐字节一致。

随后执行：

```text
patcher.py uninstall
```

原 `content` 与 `text_default.sds` 均恢复为备份前的逐字节原文件，原本不存在的 `sds_sc/gui/gui-main_dlc_zfl.sds` 被正确删除。

## 原版实测样本哈希

以下仅用于识别实测版本，不代表所有合法发行版本都必须完全一致：

```text
原版 Chinesesimp text_default.sds
6b6ba43220997900fafe2c5fc765ea7d1dae8057017f3d3dbd7822c30c2c7efe

FFL 1.1 English gui-main_dlc_zfl.sds
d7c5980e8549acad6086de966ab6b4bdae0eafe494d866e54d8bf293014303a8
```
