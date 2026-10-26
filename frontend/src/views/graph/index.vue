<template>
  <div>
    <div class="page-intro">
      <div>
        <h2>知识图谱</h2>
        <p>由资料自动提取的知识点与前置关系，是生成学习路径的基础。</p>
      </div>
      <el-button type="primary" :loading="building" :icon="MagicStick" @click="build">
        从资料构建图谱
      </el-button>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <template v-else>
      <div v-if="stats" class="stat-grid">
        <div class="stat-block"><div class="stat-value">{{ stats.node_count }}</div><div class="stat-label">知识点</div></div>
        <div class="stat-block"><div class="stat-value">{{ stats.edge_count }}</div><div class="stat-label">关系</div></div>
        <div class="stat-block"><div class="stat-value">{{ stats.mastered_count + (stats.completed_count || 0) }}</div><div class="stat-label">已掌握</div></div>
        <div class="stat-block"><div class="stat-value">{{ stats.learning_count }}</div><div class="stat-label">学习中</div></div>
        <div class="stat-block"><div class="stat-value">{{ stats.locked_count }}</div><div class="stat-label">未解锁</div></div>
      </div>

      <el-skeleton v-if="loading" :rows="6" animated />
      <el-empty v-else-if="!nodes.length" description="图谱为空，请先上传资料并点击「从资料构建图谱」" />

      <div v-else class="kp-grid graph-grid">
        <div class="kp-card">
          <h3 class="kp-card-title">知识点</h3>
          <div class="node-grid">
            <div
              v-for="n in nodes"
              :key="n.id"
              class="node-card"
              :class="`node-${n.status}`"
              @click="openNode(n)"
            >
              <div class="node-name">{{ n.name }}</div>
              <div class="node-mastery">掌握度 {{ Math.round(n.mastery || 0) }}%</div>
              <el-tag size="small" :type="statusTag(n.status)" effect="plain">{{ statusLabel(n.status) }}</el-tag>
            </div>
          </div>
        </div>

        <div class="kp-card">
          <h3 class="kp-card-title">前置关系</h3>
          <el-empty v-if="!edges.length" description="暂无关系" />
          <el-table v-else :data="edgeRows" size="small">
            <el-table-column label="前置" min-width="120">
              <template #default="{ row }">{{ nodeName(row.from) }}</template>
            </el-table-column>
            <el-table-column label="关系" width="120">
              <template #default><el-tag size="small" type="info">前置于</el-tag></template>
            </el-table-column>
            <el-table-column label="后继" min-width="120">
              <template #default="{ row }">{{ nodeName(row.to) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </template>

    <el-dialog v-model="nodeDialog.visible" :title="nodeDialog.name" width="460px">
      <p class="node-desc">{{ nodeDialog.description || '暂无描述' }}</p>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="掌握度">{{ Math.round(nodeDialog.mastery || 0) }}%</el-descriptions-item>
        <el-descriptions-item label="状态">{{ statusLabel(nodeDialog.status) }}</el-descriptions-item>
        <el-descriptions-item label="前置">
          {{ (nodeDialog.prerequisite_concept_ids || []).map(nodeName).join('、') || '无' }}
        </el-descriptions-item>
        <el-descriptions-item label="后继">
          {{ (nodeDialog.dependent_concept_ids || []).map(nodeName).join('、') || '无' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { MagicStick } from '@element-plus/icons-vue';
import { getKnowledgeGraph, buildKnowledgeGraph, listSubjects } from '@/api';
import { useAppStore } from '@/store/app';

const appStore = useAppStore();
const loading = ref(true);
const building = ref(false);
const nodes = ref([]);
const edges = ref([]);
const stats = ref(null);
const subjects = ref([]);

const subjectId = computed(() => appStore.currentSubjectId);
const nodeDialog = reactive({ visible: false, name: '', description: '', mastery: 0, status: 'unknown', prerequisite_concept_ids: [], dependent_concept_ids: [] });

const nameMap = computed(() => {
  const map = {};
  for (const n of nodes.value) {
    for (const key of [n.id, n.concept_id, n.name]) {
      if (key !== null && key !== undefined) map[String(key)] = n.name;
    }
  }
  return map;
});
function nodeName(key) {
  if (key === null || key === undefined) return '';
  return nameMap.value[String(key)] || String(key);
}
const edgeRows = computed(() =>
  edges.value
    .filter((e) => e && typeof e === 'object')
    .map((e) => ({ from: e.from ?? e.source, to: e.to ?? e.target })),
);

async function ensureSubject() {
  if (!subjects.value.length) {
    const data = await listSubjects();
    subjects.value = data.items || [];
    appStore.subjects = subjects.value;
  }
  if (!appStore.currentSubjectId && subjects.value.length) {
    appStore.setCurrentSubject(subjects.value[0].id);
  }
}

async function load() {
  await ensureSubject();
  if (!subjectId.value) return;
  loading.value = true;
  try {
    const data = await getKnowledgeGraph(subjectId.value);
    nodes.value = data.nodes || [];
    edges.value = data.edges || [];
    stats.value = data.stats || null;
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function build() {
  building.value = true;
  try {
    const data = await buildKnowledgeGraph(subjectId.value);
    ElMessage.success(data?.created ? '图谱已构建' : (data?.warning || '图谱未变化'));
    await load();
  } finally {
    building.value = false;
  }
}

function statusTag(status) {
  return { mastered: 'success', completed: 'success', learning: 'warning', locked: 'info', unknown: 'info' }[status] || 'info';
}
function statusLabel(status) {
  return {
    mastered: '已掌握', completed: '已完成', learning: '学习中', locked: '未解锁', unknown: '未测评',
  }[status] || status;
}

function openNode(n) {
  Object.assign(nodeDialog, {
    visible: true,
    name: n.name,
    description: n.description,
    mastery: n.mastery,
    status: n.status,
    prerequisite_concept_ids: n.prerequisite_concept_ids || [],
    dependent_concept_ids: n.dependent_concept_ids || [],
  });
}
</script>

<style scoped>
.graph-grid {
  grid-template-columns: 1fr 1fr;
  align-items: start;
}
.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.node-card {
  border: 1px solid #e6ecea;
  border-left: 4px solid #cbd7d3;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  background: #fff;
  transition: transform 0.12s, box-shadow 0.12s;
}
.node-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(18, 62, 52, 0.08);
}
.node-card.node-mastered, .node-card.node-completed { border-left-color: #2e9d7e; }
.node-card.node-learning { border-left-color: #e6a23c; }
.node-card.node-locked { border-left-color: #cbd7d3; opacity: 0.75; }
.node-name {
  font-size: 14px;
  font-weight: 600;
  color: #16302a;
  margin-bottom: 6px;
}
.node-mastery {
  font-size: 12px;
  color: #6b7f78;
  margin-bottom: 8px;
}
.node-desc {
  color: #455d55;
  line-height: 1.7;
  margin: 0 0 14px;
}
@media (max-width: 900px) {
  .graph-grid { grid-template-columns: 1fr; }
}
</style>
