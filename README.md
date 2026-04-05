# 跨源 AI 图片 / 视频智能管理系统

这是一个面向 Windows 桌面场景的 AI 媒体管理项目，目标是把微信目录、QQ 目录、本地图库、拍照图片以及视频统一纳入一个可检索、可归档、可自动分析的系统。

## 当前状态

当前已经完成：

- 多源目录接入
- 手动导入 + 实时目录监听
- SHA256 + pHash 去重
- 本地 OCR + 可配置视觉模型分析
- 人物库、人物参考图上传、删除人物、删除单张参考图
- 自然语言检索、标签检索、以图搜图、按人物图检索
- 人脸簇独立管理
- 批量人物标注校正
- 阈值可视化调参
- 人脸检索评估脚本

当前已完成的视频基础能力：

- 来源监听和导入流程已支持视频文件
- 已新增视频数据模型与序列化结构
- 已新增视频列表 / 详情 / 原文件 / 缩略图后端 API
- 视频导入时会执行抽帧、人物聚合和向量生成基础链路
- 视频元数据会入库：时长、分辨率、fps、采样帧数
- 已支持文本搜视频、按视频样例搜视频、相似视频
- 已新增视频页面、视频卡片和视频详情抽屉

视频扩展专项路线见：

- [docs/video-support-readme.md](./docs/video-support-readme.md)

## 当前人脸方案

系统当前采用：

- `SCRFD`：人脸检测
- `AdaFace`：人脸 embedding

默认本地部署配置：

- 检测模型：`buffalo_sc / det_500m.onnx`
- 识别模型：`minchul/cvlface_adaface_ir50_webface4m`

专项实施说明见：

- [docs/scrfd-adaface-readme.md](./docs/scrfd-adaface-readme.md)

## 视频模型路线

视频扩展当前按下面这条深度学习路线推进：

- 人物检测与识别：`SCRFD + AdaFace`
- 视频检索向量：`SigLIP2`
- 多帧场景理解：`Qwen2.5-VL`
- 抽帧策略：第一阶段均匀抽帧，第二阶段升级到 `TransNetV2`

说明：

- 当前已经落地的是视频导入、抽帧、人物聚合、视频向量生成、文本搜视频和按视频搜视频
- 尚未完成的是“按人物头像搜视频”和独立的视频检索评估脚本

## 技术栈

- 桌面端：`Tauri + Vue3 + Element Plus`
- 后端：`FastAPI + SQLModel + SQLite`
- 图片 / 视频存储：本地文件系统
- OCR：`RapidOCR`
- 视觉分析：`OpenAI-compatible` 多模态接口
- 人脸检测：`SCRFD`
- 人脸识别：`AdaFace`
- 视频向量：`SigLIP2`
- 实时监听：`watchdog`

## 已有能力

### 1. 多源接入

- 支持 `local_folder`、`wechat_folder`、`qq_folder`
- 支持桌面端直接配置来源目录
- 在 Tauri 桌面壳中支持原生目录选择器
- 来源监听现在同时支持图片和视频文件

### 2. 图片分析与检索

- 本地 OCR：提取图片中的文字
- 远程视觉模型：生成中文摘要、场景标签、物体标签
- 图片重分析
- 人物名检索、人物头像检索、自然语言检索、相似图检索

### 3. 视频基础能力

- 视频导入时自动抽帧
- 聚合视频中的已知人物识别结果
- 为视频生成缩略图
- 保存视频摘要、OCR 聚合文本、人物、场景、物体标签
- 生成视频向量，供后续视频检索使用
- 支持视频列表、视频详情、原文件播放与缩略图访问

### 4. 视频检索

- 支持文本搜视频
- 支持按视频样例搜视频
- 支持相似视频检索
- 支持在视频搜索中直接写人物名
- 已新增 `/videos` 视频浏览与搜索页面

### 5. 批量人物标注校正

- 新增“批量人物标注校正”页面
- 以人脸簇为粒度批量绑定到当前人物
- 支持从当前人物批量解绑错误绑定的人脸簇

### 6. 阈值可视化调参

- 新增“阈值可视化调参”页面
- 可调整人脸检测置信度、NMS、聚类阈值和人物识别阈值
- 支持保存阈值与保存后重建索引

### 7. 评估脚本

新增脚本：

- `scripts/evaluate-face-retrieval.py`

用于评估当前人物检索效果，输出：

- `MRR`
- `Hit@1 / Hit@5 / Hit@10`

## 当前视频 API

已可用：

- `GET /api/v1/videos`
- `GET /api/v1/videos/{video_id}`
- `GET /api/v1/videos/{video_id}/asset`
- `GET /api/v1/videos/{video_id}/thumbnail`
- `GET /api/v1/videos/{video_id}/similar`
- `POST /api/v1/search/videos`
- `POST /api/v1/search/videos/by-video`

## 项目结构

```text
docs/
  architecture.md
  scrfd-adaface-readme.md
  video-support-readme.md
  windows-build-tools.md
backend/
  app/
    adaface_model.py
    ai.py
    config.py
    connectors.py
    database.py
    embeddings.py
    face_alignment.py
    face_clustering.py
    face_engine.py
    face_tuning.py
    import_pipeline.py
    main.py
    models.py
    people.py
    repository.py
    schemas.py
    scrfd_detector.py
    search_service.py
    serializers.py
    video_embeddings.py
    video_processing.py
    watcher.py
frontend/
  src/
    components/
    layouts/
    router/
    services/
    views/
  src-tauri/
scripts/
  evaluate-face-retrieval.py
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

## 验证记录

当前已验证：

- `python -m compileall backend/app`
- `npm run build`
- `FastAPI TestClient`：
  - `GET /api/v1/health`
  - `GET /api/v1/videos`
  - `POST /api/v1/search/videos`
- 临时闭环烟测：
  - 生成一个临时 mp4
  - 导入视频成功
  - 读取视频缩略图成功
  - `POST /api/v1/search/videos/by-video` 成功命中

## 许可证与使用边界

- `SCRFD` 模型来自 InsightFace 发布包，使用前请确认对应模型的许可边界
- `AdaFace` 权重来自官方 Hugging Face 仓库，使用前同样建议核对模型许可与商用条件
- `SigLIP2` 和视频理解模型同样建议在实际商用前核对各自许可
- 当前仓库更适合作为课程项目、自用工具或内部原型
