import { createRouter, createWebHistory } from 'vue-router'

import AppShell from '../layouts/AppShell.vue'
import FaceClustersView from '../views/FaceClustersView.vue'
import JobsView from '../views/JobsView.vue'
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
            description: '用一句话召回跨来源图片，也支持上传参考图做相似检索。',
          },
        },
        {
          path: '/faces',
          component: FaceClustersView,
          meta: {
            title: '人脸簇独立管理',
            description: '查看聚类数量、样例图、命名状态，并集中管理某个人脸簇下的图片。',
          },
        },
        {
          path: '/people',
          component: PeopleView,
          meta: {
            title: '人物库与人物识别',
            description: '为特定人物上传参考图，自动绑定人脸簇，并按人名或人像检索图片。',
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
