<template>
  <div class="kp-layout">
    <Sidebar />
    <div class="kp-main">
      <Topbar />
      <main class="kp-content">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import Sidebar from './Sidebar.vue';
import Topbar from './Topbar.vue';
</script>
