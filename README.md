# 跨源 AI 图片 / 视频智能管理系统

面向 Windows 桌面场景的本地优先媒体管理系统。项目统一接入微信目录、QQ 目录、本地图库、拍照导入与视频文件，完成多源归档、OCR、人物识别、场景标签、自然语言检索、以图搜图、以视频搜视频，以及基于人物头像的图片 / 视频检索。

## 当前状态

当前已经完成：

- 多源目录接入：`local_folder`、`wechat_folder`、`qq_folder`
- 手动导入 + 实时目录监听
- 图片与视频的统一入库、去重、标签化
- `SCRFD + AdaFace` 人脸检测 / 识别链路
- 人物库、参考图上传、删除人物、删除人物部分参考图
- 批量人物标注校正
- 阈值可视化调参
- 图片检索：自然语言、标签组合、以图搜图、按人物头像搜图片
- 视频检索：文本搜视频、以视频搜视频、相似视频、按人物头像搜视频
- 删除能力：删除图片、删除视频，并自动清理视频缩略图 / 抽帧缓存 / 失效人脸簇引用
- 通过界面删除图片 / 视频时，默认会同步删除本地同步源中的原文件；若原文件已不在已配置源目录中，则仅删除应用归档副本
- 搜索页、视频页、人物页、人脸簇页支持批量多选删除图片 / 视频
- 人物页与人脸簇页同时展示相关图片和相关视频
- 检索评估脚本：图片检索评估、视频检索评估

## 技术栈

- 桌面端：`Tauri + Vue 3 + Element Plus`
- 后端：`FastAPI + SQLModel + SQLite`
- OCR：`RapidOCR`
- 人脸检测：`SCRFD`
- 人脸识别：`AdaFace`
- 图片向量：本地轻量向量服务
- 视频向量：`SigLIP2`
- 视频摘要 / 场景理解：`Qwen2.5-VL`
- 目录监听：`watchdog`

## 核心能力

### 1. 多源接入

- 配置并管理图片 / 视频来源目录
- Windows 桌面壳内支持原生目录选择器
- 支持实时监听新增文件并自动入库

### 2. 图片能力

- OCR 文字提取
- 人物、场景、物体标签生成
- 参考人物图建库
- 按人名、人物头像、自然语言描述搜索图片
- 相似图检索
- 在搜索页、人物页、人脸簇页里批量多选删除不喜欢、模糊或误匹配的图片

### 3. 视频能力

- 自动抽帧、缩略图生成、时长 / 分辨率 / FPS 采集
- 聚合视频中的人物、场景、物体标签
- 支持文本搜视频
- 支持按视频样例搜视频
- 支持按人物头像搜视频
- 支持相似视频检索
- 在视频页、人物页、人脸簇页里批量多选删除误匹配或低价值视频

### 4. 人脸工程能力

- 人脸簇独立管理页
- 人物库管理页
- 批量人物标注校正页
- 人脸识别阈值可视化调参页
- 人脸簇相关图片 / 视频统一查看与清理

## 关键模型路线

### 人脸识别

- 检测：`SCRFD`
- 识别：`AdaFace`

说明：

- 图片与视频共用同一套人脸 embedding 语义空间
- “按人物头像搜图片 / 搜视频”复用同一套人物识别评分逻辑

### 视频理解

- 视频向量：`SigLIP2`
- 多帧摘要与标签：`Qwen2.5-VL`
- 抽帧策略：当前为均匀抽帧，后续可升级到 `TransNetV2`

## 目录结构

```text
docs/
  architecture.md
  scrfd-adaface-readme.md
  video-support-readme.md
  windows-build-tools.md
backend/
  app/
frontend/
  src/
  src-tauri/
scripts/
  evaluate-face-retrieval.py
  evaluate-video-retrieval.py
  start-local.ps1
start-local.bat
```

## 一键启动

### PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

### 双击启动

```bat
start-local.bat
```

