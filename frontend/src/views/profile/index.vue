<template>
  <div>
    <div class="page-intro">
      <h2>个人设置</h2>
      <p>维护你的学习画像，个性化学习建议会参考这些信息。</p>
    </div>

    <div class="profile-layout">
      <div class="kp-card profile-side">
        <el-avatar :size="72">{{ userStore.displayName.slice(0, 1).toUpperCase() }}</el-avatar>
        <div class="profile-name">{{ userStore.displayName }}</div>
        <el-tag v-if="userStore.isAdmin" type="warning" size="small">管理员</el-tag>
      </div>

      <div class="kp-card profile-form">
        <el-skeleton v-if="loading" :rows="5" animated />
        <el-form v-else ref="formRef" :model="form" label-position="top" style="max-width: 520px">
          <el-form-item label="邮箱">
            <el-input v-model="form.email" placeholder="example@domain.com" />
          </el-form-item>
          <el-form-item label="专业 / 领域">
            <el-input v-model="form.major" placeholder="例如：计算机科学" />
          </el-form-item>
          <el-form-item label="学习阶段">
            <el-input v-model="form.level" placeholder="例如：大二 / 在职 / 初级" />
          </el-form-item>
          <el-form-item label="学习目标">
            <el-input v-model="form.goals" type="textarea" :rows="3" placeholder="例如：三个月内掌握 Python 数据分析" />
          </el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useUserStore } from '@/store/user';

const userStore = useUserStore();
const loading = ref(true);
const saving = ref(false);
const formRef = ref();
const form = reactive({ email: '', major: '', level: '', goals: '' });

onMounted(async () => {
  await userStore.fetchMe();
  const u = userStore.user || {};
  const p = u.profile || {};
  Object.assign(form, {
    email: u.email || '',
    major: p.major || '',
    level: p.level || '',
    goals: p.goals || '',
  });
  loading.value = false;
});

async function save() {
  saving.value = true;
  try {
    await userStore.saveProfile({
      email: form.email,
      major: form.major,
      level: form.level,
      goals: form.goals,
    });
    ElMessage.success('已保存');
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.profile-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 16px;
  align-items: start;
}
.profile-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px 16px;
}
.profile-name {
  font-size: 17px;
  font-weight: 600;
  color: #16302a;
}
@media (max-width: 720px) {
  .profile-layout { grid-template-columns: 1fr; }
}
</style>
