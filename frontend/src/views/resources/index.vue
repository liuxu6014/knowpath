<template>
  <div>
    <div class="page-intro">
      <div>
        <h2>资料库</h2>
        <p>上传或粘贴学习资料，系统会自动切分并用于知识图谱构建。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增资料</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />

    <el-empty v-else-if="!resources.length" description="还没有学习资料" />

    <el-table v-else :data="resources" size="default">
      <el-table-column prop="title" label="标题" min-width="180">
        <template #default="{ row }">
          <el-link type="primary" @click="openDetail(row)">{{ row.title }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="subject_name" label="学习对象" min-width="140" />
      <el-table-column prop="chunks" label="切片" width="80" />
      <el-table-column label="处理状态" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.task" :type="taskType(row.task.status)" size="small">
            {{ taskLabel(row.task) }}
          </el-tag>
          <el-tag v-else size="small" type="info">未处理</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" text @click="parse(row)">解析</el-button>
          <el-button size="small" text @click="openDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建资料 -->
    <el-dialog v-model="create.visible" title="新增资料" width="600px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top">
        <el-form-item label="标题" prop="title">
          <el-input v-model="createForm.title" placeholder="资料标题" />
        </el-form-item>
        <el-form-item label="所属学习对象" prop="subject_id">
          <el-select v-model="createForm.subject_id" placeholder="选择学习对象" style="width: 100%">
            <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="createForm.content" type="textarea" :rows="8" placeholder="粘贴 Markdown / 文本内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="create.visible = false">取消</el-button>
        <el-button type="primary" :loading="create.loading" @click="saveCreate">创建并解析</el-button>
      </template>
    </el-dialog>

    <!-- 资料详情 -->
    <el-drawer v-model="detail.visible" :title="detail.title" size="640px">
      <template v-if="detail.content">
        <pre class="resource-content">{{ detail.content }}</pre>
      </template>
      <el-empty v-else description="无内容" />
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import { listResources, listSubjects, createResource, getResource, parseResource } from '@/api';

const loading = ref(true);
const resources = ref([]);
const subjects = ref([]);

const createFormRef = ref();
const create = reactive({ visible: false, loading: false });
const createForm = reactive({ title: '', subject_id: null, content: '' });
const createRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  subject_id: [{ required: true, message: '请选择学习对象', trigger: 'change' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }],
};

const detail = reactive({ visible: false, title: '', content: '' });

async function load() {
  loading.value = true;
  try {
    const [res, subs] = await Promise.all([listResources(), listSubjects()]);
    resources.value = res.items || [];
    subjects.value = subs.items || [];
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function taskType(status) {
  return { succeeded: 'success', failed: 'danger', running: 'warning' }[status] || 'info';
}
function taskLabel(task) {
  if (task.status === 'succeeded') return '已完成';
  if (task.status === 'failed') return '失败';
  if (task.status === 'running') return `处理中 ${task.progress}%`;
  return task.status;
}

function openCreate() {
  Object.assign(createForm, { title: '', subject_id: null, content: '' });
  create.visible = true;
}

async function saveCreate() {
  await createFormRef.value.validate();
  create.loading = true;
  try {
    await createResource({
      title: createForm.title,
      subject_id: createForm.subject_id,
      content: createForm.content,
    });
    ElMessage.success('资料已创建并开始解析');
    create.visible = false;
    await load();
  } finally {
    create.loading = false;
  }
}

async function parse(row) {
  await parseResource(row.id);
  ElMessage.success('已触发重新解析');
  await load();
}

async function openDetail(row) {
  const data = await getResource(row.id);
  detail.title = data.title;
  detail.content = data.content;
  detail.visible = true;
}
</script>

<style scoped>
.resource-content {
  margin: 0;
  padding: 16px;
  background: #f6f9f8;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 70vh;
  overflow: auto;
}
</style>
