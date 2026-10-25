# lmi UEFI 移植方法与源码

## 基线与源码目录

以 Project-Silicium/Mu-Silicium 历史 lmi 平台和 HackiOS 的 Mu 适配为起点。当前构建基线 Mu 提交为 `e51cd877e31c8fbb322032dc4cb6715e83d25ad3`，Mu_Basecore 为 `cfb93724a06ff86ff5ba971413368a7809ee42a5`；其余依赖固定在 `dependency-cache/manifest.json`。

- `uefi/mu-silicium-overlay/`：从实际 WSL 构建树导出的 lmiPkg、BootShim、BootManager/嵌入 loader 和配置源码。保留原版权，不包含 Binaries 或 Build。
- `patches/mu-silicium-local.patch`、`mu-basecore-local.patch`：实际构建树相对固定基线的修改。前者的 untracked 新文件由 overlay 补齐，后者包括计时器、菜单、USB/汇编及变量服务等上游适配差异。
- `patches/upstream-hackios-mu.patch`：HackiOS 原公开 Mu 适配补丁，供来源对照；已包含在实际本地差异中，不要重复打。
- `port-drafts/uefi/`：迁移脚本的输入模板与早期独立诊断入口；不是比实际 overlay 更新的另一份驱动。

## 1. 平台与内存布局

从设备 live DT、原 boot header 和 XBL 取得板级信息，而不是直接把 alioth 的地址当作 lmi。以当前 Mu API 的 aliothPkg 作为包结构模板，设备名与 SMBIOS 改为 lmi / Redmi K30 Pro，SOC_TYPE=0（SM8250）。保留 lmi 的 MemoryMapLib/ConfigurationMapLib，将历史 Terminator 风格接口迁移到显式数组及数量接口。

历史 FD 放在 `0x9fc00000`，大小 `0x300000`；framebuffer 实测在 `0x9c000000`。内存图还区分 TZ/PIL/SMEM、显示保留区、FD、SEC heap、页表、栈和 MMIO 的类型/缓存属性。payload、framebuffer、加载缓冲区与保留区需要组合检查，不能只验证 FD 地址。

XNU 使用生成的 Apple 风格 DT，因此该档位移除 alioth 的设备 ACPI 表；SimpleFbDxe 继承 bootloader 已初始化的显示，不引入不匹配的 panel XML。具体转换见 `tools/stage-lmi-uefi.py`。

## 2. 从自己的 lmi 固件取得闭源驱动

历史 lmi 二进制目录的 XBL.info 曾指向 alioth，版本字符串相同也不代表模块相同。应从本人设备的 XBL 只读副本，通过公开 UEFIReader 解出 `BOOT.XF.3.2-00304-SM8250-2` 结构，放到脚本要求的 `firmware-extracted/xbl_4/`。`inventory_firmware.py` 与 `audit-lmi-firmware.py` 检查 INF 路径、模块数量与哈希；公开仓库不含 XBL 或提取出的 EFI/资源。

`tools/patch-lmi-firmware.py` 是五模块的可读补丁配方：ButtonsDxe 电源键 Enter 映射、DALSYSDxe 的 UFS IORT coherency 字段、TzDxe 初始化标记、UsbConfigDxe 保留 device mode、UsbMsdDxe 的 INQUIRY RMB 字节。每项检查精确输入 SHA256、偏移和原始字节，写到独立输出目录，并验证变更范围及长度。只支持列明的固件；不匹配立即拒绝，不可直接在其他版本套偏移。

## 3. BootShim、BootManager 与 loader

BootShim 提供 ARM64 kernel header 并把 FD 放到预定位置。纯控制台诊断构建不定义 PAYLOAD_BASE，因此 payload-copy 分支不编入；打包器验证入口、符号、FD 长度、FV 校验和及 ARM64 PE。

BootManager 的 lmi 入口先报告异常级、GOP 几何/地址及 UsbFunctionIo，再按显式档位启动 USB 诊断或受保护的 XNU loader。`LmiUsbProbe.h` 是由公开 loader 源码构建后嵌入的 C 字节数组，属于本项目 EFI 应用，不是提取的 Qualcomm 固件；对应构建入口是 `tools/build-lmi-loader.py`。早期仅诊断 `XnuLoader-lmi-diagnostics.c` 不启动 XNU、不向原始日志分区写入。

## 4. 固定依赖并离线构建

```sh
git clone https://github.com/Project-Silicium/Mu-Silicium.git mu-silicium
git -C mu-silicium checkout e51cd877e31c8fbb322032dc4cb6715e83d25ad3
# 按 dependency-cache/manifest.json 准备固定的公共子模块。
# Binaries 使用自己的 lmi 提取物，不下载不相关设备二进制。
git -C mu-silicium apply ../patches/mu-silicium-local.patch
git -C mu-silicium/Mu_Basecore apply ../../patches/mu-basecore-local.patch
cp -a uefi/mu-silicium-overlay/. mu-silicium/
```

以上是源码 overlay 集成示意；实际脚本默认树位于 `/root/hackios-lmi/mu-silicium`，模板树 `Mu-Silicium-base` 和 `Mu-Silicium-v3.0` 需按所固定版本准备。已有工作树不要再重复应用 patch。`stage-lmi-uefi.py` 会重新生成部分平台文件和嵌入入口；应选择“从导出的完整 overlay 构建”或“脚本从输入重新生成”的路径，避免无意用早期诊断入口覆盖当前 loader。

原项目离线生成顺序（在完整依赖/固件输入准备后）：

```sh
python3 tools/patch-lmi-firmware.py
python3 tools/stage-lmi-uefi.py --patched
bash tools/build-lmi-uefi.sh
python3 tools/export-lmi-uefi.py --patched
python3 tools/package-lmi-diagnostics.py
```

`--full-loader` 档位另需先构建并校验 loader，再在 stage/export/package 保持同一选项。`tools/build-lmi-shim.sh` 是早期组件构建入口，其 PAYLOAD_BASE 示例不等于已完成整套加载布局；诊断打包器使用不带 payload-copy 的 shim。

Python Mu venv、Clang/LLD、AArch64 objcopy、NASM、ACPICA 和固定子模块属于外部依赖。脚本用 NASM 本地 shim，构建时不使用会更新所有依赖的 `-u`。原 `boot.img` 的 header v2/page4096 和 DTB 集合用于临时打包，不公开该设备备份。

## 已验证与边界

原项目已构建 3MB FD 并通过 FV/ARM64 校验，实机临时 UEFI 诊断取得 GOP/USB 信息，随后进入受保护的 XNU/iOS RAM 测试。此源码发布没有重新编译全部 UEFI 或再次上机；不能把早期文件注释里的 pending 或单个 host 构建当作当前整机支持结论。原始 FD 不是 Android boot image，不应直接传给 fastboot。

许可证：Mu-Silicium 为其上游 BSD 风格许可（`LICENSES/Mu-Silicium-BSD.txt`），Mu_Basecore 和各文件按原版权/许可；HackiOS 派生内容保留其原许可。本项目新增工具的 MIT 不替换上游许可。
