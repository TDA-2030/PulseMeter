<template>
    <v-container>
      <v-card>
        <v-card-title>
          <v-row>
            <v-col cols="12" md="4">
              <v-date-picker v-model="dateRange" range></v-date-picker>
            </v-col>
            <!-- <v-col cols="12" md="8">
              <LineChart :data="historicalData" />
            </v-col> -->
          </v-row>
        </v-card-title>
      </v-card>
    </v-container>
  </template>
  
  <script setup>
  import { ref } from 'vue'
  import LineChart from '../components/LineChart.vue'
  
  const dateRange = ref([])
  const historicalData = ref({
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May'],
    datasets: [
      { label: 'Energy Production', data: [65, 59, 80, 81, 56] },
      { label: 'Sun Hours', data: [28, 48, 40, 19, 86] }
    ]
  })
  </script>