<template>
  <div class="login-page">
    <div class="login-card">
      <h1>青龙管理面板</h1>
      <div class="form-group">
        <label>用户名</label>
        <input v-model="username" :disabled="loading || lockdown" placeholder="请输入用户名" @keyup.enter="doLogin">
      </div>
      <div class="form-group">
        <label>密码</label>
        <input v-model="password" type="password" :disabled="loading || lockdown" placeholder="请输入密码" @keyup.enter="doLogin">
      </div>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <button class="btn-login" :disabled="loading || lockdown" @click="doLogin">
        {{ lockdown ? `锁定中 (${lockdownCountdown}s)` : (loading ? '登录中...' : '登录') }}
      </button>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'Login',
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
        const res = await axios.post('/login', {
          username: this.username,
          password: this.password,
        })
        localStorage.setItem('token', res.data.token)
        this.$router.push('/')
      } catch (e) {
        const data = e.response?.data || {}
        if (e.response?.status === 429) {
          const match = data.error?.match(/(\d+)/)
          const seconds = match ? parseInt(match[1], 10) : 300
          this.error = data.error || '登录失败次数过多，请稍后重试'
          this.startLockdown(seconds)
        } else if (e.response) {
          this.error = data.error || '登录失败'
          if (data.attempts_left !== undefined && data.attempts_left <= 2 && data.attempts_left > 0) {
            this.error += `（还剩 ${data.attempts_left} 次尝试机会）`
          } else if (data.attempts_left === 0) {
            this.error = '登录失败次数过多，请稍后重试'
            this.startLockdown(5)
          }
        } else {
          this.error = '网络错误'
        }
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 380px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.login-card h1 {
  margin: 0 0 30px;
  text-align: center;
  color: #1a1a1a;
  font-size: 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  color: #333;
  font-size: 14px;
}

.form-group input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
}

.error-msg {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fff2f0;
  color: #ff4d4f;
  border-radius: 4px;
  font-size: 13px;
}

.btn-login {
  width: 100%;
  margin-top: 8px;
  padding: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 16px;
}

.btn-login:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
