# 触控处理原理

## 1. 把 FT3518 的报文接进 XNU

硬件为 FocalTech FT3518，I²C 地址 0x38，屏幕坐标 1080×2400。`tools/lmi-touch.c` 在 lmi 的 TLMM GPIO 上用开漏方式模拟总线：GPIO36 为 SDA、37 为 SCL、38 为 reset、39 为 IRQ，板级使能还涉及 GPIO72。只驱动低电平，高电平通过释放 OE 和上拉获得；保留原 GPIO 配置，结束时恢复所改引脚。电源/reset 条件与精确芯片 ID 0x5452 是读点和投递事件的前置条件，不写触控固件。

报文由 3 字节头和最多 10 个 6 字节触点组成。先校验触点 ID、数量及重复 ID，再更新状态；把 phase 转为 down/move/up，把坐标缩放到 Redwood 输入 ABI 的 0..65535。零触点报告仍可能带最后一次抬起坐标，因此活动期间读取整帧；缺少显式 up 时，用上次坐标补一次 release。只看 count=0 就跳过整个报文，会丢掉短滑动的最后一段位移。

入口：`tools/lmi-touch.c`；解码回归：`tools/check-lmi-touch-reports.py`。

## 2. 把微秒总线延迟与调度休眠分开

原每个 GPIO 边沿通过 XNU delay API 等待 5µs；该 API 在某些 idle latency 条件下可能调度休眠，不能假定每次只是短忙等。当前 `tools/lmi-touch-timing.h` 检查 CNTFRQ_EL0 恰为 19.2MHz，用 `isb; mrs CNTVCT_EL0` 和无符号差值等待至少 96 ticks，也覆盖计数器回绕。边沿短等待保持中断开启；长复位、供电和轮询继续使用可让出 CPU 的延迟。时钟拉伸另有有界重试。

这解释了为什么需要时序修正，但**没有证据证明它是所有触控失灵的唯一根因**。新源码的设备效果必须绑定该次 manifest 和实际测试。主机测试只能验证最低等待、跳变、回绕、错误频率拒绝。

## 3. GPU 与触控必须同时接线

早期 GPU loader 曾漏传 `touchscreen=1 lmi_touch=6`，导致 GPU 场景没有启动输入路径。`tools/build-lmi-loader.py`、`build-lmi-gpu-mode.py` 的 `--touch-input` 与预检负责把组合配置传到同一个镜像，而不是仅在单独触控镜像中打开。

## 4. HID 投递成功还不代表界面收到事件

内核事件经 Redwood 输入队列进入 `userland-source/userland/src/inject.c`，建立与显示器集成的虚拟 digitizer 服务，再生成 hand/finger IOHID 事件交给 BackBoard。抬起时若坐标改变，事件 mask 也补 POSITION 位；否则最后的位移可能仅被解释为接触状态变化。

SMP 启动会改变输入服务与 event server 的时序。当前 `make_service()` 等待服务真正被 server 打开；`LMI_HID_SIMPLE_RETRY` 在创建返回 NULL 时最多尝试 20 次、间隔 250ms，服务未打开则有界移除重建。保留支持的发送 client 和连接。

诊断将原始时间戳沿 post/read/sent/HID monitor 关联，并在 BackBoard 的处理/服务选择和 SpringBoard 的两个 UIKit 入口加入有界 observer。observer 保留原方法调用、返回值与输出参数，并检查方法签名/入口条件；它是观察工具，不能当作已经修复路由的证明。日志被限制数量以减小扰动。

v21/v22：192 个事件都被接受/观测，但实际交互仍完全无响应。v23：实际交互中触控恢复、动画卡顿；原严格 GPU 验证仍是 INCOMPLETE。由此只能确认这一轮交互恢复，不能推导长期触控修复完成，也不能仅凭 UIKit observer 无日志确定唯一丢点位置。

相关测试：`check-lmi-hid-startup.py`、`check-lmi-input-observers.py`、`check-lmi-hid-routing.py`；分析器：`analyze-lmi-touch-log.py`。


## 5. v31/v32：修正 BackBoard 的零用途属性缓存

2026-10-25 的 v30 诊断在同一个 sender 上观察到：底层 IOHIDService 的 `primaryUsagePage=0xd`、`primaryUsage=0x4`，但 BKIOHIDService 的缓存仍为 `0/0`。因此，服务创建、事件被接受以及 HID monitor 收到事件都不足以证明它已被识别为主触屏。这个属性错配解释了该轮触屏路由异常；不据此断言此前所有故障都只有这一个原因。

`inject.c` 新增显式开关 `LMI_HID_USAGE_RECHECK`：在原 `_setUpInitialProperties` 返回后、服务匹配发布前，通过系统原有的序列化 `propertyForKey:` 重新读取实际属性。只在两个缓存值均为零、Product 精确为 `Redwood touch screen`、Manufacturer 精确为 `redwood`，且 CFNumber 类型/取值验证得到 page=13、usage=4 时，经原 setter 更新缓存。任何非零缓存、其他设备、属性缺失、类型错误、转换失败或用途不符都保持原行为；不从事件猜设备类型、不强制覆盖其他服务。

安装前检查 BKIOHIDService 类、原方法 ABI、带 slide 的固定入口、首条指令及五个 accessor 的 ABI。它只适配已核对的 iOS 16.5 构建，不是跨版本通用 hook。原初始化始终先执行一次；日志记录 `installed` 和 `restored page=13 usage=4`。

镜像构建通过 `build-lmi-gpu-gl-image.py --hid-usage-recheck` 启用，并在 manifest 中记录该开关。测试器要求 14 场景主机检查 PASS，且检查报告、候选 inject.c 和镜像 manifest 的源码哈希一致。`check-lmi-hid-usage.py` 覆盖一个恢复场景和 13 个拒绝/保持场景。

同时改进有界路由观察：通过已加载 backboardd 的 Mach-O header 定位独立可执行文件，不混用 shared-cache slide；增加 service/digitizer state 摘录；将路由 observer 安装放到输入服务创建后、物理采样投递前。observer 保持原转发、返回值和输出参数，不代替修复本身。

v31/v32 使用同一候选镜像、八核、两轮各 180 秒的有界 RAM 测试。两轮实际交互均确认触控正常、设置可打开；均出现用途恢复日志，并恢复 Android、核对 boot/dtbo 哈希一致。v31 原整体结果仍为 INCOMPLETE，v32 checkpoint 流程 PASS；触控交互验证与整体测试判定分别保留。当前只确认这两轮的修正有效，不代表长时间稳定或全手势覆盖。动画卡顿和上下撕裂仍待处理。

公开证据见 `evidence/v31-touch-fix.json`、`evidence/v32-touch-fix.json`；两轮 inject.c 的 SHA256 与本次公开源码一致：`12a73c139903391bd3e6576dccbaf7c1fab47197d64bea04e5e3f622e65db882`。
