import { defineStore } from 'pinia'
import { adminApi } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    ready: false,
    authenticated: false,
    loading: false,
    user: null,
  }),
  actions: {
    async bootstrap() {
      if (this.ready || this.loading) {
        return
      }
      this.loading = true
      adminApi.setAccessToken(adminApi.getAccessToken())
      try {
        const me = await adminApi.me()
        this.user = me
        this.authenticated = true
      } catch {
        try {
          const refreshed = await adminApi.refresh()
          this.user = refreshed.user
          this.authenticated = true
        } catch {
          this.user = null
          this.authenticated = false
          adminApi.setAccessToken('')
        }
      } finally {
        this.ready = true
        this.loading = false
      }
    },
    async login(payload) {
      this.loading = true
      try {
        const data = await adminApi.login(payload)
        adminApi.setAccessToken(data.access_token)
        this.user = data.user
        this.authenticated = true
        return data
      } finally {
        this.ready = true
        this.loading = false
      }
    },
    async logout() {
      this.loading = true
      try {
        await adminApi.logout()
      } finally {
        this.user = null
        this.authenticated = false
        this.loading = false
      }
    },
  },
})
