# 跨源 AI 图片智能管理系统

这是一个面向 Windows 桌面场景的 AI 图片管理 MVP，目标是把微信目录、QQ 目录、本地图库和拍照图片统一纳入一个可检索、可归档、可自动分析的系统。

当前版本已经具备：

- 多源目录接入
- 手动导入 + 实时目录监听
- SHA256 + pHash 去重
- 本地 OCR + 可配置视觉模型分析
- 人脸聚类、人物库、人物参考图上传
- 删除人物、删除单张人物参考图
- 自然语言检索、标签检索、以图搜图、按人物图检索
- 人脸簇独立管理页
- 监听任务队列化与状态展示
- 图片详情抽屉、重分析、相似图查找

## 技术栈

- 桌面端：`Tauri + Vue3 + Element Plus`
- 后端：`FastAPI + SQLModel + SQLite`
- 图片存储：本地文件系统
- OCR：`RapidOCR`
- 视觉分析：`OpenAI-compatible` 多模态接口
- 人脸识别：`OpenCV Haar Cascade + 对齐后的人脸多特征描述子`
- 向量检索：本地轻量多模态向量
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

## 人物识别算法说明

这次版本把原来过于简单的“灰度缩放 + 直方图”方案升级成了更稳定的人脸描述流程：

1. 使用 `Haar Cascade` 检测人脸
2. 尝试用眼睛检测做轻量对齐
3. 对人脸做 `CLAHE` 对比度增强
4. 组合梯度方向直方图、局部二值模式（LBP）、低频 DCT 特征和对称性特征
5. 以归一化向量做聚类和人物匹配
6. 上传新参考图后，结合人物中心和样本相似度重新绑定人脸簇

另外，启动时如果检测到数据库里还保留旧版人脸 embedding，会自动做一次索引升级，避免旧数据和新算法不兼容。

## 项目结构

```text
docs/
  architecture.md
  windows-build-tools.md
backend/
  app/
    ai.py
    config.py
    connectors.py
    database.py
    embeddings.py
    face_clustering.py
    import_pipeline.py
    main.py
    models.py
    people.py
    repository.py
    schemas.py
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
WATCHER_ENABLED=true
WATCHER_RECURSIVE=true
WATCHER_DEBOUNCE_SECONDS=3
FACE_CLUSTER_SIMILARITY_THRESHOLD=0.86
PERSON_RECOGNITION_SIMILARITY_THRESHOLD=0.84
```

如果你希望人物识别更保守，可以适当调高：

- `FACE_CLUSTER_SIMILARITY_THRESHOLD`
- `PERSON_RECOGNITION_SIMILARITY_THRESHOLD`

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
  - 健康检查
  - 按人物图检索
  - 新建人物
  - 上传参考图
  - 删除单张参考图
  - 删除人物

## 已知限制

- 当前仍是工程可落地版，不是深度学习级人脸识别方案
- 微信 / QQ 目前采用本地目录导入与监听，不涉及逆向协议登录
- 大规模图片库下，人物索引和搜索还需要进一步做批处理与异步任务化

## 下一步建议

- 替换为 `InsightFace / FaceNet` 等更强的人脸模型
- 为人物样本增加裁剪与主脸确认
- 把全库重分析做成后台任务
- 引入更强的图片向量模型，如 `CLIP / SigLIP`
