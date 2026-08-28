<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  ElAlert, ElButton, ElDialog, ElEmpty, ElForm, ElFormItem, ElInput, ElMessage, ElMessageBox,
  ElOption, ElSelect, ElSkeleton, ElTable, ElTableColumn, ElTag,
} from 'element-plus'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/tag/style/css'

import {
  createRegressionCase, deletePolicyVersion, fetchAdminFeedback, fetchAdminPolicyReader, fetchAdminSession,
  fetchAnalytics, fetchIndexStatus, fetchPolicies, fetchRegressionCases, loginAdmin, logoutAdmin, rebuildIndex,
  retestFeedback, testSearch, updateFeedbackStatus, updatePolicyVersion, uploadPolicy,
  type AdminFeedbackFilters, type SearchTestResponse,
} from '../services/admin'
import { fetchHumanChallenge } from '../services/auth'
import SliderPuzzleCaptcha from '../components/SliderPuzzleCaptcha.vue'
import type { AdminSession, AnalyticsSummary, FeedbackRecord, FeedbackType, HumanChallenge, IndexStatus, PolicyReader, PolicySummary, PolicyVersionSummary, RegressionCase } from '../types/api'

const session = ref<AdminSession>({ authenticated: false, admin: null })
const checkingSession = ref(true)
const dashboardLoading = ref(false)
const policies = ref<PolicySummary[]>([])
const index = ref<IndexStatus | null>(null)
const loginLoading = ref(false)
const uploadLoading = ref(false)
const rebuilding = ref(false)
const searchLoading = ref(false)
const uploadDialogVisible = ref(false)
const previewVisible = ref(false)
const previewReader = ref<PolicyReader | null>(null)
const searchQuestion = ref('年假如何计算？')
const searchResponse = ref<SearchTestResponse | null>(null)
const feedbackRecords = ref<FeedbackRecord[]>([])
const regressionCases = ref<RegressionCase[]>([])
const analytics = ref<AnalyticsSummary | null>(null)
const governanceLoading = ref(false)
const feedbackNotes = reactive<Record<string, string>>({})
const feedbackFilters = reactive<AdminFeedbackFilters>({ status: '', feedback_type: '', policy_id: '', date_from: '', date_to: '' })
const loginForm = reactive({ username: 'admin', password: '88888888', slider_position: null as number | null })
const humanChallenge = ref<HumanChallenge | null>(null)
const uploadForm = reactive({ code: '', title: '', category: '', version: '1.0', effective_date: '', file: null as File | null })

const policyCount = computed(() => policies.value.length)
const versionCount = computed(() => policies.value.reduce((total, item) => total + item.version_count, 0))
const activeVersionCount = computed(() => policies.value.filter((item) => item.active_version_id !== null).length)
const indexTagType = computed(() => index.value?.status === 'ready' ? 'success' : index.value?.status === 'stale' ? 'warning' : 'info')
const adminPuzzleAligned = computed(() => (
  humanChallenge.value !== null && loginForm.slider_position !== null
  && Math.abs(loginForm.slider_position - humanChallenge.value.target_position) <= 3
))

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function statusLabel(status: PolicyVersionSummary['status']): string {
  return { active: '已启用', inactive: '已停用', draft: '草稿' }[status]
}

function statusTag(status: PolicyVersionSummary['status']): 'success' | 'info' | 'warning' {
  return status === 'active' ? 'success' : status === 'draft' ? 'warning' : 'info'
}

function feedbackTypeLabel(type: FeedbackType): string {
  return { wrong_answer: '回答错误', missing_policy: '制度缺失', outdated_policy: '制度过期', unclear: '表述不清', suggestion: '改进建议' }[type]
}

function feedbackStatusLabel(status: FeedbackRecord['status']): string {
  return { open: '待处理', processing: '处理中', resolved: '已解决', rejected: '已驳回' }[status]
}

