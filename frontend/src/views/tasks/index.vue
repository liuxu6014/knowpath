<template>
  <div>
    <div class="page-intro">
      <h2>任务中心</h2>
      <p>查看资料解析等后台任务的处理状态。</p>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />
    <el-empty v-else-if="!tasks.length" description="暂无任务" />

    <el-table v-else :data="tasks" size="default">
      <el-table-column prop="name" label="任务" min-width="220" />
      <el-table-column prop="kind" label="类型" width="120" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="180">
        <template #default="{ row }">
          <el-progress :percentage="row.progress || 0" :stroke-width="8" />
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button v-if="row.status === 'failed'" size="small" text type="primary" @click="retry(row)">重试</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { listTasks, retryTask } from '@/api';

const loading = ref(true);
const tasks = ref([]);

async function load() {
  loading.value = true;
  try {
    const data = await listTasks();
    tasks.value = data.items || [];
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function retry(row) {
  await retryTask(row.id);
  ElMessage.success('已重新触发任务');
  await load();
}

function statusType(status) {
  return { succeeded: 'success', failed: 'danger', running: 'warning' }[status] || 'info';
}
function statusLabel(status) {
  return { succeeded: '已完成', failed: '失败', running: '处理中' }[status] || status;
}
function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '';
}
</script>
