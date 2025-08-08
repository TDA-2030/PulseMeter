import { createVuetify } from 'vuetify'

// import 'material-design-icons-iconfont/dist/material-design-icons.css' // Ensure your project is capable of handling css files

import 'vuetify/styles'

import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'

// 可选的主题配置
const myCustomTheme = {
    dark: false, // 设置为 false 表示亮色模式，true 则为暗色模式
    colors: {
      primary: '#19b092',  // 主要颜色
      secondary: '#b0f092', // 次要颜色
      accent: '#FF4081',    // 强调色
      error: '#FF5252',     // 错误颜色
      info: '#2196F3',      // 信息颜色
      success: '#4CAF50',   // 成功颜色
      warning: '#FB8C00',   // 警告颜色
      on_surface: '#000000', // 导航抽屉文字颜色
    },
  }

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'myCustomTheme',
    themes: {
      myCustomTheme,
    }
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: {
      mdi,
    },
  },
  
})
