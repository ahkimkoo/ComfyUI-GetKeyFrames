# ComfyUI-GetKeyFrames

[![PyPI version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/ahkimkoo/ComfyUI-GetKeyFrames)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Comfy Registry](https://img.shields.io/badge/Comfy_Registry-available-orange)](https://registry.comfy.org)

ComfyUI 自定义节点，从视频帧序列中智能提取关键帧，并提供网格拼合与拆分工具。

基于 [LonicaMewinsky/ComfyUI-MakeFrame](https://github.com/LonicaMewinsky/ComfyUI-MakeFrame) 改进而来，v2 完全重写了关键帧提取算法。

---

## 安装

### 通过 ComfyUI Manager（推荐）

在 ComfyUI Manager 中搜索 **GetKeyFrames** 并安装。

### 手动安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ahkimkoo/ComfyUI-GetKeyFrames.git
```

依赖会在首次加载时自动安装。若自动安装失败，请手动执行：

```bash
pip install opencv-python scikit-image ImageHash
```

---

## 节点一览

| 节点 | 功能 |
|------|------|
| **GetKeyFrames** | 从帧序列中智能提取关键帧（场景检测 + 帧选取） |
| **MakeGrid** | 将多张图像拼合为网格大图（适配并行帧生成工作流） |
| **BreakGrid** | 将网格图拆分回单张图像 |

---

## GetKeyFrames

智能提取关键帧节点。采用多阶段管线：**场景检测 → 优先级过滤 → 动态配额分配 → 帧内选取**。

### 处理流程

```
输入帧序列
  │
  ▼
① 逐帧差异计算（可选用 MSE / SSIM / pHash）
  │
  ▼
② 归一化差异值，按阈值切分场景
  │
  ▼
③ 若场景数 > 目标关键帧数 → 按差异幅度保留最显著的 N-1 个场景切点
  │
  ▼
④ 按场景长度动态分配关键帧配额
  │
  ▼
⑤ 在每个场景内按选定策略提取帧
  │
  ▼
输出：关键帧图像批次 + 帧索引字符串
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `frames` | IMAGE | — | 输入帧序列（ComfyUI 标准 IMAGE 类型） |
| `scene_cut_method` | 选择 | MSE | 场景切分算法，见下表 |
| `scene_select_method` | 选择 | Uniform | 场景内帧选取策略，见下表 |
| `num_keyframes` | INT | 12 | 目标提取的关键帧总数（1 ~ 4096） |
| `threshold` | FLOAT | 0.1 | 场景切分阈值（0.0 ~ 10000.0），作用于归一化后的差异值 |
| `central_focus_ratio` | FLOAT | 0.3 | 中心区域比例，仅 `Edge_Change_Rate` 策略使用（0.1 ~ 1.0） |

#### scene_cut_method（场景切分算法）

| 方法 | 原理 | 特点 |
|------|------|------|
| **MSE** | 均方误差 | 速度快，适合检测硬切 |
| **SSIM** | 结构相似度 | 较慢，但更贴近人眼感知 |
| **pHash** | 感知哈希 | 对微小编辑鲁棒，适合检测内容变化 |

> 所有方法的差异值在比较前会归一化到 `[0.0, 1.0]`，因此 `threshold` 参数在不同方法间具有一致的含义。`0.1` 意味着只保留差异强度排名前 10% 的帧间变化。推荐起始值：`0.1` ~ `0.2`。

#### scene_select_method（场景内帧选取策略）

| 方法 | 原理 | 适用场景 |
|------|------|----------|
| **Uniform** | 在场景内均匀采样 | 通用，保证时间覆盖 |
| **Peak_Difference** | 选取与场景首帧差异最大的帧 | 捕捉动作高潮 |
| **Edge_Change_Rate** | 对画面中心区域计算边缘变化率 | 检测结构性的剧烈变化 |
| **Highest_Contrast** | 选取 RMS 对比度最高的帧 | 选取视觉冲击力最强的帧 |

> 除 `Uniform` 外，其余策略均使用**带抑制的峰值检测算法**（non-maximum suppression），确保选取的帧在时间上分散、代表不同的变化时刻。

### 输出

| 端口 | 类型 | 说明 |
|------|------|------|
| `Keyframes` | IMAGE | 提取的关键帧图像批次 |
| `keyframe_indices` | STRING | 关键帧在原序列中的索引，逗号分隔（如 `"0, 5, 12, 23, 30"`） |

### 使用提示

- **低阈值（0.05 ~ 0.1）**：检测更多场景变化，适合快节奏视频。节点会自动按差异幅度保留最重要的场景。
- **高阈值（0.3 ~ 0.5）**：只保留显著变化，适合慢节奏或场景切换明显的视频。
- **`num_keyframes` 大于帧间差异点数量时**：所有场景都会被保留，关键帧会均匀分配到各场景中。
- **输出的 `keyframe_indices` 字符串**可用于后续节点（如 VHS-VideoCombine 的帧选择）精确定位关键帧。

---

## MakeGrid

将多张图像拼合为一张网格大图，适配并行帧生成工作流。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `frames` | IMAGE | — | 输入图像批次 |
| `max_width` | INT | 2048 | 输出网格最大宽度（64 ~ 8000，步长 8） |
| `max_height` | INT | 2048 | 输出网格最大高度（64 ~ 8000，步长 8） |

### 行为说明

1. 自动计算最佳行列数，使网格宽高比尽量接近 1:1
2. 所有图像统一缩放到相同尺寸（宽高对齐到 8 的倍数，避免扩散模型生成时的尺寸抖动）
3. 空位使用最后一帧填充（黑色空位会干扰生成质量）
4. 最终网格尺寸会被约束在 `max_width` × `max_height` 以内

### 输出

| 端口 | 类型 | 说明 |
|------|------|------|
| `Grid` | IMAGE | 拼合后的网格图像 |
| `Rows` | INT | 网格行数 |
| `Columns` | INT | 网格列数 |

> 💡 建议将 `Rows` 和 `Columns` 输出传给 `BreakGrid` 节点，确保准确拆分。

---

## BreakGrid

将网格图拆分回单张图像。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `grid` | IMAGE | 输入的网格图像 |
| `rows` | INT | 网格行数（通常来自 MakeGrid 的输出） |
| `columns` | INT | 网格列数（通常来自 MakeGrid 的输出） |

### 输出

| 端口 | 类型 | 说明 |
|------|------|------|
| `Frames` | IMAGE | 拆分后的单帧图像批次 |

---

## 依赖

| 包 | 用途 |
|----|------|
| `torch` | 张量计算（ComfyUI 已包含） |
| `numpy` | 数值运算（ComfyUI 已包含） |
| `Pillow` | 图像处理（ComfyUI 已包含） |
| `opencv-python` | 边缘检测（Edge_Change_Rate 策略） |
| `scikit-image` | SSIM 结构相似度计算 |
| `ImageHash` | pHash 感知哈希计算 |

---

## 致谢

本项目基于 [LonicaMewinsky/ComfyUI-MakeFrame](https://github.com/LonicaMewinsky/ComfyUI-MakeFrame) 改进而来。

## 许可证

[MIT License](LICENSE)
