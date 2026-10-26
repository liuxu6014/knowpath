import axios from 'axios';
import { ElMessage } from 'element-plus';

export const TOKEN_KEY = 'knowpath:token';

const service = axios.create({
  baseURL: import.meta.env.VITE_API_TARGET || '',
  timeout: 30000,
});

service.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

service.interceptors.response.use(
  (response) => {
    // KnowPath controllers return plain JSON payloads with real HTTP status.
    // RuoYi framework endpoints return `{ code, msg, data, success }`; unwrap them.
    const data = response.data;
    if (data && typeof data === 'object' && 'success' in data && 'data' in data) {
      return data.data;
    }
    return data;
  },
  (error) => {
    const status = error.response?.status;
    const data = error.response?.data;
    const message =
      (data && (data.message || data.msg || data.error)) ||
      (status === 401 ? '登录已过期，请重新登录' : '请求失败，请稍后重试');

    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login';
      }
    }

    ElMessage.error(message);
    return Promise.reject(error);
  },
);

export default service;
