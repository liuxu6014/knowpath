<template>
  <div>
    <div class="page-intro">
      <div>
        <h2>学习对象</h2>
        <p>每一个学习对象对应一张知识图谱与一条个性化学习路径。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建学习对象</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />

    <el-empty v-else-if="!subjects.length" description="还没有学习对象，点击右上角新建" />

    <el-row v-else :gutter="16">
      <el-col v-for="s in subjects" :key="s.id" :xs="24" :sm="12" :lg="8" :xl="6">
        <div class="subject-card">
          <div class="subject-head">
            <div class="subject-name">{{ s.name }}</div>
            <el-tag size="small" effect="plain">{{ typeLabel(s.subject_type) }}</el-tag>
          </div>
          <div class="subject-desc">{{ s.description || '暂无描述' }}</div>
          <div class="subject-progress">
            <el-progress :percentage="Math.round((s.progress || 0) * 100)" :stroke-width="8" />
          </div>
          <div class="subject-meta">
            <span>{{ s.concept_count ?? 0 }} 知识点</span>
            <span>{{ s.resource_count ?? 0 }} 资料</span>
            <span>{{ fmtMinutes(s.study_minutes) }}</span>
          </div>
          <div class="subject-actions">
            <el-button size="small" @click="openEdit(s)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="archive(s)">归档</el-button>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑学习对象' : '新建学习对象'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：Python 基础" />
        </el-form-item>
        <el-form-item label="类型" prop="subject_type">
          <el-select v-model="form.subject_type" style="width: 100%">
            <el-option label="课程" value="course" />
            <el-option label="技术主题" value="tech" />
            <el-option label="论文" value="paper" />
            <el-option label="专题" value="topic" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="这个学习对象要学什么？" />
        </el-form-item>
        <el-form-item label="学习目标" prop="learning_goal">
          <el-input v-model="form.learning_goal" type="textarea" :rows="2" placeholder="例如：能够独立完成一个数据分析项目" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import { listSubjects, createSubject, patchSubject, deleteSubject } from '@/api';
import { useAppStore } from '@/store/app';

const appStore = useAppStore();
const loading = ref(true);
const subjects = ref([]);
const formRef = ref();

const dialog = reactive({ visible: false, isEdit: false, loading: false });
const form = reactive({ name: '', subject_type: 'course', description: '', learning_goal: '' });

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  subject_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
};

async function load() {
  loading.value = true;
  try {
    const data = await listSubjects();
    subjects.value = data.items || [];
    appStore.subjects = subjects.value;
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function typeLabel(t) {
  return { course: '课程', tech: '技术', paper: '论文', topic: '专题' }[t] || t;
}
function fmtMinutes(v) {
  if (v === null || v === undefined) return '0 分钟';
  const m = Number(v);
  return m >= 60 ? `${(m / 60).toFixed(1)}h` : `${m.toFixed(0)}min`;
}

function openCreate() {
  Object.assign(form, { name: '', subject_type: 'course', description: '', learning_goal: '' });
  dialog.isEdit = false;
  dialog.visible = true;
}
function openEdit(s) {
  Object.assign(form, {
    name: s.name,
    subject_type: s.subject_type,
    description: s.description,
    learning_goal: s.learning_goal,
  });
  dialog.isEdit = true;
  dialog.editId = s.id;
  dialog.visible = true;
}

async function save() {
  await formRef.value.validate();
  dialog.loading = true;
  try {
    const payload = {
      name: form.name,
      subject_type: form.subject_type,
      description: form.description,
      learning_goal: form.learning_goal,
    };
    if (dialog.isEdit) {
      await patchSubject(dialog.editId, payload);
      ElMessage.success('已更新');
    } else {
      await createSubject(payload);
      ElMessage.success('已创建');
    }
    dialog.visible = false;
    await load();
  } finally {
    dialog.loading = false;
  }
}

async function archive(s) {
  await ElMessageBox.confirm(`归档「${s.name}」？归档后不会出现在列表中。`, '提示', { type: 'warning' });
  await deleteSubject(s.id);
  ElMessage.success('已归档');
  await load();
}
</script>

<style scoped>
.subject-card {
  border: 1px solid #e6ecea;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  background: #fff;
}
.subject-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.subject-name {
  font-size: 16px;
  font-weight: 600;
  color: #16302a;
}
.subject-desc {
  margin: 10px 0;
  min-height: 40px;
  font-size: 13px;
  color: #6b7f78;
  line-height: 1.6;
}
.subject-meta {
  display: flex;
  gap: 14px;
  margin: 10px 0;
  font-size: 12px;
  color: #8ba099;
}
.subject-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
