<template>
  <div>
    <div class="page-intro">
      <div>
        <h2>我的路径</h2>
        <p>按掌握度与前置关系生成的学习顺序，从薄弱点逐步突破。</p>
      </div>
      <div class="path-actions">
        <el-button :loading="generating" @click="generate">重新生成路径</el-button>
      </div>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <el-skeleton v-else-if="loading" :rows="6" animated />

    <el-empty v-else-if="!path" description="还没有学习路径">
      <el-button type="primary" :loading="generating" @click="generate">生成学习路径</el-button>
    </el-empty>

    <template v-else>
      <div class="kp-card">
        <div class="path-header">
          <div>
            <div class="path-title">{{ path.title }}</div>
            <div class="path-sub">已完成 {{ path.completed }} / {{ path.total }} 个知识点</div>
          </div>
          <el-progress type="circle" :percentage="Math.round((path.progress || 0) * 100)" :width="80" />
        </div>
      </div>

      <div class="kp-card">
        <div class="timeline">
          <div v-for="n in path.nodes" :key="n.id" class="timeline-item" :class="`state-${n.state || n.status}`">
            <div class="timeline-dot" />
            <div class="timeline-body">
              <div class="timeline-head">
                <span class="timeline-name">{{ n.title || n.name }}</span>
                <el-tag size="small" :type="nodeTag(n)">{{ nodeLabel(n) }}</el-tag>
              </div>
              <div class="timeline-desc">{{ n.description || '暂无描述' }}</div>
              <div class="timeline-mastery">掌握度 {{ Math.round(n.mastery || n.mastery_percent || 0) }}%</div>
              <div v-if="(n.state === 'current' || n.status === 'current' || n.status === 'pending') && !n.completed" class="timeline-actions">
                <el-button size="small" type="primary" :loading="completingId === n.id" @click="complete(n)">
                  标记完成
                </el-button>
                <el-button size="small" @click="goLearning(n)">去学习</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getCurrentPath, generatePath, updatePathProgress, listSubjects } from '@/api';
import { useAppStore } from '@/store/app';

const router = useRouter();
const appStore = useAppStore();
const loading = ref(true);
const generating = ref(false);
const completingId = ref(null);
const path = ref(null);
const subjects = ref([]);

const subjectId = computed(() => appStore.currentSubjectId);

onMounted(async () => {
  if (!subjects.value.length) {
    const data = await listSubjects();
    subjects.value = data.items || [];
    appStore.subjects = subjects.value;
  }
  if (!appStore.currentSubjectId && subjects.value.length) appStore.setCurrentSubject(subjects.value[0].id);
  await load();
});

async function load() {
  if (!subjectId.value) return;
  loading.value = true;
  try {
    const data = await getCurrentPath(subjectId.value);
    path.value = data.path || null;
  } finally {
    loading.value = false;
  }
}

async function generate() {
  generating.value = true;
  try {
    await generatePath(subjectId.value, {});
    ElMessage.success('路径已生成');
    await load();
  } finally {
    generating.value = false;
  }
}

async function complete(n) {
  completingId.value = n.id;
  try {
    await updatePathProgress(path.value.id, { node_id: n.concept_id ?? n.id, completed: true });
    ElMessage.success('已标记完成');
    await load();
  } finally {
    completingId.value = null;
  }
}

function nodeTag(n) {
  const s = n.state || n.status;
  return { completed: 'success', current: 'warning', pending: 'primary', blocked: 'info' }[s] || 'info';
}
function nodeLabel(n) {
  const s = n.state || n.status;
  return {
    completed: '已完成', current: '当前', pending: '待学习', blocked: '未解锁',
  }[s] || s;
}

function goLearning(n) {
  router.push({ path: '/learning', query: { concept: n.concept_id } });
}
</script>

<style scoped>
.path-actions {
  display: flex;
  gap: 8px;
}
.path-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.path-title {
  font-size: 18px;
  font-weight: 600;
  color: #16302a;
}
.path-sub {
  color: #6b7f78;
  font-size: 13px;
  margin-top: 4px;
}
.timeline {
  position: relative;
  padding-left: 8px;
}
.timeline-item {
  position: relative;
  display: flex;
  gap: 16px;
  padding-bottom: 20px;
}
.timeline-item::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 16px;
  bottom: 0;
  width: 2px;
  background: #e6ecea;
}
.timeline-item:last-child::before {
  display: none;
}
.timeline-dot {
  position: relative;
  z-index: 1;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #cbd7d3;
  margin-top: 4px;
  flex-shrink: 0;
}
.state-completed .timeline-dot { background: #2e9d7e; }
.state-current .timeline-dot { background: #e6a23c; box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.2); }
.state-pending .timeline-dot { background: #1a5547; }
.state-blocked .timeline-dot { background: #cbd7d3; }
.timeline-body {
  flex: 1;
  background: #fafcfb;
  border: 1px solid #eef3f1;
  border-radius: 10px;
  padding: 14px 16px;
}
.state-current .timeline-body {
  border-color: #f0d49a;
  background: #fffaf0;
}
.timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.timeline-name {
  font-weight: 600;
  color: #16302a;
}
.timeline-desc {
  color: #6b7f78;
  font-size: 13px;
  margin: 6px 0;
  line-height: 1.6;
}
.timeline-mastery {
  font-size: 12px;
  color: #8ba099;
}
.timeline-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
</style>
