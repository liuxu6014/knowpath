import { defineStore } from 'pinia';
import { login, register, getMe, patchMe, logout } from '@/api';
import { TOKEN_KEY } from '@/api/request';

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: null,
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    isAdmin: (state) => !!state.user?.is_staff,
    displayName: (state) => state.user?.username || '访客',
    profile: (state) => state.user?.profile || {},
  },
  actions: {
    async loginAction(payload) {
      const data = await login(payload);
      this.token = data.token;
      localStorage.setItem(TOKEN_KEY, data.token);
      await this.fetchMe();
    },
    async registerAction(payload) {
      await register(payload);
    },
    async fetchMe() {
      const data = await getMe();
      this.user = data.user || null;
      return this.user;
    },
    async saveProfile(payload) {
      const data = await patchMe(payload);
      this.user = data.user || this.user;
      return data;
    },
    async logoutAction() {
      try {
        await logout();
      } catch (e) {
        /* ignore network error on logout */
      }
      this.token = '';
      this.user = null;
      localStorage.removeItem(TOKEN_KEY);
    },
  },
});
