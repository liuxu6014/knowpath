<template>
  <div>
    <div class="page-intro">
      <div>
        <h2>学习报告</h2>
        <p>生成并保存阶段性的学习分析报告。</p>
      </div>
      <el-button type="primary" :loading="generating" @click="generate">生成新报告</el-button>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <el-skeleton v-else-if="loading" :rows="6" animated />

    <el-empty v-else-if="!report" description="还没有学习报告，点击右上角生成">
      <el-button type="primary" @click="generate">生成第一份报告</el-button>
    </el-empty>

    <template v-else>
      <div class="kp-card report-head">
        <div>
          <div class="report-title">学习报告 v{{ report.version }}</div>
          <div class="report-time">生成于 {{ fmtTime(report.created_at) }}</div>
        </div>
        <el-tag type="success" size="large">已保存</el-tag>
      </div>

      <div class="stat-grid">
        <div class="stat-block"><div class="stat-value">{{ fmtPct(data.mastery_score) }}</div><div class="stat-label">掌握度</div></div>
        <div class="stat-block"><div class="stat-value">{{ fmtPct(data.accuracy) }}</div><div class="stat-label">正确率</div></div>
        <div class="stat-block"><div class="stat-value">{{ data.answer_count ?? 0 }}</div><div class="stat-label">答题数</div></div>
        <div class="stat-block"><div class="stat-value">{{ fmtPct(data.path_progress) }}</div><div class="stat-label">路径进度</div></div>
        <div class="stat-block"><div class="stat-value">{{ fmtMinutes(data.study_minutes) }}</div><div class="stat-label">学习时长</div></div>
      </div>

      <div class="kp-card">
        <h3 class="kp-card-title">报告摘要</h3>
        <p class="report-summary">{{ data.summary }}</p>
      </div>

      <div class="kp-grid">
        <div class="kp-card">
          <h3 class="kp-card-title">薄弱知识点</h3>
          <el-empty v-if="!data.weak_points?.length" description="暂无薄弱点" />
          <div v-else class="weak-list">
            <div v-for="(w, i) in data.weak_points" :key="i" class="weak-item">
              <span>{{ w.name || '未关联概念' }}</span>
              <el-tag size="small" type="danger">{{ w.mistakes }} 次错误</el-tag>
            </div>
          </div>
        </div>
        <div class="kp-card">
          <h3 class="kp-card-title">学习建议</h3>
          <ul v-if="data.suggestions?.length" class="suggestion-list">
            <li v-for="(s, i) in data.suggestions" :key="i">
              <template v-if="s.name"><strong>{{ s.name }}</strong>：</template>{{ s.text }}
            </li>
          </ul>
          <el-empty v-else description="暂无建议" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getReport, generateReport, listSubjects } from '@/api';
import { useAppStore } from '@/store/app';

const appStore = useAppStore();
const loading = ref(true);
const generating = ref(false);
const report = ref(null);
const data = ref({});

const subjectId = computed(() => appStore.currentSubjectId);

onMounted(async () => {
  if (!appStore.subjects.length) {
    const subs = await listSubjects();
    appStore.subjects = subs.items || [];
  }
  if (!appStore.currentSubjectId && appStore.subjects.length) appStore.setCurrentSubject(appStore.subjects[0].id);
  await load();
});

async function load() {
  if (!subjectId.value) return;
  loading.value = true;
  try {
    try {
      report.value = await getReport(subjectId.value);
      data.value = report.value.data || {};
    } catch (e) {
      report.value = null;
      data.value = {};
    }
  } finally {
    loading.value = false;
  }
}

async function generate() {
  generating.value = true;
  try {
    report.value = await generateReport(subjectId.value);
    data.value = report.value.data || {};
    ElMessage.success('报告已生成');
  } finally {
    generating.value = false;
  }
}

function fmtPct(v) {
  if (v === null || v === undefined) return '—';
  return `${Math.round(Number(v) * 100)}%`;
}
function fmtMinutes(v) {
  if (v === null || v === undefined) return '—';
  const m = Number(v);
  return m >= 60 ? `${(m / 60).toFixed(1)}h` : `${m.toFixed(0)}min`;
}
function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '';
}
</script>

<style scoped>
.report-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.report-title {
  font-size: 18px;
  font-weight: 700;
  color: #16302a;
}
.report-time {
  color: #6b7f78;
  font-size: 13px;
  margin-top: 4px;
}
.report-summary {
  color: #455d55;
  line-height: 1.8;
  font-size: 14px;
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
.suggestion-list {
  margin: 0;
  padding-left: 18px;
  color: #455d55;
  line-height: 1.9;
}
</style>