function feedbackStatusType(status: FeedbackRecord['status']): 'warning' | 'primary' | 'success' | 'info' {
  return status === 'open' ? 'warning' : status === 'processing' ? 'primary' : status === 'resolved' ? 'success' : 'info'
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

function hasRegressionCase(feedbackId: string): boolean {
  return regressionCases.value.some((item) => item.feedback_id === feedbackId)
}

async function loadGovernance(): Promise<void> {
  governanceLoading.value = true
  try {
    const [feedback, cases, summary] = await Promise.all([
      fetchAdminFeedback(feedbackFilters), fetchRegressionCases(), fetchAnalytics(feedbackFilters),
    ])
    feedbackRecords.value = feedback
    regressionCases.value = cases
    analytics.value = summary
  } finally {
    governanceLoading.value = false
  }
}

async function loadDashboard(): Promise<void> {
  dashboardLoading.value = true
  try {
    const [policyResult, indexResult] = await Promise.all([fetchPolicies(), fetchIndexStatus(), loadGovernance()])
    policies.value = policyResult.items
    index.value = indexResult
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    dashboardLoading.value = false
  }
}

async function applyFeedbackFilters(): Promise<void> {
  try {
    await loadGovernance()
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function handleFeedback(item: FeedbackRecord, action: 'start_processing' | 'return_open' | 'resolve' | 'reject'): Promise<void> {
  try {
    await updateFeedbackStatus(item.id, action, feedbackNotes[item.id]?.trim() || undefined)
    feedbackNotes[item.id] = ''
    await loadGovernance()
    ElMessage.success('反馈状态与处理事件已更新')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function runFeedbackRetest(item: FeedbackRecord): Promise<void> {
  try {
    const result = await retestFeedback(item.id)
    await loadGovernance()
    ElMessage[result.passed ? 'success' : 'warning'](result.passed ? '当前检索已覆盖原证据，复测通过' : '当前检索未完整覆盖原证据')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function solidifyRegression(item: FeedbackRecord): Promise<void> {
  try {
    await createRegressionCase(item.id)
    await loadGovernance()
    ElMessage.success('已固化为回归用例')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function submitLogin(): Promise<void> {
  if (!loginForm.username.trim() || !loginForm.password || !adminPuzzleAligned.value || !humanChallenge.value) {
    ElMessage.warning('请完整填写账号、密码并完成滑动拼图')
    return
  }
  loginLoading.value = true
  try {
    session.value = await loginAdmin(
      loginForm.username.trim(), loginForm.password, humanChallenge.value.challenge_id, Number(loginForm.slider_position),
    )
    loginForm.password = ''
    loginForm.slider_position = null
    await loadDashboard()
    ElMessage.success('登录成功')
  } catch (error) {
    ElMessage.error(readableError(error))
    await loadHumanChallenge()
  } finally {
    loginLoading.value = false
  }
}

async function loadHumanChallenge(): Promise<void> {
  try {
    humanChallenge.value = await fetchHumanChallenge()
    loginForm.slider_position = null
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function signOut(): Promise<void> {
  try {
    await logoutAdmin()
    session.value = { authenticated: false, admin: null }
    policies.value = []
    index.value = null
    searchResponse.value = null
    feedbackRecords.value = []
    regressionCases.value = []
    analytics.value = null
    loginForm.password = '88888888'
    await loadHumanChallenge()
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

function selectFile(event: Event): void {
  uploadForm.file = (event.target as HTMLInputElement).files?.[0] ?? null
}

function resetUploadForm(): void {
  Object.assign(uploadForm, { code: '', title: '', category: '', version: '1.0', effective_date: '', file: null })
}

async function submitUpload(): Promise<void> {
  if (!uploadForm.code.trim() || !uploadForm.title.trim() || !uploadForm.category.trim() || !uploadForm.version.trim() || !uploadForm.effective_date || !uploadForm.file) {
    ElMessage.warning('请完整填写制度元数据并选择文件')
    return
  }
  const body = new FormData()
  body.set('code', uploadForm.code.trim().toUpperCase())
  body.set('title', uploadForm.title.trim())
  body.set('category', uploadForm.category.trim())
  body.set('version', uploadForm.version.trim())
  body.set('effective_date', uploadForm.effective_date)
  body.set('file', uploadForm.file)
  uploadLoading.value = true
  try {
    await uploadPolicy(body)
    uploadDialogVisible.value = false
    resetUploadForm()
    await loadDashboard()
    ElMessage.success('制度解析并保存成功，启用后请重建索引')
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    uploadLoading.value = false
  }
}

async function changeStatus(version: PolicyVersionSummary, status: PolicyVersionSummary['status']): Promise<void> {
  try {
    if (status === 'active') {
      await ElMessageBox.confirm('启用该版本会在同一事务中停用此制度的其他版本，是否继续？', '启用制度版本', { type: 'warning' })
    }
    await updatePolicyVersion(version.id, { status })
    await loadDashboard()
    ElMessage.success(status === 'active' ? '版本已启用，索引现在可能过期' : '版本已停用')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(readableError(error))
  }
}

async function deleteVersion(version: PolicyVersionSummary): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除版本 ${version.version}？该操作只允许未启用且未被回答引用的版本。`, '删除版本', { type: 'warning' })
    await deletePolicyVersion(version.id)
    await loadDashboard()
    ElMessage.success('版本已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(readableError(error))
  }
}

async function previewVersion(version: PolicyVersionSummary): Promise<void> {
  try {
    previewReader.value = await fetchAdminPolicyReader(version.id)
    previewVisible.value = true
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function rebuild(): Promise<void> {
  rebuilding.value = true
  try {
    index.value = await rebuildIndex()
    ElMessage.success(`索引发布成功，共 ${index.value.clause_count} 条条款`)
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    rebuilding.value = false
  }
}

async function runSearchTest(): Promise<void> {
  if (!searchQuestion.value.trim()) {
    ElMessage.warning('请输入测试问题')
    return
  }
  searchLoading.value = true
  try {
    searchResponse.value = await testSearch(searchQuestion.value.trim())
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    searchLoading.value = false
  }
}

onMounted(async () => {
  try {
    session.value = await fetchAdminSession()
    if (session.value.authenticated) await loadDashboard()
    else await loadHumanChallenge()
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    checkingSession.value = false
  }
})
</script>

<template>
  <el-skeleton v-if="checkingSession" :rows="8" animated />

  <section v-else-if="!session.authenticated" class="admin-login-shell">
    <div class="login-story">
      <p class="eyebrow">HR 知识治理</p>
      <h1>先把制度管可信，再让员工放心问</h1>
      <p>管理员会话受密码哈希、Cookie Session 与 CSRF 三重保护。系统不保存任何真实员工档案。</p>
      <div class="login-feature-grid">
        <span>版本唯一启用</span><span>原子索引发布</span><span>Top 5 可解释检索</span>
      </div>
      <div class="login-assurance" aria-label="治理流程">
        <span><b>01</b>上传与解析</span>
        <span><b>02</b>审核并启用</span>
        <span><b>03</b>重建可信索引</span>
      </div>
    </div>
    <el-form class="login-card" label-position="top" @submit.prevent="submitLogin">
      <div class="login-card-heading"><span class="panel-index">管理员认证</span><h2>登录 HR 控制台</h2><p>演示账号：admin　密码：88888888</p></div>
      <el-form-item label="用户名"><el-input v-model="loginForm.username" autocomplete="username" placeholder="请输入管理员用户名" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="loginForm.password" type="password" show-password autocomplete="current-password" placeholder="至少 8 位密码" @keyup.enter="submitLogin" /></el-form-item>
      <el-form-item label="人机验证">
        <slider-puzzle-captcha v-if="humanChallenge" v-model="loginForm.slider_position" :challenge="humanChallenge" @refresh="loadHumanChallenge" />
        <el-skeleton v-else :rows="2" animated />
      </el-form-item>
      <el-button native-type="submit" type="primary" size="large" :loading="loginLoading" :disabled="!adminPuzzleAligned">登录</el-button>
    </el-form>
  </section>

  <template v-else>
    <section class="hero-panel compact admin-hero">
      <div class="hero-copy"><p class="eyebrow">HR 知识治理</p><h1>制度生命周期与可信度控制台</h1><p>你好，{{ session.admin?.username }}。上传制度、启用版本、原子重建索引，再用 Top 5 验证检索质量。</p></div>
      <div class="admin-hero-side"><span>当前工作区 · HR 管理端</span><div class="hero-actions"><el-button type="primary" @click="uploadDialogVisible = true">上传制度版本</el-button><el-button @click="signOut">退出登录</el-button></div></div>
    </section>

    <section class="metric-grid admin-metrics">
      <article class="metric-card"><span>制度数量</span><strong>{{ policyCount }}</strong><small>{{ activeVersionCount }} 项有启用版本</small></article>
      <article class="metric-card"><span>版本总数</span><strong>{{ versionCount }}</strong><small>支持草稿、启用、停用</small></article>
      <article class="metric-card"><span>当前索引</span><strong>{{ index?.clause_count ?? 0 }}</strong><small>已发布条款</small></article>
      <article class="metric-card"><span>索引状态</span><strong><el-tag :type="indexTagType" effect="dark">{{ index?.status || 'unknown' }}</el-tag></strong><small>{{ index?.stale ? '知识发生变化，请重建' : '指纹与启用制度一致' }}</small></article>
    </section>

    <el-alert v-if="index?.stale" class="page-alert" type="warning" title="启用制度与当前索引指纹不一致，员工问答已停止正式生成，请立即重建索引。" show-icon :closable="false" />

    <section class="admin-grid">
      <article class="admin-card policy-management-card">
        <div class="card-heading"><div><span class="panel-index">A</span><h2>制度与版本</h2></div><el-button type="primary" plain @click="uploadDialogVisible = true">新增版本</el-button></div>
        <el-skeleton v-if="dashboardLoading" :rows="8" animated />
        <el-empty v-else-if="!policies.length" description="尚未上传制度" />
        <div v-else class="policy-list">
          <article v-for="policy in policies" :key="policy.id" class="policy-item">
            <header><div><span>{{ policy.category }}</span><h3>{{ policy.title }}</h3><small>{{ policy.code }}</small></div><el-tag :type="policy.active_version_id ? 'success' : 'info'" effect="plain">{{ policy.active_version_id ? '已有启用版本' : '暂无启用版本' }}</el-tag></header>
            <div class="version-list">
              <div v-for="version in policy.versions" :key="version.id" class="version-row">
                <div><strong>v{{ version.version }}</strong><el-tag size="small" :type="statusTag(version.status)">{{ statusLabel(version.status) }}</el-tag></div>
                <span>生效 {{ version.effective_date }}</span><span>{{ version.clause_count }} 条 · {{ formatBytes(version.size_bytes) }}</span>
                <div class="row-actions">
                  <el-button size="small" @click="previewVersion(version)">预览</el-button>
                  <el-button v-if="version.status !== 'active'" size="small" type="success" plain @click="changeStatus(version, 'active')">启用</el-button>
                  <el-button v-else size="small" type="warning" plain @click="changeStatus(version, 'inactive')">停用</el-button>
                  <el-button size="small" type="danger" plain :disabled="version.status === 'active'" @click="deleteVersion(version)">删除</el-button>
                </div>
              </div>
            </div>
          </article>
        </div>
      </article>

      <div class="admin-side-stack">
        <article class="admin-card index-card">
          <div class="card-heading"><div><span class="panel-index">B</span><h2>原子索引</h2></div><el-tag :type="indexTagType">{{ index?.status || 'unknown' }}</el-tag></div>
          <dl v-if="index"><div><dt>启用条款</dt><dd>{{ index.active_clause_count }}</dd></div><div><dt>已发布条款</dt><dd>{{ index.clause_count }}</dd></div><div><dt>嵌入模型</dt><dd>{{ index.embedding_model }}</dd></div><div><dt>构建时间</dt><dd>{{ index.built_at ? new Date(index.built_at).toLocaleString() : '尚未构建' }}</dd></div></dl>
          <el-button type="primary" :loading="rebuilding" @click="rebuild">重建并原子发布</el-button>
        </article>

        <article class="admin-card search-test-card">
          <div class="card-heading"><div><span class="panel-index">C</span><h2>Top 5 检索测试</h2></div></div>
          <el-input v-model="searchQuestion" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="输入员工可能提出的问题" />
          <el-button type="primary" plain :loading="searchLoading" @click="runSearchTest">运行混合检索</el-button>
        </article>
      </div>
    </section>

    <article v-if="searchResponse" class="admin-card search-results-card">
      <div class="card-heading"><div><span class="panel-index">D</span><h2>检索诊断结果</h2><p>问题：{{ searchResponse.question }}</p></div><el-tag effect="plain">Top {{ searchResponse.results.length }}</el-tag></div>
      <el-table :data="searchResponse.results" stripe table-layout="fixed">
        <el-table-column prop="rank" label="#" width="52" />
        <el-table-column label="制度条款" min-width="220"><template #default="scope"><strong>{{ scope.row.policy_title }}</strong><br /><small>{{ scope.row.clause_number || scope.row.section_path }}</small></template></el-table-column>
        <el-table-column prop="text" label="命中原文" min-width="360" show-overflow-tooltip />
        <el-table-column label="向量" width="96"><template #default="scope">{{ scope.row.vector_score.toFixed(3) }}<small class="rank-detail">#{{ scope.row.vector_rank }}</small></template></el-table-column>
        <el-table-column label="BM25" width="96"><template #default="scope">{{ scope.row.bm25_score.toFixed(3) }}<small class="rank-detail">#{{ scope.row.bm25_rank }}</small></template></el-table-column>
        <el-table-column label="RRF" width="100"><template #default="scope">{{ scope.row.rrf_score.toFixed(5) }}</template></el-table-column>
      </el-table>
    </article>

    <section class="governance-section">
      <div class="section-heading"><div><span class="panel-index">E</span><h2>问答数据洞察</h2><p>统计只来自匿名查询日志和制度意见，不关联员工档案。</p></div><el-button plain :loading="governanceLoading" @click="applyFeedbackFilters">刷新洞察</el-button></div>
      <section v-if="analytics" class="metric-grid insight-metrics">
        <article class="metric-card"><span>查询量</span><strong>{{ analytics.query_count }}</strong><small>平均 {{ analytics.average_latency_ms }} ms</small></article>
        <article class="metric-card"><span>可信命中率</span><strong>{{ percent(analytics.hit_rate) }}</strong><small>拒答 {{ percent(analytics.refusal_rate) }} · 澄清 {{ percent(analytics.clarification_rate) }}</small></article>
        <article class="metric-card"><span>反馈总数</span><strong>{{ analytics.feedback_count }}</strong><small>{{ analytics.open_feedback_count }} 项仍在处理</small></article>
        <article class="metric-card"><span>回归用例</span><strong>{{ analytics.regression_case_count }}</strong><small>降级率 {{ percent(analytics.degraded_rate) }}</small></article>
      </section>
      <section v-if="analytics" class="insight-grid">
        <article class="admin-card"><h3>热门问题</h3><ol class="rank-list"><li v-for="item in analytics.popular_questions" :key="item.question"><span>{{ item.question }}</span><strong>{{ item.count }}</strong></li></ol><el-empty v-if="!analytics.popular_questions.length" description="暂无查询" :image-size="45" /></article>
        <article class="admin-card"><h3>未命中问题</h3><ol class="rank-list"><li v-for="item in analytics.missed_questions" :key="item.question"><span>{{ item.question }}</span><strong>{{ item.count }}</strong></li></ol><el-empty v-if="!analytics.missed_questions.length" description="暂无拒答" :image-size="45" /></article>
        <article class="admin-card"><h3>反馈分类</h3><div class="distribution-list"><div v-for="item in analytics.feedback_by_category" :key="item.category"><span>{{ item.category }}</span><strong>{{ item.count }}</strong></div></div><el-empty v-if="!analytics.feedback_by_category.length" description="暂无反馈" :image-size="45" /></article>
      </section>
    </section>

    <section class="governance-section feedback-governance">
      <div class="section-heading"><div><span class="panel-index">F</span><h2>反馈闭环与回归</h2><p>状态变化、复测和固化操作全部追加到不可覆盖的处理时间线。</p></div><el-tag effect="plain">{{ feedbackRecords.length }} 条意见 / {{ regressionCases.length }} 个用例</el-tag></div>
      <div class="feedback-filter-bar">
        <select v-model="feedbackFilters.status" class="native-input"><option value="">全部状态</option><option value="open">待处理</option><option value="processing">处理中</option><option value="resolved">已解决</option><option value="rejected">已驳回</option></select>
        <select v-model="feedbackFilters.feedback_type" class="native-input"><option value="">全部类型</option><option value="wrong_answer">回答错误</option><option value="missing_policy">制度缺失</option><option value="outdated_policy">制度过期</option><option value="unclear">表述不清</option><option value="suggestion">改进建议</option></select>
        <select v-model="feedbackFilters.policy_id" class="native-input"><option value="">全部制度</option><option v-for="policy in policies" :key="policy.id" :value="policy.id">{{ policy.title }}</option></select>
        <input v-model="feedbackFilters.date_from" class="native-input" type="date" aria-label="反馈起始日期" />
        <input v-model="feedbackFilters.date_to" class="native-input" type="date" aria-label="反馈结束日期" />
        <el-button type="primary" :loading="governanceLoading" @click="applyFeedbackFilters">应用筛选</el-button>
      </div>
      <el-skeleton v-if="governanceLoading" :rows="6" animated />
      <el-empty v-else-if="!feedbackRecords.length" description="当前筛选条件下暂无意见" />
      <div v-else class="admin-feedback-list">
        <article v-for="item in feedbackRecords" :key="item.id" class="admin-feedback-item">
          <header><div><el-tag size="small" :type="feedbackStatusType(item.status)">{{ feedbackStatusLabel(item.status) }}</el-tag><strong>{{ feedbackTypeLabel(item.feedback_type) }}</strong><span>{{ item.is_anonymous ? '匿名员工' : item.submitter_name }}</span></div><small>{{ new Date(item.created_at).toLocaleString() }}</small></header>
          <p class="feedback-question">原问题：{{ item.answer_snapshot?.question || '回答已删除，快照仍保留' }}</p>
          <p>{{ item.content }}</p>
          <el-input v-if="item.status === 'open' || item.status === 'processing'" v-model="feedbackNotes[item.id]" type="textarea" :rows="2" maxlength="1000" placeholder="填写处理说明（可选）" />
          <div class="feedback-actions">
            <el-button v-if="item.status === 'open'" size="small" type="primary" @click="handleFeedback(item, 'start_processing')">开始处理</el-button>
            <el-button v-if="item.status === 'processing'" size="small" @click="handleFeedback(item, 'return_open')">退回待处理</el-button>
            <el-button v-if="item.status === 'processing'" size="small" type="success" @click="handleFeedback(item, 'resolve')">标记解决</el-button>
            <el-button v-if="item.status === 'open' || item.status === 'processing'" size="small" type="danger" plain @click="handleFeedback(item, 'reject')">驳回</el-button>
            <el-button size="small" type="warning" plain @click="runFeedbackRetest(item)">复测原问题</el-button>
            <el-button v-if="item.status === 'resolved' && item.last_retest?.passed && !hasRegressionCase(item.id)" size="small" type="success" plain @click="solidifyRegression(item)">固化回归用例</el-button>
          </div>
          <ol class="admin-feedback-timeline"><li v-for="event in item.events" :key="event.id"><span>{{ event.action }}</span><p>{{ event.note || '状态已更新' }}</p><small>{{ new Date(event.created_at).toLocaleString() }}</small></li></ol>
        </article>
      </div>
    </section>
  </template>

  <el-dialog v-model="uploadDialogVisible" title="上传制度版本" width="min(560px, 92vw)" destroy-on-close>
    <el-form label-position="top">
      <div class="form-grid"><el-form-item label="制度编号"><el-input v-model="uploadForm.code" placeholder="如 LEAVE-001" /></el-form-item><el-form-item label="版本号"><el-input v-model="uploadForm.version" placeholder="如 2.0" /></el-form-item></div>
      <el-form-item label="制度标题"><el-input v-model="uploadForm.title" placeholder="制度中文名称" /></el-form-item>
      <div class="form-grid"><el-form-item label="分类"><el-select v-model="uploadForm.category" placeholder="选择分类"><el-option v-for="item in ['考勤', '休假', '薪酬福利', '差旅', '员工关系']" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="生效日期"><input v-model="uploadForm.effective_date" class="native-input" type="date" /></el-form-item></div>
      <el-form-item label="制度文件"><label class="file-picker"><input type="file" accept=".md,.txt,.pdf,.docx" @change="selectFile" /><span>{{ uploadForm.file?.name || '选择 Markdown、TXT、PDF 或 DOCX（最大 10 MB）' }}</span></label></el-form-item>
    </el-form>
    <template #footer><el-button @click="uploadDialogVisible = false">取消</el-button><el-button type="primary" :loading="uploadLoading" @click="submitUpload">解析并保存草稿</el-button></template>
  </el-dialog>

  <el-dialog v-model="previewVisible" :title="previewReader?.policy_title || '制度预览'" width="min(850px, 94vw)">
    <div v-if="previewReader" class="preview-meta">{{ previewReader.policy_code }} · v{{ previewReader.policy_version }} · {{ previewReader.effective_date }} · {{ previewReader.clauses.length }} 条</div>
    <div v-if="previewReader" class="preview-clauses"><article v-for="clause in previewReader.clauses" :key="clause.stable_anchor"><strong>{{ clause.section_path }} / {{ clause.clause_number || '条款' }}</strong><p>{{ clause.text }}</p></article></div>
  </el-dialog>
</template>
