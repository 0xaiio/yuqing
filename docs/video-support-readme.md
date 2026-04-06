# 视频支持实施 README

本文档记录“把当前跨源 AI 图片管理系统扩展到图片 + 视频统一管理”的实施路线与完成状态。

## 目标

将已有的图片导入、分析、检索链路扩展到视频，覆盖：

- 监听并导入视频文件
- 提取缩略图、时长、分辨率、FPS 等元数据
- 检测并识别视频中的人物
- 提取视频中的场景、OCR 和摘要标签
- 支持文本搜视频、以视频搜视频、按人物头像搜视频
- 提供独立的视频检索评估脚本

## 模型路线

### 人物检测与识别

- 检测：`SCRFD`
- 识别：`AdaFace`

理由：

- 项目已经稳定接入这套图片人物识别链路
- 扩展到视频时可以直接复用 embedding 空间与人物库

### 视频向量与场景理解

- 视频向量：`SigLIP2`
- 视频摘要 / 标签：`Qwen2.5-VL`
- 抽帧策略：当前为均匀抽帧，后续可升级到 `TransNetV2`

## TODO 状态

### Phase 1. 文档与路线

- [x] 产出视频支持专用 README
- [x] 在主 README 中补充视频能力
- [x] 明确分阶段实施与验证目标

### Phase 2. 数据模型与导入链路

- [x] 新增视频模型与序列化结构
- [x] 新增视频后端 API：列表、详情、缩略图、原文件
- [x] 扩展来源监听和导入流程，支持视频文件
- [x] 保存视频元数据：时长、宽高、FPS、采样帧数

### Phase 3. 视频分析引擎

- [x] 实现视频抽帧服务
- [x] 实现逐帧 `SCRFD + AdaFace` 人物识别聚合
- [x] 实现基于 `SigLIP2` 的关键帧向量提取与视频向量聚合
- [x] 实现基于多帧输入的 `Qwen2.5-VL` 视频摘要与场景标签

### Phase 4. 视频检索

- [x] 新增文本搜视频接口
- [x] 新增以视频搜视频接口
- [x] 支持通过人物名检索视频
- [x] 支持通过人物头像在视频中检索
- [x] 支持相似视频检索

### Phase 5. 前端页面

- [x] 新增视频页面：最近视频 / 搜索视频 / 以视频搜视频
- [x] 新增按人物头像搜视频入口
- [x] 新增视频卡片与视频详情抽屉
- [x] 支持播放、查看元数据、查看识别人物与场景标签

### Phase 6. 质量与验证

- [x] 完成数据库兼容与导入链路校验
- [x] 完成编译、构建和接口烟测
- [x] 补充独立的视频检索评估脚本
- [x] 同步 README

## 当前结果

已经完成：

- 视频文件监听与自动导入
- 视频元数据入库
- 视频缩略图生成
- 文本搜视频
- 以视频搜视频
- 按人物头像搜视频
- 相似视频检索
- 视频检索评估脚本

相关代码入口：

- 后端视频处理：[backend/app/video_processing.py](../backend/app/video_processing.py)
- 后端视频检索：[backend/app/video_search_service.py](../backend/app/video_search_service.py)
- 视频 API：[backend/app/main.py](../backend/app/main.py)
- 视频页面：[frontend/src/views/VideosView.vue](../frontend/src/views/VideosView.vue)
- 评估脚本：[scripts/evaluate-video-retrieval.py](../scripts/evaluate-video-retrieval.py)
