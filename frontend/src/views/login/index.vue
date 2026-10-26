<template>
  <div class="login-page">
    <div class="login-brand">
      <div class="login-brand-mark">K</div>
      <div>
        <h1>Know<em>Path</em></h1>
        <p>个性化学习路径工作台</p>
      </div>
    </div>

    <el-card class="login-card" shadow="always">
      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="邮箱（选填）" prop="email">
          <el-input v-model="form.email" placeholder="example@domain.com" :prefix-icon="Message" size="large" />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          class="login-submit"
          :loading="loading"
          @click="submit"
        >
          {{ mode === 'login' ? '登录' : '创建账号' }}
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { User, Lock, Message } from '@element-plus/icons-vue';
import { useUserStore } from '@/store/user';

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();

const mode = ref('login');
const loading = ref(false);
const formRef = ref();
const form = reactive({ username: '', password: '', email: '' });

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
};

async function submit() {
  await formRef.value.validate();
  loading.value = true;
  try {
    if (mode.value === 'login') {
      await userStore.loginAction({ username: form.username, password: form.password });
    } else {
      await userStore.registerAction({
        username: form.username,
        password: form.password,
        email: form.email || undefined,
      });
      ElMessage.success('注册成功，已自动登录');
      await userStore.loginAction({ username: form.username, password: form.password });
    }
    router.push(route.query.redirect || '/');
  } catch (e) {
    // error message already surfaced by the axios interceptor
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 28px;
  padding: 24px;
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(47, 157, 126, 0.18), transparent),
    radial-gradient(900px 500px at 110% 110%, rgba(26, 85, 71, 0.22), transparent),
    #f4f8f6;
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}
.login-brand-mark {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #2e9d7e, #1a5547);
  color: #fff;
  font-size: 26px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-brand h1 {
  margin: 0;
  font-size: 26px;
  color: #16302a;
}
.login-brand h1 em {
  font-style: normal;
  color: #1a5547;
}
.login-brand p {
  margin: 2px 0 0;
  font-size: 13px;
  color: #6b7f78;
}
.login-card {
  width: 400px;
  max-width: 100%;
  border-radius: 16px;
  border: 1px solid #e6ecea;
}
.login-submit {
  width: 100%;
  margin-top: 4px;
}
</style>
