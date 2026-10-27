# 来源与许可

本仓库由 Fsasdddd 发布。新增独立移植工具及说明按根目录 MIT 许可提供；已存在的第三方源码、补丁和派生内容保留其原许可和版权，根 MIT 不替换这些许可。

- `userland-source/` 选定公开文件来自 OOSEX GANG 的 hackios-xnu-userland，固定提交 `906425b75e02b4f99eb5d7bb1ef7c9583472d772`，项目原生代码 MIT，全文见 `LICENSES/upstream-userland-MIT.txt`。本地改动列于 `patches/userland-local-changes.patch`。
- XNU/内核构建基线为 hackios-xnu-kernel `8e61187098f2c26c5daee8f9f72b6416aa64b9ab`，上游根许可 APSL 2.0，见 `LICENSES/APSL-2.0.txt`。本仓库通过链接及固定版本引用该内核，不重新分发完整 XNU。相关原始文件的逐文件版权及许可继续有效；生成或部署派生内核需遵守适用许可。
- `userland-source/tools/mesa/` 是上游公开构建补丁/桥接代码。Mesa 及其派生补丁依各自文件的原 MIT 等许可，不以发布者名义重新授权上游内容。完整 Mesa 源码与许可由固定版本下载提供。
- 寄存器/配置研究参考 Linux v6.12 MSM/Freedreno、Mesa 24.3.0 XML 及 Xiaomi lmi-q-oss；工具中的固定哈希用于审计来源，不意味着重新授权这些项目。

没有 Apple iOS 闭源二进制、SDK、系统镜像、Qualcomm 固件或设备备份。

上游：
- https://github.com/oosexgang/hackios-xnu-kernel
- https://github.com/oosexgang/hackios-xnu-userland
- https://gitlab.freedesktop.org/mesa/mesa
- https://github.com/torvalds/linux/tree/v6.12/drivers/gpu/drm/msm
- https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/lmi-q-oss

UEFI 平台/BootShim/Mu overlay 和相关差异沿用 Mu-Silicium、Mu_Basecore 及各文件原始许可，见 LICENSES/Mu-Silicium-BSD.txt；由公开 loader 源码生成的嵌入 C 数组按原源码许可。


`build-support/v72/` 中的生成C源码、头文件和链接脚本保留原始来源关系；从已有合成/图形源码生成的测试输入沿用对应源文件许可，独立测试与构建辅助部分按根MIT许可。生成目录不含系统镜像、固件或内核二进制。
