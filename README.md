# 跨源 AI 图片智能管理系统

这是一个按“Windows 桌面端 + Python 后端 + 微信/QQ 目录接入”路线搭建的可运行 MVP，目标是把微信、QQ、本地图库和拍照图片统一纳入一个可检索、可归档、可自动分析的系统。

当前版本已经具备：

- 多来源目录接入
- 手动导入 + 实时目录监听
- SHA256 + pHash 去重
- 本地 OCR + 可配置视觉模型分析
- 轻量级人脸聚类与命名
- 关键词 / 向量 / 相似图检索
- 以图搜图上传入口
- 人物库与人物参考图上传
- 按人物图检索图片
- 人脸簇独立管理页
- 监听任务队列化与队列状态展示
- 图片详情抽屉、重新分析和人脸簇命名

## 当前技术路线

- 桌面端：`Tauri + Vue3 + Element Plus`
- 后端：`FastAPI + SQLModel + SQLite`
- 图片存储：本地文件系统
- OCR：`RapidOCR`
- 视觉分析：`OpenAI-compatible` 多模态接口
- 人脸聚类：`OpenCV Haar Cascade + 本地轻量 embedding`
- 向量检索：本地 `240` 维多模态向量
- 实时监听：`watchdog`
- 微信 / QQ 接入：用户授权的本地目录导入与监听

## 当前能力说明

### 1. 多源接入

- 支持 `local_folder`、`wechat_folder`、`qq_folder`
- 可在桌面端直接配置来源目录
- 在 Tauri 桌面壳中支持原生目录选择器

### 2. AI 分析

- 本地 OCR：从图片中抽取文字
- 远程视觉模型：生成摘要、场景标签、物体标签
- 单图重新分析：可在详情抽屉中重新触发

### 3. 人脸聚类与命名

- 导入时会尝试检测图片中的人脸
- 基于本地轻量 embedding 做聚类
- 支持给人脸簇命名，例如“爸爸”“小明”
- 命名后可直接参与搜索结果召回

说明：

- 当前人脸聚类是“工程可落地版本”，重点是流程打通，不是高精度深度学习人脸识别方案
- 后续可以替换为 `InsightFace`、`FaceNet` 等更强模型

### 4. 向量检索

- 搜索页支持三种模式：
  - `混合检索`
  - `关键词优先`
  - `向量优先`
- 每张图片会生成一份本地多模态向量
- 支持“查找相似图片”

说明：

- 当前向量方案是本地轻量版本，适合 MVP 和桌面单机演示
- 后续可以替换为 `CLIP`、`SigLIP` 或云端 embedding 服务

### 5. 实时目录监听

- 对启用状态的来源目录自动开启监听
- 新增图片后不会直接在文件事件线程里导入，而是先进入后台队列
- 同一来源目录的监听事件会先合并，再由单独 worker 顺序处理
- 前端可看到来源级别的排队数量、处理中状态、最近事件时间和最近完成时间
- 工作台概览会展示当前监听目录数、排队任务数和 worker 是否忙碌

### 6. 人脸簇独立管理页

- 单独浏览所有人脸簇
- 按“全部 / 已命名 / 未命名”筛选
- 查看聚类示例图、图片数量和最近更新时间
- 在聚类详情区直接重命名，并查看该聚类下的全部图片

### 7. 以图搜图上传入口

- 搜索页支持上传一张参考图
- 后端会对上传图做 OCR、视觉摘要和本地向量编码
- 使用统一向量索引返回相似图片结果
- 上传文件只用于本次检索，处理完成后会自动删除临时文件

### 8. 人物库与按人物检索

- 支持新建人物档案，并上传带名字的人物参考图
- 上传参考图后，会抽取人脸 embedding，并尝试绑定到已有相似人脸簇
- 后续搜索可直接使用人物名
- 搜索页也支持上传一张人物头像，直接查找同一个人的图片
- 自然语言描述中可以直接使用人名，例如“和小明在海边拍的照片”

## 项目结构

```text
docs/
  architecture.md
  windows-build-tools.md
backend/
  app/
    ai.py                 # OCR + 视觉模型分析
    config.py             # 配置项
    connectors.py         # 多源目录接入
    database.py           # 数据库与轻量迁移
    embeddings.py         # 本地多模态向量
    face_clustering.py    # 人脸检测 / 聚类 / 命名
    import_pipeline.py    # 导入、归档、去重、分析
    main.py               # FastAPI 入口
    models.py             # SQLModel 数据模型
    repository.py         # 数据访问
    schemas.py            # API schema
    search_service.py     # 搜索与相似图服务
    serializers.py        # 输出序列化
    watcher.py            # 实时目录监听
frontend/
  src/
    components/           # 图片卡片、详情抽屉等
    layouts/              # 桌面壳布局
    router/               # 路由
    services/             # API 与桌面能力
    views/                # 搜索 / 人脸簇 / 图片源 / 导入任务
  src-tauri/              # Tauri 桌面壳
scripts/
  start-local.ps1         # 一键启动脚本
start-local.bat           # Windows 双击启动入口
```

