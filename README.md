# 跨源 AI 图片智能管理系统

这是一个面向 Windows 桌面场景的 AI 图片管理 MVP，目标是把微信目录、QQ 目录、本地图库和拍照图片统一纳入一个可检索、可归档、可自动分析的系统。

当前版本已经具备：

- 多源目录接入
- 手动导入 + 实时目录监听
- SHA256 + pHash 去重
- 本地 OCR + 可配置视觉模型分析
- 人物库、人物参考图上传、删除人物、删除单张参考图
- 自然语言检索、标签检索、以图搜图、按人物图检索
- 人脸簇独立管理页
- 监听任务队列化与状态展示
- 图片详情抽屉、重分析、相似图查找

## 当前人脸方案

系统已经从原来的 OpenCV 手工特征方案升级为：

- `SCRFD` 人脸检测
- `AdaFace` 人脸 embedding

默认本地部署配置为：

- 检测模型：`buffalo_sc / det_500m.onnx`
- 识别模型：`minchul/cvlface_adaface_ir50_webface4m`

可通过环境变量切换到更强的检测包，例如：

- `buffalo_l / det_10g.onnx`

这次改造的专用实施说明和 TODO 在：

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
- 微信 / QQ 接入：用户授权的本地目录导入与监听

## 当前能力

### 1. 多源接入

- 支持 `local_folder`、`wechat_folder`、`qq_folder`
- 可在桌面端直接配置来源目录
- 在 Tauri 桌面壳中支持原生目录选择器

### 2. AI 分析

- 本地 OCR：提取图片中的文字
- 远程视觉模型：生成中文摘要、场景标签、物体标签
- 单图重分析：可在图片详情中重新触发

### 3. 人脸聚类与人物库

- 导入时自动检测人脸并做聚类
- 支持给人脸簇命名
- 支持新建人物档案并上传多张人物参考图
- 支持删除整个人物档案
- 支持删除人物的部分参考图，删除后会自动重算人物中心和相关绑定
- 上传参考图后，会自动把人物绑定到相似人脸簇
- 搜索时可以直接使用人物名，也可以上传人物头像查找同一人

### 4. 检索能力

- 标签检索：人物 / 场景 / 物体 / 来源组合筛选
- 自然语言检索：例如“去年夏天和小明在海边拍的日落”
- 以图搜图：按整张图片的视觉特征和 OCR 内容找相似图
- 按人物图检索：只看人脸特征，适合查找同一个人
- 相似图片：从单张图片继续找近似结果

### 5. 实时监听与自动管理

- 对启用状态的来源目录自动开启监听
- 监听事件先进入队列，再由后台 worker 顺序处理
- 前端可看到来源级别的排队数量、处理状态和最近处理时间

## 人脸模型说明

### 检测

- 通过官方 InsightFace 发布的模型包下载 `SCRFD` 检测模型
- 默认使用 `buffalo_sc` 中的 `det_500m.onnx`
- 支持通过配置切换到 `buffalo_l` 中的 `det_10g.onnx`

### 识别

- 通过官方 Hugging Face 仓库下载 `AdaFace` 预训练权重
- 默认使用 `minchul/cvlface_adaface_ir50_webface4m`
- 输出归一化后的 `512` 维 embedding

### 数据兼容

- 启动时会检测数据库中是否仍有旧版人脸 embedding
- 如果检测到旧数据，会自动重建人物样本、人脸簇和图片索引

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

脚本默认会自动完成：

1. 检查并创建 `.venv`
2. 检查并复制 `backend/.env`
3. 安装后端依赖
4. 安装前端依赖
5. 把 `%USERPROFILE%\.cargo\bin` 注入当前启动链路的 `PATH`
6. 在 `-WithTauri` 模式下自动导入 Visual Studio Developer Shell
7. 自动补齐 `cl.exe / link.exe / rc.exe / Windows SDK`
8. 检查 `rustc`、`cargo` 和 MSVC 工具链
9. 拉起 FastAPI
10. 拉起 Vite 或 Tauri

可选参数：

```powershell
.\scripts\start-local.ps1 -SkipInstall
.\scripts\start-local.ps1 -WithTauri
```

- `-SkipInstall`：跳过 `pip install` 和 `npm install`
- `-WithTauri`：使用 Tauri 桌面壳启动，而不是浏览器版 Vite

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

## Tauri 前置条件

