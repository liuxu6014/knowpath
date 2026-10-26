<template>
  <div>
    <div class="page-intro">
      <h2>起点测评</h2>
      <p>通过一组诊断题评估你对各知识点的掌握度，测评结果会驱动个性化学习路径。</p>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <template v-else>
      <!-- 开始测评 -->
      <div v-if="!questions.length && !result" class="kp-card assessment-start">
        <p>准备对「{{ subjectName }}」进行起点测评，共 {{ questionCount }} 道题。</p>
        <div class="start-row">
          <span>题量</span>
          <el-slider v-model="questionCount" :min="5" :max="30" :step="5" style="width: 240px" />
          <el-button type="primary" :loading="starting" @click="start">开始测评</el-button>
        </div>
      </div>

      <!-- 答题 -->
      <div v-if="questions.length && !result" class="kp-card">
        <div class="quiz-head">
          <h3 class="kp-card-title">{{ assessmentTitle }}</h3>
          <span>已答 {{ answeredCount }} / {{ questions.length }}</span>
        </div>
        <div v-for="(q, i) in questions" :key="q.id" class="quiz-question">
          <div class="quiz-stem">{{ i + 1 }}. {{ q.question }}</div>
          <el-radio-group v-model="answers[q.id]" class="quiz-options">
            <el-radio v-for="(opt, j) in q.options" :key="j" :value="opt" border size="large">
              {{ opt }}
            </el-radio>
          </el-radio-group>
        </div>
        <div class="quiz-actions">
          <el-button type="primary" size="large" :loading="submitting" :disabled="answeredCount < questions.length" @click="submit">
            提交测评
          </el-button>
        </div>
      </div>

      <!-- 结果 -->
      <div v-if="result" class="kp-card">
        <h3 class="kp-card-title">测评结果</h3>
        <div class="result-score">
          <el-progress type="dashboard" :percentage="Math.round(result.score)" :width="150">
            <template #default>
              <div class="result-value">{{ result.score }}</div>
              <div class="result-sub">{{ result.correct }} / {{ result.total }} 正确</div>
            </template>
          </el-progress>
        </div>
        <el-table :data="result.details || []" size="small" style="margin-top: 16px">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="question_id" label="题号" width="110" />
          <el-table-column label="你的答案" min-width="120">
            <template #default="{ row }">{{ row.answer }}</template>
          </el-table-column>
          <el-table-column label="正确答案" min-width="120">
            <template #default="{ row }">{{ row.expected_answer }}</template>
          </el-table-column>
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag :type="row.correct ? 'success' : 'danger'" size="small">{{ row.correct ? '正确' : '错误' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div class="quiz-actions">
          <el-button type="primary" @click="reset">再次测评</el-button>
          <el-button @click="goPath">查看学习路径</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { startAssessment, submitAssessment, listSubjects } from '@/api';
import { useAppStore } from '@/store/app';

const router = useRouter();
const appStore = useAppStore();
const subjects = ref([]);
const questionCount = ref(10);
const starting = ref(false);
const submitting = ref(false);
const questions = ref([]);
const answers = ref({});
const assessmentId = ref(null);
const assessmentTitle = ref('');
const result = ref(null);

const subjectId = computed(() => appStore.currentSubjectId);
const subjectName = computed(() => appStore.currentSubject?.name || '');
const answeredCount = computed(() => Object.keys(answers.value).filter((k) => answers.value[k]).length);

onMounted(async () => {
  if (!subjects.value.length) {
    const data = await listSubjects();
    subjects.value = data.items || [];
    appStore.subjects = subjects.value;
  }
  if (!appStore.currentSubjectId && subjects.value.length) appStore.setCurrentSubject(subjects.value[0].id);
});

async function start() {
  starting.value = true;
  try {
    const data = await startAssessment(subjectId.value, { question_count: questionCount.value });
    questions.value = data.questions || [];
    assessmentId.value = data.assessment_id ?? data.id;
    assessmentTitle.value = data.title || '起点测评';
    answers.value = {};
    result.value = null;
  } finally {
    starting.value = false;
  }
}

async function submit() {
  if (answeredCount.value < questions.value.length) {
    ElMessage.warning('请完成所有题目');
    return;
  }
  submitting.value = true;
  try {
    result.value = await submitAssessment(assessmentId.value, { answers: { ...answers.value } });
  } finally {
    submitting.value = false;
  }
}

function reset() {
  questions.value = [];
  answers.value = {};
  result.value = null;
}

function goPath() {
  router.push('/path');
}
</script>

<style scoped>
.assessment-start {
  padding: 28px;
  text-align: center;
}
.assessment-start p {
  color: #455d55;
  margin-bottom: 20px;
}
.start-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.quiz-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #6b7f78;
  font-size: 13px;
  margin-bottom: 8px;
}
.quiz-question {
  padding: 18px 0;
  border-bottom: 1px solid #f0f4f3;
}
.quiz-stem {
  font-size: 15px;
  font-weight: 500;
  color: #16302a;
  margin-bottom: 12px;
  line-height: 1.6;
}
.quiz-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.quiz-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 24px;
}
.result-score {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}
.result-value {
  font-size: 30px;
  font-weight: 700;
  color: #16302a;
}
.result-sub {
  font-size: 12px;
  color: #6b7f78;
}
</style>
