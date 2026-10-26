<template>
  <div>
    <div class="page-intro">
      <h2>能力画像</h2>
      <p>查看各知识点的掌握度与答题表现，定位薄弱环节。</p>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <el-skeleton v-else-if="loading" :rows="8" animated />

    <template v-else>
      <div class="stat-grid">
        <div class="stat-block"><div class="stat-value">{{ fmtPct(summary.mastery_score) }}</div><div class="stat-label">总体掌握度</div></div>
        <div class="stat-block"><div class="stat-value">{{ fmtPct(summary.accuracy) }}</div><div class="stat-label">正确率</div></div>
        <div class="stat-block"><div class="stat-value">{{ fmtPct(summary.average_score) }}</div><div class="stat-label">平均得分</div></div>
        <div class="stat-block"><div class="stat-value">{{ summary.total_attempts ?? 0 }}</div><div class="stat-label">测评次数</div></div>
        <div class="stat-block"><div class="stat-value">{{ fmtMinutes(summary.study_minutes) }}</div><div class="stat-label">学习时长</div></div>
      </div>

      <div class="kp-card">
        <h3 class="kp-card-title">知识点掌握度</h3>
        <el-empty v-if="!masteryItems.length" description="暂无掌握度数据，先完成一次测评" />
        <div v-else class="mastery-list">
          <div v-for="m in masteryItems" :key="m.concept_id" class="mastery-item">
            <div class="mastery-head">
              <span class="mastery-name">{{ m.name }}</span>
              <el-tag size="small" :type="masteryTag(m)" effect="plain">{{ masteryLabel(m) }}</el-tag>
            </div>
            <el-progress :percentage="Math.round(m.mastery || 0)" :stroke-width="10" :color="masteryColor(m)" />
          </div>
        </div>
      </div>

      <div class="kp-card">
        <h3 class="kp-card-title">薄弱知识点</h3>
        <el-empty v-if="!summary.weak_points?.length" description="暂无薄弱点" />
        <div v-else class="weak-list">
          <div v-for="(w, i) in summary.weak_points" :key="i" class="weak-item">
            <span class="weak-name">{{ w.name || '未关联概念' }}</span>
            <el-tag size="small" type="danger">{{ w.mistakes }} 次错误</el-tag>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { getAnalytics, getMastery, listSubjects } from '@/api';
import { useAppStore } from '@/store/app';

const appStore = useAppStore();
const loading = ref(true);
const summary = ref({});
const masteryItems = ref([]);

const subjectId = computed(() => appStore.currentSubjectId);

onMounted(async () => {
  if (!appStore.subjects.length) {
    const data = await listSubjects();
    appStore.subjects = data.items || [];
  }
  if (!appStore.currentSubjectId && appStore.subjects.length) appStore.setCurrentSubject(appStore.subjects[0].id);
  await load();
});

async function load() {
  if (!subjectId.value) return;
  loading.value = true;
  try {
    const [analytics, mastery] = await Promise.all([
      getAnalytics(subjectId.value),
      getMastery(subjectId.value),
    ]);
    summary.value = analytics || {};
    masteryItems.value = mastery.items || [];
  } finally {
    loading.value = false;
  }
}

function fmtPct(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  return Number.isInteger(n) ? `${n}%` : `${n.toFixed(1)}%`;
}
function fmtMinutes(v) {
  if (v === null || v === undefined) return '—';
  const m = Number(v);
  return m >= 60 ? `${(m / 60).toFixed(1)}h` : `${m.toFixed(0)}min`;
}
function masteryTag(m) {
  const s = m.status;
  return { mastered: 'success', learning: 'warning', weak: 'danger', unknown: 'info' }[s] || 'info';
}
function masteryLabel(m) {
  return { mastered: '已掌握', learning: '学习中', weak: '薄弱', unknown: '未测评' }[m.status] || m.status;
}
function masteryColor(m) {
  const score = m.mastery || 0;
  if (score >= 80) return '#2e9d7e';
  if (score >= 60) return '#e6a23c';
  return '#f56c6c';
}
</script>

<style scoped>
.mastery-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.mastery-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.mastery-name {
  font-weight: 600;
  color: #16302a;
}
.weak-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.weak-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  background: #faf6f6;
}
.weak-name {
  font-size: 14px;
  color: #16302a;
}
</style>
