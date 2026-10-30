# Redmi K30 Pro / lmi：UEFI、触控与 Adreno 650 GPU 移植

**当前公开版本：v80 · 实机验证：2026-10-28**

面向 Xiaomi Redmi K30 Pro（lmi / SM8250）运行 HackiOS / XNU / iOS 16.5 的源码与处理原理。公开 UEFI 平台移植、FT3518 / HID 触控、Adreno 650 / Mesa Freedreno，以及截至 v80 的完整帧 GPU 复制、缓存所有权、CPU 请求与异步 DPU 显示工具。

## v80 更新

- **异步 DPU 提交**：独立内核线程负责 DPU 完成轮询和提交。呈现线程生成完整自有目标后发布，保留原源表面释放与生产者退休顺序。
- **有界缓冲和真实完成检查**：双目标状态、ticket、单待提交槽与锁共同阻止覆盖正在扫描的目标；线程不持有源表面。
- **继承触控与 GPU 改动**：保留 v72 触控等待修正、GPU 完整帧复制、映射复用和延后 CPU 缓存同步；补充 v73–v79 的显示计时、SMP 与 CPU 请求相关源码。
- **源码与验证公开**：3967 项冻结输入已复核。公开主机并发测试、ARM64 仿真、变异检查和实机摘要。

[阅读 v80 原理、验证与限制](docs/V80.zh-CN.md) · [v72 历史说明](docs/V72.zh-CN.md) · [v59 历史说明](docs/V59.zh-CN.md)

## 实机结果与边界

| 项目 | v80 已观察结果 |
| --- | --- |
| 异步 DPU | 工作线程启动；入队780、提交780、计数完成779、失败0 |
| GPU 完整帧复制 | 776/776 完成，复制 pending=0，held=0；合格帧 CPU copy_calls=0，另4帧普通路径 |
| GPU 队列与源退休 | GPU 4901/4901；源781/781退休 |
| 延后缓存同步 | CPU目标同步3次，少做773次整帧缓存遍历 |
| CPU EPSS | 三个域请求索引及恢复读回通过；请求值不是实测CPU频率 |
| 触控 | 继承v72改动；v72同触点上报间隔中位约10.2ms，v80未重新测量触控到光子延迟 |
| 恢复 | 返回Android，原boot/dtbo哈希一致，无panic记录 |
| 整体验证 | **INCOMPLETE**：新严格准入通过，冻结旧HFI DCVS请求断言仍失败 |
| 动画性能与Wi-Fi | 尚无屏幕实测动画FPS或受控跨版提升倍数；Wi-Fi未集成 |

DPU异步计数中的 `pending=18446744073709551615` 是有符号 `-1`（无待提交槽）的无符号日志表示，与GPU复制的pending计数不同。提交780次不能写成完成780次；最终扫描完成与物理显示重叠没有独立测量。

## 源码导航

| 内容 | 入口 |
| --- | --- |
| v80异步呈现 | [实现](tools/lmi-display-async-v80.c) · [接口](tools/lmi-display-async-v80.h) · [构建器](tools/build-lmi-display-async-v80.py) |
| 并发与原生代码检查 | [主机测试](tools/check-lmi-display-async-v80.c) · [ARM64检查](tools/check-lmi-display-async-v80-native.py) · [独立审查](tools/review-lmi-display-async-v80-v2.py) |
| 实机准入与分析 | [准入](tools/lmi_display_v80_policy.py) · [分析器](tools/analyze-lmi-display-v80.py) · [实机摘要](evidence/v80-touch-gpu.json) |
| 触控与GPU | [触控](docs/TOUCH.zh-CN.md) · [GPU](docs/GPU.zh-CN.md) · [v72](docs/V72.zh-CN.md) |
| UEFI移植 | [移植方法](docs/UEFI.zh-CN.md) · [平台overlay](uefi/mu-silicium-overlay/) |
| 构建与许可 | [构建说明](docs/BUILD.zh-CN.md) · [来源与许可](NOTICE.md) |

## 离线复现

Linux / WSL 中准备 Python 3 和 Clang：

```sh
python3 tools/restore-lmi-public-build-support.py
mkdir -p out/public-v80
clang -O1 -g -Wall -Wextra -Werror -pthread -fsanitize=address,undefined tools/lmi-display-async-v80.c tools/lmi-display-pipeline-v51.c tools/lmi-display-timing-v73.c tools/check-lmi-display-async-v80.c -o out/public-v80/check
./out/public-v80/check
```

主机检查覆盖12个场景和512帧流；OS、GPU和DPU服务由模型提供，不证明实际硬件时序、关机或FPS。原生ARM64检查还需要精确链接产物、前序内核与Unicorn，不能仅凭本仓库一条命令重建完整启动镜像。

`build-support/v72/` 与 `build-support/v80/` 保存选定生成源码；[source-manifest.json](source-manifest.json) 记录公开文件哈希，[validation.json](validation.json) 记录验证范围。历史证据按版本保留。

不分发 Apple iOS系统文件、SDK、dyld cache、Qualcomm/触控固件、分区备份或可刷写镜像。完整构建需自行取得外部输入。本次发布不操作设备。

独立工具与文档按根目录MIT许可提供；第三方及派生内容保留各自许可，见 [NOTICE](NOTICE.md)、[LICENSE](LICENSE) 与 [LICENSES](LICENSES/)。
