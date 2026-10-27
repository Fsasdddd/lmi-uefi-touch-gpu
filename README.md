# Redmi K30 Pro / lmi：UEFI、触控与 Adreno 650 GPU 移植

**当前公开版本：v72（实测候选 v72b） · 验证日期：2026-10-27**

面向 **Xiaomi Redmi K30 Pro（lmi / SM8250）运行 HackiOS / XNU / iOS 16.5** 的源码与处理原理。公开 UEFI 平台移植、FT3518 / HID 触控、Adreno 650 / Mesa Freedreno，以及截至 v72 的完整帧 GPU 复制、缓存所有权、构建与验证工具。

**v72 触控响应和跟手性已获实机确认：同触点上报间隔中位数约30.1ms → 10.2ms。显示低帧率与掉帧仍待解决，整体结果仍为 INCOMPLETE。** 采样节奏、GPU 完成计数和屏幕动画 FPS 是不同指标；本页分别列出。

## v72 更新了什么

- **缩短实际触控轮询等待**：在精确 v71 内核上，只改三个 ARM64 立即数：有效报告等待20ms → 1ms，空闲/首次完整读失败等待50ms → 2ms，有限循环4000 → 409600。总线5us边沿、触点解析、HID初始化和 GPU/DPU 字节保持。
- **GPU 完整帧复制**：继承截至 v71 的 GPU 复制、映射复用、复制 fence 异步等待和延后 CPU 目标缓存转换。v72 记录4513/4513次完整帧 GPU 复制，合格帧 CPU copy_calls=0；另3帧走普通 CPU 路径。
- **减少缓存遍历**：GPU 所有的目标只在 CPU 首次读写前同步；实机 CPU 目标同步3次，少做4510次整帧缓存遍历，仍保留真实 fence 和所有权转换检查。
- **完整更新源码与证据**：加入 v60–v72 的相关源码及生成测试输入、v72 冻结测试器和分析器；原1875项冻结文件已复核。旧 v59 原理及失败记录继续保留。

[阅读 v72 处理原理、源码入口与限制](docs/V72.zh-CN.md) · [v59 历史说明](docs/V59.zh-CN.md)

## 触控改善有多少

| 同触点输入指标 | v71 | v72b |
| --- | --- | --- |
| 上报间隔中位 | 30.0655ms | 10.215ms |
| 上报间隔 p95 | 30.419ms | 10.568ms |
| 中位间隔倒数 | 约33.26次/秒 | 约97.90次/秒 |

v72 前192条输入包含183个有效同触点间隔；实际反馈确认“触控响应明显改善”“跟手了”。post→sent 中位262us、p95 958us。上述数据量化输入采样节奏，**不代表屏幕约98 FPS，也不代表触控到光子延迟缩短2.94倍**；物理触点与屏幕可见时刻尚未测量。详见 [采样对比](evidence/v72-input-cadence.json)。

## 当前功能状态

| 模块 | 截至 v72 已观察到的结果 | 仍待完成 |
| --- | --- | --- |
| UEFI | lmi 平台 overlay、BootShim / BootManager 源码与移植方法已公开 | 本次发布未重建完整 UEFI 或新增设备测试 |
| FT3518 / HID | v72 触控响应和跟手性改善，同触点间隔中位约10.2ms | 长期稳定、全手势和触控到光子测量；本轮设置/壁纸/颜色状态未单独确认 |
| GPU / GLES | 原签名固件认证、normal mode、像素回读及 FD650 GLES 历史证据；v72 GPU队列26440/26440 | 所有图形 API、运行时故障恢复及长期稳定性 |
| GPU 完整帧复制 | 4513/4513完成，pending=0、held=0，合格帧 CPU copy_calls=0 | 局部、多层等普通路径仍可能 CPU 合成；执行重叠与带宽收益未测 |
| 源表面与缓存所有权 | 源4517/4517退休，CPU目标同步3次，少做4510次缓存遍历 | 不等于源表面直接 DPU 扫描；性能收益仍需受控测量 |
| DPU 桌面输出 | 4516桌面帧，4556提交、4555计数完成，恢复与新严格准入通过 | 不能把全部提交写成完成；固定CRC归一化实验的像素等价限制仍保留 |
| 桌面动画 | 较活跃 native show 窗口约42–54次/秒，也有更低窗口 | 非屏幕实测动画FPS；低帧率/排队/DPU等待仍待处理，本轮未确认掉帧已解决 |
| Wi-Fi | 尚未集成或联网 | QCA6390 平台适配及完整联网验证 |
| 整体验证 | Android返回，boot/dtbo原哈希一致，新严格GPU/显示准入通过 | **INCOMPLETE**：冻结旧校验器总线时钟记录集合断言失败 |

