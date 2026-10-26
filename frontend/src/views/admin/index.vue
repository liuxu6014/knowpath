<template>
  <div>
    <div class="page-intro">
      <h2>管理后台</h2>
      <p>管理用户、模型配置与提示词模板（仅管理员可见）。</p>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="用户" name="users">
        <el-table :data="users" size="small" v-loading="loading.users">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="username" label="用户名" min-width="140" />
          <el-table-column prop="email" label="邮箱" min-width="180" />
          <el-table-column label="角色" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_staff ? 'warning' : 'info'" size="small">{{ row.is_staff ? '管理员' : '用户' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '正常' : '停用' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="模型配置" name="models">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" :icon="Plus" @click="openModel()">新建配置</el-button>
        </div>
        <el-table :data="models" size="small" v-loading="loading.models">
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="provider" label="提供商" min-width="140" />
          <el-table-column prop="model" label="模型" min-width="140" />
          <el-table-column prop="base_url" label="Base URL" min-width="220" show-overflow-tooltip />
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openModel(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="提示词模板" name="prompts">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" :icon="Plus" @click="openPrompt()">新建模板</el-button>
        </div>
        <el-table :data="prompts" size="small" v-loading="loading.prompts">
          <el-table-column prop="code" label="代码" min-width="140" />
          <el-table-column prop="version" label="版本" width="80" />
          <el-table-column prop="template" label="模板内容" min-width="280" show-overflow-tooltip />
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openPrompt(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="审计日志" name="logs">
        <el-table :data="logs" size="small" v-loading="loading.logs">
          <el-table-column prop="action" label="动作" min-width="160" />
          <el-table-column prop="path" label="路径" min-width="200" show-overflow-tooltip />
          <el-table-column prop="user_id" label="用户" width="80" />
          <el-table-column label="时间" width="180">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 模型配置弹窗 -->
    <el-dialog v-model="modelDialog.visible" :title="modelDialog.isEdit ? '编辑模型配置' : '新建模型配置'" width="520px">
      <el-form ref="modelFormRef" :model="modelForm" label-position="top">
        <el-form-item label="名称" required>
          <el-input v-model="modelForm.name" placeholder="例如：本地 Ollama" />
        </el-form-item>
        <el-form-item label="提供商">
          <el-input v-model="modelForm.provider" placeholder="例如：openai-compatible" />
        </el-form-item>
        <el-form-item label="Base URL" required>
          <el-input v-model="modelForm.base_url" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="modelForm.model" placeholder="例如：gpt-4o-mini" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="modelForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="modelDialog.loading" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>

    <!-- 提示词弹窗 -->
    <el-dialog v-model="promptDialog.visible" :title="promptDialog.isEdit ? '编辑提示词模板' : '新建提示词模板'" width="520px">
      <el-form ref="promptFormRef" :model="promptForm" label-position="top">
        <el-form-item label="代码" required>
          <el-input v-model="promptForm.code" placeholder="例如：generate_lesson" />
        </el-form-item>
        <el-form-item label="版本" required>
          <el-input-number v-model="promptForm.version" :min="1" />
        </el-form-item>
        <el-form-item label="模板内容" required>
          <el-input v-model="promptForm.template" type="textarea" :rows="6" placeholder="提示词模板…" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="promptForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="promptDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="promptDialog.loading" @click="savePrompt">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import {
  listAdminUsers, listModelConfigs, listPrompts, listAiLogs,
  createModelConfig, patchModelConfig, createPrompt, patchPrompt,
} from '@/api';

const tab = ref('users');
const users = ref([]);
const models = ref([]);
const prompts = ref([]);
const logs = ref([]);
const loading = reactive({ users: false, models: false, prompts: false, logs: false });

const modelDialog = reactive({ visible: false, isEdit: false, loading: false });
const modelForm = reactive({ id: null, name: '', provider: 'openai-compatible', base_url: '', model: '', enabled: true });
const modelFormRef = ref();

const promptDialog = reactive({ visible: false, isEdit: false, loading: false });
const promptForm = reactive({ id: null, code: '', version: 1, template: '', enabled: true });
const promptFormRef = ref();

onMounted(async () => {
  await Promise.all([loadUsers(), loadModels(), loadPrompts(), loadLogs()]);
});

async function loadUsers() {
  loading.users = true;
  try { users.value = (await listAdminUsers()).items || []; } finally { loading.users = false; }
}
async function loadModels() {
  loading.models = true;
  try { models.value = (await listModelConfigs()).items || []; } finally { loading.models = false; }
}
async function loadPrompts() {
  loading.prompts = true;
  try { prompts.value = (await listPrompts()).items || []; } finally { loading.prompts = false; }
}
async function loadLogs() {
  loading.logs = true;
  try { logs.value = (await listAiLogs()).items || []; } finally { loading.logs = false; }
}

function openModel(row) {
  if (row) {
    Object.assign(modelForm, { id: row.id, name: row.name, provider: row.provider, base_url: row.base_url, model: row.model, enabled: row.enabled });
    modelDialog.isEdit = true;
  } else {
    Object.assign(modelForm, { id: null, name: '', provider: 'openai-compatible', base_url: '', model: '', enabled: true });
    modelDialog.isEdit = false;
  }
  modelDialog.visible = true;
}
async function saveModel() {
  if (!modelForm.name.trim() || !modelForm.base_url.trim()) {
    ElMessage.warning('请填写名称与 Base URL');
    return;
  }
  modelDialog.loading = true;
  try {
    const payload = { name: modelForm.name, provider: modelForm.provider, base_url: modelForm.base_url, model: modelForm.model, enabled: modelForm.enabled };
    if (modelDialog.isEdit) await patchModelConfig(modelForm.id, payload);
    else await createModelConfig(payload);
    ElMessage.success('已保存');
    modelDialog.visible = false;
    await loadModels();
  } finally {
    modelDialog.loading = false;
  }
}

function openPrompt(row) {
  if (row) {
    Object.assign(promptForm, { id: row.id, code: row.code, version: row.version, template: row.template, enabled: row.enabled });
    promptDialog.isEdit = true;
  } else {
    Object.assign(promptForm, { id: null, code: '', version: 1, template: '', enabled: true });
    promptDialog.isEdit = false;
  }
  promptDialog.visible = true;
}
async function savePrompt() {
  if (!promptForm.code.trim() || !promptForm.template.trim()) {
    ElMessage.warning('请填写代码与模板内容');
    return;
  }
  promptDialog.loading = true;
  try {
    const payload = { code: promptForm.code, version: promptForm.version, template: promptForm.template, enabled: promptForm.enabled };
    if (promptDialog.isEdit) await patchPrompt(promptForm.id, payload);
    else await createPrompt(payload);
    ElMessage.success('已保存');
    promptDialog.visible = false;
    await loadPrompts();
  } finally {
    promptDialog.loading = false;
  }
}

function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '';
}
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
</style>
