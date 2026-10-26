<template>
  <div>
    <div class="page-intro">
      <h2>练习与错题</h2>
      <p>针对知识点生成练习题，或复习答错的题目，巩固掌握度。</p>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <el-tabs v-else v-model="tab">
      <!-- 练习测验 -->
      <el-tab-pane label="练习测验" name="quiz">
        <div class="kp-card">
          <div class="quiz-gen">
            <span>针对知识点：</span>
            <el-select v-model="quizConceptId" placeholder="选择知识点" style="width: 260px">
              <el-option v-for="c in concepts" :key="c.concept_id" :label="c.name" :value="c.concept_id" />
            </el-select>
            <el-button type="primary" :loading="generating" @click="generateQuiz">生成练习题</el-button>
          </div>
        </div>

        <!-- 历史练习 -->
        <div class="kp-card">
          <h3 class="kp-card-title">历史练习</h3>
          <el-empty v-if="!quizzes.length" description="还没有练习记录" />
          <el-table v-else :data="quizzes" size="small">
            <el-table-column prop="title" label="标题" min-width="180" />
            <el-table-column prop="question_count" label="题量" width="90" />
            <el-table-column label="创建时间" width="180">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 错题本 -->
      <el-tab-pane label="错题本" name="wrong">
        <div class="kp-card">
          <el-empty v-if="!wrongs.length" description="暂无错题，继续保持" />
          <el-table v-else :data="wrongs" size="small">
            <el-table-column prop="question" label="题目" min-width="220" show-overflow-tooltip />
            <el-table-column label="你的答案" width="130">
              <template #default="{ row }">{{ row.answer }}</template>
            </el-table-column>
            <el-table-column label="正确答案" width="130">
              <template #default="{ row }">{{ row.expected_answer }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="retry(row)">重做</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 答题弹层 -->
    <el-dialog v-model="runner.visible" :title="runner.title" width="680px" :close-on-click-modal="false">
      <div v-if="runner.result">
        <div class="result-score">
          <el-progress type="dashboard" :percentage="Math.round(runner.result.score)" :width="140">
            <template #default>
              <div class="result-value">{{ runner.result.score }}</div>
              <div class="result-sub">{{ runner.result.correct }} / {{ runner.result.total }}</div>
            </template>
          </el-progress>
        </div>
        <div class="quiz-actions">
          <el-button type="primary" @click="closeRunner">完成</el-button>
        </div>
      </div>
      <template v-else>
        <div v-for="(q, i) in runner.questions" :key="q.id" class="quiz-question">
          <div class="quiz-stem">{{ i + 1 }}. {{ q.question }}</div>
          <el-radio-group v-model="runner.answers[q.id]" class="quiz-options">
            <el-radio v-for="(opt, j) in q.options" :key="j" :value="opt" border>{{ opt }}</el-radio>
          </el-radio-group>
        </div>
        <div class="quiz-actions">
          <el-button @click="closeRunner">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitRunner">提交</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import {
  listQuizzes, listWrongQuestions, retryWrongQuestion, generateConceptQuiz,
  submitQuiz, submitAssessment, getMastery, listSubjects,
} from '@/api';
import { useAppStore } from '@/store/app';

const appStore = useAppStore();
const tab = ref('quiz');
const quizzes = ref([]);
const wrongs = ref([]);
const concepts = ref([]);
const quizConceptId = ref(null);
const generating = ref(false);
const submitting = ref(false);

const subjectId = computed(() => appStore.currentSubjectId);
const runner = reactive({
  visible: false,
  title: '',
  submitId: null,
  submitKind: 'quiz',
  questions: [],
  answers: {},
  result: null,
});

onMounted(async () => {
  if (!appStore.subjects.length) {
    const data = await listSubjects();
    appStore.subjects = data.items || [];
  }
  if (!appStore.currentSubjectId && appStore.subjects.length) appStore.setCurrentSubject(appStore.subjects[0].id);
  await loadAll();
});

async function loadAll() {
  if (!subjectId.value) return;
  const [quizData, wrongData, masteryData] = await Promise.all([
    listQuizzes(),
    listWrongQuestions(),
    getMastery(subjectId.value),
  ]);
  quizzes.value = quizData.items || [];
  wrongs.value = wrongData.items || [];
  concepts.value = masteryData.items || [];
  if (!quizConceptId.value && concepts.value.length) quizConceptId.value = concepts.value[0].concept_id;
}

async function generateQuiz() {
  if (!quizConceptId.value) {
    ElMessage.warning('请先选择知识点');
    return;
  }
  generating.value = true;
  try {
    const data = await generateConceptQuiz(quizConceptId.value, { count: 5 });
    openRunner(data.questions || [], data.id, 'quiz', '知识点练习');
  } finally {
    generating.value = false;
  }
}

async function retry(row) {
  const data = await retryWrongQuestion(row.attempt_id);
  openRunner(data.questions || [], data.assessment_id ?? data.id, 'assessment', '错题重做');
}

function openRunner(questions, id, kind, title) {
  runner.questions = questions;
  runner.submitId = id;
  runner.submitKind = kind;
  runner.title = title;
  runner.answers = {};
  runner.result = null;
  runner.visible = true;
}

function closeRunner() {
  runner.visible = false;
  loadAll();
}

async function submitRunner() {
  if (Object.keys(runner.answers).length < runner.questions.length) {
    ElMessage.warning('请完成所有题目');
    return;
  }
  submitting.value = true;
  try {
    const payload = { answers: { ...runner.answers } };
    runner.result = runner.submitKind === 'quiz'
      ? await submitQuiz(runner.submitId, payload)
      : await submitAssessment(runner.submitId, payload);
  } finally {
    submitting.value = false;
  }
}

function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '';
}
</script>

<style scoped>
.quiz-gen {
  display: flex;
  align-items: center;
  gap: 12px;
}
.quiz-question {
  padding: 14px 0;
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
  margin-top: 20px;
}
.result-score {
  display: flex;
  justify-content: center;
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
