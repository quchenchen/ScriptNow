import { createApp } from 'vue'
import { installLocaleDirective } from '@scriptnow/shared'

import App from './App.vue'
import './style.css'

const app = createApp(App)
installLocaleDirective(app)
app.mount('#app')
