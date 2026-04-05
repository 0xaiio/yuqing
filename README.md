# 跨源 AI 图片智能管理系统

这是一个面向 Windows 桌面场景的 AI 图片管理项目，目标是把微信目录、QQ 目录、本地图库和拍照图片统一纳入一个可检索、可归档、可自动分析的系统。

当前版本已经具备：

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

## 当前人脸方案

系统已经从旧的手工特征方案升级为：

- `SCRFD`：人脸检测
- `AdaFace`：人脸 embedding

默认本地部署配置：

- 检测模型：`buffalo_sc / det_500m.onnx`
- 识别模型：`minchul/cvlface_adaface_ir50_webface4m`

可通过环境变量切换到更强的检测包，例如：

- `buffalo_l / det_10g.onnx`

专项实施说明见：

- [docs/scrfd-adaface-readme.md](./docs/scrfd-adaface-readme.md)

## 技术栈

- 桌面端：`Tauri + Vue3 + Element Plus`
- 后端：`FastAPI + SQLModel + SQLite`
- 图片存储：本地文件系统
- OCR：`RapidOCR`
- 视觉分析：`OpenAI-compatible` 多模态接口
- 人脸检测：`SCRFD`
- 人脸识别：`AdaFace`
- 实时监听：`watchdog`

## 当前能力

### 1. 多源接入

- 支持 `local_folder`、`wechat_folder`、`qq_folder`
- 支持桌面端直接配置来源目录
- 在 Tauri 桌面壳中支持原生目录选择器

### 2. AI 分析

- 本地 OCR：提取图片中的文字
- 远程视觉模型：生成中文摘要、场景标签、物体标签
- 单图重分析：可在图片详情中重新触发

### 3. 人脸识别与人物库

- 导入时自动检测人脸并完成聚类
- 上传人物参考图后自动尝试绑定相似人脸簇
- 支持删除人物和删除人物的部分参考图
- 支持通过人物名搜索图片
- 支持通过人物头像搜索图片
- 支持在自然语言描述里直接写人物名

### 4. 批量人物标注校正

- 新增“批量人物标注校正”页面
- 以人脸簇为粒度批量绑定到当前人物
- 支持从当前人物批量解绑错误绑定的人脸簇
- 支持按推荐项、已绑定、未绑定、待改派筛选候选
- 每个候选会展示相似度、竞争分数、margin 和当前绑定人物

### 5. 阈值可视化调参

- 新增“阈值可视化调参”页面
- 可调整：
  - `FACE_DETECTION_CONFIDENCE_THRESHOLD`
  - `FACE_DETECTION_NMS_THRESHOLD`
  - `FACE_CLUSTER_SIMILARITY_THRESHOLD`
  - `PERSON_RECOGNITION_SIMILARITY_THRESHOLD`
- 支持预览：
  - 聚类最近邻分数分布
  - 人物最佳匹配分数分布
  - 潜在聚类合并数量
  - 模糊人物匹配数量
  - 接近阈值的边界样本
- 支持“保存阈值”与“保存并重建索引”

说明：

- 调参结果会持久化到 `data/face-runtime-config.json`
- 其中“聚类阈值 / 人物识别阈值”的预览基于当前数据库中的 512 维人脸向量
- “检测置信度 / NMS 阈值”会影响后续重建时的人脸检测结果，因此建议保存后执行一次重建索引

### 6. 检索能力

- 标签检索：人物 / 场景 / 物体 / 来源组合筛选
- 自然语言检索：例如“去年夏天和小明在海边拍的日落”
- 以图搜图：按整张图片的视觉特征和 OCR 内容找相似图
- 按人物图检索：只看人脸特征，适合找同一个人
- 相似图片：从单张图片继续找近似结果

### 7. 实时监听与自动管理

- 对启用状态的来源目录自动开启监听
- 监听事件先进入队列，再由后台 worker 顺序处理
- 前端可看到来源级别的排队数量、处理状态和最近处理时间

### 8. 评估脚本

新增脚本：

- `scripts/evaluate-face-retrieval.py`

