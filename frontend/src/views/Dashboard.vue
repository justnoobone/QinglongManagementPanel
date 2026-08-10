<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-lockup">
        <div class="brand-mark" aria-hidden="true">
          <el-icon><Grid /></el-icon>
        </div>
        <div>
          <p class="brand-kicker">QINGLONG CONTROL</p>
          <h1>青龙控制台</h1>
        </div>
      </div>

      <div class="topbar-actions">
        <button class="icon-button" title="刷新实例" aria-label="刷新实例" @click="refreshAll">
          <el-icon><Refresh /></el-icon>
        </button>
        <button
          class="icon-button"
          :title="theme === 'dark' ? '切换浅色主题' : '切换深色主题'"
          :aria-label="theme === 'dark' ? '切换浅色主题' : '切换深色主题'"
          @click="toggleTheme"
        >
          <el-icon><Sunny v-if="theme === 'dark'" /><Moon v-else /></el-icon>
        </button>
        <button class="button button-primary" @click="showCreate = true">
          <el-icon><Plus /></el-icon>
          <span>新建实例</span>
        </button>
        <button class="icon-button icon-button-danger" title="退出登录" aria-label="退出登录" @click="logout">
          <el-icon><SwitchButton /></el-icon>
        </button>
      </div>
    </header>

    <main class="main-content">
      <section class="server-strip" aria-label="服务器选择">
        <div class="server-tabs">
          <div
            v-for="server in servers"
            :key="server.id"
            :class="['server-tab', { active: currentServer === server.id }]"
            role="button"
            tabindex="0"
            @click="switchServer(server.id)"
            @keyup.enter="switchServer(server.id)"
          >
            <span :class="['presence-dot', server.online === false ? 'offline' : 'online']"></span>
            <span class="server-tab-name">{{ server.name }}</span>
            <span v-if="server.type === 'local'" class="tab-meta">LOCAL</span>
            <span v-if="server.type === 'remote'" class="server-tab-actions">
              <button
                class="tab-action"
                title="编辑服务器"
                type="button"
                aria-label="编辑服务器"
                @click.stop="openEditServer(server)"
              >
                <el-icon><EditPen /></el-icon>
              </button>
              <button
                class="tab-action danger"
                title="删除服务器"
                type="button"
                aria-label="删除服务器"
                @click.stop="confirmDeleteServer(server)"
              >
                <el-icon><Close /></el-icon>
              </button>
            </span>
          </div>
          <button class="server-add" @click="showAddServer = true">
            <el-icon><Plus /></el-icon>
            <span>添加服务器</span>
          </button>
        </div>

        <div class="nginx-control">
          <div class="nginx-state" @click="loadNginxStatus">
            <span :class="['presence-dot', nginxStatusClass]"></span>
            <span class="nginx-label">Nginx</span>
            <span class="nginx-value">{{ nginxStatusText }}</span>
          </div>
          <button
            v-if="!nginxInfo.exists || nginxInfo.status !== 'running'"
            class="icon-button icon-button-small"
            :title="nginxInfo.exists ? '启动 Nginx' : '部署 Nginx'"
            :aria-label="nginxInfo.exists ? '启动 Nginx' : '部署 Nginx'"
            :disabled="actionLoading"
            @click="handleNginxPrimaryAction"
          >
            <el-icon><VideoPlay /></el-icon>
          </button>
          <button
            v-if="nginxInfo.exists && nginxInfo.status === 'running'"
            class="icon-button icon-button-small"
            title="停止 Nginx"
            aria-label="停止 Nginx"
            :disabled="actionLoading"
            @click="requestNginxAction('stop')"
          >
            <el-icon><VideoPause /></el-icon>
          </button>
          <button
            v-if="nginxInfo.exists"
            class="icon-button icon-button-small"
            title="重启 Nginx"
            aria-label="重启 Nginx"
            :disabled="actionLoading"
            @click="requestNginxAction('restart')"
          >
            <el-icon><RefreshRight /></el-icon>
          </button>
          <button
            v-if="!isLocalServer()"
            class="icon-button icon-button-small"
            title="一键配置 Nginx"
            aria-label="一键配置 Nginx"
            :disabled="actionLoading"
            @click="openNginxSetup"
          >
            <el-icon><Setting /></el-icon>
          </button>
        </div>
      </section>

      <section class="summary-grid" aria-label="运行概览">
        <article class="summary-card">
          <div class="summary-icon blue"><el-icon><Monitor /></el-icon></div>
          <div>
            <p>实例总数</p>
            <strong>{{ instances.length }}</strong>
          </div>
          <span class="summary-caption">{{ currentServerName }}</span>
        </article>
        <article class="summary-card">
          <div class="summary-icon green"><el-icon><CircleCheck /></el-icon></div>
          <div>
            <p>运行中</p>
            <strong>{{ runningCount }}</strong>
          </div>
          <span class="summary-caption">{{ stoppedCount }} 个未运行</span>
        </article>
        <article class="summary-card">
          <div class="summary-icon amber"><el-icon><Connection /></el-icon></div>
          <div>
            <p>反向代理</p>
            <strong class="summary-word">{{ nginxStatusText }}</strong>
          </div>
          <span class="summary-caption">端口 {{ nginxPort }}</span>
        </article>
        <article class="summary-card">
          <div class="summary-icon graphite"><el-icon><Link /></el-icon></div>
          <div>
            <p>管理入口</p>
            <strong class="summary-word">本机</strong>
          </div>
          <a class="summary-link" :href="panelUrl" target="_blank" rel="noreferrer">打开</a>
        </article>
      </section>

      <section class="workspace-panel">
        <div class="section-heading">
          <div>
            <p class="section-kicker">INSTANCES</p>
            <h2>实例管理</h2>
            <p class="section-description">管理容器状态、访问入口、到期时间与运行日志。</p>
          </div>
          <div class="section-actions">
            <span v-if="selectedIds.length" class="selection-count">已选 {{ selectedIds.length }} 项</span>
            <button class="button button-secondary" :disabled="loading" @click="loadInstances">
              <el-icon><Refresh /></el-icon>
              <span>刷新</span>
            </button>
          </div>
        </div>

        <div v-if="error" class="notice notice-error">
          <el-icon><Warning /></el-icon>
          <span>{{ error }}</span>
          <button class="notice-action" @click="loadInstances">重试</button>
        </div>

        <div v-if="loading" class="loading-state">
          <span class="loading-spinner"></span>
          <span>正在读取实例状态</span>
        </div>

        <div v-else-if="!error" class="table-scroll">
          <table class="instance-table">
            <thead>
              <tr>
                <th class="column-check">
                  <input v-model="selectAll" type="checkbox" aria-label="选择全部实例" @change="toggleSelectAll" />
                </th>
                <th>实例</th>
                <th>状态</th>
                <th>端口</th>
                <th>访问入口</th>
                <th>到期日期</th>
                <th>备注</th>
                <th class="column-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="inst in instances"
                :key="inst.id"
                :class="{ selected: selectedIds.includes(inst.id), expired: inst.expired && inst.status === 'running' }"
              >
                <td class="column-check">
                  <input
                    type="checkbox"
                    :aria-label="`选择 ${inst.name}`"
                    :checked="selectedIds.includes(inst.id)"
                    @change="toggleSelect(inst.id)"
                  />
                </td>
                <td>
                  <div class="instance-identity">
                    <div class="instance-avatar">{{ inst.id }}</div>
                    <div>
                      <strong>{{ inst.name }}</strong>
                      <span class="image-name" :title="inst.image || `Qinglong ${inst.id}`">
                        {{ inst.image || `Qinglong ${inst.id}` }}
                      </span>
                    </div>
                  </div>
                </td>
                <td>
                  <span :class="['status-pill', getStatusClass(inst)]">
                    <span class="presence-dot"></span>
                    {{ getStatusText(inst) }}
                  </span>
                </td>
                <td><code class="port-value">{{ inst.port }}</code></td>
                <td>
                  <div class="access-links">
                    <a
                      v-if="inst.use_nginx && nginxInfo.exists && nginxInfo.status === 'running'"
                      :href="getNginxUrl(inst.id)"
                      target="_blank"
                      rel="noreferrer"
                      class="access-link proxy"
                    >
                      <el-icon><Link /></el-icon>
                      <span>代理</span>
                    </a>
                    <a :href="getDirectUrl(inst.port)" target="_blank" rel="noreferrer" class="access-link direct">
                      <el-icon><Monitor /></el-icon>
                      <span>直连</span>
                    </a>
                  </div>
                </td>
                <td>
                  <el-date-picker
                    class="inline-date-picker"
                    :class="{ invalid: inst.expired }"
                    type="date"
                    :model-value="inst.end_date || null"
                    format="YYYY-MM-DD"
                    value-format="YYYY-MM-DD"
                    placeholder="选择日期"
                    clearable
                    @change="updateMetadata(inst, 'end_date', $event || '')"
                  />
                </td>
                <td>
                  <input
                    class="inline-control inline-note"
                    type="text"
                    :value="inst.notes"
                    placeholder="添加备注"
                    @blur="updateMetadata(inst, 'notes', $event.target.value)"
                    @keyup.enter="$event.target.blur()"
                  />
                </td>
                <td class="column-actions">
                  <div class="row-actions">
                    <button
                      v-if="inst.status === 'running'"
                      class="action-icon warning"
                      title="停止实例"
                      aria-label="停止实例"
                      :disabled="actionLoading"
                      @click="doAction('stop', inst.id)"
                    ><el-icon><VideoPause /></el-icon></button>
                    <button
                      v-else
                      class="action-icon success"
                      title="启动实例"
                      aria-label="启动实例"
                      :disabled="actionLoading"
                      @click="doAction('start', inst.id)"
                    ><el-icon><VideoPlay /></el-icon></button>
                    <button class="action-icon" title="查看日志" aria-label="查看日志" @click="viewLogs(inst.id)">
                      <el-icon><Document /></el-icon>
                    </button>
                    <button
                      class="action-icon"
                      title="重置实例"
                      aria-label="重置实例"
                      :disabled="actionLoading"
                      @click="confirmInstanceAction('reset', inst.id)"
                    ><el-icon><RefreshRight /></el-icon></button>
                    <button
                      class="action-icon danger"
                      title="删除实例"
                      aria-label="删除实例"
                      :disabled="actionLoading"
                      @click="confirmInstanceAction('delete', inst.id)"
                    ><el-icon><Delete /></el-icon></button>
                    <button
                      class="action-icon danger-solid"
                      title="彻底删除实例和数据"
                      aria-label="彻底删除实例和数据"
                      :disabled="actionLoading"
                      @click="confirmInstanceAction('purge', inst.id)"
                    ><el-icon><DeleteFilled /></el-icon></button>
                  </div>
                </td>
              </tr>
              <tr v-if="instances.length === 0">
                <td colspan="8">
                  <div class="empty-state">
                    <div class="empty-icon"><el-icon><Box /></el-icon></div>
                    <h3>还没有发现青龙实例</h3>
                    <p>确认 Docker 服务正常，或创建一个新的本机实例。</p>
                    <button class="button button-primary" @click="showCreate = true">
                      <el-icon><Plus /></el-icon>
                      <span>新建实例</span>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="selectedIds.length" class="batch-bar">
          <span>{{ selectedIds.length }} 个实例</span>
          <div class="batch-actions">
            <button class="button button-compact button-success" :disabled="actionLoading" @click="batchAction('start')">
              <el-icon><VideoPlay /></el-icon><span>启动</span>
            </button>
            <button class="button button-compact button-warning" :disabled="actionLoading" @click="batchAction('stop')">
              <el-icon><VideoPause /></el-icon><span>停止</span>
            </button>
            <button class="button button-compact button-secondary" :disabled="actionLoading" @click="confirmBatchAction('reset')">
              <el-icon><RefreshRight /></el-icon><span>重置</span>
            </button>
            <button class="button button-compact button-danger" :disabled="actionLoading" @click="confirmBatchAction('delete')">
              <el-icon><Delete /></el-icon><span>删除</span>
            </button>
            <button class="button button-compact button-danger-solid" :disabled="actionLoading" @click="confirmBatchAction('purge')">
              <el-icon><DeleteFilled /></el-icon><span>彻底删除</span>
            </button>
            <button class="icon-button icon-button-small" title="取消选择" aria-label="取消选择" @click="clearSelection">
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </div>
      </section>
    </main>

    <div v-if="showCreate" class="modal-backdrop" @click.self="showCreate = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="create-title">
        <div class="modal-header">
          <div><p class="section-kicker">NEW INSTANCE</p><h2 id="create-title">新建实例</h2></div>
          <button class="icon-button icon-button-small" title="关闭" aria-label="关闭" @click="showCreate = false"><el-icon><Close /></el-icon></button>
        </div>
        <div class="modal-body">
          <div class="form-grid two-columns">
            <label class="field"><span>实例编号</span><input v-model.number="createNum" type="number" min="0" placeholder="例如 2" /></label>
            <label class="field date-field"><span>到期日期</span><el-date-picker v-model="createEndDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" placeholder="选择日期" clearable /></label>
          </div>
          <label class="field"><span>备注</span><input v-model="createNotes" type="text" placeholder="用途、负责人或客户名称" /></label>
          <label class="field"><span>镜像</span><input v-model="createImage" type="text" :placeholder="`默认 ${getDefaultImageHint()}`" /></label>
          <div class="form-grid two-columns">
            <label class="field"><span>CPU 核数</span><input v-model="createCpuLimit" type="number" min="0.1" step="0.1" placeholder="1" /></label>
            <label class="field"><span>内存限制</span><input v-model="createMemLimit" type="text" placeholder="1g" /></label>
          </div>
          <label v-if="nginxInfo.exists && nginxInfo.status === 'running'" class="toggle-row">
            <span><strong>启用 Nginx 反代</strong><small>通过 :91/qlN/ 访问该实例</small></span>
            <input v-model="createUseNginx" type="checkbox" role="switch" />
          </label>
        </div>
        <div class="modal-footer">
          <button class="button button-secondary" @click="showCreate = false">取消</button>
          <button class="button button-primary" :disabled="actionLoading" @click="doCreate">
            <span>{{ actionLoading ? '创建中' : '创建实例' }}</span>
          </button>
        </div>
      </section>
    </div>

    <div v-if="showAddServer" class="modal-backdrop" @click.self="showAddServer = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="server-title">
        <div class="modal-header">
          <div><p class="section-kicker">REMOTE HOST</p><h2 id="server-title">添加远程服务器</h2></div>
          <button class="icon-button icon-button-small" title="关闭" aria-label="关闭" @click="showAddServer = false"><el-icon><Close /></el-icon></button>
        </div>
        <div class="modal-body">
          <label class="field"><span>服务器名称</span><input v-model="newServer.name" placeholder="例如 上海节点" /></label>
          <div class="form-grid host-columns">
            <label class="field"><span>主机地址</span><input v-model="newServer.host" placeholder="IP 或域名" /></label>
            <label class="field"><span>SSH 端口</span><input v-model.number="newServer.port" type="number" placeholder="22" /></label>
          </div>
          <div class="form-grid two-columns">
            <label class="field"><span>用户名</span><input v-model="newServer.username" placeholder="root" /></label>
            <label class="field"><span>密码</span><input v-model="newServer.password" type="password" autocomplete="new-password" /></label>
          </div>
          <label class="field"><span>青龙数据路径</span><input v-model="newServer.path" placeholder="/home/docker/qinglong" /></label>
          <label class="toggle-row">
            <span><strong>添加后配置 Nginx</strong><small>仅打开配置窗口，不会自动部署或重启服务</small></span>
            <input v-model="configureNginxAfterAdd" type="checkbox" role="switch" />
          </label>
          <div v-if="addServerError" class="notice notice-error"><el-icon><Warning /></el-icon><span>{{ addServerError }}</span></div>
        </div>
        <div class="modal-footer">
          <button class="button button-secondary" @click="showAddServer = false">取消</button>
          <button class="button button-primary" :disabled="actionLoading" @click="doAddServer">
            <span>{{ actionLoading ? '连接中' : '测试并添加' }}</span>
          </button>
        </div>
      </section>
    </div>

    <div v-if="showEditServer" class="modal-backdrop" @click.self="showEditServer = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="edit-server-title">
        <div class="modal-header">
          <div><p class="section-kicker">SERVER SETTINGS</p><h2 id="edit-server-title">编辑远程服务器</h2></div>
          <button class="icon-button icon-button-small" title="关闭" aria-label="关闭" @click="showEditServer = false"><el-icon><Close /></el-icon></button>
        </div>
        <div class="modal-body">
          <label class="field"><span>服务器名称</span><input v-model="editServer.name" placeholder="服务器名称" /></label>
          <div class="form-grid host-columns">
            <label class="field"><span>主机地址</span><input v-model="editServer.host" placeholder="IP 或域名" /></label>
            <label class="field"><span>SSH 端口</span><input v-model.number="editServer.port" type="number" min="1" max="65535" placeholder="22" /></label>
          </div>
          <div class="form-grid two-columns">
            <label class="field"><span>用户名</span><input v-model="editServer.username" placeholder="root" /></label>
            <label class="field"><span>新密码</span><input v-model="editServer.password" type="password" autocomplete="new-password" placeholder="留空则保持原密码" /></label>
          </div>
          <label class="field"><span>青龙数据路径</span><input v-model="editServer.path" placeholder="/home/docker/qinglong" /></label>
          <div v-if="editServerError" class="notice notice-error"><el-icon><Warning /></el-icon><span>{{ editServerError }}</span></div>
        </div>
        <div class="modal-footer">
          <button class="button button-secondary" @click="showEditServer = false">取消</button>
          <button class="button button-primary" :disabled="actionLoading" @click="doEditServer">
            <span>{{ actionLoading ? '保存中' : '保存修改' }}</span>
          </button>
        </div>
      </section>
    </div>

    <div v-if="showNginxSetup" class="modal-backdrop" @click.self="showNginxSetup = false">
      <section class="modal modal-wide nginx-setup-modal" role="dialog" aria-modal="true" aria-labelledby="nginx-setup-title">
        <div class="modal-header">
          <div><p class="section-kicker">NGINX AUTOMATION</p><h2 id="nginx-setup-title">一键配置远程 Nginx</h2></div>
          <button class="icon-button icon-button-small" title="关闭" aria-label="关闭" @click="showNginxSetup = false"><el-icon><Close /></el-icon></button>
        </div>
        <div class="modal-body nginx-setup-body">
          <div class="nginx-target-card">
            <span :class="['presence-dot', nginxStatusClass]"></span>
            <div><strong>{{ currentServerName }}</strong><small>{{ getCurrentHost() }} · 当前 {{ nginxStatusText }}</small></div>
          </div>
          <div class="form-grid two-columns">
            <label class="field"><span>Nginx 镜像版本</span><input v-model="nginxForm.image" placeholder="nginx:1.29.7-alpine" /></label>
            <label class="field"><span>宿主机端口</span><input v-model.number="nginxForm.port" type="number" min="1" max="65535" placeholder="91" /></label>
          </div>
          <label class="field"><span>配置与日志目录</span><input v-model="nginxForm.path" placeholder="/home/docker/nginx" /></label>

          <div class="deployment-steps" aria-label="部署内容">
            <div><span>1</span><p><strong>拉取并校验</strong><small>拉取指定镜像，先执行 nginx -t</small></p></div>
            <div><span>2</span><p><strong>接入容器网络</strong><small>将 Nginx 与青龙实例连接到 ql_net</small></p></div>
            <div><span>3</span><p><strong>短暂切换</strong><small>新容器失败时自动尝试恢复原容器</small></p></div>
          </div>

          <div class="notice notice-warning nginx-warning">
            <el-icon><Warning /></el-icon>
            <span>部署只作用于 <strong>{{ currentServerName }}</strong>。切换已有 Nginx 时预计会有数秒不可访问，请在维护窗口执行。</span>
          </div>

          <div v-if="nginxPreview" class="config-preview-wrap">
            <div class="config-preview-header"><span>生成配置预览</span><button class="notice-action" @click="nginxPreview = ''">收起</button></div>
            <pre class="config-preview">{{ nginxPreview }}</pre>
          </div>
        </div>
        <div class="modal-footer nginx-modal-footer">
          <button class="button button-secondary" :disabled="actionLoading" @click="previewNginxConfig">
            <el-icon><View /></el-icon><span>预览配置</span>
          </button>
          <span class="modal-footer-spacer"></span>
          <button class="button button-secondary" @click="showNginxSetup = false">取消</button>
          <button class="button button-primary" :disabled="actionLoading" @click="confirmNginxDeploy">
            <el-icon><Setting /></el-icon><span>保存并部署</span>
          </button>
        </div>
      </section>
    </div>

    <div v-if="showLogsDialog" class="modal-backdrop" @click.self="closeLogs">
      <section class="modal modal-wide modal-log" role="dialog" aria-modal="true" aria-labelledby="logs-title">
        <div class="modal-header">
          <div><p class="section-kicker">LIVE OUTPUT</p><h2 id="logs-title">{{ logInstanceName }} 日志</h2></div>
          <div class="modal-header-actions">
            <button class="icon-button icon-button-small" title="刷新日志" aria-label="刷新日志" @click="refreshLogs"><el-icon><Refresh /></el-icon></button>
            <button class="icon-button icon-button-small" title="关闭" aria-label="关闭" @click="closeLogs"><el-icon><Close /></el-icon></button>
          </div>
        </div>
        <pre class="log-console">{{ logContent }}</pre>
      </section>
    </div>

    <div v-if="confirmVisible" class="modal-backdrop">
      <section class="modal modal-compact" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <div class="modal-header">
          <div><p class="section-kicker danger-text">CONFIRM ACTION</p><h2 id="confirm-title">确认操作</h2></div>
        </div>
        <div class="modal-body">
          <p class="confirm-message">{{ confirmMsg }}</p>
          <label v-if="confirmShowNginxOption" class="toggle-row">
            <span><strong>启用 Nginx 反代</strong><small>重建后保留 :91/qlN/ 入口</small></span>
            <input v-model="confirmUseNginx" type="checkbox" role="switch" />
          </label>
          <template v-if="confirmShowAdvanced">
            <label class="field"><span>镜像</span><input v-model="confirmImage" type="text" :placeholder="`默认 ${getDefaultResetImageHint()}`" /></label>
            <div class="form-grid two-columns">
              <label class="field"><span>CPU 核数</span><input v-model="confirmCpuLimit" type="number" min="0.1" step="0.1" placeholder="1" /></label>
              <label class="field"><span>内存限制</span><input v-model="confirmMemLimit" type="text" placeholder="1g" /></label>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button class="button button-secondary" @click="confirmVisible = false">取消</button>
          <button class="button button-danger-solid" :disabled="actionLoading" @click="doConfirm">确认执行</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import { ElMessage } from 'element-plus'
