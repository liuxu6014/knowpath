import { defineStore } from 'pinia';
import { listSubjects } from '@/api';

export const useAppStore = defineStore('app', {
  state: () => ({
    sidebarCollapsed: true,
    currentSubjectId: Number(localStorage.getItem('knowpath:subject')) || null,
    subjects: [],
  }),
  getters: {
    currentSubject: (state) =>
      state.subjects.find((s) => s.id === state.currentSubjectId) || null,
  },
  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed;
    },
    setCurrentSubject(id) {
      this.currentSubjectId = id;
      if (id) localStorage.setItem('knowpath:subject', String(id));
      else localStorage.removeItem('knowpath:subject');
    },
    async loadSubjects() {
      const data = await listSubjects();
      this.subjects = data.items || [];
      return this.subjects;
    },
  },
});
