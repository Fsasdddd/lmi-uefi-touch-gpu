# 构建与验证

> 当前公开版本为 **v72b**。最新原理、源码入口及已结束实机结果见 [v72专题](V72.zh-CN.md)；以下旧轮次与v59记录保留为历史，不能代替v72结论。

这是源码和移植工具的公开快照，不是 clone 后自动生成完整 iOS 镜像的一键工程。脚本保留了原实验路径、固定 kernel 布局及哈希检查；不能直接套到别的内核或设备。

## 固定上游

```sh
git clone https://github.com/oosexgang/hackios-xnu-kernel.git hackios
git -C hackios checkout 8e61187098f2c26c5daee8f9f72b6416aa64b9ab
git clone https://github.com/oosexgang/hackios-xnu-userland.git upstream-userland
git -C upstream-userland checkout 906425b75e02b4f99eb5d7bb1ef7c9583472d772
git -C upstream-userland apply ../patches/userland-local-changes.patch
```

上面补丁应用于完整上游；本仓库 `userland-source/` 已包含选定文件的修改结果，不要再对这些快照重复打补丁。完整构建需按上游说明把 userland、XNU 工具链及公开依赖组合进构建树，再覆盖选定源码。Mesa 补丁沿用其来源许可。

原环境为 Windows + WSL Ubuntu 24.04。脚本默认项目路径为 `F:/PersonaLive`（WSL `/mnt/f/PersonaLive`），构建树 `/root/hackios-lmi/hackios`，编译器 `xnu-deps/host/bin/xnu-clang`，SDK `/root/hackios-lmi/gpu-build-env/theos/sdks/iPhoneOS16.5.sdk`。须自行准备合法 SDK/固件/系统输入，调整显式路径；设备序列号已改为 `YOUR_ADB_SERIAL`。本仓库未提供这些输入或历史 `out/` 产物。

## 不访问设备的检查

在 Linux/WSL、仓库根目录，安装 Python3、Clang（支持 ASan/UBSan）后：

```sh
python3 tools/check-lmi-gpu-gl-verifier.py
python3 tools/check-lmi-touch-reports.py
mkdir -p out
clang -O1 -g -fsanitize=address,undefined tools/check-lmi-touch-timing.c -o out/touch-timing
./out/touch-timing
clang -O1 -g -fsanitize=address,undefined tools/check-lmi-gpu-desktop.c -o out/gpu-desktop
./out/gpu-desktop
python3 tools/check-lmi-hid-usage.py
python3 tools/check-lmi-hid-startup.py
python3 tools/check-lmi-input-observers.py
python3 tools/check-lmi-hid-routing.py
```

其他源码审计/区域审计/组合预检会读取固定上游源码、符号表和实际构建产物，不属于无输入即可运行的测试。缺文件必须准备输入，不能删除 hash、范围或前置条件使其通过。

## 原离线构建档位

在完成上述完整环境准备后，原项目使用以下档位（不含 `--package`，不访问设备）：

```sh
python3 tools/build-lmi-gpu-mode.py 46 --tile --desktop --ios-observe-seconds 180 --touch-input --cpu-profile
```

`build-lmi-gpu-gl-image.py` 仅组装已有 Mesa/shim/probe 产物；不能代替 Mesa 编译。`--ios-boot-image` 才替换 checkpoint63 最终 md1 候选，`--root-image` 不是等价参数。构建需核对 kernel、loader、源文件、timing header、镜像 manifest 的绑定。

`test-lmi-checkpoints.py` 是会操作真实设备的历史测试器；本次发布未运行它。研究者应自行核实有界 RAM 返回、设备标识和前置条件。原测试采用临时 fastboot boot，不提供或要求分区刷写。

触控用途缓存修正通过 `build-lmi-gpu-gl-image.py --hid-usage-recheck` 显式启用，需与已有 payload、固件、trace/ABI 检查保持匹配。v31/v32 的成功结论仅对应已归档的同一镜像，不默认推广到其他构建。


## v59 更新

2026-10-27 已结束测试的 v59b 源码、单层整帧复制原理、前序异步 GPU 管线、验证范围与统计 ABI 缺陷详见 [v59 专文](V59.zh-CN.md)。整体结果仍为 INCOMPLETE；交互改善不能覆盖无效 FAST 计数或长期稳定性缺口。

## v72 更新

触控采样间隔中位约30.1ms降至10.2ms，实机确认响应与跟手性改善。4513/4513次完整帧GPU复制完成，新严格准入通过；整体仍为INCOMPLETE，本轮旧总线时钟记录断言受日志交错影响。未测屏幕FPS或触控到光子时间，Wi-Fi未集成。详细机制、来源和验证边界见 [v72专题](V72.zh-CN.md)。
