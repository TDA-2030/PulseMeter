<template>
  <v-container fluid>
    <v-row>
      <!-- 实时数据展示 -->
      <v-col cols="12" md="5" v-for="(panel, name) in realtimeData" :key="name">
        <v-card>
          <v-card-title>{{name}}</v-card-title>
          <v-card-text>
            <v-row>
              <v-col v-for="(value, key) in panel" :key="key" cols="6">
                <v-card variant="outlined">
                  <v-card-text class="text-center">
                    <div class="text-h6">{{ key }}</div>
                    <div class="text-h4 text-primary">{{ value }}</div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- 图表展示 -->
      <v-col cols="12" md="6">
        <v-card>
          <v-card-title>Realtime Data</v-card-title>
          <v-card-text>
            <v-container>
              <h3>Angle</h3>
              <v-sparkline v-for="(axis, index) in axisName" :key="index" 
                :gradient="['#f72047',]" :smooth="2" :padding="8" :line-width="1" auto-draw
                class="sparkline" :model-value="getAngleData(index)"></v-sparkline>

              <v-row no-gutters v-for="(axis, index) in axisName" :key="index" class="pa-3"
                :style="{ color: axis.color }">
                <v-col cols="12" sm="5">
                  <strong>Acceleration {{ axis.name }}:</strong> {{ accelerationData[accelerationData.length - 1][axis.name.toLocaleLowerCase()] }}
                </v-col>
                <v-col cols="12" sm="5">
                  <strong>Angle {{ axis.name }}:</strong> {{ angleData[angleData.length - 1][axis.name.toLocaleLowerCase()] }}
                </v-col>
              </v-row>
            </v-container>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
  <v-footer color="primary" app fixed>
      <span class="white--text">Local Time: {{ serverTime }}</span>
  </v-footer>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useSolarStore } from '../stores/solarStore'
import { storeToRefs } from 'pinia'
import axios from 'axios'
import { formatTimestamp } from '../utils/typeConversion'

const store = useSolarStore()
const { realtimeData, accelerationData, angleData } = storeToRefs(store)


const axisName = [
  { name: 'X', color: 'red' },
  { name: 'Y', color: 'green' },
  { name: 'Z', color: 'blue' }
]

let serverTime = ref('00:00:00')

// Expected data format:
// {
//   acceleration: { time: 'HH:mm:ss', x: number, y: number, z: number },
//   angle: { time: 'HH:mm:ss', x: number, y: number, z: number }
// }
// Fetch data from API and update store
const fetchData = () => {
  axios.get('/api/v1/temp/raw')
    .then(response => {
      const data = response.data
      store.updateRealData(data)
      serverTime.value = formatTimestamp(data.panel.time)
      delete data.panel.time // Remove time from panel data
    })
    .catch(error => {
      console.error('Error fetching data:', error)
    })
}

let intervalId

onMounted(() => {
  console.log('HomeView mounted')
  intervalId = setInterval(fetchData, 150)

  // Get current location and time
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition((position) => {
      const now = new Date()
      const locationData = {
        latitude: Number(position.coords.latitude),
        longitude: Number(position.coords.longitude),
        utctime: {
          year: now.getUTCFullYear(),
          month: now.getUTCMonth() + 1, // getUTCMonth() returns 0-11
          day: now.getUTCDate(),
          hours: now.getUTCHours(),
          minutes: now.getUTCMinutes(),
          seconds: now.getUTCSeconds()
        }
      }
      
      // Send location data to server
      axios.post('/api/v1/location', locationData)
        .then(response => {
          console.log('Location data sent successfully:', response.data)
        })
        .catch(error => {
          console.error('Error sending location data:', error)
        })
    }, (error) => {
      console.error('Error getting location:', error)
    })
  } else {
    console.error('Geolocation is not supported by this browser')
  }
})

onUnmounted(() => {
  console.log('HomeView unmounted')
  clearInterval(intervalId)
})

const getAngleData = (index) => {
  return angleData.value.map(data => data[axisName[index].name.toLowerCase()])
}

</script>

<style scoped>
.sparkline {
  border: 1px solid #000;
  border-radius: 2px;
  padding: 4px;
  margin-bottom: 5px;
}
</style>