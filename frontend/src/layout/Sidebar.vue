<template>
  <aside class="kp-sidebar" :class="{ collapsed }">
    <div class="kp-brand">
      <span class="kp-brand-mark">K</span>
      <span v-if="!collapsed" class="kp-brand-name">Know<em>Path</em></span>
    </div>

    <el-menu
      class="kp-menu"
      :default-active="route.path"
      :collapse="collapsed"
      :collapse-transition="false"
      router
      background-color="#123e34"
      text-color="#cfe0da"
      active-text-color="#ffffff"
    >
      <el-menu-item-group title="工作台">
        <el-menu-item index="/dashboard">
          <el-icon><Grid /></el-icon><span>总览</span>
        </el-menu-item>
        <el-menu-item index="/subjects">
          <el-icon><Notebook /></el-icon><span>学习对象</span>
        </el-menu-item>
      </el-menu-item-group>

      <el-menu-item-group title="内容与路径">
        <el-menu-item index="/resources">
          <el-icon><Document /></el-icon><span>资料库</span>
        </el-menu-item>
        <el-menu-item index="/graph">
          <el-icon><Share /></el-icon><span>知识图谱</span>
        </el-menu-item>
        <el-menu-item index="/assessment">
          <el-icon><EditPen /></el-icon><span>起点测评</span>
        </el-menu-item>
        <el-menu-item index="/path">
          <el-icon><Guide /></el-icon><span>我的路径</span>
        </el-menu-item>
        <el-menu-item index="/learning">
          <el-icon><VideoPlay /></el-icon><span>学习中心</span>
        </el-menu-item>
        <el-menu-item index="/quizzes">
          <el-icon><Tickets /></el-icon><span>练习与错题</span>
        </el-menu-item>
      </el-menu-item-group>

      <el-menu-item-group title="复盘成长">
        <el-menu-item index="/analytics">
          <el-icon><TrendCharts /></el-icon><span>能力画像</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DataAnalysis /></el-icon><span>学习报告</span>
        </el-menu-item>
        <el-menu-item index="/notes">
          <el-icon><Memo /></el-icon><span>我的笔记</span>
        </el-menu-item>
      </el-menu-item-group>

      <el-menu-item-group title="系统">
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon><span>任务中心</span>
        </el-menu-item>
        <el-menu-item v-if="userStore.isAdmin" index="/admin">
          <el-icon><Lock /></el-icon><span>管理后台</span>
        </el-menu-item>
      </el-menu-item-group>
    </el-menu>
  </aside>
</template>

<script setup>
import { storeToRefs } from 'pinia';
import { useRoute } from 'vue-router';
import {
  Grid, Notebook, Document, Share, EditPen, Guide, VideoPlay,
  Tickets, TrendCharts, DataAnalysis, Memo, List, Lock,
} from '@element-plus/icons-vue';
import { useAppStore } from '@/store/app';
import { useUserStore } from '@/store/user';

const route = useRoute();
const appStore = useAppStore();
const userStore = useUserStore();
const { sidebarCollapsed: collapsed } = storeToRefs(appStore);
</script>

<style scoped>
.kp-sidebar {
  width: 232px;
  flex-shrink: 0;
  background: var(--kp-sidebar-bg);
  color: var(--kp-sidebar-text);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  transition: width 0.2s;
}
.kp-sidebar.collapsed {
  width: 64px;
}
.kp-sidebar.collapsed .kp-brand {
  justify-content: center;
  padding: 18px 15px;
}
.kp-sidebar.collapsed .kp-menu :deep(.el-menu-item-group__title) {
  display: none;
}
.kp-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px;
}
.kp-brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: linear-gradient(135deg, #2e9d7e, #1a5547);
  color: #fff;
  font-weight: 800;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kp-brand-name {
  color: #fff;
  font-size: 18px;
  font-weight: 700;
}
.kp-brand-name em {
  font-style: normal;
  color: #4fd1a5;
}
.kp-menu {
  border-right: none;
  flex: 1;
}
.kp-menu :deep(.el-menu-item-group__title) {
  padding: 14px 20px 6px;
  font-size: 11px;
  letter-spacing: 0.06em;
  color: #6f9c8e;
}
.kp-menu :deep(.el-menu-item) {
  height: 42px;
  line-height: 42px;
}
.kp-menu :deep(.el-menu-item.is-active) {
  background: var(--kp-sidebar-active);
  border-right: 3px solid #4fd1a5;
}
</style>
