<template>
  <div class="login-page">
    <main class="login-card">
      <div class="login-brand">
        <div class="login-mark"><el-icon><Grid /></el-icon></div>
        <p>QINGLONG CONTROL</p>
        <h1>欢迎回来</h1>
        <span>登录青龙多实例控制台</span>
      </div>

      <form class="login-form" @submit.prevent="doLogin">
        <label class="field login-field">
          <span>用户名</span>
          <div class="input-with-icon">
            <el-icon><User /></el-icon>
            <input
              v-model.trim="username"
              :disabled="loading || lockdown"
              autocomplete="username"
              autofocus
              placeholder="输入用户名"
            />
          </div>
        </label>
        <label class="field login-field">
          <span>密码</span>
          <div class="input-with-icon">
            <el-icon><Lock /></el-icon>
            <input
              v-model="password"
              type="password"
              :disabled="loading || lockdown"
              autocomplete="current-password"
              placeholder="输入密码"
            />
          </div>
        </label>

        <div v-if="error" class="notice notice-error login-error">
          <el-icon><Warning /></el-icon>
          <span>{{ error }}</span>
        </div>

        <button class="button button-primary login-button" type="submit" :disabled="loading || lockdown">
          <span>{{ lockdown ? `请稍候 ${lockdownCountdown}s` : (loading ? '正在登录' : '登录控制台') }}</span>
          <el-icon v-if="!loading && !lockdown"><Right /></el-icon>
          <span v-else-if="loading" class="button-spinner"></span>
        </button>
      </form>

      <div class="login-footer">
        <span class="presence-dot online"></span>
        <span>Secure local console</span>
      </div>
    </main>
  </div>
</template>

<script>
import axios from 'axios'
import { Grid, Lock, Right, User, Warning } from '@element-plus/icons-vue'

export default {
  name: 'Login',
  components: { Grid, Lock, Right, User, Warning },
  data() {
    return {
      username: '',
      password: '',
      error: '',
      loading: false,
      lockdown: false,
      lockdownCountdown: 0,
      lockdownTimer: null,
    }
  },
  beforeUnmount() {
    if (this.lockdownTimer) clearInterval(this.lockdownTimer)
  },
  methods: {
    startLockdown(seconds) {
      this.lockdown = true
      this.lockdownCountdown = seconds
      if (this.lockdownTimer) clearInterval(this.lockdownTimer)
      this.lockdownTimer = setInterval(() => {
        this.lockdownCountdown -= 1
        if (this.lockdownCountdown <= 0) {
          this.lockdown = false
          clearInterval(this.lockdownTimer)
          this.lockdownTimer = null
          this.error = ''
        }
      }, 1000)
    },
    async doLogin() {
      if (this.lockdown || this.loading) return
      if (!this.username || !this.password) {
        this.error = '请输入用户名和密码'
        return
      }

      this.loading = true
      this.error = ''
      try {
        const response = await axios.post('/login', { username: this.username, password: this.password })
        localStorage.setItem('token', response.data.token)
        this.$router.push('/')
      } catch (error) {
        const data = error.response?.data || {}
        if (error.response?.status === 429) {
          const match = data.error?.match(/(\d+)/)
          this.error = data.error || '登录失败次数过多，请稍后重试'
          this.startLockdown(match ? Number(match[1]) : 300)
        } else if (error.response) {
          this.error = data.error || '登录失败'
          if (data.attempts_left > 0 && data.attempts_left <= 2) {
            this.error += `（还剩 ${data.attempts_left} 次尝试）`
          } else if (data.attempts_left === 0) {
            this.error = '登录失败次数过多，请稍后重试'
            this.startLockdown(5)
          }
        } else {
          this.error = '无法连接到控制台服务'
        }
      } finally {
        this.loading = false
      }
    },
  },
}
</script>
