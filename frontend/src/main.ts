import { createApp } from 'vue'
import './style.css'
// Side-effect: installs auth interceptors on the global axios and the
// api instance (see src/api.ts).
import './api'
import App from './App.vue'

createApp(App).mount('#app')
