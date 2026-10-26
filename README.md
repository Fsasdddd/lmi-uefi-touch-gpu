# Redmi K30 Pro / lmi：UEFI、触控与 Adreno 650 GPU bring-up

面向 **Xiaomi Redmi K30 Pro（lmi / SM8250）运行 HackiOS / XNU / iOS 16.5** 的源码与处理原理。这里公开 FT3518 触控接入、HID 事件链路修正、Adreno 650 初始化与桌面后端、Mesa/Freedreno GLES 探针及验证工具。

**这是进行中的移植研究；触控属性缓存修正在 v31/v32 连续两轮有效，整机图形流畅度与长期稳定性仍未完成。** 最新发布加入 2026-10-27 已结束测试的 v59b 显示/GPU 源码；证据结论以已结束的指定测试轮次为准，后续正在进行的实验不纳入成功结论。

| 能力 | 已观察到的结果 | 仍未完成 |
| --- | --- | --- |
| FT3518 | 芯片识别、报文解码、down/move/up、多指和最终抬起坐标处理 | 长期稳定性、所有滑动/边缘场景 |
| HID 触控链路 | v31/v32 同镜像连续两轮触控正常、设置可打开 | 长时间稳定性及全手势仍需验证；v21/v22 为历史失败 |
| GPU 初始化 | 原签名固件认证、normal mode、16×16 GPU 像素回读 | 所有运行时故障和恢复场景 |
| GLES | FD650，8 帧 shader 绘制，每帧 4032 像素匹配，CPU guard 通过 | GLES 探针不等于整机稳定、所有图形 API 可用 |
| CoreAnimation | FD650 上下文和连续提交已观察到 | v59 体验改善但滑动仍掉帧；FAST 统计 ABI 有缺陷，整体 INCOMPLETE |

- [v59 原理、源码入口、验证和已知缺陷](docs/V59.zh-CN.md)
- [UEFI 移植方法与源码](docs/UEFI.zh-CN.md)
- [触控处理原理与源码入口](docs/TOUCH.zh-CN.md)
- [GPU 加速处理原理与源码入口](docs/GPU.zh-CN.md)
- [构建、集成和离线验证](docs/BUILD.zh-CN.md)
- [实机证据及结论边界](docs/EVIDENCE.zh-CN.md)
- [上游、许可与来源](NOTICE.md)

`tools/` 是本项目的移植与验证工具；`userland-source/` 是公开上游的选定源码及本地修改快照，**不是完整上游仓库**。`patches/` 提供相对固定上游提交的修改补丁。`source-manifest.json` 固定本次文件哈希，`evidence/` 只含经过筛选的证据摘录和摘要。

没有分发 Apple iOS 系统文件、SDK、dyld cache、Qualcomm/触控固件、设备分区备份或可刷写镜像。需要的外部构建输入由使用者自行取得。原实验采用有界 RAM 临时启动；发布源码不会执行任何设备操作。
