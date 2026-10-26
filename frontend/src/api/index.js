import request from './request';

/* ---------- auth ---------- */
export const login = (data) => request.post('/api/v1/auth/login/', data);
export const register = (data) => request.post('/api/v1/auth/register/', data);
export const logout = () => request.post('/api/v1/auth/logout/');
export const refresh = () => request.post('/api/v1/auth/refresh/');
export const getMe = () => request.get('/api/v1/me/');
export const patchMe = (data) => request.patch('/api/v1/me/', data);

/* ---------- dashboard ---------- */
export const getDashboard = () => request.get('/api/v1/dashboard/');

/* ---------- subjects ---------- */
export const listSubjects = (params) => request.get('/api/v1/subjects/', { params });
export const createSubject = (data) => request.post('/api/v1/subjects/', data);
export const getSubject = (id) => request.get(`/api/v1/subjects/${id}/`);
export const patchSubject = (id, data) => request.patch(`/api/v1/subjects/${id}/`, data);
export const deleteSubject = (id) => request.delete(`/api/v1/subjects/${id}/`);

/* ---------- resources ---------- */
export const listResources = (params) => request.get('/api/v1/resources/', { params });
export const createResource = (data) => request.post('/api/v1/resources/', data);
export const getResource = (id) => request.get(`/api/v1/resources/${id}/`);
export const listSubjectResources = (id) => request.get(`/api/v1/subjects/${id}/resources/`);
export const uploadSubjectResource = (id, data) => request.post(`/api/v1/subjects/${id}/resources/`, data);
export const parseResource = (id) => request.post(`/api/v1/resources/${id}/parse/`);
export const listResourceChunks = (id) => request.get(`/api/v1/resources/${id}/chunks/`);

/* ---------- knowledge graph ---------- */
export const getKnowledgeGraph = (id) => request.get(`/api/v1/subjects/${id}/knowledge/graph/`);
export const buildKnowledgeGraph = (id) => request.post(`/api/v1/subjects/${id}/knowledge/build/`);
export const getKnowledgeProfile = () => request.get('/api/v1/knowledge/profile/');
export const getConceptLesson = (id) => request.get(`/api/v1/concepts/${id}/lesson/`);
export const createConceptLesson = (id, data) => request.post(`/api/v1/concepts/${id}/lesson/`, data);
export const listKnowledgeSnapshots = () => request.get('/api/v1/knowledge/snapshots/');
export const createKnowledgeSnapshot = (data) => request.post('/api/v1/knowledge/snapshots/', data);
export const syncKnowledgeSnapshot = (id) => request.post(`/api/v1/knowledge/snapshots/${id}/sync/`);
export const validateKnowledge = (data) => request.post('/api/v1/knowledge/validate/', data);
export const createRelation = (data) => request.post('/api/v1/knowledge/relations/', data);
export const patchConcept = (id, data) => request.patch(`/api/v1/knowledge/concepts/${id}/`, data);
export const patchRelation = (id, data) => request.patch(`/api/v1/knowledge/relations/${id}/`, data);
export const deleteRelation = (id) => request.delete(`/api/v1/knowledge/relations/${id}/`);

/* ---------- paths ---------- */
export const listPaths = (params) => request.get('/api/v1/paths/', { params });
export const createPath = (data) => request.post('/api/v1/paths/', data);
export const getCurrentPath = (id) => request.get(`/api/v1/subjects/${id}/paths/current/`);
export const generatePath = (id) => request.post(`/api/v1/subjects/${id}/paths/generate/`);
export const updatePathProgress = (id, data) => request.post(`/api/v1/paths/${id}/progress/`, data);

/* ---------- assessment ---------- */
export const listAssessments = (params) => request.get('/api/v1/assessments/', { params });
export const createAssessment = (data) => request.post('/api/v1/assessments/', data);
export const getAssessment = (id) => request.get(`/api/v1/assessments/${id}/`);
export const startAssessment = (id) => request.post(`/api/v1/subjects/${id}/assessments/start/`);
export const submitAssessment = (id, data) => request.post(`/api/v1/assessments/${id}/submit/`, data);

/* ---------- mastery ---------- */
export const getMastery = (id) => request.get(`/api/v1/subjects/${id}/mastery/`);
export const getMasteryHistory = (id) => request.get(`/api/v1/subjects/${id}/mastery/history/`);

/* ---------- analytics ---------- */
export const getAnalytics = (id, params) => request.get(`/api/v1/subjects/${id}/analytics/`, { params });

/* ---------- wrong questions ---------- */
export const listWrongQuestions = () => request.get('/api/v1/wrong-questions/');
export const retryWrongQuestion = (id) => request.post(`/api/v1/wrong-questions/${id}/retry/`);

/* ---------- quizzes ---------- */
export const listQuizzes = (params) => request.get('/api/v1/quizzes/', { params });
export const createQuiz = (data) => request.post('/api/v1/quizzes/', data);
export const submitQuiz = (id, data) => request.post(`/api/v1/quizzes/${id}/submit/`, data);
export const generateConceptQuiz = (id) => request.post(`/api/v1/concepts/${id}/quiz/generate/`);

/* ---------- notes ---------- */
export const listNotes = (params) => request.get('/api/v1/notes/', { params });
export const createNote = (data) => request.post('/api/v1/notes/', data);
export const patchNote = (data) => request.patch('/api/v1/notes/', data);

/* ---------- tasks ---------- */
export const listTasks = (params) => request.get('/api/v1/tasks/', { params });
export const getTask = (id) => request.get(`/api/v1/tasks/${id}/`);
export const retryTask = (id) => request.post(`/api/v1/tasks/${id}/retry/`);

/* ---------- reports ---------- */
export const getReport = (id) => request.get(`/api/v1/subjects/${id}/report/`);
export const generateReport = (id) => request.post(`/api/v1/subjects/${id}/report/generate/`);

/* ---------- next / learning ---------- */
export const getNextNode = (id) => request.get(`/api/v1/subjects/${id}/next/`);

/* ---------- AI ---------- */
export const aiChat = (data) => request.post('/api/v1/ai/chat/', data);
export const conceptChat = (id, data) => request.post(`/api/v1/concepts/${id}/chat/`, data);
export const aiQuiz = (data) => request.post('/api/v1/ai/quiz/', data);
export const aiExtract = (data) => request.post('/api/v1/ai/extract/', data);

/* ---------- admin ---------- */
export const listAdminUsers = () => request.get('/api/v1/admin/users/');
export const listModelConfigs = () => request.get('/api/v1/admin/model-configs/');
export const createModelConfig = (data) => request.post('/api/v1/admin/model-configs/', data);
export const patchModelConfig = (id, data) => request.patch(`/api/v1/admin/model-configs/${id}/`, data);
export const listPrompts = () => request.get('/api/v1/admin/prompts/');
export const createPrompt = (data) => request.post('/api/v1/admin/prompts/', data);
export const patchPrompt = (id, data) => request.patch(`/api/v1/admin/prompts/${id}/`, data);
export const listAiLogs = () => request.get('/api/v1/admin/ai-logs/');
