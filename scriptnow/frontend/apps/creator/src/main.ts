import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { installLocaleDirective } from '@scriptnow/shared'

import App from './App.vue'
import { router } from './router'
import './style.css'

const app = createApp(App)
installLocaleDirective(app)
app.use(createPinia()).use(router).mount('#app')
