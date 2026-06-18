import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/useAuth'
import './styles/app.css'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const pinia = createPinia()
const app = createApp(App)

useAuthStore(pinia).loadUser()

app.use(pinia)
app.use(router)
app.mount('#app')
