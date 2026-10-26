import { createRouter, createWebHistory } from 'vue-router';
import { useUserStore } from '@/store/user';

const Layout = () => import('@/layout/index.vue');

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/dashboard/index.vue'), meta: { title: '总览', icon: 'Grid' } },
      { path: 'subjects', name: 'Subjects', component: () => import('@/views/subjects/index.vue'), meta: { title: '学习对象', icon: 'Notebook' } },
      { path: 'resources', name: 'Resources', component: () => import('@/views/resources/index.vue'), meta: { title: '资料库', icon: 'Document' } },
      { path: 'graph', name: 'Graph', component: () => import('@/views/graph/index.vue'), meta: { title: '知识图谱', icon: 'Share' } },
      { path: 'assessment', name: 'Assessment', component: () => import('@/views/assessment/index.vue'), meta: { title: '起点测评', icon: 'EditPen' } },
      { path: 'path', name: 'Path', component: () => import('@/views/path/index.vue'), meta: { title: '我的路径', icon: 'Guide' } },
      { path: 'learning', name: 'Learning', component: () => import('@/views/learning/index.vue'), meta: { title: '学习中心', icon: 'VideoPlay' } },
      { path: 'quizzes', name: 'Quizzes', component: () => import('@/views/quizzes/index.vue'), meta: { title: '练习与错题', icon: 'Tickets' } },
      { path: 'analytics', name: 'Analytics', component: () => import('@/views/analytics/index.vue'), meta: { title: '能力画像', icon: 'TrendCharts' } },
      { path: 'reports', name: 'Reports', component: () => import('@/views/reports/index.vue'), meta: { title: '学习报告', icon: 'DataAnalysis' } },
      { path: 'notes', name: 'Notes', component: () => import('@/views/notes/index.vue'), meta: { title: '我的笔记', icon: 'Memo' } },
      { path: 'profile', name: 'Profile', component: () => import('@/views/profile/index.vue'), meta: { title: '个人设置', icon: 'User' } },
      { path: 'tasks', name: 'Tasks', component: () => import('@/views/tasks/index.vue'), meta: { title: '任务中心', icon: 'List' } },
      { path: 'admin', name: 'Admin', component: () => import('@/views/admin/index.vue'), meta: { title: '管理后台', icon: 'Lock' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const userStore = useUserStore();
  document.title = `${to.meta.title ? to.meta.title + ' · ' : ''}KnowPath 学习工作台`;

  if (!to.meta.public && !userStore.token) {
    return { path: '/login', query: { redirect: to.fullPath } };
  }
  if (to.path === '/login' && userStore.token) {
    return { path: '/' };
  }
  return true;
});

export default router;