import {
  Box,
  CircleCheck,
  Close,
  Connection,
  Delete,
  DeleteFilled,
  Document,
  EditPen,
  Grid,
  Link,
  Monitor,
  Moon,
  Plus,
  Refresh,
  RefreshRight,
  Setting,
  Sunny,
  SwitchButton,
  View,
  VideoPause,
  VideoPlay,
  Warning,
} from '@element-plus/icons-vue'

export default {
  name: 'Dashboard',
  components: {
    Box,
    CircleCheck,
    Close,
    Connection,
    Delete,
    DeleteFilled,
    Document,
    EditPen,
    Grid,
    Link,
    Monitor,
    Moon,
    Plus,
    Refresh,
    RefreshRight,
    Setting,
    Sunny,
    SwitchButton,
    View,
    VideoPause,
    VideoPlay,
    Warning,
  },
  data() {
    return {
      theme: localStorage.getItem('ql-control-theme') || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
      servers: [],
      currentServer: 'local',
      instances: [],
      loading: false,
      actionLoading: false,
      error: '',
      selectedIds: [],
      selectAll: false,
      nginxInfo: { exists: false, status: 'not_found', image: '', ports: [] },
      showCreate: false,
      createNum: null,
      createEndDate: '',
      createNotes: '',
      createUseNginx: true,
      createImage: '',
      createCpuLimit: '',
      createMemLimit: '',
      showAddServer: false,
      addServerError: '',
      newServer: { name: '', host: '', port: 22, username: 'root', password: '', path: '/home/docker/qinglong' },
      configureNginxAfterAdd: false,
      showEditServer: false,
      editServerId: '',
      editServerError: '',
      editServer: { name: '', host: '', port: 22, username: 'root', password: '', path: '/home/docker/qinglong' },
      showNginxSetup: false,
      nginxPreview: '',
      nginxForm: { image: 'nginx:1.29.7-alpine', port: 91, path: '/home/docker/nginx' },
      showLogsDialog: false,
      logId: null,
      logContent: '',
      confirmVisible: false,
      confirmMsg: '',
      confirmHandler: null,
      confirmUseNginx: true,
      confirmShowNginxOption: false,
      confirmShowAdvanced: false,
      confirmInstId: null,
      confirmImage: '',
      confirmCpuLimit: '',
      confirmMemLimit: '',
    }
  },
  computed: {
    runningCount() {
      return this.instances.filter((instance) => instance.status === 'running').length
    },
    stoppedCount() {
      return Math.max(0, this.instances.length - this.runningCount)
    },
    currentServerName() {
      return this.servers.find((server) => server.id === this.currentServer)?.name || '本机'
    },
    nginxStatusText() {
      if (!this.nginxInfo.exists) return '未部署'
      return this.nginxInfo.status === 'running' ? '运行中' : '已停止'
    },
    nginxStatusClass() {
      if (!this.nginxInfo.exists) return 'offline'
      return this.nginxInfo.status === 'running' ? 'online' : 'warning'
    },
    nginxPort() {
      if (this.nginxInfo.configured_port) return this.nginxInfo.configured_port
      const mapped = this.nginxInfo.ports?.find((port) => String(port).endsWith(':80'))
      return mapped ? String(mapped).split(':')[0] : 91
    },
    panelUrl() {
      return `${window.location.protocol}//${window.location.hostname}/`
    },
    logInstanceName() {
      return this.instances.find((instance) => instance.id === this.logId)?.name || `qinglong${this.logId ?? ''}`
    },
  },
  created() {
    this.applyTheme()
    this.loadServers()
  },
  methods: {
    applyTheme() {
      document.documentElement.dataset.theme = this.theme
      document.documentElement.classList.toggle('dark', this.theme === 'dark')
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('ql-control-theme', this.theme)
      this.applyTheme()
    },
    getAuthHeaders() {
      return { Authorization: `Bearer ${localStorage.getItem('token')}` }
    },
    notify(message, type = 'success') {
      ElMessage({ message, type, duration: 2400 })
    },
    logout() {
      localStorage.removeItem('token')
      this.$router.push('/login')
    },
    refreshAll() {
      this.loadInstances()
      this.loadNginxStatus()
    },
    getCurrentHost() {
      if (this.isLocalServer()) return window.location.hostname
      return this.servers.find((server) => server.id === this.currentServer)?.host || window.location.hostname
    },
    getDirectUrl(port) {
      return `http://${this.getCurrentHost()}:${port}/`
    },
    getNginxUrl(id) {
      return `http://${this.getCurrentHost()}:${this.nginxPort}/ql${id}/`
    },
    isLocalServer() {
      return this.currentServer === 'local'
    },
    getDefaultImageHint() {
      return this.createNum === 0 ? 'whyour/qinglong:debian-python3.10' : 'whyour/qinglong:latest'
    },
    getDefaultResetImageHint() {
      return this.confirmInstId === 0 ? 'whyour/qinglong:debian-python3.10' : 'whyour/qinglong:latest'
    },
    getStatusText(instance) {
      if (instance.expired && instance.status === 'running') return '已过期'
      const labels = { running: '运行中', exited: '已停止', restarting: '重启中', paused: '已暂停', created: '待启动', dead: '异常' }
      return labels[instance.status] || instance.status
    },
    getStatusClass(instance) {
      if (instance.expired && instance.status === 'running') return 'expired'
      if (instance.status === 'running') return 'running'
      if (instance.status === 'restarting' || instance.status === 'created') return 'pending'
      return 'stopped'
    },
    async loadServers() {
      try {
        const response = await axios.get('/servers', { headers: this.getAuthHeaders() })
        this.servers = response.data
        if (!this.servers.some((server) => server.id === this.currentServer)) {
          this.currentServer = this.servers[0]?.id || 'local'
        }
        await this.loadInstances()
        await this.loadNginxStatus()
      } catch (error) {
        if (error.response?.status === 401) this.logout()
        else this.error = error.response?.data?.error || '服务器列表加载失败'
      }
    },
    async switchServer(serverId) {
      this.currentServer = serverId
      this.error = ''
      this.clearSelection()
      await Promise.all([this.loadInstances(), this.loadNginxStatus()])
    },
    async doAddServer() {
      this.addServerError = ''
      if (!this.newServer.name || !this.newServer.host) {
        this.addServerError = '服务器名称和地址不能为空'
        return
      }
      this.actionLoading = true
      try {
        const shouldConfigureNginx = this.configureNginxAfterAdd
        const response = await axios.post('/servers', this.newServer, { headers: this.getAuthHeaders() })
        const addedServerId = response.data?.id
        this.showAddServer = false
        this.newServer = { name: '', host: '', port: 22, username: 'root', password: '', path: '/home/docker/qinglong' }
        this.configureNginxAfterAdd = false
        this.notify('服务器已添加')
        await this.loadServers()
        if (addedServerId) await this.switchServer(addedServerId)
        if (shouldConfigureNginx && addedServerId) this.openNginxSetup()
      } catch (error) {
        this.addServerError = error.response?.data?.error || '添加失败'
      } finally {
        this.actionLoading = false
      }
    },
    openEditServer(server) {
      this.editServerId = server.id
      this.editServerError = ''
      this.editServer = {
        name: server.name || '',
        host: server.host || '',
        port: server.port || 22,
        username: server.username || 'root',
        password: '',
        path: server.path || '/home/docker/qinglong',
      }
      this.showEditServer = true
    },
    async doEditServer() {
      this.editServerError = ''
      if (!this.editServer.name || !this.editServer.host) {
        this.editServerError = '服务器名称和地址不能为空'
        return
      }
      this.actionLoading = true
      try {
        await axios.put(`/servers/${this.editServerId}`, this.editServer, { headers: this.getAuthHeaders() })
        this.showEditServer = false
        this.notify('服务器配置已更新')
        await this.loadServers()
      } catch (error) {
        this.editServerError = error.response?.data?.error || '保存失败'
      } finally {
        this.actionLoading = false
      }
    },
    confirmDeleteServer(server) {
      this.confirmMsg = `确定删除服务器“${server.name}”？远程服务器上的容器不会受到影响。`
      this.confirmShowNginxOption = false
      this.confirmShowAdvanced = false
      this.confirmHandler = async () => {
        await axios.delete(`/servers/${server.id}`, { headers: this.getAuthHeaders() })
        await this.loadServers()
        this.notify('服务器已移除')
      }
      this.confirmVisible = true
    },
    async loadInstances() {
      this.loading = true
      this.error = ''
      try {
        const response = await axios.get(`/servers/${this.currentServer}/instances`, { headers: this.getAuthHeaders() })
        this.instances = response.data
        const ids = this.instances.map((instance) => instance.id)
        this.selectedIds = this.selectedIds.filter((id) => ids.includes(id))
        this.selectAll = ids.length > 0 && ids.every((id) => this.selectedIds.includes(id))
      } catch (error) {
        this.error = error.response?.data?.error || '实例列表加载失败'
        if (error.response?.status === 401) this.logout()
      } finally {
        this.loading = false
      }
    },
    async updateMetadata(instance, field, value) {
      instance[field] = value
      try {
        await axios.put(`/servers/${this.currentServer}/instances/${instance.id}/metadata`, {
          start_date: instance.start_date || '',
          end_date: instance.end_date || '',
          notes: instance.notes || '',
        }, { headers: this.getAuthHeaders() })
        if (field === 'end_date') await this.loadInstances()
      } catch (error) {
        this.notify(error.response?.data?.error || '元数据更新失败', 'error')
      }
    },
    async doCreate() {
      if (this.createNum === null || this.createNum === '') {
        this.notify('请输入实例编号', 'warning')
        return
      }
      this.actionLoading = true
      try {
        const payload = { end_date: this.createEndDate, notes: this.createNotes, use_nginx: this.createUseNginx }
        if (this.createImage) payload.image = this.createImage
        if (this.createCpuLimit) payload.cpu_limit = Number(this.createCpuLimit) * 1000000000
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
        this.notify('实例已创建')
        await this.loadInstances()
      } catch (error) {
        this.notify(error.response?.data?.error || '创建失败', 'error')
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
          if (this.confirmCpuLimit) payload.cpu_limit = Number(this.confirmCpuLimit) * 1000000000
          if (this.confirmMemLimit) payload.mem_limit = this.confirmMemLimit
          await axios.post(`/servers/${this.currentServer}/reset/${id}`, payload, { headers: this.getAuthHeaders() })
        } else {
          await axios.post(`/servers/${this.currentServer}/${action}/${id}`, {}, { headers: this.getAuthHeaders() })
        }
        this.notify({ start: '实例已启动', stop: '实例已停止', reset: '实例已重置', delete: '容器已删除', purge: '实例与数据已删除' }[action] || '操作完成')
        await this.loadInstances()
      } catch (error) {
        this.notify(error.response?.data?.error || `${action} 失败`, 'error')
      } finally {
        this.actionLoading = false
      }
    },
    confirmInstanceAction(action, id) {
      const labels = { reset: '重置', delete: '删除', purge: '彻底删除' }
      const suffix = action === 'delete' ? '数据目录会保留。' : action === 'purge' ? '容器和数据目录都将删除且无法恢复。' : '现有数据将被清除。'
      this.confirmMsg = `确定${labels[action]}实例 ${this.instances.find((item) => item.id === id)?.name || id}？${suffix}`
      this.confirmShowNginxOption = action === 'reset' && this.nginxInfo.status === 'running'
      this.confirmShowAdvanced = action === 'reset'
      this.confirmInstId = id
      this.confirmUseNginx = true
      this.confirmImage = ''
      this.confirmCpuLimit = ''
      this.confirmMemLimit = ''
      this.confirmHandler = () => this.doAction(action, id)
      this.confirmVisible = true
    },
    toggleSelectAll() {
      this.selectedIds = this.selectAll ? this.instances.map((instance) => instance.id) : []
    },
    toggleSelect(id) {
      this.selectedIds = this.selectedIds.includes(id) ? this.selectedIds.filter((item) => item !== id) : [...this.selectedIds, id]
      this.selectAll = this.instances.length > 0 && this.instances.every((instance) => this.selectedIds.includes(instance.id))
    },
    clearSelection() {
      this.selectedIds = []
      this.selectAll = false
    },
    async batchAction(action) {
      if (!this.selectedIds.length) return
      this.actionLoading = true
      try {
        const payload = { nums: this.selectedIds }
        if (action === 'reset') {
          payload.use_nginx = this.confirmUseNginx
          if (this.confirmImage) payload.image = this.confirmImage
          if (this.confirmCpuLimit) payload.cpu_limit = Number(this.confirmCpuLimit) * 1000000000
          if (this.confirmMemLimit) payload.mem_limit = this.confirmMemLimit
        }
        const response = await axios.post(`/servers/${this.currentServer}/batch/${action}`, payload, { headers: this.getAuthHeaders() })
        const failed = response.data.results?.failed || []
        if (failed.length) this.notify(`${response.data.msg}，${failed.length} 项失败`, 'warning')
        else this.notify(response.data.msg || '批量操作完成')
        this.clearSelection()
        await this.loadInstances()
      } catch (error) {
        this.notify(error.response?.data?.error || '批量操作失败', 'error')
      } finally {
        this.actionLoading = false
      }
    },
    confirmBatchAction(action) {
      const labels = { reset: '重置', delete: '删除', purge: '彻底删除' }
      const suffix = action === 'purge' ? '容器与数据目录都将被删除且无法恢复。' : action === 'reset' ? '现有数据将被清除。' : ''
      this.confirmMsg = `确定批量${labels[action]} ${this.selectedIds.length} 个实例？${suffix}`
      this.confirmShowNginxOption = action === 'reset' && this.nginxInfo.status === 'running'
      this.confirmShowAdvanced = action === 'reset'
      this.confirmInstId = null
      this.confirmUseNginx = true
      this.confirmImage = ''
      this.confirmCpuLimit = ''
      this.confirmMemLimit = ''
      this.confirmHandler = () => this.batchAction(action)
      this.confirmVisible = true
    },
    async loadNginxStatus() {
      try {
        const response = await axios.get(`/servers/${this.currentServer}/nginx`, { headers: this.getAuthHeaders() })
        this.nginxInfo = response.data
      } catch {
        const server = this.servers.find((item) => item.id === this.currentServer)
        this.nginxInfo = {
          exists: false,
          status: 'not_found',
          image: server?.nginx_image || '',
          ports: [],
          configured_port: server?.nginx_port || 91,
          configured_path: server?.nginx_path || '/home/docker/nginx',
        }
      }
    },
    handleNginxPrimaryAction() {
      if (this.nginxInfo.exists) {
        this.nginxAction('start')
      } else if (this.isLocalServer()) {
        this.nginxAction('create')
      } else {
        this.openNginxSetup()
      }
    },
    requestNginxAction(action) {
      if (this.isLocalServer()) {
        this.nginxAction(action)
        return
      }
      const label = action === 'stop' ? '停止' : '重启'
      this.confirmMsg = `确定${label}“${this.currentServerName}”上的 Nginx？代理入口会短暂不可访问。`
      this.confirmShowNginxOption = false
      this.confirmShowAdvanced = false
      this.confirmHandler = () => this.nginxAction(action)
      this.confirmVisible = true
    },
    openNginxSetup() {
      const server = this.servers.find((item) => item.id === this.currentServer) || {}
      this.nginxForm = {
        image: server.nginx_image || this.nginxInfo.image || 'nginx:1.29.7-alpine',
        port: server.nginx_port || this.nginxInfo.configured_port || 91,
        path: server.nginx_path || this.nginxInfo.configured_path || '/home/docker/nginx',
      }
      this.nginxPreview = ''
      this.showNginxSetup = true
    },
    async previewNginxConfig() {
      this.actionLoading = true
      try {
        const response = await axios.get(`/servers/${this.currentServer}/nginx/preview`, { headers: this.getAuthHeaders() })
        this.nginxPreview = response.data.config || '# 暂无配置'
      } catch (error) {
        this.notify(error.response?.data?.error || '配置预览失败', 'error')
      } finally {
        this.actionLoading = false
      }
    },
    confirmNginxDeploy() {
      if (!this.nginxForm.image || !this.nginxForm.port || !this.nginxForm.path) {
        this.notify('请填写完整的 Nginx 配置', 'warning')
        return
      }
      this.confirmMsg = `将在“${this.currentServerName}”上拉取 ${this.nginxForm.image}，使用端口 ${this.nginxForm.port} 部署 Nginx。若已有同名容器，会在配置校验通过后短暂切换。确定继续？`
      this.confirmShowNginxOption = false
      this.confirmShowAdvanced = false
      this.confirmHandler = () => this.deployRemoteNginx()
      this.confirmVisible = true
    },
    async deployRemoteNginx() {
      this.actionLoading = true
      try {
        const response = await axios.post(`/servers/${this.currentServer}/nginx/deploy`, this.nginxForm, { headers: this.getAuthHeaders() })
        this.notify(response.data.msg || 'Nginx 已部署')
        this.showNginxSetup = false
        await this.loadServers()
      } catch (error) {
        throw error
      } finally {
        this.actionLoading = false
      }
    },
    async nginxAction(action) {
      this.actionLoading = true
      try {
        const response = await axios.post(`/servers/${this.currentServer}/nginx/${action}`, {}, { headers: this.getAuthHeaders() })
        this.notify(response.data.msg || 'Nginx 操作完成')
        await this.loadNginxStatus()
        await this.loadInstances()
      } catch (error) {
        this.notify(error.response?.data?.error || 'Nginx 操作失败', 'error')
      } finally {
        this.actionLoading = false
      }
    },
    async viewLogs(id) {
      this.logId = id
      this.showLogsDialog = true
      await this.refreshLogs()
    },
    async refreshLogs() {
      try {
        const response = await axios.get(`/servers/${this.currentServer}/logs/${this.logId}`, { headers: this.getAuthHeaders() })
        this.logContent = response.data.logs || '暂无日志'
      } catch (error) {
        this.logContent = `获取日志失败: ${error.response?.data?.error || error.message}`
      }
    },
    closeLogs() {
      this.showLogsDialog = false
      this.logContent = ''
    },
    async doConfirm() {
      if (!this.confirmHandler) return
      try {
        await this.confirmHandler()
        this.confirmVisible = false
      } catch (error) {
        this.notify(error.response?.data?.error || '操作失败', 'error')
      }
    },
  },
}
</script>
