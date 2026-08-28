<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElTag } from 'element-plus'
import 'element-plus/es/components/tag/style/css'

import { useAppStore } from './stores/app'

const route = useRoute()
const appStore = useAppStore()
const activePath = computed(() => route.path)

onMounted(() => {
  void appStore.loadHealth()
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <router-link class="brand" to="/">
        <span class="brand-mark">HR</span>
        <span>
          <strong>制度智能问答</strong>
          <small>情景可推演 · 结论可验证</small>
        </span>
      </router-link>

      <nav class="topnav" aria-label="主导航">
        <router-link :class="{ active: activePath === '/' }" to="/">员工问答</router-link>
        <router-link :class="{ active: activePath.startsWith('/admin') }" to="/admin">HR 管理</router-link>
      </nav>

      <el-tag :type="appStore.healthTagType" effect="plain" round>
        {{ appStore.healthLabel }}
      </el-tag>
    </header>

    <main class="page-container">
      <router-view />
    </main>
  </div>
</template>
