import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'
import './workflow.css'
const app = createApp(App)
app.use(router)
void router.isReady().then(() => app.mount('#app'))