## 已知问题与结果边界

v72 首轮因 USB 系统镜像传输失败，未启动桌面；同候选重试才产生上述触控/GPU记录。两个轮次分别保留，未把传输失败计作触控或性能结果。

本轮整体首个失败位于 `verify-lmi-gpu-route.py:62`：原日志中按钮诊断插入 `LMI_GPU_SMMU_CLOCK` 标签，使总线时钟记录集合断言失败，独立重跑复现。原日志和旧校验器均未修改。新严格准入通过不覆盖整体 INCOMPLETE；本轮也不能沿用 v71 的旧 HFI 档位断言作为直接失败原因。

静止与交互混合窗口不能推导稳定60 FPS或跨版FPS提升。v59 的 FAST 计数 ABI 缺陷属于历史版本；v72 的 GPU/CPU 计数已通过本轮严格核对，但这同样不代表整机稳定性和图形性能问题已经全部解决。实机摘要见 [v72-touch-gpu.json](evidence/v72-touch-gpu.json)。

## 源码导航

| 内容 | 说明与源码 |
| --- | --- |
| v72 触控轮询修正 | [技术说明](docs/V72.zh-CN.md) · [构建器](tools/build-lmi-touch-cadence-v72.py) · [原始触控实现](tools/lmi-touch.c) |
| 实际ARM64循环检查 | [15场景仿真](tools/check-lmi-touch-cadence-v72.py) · [v72准入](tools/lmi_display_v72_policy.py) |
| GPU复制与延后缓存 | [v71模块](tools/lmi-gpu-deferred-cache-v71.c) · [v70异步复制等待](tools/lmi-gpu-overlap-v70.c) · [复制接口](tools/lmi-gpu-copy-v66.c) |
| 输入与图形证据分析 | [输入节奏](tools/analyze-lmi-input-cadence.py) · [本轮结果](tools/analyze-lmi-display-v72.py) · [冻结测试器](tools/test-lmi-checkpoints-v72.py) |
| HID初始化与历史触控 | [触控专题](docs/TOUCH.zh-CN.md) · [inject.c](userland-source/userland/src/inject.c) |
| GPU初始化与GLES | [GPU专题](docs/GPU.zh-CN.md) |
| UEFI移植 | [方法与源码说明](docs/UEFI.zh-CN.md) · [Mu-Silicium overlay](uefi/mu-silicium-overlay/) |
| 构建与来源 | [构建说明](docs/BUILD.zh-CN.md) · [证据范围](docs/EVIDENCE.zh-CN.md) · [来源与许可](NOTICE.md) |

## 离线验证与复现范围

v72 的独立指令解码、恢复三个指令后完整镜像字节一致，以及实际 ARM64 循环15场景已通过；I/O与yield延时由stub提供，仿真不证明真实硬件时序。前序 v71 的32个集成场景、20个变异拒绝及停止边界检查覆盖 GPU fence、源生命周期和 CPU/DMA 缓存所有权，公开副本复核情况记录在 [validation.json](validation.json)。

在 Linux / WSL 中准备 Python 3 和 Clang 后，可恢复公开的生成源码并执行主机检查：

```sh
python3 tools/restore-lmi-public-build-support.py
python3 tools/check-lmi-gpu-deferred-cache-v71.py
python3 tools/check-lmi-gpu-deferred-stop-v71.py
```

ARM64循环仿真另需 Unicorn、Capstone 和精确的前序内核/审计输入；构建器与准入保留原路径及哈希守卫。当前不能仅凭本仓库一条命令重建完整启动镜像。

## 构建输入、来源与许可

`tools/` 是移植与验证工具，`build-support/v72/` 保存公开生成源码，`userland-source/` 是选定公开源码与本地修改快照，`patches/` 保留固定上游补丁。当前完整文件哈希见 [source-manifest.json](source-manifest.json)，历史轮次保持独立。

没有分发 Apple iOS系统文件、SDK、dyld cache、Qualcomm/触控固件、分区备份或可刷写镜像。完整构建仍需自行取得外部输入。原实验采用有界 RAM 临时启动，本次发布不操作设备。

独立工具与文档按根目录MIT许可提供；第三方及派生内容保留各自许可，见 [NOTICE](NOTICE.md)、[LICENSE](LICENSE) 与 [LICENSES](LICENSES/)。
