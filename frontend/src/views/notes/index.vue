<template>
  <div>
    <div class="page-intro">
      <div>
        <h2>我的笔记</h2>
        <p>记录学习过程中的心得，可关联到具体知识点。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建笔记</el-button>
    </div>

    <div class="note-toolbar">
      <el-input v-model="query" placeholder="搜索笔记标题或内容" clearable style="max-width: 320px" @input="load" />
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />
    <el-empty v-else-if="!notes.length" description="还没有笔记" />

    <div v-else class="note-grid">
      <div v-for="n in notes" :key="n.id" class="note-card" @click="openEdit(n)">
        <div class="note-title">{{ n.title }}</div>
        <div class="note-content">{{ n.content }}</div>
        <div class="note-meta">
          <span v-if="n.subject_name">{{ n.subject_name }}</span>
          <span v-if="n.concept_name">· {{ n.concept_name }}</span>
          <span class="note-time">{{ fmtTime(n.updated_at) }}</span>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑笔记' : '新建笔记'" width="560px">
      <el-form ref="formRef" :model="form" label-position="top">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="笔记标题" />
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="8" placeholder="写下你的学习心得…" />
        </el-form-item>
        <el-form-item label="关联学习对象（选填）" prop="subject_id">
          <el-select v-model="form.subject_id" clearable placeholder="选择学习对象" style="width: 100%">
            <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
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
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import { listNotes, createNote, patchNote, listSubjects } from '@/api';

const loading = ref(true);
const notes = ref([]);
const subjects = ref([]);
const query = ref('');
const formRef = ref();

const dialog = reactive({ visible: false, isEdit: false, loading: false });
const form = reactive({ id: null, title: '', content: '', subject_id: null });

async function load() {
  loading.value = true;
  try {
    const data = await listNotes({ q: query.value || undefined });
    notes.value = data.items || [];
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  const [noteData, subData] = await Promise.all([listNotes(), listSubjects()]);
  notes.value = noteData.items || [];
  subjects.value = subData.items || [];
  loading.value = false;
});

function openCreate() {
  Object.assign(form, { id: null, title: '', content: '', subject_id: null });
  dialog.isEdit = false;
  dialog.visible = true;
}

function openEdit(n) {
  Object.assign(form, { id: n.id, title: n.title, content: n.content, subject_id: n.subject_id });
  dialog.isEdit = true;
  dialog.visible = true;
}

async function save() {
  if (!form.title.trim()) {
    ElMessage.warning('请输入标题');
    return;
  }
  dialog.loading = true;
  try {
    const payload = { title: form.title, content: form.content, subject_id: form.subject_id };
    if (dialog.isEdit) {
      await patchNote({ ...payload, id: form.id });
      ElMessage.success('已更新');
    } else {
      await createNote(payload);
      ElMessage.success('已创建');
    }
    dialog.visible = false;
    await load();
  } finally {
    dialog.loading = false;
  }
}

function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : '';
}
</script>

<style scoped>
.note-toolbar {
  margin-bottom: 16px;
}
.note-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.note-card {
  border: 1px solid #e6ecea;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
  cursor: pointer;
  transition: transform 0.12s, box-shadow 0.12s;
}
.note-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(18, 62, 52, 0.08);
}
.note-title {
  font-weight: 600;
  color: #16302a;
  margin-bottom: 8px;
}
.note-content {
  color: #6b7f78;
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.note-meta {
  margin-top: 12px;
  display: flex;
  gap: 6px;
  font-size: 12px;
  color: #8ba099;
  flex-wrap: wrap;
}
.note-time {
  margin-left: auto;
}
</style>
