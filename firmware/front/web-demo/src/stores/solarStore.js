import { defineStore } from 'pinia'

export const useSolarStore = defineStore('solar', {
  state: () => ({
    angleData: Array(20).fill({ x: 0, y: 0, z: 0 }),
    accelerationData: Array(20).fill({ x: 0, y: 0, z: 0 }),
    realtimeData: {
      panel: {
        azimuth: 45,
        elevation: 30,
      },
    },
    controlData:
    {
      pid:{
          pos:{
              p:0.1,
              i:0.1,
              d:0.1,
              maxout:100,
              maxitg:100,
          },
      },
      mode:"auto",
      th:{
          maxv:12.1,
          minv:10.1,
      },
      man:{
          pitch:20,
          yaw:30,
      },
      yaw_offset:0,
    },
  }),
  actions: {
    updateRealData(newValues) {
      this.angleData.push(newValues.angle)
      if (this.angleData.length > 20) {
        this.angleData.shift()
      }

      this.accelerationData.push(newValues.acc)
      if (this.accelerationData.length > 20) {
        this.accelerationData.shift()
      }
      delete newValues.angle
      delete newValues.acc
      this.realtimeData = { ...this.realtimeData, ...newValues };
    },
    updateSettingData(newSet) {
      this.controlData = newSet
    },
  },
  getters: {
    // Remove unused getters
    // angleDataX: (state) => state.angleData.map(data => data.x),
    // angleDataY: (state) => state.angleData.map(data => data.y),
    // angleDataZ: (state) => state.angleData.map(data => data.z)
  },
  
})