要运行 Tauri 桌面壳，需要满足下面任一套条件：

- 已安装 `rustc`
- 已安装 `cargo`
- `%USERPROFILE%\.cargo\bin` 可被脚本注入到当前环境
- 已安装带 C++ 工具链的 Visual Studio
  - `Visual Studio Community` 或 `Build Tools`
  - `MSVC C++ toolset`
  - `Windows SDK`

如果只联调前端页面，运行 `npm run dev` 即可，不强依赖 Tauri。

管理员安装 Build Tools 的详细步骤见：

- [docs/windows-build-tools.md](./docs/windows-build-tools.md)

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
```

如果你希望更保守或更激进，可以重点调这几项：

- `FACE_DETECTION_CONFIDENCE_THRESHOLD`
- `FACE_CLUSTER_SIMILARITY_THRESHOLD`
- `PERSON_RECOGNITION_SIMILARITY_THRESHOLD`

## 依赖说明

后端依赖里已经包含：

- `huggingface_hub`
- `torch`
- `torchvision`

`requirements.txt` 已经加入 PyTorch CPU 源，所以直接执行：

```powershell
pip install -r backend\requirements.txt
```

即可完成当前默认方案的依赖安装。

## 已有 API

- `GET /api/v1/health`
- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `POST /api/v1/sources/{id}/import`
- `POST /api/v1/sources/{id}/watch/start`
- `POST /api/v1/sources/{id}/watch/stop`
- `GET /api/v1/import-jobs`
- `GET /api/v1/photos`
- `GET /api/v1/photos/{id}`
- `GET /api/v1/photos/{id}/asset`
- `POST /api/v1/photos/{id}/reanalyze`
- `GET /api/v1/photos/{id}/similar`
- `GET /api/v1/face-clusters`
- `GET /api/v1/face-clusters/{label}/photos`
- `POST /api/v1/face-clusters/{label}/rename`
- `GET /api/v1/people`
- `POST /api/v1/people`
- `POST /api/v1/people/{id}/rename`
- `DELETE /api/v1/people/{id}`
- `GET /api/v1/people/{id}/samples`
- `POST /api/v1/people/{id}/samples`
- `DELETE /api/v1/people/{id}/samples/{sample_id}`
- `GET /api/v1/people/{id}/photos`
- `GET /api/v1/person-samples/{id}/asset`
- `POST /api/v1/search/by-image`
- `POST /api/v1/search/by-person-image`
- `POST /api/v1/search`

## 当前前端页面

- 搜索页
  - 关键词 / 向量 / 混合检索
  - 以图搜图
  - 按人物图检索
  - 从人物库选择已标注人物
  - 图片详情抽屉
- 人物库页
  - 新建人物档案
  - 上传人物参考图
  - 删除整个人物
  - 删除单张人物参考图
  - 查看该人物相关图片
- 人脸簇页
  - 人脸簇列表和筛选
  - 人脸簇重命名
  - 查看聚类下的全部图片
- 图片源页
  - 新建来源
  - 目录选择器
  - 手动导入
  - 实时监听开关
  - 队列状态展示
- 导入任务页
  - 批次概览
  - 导入明细
  - 去重统计

## 已验证

已经做过以下验证：

- `python -m compileall backend/app`
- `npm run build`
- `FastAPI TestClient` 烟测
  - 启动时旧 embedding 自动升级
  - 按人物图检索
  - 新建人物
  - 上传参考图
  - 删除单张参考图
  - 删除人物
  - 人名搜索

## 许可证与使用边界

- `SCRFD` 检测模型通过官方 InsightFace 模型包下载
- `AdaFace` 权重通过官方 Hugging Face 仓库下载
- 如果要做商业化发布，建议你再次确认对应模型、训练数据集和权重的实际授权边界

## 已知限制

- 当前仍是工程可落地版，不是完整商用级人脸平台
- 微信 / QQ 目前采用本地目录导入与监听，不涉及逆向协议登录
- 首次下载模型和首次索引升级耗时会明显高于旧版 OpenCV 手工特征方案
- 大规模图片库下，人物索引和搜索还需要进一步做批处理与异步任务化

## 下一步建议

- 支持 `IR101` 与 `det_10g` 的前端切换
- 为人物样本增加裁剪与主脸确认
- 把全库重分析做成后台任务
- 引入更强的图片向量模型，如 `CLIP / SigLIP`