脚本会基于当前人物样本和已绑定图片评估人脸检索效果，输出：

- 查询数
- `MRR`
- `Hit@1 / Hit@5 / Hit@10`
- 可选 JSON 详细报告

示例：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate-face-retrieval.py --top-k 1 5 10 --retrieval-limit 50
.\.venv\Scripts\python.exe .\scripts\evaluate-face-retrieval.py --output .\data\face-eval-report.json
```

## 项目结构

```text
docs/
  architecture.md
  scrfd-adaface-readme.md
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

默认脚本会自动完成：

1. 检查并创建 `.venv`
2. 检查并复制 `backend/.env`
3. 安装后端依赖
4. 安装前端依赖
5. 注入 Rust PATH
6. 在 `-WithTauri` 模式下自动导入 Visual Studio Developer Shell
7. 补齐 `cl.exe / link.exe / rc.exe / Windows SDK`
8. 启动 FastAPI
9. 启动 Vite 或 Tauri

可选参数：

```powershell
.\scripts\start-local.ps1 -SkipInstall
.\scripts\start-local.ps1 -WithTauri
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

### 6. 启动 Tauri

```powershell
cd frontend
npm run tauri:dev
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
AI_VISION_TIMEOUT_SECONDS=90
SEARCH_UPLOAD_ROOT=D:/code-repos/yuqing/data/search-uploads
PERSON_LIBRARY_ROOT=D:/code-repos/yuqing/data/person-library
FACE_MODEL_ROOT=D:/code-repos/yuqing/data/face-models
FACE_RUNTIME_CONFIG_PATH=D:/code-repos/yuqing/data/face-runtime-config.json
FACE_DETECTION_PACK_NAME=buffalo_sc
FACE_DETECTION_MODEL_FILENAME=det_500m.onnx
FACE_DETECTION_INPUT_SIZE=640
FACE_DETECTION_CONFIDENCE_THRESHOLD=0.45
FACE_DETECTION_NMS_THRESHOLD=0.4
FACE_DETECTION_MAX_FACES=6
FACE_RECOGNITION_REPO_ID=minchul/cvlface_adaface_ir50_webface4m
FACE_RECOGNITION_MODEL_FILENAME=model.pt
FACE_RECOGNITION_DEVICE=cpu
FACE_RECOGNITION_BATCH_SIZE=8
FACE_CLUSTER_SIMILARITY_THRESHOLD=0.5
PERSON_RECOGNITION_SIMILARITY_THRESHOLD=0.52
FACE_TUNING_PREVIEW_CLUSTER_LIMIT=240
```

## 主要页面

- `/search`：自然语言搜索、标签搜索、以图搜图、按人物图检索
- `/people`：人物库与人物参考图管理
- `/people-corrections`：批量人物标注校正
- `/faces`：人脸簇独立管理
- `/face-tuning`：阈值可视化调参
- `/sources`：来源配置与实时监听
- `/jobs`：导入任务记录

## 主要 API

- `GET /api/v1/people/{person_id}/correction-candidates`
- `POST /api/v1/people/{person_id}/cluster-corrections`
- `GET /api/v1/face-tuning`
- `POST /api/v1/face-tuning/preview`
- `POST /api/v1/face-tuning/settings`

## 验证记录

本轮已完成：

- `python -m compileall backend/app scripts/evaluate-face-retrieval.py`
- `npm run build`
- `FastAPI TestClient` 烟测：
  - `GET /api/v1/face-tuning`
  - `POST /api/v1/face-tuning/preview`
  - `POST /api/v1/face-tuning/settings`
  - `GET /api/v1/people/{person_id}/correction-candidates`
- 评估脚本烟测：
  - `scripts/evaluate-face-retrieval.py --top-k 1 5 10 --retrieval-limit 50`

## 许可证与使用边界

- `SCRFD` 模型来自 InsightFace 发布包，使用前请确认对应模型的许可边界
- `AdaFace` 权重来自官方 Hugging Face 仓库，使用前同样建议核对模型许可与商用条件
- 当前仓库更适合作为课程项目、自用工具或内部原型
