
// main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia' // 状态管理
import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify' // Vuetify 配置

// 创建 Vue 应用实例
const app = createApp(App)

// 注册插件
app.use(createPinia())  // 注册 Pinia
app.use(router)         // 注册路由
app.use(vuetify)        // 注册 Vuetify


// 挂载应用到 DOM
app.mount('#app')