# 架构设计

## 1. 产品边界

本项目首版做成一个 `Windows 桌面本地 AI 图片中台`：

- 输入源：本地图库、微信 PC 图片目录、QQ 图片目录、后续再加拍照上传
- 核心能力：导入、去重、标签化、检索、归档
- 部署方式：本地单机运行
- 数据落点：本地磁盘 + SQLite

不建议在首版里做的内容：

- 微信/QQ 协议逆向登录
- 云端多租户
- 自研视觉大模型
- 高并发分布式搜索

## 2. 最终推荐技术栈

### 桌面端

- 正式方案：`Tauri + Vue3 + Element Plus`
- 原因：
  - 界面适合图库检索类产品
  - Web UI 迭代快
  - 未来扩成 Web 管理页成本低
  - Tauri 比 Electron 更轻量

### 后端

- `FastAPI`
- `SQLModel`
- `SQLite`
- `watchdog`
- `Pillow + imagehash`

### AI 模块

- OCR：`PaddleOCR / RapidOCR` 或云 OCR
- 图像标签与描述：`Qwen2.5-VL`、通义千问 VL、腾讯云图像标签
- 人脸检测与聚类：`InsightFace` 或云人脸服务
- 向量检索：`CLIP / SigLIP embedding + FAISS 或 LanceDB`

## 3. 系统分层

### 3.1 Source Connector

负责发现图片，不负责 AI。

支持的 `kind`：

- `local_folder`
- `wechat_folder`
- `qq_folder`

首版规则：

- 全部通过用户明确配置的目录接入
- 不直接破解微信/QQ 私有协议
- 所有导入路径在 UI 中可见、可关闭、可重新扫描

### 3.2 Import Pipeline

统一导入管线：

1. 扫描目录拿到候选图片
2. 过滤非图片文件
3. 计算 `SHA256`
4. 计算 `pHash`
5. 判断重复
6. 拷贝到统一存储目录
7. 调用 AI 分析器
8. 写入 SQLite
9. 建立搜索索引

### 3.3 AI Analyzer

接口设计成可插拔，避免被某一个厂商锁死。

统一输出：

- `caption`
- `ocr_text`
- `people`
- `scene_tags`
- `object_tags`

首版仓库中的分析器是占位实现，只做轻量标签推断，目的是先把工程链路打通。

### 3.4 Search Service

搜索分三层：

1. 结构化过滤：人物、场景、物体、来源
2. 文本搜索：标题、OCR、标签
3. 语义搜索：自然语言转 embedding 后做相似召回

当前骨架先实现第 1 层和第 2 层，并为第 3 层保留接口。

## 4. 数据模型

### Source

- `id`
- `name`
- `kind`
- `root_path`
- `enabled`

### Photo

- `id`
- `source_id`
- `source_kind`
- `source_name`
- `original_path`
- `storage_path`
- `sha256`
- `phash`
- `caption`
- `ocr_text`
- `people`
- `scene_tags`
- `object_tags`
- `taken_at`

### ImportJob

- `id`
- `source_id`
- `source_name`
- `status`
- `scanned_count`
- `imported_count`
- `duplicate_count`
- `error_message`

## 5. 检索设计

自然语言检索建议不要直接把一句话丢给数据库，而是拆成两步：

1. `query understanding`
   - 提取人物词
   - 提取场景词
   - 提取时间词
   - 提取颜色/动作/文本关键词
2. `hybrid retrieval`
   - 结构化条件过滤
   - 文本匹配召回
   - 向量相似度排序

示例：

- 查询：`去年夏天和小明在海边拍的日落`
- 解析结果：
  - 人物：`小明`
  - 场景：`海边`
  - 时间：`去年夏天`
  - 关键词：`日落`

## 6. 微信/QQ 接入建议

### 可落地方案

- 让用户在桌面端主动配置微信/QQ 图片目录
- 或提供“从微信目录导入”“从 QQ 目录导入”向导
- 后端只处理本地已存在的图片文件

### 不建议首版做的方案

- 模拟登录抓聊天记录
- Hook 客户端进程
- 抓未授权目录内容

原因：

- 合规风险高
- 容易失效
- 评审时不好解释
- 维护成本远高于目录导入模式

## 7. 难度分级

### 第一阶段：可运行 MVP

- 本地文件夹导入
- 微信/QQ 目录导入
- 图片去重
- 基础标签
- 关键词搜索

### 第二阶段：高分答辩版

- OCR 接入
- 人脸聚类
- 场景/物体识别
- 自动相册
- 目录实时监听

### 第三阶段：亮点版

- 自然语言检索
- 以图搜图
- 向量重排
- 云端同步与备份

## 8. 你现在最该做什么

如果你准备立刻开工，优先级建议是：

1. 先把桌面端页面框架搭出来
2. 用本仓库后端先打通“创建图片源 -> 导入 -> 搜索”
3. 再替换占位 AI 为真实 OCR/视觉模型
4. 最后做微信/QQ 路径自动发现和目录监听
