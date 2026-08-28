<script setup lang="ts">
import { ElButton, ElResult } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/result/style/css'
</script>

<template>
  <el-result class="not-found-card" icon="warning" title="页面不存在" sub-title="请返回员工问答或 HR 管理端。">
    <template #extra>
      <router-link to="/"><el-button type="primary">返回首页</el-button></router-link>
    </template>
  </el-result>
</template>
