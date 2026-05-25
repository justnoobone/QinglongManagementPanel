<template>
  <div class="logs-container">
    <el-header class="header">
      <div class="header-left">
        <el-button @click="goBack">返回</el-button>
        <span class="title">实例 {{ id }} 日志</span>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadLogs">刷新</el-button>
        <el-button @click="clearLogs">清屏</el-button>
        <el-switch v-model="autoRefresh" active-text="自动刷新" />
      </div>
    </el-header>

    <el-main class="log-main">
      <pre ref="logContainer" class="log-content">{{ logs }}</pre>
    </el-main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const route = useRoute()
const id = route.params.id
const logs = ref('加载中...')
const logContainer = ref(null)
const autoRefresh = ref(true)
const loading = ref(false)
let refreshInterval = null

const scrollToBottom = () => {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

const loadLogs = async () => {
  loading.value = true
  try {
    const res = await axios.get(`/servers/local/logs/${id}`)
    logs.value = res.data.logs || '暂无日志'
    scrollToBottom()
  } catch (e) {
    logs.value = `加载日志失败: ${e.response?.data?.error || e.message}`
  } finally {
    loading.value = false
  }
}

const clearLogs = () => {
  logs.value = ''
}

const goBack = () => {
  router.push('/')
}

onMounted(() => {
  loadLogs()
  refreshInterval = setInterval(() => {
    if (autoRefresh.value) loadLogs()
  }, 3000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>

<style scoped>
.logs-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 60px;
  padding: 0 24px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.header-left,
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.log-main {
  flex: 1;
  padding: 0;
  overflow: hidden;
}

.log-content {
  height: 100%;
  margin: 0;
  padding: 16px;
  overflow-y: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
