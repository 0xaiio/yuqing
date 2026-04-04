# Windows Build Tools 安装步骤

这份说明面向 `Windows + Tauri + Rust` 的本地开发环境。

## 1. 以管理员身份打开 PowerShell

1. 在开始菜单里搜索 `PowerShell` 或 `Windows Terminal`
2. 右键
3. 选择“以管理员身份运行”

后面的安装命令都建议在这个管理员窗口里执行。

## 2. 用 winget 安装 Visual Studio Build Tools 2022

执行下面这条命令：

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e `
  --accept-package-agreements `
  --accept-source-agreements `
  --override "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --includeRecommended"
```

这条命令会安装：

- `MSVC v143 C++ toolset`
- `Windows 11 SDK 22621`
- Tauri/Rust 在 Windows 下常用的 C/C++ 编译依赖

## 3. 如果 winget 安装失败，走图形界面安装

1. 运行：

```powershell
Start-Process "https://visualstudio.microsoft.com/visual-cpp-build-tools/"
```

2. 下载并启动安装器
3. 勾选 `使用 C++ 的桌面开发`
4. 在右侧确认这两个组件已被勾选：
   - `MSVC v143 - VS 2022 C++ x64/x86 生成工具`
   - `Windows 11 SDK (10.0.22621.x)`
5. 点击安装

## 4. 安装完成后重新打开终端

安装完成后请关闭当前终端，再重新打开一个新的 PowerShell 或 Windows Terminal。

## 5. 验证是否安装成功

先检查 Visual Studio 安装记录：

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe" -products * -format json
```

再检查 `cl.exe`：

```powershell
where cl
```

如果能看到类似 `...\VC\Tools\MSVC\...\bin\Hostx64\x64\cl.exe` 的输出，说明 Build Tools 已经可用。

## 6. 如果 Rust 也需要补 PATH

如果 `rustc` 或 `cargo` 提示找不到，可以先临时执行：

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
rustc --version
cargo --version
```

项目自带的 `start-local.ps1` 和 `start-local.bat` 已经会自动补这段 PATH，并在 `-WithTauri` 模式下自动导入 Visual Studio Developer Shell，但手动开新终端时仍可能需要你自己加到系统环境变量。

## 7. 验证 Tauri

依赖安装完成后，进入前端目录运行：

```powershell
cd d:\code-repos\yuqing\frontend
npm run tauri:dev
```

如果能正常弹出桌面窗口，说明环境已经齐全。