### 启动 Tauri 桌面壳

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -WithTauri
```

## 手动启动

### 1. 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装后端依赖

```powershell
pip install -r backend\requirements.txt
```

### 3. 复制环境变量

```powershell
Copy-Item backend\.env.example backend\.env
```

### 4. 启动后端

```powershell
uvicorn app.main:app --app-dir backend --reload
```

### 5. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

## 主要 API

### 通用

- `GET /api/v1/health`
- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `POST /api/v1/sources/{source_id}/import`
- `POST /api/v1/sources/{source_id}/watch/start`
- `POST /api/v1/sources/{source_id}/watch/stop`

### 图片

- `GET /api/v1/photos`
- `GET /api/v1/photos/{photo_id}`
- `DELETE /api/v1/photos/{photo_id}`
- `GET /api/v1/photos/{photo_id}/asset`
- `GET /api/v1/photos/{photo_id}/similar`
- `POST /api/v1/photos/{photo_id}/reanalyze`
- `POST /api/v1/search`
- `POST /api/v1/search/by-image`
- `POST /api/v1/search/by-person-image`

### 视频

- `GET /api/v1/videos`
- `GET /api/v1/videos/{video_id}`
- `DELETE /api/v1/videos/{video_id}`
- `GET /api/v1/videos/{video_id}/asset`
- `GET /api/v1/videos/{video_id}/thumbnail`
- `GET /api/v1/videos/{video_id}/similar`
- `POST /api/v1/search/videos`
- `POST /api/v1/search/videos/by-video`
- `POST /api/v1/search/videos/by-person-image`

### 人物 / 人脸

- `GET /api/v1/people`
- `POST /api/v1/people`
- `POST /api/v1/people/{person_id}/rename`
- `DELETE /api/v1/people/{person_id}`
- `GET /api/v1/people/{person_id}/samples`
- `POST /api/v1/people/{person_id}/samples`
- `DELETE /api/v1/people/{person_id}/samples/{sample_id}`
- `GET /api/v1/people/{person_id}/photos`
- `GET /api/v1/people/{person_id}/videos`
- `GET /api/v1/people/{person_id}/correction-candidates`
- `POST /api/v1/people/{person_id}/cluster-corrections`
- `GET /api/v1/face-clusters`
- `POST /api/v1/face-clusters/{cluster_label}/rename`
- `GET /api/v1/face-clusters/{cluster_label}/photos`
- `GET /api/v1/face-clusters/{cluster_label}/videos`
- `GET /api/v1/face-tuning`
- `POST /api/v1/face-tuning/preview`
- `POST /api/v1/face-tuning/settings`

## 评估脚本

### 图片人物检索评估

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate-face-retrieval.py --top-k 1 5 10
```

输出：

- `MRR`
- `Hit@1 / Hit@5 / Hit@10`

### 视频人物检索评估

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate-video-retrieval.py --top-k 1 5 10
```

输出：

- `MRR`
- `Hit@1 / Hit@5 / Hit@10`

## 环境变量

复制 `backend/.env.example` 到 `backend/.env` 后，可按需配置：

```env
AI_ENABLE_OCR=true
AI_OCR_ENGINE=rapidocr
AI_ENABLE_VISION=false
AI_VISION_BASE_URL=https://api.openai.com/v1
AI_VISION_API_KEY=
AI_VISION_MODEL=
SEARCH_UPLOAD_ROOT=D:/code-repos/yuqing/data/search-uploads
PERSON_LIBRARY_ROOT=D:/code-repos/yuqing/data/person-library
FACE_MODEL_ROOT=D:/code-repos/yuqing/data/face-models
FACE_RUNTIME_CONFIG_PATH=D:/code-repos/yuqing/data/face-runtime-config.json
VIDEO_FRAME_ROOT=D:/code-repos/yuqing/data/video-frames
FACE_DETECTION_PACK_NAME=buffalo_sc
FACE_DETECTION_MODEL_FILENAME=det_500m.onnx
FACE_CLUSTER_SIMILARITY_THRESHOLD=0.5
PERSON_RECOGNITION_SIMILARITY_THRESHOLD=0.52
VIDEO_FRAME_SAMPLE_INTERVAL_SECONDS=3
VIDEO_MAX_SAMPLED_FRAMES=8
VIDEO_EMBEDDING_MODEL_ID=google/siglip2-base-patch16-224
VIDEO_EMBEDDING_DEVICE=cpu
```

## 当前验证

当前已验证：

- `python -m compileall backend/app`
- `npm run build`
- `FastAPI TestClient` 基础烟测
- 临时构造图片 / 视频 / 人脸簇 / 人物后验证：
  - `GET /api/v1/people/{person_id}/videos`
  - `GET /api/v1/face-clusters/{cluster_label}/videos`
  - `DELETE /api/v1/photos/{photo_id}`
  - `DELETE /api/v1/videos/{video_id}`
  - 删除后会同步清理文件、缩略图目录和失效的人脸簇引用

## 许可证与使用边界

- `SCRFD` 模型通常来自 InsightFace 发行包，使用前请核对模型许可
- `AdaFace`、`SigLIP2`、`Qwen2.5-VL` 在实际商用前也建议逐项确认许可条件
- 当前仓库更适合作为课程项目、研究原型、自用工具或内部原型系统
