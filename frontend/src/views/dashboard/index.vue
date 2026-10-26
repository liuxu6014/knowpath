<template>
  <div>
    <div class="page-intro">
      <h2>学习总览</h2>
      <p>汇总你的测评、练习与学习时长，帮助你了解整体进度。</p>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <template v-else>
      <div class="stat-grid">
        <div class="stat-block">
          <div class="stat-value">{{ summary.total_attempts ?? 0 }}</div>
          <div class="stat-label">学习记录</div>
        </div>
        <div class="stat-block">
          <div class="stat-value">{{ fmtPercent(summary.average_score) }}</div>
          <div class="stat-label">平均得分</div>
        </div>
        <div class="stat-block">
          <div class="stat-value">{{ fmtPercent(summary.accuracy) }}</div>
          <div class="stat-label">答题正确率</div>
        </div>
        <div class="stat-block">
          <div class="stat-value">{{ fmtPercent(summary.mastery_score) }}</div>
          <div class="stat-label">掌握度</div>
        </div>
        <div class="stat-block">
          <div class="stat-value">{{ fmtMinutes(summary.study_minutes) }}</div>
          <div class="stat-label">学习时长</div>
        </div>
      </div>

      <div class="kp-grid">
        <div class="kp-card">
          <h3 class="kp-card-title">学习对象</h3>
          <el-empty v-if="!subjects.length" description="还没有学习对象" />
          <el-table v-else :data="subjects" size="small">
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="进度" min-width="160">
              <template #default="{ row }">
                <el-progress :percentage="Math.round((row.progress || 0) * 100)" :stroke-width="8" />
              </template>
            </el-table-column>
            <el-table-column prop="concept_count" label="知识点" width="90" />
            <el-table-column prop="resource_count" label="资料" width="80" />
          </el-table>
        </div>

        <div class="kp-card">
          <h3 class="kp-card-title">薄弱知识点</h3>
          <el-empty v-if="!summary.weak_points?.length" description="暂无薄弱点，继续保持" />
          <div v-else class="weak-list">
            <div v-for="(w, i) in summary.weak_points" :key="i" class="weak-item">
              <span class="weak-name">{{ w.name || '未关联概念' }}</span>
              <el-tag size="small" type="danger">{{ w.mistakes }} 次错误</el-tag>
            </div>
          </div>
        </div>
      </div>

      <div class="kp-card">
        <h3 class="kp-card-title">学习建议</h3>
        <ul v-if="summary.suggestions?.length" class="suggestion-list">
          <li v-for="(s, i) in summary.suggestions" :key="i">
            <template v-if="s.name"><strong>{{ s.name }}</strong>：</template>{{ s.text }}
          </li>
        </ul>
        <el-empty v-else description="完成一次测评后，将为你生成学习建议" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { getDashboard, listSubjects } from '@/api';

const loading = ref(true);
const summary = ref({});
const subjects = ref([]);

onMounted(async () => {
  try {
    const [dash, subs] = await Promise.all([getDashboard(), listSubjects()]);
    summary.value = dash || {};
    subjects.value = subs?.items || [];
  } finally {
    loading.value = false;
  }
});

function fmtPercent(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  return Number.isInteger(n) ? `${n}%` : `${n.toFixed(1)}%`;
}
function fmtMinutes(v) {
  if (v === null || v === undefined) return '—';
  const m = Number(v);
  if (m >= 60) return `${(m / 60).toFixed(1)} 小时`;
  return `${m.toFixed(0)} 分钟`;
}
</script>

<style scoped>
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
.suggestion-list {
  margin: 0;
  padding-left: 18px;
  color: #455d55;
  line-height: 1.9;
}
</style>
