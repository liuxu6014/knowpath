<template>
  <div>
    <div class="page-intro">
      <h2>学习中心</h2>
      <p>按路径顺序学习当前知识点，查看讲解、示例与重点，并可随时向 AI 提问。</p>
    </div>

    <el-empty v-if="!subjectId" description="请先在顶部选择一个学习对象" />

    <template v-else>
      <div v-if="!currentNode && !loading" class="kp-card">
        <el-empty description="暂无当前学习节点，请先生成学习路径">
          <el-button type="primary" @click="goPath">去生成路径</el-button>
        </el-empty>
      </div>

      <template v-else>
        <div class="learning-head kp-card" v-if="currentNode">
          <div>
            <div class="learning-concept">{{ currentNode.title || currentNode.name }}</div>
            <div class="learning-meta">
              掌握度 {{ Math.round(currentNode.mastery || currentNode.mastery_percent || 0) }}% ·
              <el-tag size="small" effect="plain">{{ nodeLabel(currentNode) }}</el-tag>
            </div>
          </div>
          <el-button type="primary" :loading="completing" @click="complete">完成本节</el-button>
        </div>

        <div class="kp-grid learning-grid">
          <div class="kp-card">
            <el-skeleton v-if="lessonLoading" :rows="8" animated />
            <template v-else-if="lesson">
              <h3 class="kp-card-title">定义</h3>
              <p class="lesson-text">{{ lesson.definition }}</p>

              <template v-if="lesson.sections?.length">
                <h3 class="kp-card-title">讲解</h3>
                <div v-for="(s, i) in lesson.sections" :key="i" class="lesson-section">
                  <h4>{{ s.title }}</h4>
                  <p class="lesson-text">{{ s.markdown }}</p>
                </div>
              </template>

              <template v-if="lesson.examples?.length">
                <h3 class="kp-card-title">示例</h3>
                <ul class="lesson-list">
                  <li v-for="(e, i) in lesson.examples" :key="i">{{ e }}</li>
                </ul>
              </template>

              <template v-if="lesson.key_points?.length">
                <h3 class="kp-card-title">重点</h3>
                <ul class="lesson-list">
                  <li v-for="(k, i) in lesson.key_points" :key="i">{{ k }}</li>
                </ul>
              </template>

              <template v-if="lesson.check_questions?.length">
                <h3 class="kp-card-title">自测问题</h3>
                <ul class="lesson-list">
                  <li v-for="(q, i) in lesson.check_questions" :key="i">{{ q }}</li>
                </ul>
              </template>
            </template>
            <el-empty v-else description="暂无讲解内容" />
          </div>

          <div class="kp-card">
            <h3 class="kp-card-title">AI 答疑</h3>
            <div class="chat-box">
              <div v-for="(m, i) in chatMessages" :key="i" class="chat-msg" :class="m.role">
                <div class="chat-bubble">{{ m.content }}</div>
              </div>
              <el-empty v-if="!chatMessages.length" description="针对当前知识点提问" :image-size="60" />
            </div>
            <div class="chat-input">
              <el-input v-model="question" placeholder="例如：这个概念和前面的知识有什么关系？" @keyup.enter="ask" />
              <el-button type="primary" :loading="asking" @click="ask">发送</el-button>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { getNextNode, getConceptLesson, updatePathProgress, conceptChat, listSubjects } from '@/api';
import { useAppStore } from '@/store/app';

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const subjects = ref([]);
const loading = ref(true);
const lessonLoading = ref(false);
const completing = ref(false);
const asking = ref(false);
const pathData = ref(null);
const lesson = ref(null);
const question = ref('');
const chatMessages = ref([]);

const subjectId = computed(() => appStore.currentSubjectId);
const currentNode = computed(() => {
  const wanted = route.query.concept;
  if (wanted && pathData.value?.nodes) {
    return pathData.value.nodes.find((n) => String(n.concept_id) === String(wanted)) || null;
  }
  return pathData.value?.next || pathData.value?.current_node || null;
});

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
    pathData.value = await getNextNode(subjectId.value);
    await loadLesson();
  } finally {
    loading.value = false;
  }
}

async function loadLesson() {
  const node = currentNode.value;
  if (!node?.concept_id) return;
  lessonLoading.value = true;
  try {
    lesson.value = await getConceptLesson(node.concept_id);
  } finally {
    lessonLoading.value = false;
  }
}

async function complete() {
  const node = currentNode.value;
  if (!node || !pathData.value?.path_id) return;
  completing.value = true;
  try {
    await updatePathProgress(pathData.value.path_id, { node_id: node.concept_id ?? node.id, completed: true });
    ElMessage.success('已完成本节，进入下一个知识点');
    await load();
  } finally {
    completing.value = false;
  }
}

async function ask() {
  const node = currentNode.value;
  const text = question.value.trim();
  if (!node?.concept_id || !text) return;
  asking.value = true;
  chatMessages.value.push({ role: 'user', content: text });
  question.value = '';
  try {
    const data = await conceptChat(node.concept_id, { question: text });
    chatMessages.value.push({ role: 'assistant', content: data.answer || '（无回答）' });
  } catch (e) {
    chatMessages.value.push({ role: 'assistant', content: '暂时无法回答，请稍后再试。' });
  } finally {
    asking.value = false;
  }
}

function nodeLabel(n) {
  const s = n.state || n.status;
  return { completed: '已完成', current: '当前', pending: '待学习', blocked: '未解锁' }[s] || s;
}

function goPath() {
  router.push('/path');
}
</script>

<style scoped>
.learning-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.learning-concept {
  font-size: 20px;
  font-weight: 700;
  color: #16302a;
}
.learning-meta {
  margin-top: 6px;
  color: #6b7f78;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.learning-grid {
  grid-template-columns: 1.5fr 1fr;
  align-items: start;
}
.lesson-text {
  color: #455d55;
  line-height: 1.8;
  font-size: 14px;
}
.lesson-section h4 {
  margin: 16px 0 6px;
  color: #16302a;
}
.lesson-list {
  margin: 8px 0;
  padding-left: 18px;
  color: #455d55;
  line-height: 1.8;
}
.chat-box {
  height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}
.chat-msg {
  display: flex;
}
.chat-msg.user { justify-content: flex-end; }
.chat-bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  background: #f0f4f3;
  color: #16302a;
}
.chat-msg.user .chat-bubble {
  background: #1a5547;
  color: #fff;
}
.chat-input {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
@media (max-width: 900px) {
  .learning-grid { grid-template-columns: 1fr; }
}
</style>
