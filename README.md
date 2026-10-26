# Redmi K30 Pro / lmi：UEFI、触控与 Adreno 650 GPU 移植

**当前公开版本：v59（实测候选 v59b） · 2026-10-27**

面向 **Xiaomi Redmi K30 Pro（lmi / SM8250）运行 HackiOS / XNU / iOS 16.5** 的源码与处理原理。仓库公开 UEFI 平台移植、FT3518 触控、HID 初始化修正、Adreno 650 / Mesa Freedreno 图形链路，以及截至 v59 的显示优化、构建与验证工具。

v59 已完成一轮有界 RAM 实机测试：**流畅度体验有所改善，左右滑动和上划返回桌面仍掉帧，整体结果为 INCOMPLETE。** 本页以 v59 已结束的记录为准；离线检查、实际交互反馈与整体验证分别列出。

## v59 更新了什么

- **单层整帧复制优化**：完整单层 1125×2436 BGRA、pitch=4544 且符合表面资格时，跳过上一帧保留复制，在原 drawLayer 调用点一次 memcpy 写入自有缓冲。局部、多层或资格不符继续原合成路径。
- **异步 GPU 管线**：继承 v58 的一个在途任务提交方式，保留 GPU 就绪、真实完成检查、缓存/映射约束和退出排空。
- **DPU A/B 缓冲**：继续使用自有双缓冲、整帧完成检查、原缩放和恢复链。当前整帧优化仍包含 CPU 复制，源表面直接 DMA 尚未集成。
- **配套触控源码**：同步 v59 镜像实际使用的注入源码；用途缓存支持 0/0、13/0、0/4 的受限修正，原生初始化重试有界最多三次，保留完整或冲突缓存及不合法属性的拒绝检查。
- **源码与证据归档**：公开显示/GPU 前序依赖、冻结测试器、构建审计与筛选实机摘要，文件哈希记录在 [source-manifest.json](source-manifest.json)。

完整机制与代码入口见 [v59 技术说明](docs/V59.zh-CN.md)。

## 当前功能状态

| 模块 | 截至 v59 已观察到的结果 | 仍待完成 |
| --- | --- | --- |
| UEFI | lmi 平台 overlay、BootShim / BootManager 源码与移植方法已公开 | 发布过程未重新执行完整 UEFI 构建或新增硬件验证 |
| FT3518 / HID 触控 | 报文解码与事件链路已接入；v31/v32 两轮触控正常、设置可打开；v59 反馈其余功能正常 | 长时间稳定性、全手势及边缘场景覆盖 |
| GPU / GLES | 已有原签名固件认证、normal mode、GPU 像素回读和 FD650 GLES 绘制证据 | 所有 API、运行时故障恢复与整机长期稳定性 |
| GPU 异步提交 | v59 退出排空通过；670MHz 请求收到 ACK | 实际 GPU 时钟、提交重叠和受控性能收益未测量 |
| DPU 桌面输出 | v59 route2 记录 2812 桌面帧，无回退；退出恢复通过 | 固定 CRC 归一化仍属实验，严格像素等价与完整硬件缩放验证未通过 |
| 桌面动画 | v59 实际体验反馈流畅度改善 | 左右滑动和上划返回桌面仍掉帧；未获得受控动画 FPS |
| 整体验证 | Android 已返回，boot/dtbo 原哈希一致 | **INCOMPLETE**：原 index1 频率断言未通过，另有 FAST 统计 ABI 缺陷 |

## 已知问题与验证边界

**v59 的 FAST 计数无效。** ELF AArch64 helper 直接调用 Darwin 内核可变参数 `snprintf`，存在参数传递 ABI 不匹配。证据判定保持 `counts_valid=false`、`fast_path_exercised=false`；当前无法把体验改善归因为已经证实的快速路径命中。问题源码与诊断一并保留。

静止和交互混合窗口的帧数不能当作动画 FPS。日志中的 cache clean + kickoff 约 **625.03 微秒/帧**仅覆盖局部 CPU 工作，不含扫描输出、合成及 GPU 绘制。长帧和滑动掉帧仍存在，长期稳定性尚无充分结论。

此前版本的触控、GLES、壁纸和显示诊断记录保留在专题文档中；旧轮次的成功或失败不自动代替 v59 结论。实机摘要和原始证据哈希见 [v59-display.json](evidence/v59-display.json)。

## 源码导航

| 内容 | 说明与源码 |
| --- | --- |
| v59 整帧优化 | [技术说明](docs/V59.zh-CN.md) · [lmi-display-fast-v59.c](tools/lmi-display-fast-v59.c) · [构建器](tools/build-lmi-display-v59.py) |
| 异步 GPU 后端 | [lmi-gpu-desktop-v58.c](tools/lmi-gpu-desktop-v58.c) · [构建器](tools/build-lmi-gpu-async-v58.py) |
| 合成与缓冲管线 | [v56 compositor](tools/lmi-display-compositor-v56.c) · [v51 pipeline](tools/lmi-display-pipeline-v51.c) |
| 触控修正 | [处理原理](docs/TOUCH.zh-CN.md) · [inject.c](userland-source/userland/src/inject.c) |
| GPU 初始化与 GLES | [GPU 专题](docs/GPU.zh-CN.md) |
| UEFI 移植 | [方法与源码说明](docs/UEFI.zh-CN.md) · [Mu-Silicium overlay](uefi/mu-silicium-overlay/) |
| 构建与证据 | [构建说明](docs/BUILD.zh-CN.md) · [证据范围](docs/EVIDENCE.zh-CN.md) · [离线检查记录](validation.json) |

## 离线检查

在 Linux / WSL 中准备 Python 3 和 Clang 后，可独立运行：

```sh
python3 tools/check-lmi-display-fast-v59.py
python3 tools/check-lmi-display-v59-policy.py
python3 tools/check-lmi-gpu-async-v58.py
python3 tools/check-lmi-hid-usage.py
python3 tools/check-lmi-hid-initial-retry.py
```

本次公开副本已通过：17 个整帧集成场景、46 个证据用例、41 个异步 GPU 场景、117 个用途缓存场景和 1350 个原生初始化重试场景，以及源码哈希、Python 语法检查。适用的 C 检查启用 ASan/UBSan；Linux 主机测试不覆盖上述 Darwin 可变参数 ABI 缺陷，不能据此把实机 INCOMPLETE 改为 PASS。

## 构建输入、来源与许可

`tools/` 提供移植和验证工具，`userland-source/` 是选定公开源码及本地修改快照，`patches/` 保留相对固定上游的补丁。完整镜像构建依赖前序固定产物及自行取得的 iOS、SDK 和固件；原实验路径、哈希和 ABI 守卫仍保留，当前不支持仅凭本仓库一条命令重建完整启动镜像。

仓库不分发 Apple iOS 系统文件、SDK、dyld cache、Qualcomm / 触控固件、分区备份或可刷写镜像。原实验采用有界 RAM 临时启动，本次发布没有执行设备操作。

新增独立工具和文档按根目录 MIT 许可提供；第三方及派生内容沿用各自许可。详见 [来源与许可](NOTICE.md)、[LICENSE](LICENSE) 与 [LICENSES](LICENSES/)。
