import { createRouter, createWebHistory } from 'vue-router'

import AppShell from '../layouts/AppShell.vue'
import FaceClustersView from '../views/FaceClustersView.vue'
import FaceTuningView from '../views/FaceTuningView.vue'
import JobsView from '../views/JobsView.vue'
import PeopleCorrectionsView from '../views/PeopleCorrectionsView.vue'
import PeopleView from '../views/PeopleView.vue'
import SearchView from '../views/SearchView.vue'
import SourcesView from '../views/SourcesView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppShell,
      children: [
        {
          path: '',
          redirect: '/search',
        },
        {
          path: '/search',
          component: SearchView,
          meta: {
            title: '自然语言与向量检索',
            description: '用一句话找回跨来源图片，也支持上传参考图做相似检索。',
          },
        },
        {
          path: '/people',
          component: PeopleView,
          meta: {
            title: '人物库与人物识别',
            description: '上传人物参考图、维护人物档案，并按人名或人像检索图库。',
          },
        },
        {
          path: '/people-corrections',
          component: PeopleCorrectionsView,
          meta: {
            title: '批量人物标注校正',
            description: '按人脸簇批量纠正误识别、漏识别和需要改派的人物绑定。',
          },
        },
        {
          path: '/faces',
          component: FaceClustersView,
          meta: {
            title: '人脸簇独立管理',
            description: '查看聚类数量、样例图和命名状态，并集中管理某个人脸簇下的图片。',
          },
        },
        {
          path: '/face-tuning',
          component: FaceTuningView,
          meta: {
            title: '阈值可视化调参',
            description: '预览聚类阈值和人物识别阈值在当前图库上的命中边界，再决定是否重建索引。',
          },
        },
        {
          path: '/sources',
          component: SourcesView,
          meta: {
            title: '图片源配置与实时监听',
            description: '统一接入本地图库、微信目录和 QQ 目录，并观察监听队列是否堆积。',
          },
        },
        {
          path: '/jobs',
          component: JobsView,
          meta: {
            title: '导入任务与归档结果',
            description: '查看每次导入的扫描、去重和归档结果，快速判断来源接入质量。',
          },
        },
      ],
    },
  ],
})

export default router
