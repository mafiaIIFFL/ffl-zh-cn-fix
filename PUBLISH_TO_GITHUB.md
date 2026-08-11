# 发布到 GitHub

推荐仓库名：

```text
ffl-zh-cn-translation-fix
```

项目显示标题已经在 README 中设为：

```text
FFL中文翻译及修复补丁
```

## Git 命令

在项目目录打开 PowerShell：

```powershell
git init
git add .
git commit -m "release: v1.0.0"
git branch -M main
git remote add origin https://github.com/你的用户名/ffl-zh-cn-translation-fix.git
git push -u origin main
```

如果安装了 GitHub CLI，也可以在本目录执行：

```powershell
gh repo create ffl-zh-cn-translation-fix --public --source=. --remote=origin --push
```

## Releases

仓库包含 `.github/workflows/build-exe.yml`。

发布 GitHub Release 后，GitHub Actions 会构建 Windows 单文件版：

```text
FFL中文翻译及修复补丁.exe
```

源码版用户也可以直接使用 `install.bat`。

## 建议 Release 标题

```text
v1.0.0 - 首个实机验证成功版本
```

建议 Release 简介：

```text
修复 Mafia II: Definitive Edition 的 Friends for Life 1.1 在简体中文环境下无法正常进入及 77010001~77010018 显示 Undefined text id 的问题，并完成 18 条自定义文本简体中文翻译。Epic Games 版已实机验证。
```
