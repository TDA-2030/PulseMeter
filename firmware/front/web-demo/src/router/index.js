import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('../views/HomeView.vue') },
  { path: '/control', component: () => import('../views/ControlView.vue') },
  { path: '/analysis', component: () => import('../views/AnalysisView.vue') }
]

export default createRouter({
  history: createWebHistory(),
  routes
})