<template>
  <div class="dashboard">
    <!-- 顶部 -->
    <div class="header">
      <h1>青龙多实例管理面板</h1>
      <button class="btn-logout" @click="logout">退出登录</button>
    </div>

    <!-- 服务器标签页 -->
    <div class="server-tabs">
      <div
        v-for="server in servers"
        :key="server.id"
        :class="['tab', { active: currentServer === server.id }]"
        @click="switchServer(server.id)"
      >
        <span class="tab-name">{{ server.name }}</span>
        <span :class="['tab-dot', server.online !== false ? 'online' : 'offline']">&#9679;</span>
        <button v-if="server.type === 'remote'" class="tab-close" @click.stop="confirmDeleteServer(server)" title="删除服务器">&#215;</button>
      </div>
      <button class="tab-add" @click="showAddServer = true">+ 添加服务器</button>

      <!-- Nginx 状态 -->
      <div v-if="currentServer === 'local'" class="nginx-status" @click="loadNginxStatus">
        <span class="nginx-label">Nginx:</span>
        <span v-if="!nginxInfo.exists" class="nginx-dot offline" title="未部署">&#9679;</span>
        <span v-else-if="nginxInfo.status === 'running'" class="nginx-dot online" title="运行中">&#9679;</span>
        <span v-else class="nginx-dot warning" title="已停止">&#9679;</span>
        <span class="nginx-text">{{ nginxInfo.exists ? (nginxInfo.status === 'running' ? '运行' : '停止') : '未部署' }}</span>
        <button v-if="!nginxInfo.exists" class="btn-nginx btn-nginx-start" @click.stop="nginxAction('create')">部署</button>
        <button v-if="nginxInfo.exists && nginxInfo.status !== 'running'" class="btn-nginx btn-nginx-start" @click.stop="nginxAction('start')">启动</button>
        <button v-if="nginxInfo.exists && nginxInfo.status === 'running'" class="btn-nginx btn-nginx-stop" @click.stop="nginxAction('stop')">停止</button>
        <button v-if="nginxInfo.exists" class="btn-nginx btn-nginx-restart" @click.stop="nginxAction('restart')">重启</button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">加载中...</div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 实例列表 -->
    <div v-if="!loading && !error" class="instance-section">
      <div class="table-wrapper">
        <table class="instance-table">
          <thead>
            <tr>
              <th class="th-check"><input type="checkbox" v-model="selectAll" @change="toggleSelectAll" /></th>
              <th class="th-id">ID</th>
              <th class="th-name">名称</th>
              <th class="th-port">端口</th>
              <th class="th-status">状态</th>
              <th class="th-link">访问</th>
              <th class="th-date">到期日期</th>
              <th class="th-note">备注</th>
              <th class="th-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inst in instances" :key="inst.id" :class="{ 'expired-row': inst.expired && inst.status === 'running', 'selected-row': selectedIds.includes(inst.id) }">
              <td class="td-check"><input type="checkbox" :checked="selectedIds.includes(inst.id)" @change="toggleSelect(inst.id)" /></td>
              <td class="td-id">{{ inst.id }}</td>
              <td class="td-name">{{ inst.name }}</td>
              <td class="td-port">{{ inst.port }}</td>
              <td class="td-status">
                <span v-if="inst.expired && inst.status === 'running'" class="status-badge expired">&#x26A0; 已过期</span>
                <span v-else :class="['status-badge', inst.status]">
                  {{ inst.status === 'running' ? '运行中' : '已停止' }}
                </span>
              </td>
              <td class="td-link">
                <a v-if="isLocalServer() && inst.id > 0 && inst.use_nginx && nginxInfo.exists && nginxInfo.status === 'running'" :href="getNginxUrl(inst.id)" target="_blank" class="link-proxy" title="Nginx代理访问">代理</a>
                <a :href="getDirectUrl(inst.port)" target="_blank" class="link-direct" title="直连访问">直连</a>
              </td>
              <td class="td-date">
                <input
                  type="date"
                  class="inline-date"
                  :class="{ 'expired-date': inst.expired }"
                  :value="inst.end_date"
                  @change="updateMetadata(inst, 'end_date', $event.target.value)"
                  title="点击设置到期日期"
                />
              </td>
              <td class="td-note">
                <input
                  type="text"
                  class="inline-note"
                  :value="inst.notes"
                  @blur="updateMetadata(inst, 'notes', $event.target.value)"
                  @keyup.enter="$event.target.blur()"
                  placeholder="备注..."
                />
              </td>
              <td class="td-actions">
                <button v-if="inst.status === 'running'" class="btn-sm btn-stop" @click="doAction('stop', inst.id)" :disabled="actionLoading">停用</button>
                <button v-if="inst.status !== 'running'" class="btn-sm btn-start" @click="doAction('start', inst.id)" :disabled="actionLoading">启动</button>
                <button class="btn-sm btn-reset" @click="confirmAction('reset', inst.id)" :disabled="actionLoading">重置</button>
                <button class="btn-sm btn-delete" @click="confirmAction('delete', inst.id)" :disabled="actionLoading">删除</button>
                <button class="btn-sm btn-purge" @click="confirmAction('purge', inst.id)" :disabled="actionLoading">彻底删除</button>
                <button class="btn-sm btn-logs" @click="viewLogs(inst.id)">日志</button>
              </td>
            </tr>
            <tr v-if="instances.length === 0">
              <td colspan="9" class="empty">暂无实例，点击下方按钮创建</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 批量操作栏 + 工具栏 -->
      <div class="toolbar">
        <div class="toolbar-left">
          <template v-if="selectedIds.length > 0">
            <span class="selected-count">已选 {{ selectedIds.length }} 项</span>
            <button class="btn-primary btn-batch" @click="batchAction('start')" :disabled="actionLoading">批量启动</button>
            <button class="btn-warn btn-batch" @click="batchAction('stop')" :disabled="actionLoading">批量停止</button>
            <button class="btn-purple btn-batch" @click="confirmBatchAction('reset')" :disabled="actionLoading">批量重置</button>
            <button class="btn-danger btn-batch" @click="confirmBatchAction('delete')" :disabled="actionLoading">批量删除</button>
            <button class="btn-purge btn-batch" @click="confirmBatchAction('purge')" :disabled="actionLoading">批量彻底删除</button>
            <button class="btn-secondary btn-batch" @click="selectedIds = []; selectAll = false">取消选择</button>
          </template>
        </div>
        <div class="toolbar-right">
          <button class="btn-primary" @click="showCreate = true">+ 新建实例</button>
          <button class="btn-secondary" @click="loadInstances">刷新</button>
        </div>
      </div>
    </div>

    <!-- 新建实例对话框 -->
    <div v-if="showCreate" class="overlay" @click.self="showCreate = false">
      <div class="dialog">
        <h2>新建实例</h2>
        <div class="form-group">
          <label>实例编号</label>
          <input v-model.number="createNum" type="number" min="0" placeholder="输入编号，如 9">
        </div>
        <div class="form-group">
          <label>到期日期</label>
          <input v-model="createEndDate" type="date">
        </div>
        <div class="form-group">
          <label>备注</label>
          <input v-model="createNotes" type="text" placeholder="备注信息">
        </div>
        <div class="form-group">
          <label>镜像（留空使用默认）</label>
          <input v-model="createImage" type="text" :placeholder="`默认: ${getDefaultImageHint()}`">
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>CPU（核数）</label>
            <input v-model="createCpuLimit" type="text" placeholder="默认: 1">
          </div>
          <div class="form-group flex-1">
            <label>内存限制</label>
            <input v-model="createMemLimit" type="text" placeholder="默认: 1g">
          </div>
        </div>
        <div v-if="isLocalServer() && nginxInfo.exists && nginxInfo.status === 'running' && createNum !== 0" class="form-group form-group-checkbox">
          <label class="checkbox-label">
            <input type="checkbox" v-model="createUseNginx" />
            <span>使用 Nginx 代理</span>
            <span class="checkbox-hint">启用后可通过 http://host:91/qlN/ 访问</span>
          </label>
        </div>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showCreate = false">取消</button>
          <button class="btn-primary" @click="doCreate" :disabled="actionLoading">
            {{ actionLoading ? '创建中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 添加服务器对话框 -->
    <div v-if="showAddServer" class="overlay" @click.self="showAddServer = false">
      <div class="dialog">
        <h2>添加远程服务器</h2>
        <div class="form-group">
          <label>服务器名称</label>
          <input v-model="newServer.name" placeholder="如：生产服务器2">
        </div>
        <div class="form-row">
          <div class="form-group flex-3">
            <label>主机地址</label>
            <input v-model="newServer.host" placeholder="IP 或域名">
          </div>
          <div class="form-group flex-1">
            <label>SSH端口</label>
            <input v-model.number="newServer.port" type="number" placeholder="22">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>用户名</label>
            <input v-model="newServer.username" placeholder="root">
          </div>
          <div class="form-group flex-1">
            <label>密码</label>
            <input v-model="newServer.password" type="password" placeholder="SSH密码">
          </div>
        </div>
        <div class="form-group">
          <label>青龙数据路径</label>
          <input v-model="newServer.path" placeholder="/home/docker/qinglong">
        </div>
        <div v-if="addServerError" class="error-msg">{{ addServerError }}</div>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showAddServer = false">取消</button>
          <button class="btn-primary" @click="doAddServer" :disabled="actionLoading">
            {{ actionLoading ? '测试连接中...' : '测试连接并添加' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 日志对话框 -->
    <div v-if="showLogsDialog" class="overlay" @click.self="closeLogs">
      <div class="dialog dialog-logs">
        <div class="logs-header">
          <h2>日志 - qinglong{{ logId }}</h2>
          <div>
            <button class="btn-sm btn-secondary-sm" @click="refreshLogs">刷新</button>
            <button class="btn-sm btn-secondary-sm" @click="closeLogs">关闭</button>
          </div>
        </div>
        <pre class="logs-content">{{ logContent }}</pre>
      </div>
    </div>

    <!-- 确认对话框 -->
    <div v-if="confirmVisible" class="overlay">
      <div class="dialog">
        <h2>确认操作</h2>
        <p>{{ confirmMsg }}</p>
        <div v-if="confirmShowNginxOption" class="form-group form-group-checkbox" style="margin-top:12px;">
          <label class="checkbox-label">
            <input type="checkbox" v-model="confirmUseNginx" />
            <span>使用 Nginx 代理</span>
            <span class="checkbox-hint">启用后可通过 http://host:91/qlN/ 访问</span>
          </label>
        </div>
        <div v-if="confirmShowAdvanced" style="margin-top:12px;">
          <div class="form-group">
            <label>镜像（留空使用默认）</label>
            <input v-model="confirmImage" type="text" :placeholder="`默认: ${getDefaultResetImageHint()}`">
          </div>
          <div class="form-row">
            <div class="form-group flex-1">
              <label>CPU（核数）</label>
              <input v-model="confirmCpuLimit" type="text" placeholder="默认: 1">
            </div>
            <div class="form-group flex-1">
              <label>内存限制</label>
              <input v-model="confirmMemLimit" type="text" placeholder="默认: 1g">
            </div>
          </div>
        </div>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="confirmVisible = false">取消</button>
          <button class="btn-danger" @click="doConfirm" :disabled="actionLoading">确认</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'Dashboard',
  data() {
    return {
      servers: [],
      currentServer: 'local',
      instances: [],
      loading: false,
      actionLoading: false,
      error: '',

      // 批量选择
      selectedIds: [],
      selectAll: false,

      // Nginx
      nginxInfo: { exists: false, status: 'not_found', image: '', ports: [] },

      // 新建实例
      showCreate: false,
      createNum: null,
      createEndDate: '',
      createNotes: '',
      createUseNginx: true,
      createImage: '',
      createCpuLimit: '',
      createMemLimit: '',

      // 添加服务器
      showAddServer: false,
      addServerError: '',
      newServer: { name: '', host: '', port: 22, username: 'root', password: '', path: '/home/docker/qinglong' },

      // 日志
      showLogsDialog: false,
      logId: null,
      logContent: '',

      // 确认对话框
      confirmVisible: false,
      confirmMsg: '',
      confirmAction: null,
      confirmUseNginx: true,
      confirmShowNginxOption: false,
      confirmShowAdvanced: false,
      confirmInstId: null,
      confirmImage: '',
      confirmCpuLimit: '',
      confirmMemLimit: '',
    }
  },
  created() {
    this.loadServers()
  },
  methods: {
    getAuthHeaders() {
      const token = localStorage.getItem('token')
      return { Authorization: `Bearer ${token}` }
    },

    logout() {
      localStorage.removeItem('token')
      this.$router.push('/login')
    },

    // ===== 访问链接 =====
    // 获取当前服务器的主机地址（本地用浏览器hostname，远程用服务器IP）
    getCurrentHost() {
      if (this.currentServer === 'local') {
        return window.location.hostname
      }
      const server = this.servers.find(s => s.id === this.currentServer)
      return server ? server.host : window.location.hostname
    },

    // 直连：直接访问容器端口，不走 Nginx，不带子路径
    getDirectUrl(port) {
      const host = this.getCurrentHost()
      return `http://${host}:${port}/`
    },

    // 代理：通过 Nginx 访问，只有本地服务器才有 Nginx 代理
    getNginxUrl(id) {
      const hostname = window.location.hostname
      return `http://${hostname}:91/ql${id}/`
    },

    // 判断当前是否为本地服务器
    isLocalServer() {
      return this.currentServer === 'local'
    },

    // 获取默认镜像名称提示
    getDefaultImageHint() {
      return this.createNum === 0 ? 'whyour/qinglong:debian-python3.10' : 'whyour/qinglong:latest'
    },

    getDefaultResetImageHint() {
      return this.confirmInstId === 0 ? 'whyour/qinglong:debian-python3.10' : 'whyour/qinglong:latest'
    },

    // ===== 服务器管理 =====
    async loadServers() {
      try {
        const res = await axios.get('/servers', { headers: this.getAuthHeaders() })
        this.servers = res.data
        if (!this.servers.find(s => s.id === this.currentServer)) {
          this.currentServer = this.servers.length > 0 ? this.servers[0].id : 'local'
        }
        this.loadInstances()
        if (this.currentServer === 'local') {
          this.loadNginxStatus()
        }
      } catch (e) {
        if (e.response && e.response.status === 401) {
          this.logout()
        }
      }
    },

    switchServer(serverId) {
      this.currentServer = serverId
      this.error = ''
      this.selectedIds = []
      this.selectAll = false
      this.loadInstances()
      if (serverId === 'local') {
        this.loadNginxStatus()
      }
    },

    async doAddServer() {
      this.addServerError = ''
      if (!this.newServer.name || !this.newServer.host) {
        this.addServerError = '服务器名称和地址不能为空'
        return
      }
      this.actionLoading = true
      try {
        await axios.post('/servers', this.newServer, { headers: this.getAuthHeaders() })
        this.showAddServer = false
        this.newServer = { name: '', host: '', port: 22, username: 'root', password: '', path: '/home/docker/qinglong' }
        this.loadServers()
      } catch (e) {
        this.addServerError = e.response?.data?.error || '添加失败'
      } finally {
        this.actionLoading = false
      }
    },

    confirmDeleteServer(server) {
      this.confirmMsg = `确定删除服务器「${server.name}」？这不会影响远程服务器上的容器。`
      this.confirmAction = async () => {
        await axios.delete(`/servers/${server.id}`, { headers: this.getAuthHeaders() })
        this.loadServers()
      }
      this.confirmVisible = true
    },

    // ===== 实例管理 =====
    async loadInstances() {
      this.loading = true
      this.error = ''
      try {
        const res = await axios.get(`/servers/${this.currentServer}/instances`, { headers: this.getAuthHeaders() })
        this.instances = res.data
        // 清除不存在的选中项
        const existingIds = this.instances.map(i => i.id)
        this.selectedIds = this.selectedIds.filter(id => existingIds.includes(id))
        this.selectAll = existingIds.length > 0 && existingIds.every(id => this.selectedIds.includes(id))
      } catch (e) {
        this.error = e.response?.data?.error || '加载实例列表失败'
        if (e.response && e.response.status === 401) this.logout()
      } finally {
        this.loading = false
      }
    },

    async updateMetadata(inst, field, value) {
      inst[field] = value
      try {
        await axios.put(`/servers/${this.currentServer}/instances/${inst.id}/metadata`, {
          start_date: inst.start_date || '',
          end_date: inst.end_date || '',
          notes: inst.notes || '',
        }, { headers: this.getAuthHeaders() })
        this.loadInstances()
      } catch (e) {
        console.error('更新元数据失败:', e)
      }
    },

    async doCreate() {
      if (this.createNum === null || this.createNum === '') {
        alert('请输入实例编号')
        return
      }
      this.actionLoading = true
      try {
        const payload = {
          end_date: this.createEndDate,
          notes: this.createNotes,
          use_nginx: this.createUseNginx,
        }
        if (this.createImage) payload.image = this.createImage
        if (this.createCpuLimit) payload.cpu_limit = parseInt(this.createCpuLimit) * 1000000000 || undefined
        if (this.createMemLimit) payload.mem_limit = this.createMemLimit
        await axios.post(`/servers/${this.currentServer}/create/${this.createNum}`, payload, { headers: this.getAuthHeaders() })
        this.showCreate = false
        this.createNum = null
        this.createEndDate = ''
        this.createNotes = ''
        this.createUseNginx = true
        this.createImage = ''
        this.createCpuLimit = ''
        this.createMemLimit = ''
        this.loadInstances()
      } catch (e) {
        alert(e.response?.data?.error || '创建失败')
      } finally {
        this.actionLoading = false
      }
    },

    async doAction(action, id) {
      this.actionLoading = true
      try {
        if (action === 'delete') {
          await axios.delete(`/servers/${this.currentServer}/delete/${id}`, { headers: this.getAuthHeaders() })
        } else if (action === 'purge') {
          await axios.delete(`/servers/${this.currentServer}/purge/${id}`, { headers: this.getAuthHeaders() })
        } else if (action === 'reset') {
          const payload = { use_nginx: this.confirmUseNginx }
          if (this.confirmImage) payload.image = this.confirmImage
          if (this.confirmCpuLimit) payload.cpu_limit = parseInt(this.confirmCpuLimit) * 1000000000 || undefined
          if (this.confirmMemLimit) payload.mem_limit = this.confirmMemLimit
          await axios.post(`/servers/${this.currentServer}/reset/${id}`, payload, { headers: this.getAuthHeaders() })
        } else {
          await axios.post(`/servers/${this.currentServer}/${action}/${id}`, {}, { headers: this.getAuthHeaders() })
        }
        this.loadInstances()
      } catch (e) {
        alert(e.response?.data?.error || `${action}失败`)
      } finally {
        this.actionLoading = false
      }
    },

    confirmAction(action, id) {
      const actionNames = { reset: '重置', delete: '删除', purge: '彻底删除' }
      this.confirmMsg = `确定${actionNames[action]}实例 qinglong${id}？${action === 'delete' ? '数据将不会被删除。' : action === 'purge' ? '容器和数据目录将被一并删除，不可恢复！' : '所有数据将被清除！'}`
      // 重置操作且本地服务器有nginx运行时，显示nginx选项
      this.confirmShowNginxOption = action === 'reset' && this.isLocalServer() && this.nginxInfo.exists && this.nginxInfo.status === 'running' && id > 0
      // 重置操作且本地服务器时，显示高级配置
      this.confirmShowAdvanced = action === 'reset'
      this.confirmInstId = id
      this.confirmUseNginx = true
      this.confirmImage = ''
      this.confirmCpuLimit = ''
      this.confirmMemLimit = ''
      this.confirmAction = async () => {
        await this.doAction(action, id)
      }
      this.confirmVisible = true
    },

    // ===== 批量操作 =====
    toggleSelectAll() {
      if (this.selectAll) {
        this.selectedIds = this.instances.map(i => i.id)
      } else {
        this.selectedIds = []
      }
    },

    toggleSelect(id) {
      const idx = this.selectedIds.indexOf(id)
      if (idx >= 0) {
        this.selectedIds.splice(idx, 1)
      } else {
        this.selectedIds.push(id)
      }
      this.selectAll = this.instances.length > 0 && this.instances.every(i => this.selectedIds.includes(i.id))
    },

    async batchAction(action) {
      if (this.selectedIds.length === 0) return
      this.actionLoading = true
      try {
        const payload = { nums: this.selectedIds }
        if (action === 'reset') {
          payload.use_nginx = this.confirmUseNginx
          if (this.confirmImage) payload.image = this.confirmImage
          if (this.confirmCpuLimit) payload.cpu_limit = parseInt(this.confirmCpuLimit) * 1000000000 || undefined
          if (this.confirmMemLimit) payload.mem_limit = this.confirmMemLimit
        }
        const res = await axios.post(`/servers/${this.currentServer}/batch/${action}`, payload, { headers: this.getAuthHeaders() })
        const data = res.data
        if (data.results && data.results.failed && data.results.failed.length > 0) {
          alert(data.msg + '\n失败: ' + data.results.failed.map(f => `ql${f.num}: ${f.error}`).join('\n'))
        }
        this.selectedIds = []
        this.selectAll = false
        this.loadInstances()
      } catch (e) {
        alert(e.response?.data?.error || '批量操作失败')
      } finally {
        this.actionLoading = false
      }
    },

    confirmBatchAction(action) {
      const actionNames = { reset: '重置', delete: '删除', purge: '彻底删除' }
      const count = this.selectedIds.length
      this.confirmMsg = `确定批量${actionNames[action]} ${count} 个实例？${action === 'reset' ? '所有数据将被清除！' : action === 'purge' ? '容器和数据目录将被一并删除，不可恢复！' : ''}`
      this.confirmShowNginxOption = action === 'reset' && this.isLocalServer() && this.nginxInfo.exists && this.nginxInfo.status === 'running'
      this.confirmShowAdvanced = action === 'reset'
      this.confirmInstId = null
      this.confirmUseNginx = true
      this.confirmImage = ''
      this.confirmCpuLimit = ''
      this.confirmMemLimit = ''
      this.confirmAction = async () => {
        await this.batchAction(action)
      }
      this.confirmVisible = true
    },

    // ===== Nginx 管理 =====
    async loadNginxStatus() {
      try {
        const res = await axios.get(`/servers/${this.currentServer}/nginx`, { headers: this.getAuthHeaders() })
        this.nginxInfo = res.data
      } catch (e) {
        this.nginxInfo = { exists: false, status: 'not_found', image: '', ports: [] }
      }
    },

    async nginxAction(action) {
      this.actionLoading = true
      try {
        const res = await axios.post(`/servers/${this.currentServer}/nginx/${action}`, {}, { headers: this.getAuthHeaders() })
        alert(res.data.msg || '操作成功')
        this.loadNginxStatus()
      } catch (e) {
        alert(e.response?.data?.error || 'nginx操作失败')
      } finally {
        this.actionLoading = false
      }
    },

    // ===== 日志 =====
    async viewLogs(id) {
      this.logId = id
      this.showLogsDialog = true
      await this.refreshLogs()
    },

    async refreshLogs() {
      try {
        const res = await axios.get(`/servers/${this.currentServer}/logs/${this.logId}`, { headers: this.getAuthHeaders() })
        this.logContent = res.data.logs || '暂无日志'
      } catch (e) {
        this.logContent = '获取日志失败: ' + (e.response?.data?.error || e.message)
      }
    },

    closeLogs() {
      this.showLogsDialog = false
      this.logContent = ''
    },

    // ===== 通用 =====
    async doConfirm() {
      this.actionLoading = true
      try {
        await this.confirmAction()
        this.confirmVisible = false
      } catch (e) {
        alert(e.response?.data?.error || '操作失败')
      } finally {
        this.actionLoading = false
      }
    },
  }
}
</script>

<style scoped>
.dashboard {
  min-height: 100vh;
  background: #f0f2f5;
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header h1 {
  font-size: 22px;
  color: #1a1a1a;
  margin: 0;
}

.btn-logout {
  padding: 5px 14px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: #666;
}

.btn-logout:hover { color: #ff4d4f; border-color: #ff4d4f; }

/* 服务器标签页 */
.server-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  align-items: center;
  background: #fff;
  padding: 8px 12px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #555;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.tab:hover { background: #f5f5f5; }

.tab.active {
  background: #1890ff;
  color: #fff;
  border-color: #1890ff;
}

.tab-dot { font-size: 9px; }
.tab-dot.online { color: #52c41a; }
.tab.active .tab-dot.online { color: #b7eb8f; }
.tab-dot.offline { color: #ff4d4f; }
.tab.active .tab-dot.offline { color: #ffa39e; }

.tab-close {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
  opacity: 0.5;
  border-radius: 50%;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tab-close:hover { opacity: 1; background: rgba(0,0,0,0.1); }
.tab.active .tab-close:hover { background: rgba(255,255,255,0.2); }

.tab-add {
  padding: 7px 14px;
  background: none;
  border: 1px dashed #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #999;
}

.tab-add:hover { border-color: #1890ff; color: #1890ff; }

/* Nginx 状态 */
.nginx-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  font-size: 13px;
  color: #666;
  cursor: pointer;
}

.nginx-label { font-weight: 500; }
.nginx-dot { font-size: 10px; }
.nginx-dot.online { color: #52c41a; }
.nginx-dot.offline { color: #ff4d4f; }
.nginx-dot.warning { color: #fa8c16; }
.nginx-text { margin-right: 4px; }

.btn-nginx {
  padding: 2px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  margin-left: 3px;
}

.btn-nginx-start { background: #e6f7ff; color: #1890ff; }
.btn-nginx-start:hover { background: #bae7ff; }
.btn-nginx-stop { background: #fff7e6; color: #fa8c16; }
.btn-nginx-stop:hover { background: #ffe7ba; }
.btn-nginx-restart { background: #f9f0ff; color: #722ed1; }
.btn-nginx-restart:hover { background: #efdbff; }

/* 实例列表 */
.instance-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.table-wrapper {
  overflow-x: auto;
}

.instance-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  table-layout: fixed;
}

.instance-table th {
  text-align: left;
  padding: 10px 8px;
  border-bottom: 2px solid #f0f0f0;
  color: #666;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.instance-table td {
  padding: 8px;
  border-bottom: 1px solid #f5f5f5;
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
}

.instance-table tr:hover { background: #fafafa; }
.instance-table tr.expired-row { background: #fff1f0; }
.instance-table tr.expired-row:hover { background: #ffccc7; }
.instance-table tr.selected-row { background: #e6f7ff; }
.instance-table tr.selected-row:hover { background: #bae7ff; }

.empty {
  text-align: center;
  color: #999;
  padding: 30px !important;
}

/* 列宽 */
.th-check, .td-check { width: 36px; text-align: center; }
.th-id, .td-id { width: 40px; }
.th-name, .td-name { width: 100px; }
.th-port, .td-port { width: 50px; }
.th-status, .td-status { width: 80px; }
.th-link, .td-link { width: 90px; }
.th-date, .td-date { width: 130px; }
.th-note, .td-note { width: 200px; }
.th-actions, .td-actions { width: 220px; position: sticky; right: 0; background: #fff; z-index: 1; }
.instance-table tr:hover .td-actions { background: #fafafa; }
.instance-table tr.expired-row .td-actions { background: #fff1f0; }
.instance-table tr.selected-row .td-actions { background: #e6f7ff; }

.td-actions {
  box-shadow: -2px 0 4px rgba(0,0,0,0.04);
}

.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  white-space: nowrap;
}

.status-badge.running {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.status-badge.exited {
  background: #fff2f0;
  color: #ff4d4f;
  border: 1px solid #ffa39e;
}

.status-badge.expired {
  background: #ff4d4f;
  color: #fff;
  border: 1px solid #cf1322;
  font-weight: bold;
}

/* 访问链接 */
.td-link {
  white-space: nowrap;
}

.link-proxy, .link-direct {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  text-decoration: none;
  margin-right: 4px;
  cursor: pointer;
}

.link-proxy {
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.link-proxy:hover { background: #bae7ff; }

.link-direct {
  background: #f0f0f0;
  color: #666;
  border: 1px solid #d9d9d9;
}

.link-direct:hover { background: #e8e8e8; }

/* 行内编辑 */
.inline-date {
  padding: 4px 6px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  font-size: 13px;
  width: 100%;
  cursor: pointer;
  background: #fafafa;
}

.inline-date:hover { border-color: #1890ff; }
.inline-date:focus { outline: none; border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.2); }
.inline-date.expired-date { border-color: #ff4d4f; background: #fff1f0; }

.inline-note {
  padding: 4px 8px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  font-size: 13px;
  width: 100%;
  background: #fafafa;
  box-sizing: border-box;
}

.inline-note:hover { border-color: #1890ff; }
.inline-note:focus { outline: none; border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.2); background: #fff; }

/* 操作按钮 */
.btn-sm {
  padding: 3px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  margin-right: 3px;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-start { background: #e6f7ff; color: #1890ff; }
.btn-start:hover:not(:disabled) { background: #bae7ff; }
.btn-stop { background: #fff7e6; color: #fa8c16; }
.btn-stop:hover:not(:disabled) { background: #ffe7ba; }
.btn-reset { background: #f9f0ff; color: #722ed1; }
.btn-reset:hover:not(:disabled) { background: #efdbff; }
.btn-delete { background: #fff1f0; color: #ff4d4f; }
.btn-delete:hover:not(:disabled) { background: #ffccc7; }
.btn-logs { background: #e6fffb; color: #13c2c2; }
.btn-logs:hover:not(:disabled) { background: #b5f5ec; }
.btn-purge { background: #ff4d4f; color: #fff; }
.btn-purge:hover:not(:disabled) { background: #ff7875; }
.btn-secondary-sm { background: #f5f5f5; color: #666; border: 1px solid #d9d9d9; }

/* 工具栏 */
.toolbar {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  gap: 10px;
}

.selected-count {
  font-size: 13px;
  color: #1890ff;
  font-weight: 500;
  margin-right: 4px;
}

.btn-batch {
  padding: 5px 14px;
  font-size: 13px;
}

.btn-primary {
  padding: 7px 18px;
  background: #1890ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover { background: #40a9ff; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  padding: 7px 18px;
  background: #fff;
  color: #666;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-secondary:hover { border-color: #1890ff; color: #1890ff; }

.btn-warn {
  padding: 5px 14px;
  background: #fff7e6;
  color: #fa8c16;
  border: 1px solid #ffd591;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.btn-warn:hover { background: #ffe7ba; }

.btn-purple {
  padding: 5px 14px;
  background: #f9f0ff;
  color: #722ed1;
  border: 1px solid #d3adf7;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.btn-purple:hover { background: #efdbff; }

.btn-danger {
  padding: 7px 18px;
  background: #ff4d4f;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-danger:hover { background: #ff7875; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

/* 对话框 */
.overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.45);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog {
  background: #fff;
  border-radius: 10px;
  padding: 24px;
  min-width: 400px;
  max-width: 560px;
  box-shadow: 0 6px 16px rgba(0,0,0,0.15);
}

.dialog h2 {
  font-size: 18px;
  margin: 0 0 20px;
  color: #1a1a1a;
}

.dialog-logs {
  min-width: 700px;
  max-width: 900px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
  color: #333;
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-group input:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24,144,255,0.2);
}

/* 复选框样式 */
.form-group-checkbox {
  display: flex;
  align-items: center;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #1890ff;
}

.checkbox-hint {
  font-size: 12px;
  color: #999;
}

.form-row {
  display: flex;
  gap: 10px;
}

.flex-1 { flex: 1; }
.flex-3 { flex: 3; }

.dialog-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.error-msg {
  color: #ff4d4f;
  font-size: 13px;
  padding: 6px 10px;
  background: #fff2f0;
  border-radius: 4px;
  margin-bottom: 10px;
}

.loading {
  text-align: center;
  padding: 30px;
  color: #999;
  font-size: 15px;
}

/* 日志 */
.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.logs-header h2 { margin: 0; }

.logs-content {
  flex: 1;
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow: auto;
  max-height: 60vh;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
