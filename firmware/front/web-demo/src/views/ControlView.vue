<template>
  <v-container>
    <v-row>
      <!-- 模式控制 -->
      <v-col cols="12" >
        <v-row align="center">
          <v-col cols="6">
            <v-radio-group v-model="mode" inline>
              <v-radio label="Manual Mode" value="manual"></v-radio>
              <v-radio label="Toward Mode" value="toward"></v-radio>
              <v-radio label="Reflect Mode" value="reflect"></v-radio>
            </v-radio-group>
          </v-col>
          <v-col cols="6" class="text-right">
            <v-btn class="mr-4" color="warning" variant="elevated" @click="restartServer">
              Restart
            </v-btn>
            <v-btn class="mr-4" color="teal" variant="elevated" @click="readSettingData">
              Load
            </v-btn>
            <v-btn color="amber" variant="elevated" @click="sendSettingData">
              Save
            </v-btn>
          </v-col>
        </v-row>
      </v-col>

      <!-- 角度控制 -->
      <v-col cols="12" md="6">
        <v-card>
          <v-card-title>Angle Control</v-card-title>
          <v-card-text>
            <v-slider v-model="controlData.man.yaw" label="Azimuth" min="-180" max="180" step="1" thumb-label="always"
              :disabled="mode === 'toward'"></v-slider>

            <v-slider v-model="controlData.man.pitch" label="Elevation" min="-90" max="90" step="1" thumb-label="always"
              :disabled="mode === 'toward'"></v-slider>
            <v-text-field v-model="controlData.yaw_offset" label="Yaw Offset Angle (°)" type="number"></v-text-field>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- 阈值设置 -->
      <v-col cols="12" md="6">
        <v-card>
          <v-card-title>Threshold Settings</v-card-title>
          <v-card-text>
            <v-range-slider v-model="voltageRange" label="Voltage Range" min="4" max="14" step="0.1" thumb-label="always"></v-range-slider>
          </v-card-text>

        </v-card>
      </v-col>

      <!-- PID控制器设置 -->
      <v-col cols="12" md="6" v-for="(piditem, pidname) in controlData.pid ":key="pidname">
        <v-card>
          <v-card-title>{{ pidname }} PID Control</v-card-title>
          <v-card-text>
            <v-slider v-for="(value, key) in piditem" :label="key" v-model="piditem[key]" min="0" :max="pid_param_max[pidname][key]" step="0.01" thumb-label="always">
              <template v-slot:append>
              <v-text-field v-model="pid_param_max[pidname][key]" density="compact" style="width: 85px; height: 30px" type="number" hide-details single-line ></v-text-field>
            </template>
            </v-slider>
          </v-card-text>
        </v-card>
      </v-col>

    </v-row>
  </v-container>
</template>

<script setup>
import { onMounted, onUnmounted} from 'vue'
import { computed, ref } from 'vue' // 添加 computed 导入
import { useSolarStore } from '../stores/solarStore'
import { storeToRefs } from 'pinia'
import axios from 'axios'
import { convertToNumbers } from '../utils/typeConversion'

const store = useSolarStore()
const { controlData } = storeToRefs(store)

const mode = computed({
  get: () => controlData.value.mode,
  set: (val) => {
    controlData.value.mode = val
  }
})

const voltageRange = computed({
  get: () => [controlData.value.th.minv, controlData.value.th.maxv],
  set: (val) => {
    controlData.value.th.minv = val[0]
    controlData.value.th.maxv = val[1]
  }
})

const pid_param_max = ref({
    pos: { p: 1000, i: 1000, d: 10, maxout: 1000, maxitg: 1000 },
    vel: { p: 30, i: 100, d: 10, maxout: 1000, maxitg: 1000 },
    pitch_pos: { p: 200, i: 100, d: 1, maxout: 1000, maxitg: 1000 },
    pitch_vel: { p: 200, i: 100, d: 1, maxout: 1000, maxitg: 1000 },
})

onMounted(() => {
  console.log('ControlView mounted')
  readSettingData()
})

const sendSettingData = () => {
  const _data = convertToNumbers(controlData.value);
  axios.post("/api/v1/setting", _data )
    .then(data => {
      console.log(data.data);
    })
    .catch(error => {
      console.log(error);
    });
}

const readSettingData = () => {
  axios.get('/api/v1/setting')
    .then(response => {
      const data = response.data
      store.updateSettingData(data)
    })
    .catch(error => {
      console.error('Error fetching data:', error)
    })
}

const restartServer = () => {
  // check user confirm
  if (confirm("Are you sure you want to restart the server?")) {
    axios.post('/api/v1/sysctrl', { restart: 1 })
    .then(response => {
      console.log('Server restarted:', response.data)
    })
    .catch(error => {
      console.error('Error restarting server:', error)
    })
  }
}
</script>
