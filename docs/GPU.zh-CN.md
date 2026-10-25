# GPU 加速处理原理

目标是让 lmi 的 Adreno 650 使用现有 RedwoodGPU ABI，并通过 Mesa/Freedreno 为 GLES 和 CoreAnimation 提供 GPU 提交路径。不是把 framebuffer 拷贝或 renderer 名称当作 GPU 绘图完成。

## 初始化依赖链

1. `lmi-gpu-resources.c`、`rpmh.c`、`rsc-init.c`、`clock.c`、`route.c`：从 lmi/SM8250 的电源、时钟、RSCC/PDC、RPMh 路由逐层建立可验证前置条件。历史 mode29..46 是阶段性诊断档位，不是可互换的成品驱动。
2. `ram.c`、`hfi*.c`、`boot.c`、`gx.c`：使用受管理 RAM 和 GMU/HFI 队列启动控制路径，等待、响应序号、错误与超时都有检查。
3. `table-plan.c`、`core-memory.c`、`context.c`、`cp*.c`：建立地址空间和 CP ring/fence。CPU 虚拟地址、物理地址、GPU IOVA 必须区分，检查连续性、对齐、范围、缓存属性及 SMMU fault。
4. `scm.c`、`zap-metadata.c`、`zap-load.c`：通过设备原签名 ZAP 固件进行认证。早期把分配的 CPU VA 也要求 1MB 对齐会误拒绝合法分配；修正为 VA 满足 XNU 页对齐，同时仍要求 PA 的 1MB 对齐、连续性、边界和原始 CRC。没有绕过固件认证，也不分发固件。
5. `unsecure.c`：在认证和 idle/fault 前置满足后切 normal mode，保留超时与回读 guard。不能把命令被 CP 读完当作 GPU 已绘图。

## 从像素回读到桌面后端

`lmi-gpu-tile.c` 提交 16×16 图块并核对全部 256 像素、两侧 guard、周围 scratch 和新旧 fence。只有这层通过才允许 `lmi-gpu-desktop.c` 接管原 RedwoodGPU user client。

桌面后端复用 CB1 / ASID2 地址空间和既有 ABI，修正 type7 packet parity，配置 A650 UBWC/UCHE/cache bypass 等板级参数。map/unmap 后执行正确 cache sync 与 TLB 失效，提交 indirect buffer、等待 fence、处理 ring 回绕。测试独立解码命令，避免仅以生产 helper 自证。

DMA 是否结束或地址空间失效不确定时，后端不释放仍可能被 GPU 使用的 backing；故障资源保持到 RAM 测试的有界重启。它不具备完整生产驱动的热恢复能力。

## Mesa / GLES / CoreAnimation

`userland-source/tools/mk-mesa.sh` 和 `tools/mesa/` 中的公开补丁构建 Mesa 25.0.7 softpipe + freedreno；Redwood DRM 桥把 Freedreno 的分配/提交/等待转到 RedwoodGPU。`userland/src/gl_osmesa.c` 和 `eagl.c` 提供 GLES/EAGL 适配。原注入层只在 RedwoodGPU 存在时加载 GL shim。

`tools/lmi-gpu-gl-probe.c` 用 shader 绘制红绿交替三角形与蓝背景，共 8 帧。每帧从 GPU 渲染结果读取 64×64 RGBA，排除边界规则 tie 的 64 像素，剩余 4032 像素必须精确匹配，检查 GL error 和 CPU readback 两侧 guard。CPU 只校验结果，不构造绘图像素。`verify-lmi-gpu-gl.py` 严格要求 FD650、frame0..7 顺序与最终 PASS，拒绝软件 renderer、缺帧、重复、错误及矛盾日志。

## 两类卡顿改进

- `build-lmi-gpu-gl-image.py --quiet-oslog` 移除部分系统服务的调试日志开关，减少日志开销。实际交互反馈显示明显改善，但无法单独归因所有性能变化。
- `lmi-gpu-desktop.c` 的 idle 等待前 20 次各忙等约 100µs（总计约 2ms），避免每次短提交都让出单 CPU 一个调度时间片；之后保留原长等待/fault 路径。检查计数器频率，测试短完成、长等待回退、回绕和错误频率。保持中断开启。

CoreAnimation 建立 FD650 上下文并连续提交与八帧探针通过，是不同层次的证据。v31/v32 设置已可打开，但壁纸失败、动画卡顿和上下撕裂仍存在；五秒显示窗口包含空闲，不能当作连续动画 FPS，也不能把 glFlush 同步时间当作纯 GPU 执行时间。严格报告仍保留 `desktop_acceleration_verified=false`。