## 一键启动

### Windows 双击版

直接运行：

```bat
start-local.bat
```

### PowerShell 版

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

脚本默认会：

1. 检查并创建 `.venv`
2. 检查并复制 `backend/.env`
3. 安装后端依赖
4. 安装前端依赖
5. 自动把 `%USERPROFILE%\.cargo\bin` 注入当前启动链路的 `PATH`
6. 在 `-WithTauri` 模式下检查 `rustc/cargo` 与 `MSVC Build Tools`
7. 拉起 FastAPI
8. 拉起 Vite 或 Tauri
9. 打开前端页面和 Swagger 文档

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
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run tauri:dev
```

## Tauri 前置条件

要运行 Tauri 桌面壳，需要安装：

- `rustc`
- `cargo`
- 确保 `%USERPROFILE%\.cargo\bin` 已加入 `PATH`
- `Windows Visual Studio Build Tools 2022`
  - `MSVC v143 C++ toolset`
  - `Windows 11 SDK 22621`

如果只联调前端页面，运行 `npm run dev` 即可，不强依赖 Tauri。

## 管理员安装 Build Tools

推荐在“管理员 PowerShell”里直接执行：

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e `
  --accept-package-agreements `
  --accept-source-agreements `
  --override "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --includeRecommended"
```

安装完成后重开终端，再执行：

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe" -products * -format json
where cl
```

更完整的管理员安装与排障步骤见 [docs/windows-build-tools.md](./docs/windows-build-tools.md)。

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
WATCHER_ENABLED=true
WATCHER_RECURSIVE=true
WATCHER_DEBOUNCE_SECONDS=3
FACE_CLUSTER_SIMILARITY_THRESHOLD=0.86
PERSON_RECOGNITION_SIMILARITY_THRESHOLD=0.84
```

## 已有 API 能力

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
- `GET /api/v1/people/{id}/samples`
- `POST /api/v1/people/{id}/samples`
- `GET /api/v1/people/{id}/photos`
- `GET /api/v1/person-samples/{id}/asset`
- `POST /api/v1/search/by-image`
- `POST /api/v1/search/by-person-image`
- `POST /api/v1/search`

## 当前前端页面

- 搜索页
  - 关键词 / 向量 / 混合检索
  - 上传参考图做以图搜图
  - 上传人物头像做按人物检索
  - 从人物库选择已标注人物
  - 相似图检索
  - 图片详情抽屉
- 人物库页
  - 新建人物档案
  - 上传带名字的人物参考图
  - 查看该人物相关图片
- 人脸簇页
  - 聚类列表与筛选
  - 人脸簇重命名
  - 查看该聚类下的全部图片
- 图片源页
  - 新建图片源
  - 原生目录选择器
  - 手动导入
  - 实时监听开关
  - 监听队列状态与最近处理时间
- 导入任务页
  - 批次概览
  - 导入明细
  - 去重统计

## 验证情况

本地已完成：

- 后端依赖安装校验
- 后端语法检查
- FastAPI 启动校验
- 前端 `npm run build`
- 本地 smoke test：
  - 新建来源
  - 导入两张测试图片
  - 关键词搜索命中
  - 向量搜索命中
  - 相似图检索返回结果
  - 实时监听状态可读取

当前开发机环境检查结果：

- `rustc` 已安装，位于 `%USERPROFILE%\.cargo\bin`
- `cargo` 已安装，位于 `%USERPROFILE%\.cargo\bin`
- 当前 shell 默认仍不一定自动带上该目录到 `PATH`，但一键启动脚本会自动补齐
- 已检测到 `Visual Studio Community 2026`
- 已检测到 `cl.exe`，位于 `D:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\...`
- 当前尚未完成一次稳定的 `tauri info / tauri dev` 验证，因此 Tauri 环境已接近可用，但还没做最终确认

## 下一步建议

- 替换成更强的人脸识别与向量模型
- 增加自动相册与时间轴视图
- 把监听队列升级为持久化任务系统
- 为以图搜图补“上传后裁剪 / 多图比对 / 搜索历史”
