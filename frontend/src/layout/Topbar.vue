<template>
  <header class="kp-topbar">
    <div class="kp-topbar-left">
      <el-button text @click="appStore.toggleSidebar()">
        <el-icon size="18"><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
      </el-button>
      <span class="kp-topbar-title">{{ route.meta.title || 'KnowPath' }}</span>
    </div>

    <div class="kp-topbar-right">
      <el-select
        v-model="appStore.currentSubjectId"
        placeholder="选择学习对象"
        clearable
        size="default"
        style="width: 220px"
        @change="onSubjectChange"
      >
        <el-option
          v-for="s in appStore.subjects"
          :key="s.id"
          :label="s.name"
          :value="s.id"
        />
      </el-select>

      <el-tooltip content="刷新" placement="bottom">
        <el-button text @click="reload">
          <el-icon size="18"><Refresh /></el-icon>
        </el-button>
      </el-tooltip>

      <el-dropdown trigger="click" @command="onCommand">
        <span class="kp-user">
          <el-avatar :size="30">{{ userStore.displayName.slice(0, 1).toUpperCase() }}</el-avatar>
          <span class="kp-user-name">{{ userStore.displayName }}</span>
          <el-icon><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">个人设置</el-dropdown-item>
            <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessageBox } from 'element-plus';
import { Fold, Expand, Refresh, ArrowDown } from '@element-plus/icons-vue';
import { useAppStore } from '@/store/app';
import { useUserStore } from '@/store/user';

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const userStore = useUserStore();

onMounted(() => {
  if (userStore.isLoggedIn) {
    userStore.fetchMe().catch(() => {});
    appStore.loadSubjects().catch(() => {});
  }
});

function onSubjectChange(id) {
  appStore.setCurrentSubject(id);
}

function reload() {
  window.location.reload();
}

async function onCommand(cmd) {
  if (cmd === 'profile') {
    router.push('/profile');
  } else if (cmd === 'logout') {
    await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' }).then(
      async () => {
        await userStore.logoutAction();
        router.push('/login');
      },
    ).catch(() => {});
  }
}
</script>

<style scoped>
.kp-topbar {
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid #e6ecea;
}
.kp-topbar-left,
.kp-topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.kp-topbar-title {
  font-size: 15px;
  font-weight: 600;
  color: #16302a;
}
.kp-user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #16302a;
}
.kp-user-name {
  font-size: 13px;
}
</style>
